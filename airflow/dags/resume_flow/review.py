"""Explicit, content-bound human review. Local HTTP UI never calls a model."""
import hmac
import json
import secrets
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .storage import digest, file_hash, inside, read_json, review_dir, run_dir, verify_sources, write_json
from .workflow import validate_resume


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_selection(value):
    if not isinstance(value, dict) or value.get('schema_version') != 1:
        raise ValueError('请先选择模板')
    for key, choices in [('template_id', ('classic', 'minimal', 'technical')),
                         ('mode', ('print', 'digital')), ('paper', ('A4', 'Letter'))]:
        if value.get(key) not in choices:
            raise ValueError('模板选择无效：' + key)


def prepare_review(workspace: Path, run_key: str) -> str:
    directory, target = run_dir(workspace, run_key), review_dir(workspace, run_key)
    bundle = read_json(directory / 'facts.json')
    target.mkdir(parents=True, exist_ok=True)
    # Retries must not erase a user's edits or decisions.
    for name, data in [('resume.json', read_json(directory / 'resume.draft.json')),
                       ('questions.json', bundle['questions'])]:
        if not (target / name).exists():
            write_json(target / name, data)
    lines = ['# 待确认项', '', '请在本机审阅页处理问题；此文件只作阅读。', '']
    lines.extend(f"- {q['id']}：{q['text']}" for q in bundle['questions'])
    (directory / 'questions.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    facts = ['# 事实与来源', '']
    facts.extend(f"- {f['id']} [{f['field']}] {f['value']}\n  来源：{f['source']} / {f['location']}\n  原文：{f['quote']}\n  状态：{f['status']}；归属：{f['ownership']}"
                 for f in bundle['facts'])
    (directory / 'facts.md').write_text('\n'.join(facts) + '\n', encoding='utf-8')
    write_json(directory / 'status.json', {'state': 'waiting_input' if bundle['questions'] else 'waiting_review',
                                          'synthetic': bundle['synthetic']})
    return run_key


def current_state(workspace, run_key):
    folder = review_dir(workspace, run_key)
    bundle = read_json(run_dir(workspace, run_key) / 'facts.json')
    state = {'run_key': run_key, 'synthetic': bundle['synthetic'], 'facts': bundle['facts'],
             'resume': read_json(folder / 'resume.json'), 'questions': read_json(folder / 'questions.json'),
             'selection': read_json(folder / 'selection.json') if (folder / 'selection.json').exists() else None}
    state['revision'] = digest(state)
    return state


def save_review(workspace, run_key, payload):
    state = current_state(workspace, run_key)
    if payload.get('revision') != state['revision']:
        raise ValueError('审阅内容已变化，请刷新页面后再保存')
    if not isinstance(payload.get('resume'), dict) or not isinstance(payload.get('questions'), list):
        raise ValueError('审阅数据结构无效')
    questions = payload['questions']
    baseline = read_json(run_dir(workspace, run_key) / 'facts.json')['questions']
    if len(questions) != len(baseline):
        raise ValueError('不可删除待确认问题，请选择核实或省略')
    for original, item in zip(baseline, questions):
        if any(item.get(k) != original[k] for k in ('id', 'text', 'fact_ids')):
            raise ValueError('不可替换原始问题或关联事实')
        if item.get('resolution') not in ('', 'confirmed', 'omitted') or not isinstance(item.get('note'), str):
            raise ValueError('问题处理方式无效')
    validate_selection(payload.get('selection'))
    folder = review_dir(workspace, run_key)
    write_json(folder / 'resume.json', payload['resume'])
    write_json(folder / 'questions.json', questions)
    write_json(folder / 'selection.json', payload['selection'])
    return current_state(workspace, run_key)


def approval_content(workspace, run_key):
    manifest = verify_sources(workspace, run_key)
    directory, folder = run_dir(workspace, run_key), review_dir(workspace, run_key)
    files = [directory / 'extracted.json', directory / 'facts.json', directory / 'resume.draft.json',
             folder / 'resume.json', folder / 'questions.json', folder / 'selection.json']
    try:
        hashes = {p.name + ('/review' if p.parent == folder else '/run'): file_hash(p) for p in files}
    except FileNotFoundError:
        raise ValueError('审阅文件或模板选择缺失') from None
    return {'snapshot_hash': manifest['snapshot_hash'], 'hashes': hashes}


def approve(workspace: Path, run_key: str):
    folder = review_dir(workspace, run_key)
    before = approval_content(workspace, run_key)
    state = current_state(workspace, run_key)
    validate_resume(state['resume'])
    validate_selection(state['selection'])
    baseline = read_json(run_dir(workspace, run_key) / 'facts.json')['questions']
    questions = state['questions']
    if [q['id'] for q in questions] != [q['id'] for q in baseline]:
        raise ValueError('待确认清单被删改，请保留全部问题')
    for original, item in zip(baseline, questions):
        if any(item.get(k) != original[k] for k in ('text', 'fact_ids')):
            raise ValueError('问题原文或事实关联被修改')
        if item.get('resolution') not in ('confirmed', 'omitted') or not item.get('note', '').strip():
            raise ValueError('请逐项核实或省略，并填写原因/补充依据')
        if item['resolution'] == 'omitted':
            omitted = set(item['fact_ids'])
            if omitted.intersection(state['resume'].get('name_fact_ids', [])):
                raise ValueError('姓名仍引用已省略的事实，请先修改姓名及其来源')
            facts = {f['id']: f for f in state['facts']}
            for fid in omitted:
                fact = facts.get(fid)
                if fact and fact['field'] == 'name' and state['resume']['name'] == fact['value']:
                    raise ValueError('已省略的姓名仍出现在正文')
                if fact and fact['field'] in ('email', 'phone'):
                    if any(c.get('value') == fact['value'] for c in state['resume']['contact']):
                        raise ValueError('已省略的联系方式仍出现在正文')
            for contact in state['resume']['contact']:
                if omitted.intersection(contact.get('fact_ids', [])):
                    raise ValueError('联系方式仍引用已省略的事实')
            for section in state['resume']['sections']:
                for entry in section['items']:
                    if omitted.intersection(entry.get('fact_ids', [])):
                        raise ValueError('正文仍引用已省略的事实，请先移除相关内容')
    if before != approval_content(workspace, run_key):
        raise ValueError('确认期间内容发生变化，请重试')
    record = {'schema_version': 1, 'content_hash': digest(before), 'approved_at': now(),
              'synthetic': state['synthetic'], 'statement': '本人已核实正文及问题处理，确认模板，允许导出。'}
    write_json(folder / 'approval.json', record)
    return record


def verify_approval(workspace: Path, run_key: str):
    path = review_dir(workspace, run_key) / 'approval.json'
    if not path.exists():
        raise ValueError('尚未明确确认正文与模板，不能导出')
    record = read_json(path)
    if record.get('content_hash') != digest(approval_content(workspace, run_key)):
        raise ValueError('材料、正文、问题处理或模板已变化，请重新确认')
    return record


def get_status(workspace, run_key):
    bundle = read_json(run_dir(workspace, run_key) / 'facts.json')
    questions = read_json(review_dir(workspace, run_key) / 'questions.json')
    pending = sum(q.get('resolution') not in ('confirmed', 'omitted') or not q.get('note', '').strip()
                  for q in questions)
    status = {'state': 'waiting_input' if pending else 'waiting_review',
              'run_key': run_key, 'synthetic': bundle['synthetic'], 'pending_questions': pending}
    try:
        approval = verify_approval(workspace, run_key)
    except (ValueError, OSError):
        return status
    status['state'] = 'approved'
    outputs = inside(workspace, 'outputs')
    reports = sorted(outputs.glob('*/report.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in reports:
        if not path.resolve().is_relative_to(outputs.resolve()):
            continue
        if not (path.parent / 'input.json').exists():
            continue
        inputs = read_json(path.parent / 'input.json')
        if inputs.get('run_key') != run_key or inputs.get('approval_hash') != approval['content_hash']:
            continue
        report = read_json(path)
        status.update({'state': report['state'], 'export_key': path.parent.name})
        accepted = path.parent / 'visual-acceptance.json'
        if accepted.exists() and read_json(accepted).get('report_hash') == digest(report):
            hashes = report.get('artifact_hashes', {})
            if hashes and all(file_hash(inside(path.parent, name)) == expected for name, expected in hashes.items()):
                status['state'] = 'final'
            else:
                status['state'] = 'failed'
        break
    return status


def make_server(workspace: Path, run_key: str, port=0):
    current_state(workspace, run_key)
    token, lock = secrets.token_urlsafe(32), threading.Lock()
    assets = Path(__file__).parent / 'web'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body, mime='application/json; charset=utf-8'):
            raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self):
            expected = f'127.0.0.1:{self.server.server_port}'
            origin = self.headers.get('Origin')
            valid = (self.headers.get('Host') == expected and
                     (not origin or origin == 'http://' + expected) and
                     hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token))
            if not valid:
                self.send(403, {'error': '请使用启动命令提供的本机链接'})
            return valid

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ('/', '/app.js', '/style.css'):
                name = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[path]
                mime = {'html': 'text/html', 'js': 'text/javascript', 'css': 'text/css'}[name.rsplit('.', 1)[1]]
                self.send(200, (assets / name).read_bytes(), mime + '; charset=utf-8')
            elif path == '/api/state' and self.authorized():
                with lock:
                    self.send(200, current_state(workspace, run_key))
            elif path != '/api/state':
                self.send(404, {'error': 'Not found'})

        def do_POST(self):
            if not self.authorized():
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 300000:
                    raise ValueError('请求体大小无效')
                payload = json.loads(self.rfile.read(length))
                path = urlsplit(self.path).path
                if path not in ('/api/save', '/api/approve'):
                    self.send(404, {'error': 'Not found'})
                    return
                with lock:
                    save_review(workspace, run_key, payload)
                    if path == '/api/approve':
                        approve(workspace, run_key)
                    self.send(200, {'ok': True, 'state': current_state(workspace, run_key)})
            except (ValueError, KeyError, TypeError, OSError) as error:
                self.send(400, {'error': str(error) if isinstance(error, ValueError) else '审阅数据无效或文件不可用',
                                'state': current_state(workspace, run_key)})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler), token
