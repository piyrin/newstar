"""Durable material-entry requests, separate from serial resume preparation."""
from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlencode

from .materials import EXTENSIONS
from .storage import digest, inside, read_json, validate_id, write_json


def intake_path(workspace, intake_id):
    return inside(workspace, 'intakes', validate_id(intake_id) + '.json')


def has_materials(workspace, case_id):
    folder = inside(workspace, 'inputs', validate_id(case_id))
    return folder.is_dir() and not folder.is_symlink() and any(
        file.is_file() and not file.is_symlink() and file.resolve().is_relative_to(folder.resolve())
        and not any(part.startswith('.') for part in file.relative_to(folder).parts)
        and file.suffix.lower() in EXTENSIONS and file.stat().st_size > 0
        for file in folder.rglob('*'))


def open_intake(workspace, dag_id, dag_run_id, params, inline=False):
    if dag_id not in ('resume_start', 'resume_prepare'):
        raise ValueError('材料入口工作流无效')
    intake_id = digest([dag_id, dag_run_id])[:32]
    path = intake_path(workspace, intake_id)
    if path.exists():
        return read_json(path)
    case_id = validate_id(params.get('case_id') or 'resume-' + intake_id[:12])
    created = datetime.now(timezone.utc)
    record = {'id': intake_id, 'dag_id': dag_id, 'dag_run_id': dag_run_id,
              'case_id': case_id, 'state': 'waiting_materials',
              'defaults': {key: params.get(key) or default for key, default in
                           [('target', ''), ('jd', ''), ('mode', 'deepseek'), ('run_key', '')]},
              'created_at': created.isoformat(), 'expires_at': (created + timedelta(hours=24)).isoformat(),
              'url': 'http://localhost:8765/?' + urlencode({'intake_id': intake_id}),
              'child_run_id': dag_run_id if inline else 'intake-' + intake_id,
              'inline': inline}
    write_json(path, record)
    print('请打开材料填写页：' + record['url'])
    return record


def prepare_entry(workspace, dag_run_id, params, scheduled=False):
    """Resolve an existing snapshot or publish a same-run material form."""
    pending = intake_path(workspace, digest(['resume_prepare', dag_run_id])[:32])
    if not scheduled and pending.is_file():
        record = read_json(pending)
        if not record.get('inline') and record['state'] == 'waiting_materials':
            record.update(inline=True,child_run_id=dag_run_id)
            write_json(pending,record)
        return {'case_id':record['case_id'],'intake_id':record['id'],'url':record['url'],'ready':False}
    conf = {key: params.get(key) or default for key, default in
            [('case_id',''),('run_key',''),('target',''),('jd',''),('mode','deepseek')]}
    if scheduled and not conf['case_id']:
        conf['case_id'] = os.environ.get('RESUME_DEFAULT_CASE', 'demo')
    fixed = conf['run_key'] and inside(workspace, 'runs', validate_id(conf['run_key']), 'manifest.json').is_file()
    if scheduled or fixed or (conf['case_id'] and has_materials(workspace, conf['case_id'])
                              and not params.get('upload_materials')):
        return {'case_id': conf['case_id'], 'conf': conf, 'ready': True}
    record = open_intake(workspace, 'resume_prepare', dag_run_id, conf, inline=True)
    return {'case_id': record['case_id'], 'intake_id': record['id'], 'url': record['url'], 'ready': False}


def entry_ready(workspace, entry):
    if entry['ready']:
        return True
    record = get_intake(workspace,entry['intake_id'])
    if record['state'] in ('cancelled','expired','superseded'):
        raise ValueError('材料入口已结束，请重新开始制作流程')
    return record['state'] == 'submitted'


def entry_config(workspace, entry):
    if entry['ready']:
        return entry['conf']
    record = get_intake(workspace, entry['intake_id'])
    if record['state'] != 'submitted':
        raise ValueError('请先在本次材料页提交材料')
    return record['conf']


def get_intake(workspace, intake_id):
    record = read_json(intake_path(workspace, intake_id))
    if record['state'] == 'waiting_materials' and datetime.now(timezone.utc) >= datetime.fromisoformat(record['expires_at']):
        return {**record, 'state': 'expired'}
    return record


def list_intakes(workspace):
    folder = inside(workspace, 'intakes')
    result = []
    for path in sorted(folder.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
        record = get_intake(workspace, path.stem)
        if record['state'] == 'waiting_materials':
            result.append({**{key: record[key] for key in ('id', 'case_id', 'url', 'created_at', 'dag_id', 'dag_run_id')},
                           'opened': bool(record.get('opened'))})
    return result


def intake_ready(workspace, intake_id):
    record = get_intake(workspace, intake_id)
    return record['state'] == 'submitted'


def submit_intake(workspace, intake_id, payload, api=None):
    record = get_intake(workspace, intake_id)
    if record['state'] == 'expired':
        raise ValueError('材料入口已过期，请重新触发开始流程')
    if record['state'] == 'cancelled':
        raise ValueError('该材料入口已结束，请重新开始制作流程')
    if record['state'] == 'superseded':
        raise ValueError('已合并到新的制作流程，请打开页面中的最新入口')
    if not has_materials(workspace, record['case_id']):
        raise ValueError('请先在上方导入至少一份材料，再提交继续')
    defaults = record['defaults']
    conf = {'case_id': record['case_id'], 'run_key': defaults['run_key']}
    for key, limit in [('target', 200), ('jd', 20000)]:
        value = payload.get(key, defaults[key])
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError('目标岗位或岗位要求格式无效')
        conf[key] = value
    conf['mode'] = payload.get('mode', defaults['mode'])
    if conf['mode'] not in ('deepseek', 'offline'):
        raise ValueError('模型模式无效')
    if record['state'] == 'submitted' and record['conf'] != conf:
        raise ValueError('本次材料已经提交，修改需求请重新开始流程')
    if record['state'] != 'submitted':
        record = {**record, 'state': 'submitted', 'conf': conf,
                  'submitted_at': datetime.now(timezone.utc).isoformat()}
        write_json(intake_path(workspace, intake_id), record)
    # Legacy triggers finish their missing-input check. Their form resumes a
    # fresh preparation run. resume_start resumes through its own downstream task.
    if record['dag_id'] == 'resume_prepare' and not record.get('inline'):
        if api is None:
            raise ValueError('需要通过本机工作台提交继续')
        api.trigger('resume_prepare', record['child_run_id'], conf)
    return record


def cancel_intake(workspace, intake_id, api):
    record = get_intake(workspace, intake_id)
    if record['state'] == 'cancelled':
        return record
    if record['state'] not in ('waiting_materials','expired'):
        raise ValueError('材料已提交，请到对应草稿管理后续运行')
    api.cancel_waiting(record['dag_id'], record['dag_run_id'])
    record.update(state='cancelled', cancelled_at=datetime.now(timezone.utc).isoformat())
    write_json(intake_path(workspace,intake_id),record)
    return record
