import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow/dags'))
from resume_flow import skill_jobs


class SkillJobsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.api = Mock()
        self.api.trigger.return_value = {'state': 'queued'}

    def payload(self):
        return {'request_id': 'test-1', 'request': '完整发布材料', 'size': 166,
                'backend': 'local', 'seed': 3}

    def test_start_is_idempotent_and_uses_airflow(self):
        first = skill_jobs.start(self.root, self.payload(), self.api)
        second = skill_jobs.start(self.root, self.payload(), self.api)
        self.assertEqual(first['job_id'], second['job_id'])
        self.assertEqual(self.api.trigger.call_args.args[0], 'skill_experiment')
        changed = {**self.payload(), 'size': 100}
        with self.assertRaises(ValueError):
            skill_jobs.start(self.root, changed, self.api)

    def test_cloud_requires_explicit_cost_consent(self):
        with self.assertRaises(ValueError):
            skill_jobs.start(self.root, {**self.payload(), 'backend': 'deepseek'}, self.api)
        self.api.trigger.assert_not_called()

    def test_cloud_normalization_can_be_validated_repeatedly(self):
        settings = skill_jobs.config({**self.payload(), 'backend': 'deepseek', 'accept_api_cost': True})
        self.assertIsNone(settings['seed'])
        self.assertEqual(skill_jobs.config(settings), settings)

    def test_qualified_180_candidate_scale_is_available(self):
        self.assertEqual(skill_jobs.config({**self.payload(), 'size': 180})['size'], 180)

    def test_transient_windows_bind_mount_replace_is_retried(self):
        with patch.object(skill_jobs, 'atomic_json', side_effect=[PermissionError('sharing'), None]) as writer:
            with patch.object(skill_jobs.time, 'sleep'):
                skill_jobs.write_json(self.root / 'heartbeat.json', {'online': True})
        self.assertEqual(writer.call_count, 2)

    def test_failed_api_submission_is_visible_and_retried_with_same_id(self):
        self.api.trigger.side_effect = ValueError('Airflow 连接失败')
        with self.assertRaises(ValueError):
            skill_jobs.start(self.root, self.payload(), self.api)
        failed = skill_jobs.catalog(self.root)['jobs'][0]
        self.assertEqual(failed['phase'], 'submission_failed')
        self.api.trigger.side_effect = None
        self.api.trigger.return_value = {'state': 'queued'}
        retried = skill_jobs.start(self.root, self.payload(), self.api)
        self.assertEqual(retried['job_id'], failed['job_id'])
        self.assertEqual(retried['phase'], 'queued')
        self.assertNotIn('error', retried)

    def make_result(self):
        from resume_flow.storage import write_json, file_hash
        job = skill_jobs.start(self.root, self.payload(), self.api)
        target = skill_jobs.folder(self.root, job['job_id'])
        trial = target / 'run/n166/dock-r1'
        artifacts = trial / 'artifacts'
        artifacts.mkdir(parents=True)
        doc = artifacts / 'STEP-001.md'
        doc.write_text('原始正文', encoding='utf-8')
        asset = artifacts / 'STEP-001-1.csv'
        asset.write_text('issue_id,course,description,status\n', encoding='utf-8')
        ref = {'reference_id': 'DOC-001', 'path': r'D:\original\artifacts\STEP-001.md',
               'content': '原始正文', 'files': [{'path': r'D:\original\artifacts\STEP-001-1.csv',
                   'reference_id': 'FILE-001-01', 'sha256': file_hash(asset)}]}
        write_json(artifacts / 'STEP-001.json', {'outputs': [ref]})
        write_json(trial / 'summary.json', {'passed': True, 'skills': 166, 'actual_skills': 2, 'nodes': 2, 'chain': 2})
        write_json(trial / 'manifest.json', {'deliverables': [{'reference_ids': ['DOC-001']}]})
        skill_jobs.collect_result(self.root, job['job_id'])
        return job, doc

    def test_windows_paths_and_implicit_attachments_are_collected(self):
        job, _ = self.make_result()
        report = skill_jobs.detail(self.root, job['job_id'])['result']
        self.assertEqual(len([f for f in report['files'] if f['final']]), 2)

    def test_explanation_excerpt_has_real_lines_and_verified_hash(self):
        from resume_flow.skill_explanations import excerpt
        job, doc = self.make_result()
        report = skill_jobs.detail(self.root, job['job_id'])['result']
        target = skill_jobs.folder(self.root, job['job_id'])
        evidence = excerpt(target, report, 'STEP-001.md', '原始正文', '正文')
        self.assertTrue(evidence['verified'])
        self.assertEqual(evidence['line'], 1)
        self.assertEqual(evidence['lines'][0]['text'], '原始正文')
        doc.write_text('已经改变', encoding='utf-8')
        self.assertFalse(excerpt(target, report, 'STEP-001.md', '已经改变', '正文')['verified'])

    def test_explanation_excerpt_reports_missing_quote(self):
        from resume_flow.skill_explanations import excerpt
        job, _ = self.make_result()
        report = skill_jobs.detail(self.root, job['job_id'])['result']
        target = skill_jobs.folder(self.root, job['job_id'])
        self.assertFalse(excerpt(target, report, 'STEP-001.md', '未出现的句子', '正文')['verified'])

    def test_success_explanation_points_to_actual_maintenance_section(self):
        from resume_flow.skill_explanations import explain
        from resume_flow.storage import file_hash
        job, _ = self.make_result()
        target = skill_jobs.folder(self.root, job['job_id'])
        report = skill_jobs.detail(self.root, job['job_id'])['result']
        for name, body in [('STEP-002.md', '安装方式未知，请向维护者确认'),
                           ('STEP-004.md', '## 3. 建议的维护职责分工\n建议维护者负责分诊与关闭')]:
            path = target / 'run/n166/dock-r1/artifacts' / name
            path.write_text(body, encoding='utf-8')
            report['files'].append({'name': path.relative_to(target).as_posix(),
                                    'sha256': file_hash(path), 'final': True})
        value = explain(target, {'job_id': 'deepseek-20261113-n100-03'}, report)
        roles = next(e for e in value['evidence'] if e['label'] == '第5项 · 建议职责')
        self.assertTrue(roles['verified'])
        self.assertTrue(roles['name'].endswith('STEP-004.md'))

    def test_old_published_model_failure_is_visible_as_failure(self):
        from resume_flow.storage import read_json, write_json
        job, _ = self.make_result()
        target = skill_jobs.folder(self.root, job['job_id'])
        report = read_json(target / 'result.json')
        report.update(automatic_passed=False, error='URLError')
        write_json(target / 'result.json', report)
        write_json(target / 'execution.json', {'phase': 'finished', 'published': True})
        detail = skill_jobs.detail(self.root, job['job_id'])
        self.assertEqual(detail['job']['phase'], 'failed')
        self.assertIn('DeepSeek', detail['job']['error'])
        self.assertIn('result', detail)

    def test_missing_final_file_invalidates_catalog_and_detail(self):
        job, doc = self.make_result()
        skill_jobs.record_review(self.root, job['job_id'], {'checks': [True] * 6, 'notes': '逐项核对'})
        doc.unlink()
        self.assertEqual(skill_jobs.detail(self.root, job['job_id'])['result']['review']['state'], 'invalidated')
        self.assertEqual(skill_jobs.catalog(self.root)['jobs'][0]['review']['state'], 'invalidated')

    def test_file_is_contained_and_hash_bound(self):
        job = skill_jobs.start(self.root, self.payload(), self.api)
        with self.assertRaises(ValueError):
            skill_jobs.download(self.root, job['job_id'], '../../secret')

    def test_manual_review_rejects_missing_results(self):
        job = skill_jobs.start(self.root, self.payload(), self.api)
        with self.assertRaises(ValueError):
            skill_jobs.record_review(self.root, job['job_id'], {'checks': [True] * 6})

    def test_crashed_run_exposes_hash_bound_partial_evidence(self):
        from resume_flow.storage import write_json
        job = skill_jobs.start(self.root, self.payload(), self.api)
        target = skill_jobs.folder(self.root, job['job_id'])
        diagnostic = target / 'run/diagnostic.json'
        write_json(diagnostic, {'synthetic_failure': True})
        report = skill_jobs.collect_failure(self.root, job['job_id'], '进程退出')
        self.assertTrue(report['partial'])
        self.assertTrue(all(not item['final'] for item in report['files']))
        self.assertEqual(skill_jobs.download(self.root, job['job_id'], 'run/diagnostic.json'), diagnostic.resolve())
        with self.assertRaises(ValueError):
            skill_jobs.record_review(self.root, job['job_id'], {'checks': [True] * 6})

    def test_torn_dag_from_terminated_writer_is_downloadable_without_blocking_recovery(self):
        job = skill_jobs.start(self.root, self.payload(), self.api)
        target = skill_jobs.folder(self.root, job['job_id'])
        dag = target / 'run/n166/dock-r1/dag.json'
        dag.parent.mkdir(parents=True)
        dag.write_text('[{"id":', encoding='utf-8')
        self.assertEqual(skill_jobs.detail(self.root, job['job_id'])['progress']['dag'], [])
        report = skill_jobs.collect_failure(self.root, job['job_id'], '写入中退出')
        self.assertEqual(report['dag'], [])
        self.assertIsNone(report['metrics']['nodes'])
        self.assertEqual(skill_jobs.download(self.root, job['job_id'], 'run/n166/dock-r1/dag.json').read_text(), '[{"id":')

    def test_native_and_normalized_files_count_as_one_reply(self):
        from resume_flow.storage import write_json
        job = skill_jobs.start(self.root, self.payload(), self.api)
        target = skill_jobs.folder(self.root, job['job_id']) / 'run/n166/dock-r1'
        write_json(target / 'planner-00.native.json', {'test_reply': True})
        write_json(target / 'planner-00.response.json', {'test_reply': True})
        self.assertEqual(skill_jobs.detail(self.root, job['job_id'])['progress']['responses'], 1)

    def start_server(self):
        from resume_flow.portal import make_portal
        self.api.status.return_value = {'state': 'running', 'tasks': [], 'dag_id': 'skill_experiment'}
        server, token = make_portal(self.root, api=self.api)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f'http://127.0.0.1:{server.server_port}', token

    def test_http_page_trigger_status_preview_download_and_review(self):
        base, token = self.start_server()

        def call(path, payload=None):
            body = None if payload is None else json.dumps(payload).encode('utf-8')
            request = urllib.request.Request(base + path, body,
                {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(request) as response:
                return response.read()

        self.assertIn('Skill 编排实验', call('/skills').decode('utf-8'))
        created = json.loads(call('/api/skills/start', self.payload()))
        self.assertEqual(created['job_id'], 'test-1')
        job, _ = self.make_result()
        detail = json.loads(call('/api/skills/job?job_id=' + job['job_id']))
        self.assertEqual(detail['airflow']['state'], 'running')
        entry = next(f for f in detail['result']['files'] if f['final'] and f['name'].endswith('.md'))
        query = '?job_id=' + job['job_id'] + '&name=' + urllib.parse.quote(entry['name'])
        self.assertEqual(json.loads(call('/api/skills/file' + query + '&preview=1'))['content'], '原始正文')
        self.assertEqual(call('/api/skills/file' + query).decode('utf-8'), '原始正文')
        review = json.loads(call('/api/skills/review', {'job_id': job['job_id'], 'checks': [True] * 6}))
        self.assertEqual(review['state'], 'accepted')
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(base + '/api/skills/catalog')
        with self.assertRaises(urllib.error.HTTPError):
            call('/api/skills/file?job_id=test-1&name=../../job.json')


if __name__ == '__main__':
    unittest.main()
