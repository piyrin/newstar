"""Verify the advanced-tier evidence without model calls or historical writes."""

import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path

import audit_progressive
from context_replay import classify_resource, input_digest
from runner import BASE, REPO, read


def require(condition, message):
    if not condition:
        raise ValueError(message)


def review_trial(trial, baseline_case):
    summary = read(trial / 'summary.json')
    require(read(trial / 'case.json') == baseline_case, f'Changed task: {trial}')
    reviews = sorted(trial.glob('content-adjudication-*.json'))
    if not reviews:
        reviews = sorted(trial.glob('content-review-*.json'))
    review_path = reviews[-1] if reviews else None
    review = read(review_path) if review_path else None
    require(not summary['passed'] or review is not None, f'Missing content review: {trial}')
    accepted = bool(review and review['effective_passed'])
    require(not accepted or summary['passed'], f'Accepted incomplete task: {trial}')
    references = {}
    for node_path in sorted((trial / 'artifacts').glob('STEP-*.json')):
        references.update({r['reference_id']: r for r in read(node_path)['outputs']})
    selected = set()
    if (trial / 'manifest.json').exists():
        selected = {ref for item in read(trial / 'manifest.json')['deliverables']
                    for ref in item['reference_ids']}
    if review:
        hashes = review['final_document_hashes']
        require(selected <= hashes.keys(), f'Unreviewed final references: {trial}')
        for ident, expected in hashes.items():
            ref = references[ident]
            content = Path(ref['path']).read_text(encoding='utf-8-sig')
            require(hashlib.sha256(content.encode()).hexdigest() == expected,
                    f'Content review hash mismatch: {trial}/{ident}')
        for evidence in review.get('criteria_evidence', []) + review.get('findings', []):
            line_id = evidence.get('line_id', '')
            if ':L' in line_id and evidence.get('text'):
                ident, number = line_id.rsplit(':L', 1)
                lines = Path(references[ident]['path']).read_text(encoding='utf-8-sig').splitlines()
                require(lines[int(number) - 1] == evidence['text'],
                        f'Review line mismatch: {trial}/{line_id}')
    if accepted:
        for ident in selected:
            ref = references[ident]
            if ref['kind'] == 'file' and Path(ref['path']).suffix == '.csv':
                rows = list(csv.reader(io.StringIO(ref['content'])))
                if rows and rows[0] == baseline_case['facts']['feedback_fields']:
                    require(len(rows) == 1, f'Nonempty feedback CSV: {trial}/{ident}')
    return {'trial': str(trial.relative_to(REPO)), 'N': summary['skills'],
            'seed': summary.get('local_seed'), 'accepted': accepted,
            'automatic_passed': summary['passed'], 'error': summary.get('error'),
            'K': summary['actual_skills'], 'nodes': summary['nodes'], 'chain': summary['chain'],
            'review': str(review_path.relative_to(REPO)) if review_path else None}


def verify_context(folder):
    protocol = read(folder / 'protocol.json')
    source = read(folder / 'source-request.json')
    require(protocol['only_changed_field'] == 'options.num_ctx', 'Context protocol changed')
    require(protocol['contexts'] == [32768, 40960] and protocol['repeats'] == 2,
            'Incomplete context experiment design')
    state = read(folder / 'state.json')
    require(state['status'] == 'finished', 'Context experiment still running')
    results = []
    for repeat in (1, 2):
        for context in (32768, 40960):
            run = folder / f'ctx{context}-r{repeat}'
            request = read(run / 'request.json')
            expected = copy.deepcopy(source)
            expected['options']['num_ctx'] = context
            require(request == expected, f'Uncontrolled input change: {run}')
            result = read(run / 'summary.json')
            require(result['input_digest'] == input_digest(source), f'Digest mismatch: {run}')
            if context == 32768:
                require(result['status'] == 'context_failure' and result['http_status'] == 400,
                        f'Unexpected 32k result: {run}')
                error = read(run / 'error.json')['error']
                require('32849' in error and '32768' in error, f'Unexpected failure: {run}')
            else:
                raw = read(run / 'native.json')
                require(result['status'] == 'complete_response_without_detected_truncation',
                        f'Unexpected 40k result: {run}')
                require(raw['done'] is True and raw['done_reason'] == 'stop',
                        f'Incomplete response: {run}')
                require(raw['prompt_eval_count'] == 32849, f'Unexpected prompt count: {run}')
                require(raw['message'].get('tool_calls'), f'Missing native tool call: {run}')
                log = (run / 'runtime.log').read_text(encoding='utf-8')
                require(classify_resource(raw, log) == result['status'], f'Runtime mismatch: {run}')
            results.append(result)
    require(state['results'] == results, 'Context ledger mismatch')
    return {'protocol': str(folder.relative_to(REPO) / 'protocol.json'), 'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=REPO / 'output/skill-advanced-20261112/verification.json')
    args = parser.parse_args()
    baseline_case = read(BASE / 'progressive/boundary-repeatqualified-166-f32/n166/dock-r3/case.json')
    series_names = [
        'boundary-repeatqualified-166-f32-minimum-control',
        'boundary-repeatqualified-166-f32-stability-refinement',
        'boundary-repeatqualified-166-f32',
        'boundary-repeatqualified-166-f32-ten-trial-supplement',
        'boundary-repeatqualified-166-f40',
    ]
    series_reports, trials = [], []
    # Reuse the existing full source/upstream/native-output auditor. Capture its
    # derived report in memory so historical audit files keep their original bytes.
    original_save = audit_progressive.save
    audit_progressive.save = lambda path, value: None
    try:
        for name in series_names:
            series = BASE / 'progressive' / name
            report = audit_progressive.audit(series)
            series_reports.append(report)
            for summary in sorted(series.glob('n*/dock-r*/summary.json')):
                trials.append(review_trial(summary.parent, baseline_case))
    finally:
        audit_progressive.save = original_save
    groups = []
    for name in series_names:
        subset = [t for t in trials if f'/{name}/' in t['trial'].replace('\\', '/')]
        for size in sorted({t['N'] for t in subset}):
            rows = [t for t in subset if t['N'] == size]
            groups.append({'series': name, 'N': size, 'completed': len(rows),
                           'accepted': sum(t['accepted'] for t in rows)})
    context = verify_context(BASE / 'context-controls/advanced-20261112-seed6-32k40k')
    expected_groups = [(5, 3, 1), (10, 3, 1), (40, 3, 1), (60, 3, 2), (80, 3, 0),
                       (100, 3, 1), (166, 3, 1), (100, 7, 5), (166, 7, 1),
                       (100, 3, 1), (166, 3, 1)]
    require([(g['N'], g['completed'], g['accepted']) for g in groups] == expected_groups,
            'Report counts differ from reviewed evidence')
    output = {'checked_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Source, execution, dependencies and existing content-review bindings; four new local diagnostic requests',
              'all_checks_passed': True, 'trials_checked': len(trials),
              'model_calls_by_this_verifier': 0, 'series_audits': series_reports,
              'groups': groups, 'trials': trials, 'new_context_control': context,
              'personal_narrated_recording': 'pending', 'course_submission': 'pending'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    for group in groups:
        print(f"{group['series']} N{group['N']}: {group['accepted']}/{group['completed']}")
    print(f'Verified {len(trials)} complete-task observations and four fresh context controls.')
    print(f'Report: {args.output}')


if __name__ == '__main__':
    main()
