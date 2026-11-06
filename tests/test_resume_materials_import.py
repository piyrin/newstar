import base64
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow/dags'))
from resume_flow.materials import import_materials
from resume_flow.storage import snapshot


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)

    def payload(self, request='req1', name='资料.md', content=b'first'):
        return {'case_id': 'my-resume', 'request_id': request,
                'files': [{'name': name, 'content_base64': base64.b64encode(content).decode()}]}

    def test_add_retry_update_backup_and_snapshot(self):
        first = import_materials(self.ws, self.payload())
        self.assertEqual(first['files'][0]['action'], 'added')
        self.assertEqual(import_materials(self.ws, self.payload()), first)
        result = import_materials(self.ws, self.payload('req2', content=b'updated'))
        self.assertEqual(result['files'][0]['action'], 'updated')
        self.assertEqual((self.ws / 'input_history/my-resume/req2/资料.md').read_bytes(), b'first')
        snapshot(self.ws, 'my-resume', 'v1')
        self.assertEqual((self.ws / 'runs/v1/sources/资料.md').read_bytes(), b'updated')

    def test_rejects_escape_invalid_content_and_reused_request(self):
        for name in ('../x.md', 'sub\\x.md', 'a.exe', '.hidden.md', 'CON.txt'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                import_materials(self.ws, self.payload(name=name))
        import_materials(self.ws, self.payload())
        with self.assertRaises(ValueError):
            import_materials(self.ws, self.payload(content=b'different'))
        bad = self.payload('req3')
        bad['files'][0]['content_base64'] = 'not base64!'
        with self.assertRaises(ValueError):
            import_materials(self.ws, bad)

    def test_batch_rollback_if_commit_fails(self):
        import_materials(self.ws, self.payload())
        from resume_flow import materials
        original = materials.atomic_bytes
        def fail_second(path, content):
            if path.name == 'second.md':
                raise OSError('simulated write failure')
            return original(path, content)
        payload = self.payload('req2', content=b'changed')
        payload['files'].append({'name': 'second.md', 'content_base64': base64.b64encode(b'two').decode()})
        with patch.object(materials, 'atomic_bytes', side_effect=fail_second), self.assertRaises(OSError):
            import_materials(self.ws, payload)
        self.assertEqual((self.ws / 'inputs/my-resume/资料.md').read_bytes(), b'first')
        self.assertFalse((self.ws / 'inputs/my-resume/.importing').exists())
        first_revision = (self.ws / 'inputs/my-resume/.material-revision').read_bytes()
        with patch.object(materials, 'atomic_bytes', side_effect=fail_second), self.assertRaises(OSError):
            import_materials(self.ws, payload)
        self.assertNotEqual((self.ws / 'inputs/my-resume/.material-revision').read_bytes(), first_revision)

    def test_failed_recovery_keeps_case_isolated(self):
        import_materials(self.ws, self.payload())
        from resume_flow import materials
        original = materials.atomic_bytes
        def fail_commit_and_restore(path, content):
            if path.name == 'second.md' or (path.parent.name == 'my-resume' and content == b'first'):
                raise OSError('simulated persistent failure')
            return original(path, content)
        payload = self.payload('req2', content=b'changed')
        payload['files'].append({'name': 'second.md', 'content_base64': base64.b64encode(b'two').decode()})
        with patch.object(materials, 'atomic_bytes', side_effect=fail_commit_and_restore), self.assertRaises(ValueError):
            import_materials(self.ws, payload)
        self.assertTrue((self.ws / 'inputs/my-resume/.importing').exists())
        with self.assertRaises(RuntimeError):
            snapshot(self.ws, 'my-resume', 'blocked')

    def test_snapshot_rejects_partial_import(self):
        case = self.ws / 'inputs/my-resume'
        case.mkdir(parents=True)
        (case / '.importing').write_text('busy')
        with self.assertRaises(RuntimeError):
            snapshot(self.ws, 'my-resume', 'blocked')


if __name__ == '__main__':
    unittest.main()
