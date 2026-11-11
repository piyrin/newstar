import unittest
from runner import TASKS,deterministic_checks

class ActualDeliverableChecks(unittest.TestCase):
    def check_launch(self,body):
        case=next(t for t in TASKS if t['id']=='launch')
        return deterministic_checks(case,{'A1':{'artifact':body}})

    def test_empty_csv_and_real_commands(self):
        result=self.check_launch('```csv\nissue_id,course,description,status\n```\n'
            'python -m coursedock index ./notes\npython -m coursedock serve --port 4177')
        self.assertTrue(all(result.values()))

    def test_invented_data_cannot_pass_as_empty_template(self):
        result=self.check_launch('```csv\nissue_id,course,description,status\nI1,math,fake,new\n```')
        self.assertFalse(result['parseable_exact_csv_header'])

    def test_wrong_header_order_rejected(self):
        result=self.check_launch('```csv\ncourse,issue_id,description,status\n```')
        self.assertFalse(result['parseable_exact_csv_header'])

    def test_wrong_port_rejected(self):
        result=self.check_launch('python -m coursedock index ./notes\npython -m coursedock serve --port 8080')
        self.assertFalse(result['quickstart_commands_preserved'])

    def test_csv_after_other_code_fences_is_not_lost(self):
        result=self.check_launch('```bash\npython -m coursedock index ./notes\n```\n'
            '```json\n{"status":"new"}\n```\n'
            '```csv\nissue_id,course,description,status\n```\n'
            'python -m coursedock serve --port 4177')
        self.assertTrue(result['parseable_exact_csv_header'])

if __name__=='__main__':unittest.main()
