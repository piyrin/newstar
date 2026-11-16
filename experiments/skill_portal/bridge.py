"""Single host executor for requests dispatched by the Airflow DAG."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'airflow/dags'))
sys.path.insert(0, str(REPO))
from resume_flow import skill_jobs
from resume_flow.storage import read_json
from resume_flow.skill_jobs import write_json


def prepare(workspace):
    target = skill_jobs.root(workspace)
    target.mkdir(parents=True, exist_ok=True)
    case = read_json(REPO / 'deliverables/skill-boundary-ten-trial-repro-20261111/inputs/fixtures.json')[0]
    local = read_json(REPO / 'tmp/skill-boundary-v2/ten-trial-status-20261111.json')
    cloud = read_json(REPO / 'tmp/skill-boundary-v2/deepseek-ten-results-20261111.json')
    cohorts = []
    for stage in local['stages']:
        cohorts.append({'model': 'Qwen3.5:9b · 32k · fact-evidence', 'size': stage['size'],
                        'completed': stage['completed'], 'correct': stage['verified_correct'],
                        'accuracy': stage['accuracy'], 'group': 'local-' + str(stage['size'])})
        for trial in stage['trials']:
            import_trial(workspace, 'history-local-' + str(stage['size']) + '-' + str(trial['model_seed']),
                         Path(trial['trial']), trial['verified_correct'], trial['state'], 'local', stage['size'], trial['model_seed'])
    cohorts.append({'model': 'deepseek-flash · legacy', 'size': 166, 'completed': cloud['completed'],
                    'correct': cloud['verified_correct'], 'accuracy': cloud['accuracy'], 'group': 'deepseek-166'})
    for trial in cloud['trials']:
        import_trial(workspace, 'history-deepseek-' + str(trial['cohort_ordinal']),
                     Path(trial['trial_directory']), trial['verified_correct'], trial['state'], 'deepseek', 166, None)
    from experiments.skill_portal.presentation import prepare_presentation
    expanded, context = prepare_presentation(workspace, import_trial)
    cloud_group = cohorts[-1]
    cloud_group['jobs'] = ['history-deepseek-' + str(t['cohort_ordinal']) for t in cloud['trials']]
    write_json(target / 'catalog.json', {'case': case, 'cohorts': expanded + [cloud_group],
                                        'context_control': context})
    print('Imported reviewed cohorts, complete case and recording evidence', flush=True)


def import_trial(workspace, job_id, source, accepted, state, backend, size, seed):
    target = skill_jobs.folder(workspace, job_id)
    if (target / 'result.json').exists():
        return
    run = target / 'run' / f'n{size:03}' / 'dock-r1'
    run.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, run, dirs_exist_ok=True)
    request = read_json(run / 'case.json')['request']
    record = {'job_id': job_id, 'config': {'request': request, 'backend': backend, 'size': size, 'seed': seed},
              'origin': 'history', 'created_at': source.stat().st_mtime, 'dag_run_id': None, 'phase': 'finished'}
    write_json(target / 'job.json', record)
    write_json(target / 'execution.json', {'phase': 'finished', 'published': True})
    report = skill_jobs.collect_result(workspace, job_id)
    # Keep original review text alongside the exact artifacts it judges.
    report['review_evidence'] = [f['name'] for f in report['files']
                                 if 'content-review' in f['name'] or 'adjudication' in f['name']]
    report['review'] = {'state': 'accepted' if accepted else 'rejected',
                        'label': '历史内容复核通过' if accepted else '历史复核未通过 · ' + state,
                        'original_state': state, 'original_directory': str(source)}
    write_json(target / 'result.json', report)


def pid_alive(pid):
    if not pid:
        return False
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return bool(ok) and code.value == 259
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def serve(workspace):
    import msvcrt
    root = skill_jobs.root(workspace)
    root.mkdir(parents=True, exist_ok=True)
    lock = (root / 'bridge.lock').open('a+b')
    lock.seek(0)
    if not lock.read(1):
        lock.write(b'1')
        lock.flush()
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    print('Skill Airflow host bridge started', os.getpid(), flush=True)
    while True:
        active = None
        # Recover a surviving child after a bridge restart before dispatching another run.
        for path in (root / 'jobs').glob('*/execution.json'):
            state = read_json(path)
            if state.get('phase') == 'running':
                if pid_alive(state.get('pid')):
                    active = path.parent.name
                    break
                message = '执行进程已退出，原始请求与部分产物已保留'
                skill_jobs.collect_failure(workspace, path.parent.name, message)
                write_json(path, {'phase': 'failed', 'error': message, 'ended_at': time.time()})
        for claim in (root / 'jobs').glob('*/claim.json'):
            state_path = claim.parent / 'execution.json'
            if not state_path.exists() and time.time() - claim.stat().st_mtime > 30:
                write_json(state_path, {'phase': 'failed', 'error': '执行桥在启动握手前中断，请使用新运行标识重试', 'ended_at': time.time()})
            elif not state_path.exists():
                active = claim.parent.name
        write_json(root / 'bridge.json', {'pid': os.getpid(), 'heartbeat': time.time(), 'active_job': active})
        if active is None:
            for queued in sorted((root / 'queue').glob('*.json'), key=lambda p: p.stat().st_mtime):
                job_id = read_json(queued)['job_id']
                target = skill_jobs.folder(workspace, job_id)
                if (target / 'execution.json').exists() or (target / 'claim.json').exists():
                    queued.unlink()
                    continue
                with (target / 'claim.json').open('x', encoding='utf-8') as claim:
                    json.dump({'job_id': job_id, 'bridge_pid': os.getpid(), 'claimed_at': time.time()}, claim)
                with (target / 'execution.log').open('ab', buffering=0) as log:
                    process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).with_name('execute.py')),
                                                '--workspace', str(workspace), '--job-id', job_id],
                                               cwd=REPO, stdout=log, stderr=log,
                                               env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'},
                                               creationflags=subprocess.CREATE_NO_WINDOW)
                queued.unlink()
                break
        time.sleep(2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, default=REPO / 'airflow/resume_workspace')
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare(args.workspace)
    else:
        serve(args.workspace)
