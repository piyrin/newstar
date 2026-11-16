"""Shared Skill experiment records used by the portal, Airflow and host bridge."""
import time
import uuid
from pathlib import Path, PureWindowsPath

from .storage import digest, file_hash, inside, read_json, validate_id, write_json as atomic_json

DAG_ID = 'skill_experiment'
TERMINAL = {'finished', 'failed'}


def write_json(path, value):
    # Docker's Windows bind mount can briefly hold a file without delete sharing.
    for attempt in range(6):
        try:
            atomic_json(path, value)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


def root(workspace):
    return Path(workspace) / 'skill_experiments'


def folder(workspace, job_id):
    return inside(root(workspace), 'jobs', validate_id(job_id))


def config(payload):
    request = payload.get('request')
    size, seed = payload.get('size', 166), payload.get('seed', 3)
    backend = payload.get('backend', 'local')
    if not isinstance(request, str) or not 1 <= len(request.strip()) <= 10000:
        raise ValueError('请输入 1–10000 字的完整需求')
    if type(size) is not int or size not in (100, 166, 180):
        raise ValueError('候选规模需为 100、166 或 180')
    if backend not in ('local', 'deepseek'):
        raise ValueError('模型配置无效')
    if backend == 'local' and (type(seed) is not int or not 1 <= seed <= 100000):
        raise ValueError('本地 seed 需为 1–100000 的整数')
    if backend == 'deepseek' and payload.get('accept_api_cost') is not True:
        raise ValueError('请明确确认本次 DeepSeek API 费用及发送公开用例材料')
    return {'request': request.strip(), 'size': size, 'backend': backend,
            'seed': seed if backend == 'local' else None,
            'accept_api_cost': backend == 'deepseek'}


def start(workspace, payload, api):
    settings = config(payload)
    job_id = validate_id(payload.get('request_id') or uuid.uuid4().hex)
    target = folder(workspace, job_id)
    target.mkdir(parents=True, exist_ok=True)
    record_path = target / 'job.json'
    if record_path.exists():
        record = read_json(record_path)
        if record['config'] != settings:
            raise ValueError('同一请求标识已使用其他参数')
    else:
        record = {'job_id': job_id, 'dag_id': DAG_ID, 'dag_run_id': 'skill-' + job_id,
                  'config': settings, 'created_at': time.time(), 'origin': 'web',
                  'phase': 'submitted'}
        write_json(record_path, record)
    try:
        response = api.trigger(DAG_ID, record['dag_run_id'], {'job_id': job_id})
    except ValueError as error:
        write_json(record_path, {**record, 'phase': 'submission_failed', 'submission_error': str(error)})
        raise
    record = {**record, 'phase': response.get('state', 'queued')}
    record.pop('submission_error', None)
    write_json(record_path, record)
    return public_record(workspace, record)


def enqueue(workspace, job_id):
    target = folder(workspace, job_id)
    record = read_json(target / 'job.json')
    config(record['config'])
    queue = root(workspace) / 'queue'
    queue.mkdir(parents=True, exist_ok=True)
    # A retry may rediscover the existing request, claim or terminal result.
    if not (target / 'execution.json').exists():
        write_json(queue / (job_id + '.json'), {'job_id': job_id})
    return job_id


def execution_done(workspace, job_id):
    path = folder(workspace, job_id) / 'execution.json'
    return path.is_file() and read_json(path).get('phase') in TERMINAL


def bridge_status(workspace):
    path = root(workspace) / 'bridge.json'
    value = read_json(path) if path.exists() else {}
    return {'online': time.time() - value.get('heartbeat', 0) < 20,
            'active_job': value.get('active_job'), 'heartbeat': value.get('heartbeat')}


def catalog(workspace):
    source = root(workspace) / 'catalog.json'
    value = read_json(source) if source.exists() else {'case': None, 'cohorts': []}
    records = []
    for path in (root(workspace) / 'jobs').glob('*/job.json'):
        records.append(public_record(workspace, read_json(path)))
    records.sort(key=lambda r: r['created_at'], reverse=True)
    by_id = {r['job_id']: r for r in records}
    for batch_path in sorted((root(workspace) / 'batches').glob('*.json')):
        batch = read_json(batch_path)
        for group in batch['groups']:
            jobs = [by_id[ident] for ident in group['jobs'] if ident in by_id]
            completed = sum(job['phase'] in TERMINAL for job in jobs)
            correct = sum(job.get('review', {}).get('state') == 'accepted' for job in jobs)
            pending = sum(job.get('review', {}).get('state') == 'pending' for job in jobs)
            value['cohorts'].append({'model': 'deepseek-flash · legacy · 新测 ' + batch['name'],
                'size': group['size'], 'group': batch['name'] + '-' + str(group['size']),
                'planned': len(group['jobs']), 'completed': completed, 'correct': correct,
                'pending_review': pending, 'accuracy': correct / completed if completed else 0,
                'jobs': [ident for ident in group['jobs'] if ident in by_id]})
    return {**value, 'bridge': bridge_status(workspace), 'jobs': records[:150]}


