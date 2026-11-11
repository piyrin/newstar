import copy
import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
from runner import save
from boundary_scan import validate_extension, summarize_stage, validate_calibration
from progressive import candidate_rows


class BoundaryProtocol(unittest.TestCase):
    def test_frozen_catalog_retains_existing_relative_positions_when_extended(self):
        old=[{'tool_name':str(i)} for i in range(8)]
        expanded=old+[{'tool_name':'new'}]
        for repeat in [1,2,3]:
            self.assertEqual(candidate_rows(old,repeat,'frozen'),old)
            self.assertEqual(candidate_rows(expanded,repeat,'frozen')[:len(old)],old)
        self.assertEqual(expanded[-1]['tool_name'],'new')
    def setUp(self):
        self.payload='tested payload';sha=hashlib.sha256(self.payload.encode()).hexdigest()
        self.old=[{'tool_name':'a','sha256':'1','normalized_sha256':'n1'}]
        self.new={'tool_name':'b','sha256':'2','normalized_sha256':'n2','local_qualification_evidence':'evidence',
            'agent_review_evidence':'review','artifact_sha256':sha}
        self.proof={'passed':True,'backend':'local','source_sha256':'2','tool_name':'b','artifact_sha256':sha}
        self.review={'decision':'include','source_sha256':'2','artifact_sha256':sha,
            'reason':'原能力、输入与产物已逐文检查','manual_verdict':{'passed':True,'checks':{'1':True,'2':True,'3':True},
                'errors':[],'evidence':[{'check':str(i),'quote':'tested payload'} for i in range(1,4)]}}

    def loader(self,path,proof=None,review=None):
        if str(path)=='evidence':return proof or self.proof
        if str(path)=='artifact.json':return {'status':'done','artifact':self.payload}
        return {'reviews':{'b':review or self.review}}

    def test_extension_preserves_old_order_and_requires_matching_positive_local_proof(self):
        loader=self.loader
        self.assertTrue(validate_extension(self.old,self.old+[self.new],loader))
        with self.assertRaises(ValueError):validate_extension(self.old,[self.new]+self.old,loader)
        for k,value in [('passed',False),('backend','deepseek'),('source_sha256','wrong'),('tool_name','wrong')]:
            proof={**self.proof,k:value}
            with self.assertRaises(ValueError):validate_extension(self.old,self.old+[self.new],lambda p:self.loader(p,proof=proof))
        with self.assertRaises(ValueError):validate_extension(self.old,self.old+[self.new],lambda p:self.loader(p,review={**self.review,'decision':'exclude'}))

    def test_direct_adjudication_can_correct_a_judge_with_real_checked_evidence(self):
        proof={**self.proof,'passed':False};review={**self.review,'overrides_automatic_verdict':True}
        self.assertTrue(validate_extension(self.old,self.old+[self.new],lambda p:self.loader(p,proof,review)))
        bad=copy.deepcopy(review);bad['manual_verdict']['evidence'][0]['quote']='invented evidence'
        with self.assertRaises(ValueError):validate_extension(self.old,self.old+[self.new],lambda p:self.loader(p,proof,bad))

    def test_all_failures_remain_in_denominator_and_partial_stage_cannot_pass(self):
        results=[{'case':'dock','repeat':1,'passed':True},{'case':'dock','repeat':2,'passed':False,'error':'context'}]
        s=summarize_stage(180,results,3,'dock')
        self.assertEqual((s['passed'],s['completed'],s['planned']),(1,2,3))
        self.assertFalse(s['fully_passed']);self.assertEqual(s['results'],results)
        results.append({'case':'dock','repeat':3,'passed':True})
        self.assertFalse(summarize_stage(180,results,3,'dock')['fully_passed'])

    def test_evidence_profile_requires_all_known_cases_and_matching_implementation(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ['semantic_review.py','progressive.py','local_api.py','calibrate_semantic_review.py','extended_release_facts.py','release_fact_issues.py']:
                shutil.copyfile(Path(__file__).parent/name,root/name)
            save(root/'protocol.json',{'backend':'local','thinking':'off','sampling':'qwen-recommended'})
            results=[{'predicted_passed':i==0,'expected_passed':i==0,'matches_expected':True} for i in range(5)]
            ledger={'status':'all_cases_finished','planned':5,'completed':5,'matched':5,'results':results}
            save(root/'ledger.json',ledger)
            self.assertTrue(validate_calibration(root))
            save(root/'protocol.json',{'backend':'local','thinking':'all','sampling':'qwen-recommended'})
            with self.assertRaises(ValueError):validate_calibration(root)
            save(root/'protocol.json',{'backend':'local','thinking':'off','sampling':'qwen-recommended'})
            bad=copy.deepcopy(ledger);bad['results'][1]['predicted_passed']=None
            save(root/'ledger.json',bad)
            with self.assertRaises(ValueError):validate_calibration(root)
            save(root/'ledger.json',ledger)
            guard=root/'extended_release_facts.py';original_guard=guard.read_bytes()
            guard.write_text('changed guard',encoding='utf-8')
            with self.assertRaises(ValueError):validate_calibration(root)
            guard.write_bytes(original_guard)
            (root/'semantic_review.py').write_text('changed implementation',encoding='utf-8')
            with self.assertRaises(ValueError):validate_calibration(root)


if __name__=='__main__':unittest.main()
