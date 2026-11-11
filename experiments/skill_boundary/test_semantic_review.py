import copy
import csv
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from semantic_review import review_input, review_schema, resolve_evidence, review
from progressive import csv_asset_issues, evaluate_delivery, suite


class EvidenceReview(unittest.TestCase):
    def setUp(self):
        self.case = {'request': '生成材料，不发送。', 'facts': {'name': 'Demo', 'port': None},
                     'criteria': [str(i) for i in range(6)]}
        self.selected = {'DOC-1': {'kind': 'document', 'path': 'draft.md',
                                  'content': '# Demo\n端口未知。\n```csv\na,b\n```\n'}}

    def verdict(self):
        return {'checks': {str(i): True for i in range(1, 7)}, 'errors': [],
                'evidence': {str(i): {'line_ids': ['DOC-1:L2'], 'fact_keys': ['facts.port'],
                                     'finding': '未知保持未知。'} for i in range(1, 7)}}

    def test_full_original_lines_and_facts_survive_numbering(self):
        payload, lines = review_input(self.case, self.selected)
        self.assertEqual(payload['user_request'], self.case)
        self.assertEqual(payload['final_deliverables'][0]['lines'],
                         [{'line_id': f'DOC-1:L{i}', 'text': line} for i, line in
                          enumerate(self.selected['DOC-1']['content'].splitlines(), 1)])
        self.assertEqual(lines['DOC-1:L2']['quote'], '端口未知。')
        self.assertEqual(payload['final_deliverables'][0]['content_sha256'],
                         hashlib.sha256(self.selected['DOC-1']['content'].encode()).hexdigest())

    def test_six_evidence_slots_cannot_repeat_only_first_criterion(self):
        _, lines = review_input(self.case, self.selected)
        shape = review_schema(self.case, lines)
        evidence = shape['properties']['evidence']
        self.assertEqual(set(evidence['required']), {str(i) for i in range(1, 7)})
        allowed = evidence['properties']['1']['properties']['line_ids']['items']['enum']
        self.assertIn('DOC-1:L2', allowed)
        self.assertNotIn('DOC-1:L999', allowed)

    def test_attached_csv_is_read_even_without_explicit_file_in_final_manifest(self):
        with TemporaryDirectory() as directory:
            p = Path(directory) / 'feedback.csv'
            p.write_text('a,b\n', encoding='utf-8')
            selected = copy.deepcopy(self.selected)
            selected['DOC-1']['files'] = [{'reference_id': 'FILE-1', 'path': str(p),
                                         'format': 'csv', 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}]
            payload, lines = review_input(self.case, selected)
            self.assertIn('FILE-1:L1', lines)
            self.assertEqual(lines['FILE-1:L1']['quote'], 'a,b')
            self.assertEqual(len(payload['final_deliverables']), 2)

    def test_fabricated_or_missing_evidence_is_rejected(self):
        _, lines = review_input(self.case, self.selected)
        resolved = resolve_evidence(self.verdict(), self.case, lines)
        self.assertEqual(resolved['1']['quotes'][0]['quote'], '端口未知。')
        for change in ['missing', 'line', 'fact']:
            v = copy.deepcopy(self.verdict())
            if change == 'missing': del v['evidence']['6']
            if change == 'line': v['evidence']['1']['line_ids'] = ['DOC-1:L999']
            if change == 'fact': v['evidence']['1']['fact_keys'] = ['facts.not_supplied']
            with self.assertRaises(ValueError): resolve_evidence(v, self.case, lines)

    def test_review_preserves_negative_model_decision_and_actual_artifact(self):
        with TemporaryDirectory() as directory:
            api = Mock();v = self.verdict();v['checks']['4'] = False;v['errors'] = ['不支持的断言']
            api.call.return_value = (v, {})
            before = copy.deepcopy(self.selected)
            actual = review(api, self.case, self.selected, Path(directory))
            self.assertEqual(actual, v)
            self.assertFalse(actual['checks']['4'])
            self.assertEqual(self.selected, before)
            self.assertTrue((Path(directory) / 'semantic-evidence.json').exists())

    def test_strict_blank_record_shape_differs_from_ignored_blank_physical_lines(self):
        with TemporaryDirectory() as directory:
            p = Path(directory) / 'template.csv'
            selected = {'DOC-1': {'files': [{'path': str(p), 'format': 'csv'}]}}
            p.write_text('a,b\n,,\n', encoding='utf-8')
            self.assertFalse(csv_asset_issues(selected))  # Historical behavior unchanged.
            issues = csv_asset_issues(selected, strict_blank_rows=True)
            self.assertEqual((issues[0]['expected_columns'], issues[0]['actual_columns']), (2, 3))
            p.write_text('a,b\n\n,\n', encoding='utf-8')
            self.assertFalse(csv_asset_issues(selected, strict_blank_rows=True))

    def test_evidence_profile_rejects_bad_empty_csv_before_spending_model_call(self):
        with TemporaryDirectory() as directory:
            root = Path(directory);case = suite('release')[0]
            body = '\n'.join(case['facts']['quickstart'])
            doc = root/'doc.md';doc.write_text(body, encoding='utf-8')
            asset = root/'feedback.csv';asset.write_text('issue_id,course,description,status\n,,,,\n', encoding='utf-8')
            selected = {'DOC-1': {'path': str(doc), 'content': body, 'artifact': body,
                'files': [{'path': str(asset), 'format': 'csv', 'reference_id': 'FILE-1',
                           'sha256': hashlib.sha256(asset.read_bytes()).hexdigest()}]}}
            api = Mock()
            hard, verdict = evaluate_delivery(api, case, selected, root/'review',
                short_circuit_hard_failure=True, semantic_review_profile='fact-evidence')
            self.assertFalse(hard['csv_assets_rectangular'])
            api.call.assert_not_called()
            self.assertIn('not_evaluated', verdict)

    def test_evidence_profile_rejects_unknown_ui_claim_before_model_call(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);case=suite('release')[0]
            body='在管理界面导出CSV。\n'+'\n'.join(case['facts']['quickstart'])
            doc=root/'doc.md';doc.write_text(body,encoding='utf-8')
            asset=root/'feedback.csv';asset.write_text('issue_id,course,description,status\n',encoding='utf-8')
            selected={'DOC-1':{'path':str(doc),'content':body,'artifact':body,
                'files':[{'path':str(asset),'format':'csv','reference_id':'FILE-1',
                          'sha256':hashlib.sha256(asset.read_bytes()).hexdigest()}]}}
            api=Mock();api.call.side_effect=AssertionError('unknown UI must fail before model call')
            hard,_=evaluate_delivery(api,case,selected,root/'review',short_circuit_hard_failure=True,
                                     semantic_review_profile='fact-evidence')
            self.assertFalse(hard['no_unprovided_interface_license_security_claims'])
            api.call.assert_not_called()


if __name__ == '__main__': unittest.main()
