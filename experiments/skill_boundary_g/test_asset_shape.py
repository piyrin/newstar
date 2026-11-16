import unittest,uuid,hashlib
from runner import BASE
from progressive import physical_checks,review_diagnostics,csv_asset_issues

class CSVDeliveryShape(unittest.TestCase):
    def selected(self,text):
        root=BASE/'offline-tests'/str(uuid.uuid4());root.mkdir(parents=True)
        p=root/'records.csv';p.write_text(text,encoding='utf-8')
        return {'FILE-001-01':{'path':str(p),'content':text,'artifact':text,
            'files':[{'path':str(p),'format':'csv','sha256':hashlib.sha256(p.read_bytes()).hexdigest()}]}}
    def test_mixed_tables_are_not_a_usable_single_csv(self):
        selected=self.selected('name,session,date\nA,first,2026-11-21\nvenue,800\n')
        self.assertFalse(physical_checks({'facts':{}},selected,check_csv_shape=True)['csv_assets_rectangular'])
        issues=csv_asset_issues(selected)
        self.assertEqual(issues[0]['reference_id'],'FILE-001-01')
        self.assertEqual((issues[0]['row'],issues[0]['expected_columns'],issues[0]['actual_columns']),(3,3,2))
    def test_quoted_commas_and_empty_rows_are_valid(self):
        selected=self.selected('name,session\n"A,B",first\n\n,\n')
        self.assertTrue(physical_checks({'facts':{}},selected,check_csv_shape=True)['csv_assets_rectangular'])
    def test_schedule_feedback_states_missing_constraint_without_answer(self):
        text=' '.join(review_diagnostics({'event_feasible_explicit_allocation':False}))
        self.assertIn('明确场次分配',text);self.assertNotIn('60',text);self.assertNotIn('14:00',text)

if __name__=='__main__':unittest.main()
