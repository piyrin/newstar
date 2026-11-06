"""Reversible draft visibility and durable, retryable waiting-run cancellation."""
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from .airflow_api import ALLOWED_DAGS
from .storage import inside, read_json, validate_id, write_json


def marker_path(workspace, run_key):
    return inside(workspace, 'deleted_drafts', validate_id(run_key) + '.json')


class DraftBusyError(ValueError):
    """A retryable cross-process draft mutation conflict."""


@contextmanager
def draft_guard(workspace, run_key, timeout=0):
    """Serialize a draft mutation across portal processes and Airflow workers.

    Call ensure_active inside this guard before writing or triggering a run.
    Nested guards for the same key are intentionally unsupported.
    """
    path = inside(workspace, 'deleted_drafts', validate_id(run_key) + '.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0)
        deadline = time.monotonic() + timeout
        if os.name == 'nt':
            import msvcrt
            if path.stat().st_size == 0:
                stream.write(b'0')
                stream.flush()
            stream.seek(0)
        while True:
            try:
                if os.name == 'nt':
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DraftBusyError('草稿正在处理另一项操作，请稍后重试') from None
                time.sleep(min(0.1, remaining))
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def is_deleted(workspace, run_key):
    path = marker_path(workspace, run_key)
    return path.is_file() and read_json(path).get('state') != 'restored'


def ensure_active(workspace, run_key):
    if is_deleted(workspace, run_key):
        raise ValueError('草稿已移入回收站或正在停止工作流，请先恢复草稿')


def list_deleted(workspace):
    result = []
    for path in inside(workspace, 'deleted_drafts').glob('*.json'):
        try:
            key = validate_id(path.stem)
            record = read_json(inside(workspace, 'deleted_drafts', path.name))
            if record.get('state') == 'restored':
                continue
            result.append({'run_key': key, 'state': record.get('state', 'pending'),
                           'deleted_at': record.get('deleted_at'),
                           'stopped': record.get('stopped', []),
                           'error': record.get('error', '')})
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return sorted(result, key=lambda item: item['deleted_at'] or '', reverse=True)


def _run_reference(record, allowed):
    dag, run = record.get('dag_id'), record.get('dag_run_id')
    if dag not in allowed or not isinstance(run, str) or not 1 <= len(run) <= 250 or any(ord(c) < 32 for c in run):
        raise ValueError('关联工作流标识无效，请检查草稿运行记录')
    return dag, run


def _records(workspace, folder):
    for path in sorted(inside(workspace, folder).glob('*.json')):
        record = read_json(inside(workspace, folder, path.name))
        if not isinstance(record, dict):
            raise ValueError('工作流记录格式无效，请检查 ' + folder)
        yield record


def associated_runs(workspace, run_key):
    """Resolve exact version links, never case/material-wide matches."""
    found = set()
    for record in _records(workspace, 'requests'):
        if record.get('run_key') == run_key:
            found.add(_run_reference(record, {'resume_prepare', 'resume_export'}))
    for folder in ('workflow_links', 'web_requests'):
        path = inside(workspace, folder, run_key + '.json')
        if path.is_file():
            record = read_json(path)
            if record.get('run_key', run_key) != run_key:
                raise ValueError('草稿与关联工作流版本不匹配')
            found.add(_run_reference(record, {'resume_prepare', 'resume_export'}))
    children = {run for dag, run in found if dag == 'resume_prepare'}
    for record in _records(workspace, 'intakes'):
        if record.get('dag_id') == 'resume_start' and record.get('child_run_id') in children:
            found.add(_run_reference(record, {'resume_start'}))
    # Stop parent triggers before their children.
    return sorted(found, key=lambda pair: (pair[0] != 'resume_start', pair))


def delete_draft(workspace, run_key, api):
    path = marker_path(workspace, run_key)
    with draft_guard(workspace, run_key):
        if not inside(workspace, 'runs', run_key).is_dir() and not inside(workspace, 'reviews', run_key).is_dir():
            raise ValueError('草稿不存在')
        old = read_json(path) if path.is_file() else {}
        now = datetime.now(timezone.utc).isoformat()
        record = {'run_key': run_key, 'state': 'pending',
                  'deleted_at': old.get('deleted_at', now) if old.get('state') != 'restored' else now,
                  'stopped': old.get('stopped', []), 'runs': old.get('runs', [])}
        write_json(path, record)
        try:
            runs = set(associated_runs(workspace, run_key))
            for reference in record['runs']:
                runs.add(_run_reference(reference, ALLOWED_DAGS))
            record['runs'] = [{'dag_id': dag, 'dag_run_id': run} for dag, run in
                              sorted(runs, key=lambda pair: (pair[0] != 'resume_start', pair))]
            write_json(path, record)
            stopped = {(item['dag_id'], item['dag_run_id']): item for item in record['stopped']}
            for reference in record['runs']:
                dag, run = reference['dag_id'], reference['dag_run_id']
                outcome = api.cancel_waiting(dag, run)
                if outcome.get('result') not in ('stopped', 'already_finished'):
                    raise ValueError('工作流尚未确认停止，请重试删除')
                if outcome['result'] == 'stopped':
                    stopped[(dag, run)] = {**reference, 'state': outcome.get('state', 'failed')}
                record['stopped'] = list(stopped.values())
                write_json(path, record)
                if dag == 'resume_start':
                    for intake in _records(workspace, 'intakes'):
                        if (intake.get('dag_id') == dag and intake.get('dag_run_id') == run
                                and intake.get('state') == 'waiting_materials'):
                            from .intake import intake_path
                            write_json(intake_path(workspace, intake['id']),
                                       {**intake, 'state': 'cancelled', 'cancelled_at': now})
        except (ValueError, OSError) as error:
            record['error'] = str(error)
            write_json(path, record)
            raise ValueError('草稿删除尚未完成，已保留恢复入口。' + str(error)) from None
        record['state'] = 'cancelled'
        write_json(path, record)
        return {**record, 'deleted': True}


def restore_draft(workspace, run_key):
    path = marker_path(workspace, run_key)
    with draft_guard(workspace, run_key):
        if not path.is_file():
            raise ValueError('草稿不在回收站')
        record = read_json(path)
        record.update(state='restored', restored_at=datetime.now(timezone.utc).isoformat())
        record.pop('error', None)
        write_json(path, record)
        return {'run_key': run_key, 'deleted': False, 'stopped': record.get('stopped', [])}
