import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow/dags'))
from resume_flow.incremental import prepare_version, finish_version
from resume_flow.storage import write_json, read_json, run_dir


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        self.source = self.ws / 'inputs/demo/profile.md'
        self.source.parent.mkdir(parents=True)
        self.source.write_text('姓名：虚构同学', encoding='utf-8')

    def complete(self, key):
        folder = self.ws / 'reviews' / key
        write_json(folder / 'resume.json', {'draft': 'reviewed'})
        write_json(folder / 'questions.json', [])
        write_json(run_dir(self.ws, key) / 'status.json', {'state': 'waiting_review'})
        finish_version(self.ws, key)

    def test_unchanged_and_touch_skip_without_erasing_review(self):
        first = prepare_version(self.ws, 'demo', mode='offline')
        self.assertFalse(first['skip'])
        self.complete(first['run_key'])
        os.utime(self.source, (1000, 1000))
        second = prepare_version(self.ws, 'demo', mode='offline')
        self.assertTrue(second['skip'])
        self.assertEqual(second['run_key'], first['run_key'])
        self.assertEqual(read_json(self.ws / 'reviews' / first['run_key'] / 'resume.json'), {'draft': 'reviewed'})

    def test_failure_reuses_version_until_success(self):
        a = prepare_version(self.ws, 'demo')
        b = prepare_version(self.ws, 'demo')
        self.assertEqual(a, b)
        self.assertFalse(b['skip'])
        with self.assertRaises(ValueError):
            finish_version(self.ws, a['run_key'])

    def test_content_deleted_file_target_and_mode_change_versions(self):
        a = prepare_version(self.ws, 'demo')
        self.complete(a['run_key'])
        self.source.write_text('姓名：另一个虚构同学', encoding='utf-8')
        b = prepare_version(self.ws, 'demo')
        self.assertNotEqual(a['run_key'], b['run_key'])
        extra = self.source.with_name('extra.md')
        extra.write_text('技能 Python', encoding='utf-8')
        c = prepare_version(self.ws, 'demo')
        extra.unlink()
        self.assertEqual(prepare_version(self.ws, 'demo')['run_key'], b['run_key'])
        self.assertNotEqual(c['run_key'], b['run_key'])
        self.assertNotEqual(prepare_version(self.ws, 'demo', target='后端')['run_key'], b['run_key'])
        self.assertNotEqual(prepare_version(self.ws, 'demo', mode='offline')['run_key'], b['run_key'])

    def test_explicit_version_cannot_change_config(self):
        prepare_version(self.ws, 'demo', run_key='named')
        with self.assertRaises(ValueError):
            prepare_version(self.ws, 'demo', run_key='named', target='new')

    def test_missing_review_is_not_silently_skipped(self):
        a = prepare_version(self.ws, 'demo')
        self.complete(a['run_key'])
        (self.ws / 'reviews' / a['run_key'] / 'resume.json').unlink()
        self.assertFalse(prepare_version(self.ws, 'demo')['skip'])

    def test_successful_legacy_run_is_reused(self):
        from resume_flow.storage import snapshot
        snapshot(self.ws, 'demo', 'old-run')
        manifest = read_json(run_dir(self.ws, 'old-run') / 'manifest.json')
        write_json(run_dir(self.ws, 'old-run') / 'facts.json',
                   {'mode': 'deepseek', 'snapshot_hash': manifest['snapshot_hash']})
        review = self.ws / 'reviews/old-run'
        write_json(review / 'resume.json', {})
        write_json(review / 'questions.json', [])
        write_json(run_dir(self.ws, 'old-run') / 'status.json', {'state': 'waiting_review'})
        result = prepare_version(self.ws, 'demo')
        self.assertTrue(result['skip'])
        self.assertEqual(result['run_key'], 'old-run')
        again = prepare_version(self.ws, 'demo')
        self.assertTrue(again['skip'])
        self.assertEqual(again['run_key'], 'old-run')

    def test_completed_named_run_is_reused_by_automatic_checks(self):
        prepare_version(self.ws, 'demo', run_key='named')
        self.complete('named')
        result = prepare_version(self.ws, 'demo')
        self.assertTrue(result['skip'])
        self.assertEqual(result['run_key'], 'named')

    def test_jd_and_file_rename_change_version(self):
        a = prepare_version(self.ws, 'demo')['run_key']
        self.assertNotEqual(prepare_version(self.ws, 'demo', jd='需要 Python')['run_key'], a)
        self.source.rename(self.source.with_name('renamed.md'))
        self.assertNotEqual(prepare_version(self.ws, 'demo')['run_key'], a)

    def test_unreadable_unrelated_history_does_not_block_new_materials(self):
        old = self.ws / 'runs/unrelated/facts.json'
        write_json(old, {})
        original = read_json
        def read(path):
            if Path(path) == old:
                raise PermissionError('unreadable old run')
            return original(path)
        with patch('resume_flow.incremental.read_json', side_effect=read):
            self.assertFalse(prepare_version(self.ws, 'demo')['skip'])


if __name__ == '__main__':
    unittest.main()
