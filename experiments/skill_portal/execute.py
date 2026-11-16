"""One host-native run, invoked only from the Airflow shared queue bridge."""
import argparse
import copy
import hashlib
import json
import os
import runpy
from pathlib import Path, PurePosixPath
import sys
import time
import traceback
import urllib.request

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'airflow/dags'))
sys.path.insert(0, str(REPO / 'experiments/skill_boundary_f'))
from resume_flow import skill_jobs
from resume_flow.storage import read_json
from resume_flow.skill_jobs import write_json


def frozen_runtime_hashes(source_runtime, frozen_manifest):
    prefix = PurePosixPath('experiments/skill_boundary_f')
    frozen = {PurePosixPath(name).name: digest for name, digest in frozen_manifest.items()
              if PurePosixPath(name).parent == prefix and name.endswith('.py')}
    if not frozen:
        raise ValueError('Frozen Skill runtime manifest is empty')
    hashes = {}
    for name, expected in frozen.items():
        path = source_runtime / name
        if not path.is_file():
            raise ValueError('Frozen implementation missing ' + name)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected != actual:
            raise ValueError('Loaded runtime differs from frozen implementation ' + name)
        hashes[name] = actual
    return hashes


def execute(workspace, job_id):
    from boundary_scan import validate_calibration
    from progressive import run_one
    from runner import save
    from resume_flow.config import load_env
    load_env(REPO / 'airflow/.env')
    target = skill_jobs.folder(workspace, job_id)
    settings = skill_jobs.config(read_json(target / 'job.json')['config'])
    bundle = REPO / 'deliverables/skill-boundary-ten-trial-repro-20261111'
    source_runtime = REPO / 'experiments/skill_boundary_f'
    runpy.run_path(str(bundle / 'verify_bundle.py'))
    frozen_manifest = read_json(bundle / 'manifest.sha256.json')
    runtime_hashes = frozen_runtime_hashes(source_runtime, frozen_manifest)
    validate_calibration(bundle / 'calibration32')
    rows = read_json(bundle / 'inputs/registry.json')
    for row in rows:
        source = (bundle / row['path']).resolve()
        if not source.is_relative_to(bundle) or hashlib.sha256(source.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Skill source integrity mismatch ' + row['tool_name'])
        row['path'] = str(source)
    if len(rows) != 166 or len({row['sha256'] for row in rows}) != 166:
        raise ValueError('Expected 166 unique original Skill sources')
    if settings['size'] == 180:
        expanded = read_json(REPO / 'tmp/skill-boundary-v2/above166-preparation/registry-180.json')
        if (len(expanded) != 180 or len({r['sha256'] for r in expanded}) != 180
                or [(r['tool_name'], r['sha256']) for r in expanded[:166]]
                != [(r['tool_name'], r['sha256']) for r in rows]):
            raise ValueError('Expanded registry must preserve the original 166-source prefix')
        for row in expanded:
            source = Path(row['path']).resolve()
            if not source.is_relative_to(REPO) or hashlib.sha256(source.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('Expanded source integrity mismatch ' + row['tool_name'])
        rows = expanded
    rows = rows[:settings['size']]
    model_identity = None
    if settings['backend'] == 'local':
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:11434/api/version', timeout=10) as response:
            version = json.load(response)['version']
        with opener.open('http://127.0.0.1:11434/api/tags', timeout=10) as response:
            models = json.load(response)['models']
        expected = '6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7'
        if version != '0.33.1' or not any(model['name'] == 'qwen3.5:9b' and model['digest'] == expected for model in models):
            raise ValueError('Local Ollama version or model digest differs from frozen experiment')
        model_identity = {'ollama_version': version, 'model': 'qwen3.5:9b', 'digest': expected}
    case = copy.deepcopy(read_json(bundle / 'inputs/fixtures.json')[0])
    original_request = case['request']
    case['request'] = settings['request']
    series = target / 'run'
    series.mkdir(exist_ok=False)
    protocol = read_json(bundle / 'inputs/protocol.json')
    protocol.update(scope='Web/Airflow new standalone observation; excluded from historical ten-trial rates',
                    sizes=[settings['size']], repeats=1, backend=settings['backend'],
                    seed=settings['seed'], request_edited=case['request'] != original_request,
                    model_identity=model_identity,
                    runtime_hashes=runtime_hashes,
                    semantic_review_profile='fact-evidence' if settings['backend'] == 'local' else 'legacy',
                    model='qwen3.5:9b' if settings['backend'] == 'local' else os.environ.get('DEEPSEEK_MODEL', 'deepseek-flash'),
                    local_context=32768 if settings['backend'] == 'local' else None,
                    local_gpu_layers=24 if settings['backend'] == 'local' else None,
                    local_planner='native' if settings['backend'] == 'local' else None,
                    thinking='off' if settings['backend'] == 'local' else 'disabled',
                    semantic_review_thinking='off' if settings['backend'] == 'local' else 'disabled',
                    server_truncate=False if settings['backend'] == 'local' else None,
                    server_shift=False if settings['backend'] == 'local' else None,
                    paired_seeds=False,
                    strict_blank_csv_records=settings['backend'] == 'local',
                    semantic_calibration=protocol.get('semantic_calibration') if settings['backend'] == 'local' else None)
    if settings['size'] == 180:
        protocol['expanded_registry_source'] = 'tmp/skill-boundary-v2/above166-preparation/registry-180.json'
        protocol['recent_extension_gate'] = 'New fourteen sources retain historical single-use smoke qualification'
    save(series / 'protocol.json', protocol)
    save(series / 'registry.json', rows)
    save(series / 'fixtures.json', [case])
    print('真实模型任务开始', job_id, settings, flush=True)
    result = run_one(series, rows, case, 1, variant='grounded', schema_ids='controls-only',
                     backend=settings['backend'], local_context=32768, exposure='on-call',
                     local_thinking='off', local_sampling='legacy', local_planner='native',
                     local_gpu_layers=24, planner_artifacts='receipts', strict_feedback_csv=True,
                     short_circuit_hard_failure=True, strict_release_facts=True,
                     candidate_order='frozen', local_seed=settings['seed'],
                     semantic_review_profile=protocol['semantic_review_profile'])
    print('真实模型任务结束', result, flush=True)
    skill_jobs.collect_result(workspace, job_id)
    if not result['passed']:
        raise ValueError(result.get('error') or '模型交付未通过自动核验，请查看本次审查证据')
    write_json(target / 'execution.json', {'phase': 'finished', 'ended_at': time.time(),
                                         'automatic_passed': result['passed']})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--job-id', required=True)
    args = parser.parse_args()
    try:
        write_json(skill_jobs.folder(args.workspace, args.job_id) / 'execution.json',
                   {'phase': 'running', 'pid': os.getpid(), 'started_at': time.time()})
        execute(args.workspace, args.job_id)
    except Exception as error:
        traceback.print_exc()
        try:
            skill_jobs.collect_failure(args.workspace, args.job_id, str(error)[:1000])
        except Exception:
            traceback.print_exc()
        write_json(skill_jobs.folder(args.workspace, args.job_id) / 'execution.json',
                   {'phase': 'failed', 'ended_at': time.time(), 'error': str(error)[:1000]})
        sys.exit(1)
