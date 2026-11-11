import hashlib
from pathlib import Path
import unittest
import uuid
from reference_store import ReferenceStore,model_reference
from runner import BASE

class TypedReferenceContract(unittest.TestCase):
    def test_invalid_manifest_shapes_are_rejected_without_coercion(self):
        store=ReferenceStore()
        for manifest in [None, [], {'deliverables':'[{"reference_ids":["DOC-001"]}]'},
                         {'deliverables':['DOC-001']}, {'deliverables':[None]},
                         {'deliverables':[{'reference_ids':[{}]}]}]:
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                store.select(manifest)

    def test_model_view_does_not_duplicate_body_or_change_saved_record(self):
        ref={'reference_id':'DOC-001','kind':'document','content':'UNIQUE_BODY_TOKEN','artifact':'UNIQUE_BODY_TOKEN','files':[]}
        projected=model_reference(ref)
        import json
        self.assertEqual(json.dumps(projected).count('UNIQUE_BODY_TOKEN'),1)
        self.assertEqual(ref['artifact'],'UNIQUE_BODY_TOKEN')
        self.assertEqual(projected['reference_id'],ref['reference_id'])
    def make(self):
        folder=BASE/'offline-tests'/str(uuid.uuid4());folder.mkdir(parents=True)
        doc=folder/'A003.md';doc.write_text('完整正文',encoding='utf-8')
        csv=folder/'A003-1.csv';csv.write_text('name,session\n',encoding='utf-8')
        return folder,doc,{'path':str(csv),'format':'csv','sha256':hashlib.sha256(csv.read_bytes()).hexdigest()}

    def test_document_and_attachment_get_explicit_distinct_ids(self):
        _,doc,file=self.make();store=ReferenceStore()
        result=store.register('STEP-003','csv-manual-export',doc,'完整正文',[file],2)
        ids=[r['reference_id'] for r in result['outputs']]
        self.assertEqual(len(ids),2);self.assertEqual(len(set(ids)),2)
        attachment=next(r for r in result['outputs'] if r['kind']=='file')
        self.assertEqual(store.resolve([attachment['reference_id']])[0]['content'],'name,session\n')
        self.assertEqual(store.producers([attachment['reference_id']]),['STEP-003'])

    def test_filename_is_not_silently_accepted_as_id(self):
        _,doc,file=self.make();store=ReferenceStore();store.register('STEP-003','csv-manual-export',doc,'完整正文',[file],2)
        with self.assertRaises(ValueError):store.resolve(['A003-1'])

    def test_attachment_hash_is_verified_before_registration(self):
        _,doc,file=self.make();file['sha256']='incorrect';store=ReferenceStore()
        with self.assertRaises(ValueError):store.register('STEP-003','csv-manual-export',doc,'完整正文',[file],2)
        self.assertEqual(store.ids(),[])

    def test_final_file_selection_is_physically_verifiable(self):
        _,doc,file=self.make();store=ReferenceStore();r=store.register('STEP-003','csv-manual-export',doc,'完整正文',[file],2)
        ident=next(x['reference_id'] for x in r['outputs'] if x['kind']=='file')
        selected=store.select({'deliverables':[{'purpose':'CSV模板','reference_ids':[ident]}],'unresolved':[]})
        self.assertEqual(list(selected),[ident])
        self.assertTrue(Path(selected[ident]['files'][0]['path']).is_file())

if __name__=='__main__':unittest.main()
