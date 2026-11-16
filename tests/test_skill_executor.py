import hashlib
from pathlib import Path
import tempfile
import unittest

from experiments.skill_portal.execute import frozen_runtime_hashes


class FrozenSkillRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.runtime = Path(self.directory.name)
        self.worker = self.runtime / 'runner.py'
        self.worker.write_text('frozen worker', encoding='utf-8')
        self.expected = hashlib.sha256(self.worker.read_bytes()).hexdigest()
        self.manifest = {'experiments/skill_boundary_f/runner.py': self.expected,
                         'inputs/fixtures.json': 'unrelated entry'}

    def test_new_offline_script_does_not_invalidate_frozen_worker(self):
        (self.runtime / 'verify_advanced.py').write_text('offline verifier', encoding='utf-8')
        try:
            result = frozen_runtime_hashes(self.runtime, self.manifest)
        except ValueError as error:
            self.fail(str(error))
        self.assertEqual(result, {'runner.py': self.expected})

    def test_modified_frozen_worker_is_rejected(self):
        self.worker.write_text('changed worker', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'runner.py'):
            frozen_runtime_hashes(self.runtime, self.manifest)

    def test_missing_frozen_worker_is_rejected(self):
        self.worker.unlink()
        with self.assertRaisesRegex(ValueError, 'runner.py'):
            frozen_runtime_hashes(self.runtime, self.manifest)


if __name__ == '__main__':
    unittest.main()
