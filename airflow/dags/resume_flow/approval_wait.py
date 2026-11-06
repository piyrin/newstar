"""Publish review entry points and bind approval to one Airflow DagRun."""
from urllib.parse import urlencode

from .review import verify_approval
from .storage import digest, inside, read_json, validate_id, write_json


def request_path(workspace, dag_run_id):
    return inside(workspace, 'requests', digest(dag_run_id) + '.json')


def bind_run_approval(workspace, record):
    """Persist a single immutable confirmation before triggering its run.

    The separate signal survives a concurrent metadata publication based on an
    earlier read. The portal serializes confirmations with the draft guard.
    """
    signal = {name: record[name] for name in
              ('dag_id', 'dag_run_id', 'run_key', 'approval_hash', 'export_key')}
    path = inside(workspace, 'requests', digest(record['dag_run_id']) + '.approval.json')
    if path.is_file():
        if read_json(path) != signal:
            raise ValueError('本次工作流已绑定另一个确认版本，请创建新的导出运行')
    else:
        write_json(path, signal)
    write_json(request_path(workspace, record['dag_run_id']), record)


def publish_review_request(workspace, version, dag_run_id, params=None):
    key = validate_id(version['run_key'])
    path = request_path(workspace, dag_run_id)
    previous = read_json(path) if path.exists() else {}
    if previous.get('run_key') != key:
        previous = {}
    review_url = 'http://localhost:8765/review?' + urlencode(
        {'run_key': key, 'dag_run_id': dag_run_id})
    metadata = {**(params or {}), **version, 'dag_id': 'resume_prepare',
                'dag_run_id': dag_run_id, 'review_url': review_url}
    # A retry must leave the published request untouched while the portal may
    # concurrently attach the user's confirmation to it.
    if any(previous.get(name) != value for name, value in metadata.items()):
        write_json(path, {**previous, **metadata})
    write_json(inside(workspace, 'workflow_links', key + '.json'),
               {'dag_id': 'resume_prepare', 'dag_run_id': dag_run_id, 'run_key': key})
    print('人工审阅入口：' + review_url)
    return key


def run_approval(workspace, run_key, dag_run_id):
    record = read_json(request_path(workspace, dag_run_id))
    signal = inside(workspace, 'requests', digest(dag_run_id) + '.approval.json')
    if signal.is_file():
        record.update(read_json(signal))
    if (record.get('dag_id') != 'resume_prepare'
            or record.get('dag_run_id') != dag_run_id or record.get('run_key') != run_key):
        raise ValueError('审阅请求与当前工作流运行不匹配')
    if not record.get('approval_hash') or not record.get('export_key'):
        raise ValueError('请在本次工作流的审阅页确认继续')
    validate_id(record['export_key'])
    approval = verify_approval(workspace, run_key)
    if approval['content_hash'] != record['approval_hash']:
        raise ValueError('本次运行确认的内容已变化，请重新审阅')
    return record


def await_run_approval(workspace, run_key, dag_run_id):
    try:
        run_approval(workspace, run_key, dag_run_id)
    except (ValueError, OSError):
        return False
    return True


def freeze_run_export(workspace, run_key, dag_run_id):
    from .export import freeze_export, output_dir
    record = run_approval(workspace, run_key, dag_run_id)
    key = freeze_export(workspace, run_key, record['export_key'])
    frozen = read_json(output_dir(workspace, key) / 'input.json')
    if frozen['approval_hash'] != record['approval_hash']:
        raise ValueError('冻结期间确认内容变化，请重新审阅')
    return key
