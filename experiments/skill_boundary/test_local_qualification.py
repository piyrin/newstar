import copy
import unittest
import hashlib
from pathlib import Path
import uuid
from unittest.mock import Mock
from local_qualification import validate_case, validate_verdict, extend_registry, case_schema, judge_schema
from local_qualification import qualify
from runner import BASE


class QualificationEvidence(unittest.TestCase):
    def setUp(self):
        self.case={'eligible':True,'request':'改写给定段落','facts':{'text':'输入段落'},
            'checks':['保留事实','更清晰','不添加信息'],'scope':'本地文本改写',
            'source_quote':'rewrite prose','boundary':'不新增事实'}
        self.actual='改写结果，保留事实。'
        self.verdict={'passed':True,'checks':{'1':True,'2':True,'3':True},'errors':[],
            'evidence':[{'check':'1','quote':'改写结果'},{'check':'2','quote':'保留事实'},{'check':'3','quote':'事实'}]}

    def test_case_requires_local_scope_and_real_source_quote(self):
        self.assertTrue(validate_case(self.case,'We rewrite prose here.'))
        for key,value in [('eligible',False),('source_quote','nonexistent'),('checks',['a']),('facts',{}),('boundary','')]:
            c=copy.deepcopy(self.case);c[key]=value
            self.assertFalse(validate_case(c,'We rewrite prose here.'))

    def test_judge_cannot_pass_with_false_missing_or_invented_evidence(self):
        self.assertTrue(validate_verdict(self.verdict,self.actual))
        for change in ['false','missing','invented','errors','bool']:
            v=copy.deepcopy(self.verdict)
            if change=='false':v['checks']['3']=False
            if change=='missing':v['evidence']=v['evidence'][:2]
            if change=='invented':v['evidence'][0]['quote']='不存在的内容'
            if change=='errors':v['errors']=['业务不满足']
            if change=='bool':v['passed']='true'
            self.assertFalse(validate_verdict(v,self.actual))

    def test_extension_preserves_prefix_and_rejects_duplicate_names_and_hashes(self):
        original=[{'tool_name':'a','sha256':'1','normalized_sha256':'n1'}]
        new=[{'tool_name':'b','sha256':'2','normalized_sha256':'n2'}]
        self.assertEqual(extend_registry(original,new),original+new)
        for row in [{'tool_name':'a','sha256':'2','normalized_sha256':'n2'},
                    {'tool_name':'b','sha256':'1','normalized_sha256':'n2'},
                    {'tool_name':'b','sha256':'2','normalized_sha256':'n1'}]:
            with self.assertRaises(ValueError):extend_registry(original,[row])

    def test_case_source_quote_schema_only_offers_real_original_substrings(self):
        source='---\nname: demo\n---\nRewrite supplied prose without adding facts.\nExplain the provided code and its boundary conditions.'
        choices=case_schema(source)['properties']['source_quote']['enum']
        self.assertIn('Rewrite supplied prose without adding facts.',choices)
        self.assertTrue(all(q in source for q in choices))
        self.assertNotIn('name: demo',choices)

    def test_judge_schema_cannot_stitch_or_paraphrase_evidence(self):
        actual='第一项事实明确。\n第二项边界：缺失值保持未知。'
        quotes=judge_schema(actual)['properties']['evidence']['items']['properties']['quote']['enum']
        self.assertIn('第二项边界：缺失值保持未知。',quotes)
        self.assertTrue(all(q in actual for q in quotes))

    def test_fixed_case_is_not_redesigned_by_model_and_hard_literals_can_veto_judge(self):
        root=BASE/'offline-tests'/str(uuid.uuid4());root.mkdir(parents=True)
        source=root/'source.md';source.write_text('We rewrite prose here.',encoding='utf-8')
        row={'name':'test','tool_name':'test','sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'path':str(source),'source_url':'offline-fixture'}
        for index,required in enumerate([['保留事实'],['不存在的结论']]):
            api=Mock();api.model='offline-test-double'
            api.call.side_effect=[({'status':'done','artifact':self.actual,'limitations':[]},{}),(self.verdict,{})]
            case={**self.case,'required_literals':required}
            result=qualify(api,row,root/f'trial{index}',fixed_case=case)
            self.assertEqual(api.call.call_count,2)
            self.assertEqual(result['passed'],index==0)
            self.assertTrue((root/f'trial{index}/case-origin.json').exists())

    def test_typed_worker_contract_constrains_container_not_business_answer(self):
        root=BASE/'offline-tests'/str(uuid.uuid4());root.mkdir(parents=True)
        source=root/'source.md';source.write_text('We rewrite prose here.',encoding='utf-8')
        row={'name':'test','tool_name':'test','sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'path':str(source),'source_url':'offline-fixture'}
        api=Mock();api.model='offline-test-double'
        api.call.side_effect=[({'status':'done','artifact':self.actual,'limitations':[]},{}),(self.verdict,{})]
        qualify(api,row,root/'typed',fixed_case=self.case,typed_worker=True)
        shape=api.call.call_args_list[0].kwargs['json_mode']
        self.assertEqual(shape['properties']['artifact'],{'type':'string'})
        self.assertNotIn('enum',shape['properties']['artifact'])


if __name__=='__main__':unittest.main()
