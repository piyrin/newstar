import ast
import sys
import unittest
import types
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DagContractTests(unittest.TestCase):
    def test_material_entry_waits_in_an_independent_dag(self):
        source = (ROOT / 'airflow/dags/resume_start.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        self.assertIn('await_materials', source)
        self.assertIn('start_prepare', source)
        decorator = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                         and isinstance(node.func, ast.Name) and node.func.id == 'dag')
        options = {k.arg: k.value for k in decorator.keywords}
        self.assertEqual(ast.literal_eval(options['dag_id']), 'resume_start')
        self.assertIsNone(ast.literal_eval(options['schedule']))
        self.assertGreater(ast.literal_eval(options['max_active_runs']), 1)

    def test_manual_review_keeps_waiting_until_bound_confirmation(self):
        source = (ROOT / 'airflow/dags/resume_workflows.py').read_text(encoding='utf-8')
        function = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)
                        and n.name == 'review_approved')
        namespace = {'workspace': lambda: Path('/unused'),
                     'get_current_context': lambda: {'dag_run': types.SimpleNamespace(run_type='manual')}}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<review_sensor>', 'exec'), namespace)
        class Skip(Exception):
            pass
        sdk = types.ModuleType('airflow.sdk.exceptions')
        sdk.AirflowSkipException = Skip
        sys.path.insert(0, str(ROOT / 'airflow/dags'))
        with patch.dict(sys.modules, {'airflow.sdk.exceptions': sdk}), \
                patch('resume_flow.approval_wait.await_run_approval', return_value=False) as approved:
            version = {'run_key': 'existing', 'skip': True}
            self.assertFalse(namespace['review_approved'](version, 'manual-duplicate'))
            self.assertFalse(namespace['review_approved'](dict(version, skip=False), 'new-draft'))
            with self.assertRaises(Skip):
                namespace['review_approved'](dict(version, scheduled_unchanged=True), 'scheduled-check')
            approved.return_value = True
            self.assertTrue(namespace['review_approved'](version, 'confirmed-export'))

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

    def test_trigger_form_allows_empty_optional_fields(self):
        tree = ast.parse((ROOT / 'airflow/dags/resume_workflows.py').read_text(encoding='utf-8'))
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != 'dag':
                continue
            kwargs = {k.arg: k.value for k in call.keywords}
            dag_id = ast.literal_eval(kwargs['dag_id'])
            optional = {'run_key', 'target', 'jd'} if dag_id == 'resume_prepare' else {'export_key'}
            params = kwargs['params']
            for key, value in zip(params.keys, params.values):
                name = ast.literal_eval(key)
                if name in optional:
                    options = {k.arg: k.value for k in value.keywords}
                    self.assertEqual(set(ast.literal_eval(options['type'])), {'null', 'string'})

    def test_prepare_has_full_chain_and_nonblocking_review_gate(self):
        tree = ast.parse((ROOT / 'airflow/dags/resume_workflows.py').read_text(encoding='utf-8'))
        prepare = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                       and node.name == 'resume_prepare')
        functions = {node.name: node for node in prepare.body if isinstance(node, ast.FunctionDef)}
        self.assertTrue({'snapshot_materials', 'extract_materials', 'organize_facts', 'write_draft',
                         'publish_review', 'verify_and_freeze', 'render_word', 'export_pdf',
                         'check_pages', 'open_material_page'}.issubset(functions))
        decorator = functions['publish_review'].decorator_list[0]
        self.assertEqual(ast.literal_eval(decorator.keywords[0].value), 'none_failed')
        self.assertFalse(any(isinstance(n, ast.Name) and n.id == 'AirflowSkipException'
                             for n in ast.walk(functions['snapshot_materials'])))
        self.assertTrue(any(isinstance(n, ast.Name) and n.id == 'AirflowSkipException'
                            for n in ast.walk(functions['extract_materials'])))
        sensor = next(n for n in ast.walk(prepare) if isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Name) and n.func.id == 'PythonSensor')
        options = {k.arg:k.value for k in sensor.keywords}
        self.assertEqual(ast.literal_eval(options['task_id']), 'await_materials')
        self.assertEqual(ast.literal_eval(options['mode']), 'reschedule')
        for name in ('snapshot_materials','extract_materials','organize_facts','write_draft','publish_review'):
            decorator = functions[name].decorator_list[0]
            opts = {k.arg:k.value for k in decorator.keywords}
            self.assertEqual(ast.literal_eval(opts['pool']), 'resume_preparation')
        review_sensor = next(n for n in ast.walk(prepare) if isinstance(n, ast.Call)
                             and isinstance(n.func, ast.Name) and n.func.id == 'PythonSensor'
                             and any(k.arg == 'task_id' and ast.literal_eval(k.value) == 'await_review'
                                     for k in n.keywords))
        opts = {k.arg: k.value for k in review_sensor.keywords}
        self.assertEqual(ast.literal_eval(opts['mode']), 'reschedule')
        self.assertEqual(ast.literal_eval(opts['timeout']), 604800)
        self.assertEqual(ast.unparse(opts['python_callable']), 'review_approved')
        self.assertNotIn('soft_fail', opts)

    def test_main_dag_accepts_multiple_waiting_intakes_and_blank_new_case(self):
        tree = ast.parse((ROOT/'airflow/dags/resume_workflows.py').read_text(encoding='utf-8'))
        prepare = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='resume_prepare')
        options = {k.arg:k.value for k in prepare.decorator_list[0].keywords}
        self.assertGreater(ast.literal_eval(options['max_active_runs']), 1)
        params = options['params']
        case = next(v for k,v in zip(params.keys,params.values) if ast.literal_eval(k)=='case_id')
        self.assertEqual(ast.literal_eval(case.args[0]), '')


if __name__ == '__main__':
    unittest.main()
