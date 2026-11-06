"""Continue a human-reviewed DAG run or start a new run for a revised approval."""
from urllib.parse import urlencode

from .approval_wait import bind_run_approval
from .review import verify_approval
from .storage import digest, inside, read_json, validate_id, write_json
from .drafts import ensure_active


def review_workflow(workspace, run_key, dag_run_id=None):
    validate_id(run_key)
    if dag_run_id is None:
        link = inside(workspace, 'workflow_links', run_key + '.json')
        if not link.is_file():
            return None
        dag_run_id = read_json(link)['dag_run_id']
    if not isinstance(dag_run_id, str) or not 1 <= len(dag_run_id) <= 250:
        raise ValueError('工作流运行标识无效')
    path = inside(workspace, 'requests', digest(dag_run_id) + '.json')
    record = read_json(path)
    if record.get('dag_id') != 'resume_prepare' or record.get('run_key') != run_key:
        raise ValueError('审阅版本与工作流不匹配，请从草稿列表重新进入')
    signal = inside(workspace, 'requests', digest(dag_run_id) + '.approval.json')
    if signal.is_file():
        record.update(read_json(signal))
    return record


def submit_reviewed_export(workspace, run_key, request_id, api, dag_run_id=None):
    ensure_active(workspace, run_key)
    approval = verify_approval(workspace, run_key)
    validate_id(request_id)
    flow = review_workflow(workspace, run_key, dag_run_id)
    previous = None
    previous_path = inside(workspace, 'web_requests', run_key + '.json')
    if previous_path.is_file():
        previous = read_json(previous_path)
        if previous.get('approval_hash') == approval['content_hash']:
            execution = api.status(previous.get('dag_id', 'resume_export'), previous['dag_run_id'])
            gate_ended = previous.get('dag_id') == 'resume_prepare' and any(
                task['task_id'] == 'await_review'
                and task['state'] in ('skipped', 'failed', 'upstream_failed')
                for task in execution['tasks'])
            same_review = (flow is None or flow.get('review_wait') != 'reschedule'
                           or previous['dag_run_id'] == flow['dag_run_id'])
            if execution['state'] in ('running', 'queued') and not gate_ended and same_review:
                return {**previous, 'state': execution['state']}
    if flow is None:
        export_key = 'web-' + digest([run_key, approval['content_hash'], request_id])[:32]
        run_id = 'web-export-' + export_key[4:]
        run = api.trigger('resume_export', run_id, {'run_key': run_key, 'export_key': export_key})
        result = {'dag_id': 'resume_export', 'dag_run_id': run_id, 'state': run['state'],
                  'export_key': export_key, 'approval_hash': approval['content_hash']}
    else:
        run_id = flow['dag_run_id']
        execution = api.status('resume_prepare', run_id)
        active = execution['state'] in ('running', 'queued')
        gate_state = next((t['state'] for t in execution['tasks'] if t['task_id'] == 'await_review'), None)
        bound_hash = flow.get('approval_hash')
        if active and bound_hash and bound_hash != approval['content_hash']:
            raise ValueError('当前运行已开始导出，请等待完成后再确认新修改')
        # A rescheduling review sensor stays in this DagRun until confirmation.
        # Older one-shot gates still need their compatible continuation path.
        active = active and gate_state not in ('skipped', 'failed', 'upstream_failed')
        active = active and (bound_hash == approval['content_hash']
                             or flow.get('review_wait') == 'reschedule'
                             or gate_state in ('up_for_reschedule', 'deferred'))
        resume_skipped = gate_state == 'skipped' and (
            not bound_hash or (bound_hash == approval['content_hash']
                               and flow.get('review_wait') == 'reschedule'))
        if not active and not resume_skipped:
            run_id = 'web-review-' + digest([run_key, approval['content_hash'], request_id])[:32]
        export_key = 'flow-' + digest([run_id, approval['content_hash']])[:32]
        if resume_skipped and previous and previous.get('approval_hash') == approval['content_hash']:
            export_key = previous['export_key']
        record = {**flow, 'dag_run_id': run_id, 'run_key': run_key,
                  'approval_hash': approval['content_hash'], 'export_key': export_key}
        if resume_skipped:
            record['review_wait'] = 'reschedule'
        record['review_url'] = 'http://localhost:8765/review?' + urlencode({'run_key': run_key, 'dag_run_id': run_id})
        bind_run_approval(workspace, record)
        if resume_skipped:
            api.resume_review(run_id)
            write_json(inside(workspace, 'workflow_links', run_key + '.json'),
                       {'dag_id': 'resume_prepare', 'dag_run_id': run_id, 'run_key': run_key})
            state = 'queued'
        elif active:
            state = execution['state']
        else:
            manifest = read_json(inside(workspace, 'runs', run_key, 'manifest.json'))
            bundle = read_json(inside(workspace, 'runs', run_key, 'facts.json'))
            config = manifest['config']
            conf = {'case_id': config['case_id'], 'target': config['target'], 'jd': config['jd'],
                    'mode': bundle['mode'], 'run_key': run_key}
            state = api.trigger('resume_prepare', run_id, conf)['state']
        result = {'dag_id': 'resume_prepare', 'dag_run_id': run_id, 'state': state,
                  'review_dag_run_id': flow['dag_run_id'],
                  'export_key': export_key, 'approval_hash': approval['content_hash']}
    write_json(inside(workspace, 'web_requests', run_key + '.json'), result)
    return result
