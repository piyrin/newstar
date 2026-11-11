import json
import uuid
import unittest
from unittest.mock import patch
from planner_receipts import receipt_result
from progressive import BASE,ordered_registry,suite,run_one,make_tools


class PlannerReceiptContract(unittest.TestCase):
    def test_receipt_has_exact_identity_but_no_duplicated_business_body(self):
        ref={'reference_id':'DOC-001','content':'UNIQUE_LONG_BODY','artifact':'UNIQUE_LONG_BODY','path':'saved.md','files':[]}
        result={'producer_node_id':'STEP-001','outputs':[ref]}
        view=receipt_result(result)
        self.assertNotIn('UNIQUE_LONG_BODY',json.dumps(view))
        self.assertEqual(view['outputs'][0]['reference_id'],'DOC-001')
        self.assertEqual(result['outputs'][0]['content'],'UNIQUE_LONG_BODY')

    def test_explicit_read_and_downstream_receive_whole_saved_body(self):
        rows=ordered_registry()[0:3:2];case=suite('release')[0]
        full='EXACT_COMPLETE_UPSTREAM\n'+'\n'.join(case['facts']['quickstart'])
        manifest={'deliverables':[{'purpose':'文档','reference_ids':['DOC-001']},{'purpose':'CSV','reference_ids':['FILE-002-01']}],'unresolved':[]}
        def call(name,args):return {'role':'assistant','content':'','tool_calls':[{'id':str(uuid.uuid4()),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
        sequence=[call(rows[0]['tool_name'],{'request':'文档','artifact_ids':[]}),call('read_artifacts',{'reference_ids':['DOC-001']}),
            call(rows[1]['tool_name'],{'request':'CSV','artifact_ids':['DOC-001']}),call('review_deliverables',manifest),call('submit_deliverables',manifest)]
        observed=[]
        class API:
            model='offline-test-double'
            def call(self,messages,path,**kwargs):
                if path.name.startswith('planner'):
                    observed.append(json.loads(json.dumps(messages)))
                    return sequence.pop(0),{}
                return {'checks':{str(i):True for i in range(1,7)},'errors':[]},{}
        def worker(api,row,request,facts,upstream,path,guidance=''):
            if upstream:self.assertEqual(upstream[0]['content'],full)
            return {'artifact':','.join(facts['feedback_fields'])+'\n' if upstream else full},{}
        root=BASE/'offline-tests'/str(uuid.uuid4());root.mkdir(parents=True)
        with patch('progressive.raw_worker',side_effect=worker):
            result=run_one(root,rows,case,1,'grounded',backend='local',replay_api=API(),planner_artifacts='receipts')
        self.assertTrue(result['passed']);self.assertEqual(result['nodes'],2)
        self.assertEqual(result['control_tools'],3);self.assertEqual(result['artifact_read_calls'],1)
        self.assertNotIn('EXACT_COMPLETE_UPSTREAM',json.dumps(observed[1]))
        self.assertIn('EXACT_COMPLETE_UPSTREAM',json.dumps(observed[2]))
        self.assertEqual(len(make_tools(rows,[],planner_artifacts='receipts')),len(rows)+3)

if __name__=='__main__':unittest.main()
