import unittest
from pathlib import Path
from unittest.mock import patch
from progressive import make_tools, qualified, suite, ordered_registry

class ProgressiveContracts(unittest.TestCase):
    def test_hard_failure_cannot_pass_or_spend_a_semantic_verifier_call(self):
        import progressive
        from unittest.mock import Mock
        api=Mock();api.call.side_effect=AssertionError('hard-rejected artifacts must not call semantic verifier')
        with patch.object(progressive,'physical_checks',return_value={'persisted_outputs':False}),patch.object(progressive,'save'):
            hard,verdict=progressive.evaluate_delivery(api,suite('release')[0],{},Path('unused'),short_circuit_hard_failure=True)
        self.assertFalse(all(hard.values()));self.assertFalse(qualified(verdict));self.assertFalse(api.call.called)
    def test_small_baseline_keeps_all_full_suite_cases_and_gate(self):
        import progressive,json,sys,uuid
        root=progressive.BASE/'offline-tests'/str(uuid.uuid4());root.mkdir(parents=True)
        called=[]
        def run(series,rows,case,repeat,**kwargs):
            called.append((len(rows),case['id'],repeat))
            return {'case':case['id'],'repeat':repeat,'passed':len(rows)==5}
        with patch.object(progressive,'BASE',root),patch.object(progressive,'ordered_registry',return_value=[{}]*15),patch.object(progressive,'run_one',side_effect=run),patch.object(sys,'argv',['progressive','--prefix','small','--allow-small-baseline','--sizes','5','10','15']):
            progressive.main()
        ledger=json.loads((root/'progressive/small/series.json').read_text(encoding='utf-8'))
        self.assertEqual(ledger['last_fully_passed_size'],5)
        self.assertEqual(len([c for c in called if c[0]==5]),12)
        self.assertEqual({c[1] for c in called if c[0]==5},{'dock','ledger','club','event','recruit','competition'})
        self.assertEqual(len([c for c in called if c[0]==10]),12)
        self.assertFalse(any(c[0]==15 for c in called))
    def test_execution_error_is_counted_and_not_retried(self):
        import progressive,uuid,json
        root=progressive.BASE/'offline-tests'/str(uuid.uuid4());root.mkdir(parents=True)
        row=ordered_registry()[0];case=suite('release')[0]
        message={'role':'assistant','content':'','tool_calls':[{'id':'failure-test','type':'function','function':{'name':row['tool_name'],'arguments':json.dumps({'request':'生成','artifact_ids':[]})}}]}
        with patch.object(progressive,'API') as factory,patch.object(progressive,'raw_worker',side_effect=RuntimeError('incomplete local response: length')) as worker:
            factory.return_value.model='offline-test-double';factory.return_value.call.return_value=(message,{})
            result=progressive.run_one(root,[row],case,1,backend='deepseek')
        self.assertFalse(result['passed']);self.assertEqual(result['nodes'],0)
        self.assertEqual(result['failed_skill_calls'],1);self.assertEqual(worker.call_count,1)
        attempts=json.loads((root/'n001/dock-r1/skill-attempts.json').read_text(encoding='utf-8'))
        self.assertEqual(attempts[0]['status'],'execution_error')
    def test_fail_fast_never_promotes_or_runs_remaining_jobs(self):
        import progressive,json,sys,uuid
        root=progressive.BASE/'offline-tests'/str(uuid.uuid4());root.mkdir(parents=True)
        called=[]
        def run(series,rows,case,repeat,**kwargs):
            called.append((len(rows),case['id'],repeat))
            return {'case':case['id'],'repeat':repeat,'passed':False}
        with patch.object(progressive,'BASE',root),patch.object(progressive,'ordered_registry',return_value=[{}]*20),patch.object(progressive,'run_one',side_effect=run),patch.object(sys,'argv',['progressive','--prefix','fast','--sizes','10','15','--critical-first','--fail-fast']):
            progressive.main()
        ledger=json.loads((root/'progressive/fast/series.json').read_text(encoding='utf-8'))
        self.assertEqual(called,[(10,'event',1)])
        self.assertIsNone(ledger['last_fully_passed_size'])
        self.assertFalse(ledger['stages'][0]['fully_passed']);self.assertEqual(ledger['stages'][0]['planned'],12)
    def test_unsupported_skill_is_visible_and_other_skill_can_finish(self):
        import progressive,json,uuid
        from incremental import SkillUnavailable
        root=progressive.BASE/'offline-tests'/str(uuid.uuid4());root.mkdir(parents=True)
        case=suite('release')[0];rows=ordered_registry()[0:3:2]
        manifest={'deliverables':[{'purpose':'文档','reference_ids':['DOC-001']},{'purpose':'CSV','reference_ids':['FILE-002-01']}],'unresolved':[]}
        def call(name,args):return {'role':'assistant','content':'','tool_calls':[{'id':str(uuid.uuid4()),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
        sequence=[call(rows[1]['tool_name'],{'request':'unsupported','artifact_ids':[]}),
                  call(rows[0]['tool_name'],{'request':'文档','artifact_ids':[]}),
                  call(rows[1]['tool_name'],{'request':'CSV','artifact_ids':['DOC-001']}),
                  call('review_deliverables',manifest),call('submit_deliverables',manifest)]
        class API:
            model='offline-test-double'
            def call(self,messages,path,**kwargs):
                if path.name.startswith('planner'):return sequence.pop(0),{}
                return {'checks':{str(i):True for i in range(1,7)},'errors':[]},{}
        def worker(api,row,request,facts,upstream,path,guidance=''):
            if request=='unsupported':raise SkillUnavailable('该请求不在本Skill已具备的能力范围内')
            return {'artifact':'\n'.join(facts['quickstart']) if not upstream else ','.join(facts['feedback_fields'])+'\n'},{}
        with patch.object(progressive,'API',API),patch.object(progressive,'raw_worker',side_effect=worker):
            result=progressive.run_one(root,rows,case,1,'grounded',backend='deepseek')
        self.assertTrue(result['passed']);self.assertEqual(result['nodes'],2)
        self.assertEqual(result['failed_skill_calls'],1);self.assertEqual(result['skill_call_attempts'],3)
        attempts=json.loads((root/'n002/dock-r1/skill-attempts.json').read_text(encoding='utf-8'))
        self.assertEqual([x['status'] for x in attempts],['unsupported','done','done'])
        self.assertEqual(len({x['execution_request_stem'] for x in attempts}),3)

    def test_visible_review_then_native_submission_end_to_end(self):
        import progressive,json,uuid
        root=progressive.BASE/'offline-tests'/str(uuid.uuid4());root.mkdir(parents=True)
        case=suite('release')[0];rows=ordered_registry()[0:3:2]
        manifest={'deliverables':[{'purpose':'文档','reference_ids':['DOC-001']},{'purpose':'CSV','reference_ids':['FILE-002-01']}],'unresolved':[]}
        def msg(name,args):
            return {'role':'assistant','content':None,'tool_calls':[{'id':str(uuid.uuid4()),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
        mixed=msg('review_deliverables',manifest)
        mixed['tool_calls']+=msg('submit_deliverables',manifest)['tool_calls']
        sequence=[{'role':'assistant','content':'已全部完成'},
                  msg(rows[0]['tool_name'],{'request':'非法引用','artifact_ids':['DOC-999']}),
                  msg(rows[0]['tool_name'],{'request':'生成文档','artifact_ids':[]}),
                  msg(rows[1]['tool_name'],{'request':'生成空CSV','artifact_ids':['DOC-001']}),
                  mixed,
                  msg('submit_deliverables',manifest),
                  msg('review_deliverables',manifest),msg('submit_deliverables',manifest)]
        class FakeAPI:
            model='offline-test-double'
            def call(self,messages,path,**kwargs):
                if path.name.startswith('planner'):
                    assert '执行器当前真实状态' in messages[0]['content']
                    return sequence.pop(0),{}
                return {'checks':{str(i):True for i in range(1,7)},'errors':[]},{}
        def worker(api,row,request,facts,upstream,path,guidance=''):
            text='\n'.join(facts['quickstart']) if not upstream else ','.join(facts['feedback_fields'])+'\n'
            return {'artifact':text},{}
        with patch.object(progressive,'API',FakeAPI),patch.object(progressive,'raw_worker',side_effect=worker):
            result=progressive.run_one(root,rows,case,1,'grounded',backend='deepseek')
        self.assertTrue(result['passed']);self.assertEqual(result['nodes'],2)
        self.assertEqual(result['control_tools'],2);self.assertEqual(result['review_calls'],1)
        self.assertEqual(result['rejected_calls'],4)
        self.assertEqual(result['protocol_rejections'],1)

    def test_twelve_of_twelve_required_before_next_size(self):
        import progressive,json,sys,uuid
        root=progressive.BASE/'offline-tests'/str(uuid.uuid4());root.mkdir(parents=True)
        called=[]
        def fake_run(series,rows,case,repeat,variant='baseline',schema_ids='all',**kwargs):
            called.append(len(rows))
            return {'case':case['id'],'repeat':repeat,
                    'passed':not(len(rows)==15 and case['id']=='competition' and repeat==2)}
        with patch.object(progressive,'BASE',root),patch.object(progressive,'API'),patch.object(progressive,'ordered_registry',return_value=[{}]*20),patch.object(progressive,'run_one',side_effect=fake_run),patch.object(sys,'argv',['progressive','--prefix','gate','--sizes','10','15','20']):
            progressive.API.return_value.model='offline-test-double'
            progressive.main()
        ledger=json.loads((root/'progressive/gate/series.json').read_text(encoding='utf-8'))
        self.assertEqual(ledger['last_fully_passed_size'],10)
        self.assertEqual(called.count(10),12);self.assertEqual(called.count(15),12)
        self.assertNotIn(20,called)

    def test_control_is_separate_from_skill_count(self):
        with patch.object(Path,'read_text',return_value='source'):
            ts=make_tools([{'tool_name':'one','description':'test','path':'x'}],['FILE-001-01'])
        self.assertEqual([t['function']['name'] for t in ts],['one','submit_deliverables','review_deliverables'])
        items=ts[0]['function']['parameters']['properties']['artifact_ids']['items']
        self.assertEqual(items['enum'],['FILE-001-01'])

    def test_constant_skill_schema_keeps_full_source_and_exact_control_enums(self):
        rows=[{'tool_name':'one','description':'test','path':'x'}]
        with patch.object(Path,'read_text',return_value='FULL ORIGINAL SOURCE'):
            ts=make_tools(rows,[],'controls-only');later=make_tools(rows,['DOC-001'],'controls-only')
        self.assertEqual(ts[0],later[0])
        self.assertIn('FULL ORIGINAL SOURCE',ts[0]['function']['description'])
        item=later[1]['function']['parameters']['properties']['deliverables']['items']['properties']['reference_ids']['items']
        self.assertEqual(item['enum'],['DOC-001'])

    def test_business_scope_has_six_cases(self):
        cases=suite('broad')
        self.assertEqual({c['id'] for c in cases},{'dock','ledger','club','event','recruit','competition'})
        self.assertTrue(all(len(c['criteria'])==6 for c in cases))

    def test_visible_review_catches_parallel_only_calls(self):
        import progressive
        with patch.object(progressive,'physical_checks',return_value={'persisted_outputs':True}),patch.object(progressive,'save'):
            class API:
                def call(self,*args,**kwargs):return {'checks':{str(i):True for i in range(1,7)},'errors':[]},{}
            hard,_=progressive.evaluate_delivery(API(),suite('release')[0],{},Path('unused'),
                [{'skill':'one','depends_on':[]},{'skill':'two','depends_on':[]}])
        self.assertFalse(hard['actual_skill_composition'])

    def test_errors_or_missing_criterion_do_not_pass(self):
        v={'checks':{str(i):True for i in range(1,7)},'errors':[]}
        self.assertTrue(qualified(v));v['errors']=['缺失实际交付'];self.assertFalse(qualified(v))
        v['errors']=[];del v['checks']['6'];self.assertFalse(qualified(v))

    def test_nested_pool_has_broad_capability_baseline(self):
        rows=ordered_registry();names=[r['tool_name'] for r in rows[:10]]
        self.assertIn('events-activities',names);self.assertIn('candidate-talent-pool',names)
        self.assertEqual(len(rows),len(set(r['tool_name'] for r in rows)))

if __name__=='__main__':unittest.main()
