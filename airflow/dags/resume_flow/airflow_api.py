"""Minimal Airflow 3 public API client; no arbitrary DAGs or remote plain HTTP."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_DAGS = {'resume_prepare', 'resume_export'}


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
        self.opener = urllib.request.build_opener(NoRedirect())

    def _send(self, method, path, payload=None, auth=True):
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
            if not isinstance(run_id, str) or not run_id or len(run_id) > 250:
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
