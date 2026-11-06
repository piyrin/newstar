import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow/dags'))
from resume_flow.airflow_api import AirflowClient
from resume_flow.drafts import DraftBusyError, delete_draft, draft_guard, ensure_active, is_deleted, list_deleted, restore_draft
from resume_flow.storage import read_json, write_json


class DraftTests(unittest.TestCase):
    def test_worker_waits_for_short_portal_lock_instead_of_failing_export(self):
        with tempfile.TemporaryDirectory() as folder:
            locked = threading.Event()

            def portal_request():
                with draft_guard(Path(folder), 'one'):
                    locked.set()
                    time.sleep(0.2)

            thread = threading.Thread(target=portal_request)
            thread.start()
            self.assertTrue(locked.wait(2))
            with draft_guard(Path(folder), 'one', timeout=2):
                self.assertFalse(thread.is_alive())
            thread.join(2)

    def test_lock_timeout_is_distinct_retryable_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with draft_guard(Path(folder), 'one'):
                with self.assertRaises(DraftBusyError):
                    with draft_guard(Path(folder), 'one', timeout=0.02):
                        self.fail('The second mutation acquired a held lock')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        write_json(self.ws / 'runs/one/manifest.json', {'config': {'case_id': 'shared'}})
        write_json(self.ws / 'reviews/one/resume.json', {'name': 'fiction'})
        write_json(self.ws / 'inputs/shared/source.json', {'preserved': True})
        self.api = Mock()
        self.api.cancel_waiting.return_value = {'result': 'stopped', 'state': 'failed'}

    def record(self, folder, filename, **data):
        write_json(self.ws / folder / (filename + '.json'), data)

    def test_exact_links_and_parent_only(self):
        self.record('requests', 'first', run_key='one', dag_id='resume_prepare', dag_run_id='prepare1')
        self.record('requests', 'other', run_key='two', case_id='shared', dag_id='resume_prepare', dag_run_id='prepare2')
        self.record('workflow_links', 'one', run_key='one', dag_id='resume_prepare', dag_run_id='prepare1')
        self.record('web_requests', 'one', dag_id='resume_export', dag_run_id='export1')
        self.record('intakes', 'parent', dag_id='resume_start', dag_run_id='parent1', child_run_id='prepare1')
        self.record('intakes', 'other', dag_id='resume_start', dag_run_id='parent2', child_run_id='prepare2', case_id='shared')
        result = delete_draft(self.ws, 'one', self.api)
        self.assertTrue(result['deleted'])
        self.assertEqual(set(c.args for c in self.api.cancel_waiting.call_args_list),
                         {('resume_prepare', 'prepare1'), ('resume_export', 'export1'), ('resume_start', 'parent1')})

    def test_archive_restore_keeps_bytes_and_blocks_pending(self):
        before = {p.relative_to(self.ws): p.read_bytes() for p in self.ws.rglob('*.json')}
        delete_draft(self.ws, 'one', self.api)
        self.assertTrue(is_deleted(self.ws, 'one'))
        with self.assertRaises(ValueError):
            ensure_active(self.ws, 'one')
        self.assertEqual(list_deleted(self.ws)[0]['run_key'], 'one')
        self.assertFalse(restore_draft(self.ws, 'one')['deleted'])
        ensure_active(self.ws, 'one')
        self.assertEqual(list_deleted(self.ws), [])
        for path, content in before.items():
            self.assertEqual((self.ws / path).read_bytes(), content)

    def test_waiting_material_form_is_closed_with_its_parent_run(self):
        self.record('workflow_links', 'one', run_key='one', dag_id='resume_prepare', dag_run_id='child')
        self.record('intakes', 'parent', id='parent', dag_id='resume_start', dag_run_id='parent-run',
                    child_run_id='child', state='waiting_materials')
        delete_draft(self.ws, 'one', self.api)
        self.assertEqual(read_json(self.ws / 'intakes/parent.json')['state'], 'cancelled')

    def test_partial_failure_is_pending_and_retry_finishes(self):
        for number in (1, 2):
            self.record('requests', str(number), run_key='one', dag_id='resume_prepare', dag_run_id=str(number))
        self.api.cancel_waiting.side_effect = [{'result': 'stopped', 'state': 'failed'}, ValueError('busy')]
        with self.assertRaisesRegex(ValueError, 'busy'):
            delete_draft(self.ws, 'one', self.api)
        self.assertTrue(is_deleted(self.ws, 'one'))
        self.assertEqual(list_deleted(self.ws)[0]['state'], 'pending')
        self.api.cancel_waiting.side_effect = None
        self.assertTrue(delete_draft(self.ws, 'one', self.api)['deleted'])
        self.assertEqual(list_deleted(self.ws)[0]['state'], 'cancelled')

    def test_invalid_ids_and_missing_draft(self):
        for key in ('../one', '', None):
            with self.assertRaises(ValueError):
                delete_draft(self.ws, key, self.api)
        with self.assertRaises(ValueError):
            delete_draft(self.ws, 'missing', self.api)
        self.api.cancel_waiting.assert_not_called()

    def test_invalid_associated_id_leaves_recoverable_pending_marker(self):
        self.record('workflow_links', 'one', run_key='one', dag_id='unrelated_dag', dag_run_id='bad')
        with self.assertRaisesRegex(ValueError, '关联工作流标识无效'):
            delete_draft(self.ws, 'one', self.api)
        self.assertTrue(is_deleted(self.ws, 'one'))
        self.api.cancel_waiting.assert_not_called()
        restore_draft(self.ws, 'one')
        self.assertFalse(is_deleted(self.ws, 'one'))

    def test_restore_retains_stopped_runs_without_retriggering(self):
        self.record('workflow_links', 'one', run_key='one', dag_id='resume_prepare', dag_run_id='prepare1')
        deleted = delete_draft(self.ws, 'one', self.api)
        restored = restore_draft(self.ws, 'one')
        self.assertEqual(deleted['stopped'], restored['stopped'])
        self.api.trigger.assert_not_called()

    def test_guard_serializes_mutation(self):
        with draft_guard(self.ws, 'one'):
            with self.assertRaisesRegex(ValueError, '另一项操作'):
                delete_draft(self.ws, 'one', self.api)
        self.assertFalse(is_deleted(self.ws, 'one'))


