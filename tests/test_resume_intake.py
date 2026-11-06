import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow/dags'))
from resume_flow.intake import (open_intake, intake_ready, submit_intake, list_intakes,
                               prepare_entry, entry_ready, entry_config, cancel_intake)
from resume_flow.sample import SAMPLE_TEXT


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)

    def test_missing_folder_opens_form_and_waits_until_explicit_material_submission(self):
        record = open_intake(self.ws, 'resume_start', 'manual-one', {'case_id': 'new-case'})
        self.assertFalse((self.ws / 'inputs/new-case').exists())
        self.assertFalse(intake_ready(self.ws, record['id']))
        self.assertIn('intake_id=', record['url'])
        with self.assertRaisesRegex(ValueError, '导入'):
            submit_intake(self.ws, record['id'], {'target': '', 'mode': 'offline'})
        folder = self.ws / 'inputs/new-case'
        folder.mkdir(parents=True)
        (folder / 'profile.md').write_text(SAMPLE_TEXT, encoding='utf-8')
        self.assertFalse(intake_ready(self.ws, record['id']))
        submitted = submit_intake(self.ws, record['id'], {'target': '', 'mode': 'offline'})
        self.assertTrue(intake_ready(self.ws, record['id']))
        self.assertEqual(submitted['conf']['case_id'], 'new-case')
        self.assertEqual(submitted, submit_intake(self.ws, record['id'], {'target': '', 'mode': 'offline'}))
        with self.assertRaises(ValueError):
            submit_intake(self.ws, record['id'], {'target': 'changed', 'mode': 'offline'})

    def test_inline_entry_keeps_submission_in_the_same_dag_run(self):
        entry = prepare_entry(self.ws, 'manual-five', {'case_id': '5', 'mode': 'offline'})
        self.assertFalse(entry_ready(self.ws, entry))
        self.assertEqual(entry['intake_id'], open_intake(self.ws, 'resume_prepare', 'manual-five', {})['id'])
        folder = self.ws / 'inputs/5'
        folder.mkdir(parents=True)
        (folder / 'profile.md').write_text(SAMPLE_TEXT, encoding='utf-8')
        api = Mock()
        submitted = submit_intake(self.ws, entry['intake_id'], {'target': '页面新岗位', 'mode': 'offline'}, api)
        self.assertTrue(entry_ready(self.ws, entry))
        self.assertEqual(submitted['child_run_id'], 'manual-five')
        self.assertEqual(entry_config(self.ws, entry)['target'], '页面新岗位')
        api.trigger.assert_not_called()

    def test_ready_inputs_bypass_wait_and_manual_can_request_edit_page(self):
        folder = self.ws / 'inputs/ready'
        folder.mkdir(parents=True)
        (folder / 'profile.md').write_text(SAMPLE_TEXT, encoding='utf-8')
        ready = prepare_entry(self.ws, 'ready-run', {'case_id': 'ready'})
        self.assertTrue(entry_ready(self.ws, ready))
        self.assertNotIn('intake_id', ready)
        edit = prepare_entry(self.ws, 'edit-run', {'case_id': 'ready', 'upload_materials': True})
        self.assertFalse(entry_ready(self.ws, edit))

    def test_retry_after_upload_still_requires_explicit_submission(self):
        params={'case_id':'new','mode':'offline'}
        entry=prepare_entry(self.ws,'retry-run',params)
        folder=self.ws/'inputs/new'
        folder.mkdir(parents=True)
        (folder/'profile.md').write_text(SAMPLE_TEXT,encoding='utf-8')
        again=prepare_entry(self.ws,'retry-run',params)
        self.assertEqual(again,entry)
        self.assertFalse(entry_ready(self.ws,again))

    def test_empty_manual_case_gets_new_folder_and_scheduled_checks_never_open_form(self):
        entry = prepare_entry(self.ws, 'new-run', {'case_id': ''})
        self.assertTrue(entry['case_id'].startswith('resume-'))
        scheduled = prepare_entry(self.ws, 'scheduled-run', {'case_id': 'missing'}, scheduled=True)
        self.assertTrue(entry_ready(self.ws, scheduled))
        self.assertNotIn('intake_id', scheduled)

    def test_cancel_inline_wait_ends_its_own_dag_run_and_blocks_submission(self):
        entry=prepare_entry(self.ws,'cancel-this-run',{'case_id':'waiting'})
        api=Mock()
        cancelled=cancel_intake(self.ws,entry['intake_id'],api)
        self.assertEqual(cancelled['state'],'cancelled')
        api.cancel_waiting.assert_called_once_with('resume_prepare','cancel-this-run')
        self.assertEqual(cancel_intake(self.ws,entry['intake_id'],api)['state'],'cancelled')
        with self.assertRaises(ValueError):
            entry_ready(self.ws,entry)
        with self.assertRaises(ValueError):
            submit_intake(self.ws,entry['intake_id'],{'mode':'offline'},api)

    def test_existing_fixed_snapshot_can_continue_without_current_input_folder(self):
        from resume_flow.storage import write_json
        write_json(self.ws/'runs/fixed/manifest.json',{'snapshot_hash':'existing'})
        entry=prepare_entry(self.ws,'export-continued',{'case_id':'','run_key':'fixed','upload_materials':True})
        self.assertTrue(entry_ready(self.ws,entry))
        self.assertNotIn('intake_id',entry)

    def test_same_run_is_idempotent_and_different_runs_have_separate_intakes(self):
        first = open_intake(self.ws, 'resume_start', 'manual-one', {})
        self.assertEqual(first, open_intake(self.ws, 'resume_start', 'manual-one', {}))
        other = open_intake(self.ws, 'resume_start', 'manual-two', {})
        self.assertNotEqual(first['case_id'], other['case_id'])
        self.assertEqual(len(list_intakes(self.ws)), 2)

    def test_legacy_missing_material_submission_triggers_exactly_matching_child(self):
        api = Mock()
        api.trigger.return_value = {'state': 'queued'}
        record = open_intake(self.ws, 'resume_prepare', 'missing-run', {'case_id': 'missing'})
        folder = self.ws / 'inputs/missing'
        folder.mkdir(parents=True)
        (folder / 'profile.md').write_text(SAMPLE_TEXT, encoding='utf-8')
        submitted = submit_intake(self.ws, record['id'], {'mode': 'offline'}, api)
        self.assertEqual(api.trigger.call_args.args,
                         ('resume_prepare', 'intake-' + record['id'], submitted['conf']))


if __name__ == '__main__':
    unittest.main()
