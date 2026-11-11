import unittest
from business_evidence import validate_event_evidence, resolve_line_evidence,line_evidence_schema,event_constraint_issues,verified_actual_spend_claims

class BusinessEvidenceContract(unittest.TestCase):
    def setUp(self):
        self.facts={'registered_people':120,'room_capacity':80,'session_minutes':120,'time_window':'14:00—18:00','budget_yuan':3000,
                    'costs':{'venue_yuan':800,'materials_per_person_yuan':6,'snacks_per_person_yuan':4,'photography_yuan':500}}
        self.text='第一场14:00—16:00分配60人；第二场16:00—18:00分配60人。预计合计2500元，结余500元。'
        self.evidence={'sessions':[{'start':'14:00','end':'16:00','allocated_people':60,'quote':'第一场14:00—16:00分配60人'},
                                   {'start':'16:00','end':'18:00','allocated_people':60,'quote':'第二场16:00—18:00分配60人'}],
                       'total':{'value':2500,'quote':'预计合计2500元'},'remaining':{'value':500,'quote':'结余500元'},
                       'unsupported_actual_spend_claims':[]}
    def test_explicit_assignment_and_quote_grounded_budget_pass(self):
        self.assertTrue(all(validate_event_evidence(self.facts,self.text,self.evidence).values()))
    def test_capacity_cannot_replace_actual_planned_allocation(self):
        self.evidence['sessions'][0]['allocated_people']=80
        self.assertFalse(all(validate_event_evidence(self.facts,self.text,self.evidence).values()))
    def test_invented_evidence_cannot_pass(self):
        self.evidence['sessions'][0]['quote']='这个片段在产物中并不存在'
        self.assertFalse(all(validate_event_evidence(self.facts,self.text,self.evidence).values()))
    def test_plan_cannot_be_claimed_as_observed_spending(self):
        self.text+='\n| 实际支出合计 | 2500 元 |'
        self.assertFalse(all(validate_event_evidence(self.facts,self.text,self.evidence).values()))

    def test_line_selection_reads_verbatim_source_in_host(self):
        text='第一场14:00—16:00分配60人\n第二场16:00—18:00分配60人\n预计合计2500元\n结余500元\n状态：待支付/已支付（待选）'
        raw={'sessions':[{'start':'14:00','end':'16:00','allocated_people':60,'time_line_id':'L0001','people_line_id':'L0001'},
                         {'start':'16:00','end':'18:00','allocated_people':60,'time_line_id':'L0002','people_line_id':'L0002'}],
             'total':{'value':2500,'line_id':'L0003'},'remaining':{'value':500,'line_id':'L0004'},'unsupported_actual_spend_claim_line_ids':['L0005']}
        evidence=resolve_line_evidence(text,raw)
        self.assertEqual(evidence['total']['quote'],'预计合计2500元')
        self.assertTrue(all(validate_event_evidence(self.facts,text,evidence).values()))

    def test_unknown_line_id_cannot_become_a_quote(self):
        with self.assertRaises(ValueError):
            resolve_line_evidence('只有一行',{'sessions':[],'total':{'value':2500,'line_id':'L9999'},
                'remaining':{'value':500,'line_id':'L0001'},'unsupported_actual_spend_claim_line_ids':[]})

    def test_line_protocol_does_not_ignore_actual_spending(self):
        text=self.text+'\n实际支出合计：2500元'
        evidence=dict(self.evidence,schema_version='line_ids_v1',unsupported_actual_spend_claims=['实际支出合计：2500元'])
        self.assertFalse(validate_event_evidence(self.facts,text,evidence)['event_no_unverified_actual_spend'])

    def test_schema_only_permits_real_source_line_ids(self):
        schema=line_evidence_schema('第一行\n第二行')
        allowed=schema['properties']['total']['properties']['line_id']['enum']
        self.assertEqual(allowed,['L0001','L0002',None])

    def test_diagnostics_report_actual_and_required_session_duration(self):
        self.evidence['sessions'][0]['end']='15:20'
        issues=event_constraint_issues(self.facts,self.evidence)
        self.assertTrue(any(x.get('actual_minutes')==80 and x.get('required_minutes')==120 for x in issues))

    def test_budget_column_is_not_a_payment_even_if_model_flags_it(self):
        text='| 项目 | 预计金额 | 实际金额 |\n|---|---|---|\n| 场地 | 800 | 待填写 |'
        self.assertEqual(verified_actual_spend_claims(text),[])
        self.assertTrue(verified_actual_spend_claims(text.replace('待填写','800')))

    def test_actual_happened_status_is_not_missed(self):
        text='| 合计支出 | 2500 | 实际发生 |'
        self.assertEqual(verified_actual_spend_claims(text),[text])

if __name__=='__main__':unittest.main()
