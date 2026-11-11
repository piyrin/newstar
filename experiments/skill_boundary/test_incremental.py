import unittest
from incremental import stage_passes,select_deliverables,raw_worker,verdict_all_pass

class StrictExpansion(unittest.TestCase):
    def results(self):
        return [{'case':c,'repeat':r,'passed':True} for c in ['dock','ledger','club'] for r in [1,2]]

    def test_all_six_unique_trials_required(self):
        self.assertTrue(stage_passes(self.results(),['dock','ledger','club'],2))

    def test_five_of_six_does_not_promote(self):
        xs=self.results();xs[-1]['passed']=False
        self.assertFalse(stage_passes(xs,['dock','ledger','club'],2))

    def test_duplicate_trial_cannot_fill_missing_variant(self):
        xs=self.results();xs[-1]=dict(xs[0])
        self.assertFalse(stage_passes(xs,['dock','ledger','club'],2))

    def test_only_final_selected_documents_are_graded(self):
        artifacts={'A001':{'artifact':'旧稿错误'},'A002':{'artifact':'已修正的终稿'}}
        manifest={'deliverables':[{'purpose':'终稿','artifact_ids':['A002']}],'unresolved':[]}
        self.assertEqual(list(select_deliverables(manifest,artifacts)),['A002'])

    def test_final_text_cannot_replace_missing_artifact(self):
        with self.assertRaises(ValueError):
            select_deliverables({'deliverables':[{'purpose':'声称完成','artifact_ids':['A999']} ]},{})

    def test_worker_accepts_raw_short_multiline_content(self):
        class API:
            def call(self,messages,path,**kwargs):
                assert not kwargs.get('json_mode',False)
                return {'content':'name,session\n'},{}
        from pathlib import Path
        from unittest.mock import patch
        with patch.object(Path,'read_text',return_value='生成原样CSV，不造字段。'):
            result,_=raw_worker(API(),{'path':'fixture.md'},'生成空模板',{},[],Path('unused'))
        self.assertEqual(result['artifact'],'name,session\n')

    def test_contradictory_verifier_cannot_count_as_success(self):
        checks={k:True for k in ['features','commands','csv','unknowns','feedback','consistency']}
        self.assertFalse(verdict_all_pass({'checks':checks,'errors':['仍缺反馈流程']}))

    def test_driver_never_creates_next_level_after_failed_stage(self):
        import incremental
        import json,sys,uuid
        from unittest.mock import patch
        root=incremental.BASE/'offline-tests'/str(uuid.uuid4());root.mkdir(parents=True)
        called=[]
        def fake_run(series,rows,case,repeat,variant='baseline'):
            called.append(len(rows))
            return {'case':case['id'],'repeat':repeat,'passed':not(len(rows)==10 and case['id']=='club' and repeat==2)}
        with patch.object(incremental,'BASE',root),patch.object(incremental,'ordered_registry',return_value=[{'tool_name':str(i)} for i in range(15)]),patch.object(incremental,'run_one',side_effect=fake_run),patch.object(sys,'argv',['incremental.py','--prefix','offline-driver','--sizes','5','10','15']):
            incremental.main()
        result=json.loads((root/'incremental/offline-driver/series.json').read_text(encoding='utf-8'))
        self.assertEqual(result['last_fully_passed_size'],5)
        self.assertEqual(result['first_failed_size'],10)
        self.assertEqual(called.count(5),6);self.assertEqual(called.count(10),6)
        self.assertNotIn(15,called)

if __name__=='__main__':unittest.main()
