"""Local browser workspace: prepare, review, Airflow export and checked downloads."""
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .airflow_api import AirflowClient
from .natural import workflow_status
from .review import current_state, save_review, approve, verify_approval, get_status
from .storage import digest, file_hash, inside, read_json, validate_id, write_json
from .flow_control import review_workflow, submit_reviewed_export
from .intake import get_intake, list_intakes, open_intake, submit_intake, intake_path, cancel_intake
from .drafts import is_deleted, list_deleted, delete_draft, restore_draft, draft_guard, ensure_active


def jobs(workspace):
    cases, runs = [], []
    root = Path(workspace)
    for p in sorted((root / 'inputs').glob('*')):
        if p.is_dir() and not p.is_symlink():
            try:
                cases.append(validate_id(p.name))
            except ValueError:
                pass
    folders = sorted((root / 'reviews').glob('*'), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in folders[:100]:
        if not p.is_dir() or p.is_symlink():
            continue
        try:
            if is_deleted(root, p.name):
                continue
            status = get_status(root, validate_id(p.name))
            grouped = current_state(root, p.name)['question_groups']
            status['pending_groups'] = sum(any(q.get('resolution') not in ('confirmed','omitted')
                                              or (q.get('resolution') == 'omitted' and not q.get('note','').strip())
                                              for q in group['questions']) for group in grouped
                                           if group['fact_ids'] or not group['text'].startswith('缺少联系方式'))
            config = read_json(inside(root, 'runs', p.name, 'manifest.json'))['config']
            flow = review_workflow(root, p.name)
            if flow:
                status['workflow'] = {'dag_id': flow['dag_id'], 'dag_run_id': flow['dag_run_id']}
                status['review_url'] = flow['review_url']
            runs.append({**status, 'target': config['target'], 'case_id': config['case_id'], 'updated_at': p.stat().st_mtime})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    guide = root / 'browser-guide.json'
    connected = guide.is_file() and time.time() - read_json(guide).get('heartbeat', 0) < 15
    deleted = list_deleted(workspace)
    for record in deleted:
        manifest = inside(root, 'runs', record['run_key'], 'manifest.json')
        if manifest.is_file():
            config = read_json(manifest)['config']
            record.update(target=config.get('target', ''), case_id=config.get('case_id', ''))
    return {'cases': cases, 'runs': runs, 'intakes': list_intakes(workspace),
            'deleted_drafts': deleted, 'browser_guide_connected': connected}


def make_portal(workspace, port=0, host='127.0.0.1', fixed_run_key=None, api=None):
    workspace = Path(workspace)
    token, lock = secrets.token_urlsafe(32), threading.Lock()
    assets = Path(__file__).parent / 'web'
    client = api or AirflowClient()
    from . import skill_jobs

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, value, mime='application/json; charset=utf-8', download=None):
            raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'")
            if download:
                self.send_header('Content-Disposition', 'attachment; filename="' + download + '"')
            self.end_headers()
            self.wfile.write(raw)

        def same_origin(self):
            hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            authority = self.headers.get('Host', '')
            return (authority in hosts and self.headers.get('Origin') in (None, 'http://' + authority)
                    and self.headers.get('Sec-Fetch-Site') not in ('cross-site',))

        def authorized(self):
            valid = self.same_origin() and hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token)
            if not valid:
                self.send(403, {'error': '会话失效，请从本机工作台重新打开'})
            return valid

        def query(self):
            return {k: v[-1] for k, v in parse_qs(urlsplit(self.path).query).items()}

        def key(self):
            return validate_id(fixed_run_key or self.query().get('run_key'))

        def status(self, key):
            result = get_status(workspace, key)
            flow = review_workflow(workspace, key, self.query().get('dag_run_id'))
            path = inside(workspace, 'web_requests', key + '.json')
            request = read_json(path) if path.exists() else None
            continued = request and flow and request.get('review_dag_run_id') == flow['dag_run_id']
            if flow and not flow.get('approval_hash') and not continued:
                execution = client.status('resume_prepare', flow['dag_run_id'])
                if execution['state'] in ('running', 'queued'):
                    return {'state': 'waiting_review', 'run_key': key, 'synthetic': result['synthetic'],
                            'pending_questions': result['pending_questions'], 'execution': execution, 'files': []}
            if request:
                try:
                    approval = verify_approval(workspace, key)
                except (ValueError, OSError):
                    return result
                if request['approval_hash'] == approval['content_hash']:
                    result['request'] = request
                    result.pop('report', None)
                    result['export_key'] = request['export_key']
                    execution = client.status(request.get('dag_id', 'resume_export'), request['dag_run_id'])
                    result['execution'] = execution
                    result['state'] = 'failed' if execution['state'] == 'failed' else 'approved'
                    folder = inside(workspace, 'outputs', request['export_key'])
                    if execution['state'] != 'success' or not (folder / 'report.json').is_file():
                        result['files'] = []
                        if execution['state'] == 'success':
                            result['state'] = 'failed'
                            result['error'] = '工作流已结束，但未生成导出报告，请重新确认导出'
                        elif execution['state'] == 'failed' and (folder / 'report.json').is_file():
                            result['report'] = read_json(folder / 'report.json')
                            result['error'] = result['report'].get('failure_message', '导出失败，请检查工作流任务日志')
                        return result
                    report = read_json(folder / 'report.json')
                    result['state'] = report['state']
                    if (folder / 'visual-acceptance.json').is_file():
                        accepted = read_json(folder / 'visual-acceptance.json')
                        hashes = report.get('artifact_hashes', {})
                        if (accepted.get('report_hash') == digest(report) and hashes
                                and all(file_hash(inside(folder, name)) == expected for name, expected in hashes.items())):
                            result['state'] = 'final'
                    result.pop('execution', None)
            if result.get('export_key'):
                folder = inside(workspace, 'outputs', result['export_key'])
                report = read_json(folder / 'report.json')
                result['report'] = report
                result['directory'] = 'D:\\code\\newstar\\airflow\\resume_workspace\\outputs\\' + result['export_key']
                result['files'] = list(report.get('artifact_hashes', {})) if report.get('ok') else []
            return result

        def do_GET(self):
            path = urlsplit(self.path).path
            static = {'/': 'index.html' if fixed_run_key else 'portal.html', '/review': 'index.html',
                      '/app.js': 'app.js', '/style.css': 'style.css', '/template.css': 'template.css',
                      '/portal.js': 'portal.js', '/portal.css': 'portal.css',
                      '/skills': 'skills.html', '/skills.js': 'skills.js', '/skills.css': 'skills.css'}
            if path in static:
                name = static[path]
                mime = {'html': 'text/html', 'js': 'text/javascript', 'css': 'text/css'}[name.rsplit('.', 1)[1]]
                self.send(200, (assets / name).read_bytes(), mime + '; charset=utf-8')
                return
            if path == '/api/session':
                if self.same_origin() and self.headers.get('X-Resume-Portal') == '1' and not fixed_run_key:
                    self.send(200, {'token': token})
                else:
                    self.send(403, {'error': '请从本机工作台进入'})
                return
            if not self.authorized():
                return
            try:
                if path == '/api/skills/catalog':
                    result = skill_jobs.catalog(workspace)
                elif path == '/api/skills/job':
                    result = skill_jobs.detail(workspace, self.query().get('job_id'), client)
                elif path == '/api/skills/file':
                    q = self.query()
                    target = skill_jobs.download(workspace, q.get('job_id'), q.get('name'))
                    if q.get('preview') == '1':
                        if target.stat().st_size > 2_000_000:
                            raise ValueError('文件较大，请下载查看')
                        self.send(200, {'name': target.name, 'content': target.read_text(encoding='utf-8-sig')})
                    else:
                        self.send(200, target.read_bytes(), 'application/octet-stream', target.name)
                    return
                elif path == '/api/jobs':
                    result = jobs(workspace)
                elif path == '/api/intakes':
                    result = {'intakes': list_intakes(workspace)}
                elif path == '/api/intake':
                    result = get_intake(workspace, self.query().get('intake_id'))
                    if result['state'] == 'submitted':
                        from .airflow_api import ApiError
                        try:
                            result['child'] = client.status('resume_prepare', result['child_run_id'])
                        except ApiError as error:
                            if error.code != 404:
                                raise
                elif path == '/api/state':
                    result = current_state(workspace, self.key())
                elif path == '/api/photo':
                    photo = inside(workspace, 'reviews', self.key(), 'photo.jpg')
                    state = current_state(workspace, self.key())
                    if state['resume'].get('photo') != 'photo.jpg' or not photo.is_file():
                        self.send(404, {'error': '当前未选择照片'})
                        return
                    self.send(200, photo.read_bytes(), 'image/jpeg')
                    return
                elif path == '/api/export-status':
                    result = self.status(self.key())
                elif path == '/api/run':
                    q = self.query()
                    result = workflow_status(workspace, client, q.get('dag_id'), q.get('dag_run_id'))
                    result['url'] = 'http://localhost:8080/dags/' + result['dag_id'] + '/runs/' + result['dag_run_id']
                elif path == '/api/file':
                    q, key = self.query(), self.key()
                    name = q.get('name', '')
                    if name not in ('resume.docx', 'resume.pdf') and not re.fullmatch(r'page-[1-9][0-9]*\.png', name):
                        raise ValueError('不允许访问该文件')
                    folder = inside(workspace, 'outputs', validate_id(q.get('export_key')))
                    record, report = read_json(folder / 'input.json'), read_json(folder / 'report.json')
                    target = inside(folder, name)
                    if (record['run_key'] != key or not report.get('ok') or
                            report.get('artifact_hashes', {}).get(name) != file_hash(target)):
                        raise ValueError('文件未通过检查、版本不匹配或文件已改动')
                    mime = 'image/png' if name.endswith('.png') else ('application/pdf' if name.endswith('.pdf') else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
                    self.send(200, target.read_bytes(), mime, None if name.endswith('.png') else name)
                    return
                else:
                    self.send(404, {'error': '未找到页面'})
                    return
                self.send(200, result)
            except (ValueError, OSError, KeyError, TypeError) as error:
                self.fail(error)

        def fail(self, error):
            result = {'error': str(error) if isinstance(error, ValueError) else '文件暂不可用，请检查任务状态'}
            try:
                result['state'] = current_state(workspace, self.key())
            except (ValueError, OSError, KeyError, TypeError):
                pass
            self.send(400, result)

        def do_POST(self):
            if not self.authorized():
                return
            try:
                path = urlsplit(self.path).path
                length = int(self.headers.get('Content-Length', '0'))
                limit = 28_000_000 if path == '/api/import' else (3_000_000 if path == '/api/photo' else 300000)
                if not 0 < length <= limit:
                    raise ValueError('请求体大小无效')
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError('请求必须是对象')
                draft_operations = {'/api/save', '/api/approve', '/api/photo', '/api/export', '/api/accept', '/api/project-preview'}
                key = self.key() if path in draft_operations else None
                with lock, (draft_guard(workspace, key) if key else nullcontext()):
                    if key:
                        ensure_active(workspace, key)
                    if path == '/api/skills/start':
                        result = skill_jobs.start(workspace, payload, client)
                    elif path == '/api/skills/review':
                        result = skill_jobs.record_review(workspace, payload.get('job_id'), payload)
                    elif path == '/api/draft-delete':
                        result = delete_draft(workspace, validate_id(payload.get('run_key')), client)
                    elif path == '/api/draft-restore':
                        result = restore_draft(workspace, validate_id(payload.get('run_key')))
                    elif path == '/api/project-preview':
                        from .project_edit import adopt_project_items
                        state = current_state(workspace, key)
                        if payload.get('revision') != state['revision']:
                            raise ValueError('审阅内容已变化，请刷新页面后再保存')
                        ids = payload.get('fact_ids')
                        if not isinstance(ids, list) or not ids or any(not isinstance(fid, str) for fid in ids):
                            raise ValueError('请选择需要采用的项目事实')
                        facts = [fact for fact in state['facts'] if fact['id'] in ids and fact['field'] == 'project']
                        if {fact['id'] for fact in facts} != set(ids):
                            raise ValueError('项目事实与当前材料不匹配')
                        resume = payload.get('resume')
                        contribution = payload.get('contribution', '')
                        if not isinstance(resume, dict) or not isinstance(resume.get('sections'), list) or not isinstance(contribution, str) or len(contribution) > 10000:
                            raise ValueError('项目编辑内容无效')
                        sources = {fact['source'] for fact in facts}
                        segments = read_json(inside(workspace, 'runs', key, 'extracted.json'))['segments']
                        source_text = '\n'.join(segment['text'] for segment in segments if segment['source'] in sources)
                        result = {'resume': adopt_project_items(resume, facts, source_text, contribution)}
                    elif path == '/api/intake-cancel':
                        result = cancel_intake(workspace, payload.get('intake_id'), client)
                    elif path == '/api/intake-submit':
                        result = submit_intake(workspace, payload.get('intake_id'), payload, client)
                    elif path == '/api/intake-opened':
                        record = get_intake(workspace, payload.get('intake_id'))
                        write_json(intake_path(workspace, record['id']), {**record, 'opened': True})
                        result = {'ok': True}
                    elif path in ('/api/save', '/api/approve'):
                        key = self.key()
                        save_review(workspace, key, payload)
                        if path == '/api/approve':
                            approve(workspace, key)
                        result = {'ok': True, 'state': current_state(workspace, key)}
                    elif path == '/api/import':
                        from .materials import import_materials
                        result = import_materials(workspace, payload)
                    elif path == '/api/github':
                        from .github_materials import import_github
                        result = import_github(workspace, payload)
                    elif path == '/api/photo':
                        from .photos import save_photo
                        result = {'ok': True, 'state': save_photo(workspace, self.key(), payload)}
                    elif path == '/api/prepare':
                        case = validate_id(payload.get('case_id'))
                        mode, target, jd = payload.get('mode', 'deepseek'), payload.get('target', ''), payload.get('jd', '')
                        if case not in jobs(workspace)['cases'] or mode not in ('deepseek', 'offline') or not isinstance(target, str) or len(target) > 200:
                            raise ValueError('材料案例、岗位或模式无效')
                        if not isinstance(jd, str) or len(jd) > 20000:
                            raise ValueError('岗位要求格式无效')
                        request_id = validate_id(payload.get('request_id') or uuid.uuid4().hex)
                        run_id = 'web-' + request_id
                        conf = {'case_id': case, 'target': target, 'mode': mode, 'jd': jd, 'run_key': ''}
                        run = client.trigger('resume_prepare', run_id, conf)
                        result = {'dag_id': 'resume_prepare', 'dag_run_id': run_id, 'state': run.get('state')}
                    elif path == '/api/export':
                        key = self.key()
                        request_id = validate_id(payload.get('request_id') or uuid.uuid4().hex)
                        result = submit_reviewed_export(workspace, key, request_id, client, self.query().get('dag_run_id'))
                    elif path == '/api/accept':
                        from .export import accept_visual
                        key = self.key()
                        if payload.get('confirm_all_pages') is not True:
                            raise ValueError('请先逐页查看并明确确认')
                        export_key = validate_id(payload.get('export_key'))
                        if read_json(inside(workspace, 'outputs', export_key, 'input.json'))['run_key'] != key:
                            raise ValueError('导出版本不匹配')
                        result = accept_visual(workspace, export_key)
                    else:
                        self.send(404, {'error': '未找到操作'})
                        return
                self.send(200, result)
            except (ValueError, OSError, KeyError, TypeError) as error:
                self.fail(error)

    return ThreadingHTTPServer((host, port), Handler), token


def main():
    from .config import load_env
    load_env(Path(__file__).resolve().parents[2] / '.env')
    ws = Path(os.environ.get('RESUME_WORKSPACE', Path(__file__).resolve().parents[2] / 'resume_workspace'))
    server, _ = make_portal(ws, int(os.environ.get('RESUME_PORTAL_PORT', '8765')),
                            os.environ.get('RESUME_PORTAL_BIND', '127.0.0.1'))
    print('简历工作台：http://localhost:8765', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
