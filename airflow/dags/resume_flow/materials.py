"""Bounded local material import with rollback, backups and retry identity."""
import base64
import binascii
import hashlib
import os
import re
import tempfile
import uuid
from pathlib import Path

from .storage import digest, inside, read_json, validate_id, write_json

EXTENSIONS = {'.txt', '.md', '.docx', '.pdf', '.png', '.jpg', '.jpeg'}
MAX_FILE = 5_000_000
MAX_TOTAL = 20_000_000


def atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.import-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def import_materials(workspace, payload):
    case_id = validate_id(payload.get('case_id'))
    request_id = validate_id(payload.get('request_id'))
    files = payload.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= 100:
        raise ValueError('请选择 1–100 个文件')
    prepared, names, total = [], set(), 0
    devices = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{p}{i}' for p in ('COM', 'LPT') for i in range(1, 10)}
    for item in files:
        if not isinstance(item, dict):
            raise ValueError('文件格式无效')
        name, encoded = item.get('name'), item.get('content_base64')
        if (not isinstance(name, str) or not 1 <= len(name) <= 180 or name.startswith('.')
                or name[-1:] in (' ', '.') or re.search(r'[\\/:\x00-\x1f<>"|?*]', name)
                or name.split('.')[0].upper() in devices or Path(name).suffix.lower() not in EXTENSIONS):
            raise ValueError('文件名或格式无效，请使用 TXT、MD、DOCX、PDF、PNG、JPG')
        if name.casefold() in names:
            raise ValueError('一次导入中存在同名文件，请分别导入或先改名')
        names.add(name.casefold())
        if not isinstance(encoded, str) or len(encoded) > 6_666_668:
            raise ValueError('每个文件最多 5 MB')
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('文件传输内容无效') from None
        total += len(content)
        if len(content) > MAX_FILE or total > MAX_TOTAL:
            raise ValueError('每个文件最多 5 MB，每次总计最多 20 MB')
        prepared.append((name, content))
    fingerprint = digest({'case_id': case_id, 'files': [(name, hashlib.sha256(content).hexdigest()) for name, content in prepared]})
    record_path = inside(workspace, 'import_requests', request_id + '.json')
    if record_path.is_file():
        record = read_json(record_path)
        if record['fingerprint'] != fingerprint:
            raise ValueError('同一导入请求标识已用于不同文件，请重新发起导入')
        return record['result']
    case = inside(workspace, 'inputs', case_id)
    if case.is_symlink():
        raise ValueError('材料目录不能是链接')
    case.mkdir(parents=True, exist_ok=True)
    existing = {}
    for path in case.rglob('*'):
        if path.is_file() and not path.is_symlink() and not any(p.startswith('.') for p in path.relative_to(case).parts):
            existing[path.relative_to(case).as_posix().casefold()] = (path, path.stat().st_size)
    resulting_size = sum(size for _, size in existing.values())
    resulting_count = len(existing)
    for name, content in prepared:
        old = existing.get(name.casefold())
        resulting_size += len(content) - (old[1] if old else 0)
        resulting_count += int(old is None)
    if resulting_count > 100 or resulting_size > MAX_TOTAL:
        raise ValueError('该案例累计材料超过 100 个文件或 20 MB，请分成不同案例')
    marker = case / '.importing'
    try:
        with marker.open('x', encoding='utf-8') as stream:
            stream.write(request_id)
    except FileExistsError:
        raise ValueError('该案例正在导入，请稍后重试') from None
    changes, results = [], []
    attempt = uuid.uuid4().hex
    revision = {'request_id': request_id, 'attempt': attempt}
    release_marker = False
    try:
        write_json(case / '.material-revision', {**revision, 'state': 'importing'})
        for name, content in prepared:
            old_entry = existing.get(name.casefold())
            target = old_entry[0] if old_entry else inside(case, name)
            before = target.read_bytes() if target.exists() else None
            action = 'unchanged' if before == content else ('updated' if before is not None else 'added')
            if action != 'unchanged':
                if before is not None:
                    atomic_bytes(inside(workspace, 'input_history', case_id, request_id, target.name), before)
                changes.append((target, before))
                atomic_bytes(target, content)
            results.append({'name': name, 'stored_name': target.name, 'action': action})
        result = {'case_id': case_id, 'files': results,
                  'directory': 'D:/code/newstar/airflow/resume_workspace/inputs/' + case_id}
        write_json(case / '.material-revision', {**revision, 'state': 'complete'})
        write_json(record_path, {'fingerprint': fingerprint, 'result': result})
        release_marker = True
        return result
    except Exception:
        recovery_errors = []
        for path, before in reversed(changes):
            try:
                if before is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_bytes(path, before)
            except OSError:
                recovery_errors.append(path.name)
        if recovery_errors:
            raise ValueError('导入与恢复均遇到文件错误，该案例已暂停。请检查磁盘或文件权限，并从 input_history 中恢复后再处理。') from None
        write_json(case / '.material-revision', {**revision, 'state': 'rolled_back'})
        release_marker = True
        raise
    finally:
        if release_marker:
            marker.unlink(missing_ok=True)