def public_record(workspace, record):
    target = folder(workspace, record['job_id'])
    result = dict(record)
    if record.get('submission_error'):
        result['error'] = record['submission_error']
    state = target / 'execution.json'
    if state.exists():
        result.update(read_json(state))
    report = target / 'result.json'
    if report.exists():
        value = checked_report(target)
        result['metrics'] = value.get('metrics')
        result['automatic_passed'] = value.get('automatic_passed', False)
        result['review'] = value.get('review')
        if (record.get('origin') != 'history' and result.get('phase') == 'finished'
                and not value.get('automatic_passed')):
            result['phase'] = 'failed'
        failure = value.get('error') or result.get('error')
        if failure:
            result['error'] = failure
            if failure == 'URLError':
                result['error'] = ('DeepSeek 请求连接失败（URLError），未取得模型结果。'
                                   '请检查执行桥进程的联网权限、代理与网络，恢复后发起新运行。'
                                   'Airflow 历史 success 表示旧版归档完成。')
    result['airflow_url'] = ('http://localhost:8080/dags/' + DAG_ID + '/runs/'
                            + record['dag_run_id']) if record.get('dag_run_id') else None
    return result


def checked_report(target):
    report = read_json(target / 'result.json')
    for item in report['files']:
        if item['final']:
            path = inside(target, item['name'])
            if not path.is_file() or file_hash(path) != item['sha256']:
                return {**report, 'review': {'state': 'invalidated', 'label': '最终文件变化，需重新核验'}}
    if not report.get('automatic_passed') and report.get('review', {}).get('state') == 'pending':
        return {**report, 'review': {'state': 'incomplete', 'label': '自动核验未通过，请查看错误和原始证据'}}
    return report


def evidence_files(target, final_names=frozenset()):
    files = []
    for path in sorted((target / 'run').rglob('*')):
        if path.is_file() and path.suffix in ('.json', '.md', '.csv', '.txt'):
            relative = path.relative_to(target).as_posix()
            resolved = inside(target, relative)
            files.append({'name': relative, 'sha256': file_hash(resolved),
                          'bytes': resolved.stat().st_size, 'final': relative in final_names})
    return files


def partial_dag(run):
    paths = list(run.glob('n*/dock-r1/dag.json'))
    if len(paths) != 1:
        return []
    try:
        nodes = read_json(paths[0])
    except (OSError, ValueError):
        return []
    if not isinstance(nodes, list):
        return []
    for node in nodes:
        if not isinstance(node, dict) or type(node.get('depth')) is not int or node['depth'] < 1:
            return []
        if any(not isinstance(node.get(key), str) for key in ('id', 'skill', 'request')):
            return []
        for key in ('depends_on', 'input_reference_ids', 'output_reference_ids'):
            if not isinstance(node.get(key), list) or any(not isinstance(value, str) for value in node[key]):
                return []
    return nodes


def collect_failure(workspace, job_id, error):
    target = folder(workspace, job_id)
    if (target / 'result.json').exists():
        return read_json(target / 'result.json')
    dag = partial_dag(target / 'run')
    record = read_json(target / 'job.json')
    result = {'job_id': job_id, 'partial': True, 'automatic_passed': False, 'error': error,
              'metrics': {'skills': record['config']['size'], 'actual_skills': len({n['skill'] for n in dag}) if dag else None,
                          'nodes': len(dag) if dag else None, 'chain': max((n['depth'] for n in dag), default=None)},
              'files': evidence_files(target), 'dag': dag, 'manifest': {'deliverables': []},
              'summary': {'passed': False, 'error': error},
              'review': {'state': 'incomplete', 'label': '执行中断，无正式终稿；部分证据已保留'}}
    write_json(target / 'result.json', result)
    return result


