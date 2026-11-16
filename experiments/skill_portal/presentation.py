"""Import reviewed experiments and recording evidence without model calls."""
from pathlib import Path
import shutil

from resume_flow import skill_jobs
from resume_flow.storage import read_json
from resume_flow.skill_jobs import write_json

REPO = Path(__file__).resolve().parents[2]


def prepare_presentation(workspace, import_trial):
    verified = read_json(REPO / 'output/skill-advanced-20261112/verification.json')
    cohorts = {}
    for trial in verified['trials']:
        context = 40960 if '-f40' in trial['trial'] else 32768
        size, seed = trial['N'], trial['seed']
        group_id = f'local-{context}-{size}'
        job_id = f'history-{group_id}-{seed}'
        if context == 32768 and size in (100, 166):
            job_id = f'history-local-{size}-{seed}'
        source = REPO / trial['trial']
        import_trial(workspace, job_id, source, trial['accepted'],
                     '内容通过' if trial['accepted'] else '内容或执行未通过', 'local', size, seed)
        group = cohorts.setdefault(group_id, {
            'model': f'Qwen3.5:9b · {context // 1024}k · fact-evidence',
            'size': size, 'group': group_id, 'completed': 0, 'correct': 0, 'jobs': []})
        group['completed'] += 1
        group['correct'] += int(trial['accepted'])
        group['jobs'].append(job_id)

    above = read_json(REPO / 'tmp/skill-boundary-v2/progressive/above166-170-180-f32-20261112/effective-status-20261112.json')
    for trial in above['trials']:
        size, seed = trial['N'], trial['seed']
        job_id = f'history-local-32768-{size}-{seed}'
        import_trial(workspace, job_id, REPO / trial['trial'], trial['verified_correct'],
                     trial['failure_kind'], 'local', size, seed)
        group_id = f'local-32768-{size}'
        group = cohorts.setdefault(group_id, {'model': 'Qwen3.5:9b · 32k · fact-evidence',
            'size': size, 'group': group_id, 'completed': 0, 'correct': 0, 'jobs': []})
        group['completed'] += 1
        group['correct'] += int(trial['verified_correct'])
        group['jobs'].append(job_id)

    cloud_root = REPO / 'tmp/skill-boundary-v2/progressive/boundary-180-deepseek-once-20261112-network-recovery'
    cloud = read_json(cloud_root / 'result-20261112.json')
    import_trial(workspace, 'history-deepseek-180-1', Path(cloud['trial']), False,
                 '有歧义，未计入正确', 'deepseek', 180, None)
    cohorts['deepseek-180'] = {'model': 'deepseek-flash · legacy · 单次观测', 'size': 180,
        'group': 'deepseek-180', 'completed': 1, 'correct': 0, 'jobs': ['history-deepseek-180-1']}

    # Copy diagnostic files into the same contained, hash-checked download system.
    job_id = 'history-context-controls-20261112'
    target = skill_jobs.folder(workspace, job_id)
    source = REPO / 'tmp/skill-boundary-v2/context-controls/advanced-20261112-seed6-32k40k'
    shutil.copytree(source, target / 'run/context', dirs_exist_ok=True)
    shutil.copytree(REPO / 'tmp/skill-boundary-v2/above166-g-guard',
                    target / 'run/guard', dirs_exist_ok=True)
    shutil.copyfile(REPO / 'experiments/skill_boundary_g/VARIANT_G.md',
                    target / 'run/guard/VARIANT_G.md')
    write_json(target / 'job.json', {'job_id': job_id, 'origin': 'history',
        'phase': 'finished', 'created_at': source.stat().st_mtime, 'dag_run_id': None,
        'config': {'size': 166, 'backend': 'local', 'seed': 6}})
    write_json(target / 'result.json', {'job_id': job_id, 'partial': True,
        'automatic_passed': False, 'metrics': {'skills': 166}, 'dag': [],
        'files': skill_jobs.evidence_files(target),
        'review': {'state': 'diagnostic', 'label': '请求级容量对照，32k两次失败、40k两次返回。完整业务正确率见各组。'}})
    groups = list(cohorts.values())
    for group in groups:
        group['accuracy'] = group['correct'] / group['completed']
    return groups, verified['new_context_control']
