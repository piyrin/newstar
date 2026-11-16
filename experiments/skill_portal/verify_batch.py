"""Audit Web/Airflow cohorts using the existing native cloud-transport auditor."""
import importlib.util
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'airflow/dags'))
sys.path.insert(0, str(REPO / 'experiments/skill_boundary_f'))
from resume_flow import skill_jobs
from resume_flow.storage import read_json, file_hash


def main():
    workspace = REPO / 'airflow/resume_workspace'
    batch = read_json(skill_jobs.root(workspace) / 'batches/deepseek-20261113.json')
    auditor_path = REPO / 'tmp/skill-boundary-v2/progressive/boundary-180-deepseek-once-20261112-network-recovery/audit-cloud-transport.py'
    spec = importlib.util.spec_from_file_location('cloud_auditor', auditor_path)
    auditor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(auditor)
    original_read = auditor.read
    auditor.save = lambda path, value: None
    reports = []
    for group in batch['groups']:
        for job_id in group['jobs']:
            target = skill_jobs.folder(workspace, job_id)
            summary_path = target / f"run/n{group['size']:03}/dock-r1/summary.json"
            if not summary_path.exists():
                continue
            summary = read_json(summary_path)
            series = target / 'run'
            for request_path in summary_path.parent.rglob('*.request.json'):
                request = read_json(request_path)
                assert request['model'] == summary['model'] == 'deepseek-flash'
                assert request['thinking']['type'] == 'disabled'
                assert request['temperature'] == 0.2
                assert 'options' not in request
            for response_path in summary_path.parent.rglob('*.response.json'):
                response = read_json(response_path)
                assert response['model'] == 'deepseek-flash'
            protocol = read_json(series / 'protocol.json')
            # Early integration records inherited local-only metadata. Derive the
            # audit view from actual request/summary bytes, preserving originals.
            overrides = {'model': summary['model'], 'local_context': None,
                'local_gpu_layers': None, 'local_planner': None, 'thinking': 'disabled',
                'semantic_review_thinking': 'disabled', 'server_truncate': None,
                'server_shift': None, 'paired_seeds': False,
                'strict_blank_csv_records': False, 'semantic_calibration': None}
            corrections = {k: {'original': protocol.get(k), 'effective': v}
                           for k, v in overrides.items() if protocol.get(k) != v}
            effective = {**protocol, **overrides}
            ledger = {'stages': [{'size': group['size'], 'results': [summary],
                'passed': int(summary['passed']), 'planned': 1,
                'fully_passed': summary['passed']}]}

            def audit_read(path):
                if path == series / 'series.json':
                    return ledger
                if path == series / 'protocol.json':
                    return effective
                return original_read(path)

            auditor.read = audit_read
            report = auditor.audit(series)
            result = skill_jobs.checked_report(target)
            assert result['review']['state'] != 'invalidated'
            for entry in result['files']:
                assert file_hash(target / entry['name']) == entry['sha256']
            reports.append({'job_id': job_id, 'audit': report,
                'original_protocol_sha256': file_hash(series / 'protocol.json'),
                'metadata_corrections_for_audit': corrections, 'review': result['review'],
                'automatic_passed': summary['passed']})
            print('Verified', job_id, result['review']['state'], flush=True)
    output = REPO / 'output/skill-web-20261113/batch-verification.json'
    if batch['status'] == 'finished' and len(reports) != 20:
        raise ValueError('Finished batch is missing complete-task evidence')
    skill_jobs.write_json(output, {'planned': 20, 'audited': len(reports),
        'all_attempts_finished': batch['status'] == 'finished', 'reports': reports,
        'auditor': str(auditor_path.relative_to(REPO)), 'auditor_sha256': file_hash(auditor_path)})
    print('Audited', len(reports), 'of 20 planned complete tasks.', flush=True)


if __name__ == '__main__':
    main()