def collect_result(workspace, job_id):
    """Index actual files, including implicit final attachments, without rewriting them."""
    target = folder(workspace, job_id)
    record = read_json(target / 'job.json')
    run = target / 'run'
    trials = list(run.glob('n*/dock-r1'))
    if len(trials) != 1:
        raise ValueError('执行未产生唯一完整任务目录，请查看主机执行日志')
    trial = trials[0]
    summary = read_json(trial / 'summary.json')
    refs = {}
    for path in (trial / 'artifacts').glob('STEP-*.json'):
        for ref in read_json(path).get('outputs', []):
            refs[ref['reference_id']] = ref
    manifest_path = trial / 'manifest.json'
    manifest = read_json(manifest_path) if manifest_path.exists() else {'deliverables': []}
    final_ids = {ident for item in manifest['deliverables'] for ident in item['reference_ids']}
    final_paths = set()
    for ident in list(final_ids):
        ref = refs[ident]
        for asset in ref.get('files', []):
            asset_path = 'artifacts/' + PureWindowsPath(asset['path']).name
            if file_hash(inside(trial, asset_path)) != asset['sha256']:
                raise ValueError('最终附件摘要不一致 ' + asset['reference_id'])
            final_paths.add(asset_path)
            final_ids.add(asset['reference_id'])
        relative = 'artifacts/' + PureWindowsPath(ref.get('path', ref.get('document_path', ''))).name
        actual = inside(trial, relative)
        if not actual.is_file() or actual.read_text(encoding='utf-8-sig') != ref['content']:
            raise ValueError('最终引用与实际文件正文不一致 ' + ident)
        final_paths.add(relative)
    final_names = {(trial / name).relative_to(target).as_posix() for name in final_paths}
    files = evidence_files(target, final_names)
    metrics = {name: summary.get(name) for name in ('skills', 'actual_skills', 'nodes', 'chain')}
    result = {'job_id': job_id, 'metrics': metrics, 'automatic_passed': summary['passed'],
              'error': summary.get('error'), 'files': files,
              'dag': read_json(trial / 'dag.json') if (trial / 'dag.json').exists() else [],
              'manifest': manifest, 'summary': summary,
              'review': {'state': 'pending', 'label': '待人工六项复核'}}
    previous = target / 'result.json'
    if previous.exists():
        old = read_json(previous)
        if digest(old.get('files')) == digest(files):
            result['review'] = old.get('review', result['review'])
    write_json(previous, result)
    return result


def detail(workspace, job_id, api=None):
    target = folder(workspace, job_id)
    record = read_json(target / 'job.json')
    result = {'job': public_record(workspace, record), 'bridge': bridge_status(workspace)}
    if (target / 'result.json').exists():
        result['result'] = checked_report(target)
        from .skill_explanations import explain
        result['explanation'] = explain(target, record, result['result'])
    else:
        run = target / 'run'
        responses = list(run.rglob('*.response.json')) + list(run.rglob('*.native.json'))
        response_stems = {path.relative_to(run).as_posix().rsplit('.', 2)[0] for path in responses}
        result['progress'] = {'dag': partial_dag(run),
                              'requests': len(list(run.rglob('*.request.json'))),
                              'responses': len(response_stems)}
    if api and record.get('dag_run_id'):
        try:
            result['airflow'] = api.status(DAG_ID, record['dag_run_id'])
        except ValueError as error:
            result['airflow_error'] = str(error)
    log = target / 'execution.log'
    if log.exists():
        with log.open('rb') as stream:
            stream.seek(max(0, log.stat().st_size - 16000))
            raw = stream.read()
            try:
                result['log'] = raw.decode('utf-8')
            except UnicodeDecodeError:
                result['log'] = raw.decode('gb18030', errors='replace')
    return result


def download(workspace, job_id, name):
    target = folder(workspace, job_id)
    report_path = target / 'result.json'
    if not report_path.exists():
        raise ValueError('产物尚未归档')
    report = read_json(report_path)
    entry = next((item for item in report['files'] if item['name'] == name), None)
    if entry is None:
        raise ValueError('该文件未登记在本次运行中')
    path = inside(target, name)
    if file_hash(path) != entry['sha256']:
        raise ValueError('文件摘要变化，请重新核验')
    return path


def record_review(workspace, job_id, payload):
    target = folder(workspace, job_id)
    if not (target / 'result.json').exists():
        raise ValueError('请等待产物归档完成')
    report = read_json(target / 'result.json')
    checks = payload.get('checks')
    if not isinstance(checks, list) or len(checks) != 6 or any(type(c) is not bool for c in checks):
        raise ValueError('需逐项记录原六项复核结果')
    notes = payload.get('notes', '')
    if not isinstance(notes, str) or len(notes) > 10000:
        raise ValueError('复核说明无效')
    final = [item for item in report['files'] if item['final']]
    if not final:
        raise ValueError('本次没有正式提交的最终文件')
    for item in final:
        download(workspace, job_id, item['name'])
    review = {'state': 'accepted' if all(checks) and report['automatic_passed'] else 'rejected',
              'label': '人工六项复核通过' if all(checks) and report['automatic_passed'] else '人工复核未通过',
              'checks': checks, 'notes': notes, 'reviewed_at': time.time(),
              'files_digest': digest(report['files'])}
    write_json(target / ('review-' + uuid.uuid4().hex + '.json'), review)
    write_json(target / 'result.json', {**report, 'review': review})
    return review
