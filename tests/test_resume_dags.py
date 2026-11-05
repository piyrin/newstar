import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DagContractTests(unittest.TestCase):
    def test_incremental_prepare_and_manual_export(self):
        source = (ROOT / 'airflow/dags/resume_workflows.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        dag_calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'dag']
        self.assertEqual(len(dag_calls), 2)
        for call in dag_calls:
            kwargs = {k.arg: k.value for k in call.keywords}
            schedule = ast.literal_eval(kwargs['schedule'])
            dag_id = ast.literal_eval(kwargs['dag_id'])
            self.assertEqual(schedule, '*/30 * * * *' if dag_id == 'resume_prepare' else None)
            self.assertTrue(ast.literal_eval(kwargs['is_paused_upon_creation']))
        self.assertIn('resume_prepare', source)
        self.assertIn('resume_export', source)


if __name__ == '__main__':
    unittest.main()
