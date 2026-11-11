from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from calibrate_semantic_review import classify_case


class CalibrationAccounting(unittest.TestCase):
    def test_transport_failure_is_unknown_not_a_correct_negative(self):
        with TemporaryDirectory() as directory:
            case = {'request': 'r', 'criteria': ['x'] * 6, 'facts': {'x': None}}
            api = Mock();api.call.side_effect = RuntimeError('deliberate offline transport failure')
            # No release-specific physical checks; the completed document exists.
            p = Path(directory) / 'doc.md';p.write_text('事实未知。', encoding='utf-8')
            selected = {'DOC-1': {'path': str(p), 'content': '事实未知。',
                                  'artifact': '事实未知。', 'files': []}}
            result = classify_case(api, case, selected, Path(directory) / 'out', expected=False)
            self.assertIsNone(result['predicted_passed'])
            self.assertFalse(result['matches_expected'])
            self.assertIn('transport failure', result['error'])
            payload = api.call.call_args.args[0][1]['content']
            self.assertNotIn('expected', payload)


if __name__ == '__main__': unittest.main()
