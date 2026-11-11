"""Observed reproduction regression: output directory is not business input."""
import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import reference_store

from reference_store import ReferenceStore, model_reference
from planner_receipts import receipt_result
from semantic_review import review_input
from incremental import raw_worker
from progressive import csv_asset_issues, suite, run_one


class StableModelViews(unittest.TestCase):
    def make_artifacts(self, folder, csv_text='left,right\n'):
        folder.mkdir()
        body = '# Original document\n\nKeep ./notes and every original line.\n'
        doc = folder / 'STEP-001.md'
        doc.write_text(body, encoding='utf-8')
        csv = folder / 'STEP-001-1.csv'
        csv.write_text(csv_text, encoding='utf-8')
        asset = {'path': str(csv), 'format': 'csv',
                 'sha256': hashlib.sha256(csv.read_bytes()).hexdigest()}
        result = ReferenceStore().register('STEP-001', 'real-source', doc, body, [asset], 1)
        return result, {r['reference_id']: r for r in result['outputs']}

    def test_complete_reads_and_receipts_ignore_run_directory_without_mutating_storage(self):
        with TemporaryDirectory() as directory:
            a, refs_a = self.make_artifacts(Path(directory) / 'original-run')
            b, refs_b = self.make_artifacts(Path(directory) / 'fresh-longer-run')
            original_a, original_b = copy.deepcopy(a), copy.deepcopy(b)
            self.assertEqual([model_reference(r) for r in a['outputs']],
                             [model_reference(r) for r in b['outputs']])
            self.assertEqual(receipt_result(a), receipt_result(b))
            self.assertEqual(model_reference(refs_a['DOC-001'])['content'],
                             refs_a['DOC-001']['content'])
            self.assertEqual(model_reference(refs_a['FILE-001-01'])['content'], 'left,right\n')
            self.assertEqual(a, original_a)
            self.assertEqual(b, original_b)
            for ref in refs_a.values():
                self.assertTrue(Path(ref['path']).is_file())
                for asset in ref['files']:
                    self.assertTrue(Path(asset['path']).is_file())
            self.assertNotIn(str(Path(directory)), json.dumps(receipt_result(a)))

    def test_reviewer_reads_real_files_but_sees_identical_full_text_across_directories(self):
        with TemporaryDirectory() as directory:
            _, a = self.make_artifacts(Path(directory) / 'original')
            _, b = self.make_artifacts(Path(directory) / 'fresh')
            case = {'request': 'Preserve actual text.', 'facts': {}, 'criteria': ['check'] * 6}
            payload_a, lines_a = review_input(case, {'DOC-001': a['DOC-001']})
            payload_b, lines_b = review_input(case, {'DOC-001': b['DOC-001']})
            self.assertEqual(payload_a, payload_b)
            self.assertEqual(lines_a, lines_b)
            self.assertEqual(payload_a['final_deliverables'][0]['lines'][2]['text'],
                             'Keep ./notes and every original line.')
            self.assertEqual(len(payload_a['final_deliverables']), 2)
            Path(a['DOC-001']['files'][0]['path']).write_text('tampered\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                review_input(case, {'DOC-001': a['DOC-001']})

    def test_real_csv_failure_feedback_keeps_file_identity_but_not_output_directory(self):
        with TemporaryDirectory() as directory:
            _, a = self.make_artifacts(Path(directory) / 'old', 'left,right\n1,2,3\n')
            _, b = self.make_artifacts(Path(directory) / 'new', 'left,right\n1,2,3\n')
            fa={'csv_file_issues':csv_asset_issues(a,strict_blank_rows=True),
                'feedback_csv_issues':[{'reference_id':'DOC-001','path':a['FILE-001-01']['path'],'header_line':1}],
                'errors':['Preserve this original error and ./notes.']}
            fb={'csv_file_issues':csv_asset_issues(b,strict_blank_rows=True),
                'feedback_csv_issues':[{'reference_id':'DOC-001','path':b['FILE-001-01']['path'],'header_line':1}],
                'errors':['Preserve this original error and ./notes.']}
            original=copy.deepcopy(fa)
            self.assertTrue(hasattr(reference_store,'model_feedback'), 'review feedback is also model input')
            view=reference_store.model_feedback(fa,list(a.values()))
            self.assertEqual(view,reference_store.model_feedback(fb,list(b.values())))
            self.assertEqual(view['feedback_csv_issues'][0]['path'],'artifact://FILE-001-01')
            self.assertEqual(view['csv_file_issues'][0]['values'],['1','2','3'])
            self.assertEqual(view['errors'],fa['errors'])
            self.assertEqual(fa,original)

    def test_worker_keeps_source_and_facts_and_never_repairs_model_output(self):
        class CaptureAPI:
            def call(self, messages, path, **kwargs):
                self.messages = messages
                return {'content': 'Owner: LibraryPerson (deliberately uncorrected mock output)'}, {}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = '---\nname: original\nauthor: LibraryPerson\nsource_repo: library/demo\n---\nOriginal full instructions.\n'
            skill = root / 'SKILL.md'
            skill.write_text(source, encoding='utf-8')
            api = CaptureAPI()
            facts = {'owner': None, 'installation_command': None}
            result, _ = raw_worker(api, {'path': str(skill)}, 'Create a document.', facts, [], root / 'call')
            system = api.messages[0]['content']
            self.assertIn(source, system)
            self.assertEqual(json.loads(api.messages[1]['content'])['facts'], facts)
            tail = system.split('</SKILL>', 1)[1]
            self.assertTrue(tail.strip(), 'source boundary must follow the complete Skill text')
            self.assertIn('author', tail)
            self.assertIn('facts', tail)
            self.assertEqual(result['artifact'], 'Owner: LibraryPerson (deliberately uncorrected mock output)')

    def test_controller_sends_logical_error_location_and_keeps_physical_evidence(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);case=suite('release')[0];rows=[]
            for name in ['document-source','csv-source']:
                source=root/(name+'.md');source.write_text('Original source '+name,encoding='utf-8')
                sha=hashlib.sha256(source.read_bytes()).hexdigest()
                rows.append({'name':name,'tool_name':name,'path':str(source),'description':name,
                             'sha256':sha,'normalized_sha256':sha})
            def call(name,args):
                return {'role':'assistant','content':'','tool_calls':[{'id':'id-'+name,
                    'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
            def manifest(number):
                return {'deliverables':[{'purpose':'document','reference_ids':['DOC-001']},
                    {'purpose':'CSV','reference_ids':[f'FILE-{number:03}-01']}],'unresolved':[]}
            sequence=[call('document-source',{'request':'document','artifact_ids':[]}),
                call('csv-source',{'request':'bad CSV','artifact_ids':['DOC-001']}),
                call('review_deliverables',manifest(2)),
                call('csv-source',{'request':'repair CSV','artifact_ids':['FILE-002-01']}),
                call('review_deliverables',manifest(3)),call('submit_deliverables',manifest(3))]
            observed=[]
            class API:
                model='offline-feedback-test-double'
                def call(self,messages,path,**kwargs):
                    if path.name.startswith('planner'):
                        observed.append(copy.deepcopy(messages));return sequence.pop(0),{}
                    return {'checks':{str(i):True for i in range(1,7)},'errors':[]},{}
            def worker(api,row,request,facts,upstream,path,guidance=''):
                header=','.join(facts['feedback_fields'])+'\n'
                body='\n'.join(facts['quickstart']) if request=='document' else '```csv\n'+header+('1,2,3\n' if request=='bad CSV' else '')+'```'
                return {'artifact':body},{}
            with patch('progressive.raw_worker',side_effect=worker):
                result=run_one(root/'series',rows,case,1,'grounded',backend='local',replay_api=API(),
                    planner_artifacts='receipts',short_circuit_hard_failure=True)
            self.assertTrue(result['passed'])
            received=json.loads(observed[3][-1]['content'])
            self.assertEqual(received['csv_file_issues'][0]['path'],'artifact://FILE-002-01')
            trial=root/'series/n002/dock-r1'
            saved=json.loads((trial/'control-calls.json').read_text(encoding='utf-8'))[0]
            self.assertEqual(saved['model_feedback'],received)
            actual=Path(saved['feedback']['csv_file_issues'][0]['path'])
            self.assertTrue(actual.is_file())
            self.assertIn('1,2,3',actual.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
