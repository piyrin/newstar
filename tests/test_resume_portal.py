import json
import base64
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow/dags'))
from resume_flow.portal import make_portal
from resume_flow.sample import SAMPLE_TEXT
from resume_flow.storage import snapshot, write_json, read_json
from resume_flow.extract import extract_run
from resume_flow.workflow import collect_facts, draft_resume
from resume_flow.review import prepare_review


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        p = self.ws / 'inputs/demo/profile.md'
        p.parent.mkdir(parents=True)
        p.write_text(SAMPLE_TEXT, encoding='utf-8')
        snapshot(self.ws, 'demo', 'run1')
        extract_run(self.ws, 'run1')
        collect_facts(self.ws, 'run1', 'offline')
        draft_resume(self.ws, 'run1', 'offline')
        prepare_review(self.ws, 'run1')
        self.api = Mock()
        self.api.base = 'http://localhost:8080'
        self.api.trigger.side_effect = lambda dag, run, conf: {'state': 'queued', 'dag_run_id': run}
        self.server, self.token = make_portal(self.ws, api=self.api)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def call(self, path, data=None, headers=None):
        req = urllib.request.Request(self.base + path, None if data is None else json.dumps(data).encode(),
                                     headers or {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            return json.load(response)

    def test_session_requires_same_origin_custom_header(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.call('/api/session', headers={'X-Unrelated': '1'})
        self.assertEqual(self.call('/api/session', headers={'X-Resume-Portal': '1'})['token'], self.token)
        with self.assertRaises(urllib.error.HTTPError):
            self.call('/api/session', headers={'X-Resume-Portal': '1', 'Origin': 'https://other.example'})

    def test_jobs_lists_review_and_state_does_not_approve(self):
        self.assertEqual(self.call('/api/jobs')['cases'], ['demo'])
        self.assertEqual(self.call('/api/state?run_key=run1')['run_key'], 'run1')
        self.assertFalse((self.ws / 'reviews/run1/approval.json').exists())

    def test_delete_restore_hides_draft_and_stops_only_linked_run(self):
        from resume_flow.approval_wait import publish_review_request
        publish_review_request(self.ws, {'run_key': 'run1', 'skip': True}, 'waiting-run')
        self.api.cancel_waiting.return_value = {'result': 'stopped', 'state': 'failed'}
        result = self.call('/api/draft-delete', {'run_key': 'run1'})
        self.assertTrue(result['deleted'])
        self.api.cancel_waiting.assert_called_once_with('resume_prepare', 'waiting-run')
        listing = self.call('/api/jobs')
        self.assertEqual(listing['runs'], [])
        self.assertEqual(listing['deleted_drafts'][0]['run_key'], 'run1')
        self.assertTrue((self.ws / 'inputs/demo/profile.md').is_file())
        with self.assertRaises(urllib.error.HTTPError):
            self.call('/api/state?run_key=run1')
        self.call('/api/draft-restore', {'run_key': 'run1'})
        self.assertEqual(len(self.call('/api/jobs')['runs']), 1)

    def test_project_preview_consolidates_legacy_fact_bullets_without_saving(self):
        from resume_flow.storage import run_dir
        folder = run_dir(self.ws, 'run1')
        bundle = read_json(folder / 'facts.json')
        facts = [{'id': 'p1', 'field': 'project', 'source': 'profile.md', 'value': 'huawei'},
                 {'id': 'p2', 'field': 'project', 'source': 'profile.md', 'value': '实现姿态特征提取'}]
        bundle['facts'].extend(facts)
        write_json(folder / 'facts.json', bundle)
        extracted = read_json(folder / 'extracted.json')
        extracted['segments'][0]['text'] = '项目名称 huawei\n仓库链接 https://github.com/example/huawei\n# 端侧跌倒检测\n实现姿态特征提取'
        write_json(folder / 'extracted.json', extracted)
        state = self.call('/api/state?run_key=run1')
        before = read_json(self.ws / 'reviews/run1/resume.json')
        state['resume']['sections'].append({'title': '项目经历', 'items': [
            {'title': '', 'paragraphs': [f['value']], 'fact_ids': [f['id']]} for f in facts]})
        result = self.call('/api/project-preview?run_key=run1', {
            'revision': state['revision'], 'resume': state['resume'], 'fact_ids': ['p1','p2'],
            'contribution': '本人负责特征处理模块'})
        project = result['resume']['sections'][-1]['items']
        self.assertEqual(len(project), 1)
        self.assertEqual(project[0]['title'], '端侧跌倒检测')
        self.assertIn('本人负责特征处理模块', project[0]['paragraphs'])
        self.assertEqual(read_json(self.ws / 'reviews/run1/resume.json'), before)

    def test_prepare_validates_case_and_uses_airflow(self):
        result = self.call('/api/prepare', {'case_id': 'demo', 'target': '技术实习', 'mode': 'offline', 'request_id': 'req1'})
        self.assertEqual(result['state'], 'queued')
        self.assertEqual(self.api.trigger.call_args.args[0], 'resume_prepare')
        with self.assertRaises(urllib.error.HTTPError):
            self.call('/api/prepare', {'case_id': '../escape', 'mode': 'offline', 'request_id': 'req2'})

    def test_intake_form_tracks_pending_input_and_submission(self):
        from resume_flow.intake import open_intake
        record = open_intake(self.ws, 'resume_start', 'new-intake', {'case_id': 'new'})
        self.assertEqual(self.call('/api/intakes')['intakes'][0]['id'], record['id'])
        self.assertEqual(self.call('/api/intake?intake_id=' + record['id'])['state'], 'waiting_materials')
        with self.assertRaises(urllib.error.HTTPError):
            self.call('/api/intake-submit', {'intake_id': record['id'], 'mode': 'offline'})
        self.call('/api/import', {'case_id': 'new', 'request_id': 'intake-import',
                   'files': [{'name': 'profile.md', 'content_base64': base64.b64encode(SAMPLE_TEXT.encode()).decode()}]})
        result = self.call('/api/intake-submit', {'intake_id': record['id'], 'mode': 'offline'})
        self.assertEqual(result['state'], 'submitted')
        self.api.trigger.assert_not_called()
        self.assertEqual(self.call('/api/intakes')['intakes'], [])

    def test_export_refuses_unapproved_and_unsafe_download(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.call('/api/export?run_key=run1', {'request_id': 'e1'})
        self.api.trigger.assert_not_called()
        with self.assertRaises(urllib.error.HTTPError):
            self.call('/api/file?run_key=run1&export_key=anything&name=../../facts.json')

    def test_approved_export_is_queued_and_tracks_location(self):
        state = self.call('/api/state?run_key=run1')
        state['selection'] = {'schema_version': 1, 'template_id': 'classic', 'mode': 'print', 'paper': 'A4'}
        self.call('/api/approve?run_key=run1', state)
        result = self.call('/api/export?run_key=run1', {'request_id': 'e1'})
        self.assertEqual(result['state'], 'queued')
        self.assertEqual(self.api.trigger.call_args.args[0], 'resume_export')
        self.assertIn('export_key', result)

    def test_retry_shows_current_request_instead_of_old_failure(self):
        state = self.call('/api/state?run_key=run1')
        state['selection'] = {'schema_version': 1, 'template_id': 'classic', 'mode': 'print', 'paper': 'A4'}
        self.call('/api/approve?run_key=run1', state)
        result = self.call('/api/export?run_key=run1', {'request_id': 'retry1'})
        write_json(self.ws / 'outputs/old/input.json', {'run_key': 'run1', 'approval_hash': result['approval_hash']})
        write_json(self.ws / 'outputs/old/report.json', {'state': 'failed', 'ok': False})
        self.api.status.return_value = {'state': 'queued', 'tasks': []}
        status = self.call('/api/export-status?run_key=run1')
        self.assertEqual(status['export_key'], result['export_key'])
        self.assertEqual(status['execution']['state'], 'queued')
        self.assertNotEqual(status['state'], 'failed')
        self.assertEqual(status.get('files', []), [])

    def test_import_endpoint_accepts_document_sized_body(self):
        content = b'a' * 300_001
        result = self.call('/api/import', {'case_id': 'imported', 'request_id': 'import1',
                           'files': [{'name': 'profile.md', 'content_base64': base64.b64encode(content).decode()}]})
        self.assertEqual(result['files'][0]['action'], 'added')
        self.assertEqual((self.ws / 'inputs/imported/profile.md').read_bytes(), content)

    def test_confirm_continues_the_same_dag_run(self):
        from resume_flow.approval_wait import publish_review_request
        from resume_flow.storage import digest
        publish_review_request(self.ws, {'run_key': 'run1', 'skip': True}, 'manual-flow')
        state = self.call('/api/state?run_key=run1')
        state['selection'] = {'schema_version': 1, 'template_id': 'classic', 'mode': 'print', 'paper': 'A4'}
        self.call('/api/approve?run_key=run1', state)
        self.api.status.return_value = {'state': 'running', 'tasks': [{'task_id': 'await_review', 'state': 'up_for_reschedule'}]}
        result = self.call('/api/export?run_key=run1&dag_run_id=manual-flow', {'request_id': 'continue1'})
        self.assertEqual(result['dag_id'], 'resume_prepare')
        self.assertEqual(result['dag_run_id'], 'manual-flow')
        self.api.trigger.assert_not_called()
        record = read_json(self.ws / 'requests' / (digest('manual-flow') + '.json'))
        self.assertEqual(record['approval_hash'], result['approval_hash'])

    def test_new_rescheduling_review_uses_same_run_before_first_sensor_poke(self):
        from resume_flow.approval_wait import publish_review_request
        publish_review_request(self.ws, {'run_key': 'run1', 'skip': False}, 'new-sensor-flow',
                               {'review_wait': 'reschedule'})
        state = self.call('/api/state?run_key=run1')
        state['selection'] = {'schema_version': 1, 'template_id': 'classic', 'mode': 'print', 'paper': 'A4'}
        self.call('/api/approve?run_key=run1', state)
        self.api.status.return_value = {'state': 'running', 'tasks': [{'task_id': 'await_review', 'state': 'scheduled'}]}
        result = self.call('/api/export?run_key=run1&dag_run_id=new-sensor-flow', {'request_id': 'confirm-sensor'})
        self.assertEqual(result['dag_run_id'], 'new-sensor-flow')
        self.api.trigger.assert_not_called()

    def test_explicit_sensor_review_does_not_bind_another_waiting_run(self):
        from resume_flow.approval_wait import publish_review_request
        state = self.call('/api/state?run_key=run1')
        state['selection'] = {'schema_version': 1, 'template_id': 'classic', 'mode': 'print', 'paper': 'A4'}
        self.call('/api/approve?run_key=run1', state)
        self.api.status.return_value = {'state': 'running', 'tasks': [{'task_id': 'await_review', 'state': 'up_for_reschedule'}]}
        for run in ('sensor-one', 'sensor-two'):
            publish_review_request(self.ws, {'run_key': 'run1', 'skip': True}, run,
                                   {'review_wait': 'reschedule'})
            result = self.call('/api/export?run_key=run1&dag_run_id=' + run, {'request_id': run})
            self.assertEqual(result['dag_run_id'], run)
        self.api.trigger.assert_not_called()

    def test_confirmation_after_old_gate_skipped_restores_original_run(self):
        from resume_flow.approval_wait import publish_review_request
        publish_review_request(self.ws, {'run_key': 'run1', 'skip': True}, 'ending-flow')
        state = self.call('/api/state?run_key=run1')
        state['selection'] = {'schema_version': 1, 'template_id': 'classic', 'mode': 'print', 'paper': 'A4'}
        self.call('/api/approve?run_key=run1', state)
        self.api.status.return_value = {'state': 'running', 'tasks': [{'task_id': 'await_review', 'state': 'skipped'}]}
        result = self.call('/api/export?run_key=run1&dag_run_id=ending-flow', {'request_id': 'after-gate'})
        self.assertEqual(result['dag_run_id'], 'ending-flow')
        self.api.trigger.assert_not_called()
        self.api.resume_review.assert_called_once_with('ending-flow')

    def test_first_confirmation_prebinds_continuation_before_trigger(self):
        from resume_flow.approval_wait import await_run_approval, publish_review_request
        from resume_flow.storage import digest
        publish_review_request(self.ws, {'run_key': 'run1', 'skip': True}, 'racing-flow')
        state = self.call('/api/state?run_key=run1')
        state['selection'] = {'schema_version': 1, 'template_id': 'classic', 'mode': 'print', 'paper': 'A4'}
        self.call('/api/approve?run_key=run1', state)
        for gate_state in ('running', 'queued', None):
            with self.subTest(gate_state=gate_state):
                self.api.status.return_value = {'state': 'running', 'tasks': [{'task_id': 'await_review', 'state': gate_state}]}
                def trigger(dag, run, conf):
                    self.assertTrue(await_run_approval(self.ws, 'run1', run))
                    self.assertEqual(conf['run_key'], 'run1')
                    return {'state': 'queued'}
                self.api.trigger.side_effect = trigger
                result = self.call('/api/export?run_key=run1&dag_run_id=racing-flow', {'request_id': 'first-' + str(gate_state)})
                self.assertNotEqual(result['dag_run_id'], 'racing-flow')
                status = self.call('/api/export-status?run_key=run1&dag_run_id=racing-flow')
                self.assertEqual(status['export_key'], result['export_key'])
                self.assertEqual(status['request']['dag_run_id'], result['dag_run_id'])
                self.assertNotIn('approval_hash', read_json(self.ws / 'requests' / (digest('racing-flow') + '.json')))
                # Each subcase starts without a previous active export.
                (self.ws / 'web_requests/run1.json').unlink()

    def test_repeated_click_reuses_pending_confirmation(self):
        from resume_flow.approval_wait import publish_review_request
        publish_review_request(self.ws, {'run_key': 'run1', 'skip': True}, 'done-flow')
        state = self.call('/api/state?run_key=run1')
        state['selection'] = {'schema_version': 1, 'template_id': 'classic', 'mode': 'print', 'paper': 'A4'}
        self.call('/api/approve?run_key=run1', state)
        self.api.status.return_value = {'state': 'success', 'tasks': []}
        first = self.call('/api/export?run_key=run1&dag_run_id=done-flow', {'request_id': 'first-click'})
        self.api.status.return_value = {'state': 'running', 'tasks': []}
        second = self.call('/api/export?run_key=run1&dag_run_id=done-flow', {'request_id': 'second-click'})
        self.assertEqual(second['dag_run_id'], first['dag_run_id'])
        self.assertEqual(second['export_key'], first['export_key'])
        self.assertEqual(self.api.trigger.call_count, 1)
        self.api.status.return_value = {'state': 'running', 'tasks': [{'task_id': 'await_review', 'state': 'skipped'}]}
        retry = self.call('/api/export?run_key=run1&dag_run_id=done-flow', {'request_id': 'after-skip'})
        self.assertNotEqual(retry['dag_run_id'], first['dag_run_id'])
        self.assertEqual(retry['dag_run_id'], 'done-flow')
        self.assertEqual(self.api.trigger.call_count, 1)
        self.api.resume_review.assert_called_once_with('done-flow')

    def test_successful_dag_without_export_report_is_failed(self):
        state = self.call('/api/state?run_key=run1')
        state['selection'] = {'schema_version': 1, 'template_id': 'classic', 'mode': 'print', 'paper': 'A4'}
        self.call('/api/approve?run_key=run1', state)
        self.call('/api/export?run_key=run1', {'request_id': 'skipped-export'})
        self.api.status.return_value = {'state': 'success', 'tasks': [{'task_id': 'verify_and_freeze', 'state': 'skipped'}]}
        result = self.call('/api/export-status?run_key=run1')
        self.assertEqual(result['state'], 'failed')
        self.assertIn('error', result)
        self.assertEqual(result['files'], [])

    def test_revised_completed_flow_starts_another_complete_flow(self):
        from resume_flow.approval_wait import publish_review_request
        publish_review_request(self.ws, {'run_key': 'run1', 'skip': True}, 'finished-flow')
        state = self.call('/api/state?run_key=run1')
        state['selection'] = {'schema_version': 1, 'template_id': 'minimal', 'mode': 'print', 'paper': 'A4'}
        self.call('/api/approve?run_key=run1', state)
        self.api.status.return_value = {'state': 'success', 'tasks': []}
        result = self.call('/api/export?run_key=run1&dag_run_id=finished-flow', {'request_id': 'new-flow'})
        self.assertEqual(result['dag_id'], 'resume_prepare')
        self.assertNotEqual(result['dag_run_id'], 'finished-flow')
        self.assertEqual(self.api.trigger.call_args.args[0], 'resume_prepare')
        self.assertEqual(self.api.trigger.call_args.args[2]['run_key'], 'run1')

    def test_new_review_wait_does_not_show_previous_run_as_finished(self):
        from resume_flow.approval_wait import publish_review_request
        state = self.call('/api/state?run_key=run1')
        state['selection'] = {'schema_version': 1, 'template_id': 'classic', 'mode': 'print', 'paper': 'A4'}
        self.call('/api/approve?run_key=run1', state)
        old = self.call('/api/export?run_key=run1', {'request_id': 'old1'})
        write_json(self.ws / 'outputs/old/input.json', {'run_key': 'run1', 'approval_hash': old['approval_hash']})
        write_json(self.ws / 'outputs/old/report.json', {'state': 'failed', 'ok': False})
        publish_review_request(self.ws, {'run_key': 'run1', 'skip': True}, 'new-review')
        self.api.status.return_value = {'state': 'running', 'tasks': [{'task_id': 'await_review', 'state': 'up_for_reschedule'}]}
        result = self.call('/api/export-status?run_key=run1&dag_run_id=new-review')
        self.assertEqual(result['state'], 'waiting_review')
        self.assertEqual(result['files'], [])
        self.assertNotIn('export_key', result)


if __name__ == '__main__':
    unittest.main()
