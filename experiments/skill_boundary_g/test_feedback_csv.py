import unittest
from feedback_csv import feedback_csv_issues


class AllFeedbackCSVContract(unittest.TestCase):
    def test_hard_gate_rejects_extra_records_even_with_one_exact_empty_file(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import hashlib
        from progressive import physical_checks,suite
        with TemporaryDirectory() as directory:
            selected={}
            for name,text in [('empty','issue_id,course,description,status\n'),('extra','issue_id,course,description,status\nISS-1,Search,invented,new\n')]:
                path=Path(directory)/(name+'.csv');path.write_text(text,encoding='utf-8')
                selected[name]={'path':str(path),'content':text,'artifact':text,'files':[{'path':str(path),'format':'csv','sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]}
            checks=physical_checks(suite('release')[0],selected,check_csv_shape=True,strict_feedback_csv=True)
            self.assertTrue(checks['csv_file_exact_empty_template'])
            self.assertFalse(checks['all_feedback_csvs_without_invented_rows'])
    facts={'feedback_fields':['issue_id','course','description','status'],'statuses':['new','triaged','closed']}
    def ref(self,body):return {'DOC-001':{'content':body,'path':'saved.md','files':[]}}

    def test_empty_template_does_not_excuse_a_second_populated_feedback_csv(self):
        body='```csv\nissue_id,course,description,status\n```\n\n```csv\nissue_id,course,description,status\nISS-001,Indexing,invented bug,new\n```'
        self.assertTrue(feedback_csv_issues(self.facts,self.ref(body)))

    def test_nested_markdown_example_is_checked_even_without_exported_attachment(self):
        body='```markdown\n# Suggested workflow\n```csv\nissue_id,course,description,status\nISS-001,Search,invented bug,closed (unsupported)\n```\n```'
        issues=feedback_csv_issues(self.facts,self.ref(body))
        self.assertEqual(issues[0]['reference_id'],'DOC-001')
        self.assertIn('data_rows',issues[0])

    def test_prose_field_list_and_markdown_table_are_not_csv_records(self):
        body='字段：issue_id,course,description,status\n\n| issue_id | course | description | status |\n| --- | --- | --- | --- |\n'
        self.assertEqual(feedback_csv_issues(self.facts,self.ref(body)),[])

    def test_blank_or_explicit_fill_placeholders_are_not_invented_records(self):
        body='```csv\nissue_id,course,description,status\n,,,\n<issue_id>,<course>,<description>,new\n```'
        self.assertEqual(feedback_csv_issues(self.facts,self.ref(body)),[])

    def test_wrong_field_order_is_rejected_for_every_feedback_table(self):
        body='```csv\ncourse,issue_id,description,status\n```'
        self.assertTrue(feedback_csv_issues(self.facts,self.ref(body)))

if __name__=='__main__':unittest.main()
