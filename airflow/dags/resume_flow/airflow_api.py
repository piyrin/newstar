"""Minimal Airflow 3 public API client; no arbitrary DAGs or remote plain HTTP."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_DAGS = {'resume_start', 'resume_prepare', 'resume_export', 'skill_experiment'}


class ApiError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(f'Airflow HTTP {code}；请检查登录配置、DAG 和运行标识')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class AirflowClient:
    def __init__(self, base_url=None, username=None, password=None, token=None):
        self.base = (base_url or os.environ.get('AIRFLOW_API_URL', 'http://localhost:8080')).rstrip('/')
        url = urllib.parse.urlsplit(self.base)
        if (url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path not in ('', '/')
                or (url.scheme == 'http' and url.hostname not in ('localhost', '127.0.0.1', '::1', 'airflow-apiserver'))):
            raise ValueError('AIRFLOW_API_URL 需为本机 HTTP 或 HTTPS 服务根地址')
        self.username = username or os.environ.get('AIRFLOW_API_USERNAME', '')
        self.password = password or os.environ.get('AIRFLOW_API_PASSWORD', '')
        self.token = token or os.environ.get('AIRFLOW_API_TOKEN', '')
        self.static_token = bool(self.token)
        self.opener = urllib.request.build_opener(NoRedirect())

    def _send(self, method, path, payload=None, auth=True, refreshed=False):
        if auth and not self.token:
            if not self.username or not self.password:
                raise ValueError('配置 AIRFLOW_API_TOKEN 或 AIRFLOW_API_USERNAME/AIRFLOW_API_PASSWORD')
            result = self._send('POST', '/auth/token', {'username': self.username, 'password': self.password}, auth=False)
            if not isinstance(result.get('access_token'), str) or not result['access_token']:
                raise ValueError('Airflow 未返回有效登录令牌')
            self.token = result['access_token']
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + self.token
        body = None if payload is None else json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(self.base + path, body, headers, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('Airflow 响应过大')
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError('Airflow 响应结构无效')
            return result
        except urllib.error.HTTPError as error:
            if error.code == 401 and auth and not refreshed and not self.static_token and self.username and self.password:
                self.token = ''
                return self._send(method, path, payload, auth=True, refreshed=True)
            raise ApiError(error.code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ValueError('Airflow 连接失败或超时；请确认平台已启动') from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError('Airflow 返回无效 JSON') from None

    def _path(self, dag_id, run_id=None):
        if dag_id not in ALLOWED_DAGS:
            raise ValueError('不允许调用此 DAG')
        path = '/api/v2/dags/' + dag_id + '/dagRuns'
        if run_id is not None:
            if (not isinstance(run_id, str) or not run_id or len(run_id) > 250
                    or any(ord(char) < 32 for char in run_id)):
                raise ValueError('运行标识无效')
            path += '/' + urllib.parse.quote(run_id, safe='')
        return path

    def trigger(self, dag_id, run_id, conf):
        path = self._path(dag_id, run_id)
        try:
            return self._send('POST', self._path(dag_id),
                              {'dag_run_id': run_id, 'logical_date': None, 'conf': conf})
        except ApiError as error:
            if error.code != 409:
                raise
            existing = self._send('GET', path)
            if existing.get('conf') != conf:
                raise ValueError('请求 ID 已用于不同参数，请换一个 request-id') from None
            return existing

    def status(self, dag_id, run_id):
        path = self._path(dag_id, run_id)
        run = self._send('GET', path)
        tasks = self._send('GET', path + '/taskInstances')
        return {'dag_id': dag_id, 'dag_run_id': run_id, 'state': run.get('state'),
                'tasks': [{'task_id': t.get('task_id'), 'state': t.get('state'),
                           'try_number': t.get('try_number')} for t in tasks.get('task_instances', [])]}

    def resume_review(self, run_id):
        """Requeue only the old skipped review gate and its export descendants."""
        self._path('resume_prepare', run_id)
        return self._send('POST', '/api/v2/dags/resume_prepare/clearTaskInstances', {
            'dag_run_id': run_id, 'task_ids': ['await_review', 'verify_and_freeze',
                'render_word', 'export_pdf', 'check_pages'],
            'dry_run': False, 'only_failed': False, 'reset_dag_runs': True,
            'run_on_latest_version': True, 'prevent_running_task': True,
            'note': 'Resume the original human-review run after explicit confirmation',
        })

    def cancel_waiting(self, dag_id, run_id):
        """End an idle run, preserving its history and all finished runs.

        Airflow 3.3.2 DAGRunPatchBody accepts state=failed. Its public PATCH
        handler invokes set_dag_run_state_to_failed, never task success.
        Only known waiting sensors may currently be executing.
        """
        path = self._path(dag_id, run_id)
        try:
            run = self._send('GET', path)
        except ApiError as error:
            if error.code != 404:
                raise
            return {'result': 'already_finished', 'state': 'not_found'}
        state = run.get('state')
        if state in ('success', 'failed'):
            return {'result': 'already_finished', 'state': state}
        if state not in ('queued', 'running'):
            raise ValueError('工作流状态无法确认，请刷新后重试删除')
        tasks, offset = [], 0
        while True:
            suffix = '' if offset == 0 else '?offset=' + str(offset)
            page = self._send('GET', path + '/taskInstances' + suffix)
            batch = page.get('task_instances')
            if not isinstance(batch, list):
                raise ValueError('无法确认工作流任务状态，请稍后重试')
            tasks.extend(batch)
            offset += len(batch)
            total = page.get('total_entries', offset)
            if not isinstance(total, int) or total > 10000:
                raise ValueError('工作流任务数量无效')
            if offset >= total:
                break
            if not batch:
                raise ValueError('工作流任务状态未完整返回，请重试')
        waiting = {'resume_start': {'await_materials'},
                   'resume_prepare': {'await_review', 'await_materials'}, 'resume_export': set()}[dag_id]
        for task in tasks:
            if task.get('state') in ('running', 'restarting') and task.get('task_id') not in waiting:
                raise ValueError('任务 ' + str(task.get('task_id')) + ' 正在执行，请等待结束后重试删除')
        # Airflow has no conditional PATCH. Recheck completion before mutation,
        # and use the workspace draft guard for application-controlled writes.
        current = self._send('GET', path)
        if current.get('state') in ('success', 'failed'):
            return {'result': 'already_finished', 'state': current['state']}
        if current.get('state') not in ('queued', 'running'):
            raise ValueError('工作流状态已变化，请刷新后重试删除')
        result = self._send('PATCH', path + '?update_mask=state', {'state': 'failed'})
        if result.get('state') != 'failed':
            raise ValueError('Airflow 尚未确认工作流停止，请重试删除')
        return {'result': 'stopped', 'state': 'failed'}
