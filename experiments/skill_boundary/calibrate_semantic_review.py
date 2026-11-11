"""Known-case diagnostic only; these calls are never business capacity trials."""
import argparse
import hashlib
from pathlib import Path
import shutil

from local_api import LocalAPI
from progressive import physical_checks, csv_asset_issues, qualified
from runner import BASE, read, save
from semantic_review import review
from extended_release_facts import extended_release_fact_issues


def classify_case(api, case, selected, out, expected):
    result = {'expected_passed': expected, 'predicted_passed': None,
              'matches_expected': False, 'scope': 'known-case review calibration, not business trial'}
    try:
        hard = physical_checks(case, selected, check_csv_shape=True,
                               strict_feedback_csv=True, strict_release_facts=True,extended_release_claims=True)
        save(out / 'extended-fact-issues.json',extended_release_fact_issues(case['facts'],selected))
        shape = csv_asset_issues(selected, strict_blank_rows=True)
        hard['csv_assets_rectangular'] = not shape
        save(out / 'strict-csv-issues.json', shape)
        result['physical_checks'] = hard
        if not all(hard.values()):
            result.update(predicted_passed=False, decision_origin='strict_physical_gate',
                          semantic_checks_not_evaluated=True)
        else:
            # expected is deliberately never included in this model call.
            verdict = review(api, case, selected, out)
            save(out / 'verdict.json', verdict)
            result.update(predicted_passed=qualified(verdict), decision_origin='local_evidence_review')
        result['matches_expected'] = result['predicted_passed'] is expected
    except Exception as exc:
        result['error'] = str(exc)[:1000]
    save(out / 'summary.json', result)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--prefix', required=True)
    p.add_argument('--inputs', type=Path, required=True)
    args = p.parse_args()
    source = args.inputs.resolve()
    for path, expected in read(source / 'immutable.json').items():
        if hashlib.sha256((source / path).read_bytes()).hexdigest() != expected:
            raise ValueError('calibration input changed: ' + path)
    target = BASE / 'semantic-calibration' / args.prefix
    target.mkdir(parents=True, exist_ok=False)
    fixtures = read(source / 'fixtures.json')
    save(target / 'fixtures.json', fixtures)
    for path in Path(__file__).parent.glob('*.py'):
        shutil.copyfile(path, target / path.name)
    save(target / 'protocol.json', {'scope': 'known-case diagnostic, not fresh business success or capacity',
        'backend': 'local', 'model': 'qwen3.5:9b', 'context': 32768, 'gpu_layers': 24,
        'thinking': 'off', 'sampling': 'qwen-recommended', 'seed': 1,
        'hidden_retries': 0, 'server_truncate': False, 'server_shift': False,
        'inputs': str(source), 'gold_labels_visible_to_model': False,
        'layers':'strict CSV and observed-claim rules first; local evidence review only for remaining cases',
        'acceptance': 'all preregistered expected labels matched; transport/error is unknown, not correct rejection'})
    api = LocalAPI(context=32768, thinking='off', sampling='qwen-recommended', gpu_layers=24, seed=1)
    results = []
    for sample in fixtures:
        case = read(source / sample['case'])
        selected = read(source / sample['selected'])
        for ref in selected.values():
            ref['path'] = str((source / ref['path']).resolve())
            for asset in ref.get('files', []):
                asset['path'] = str((source / asset['path']).resolve())
        result = classify_case(api, case, selected, target / sample['id'], sample['expected_passed'])
        results.append({'id': sample['id'], **result})
        save(target / 'ledger.json', {'status': 'running', 'planned': len(fixtures),
            'completed': len(results), 'matched': sum(r['matches_expected'] for r in results), 'results': results})
        print('CALIBRATION', sample['id'], result['predicted_passed'], result['matches_expected'],
              result.get('error', ''), flush=True)
    save(target / 'ledger.json', {'status': 'all_cases_finished', 'planned': len(fixtures),
        'completed': len(results), 'matched': sum(r['matches_expected'] for r in results), 'results': results})


if __name__ == '__main__':
    main()
