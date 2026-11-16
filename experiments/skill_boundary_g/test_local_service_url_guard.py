import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from extended_release_facts import extended_release_fact_issues
from progressive import evaluate_delivery, review_diagnostics, suite


class LocalServiceAccessClaims(unittest.TestCase):
    observed_claim = (
        '由于 `service_url` 和 `web_management_ui` 均为未知，请直接访问本地服务地址'
        '（通常为 `http://localhost:4177`，具体取决于运行环境配置）。'
    )

    def setUp(self):
        self.facts = {'feedback_fields': ['issue_id', 'course', 'description', 'status'],
                      'service_url': None, 'web_management_ui': None}

    def issues(self, text, facts=None):
        return extended_release_fact_issues(
            self.facts if facts is None else facts, {'DOC-1': {'content': text}})

    def test_unknown_fields_do_not_justify_a_direct_concrete_access_instruction(self):
        issues = self.issues(self.observed_claim)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['kind'], 'unprovided_browser_url')
        self.assertEqual(issues[0]['quote'], self.observed_claim)

    def test_local_access_instructions_do_not_require_the_word_browser(self):
        for text in ['请访问 http://localhost:4177 查看服务。',
                     '打开 http://127.0.0.1:8080/notes。',
                     'Open http://localhost:4177 to use the service.',
                     'Visit http://127.0.0.1:8080/notes.']:
            with self.subTest(text=text):
                self.assertTrue(self.issues(text))

    def test_explicitly_supplied_service_url_is_accepted(self):
        facts = {**self.facts, 'service_url': 'http://localhost:4177'}
        self.assertEqual(self.issues('请访问 http://localhost:4177。', facts), [])

    def test_conditional_proposals_and_unknown_only_statements_are_accepted(self):
        for text in ['如果未来确认该URL可用才访问 http://localhost:4177 作为示例。',
                     '假设后续提供本地HTTP界面，建议访问 http://127.0.0.1:8080。',
                     'Proposed example: open http://localhost:4177 if configured.',
                     'service_url未知，访问地址需先确认。',
                     '给定命令仅指定端口4177，service_url和浏览器界面未知。']:
            with self.subTest(text=text):
                self.assertEqual(self.issues(text), [])

    def test_negated_access_instructions_do_not_assert_a_service_url(self):
        for text in ['Do not visit http://localhost:4177.',
                     '请勿访问推断的 http://localhost:4177。',
                     '不要打开 http://127.0.0.1:8080。']:
            with self.subTest(text=text):
                self.assertEqual(self.issues(text), [])

    def test_conditional_url_examples_keep_their_antecedent_across_a_comma(self):
        for text in ['如果后续确认该URL可用，可访问 http://localhost:4177 作为示例。',
                     'If configured as a local HTTP interface, open http://localhost:4177.',
                     '假设后续提供该界面，打开 http://127.0.0.1:8080 作为访问示例。']:
            with self.subTest(text=text):
                self.assertEqual(self.issues(text), [])

    def test_real_delivery_gate_persists_feedback_for_the_observed_access_claim(self):
        case = suite('release')[0]
        body = '\n'.join(case['facts']['quickstart']) + '\n' + self.observed_claim
        with TemporaryDirectory() as directory:
            root = Path(directory)
            doc = root / 'draft.md'
            doc.write_text(body, encoding='utf-8')
            csv = root / 'feedback.csv'
            csv.write_text('issue_id,course,description,status\n', encoding='utf-8')
            selected = {'DOC-1': {'path': str(doc), 'content': body, 'artifact': body,
                                  'files': [{'path': str(csv), 'format': 'csv',
                                             'sha256': hashlib.sha256(csv.read_bytes()).hexdigest()}]}}
            semantic_pass = {'checks': {str(i): True for i in range(1, 7)}, 'errors': []}
            with patch('semantic_review.review', return_value=semantic_pass):
                hard, verdict = evaluate_delivery(
                    None, case, selected, root / 'review',
                    semantic_review_profile='fact-evidence',
                    short_circuit_hard_failure=True)
            self.assertFalse(hard['no_unprovided_interface_license_security_claims'])
            issues = json.loads((root / 'review/extended-fact-issues.json').read_text(encoding='utf-8'))
            self.assertEqual(issues[0]['quote'], self.observed_claim)
            self.assertTrue(any('URL' in message for message in review_diagnostics(hard)))
            self.assertIn('not_evaluated', verdict)


if __name__ == '__main__':
    unittest.main()
