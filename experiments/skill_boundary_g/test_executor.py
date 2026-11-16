"""Offline test doubles validate executor wiring, never model capability metrics."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid
import runner

class FakeAPI:
    model='offline-test-double'
    invalid_reference=False
    consumed_actual_upstream=False

    def call(self,messages,path,tools=None,json_mode=False,max_tokens=None):
        if path.name=='planner-00':
            refs=['missing'] if self.invalid_reference else []
            return {'role':'assistant','content':None,'tool_calls':[{'id':'T1','type':'function',
                'function':{'name':'first','arguments':json.dumps({'request':'做第一项','artifact_ids':refs})}}]},{}
        if path.name=='planner-01':
            return {'role':'assistant','content':None,'tool_calls':[{'id':'T2','type':'function',
                'function':{'name':'second','arguments':json.dumps({'request':'读取前一步并处理','artifact_ids':['A001']})}}]},{}
        if path.name=='planner-02':return {'role':'assistant','content':'{"artifacts":["A001","A002"]}'},{}
        if path.name=='judge':return {'passed':True,'checks':[],'errors':[]},{}
        payload=json.loads(messages[-1]['content'])
        if path.name=='skill-A002':
            upstream=payload['actual_upstream_artifacts']
            assert upstream[0]['artifact_id']=='A001'
            assert 'UNIQUE_UPSTREAM_MARKER' in upstream[0]['artifact']
            type(self).consumed_actual_upstream=True
        return {'status':'done','artifact':'UNIQUE_UPSTREAM_MARKER '+('离线接线测试内容。'*20),
                'assumptions':[],'limitations':[]},{}

class ExecutorWiring(unittest.TestCase):
    def setup_base(self):
        base=runner.BASE/'offline-tests'/str(uuid.uuid4());base.mkdir(parents=True)
        rows=[]
        for name in ['first','second']:
            p=base/(name+'.md');p.write_text('Synthetic executor test fixture.',encoding='utf-8')
            rows.append({'tool_name':name,'name':name,'description':'synthetic test only','path':str(p)})
        runner.save(base/'registry.json',rows)
        return base

    def test_real_artifact_dependency_passes_between_calls(self):
        base=self.setup_base();FakeAPI.invalid_reference=False;FakeAPI.consumed_actual_upstream=False
        with patch.object(runner,'BASE',base),patch.object(runner,'API',FakeAPI):
            summary=runner.run_task(2,'competition',1,'offline')
        self.assertTrue(FakeAPI.consumed_actual_upstream)
        self.assertEqual(summary['dag_nodes'],2)
        self.assertEqual(summary['longest_dependency_chain_nodes'],2)
        self.assertEqual(summary['non_root_nodes'],1)
        self.assertTrue((base/'runs'/summary['run_id']/'artifacts/A002.md').exists())

    def test_unknown_upstream_is_rejected_before_worker(self):
        base=self.setup_base();FakeAPI.invalid_reference=True
        with patch.object(runner,'BASE',base),patch.object(runner,'API',FakeAPI):
            summary=runner.run_task(2,'competition',1,'offline')
        FakeAPI.invalid_reference=False
        self.assertFalse(summary['passed'])
        self.assertEqual(summary['dag_nodes'],0)
        self.assertIn('invalid artifact reference',summary['errors'][0])

if __name__=='__main__':unittest.main()
