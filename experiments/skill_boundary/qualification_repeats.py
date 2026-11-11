"""Frozen local smoke repetitions; automatic scores never establish stability."""
import argparse
import copy
import hashlib
from pathlib import Path
import re
import shutil

from local_api import LocalAPI
from local_qualification import extend_registry, qualify, validate_case
from runner import read, save


RUNTIME = ['qualification_repeats.py', 'local_qualification.py', 'local_api.py', 'runner.py']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_jobs(names, seeds):
    if (len(seeds) != 3 or any(type(s) is not int or s < 0 for s in seeds)
            or len(set(seeds)) != 3 or not names or len(set(names)) != len(names)
            or any(not re.fullmatch(r'[a-zA-Z0-9_-]+', n) for n in names)):
        raise ValueError('require unique names and exactly three distinct nonnegative seeds')
    return [{'id': f'{name}/trial-{index + 1:02}', 'tool_name': name, 'seed': seed,
             'kind': 'independent_seed' if index < 3 else 'same_seed_reproduction',
             'reproduces': None if index < 3 else f'{name}/trial-01'}
            for index, seed in enumerate([*seeds, seeds[0]]) for name in names]


def freeze_campaign(root, rows, cases, seeds):
    if root.exists():
        raise FileExistsError(root)
    extend_registry([], rows)
    names = [r['tool_name'] for r in rows]
    jobs = make_jobs(names, seeds)
    if set(cases) != set(names):
        raise ValueError('cases must cover exactly the selected original sources')
    for row in rows:
        source = Path(row['path'])
        if sha(source) != row['sha256']:
            raise ValueError('source hash changed')
        if not validate_case(cases[row['tool_name']], source.read_text(encoding='utf-8-sig')):
            raise ValueError('invalid original source-grounded case')
    root.mkdir(parents=True)
    frozen = []
    for row in rows:
        relative = Path('sources') / row['tool_name'] / 'SKILL.md'
        destination = root / relative
        destination.parent.mkdir(parents=True)
        shutil.copyfile(row['path'], destination)
        frozen.append({**row, 'original_source_path': row['path'], 'path': relative.as_posix()})
    save(root / 'registry.json', frozen)
    save(root / 'cases.json', copy.deepcopy(cases))
    save(root / 'jobs.json', jobs)
    save(root / 'protocol.json', {
        'backend': 'local', 'model': 'qwen3.5:9b', 'context': 32768,
        'gpu_layers': 24, 'thinking': 'off', 'sampling': 'legacy',
        'server_truncate': False, 'server_shift': False, 'paid_api': False,
        'seeds': seeds, 'typed_worker': True, 'hidden_retries': 0,
        'qualification': 'three seed draws plus one separately labelled same-seed reproduction',
        'acceptance': 'all original criteria, source capability, hard checks and direct content review',
        'pool_gate': 'all four trials content-reviewed correct; failures and original scores retained',
        'limits': 'finite smoke repetitions do not guarantee future correctness or universal stability'})
    for name in RUNTIME:
        destination = root / 'implementation' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(__file__).parent / name, destination)
    immutable = {str(p.relative_to(root).as_posix()): sha(p)
                 for p in root.rglob('*') if p.is_file()}
    save(root / 'immutable.json', immutable)
    return jobs


def run_campaign(root, api_factory=LocalAPI, qualifier=qualify):
    for name, expected in read(root / 'immutable.json').items():
        if sha(root / name) != expected:
            raise ValueError('frozen input changed: ' + name)
    for name in RUNTIME:
        if sha(Path(__file__).parent / name) != sha(root / 'implementation' / name):
            raise ValueError('runtime differs from frozen implementation: ' + name)
    rows = {r['tool_name']: r for r in read(root / 'registry.json')}
    cases = read(root / 'cases.json')
    jobs = read(root / 'jobs.json')
    results = []
    ledger = {'status': 'running', 'planned': len(jobs), 'completed': 0,
              'automatic_passed': 0, 'results': results,
              'planned_independent_trials': sum(j['kind'] == 'independent_seed' for j in jobs),
              'planned_reproductions': sum(j['kind'] == 'same_seed_reproduction' for j in jobs)}
    for job in jobs:
        if (root / 'STOP_AFTER_CURRENT').exists():
            break
        folder = root / 'trials' / job['id']
        row = rows[job['tool_name']]
        if (folder / 'summary.json').exists():
            result = read(folder / 'summary.json')
            if result['source_sha256'] != row['sha256'] or result['tool_name'] != row['tool_name']:
                raise ValueError('saved summary does not match frozen source')
        elif folder.exists():
            raise RuntimeError('partial attempt preserved; inspect before resume: ' + str(folder))
        else:
            actual_row = {**row, 'path': str((root / row['path']).resolve())}
            api = api_factory(gpu_layers=24, seed=job['seed'])
            result = qualifier(api, actual_row, folder, fixed_case=cases[job['tool_name']],
                               typed_worker=True)
            print('REPEATED_QUALIFICATION', job['id'], job['seed'], result['passed'],
                  result.get('error', ''), flush=True)
        results.append({'job': job, 'summary': result})
        ledger.update(completed=len(results), results=results,
                      automatic_passed=sum(r['summary']['passed'] is True for r in results))
        save(root / 'ledger.json', ledger)
    ledger['status'] = 'all_trials_finished' if len(results) == len(jobs) else 'stopped_after_current'
    save(root / 'ledger.json', ledger)
    return ledger


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--campaign', required=True, type=Path)
    parser.add_argument('--registry', type=Path)
    parser.add_argument('--cases', type=Path)
    parser.add_argument('--seeds', nargs=3, type=int, default=[101, 102, 103])
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if not args.resume:
        if not args.registry or not args.cases:
            parser.error('new campaign requires registry and cases')
        freeze_campaign(args.campaign, read(args.registry), read(args.cases), args.seeds)
    elif args.registry or args.cases:
        parser.error('resume uses only frozen campaign inputs')
    run_campaign(args.campaign)


if __name__ == '__main__':
    main()