class CancellationTests(unittest.TestCase):
    def test_old_review_resume_targets_only_this_run_and_its_five_remaining_tasks(self):
        api = AirflowClient(token='synthetic')
        api._send = Mock(return_value={'task_instances': []})
        api.resume_review('manual__one')
        method, path, body = api._send.call_args.args
        self.assertEqual(method, 'POST')
        self.assertEqual(path, '/api/v2/dags/resume_prepare/clearTaskInstances')
        self.assertEqual(body['dag_run_id'], 'manual__one')
        self.assertEqual(body['task_ids'], ['await_review', 'verify_and_freeze', 'render_word', 'export_pdf', 'check_pages'])
        self.assertTrue(body['run_on_latest_version'])
        self.assertTrue(body['prevent_running_task'])
        self.assertFalse(body['dry_run'])

    def client(self, run_state, tasks):
        api = AirflowClient(token='synthetic')
        api._send = Mock(side_effect=[{'state': run_state}, {'task_instances': tasks},
                                    {'state': run_state}, {'state': 'failed'}])
        return api

    def test_waiting_patch_contract(self):
        api = self.client('running', [{'task_id': 'await_review', 'state': 'running'}])
        self.assertEqual(api.cancel_waiting('resume_prepare', 'manual__one')['result'], 'stopped')
        self.assertEqual(api._send.call_args.args,
                         ('PATCH', '/api/v2/dags/resume_prepare/dagRuns/manual__one?update_mask=state', {'state': 'failed'}))

    def test_active_extraction_or_export_refused(self):
        for task in ('extract_materials', 'organize_facts', 'write_draft', 'render_word', 'export_pdf'):
            api = self.client('running', [{'task_id': task, 'state': 'running'}])
            with self.assertRaisesRegex(ValueError, task):
                api.cancel_waiting('resume_prepare', 'manual__one')
            self.assertFalse(any(call.args[0] == 'PATCH' for call in api._send.call_args_list))

    def test_finished_run_kept(self):
        for state in ('failed', 'success'):
            api = self.client(state, [])
            self.assertEqual(api.cancel_waiting('resume_prepare', 'manual__one')['result'], 'already_finished')
            self.assertEqual(api._send.call_count, 1)

    def test_paginated_tasks_checked(self):
        api = AirflowClient(token='synthetic')
        api._send = Mock(side_effect=[{'state': 'running'},
                                    {'task_instances': [{'task_id': 'await_review', 'state': 'up_for_reschedule'}], 'total_entries': 2},
                                    {'task_instances': [{'task_id': 'render_word', 'state': 'running'}], 'total_entries': 2}])
        with self.assertRaisesRegex(ValueError, 'render_word'):
            api.cancel_waiting('resume_prepare', 'manual__one')

    def test_run_completed_during_inspection_is_preserved(self):
        api = AirflowClient(token='synthetic')
        api._send = Mock(side_effect=[{'state': 'running'}, {'task_instances': []}, {'state': 'success'}])
        self.assertEqual(api.cancel_waiting('resume_prepare', 'manual__one')['result'], 'already_finished')
        self.assertFalse(any(call.args[0] == 'PATCH' for call in api._send.call_args_list))

    def test_bad_dag_and_run_id_rejected(self):
        api = AirflowClient(token='synthetic')
        api._send = Mock()
        for dag, run in [('other', 'manual__one'), ('resume_prepare', ''), ('resume_prepare', 'bad\nrun')]:
            with self.assertRaises(ValueError):
                api.cancel_waiting(dag, run)
        api._send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
