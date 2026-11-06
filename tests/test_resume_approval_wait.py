import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow/dags'))
from resume_flow.approval_wait import (await_run_approval, bind_run_approval, freeze_run_export,
                                       publish_review_request, request_path)
from resume_flow.storage import read_json, write_json
from resume_flow.export import output_dir
from resume_flow.review import approve
import test_resume_review as review_tests


class RunApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        self.version = {'run_key': 'run1', 'skip': True, 'reason': 'unchanged'}
        publish_review_request(self.ws, self.version, 'manual__one')

    def signal(self, **changes):
        path = request_path(self.ws, 'manual__one')
        data = read_json(path)
        data.update(approval_hash='approved-content', export_key='export1')
        data.update(changes)
        write_json(path, data)

    @patch('resume_flow.approval_wait.verify_approval')
    def test_old_approval_does_not_approve_new_run(self, verify):
        verify.return_value = {'content_hash': 'approved-content'}
        self.assertFalse(await_run_approval(self.ws, 'run1', 'manual__one'))
        verify.assert_not_called()
        self.signal()
        self.assertTrue(await_run_approval(self.ws, 'run1', 'manual__one'))
        publish_review_request(self.ws, self.version, 'manual__two')
        self.assertFalse(await_run_approval(self.ws, 'run1', 'manual__two'))

    @patch('resume_flow.approval_wait.verify_approval')
    def test_run_identity_and_current_content_must_match(self, verify):
        verify.return_value = {'content_hash': 'approved-content'}
        for changes in [{'dag_run_id': 'another'}, {'run_key': 'another'},
                        {'dag_id': 'resume_export'}, {'approval_hash': 'old-content'},
                        {'export_key': ''}]:
            publish_review_request(self.ws, self.version, 'manual__one')
            self.signal(**changes)
            self.assertFalse(await_run_approval(self.ws, 'run1', 'manual__one'))
        self.signal(dag_run_id='manual__one', run_key='run1', dag_id='resume_prepare')
        verify.side_effect = ValueError('content changed')
        self.assertFalse(await_run_approval(self.ws, 'run1', 'manual__one'))

    def test_republish_preserves_same_run_signal_and_review_link(self):
        self.signal()
        key = publish_review_request(self.ws, self.version, 'manual__one', {'mode': 'offline'})
        self.assertEqual(key, 'run1')
        request = read_json(request_path(self.ws, 'manual__one'))
        self.assertEqual(request['approval_hash'], 'approved-content')
        self.assertEqual(request['export_key'], 'export1')
        self.assertEqual(request['mode'], 'offline')
        self.assertIn('dag_run_id=manual__one', request['review_url'])
        self.assertEqual(read_json(self.ws / 'workflow_links/run1.json'),
                         {'dag_id': 'resume_prepare', 'dag_run_id': 'manual__one', 'run_key': 'run1'})
        publish_review_request(self.ws, dict(self.version, run_key='run2'), 'manual__one')
        changed = read_json(request_path(self.ws, 'manual__one'))
        self.assertNotIn('approval_hash', changed)
        self.assertNotIn('export_key', changed)

    def test_retry_does_not_overwrite_a_concurrent_portal_confirmation(self):
        path = request_path(self.ws, 'manual__one')

        def read_before_confirmation(target):
            previous = read_json(target)
            self.signal()
            return previous

        with patch('resume_flow.approval_wait.read_json', side_effect=read_before_confirmation):
            publish_review_request(self.ws, self.version, 'manual__one')
        self.assertEqual(read_json(path)['approval_hash'], 'approved-content')
        self.assertEqual(read_json(path)['export_key'], 'export1')

    @patch('resume_flow.approval_wait.verify_approval', return_value={'content_hash': 'approved-content'})
    def test_immutable_signal_survives_stale_metadata_write(self, verify):
        path = request_path(self.ws, 'manual__one')
        stale = read_json(path)
        bound = dict(stale, approval_hash='approved-content', export_key='export1')
        bind_run_approval(self.ws, bound)
        write_json(path, stale)
        self.assertTrue(await_run_approval(self.ws, 'run1', 'manual__one'))
        bind_run_approval(self.ws, bound)
        with self.assertRaises(ValueError):
            bind_run_approval(self.ws, dict(bound, approval_hash='changed'))
        self.assertTrue(await_run_approval(self.ws, 'run1', 'manual__one'))

    @patch('resume_flow.export.freeze_export')
    @patch('resume_flow.approval_wait.verify_approval')
    def test_freeze_revalidates_signal_and_uses_bound_export_key(self, verify, freeze):
        verify.return_value = {'content_hash': 'approved-content'}
        self.signal()
        freeze.return_value = 'export1'
        write_json(self.ws / 'outputs/export1/input.json', {'approval_hash': 'approved-content'})
        self.assertEqual(freeze_run_export(self.ws, 'run1', 'manual__one'), 'export1')
        freeze.assert_called_once_with(self.ws, 'run1', 'export1')
        verify.return_value = {'content_hash': 'changed'}
        with self.assertRaises(ValueError):
            freeze_run_export(self.ws, 'run1', 'manual__one')
        self.assertEqual(freeze.call_count, 1)

    @patch('resume_flow.export.freeze_export', return_value='export1')
    @patch('resume_flow.approval_wait.verify_approval', return_value={'content_hash': 'approved-content'})
    def test_freeze_detects_approval_changed_during_copy(self, verify, freeze):
        self.signal()
        write_json(self.ws / 'outputs/export1/input.json', {'approval_hash': 'changed'})
        with self.assertRaises(ValueError):
            freeze_run_export(self.ws, 'run1', 'manual__one')


class RealApprovalTests(unittest.TestCase):
    setUp = review_tests.ReviewTests.setUp
    choose = review_tests.ReviewTests.choose

    def test_existing_approval_requires_a_new_run_signal_and_freezes_bound_version(self):
        self.choose()
        approval = approve(self.ws, 'run1')
        version = {'run_key': 'run1', 'skip': True, 'reason': 'reuse'}
        publish_review_request(self.ws, version, 'manual__real')
        self.assertFalse(await_run_approval(self.ws, 'run1', 'manual__real'))
        path = request_path(self.ws, 'manual__real')
        request = read_json(path)
        request.update(approval_hash=approval['content_hash'], export_key='bound-export')
        write_json(path, request)
        self.assertTrue(await_run_approval(self.ws, 'run1', 'manual__real'))
        self.assertEqual(freeze_run_export(self.ws, 'run1', 'manual__real'), 'bound-export')
        self.assertEqual(read_json(output_dir(self.ws, 'bound-export') / 'input.json')['approval_hash'],
                         approval['content_hash'])
        self.choose('technical')
        approve(self.ws, 'run1')
        self.assertFalse(await_run_approval(self.ws, 'run1', 'manual__real'))
        with self.assertRaises(ValueError):
            freeze_run_export(self.ws, 'run1', 'manual__real')


if __name__ == '__main__':
    unittest.main()
