import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow/dags'))
from resume_flow.natural import parse_request, execute_request
from resume_flow.airflow_api import AirflowClient


class NaturalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        (self.ws / 'inputs/demo').mkdir(parents=True)

    def model(self, response):
        client = unittest.mock.Mock()
        client.complete.return_value = response
        return client

    def test_prepare_resolves_only_existing_case_and_validated_parameters(self):
        model = self.model({'action': 'prepare', 'case_id': 'demo', 'target': '后端实习', 'mode': 'offline'})
        plan = parse_request(self.ws, '用 demo 虚构材料做后端实习草稿，离线运行', model)
        self.assertEqual(plan['dag_id'], 'resume_prepare')
        self.assertEqual(plan['conf']['target'], '后端实习')
        self.assertNotIn('材料正文', str(model.complete.call_args))

    def test_unknown_dag_and_extra_fields_are_rejected(self):
        for raw in [{'action': 'delete'}, {'action': 'prepare', 'case_id': 'demo', 'code': 'evil'},
                    {'action': 'prepare', 'case_id': '../private'},
                    {'action': 'prepare', 'case_id': 'missing'},
                    {'action': 'prepare', 'case_id': 'demo', 'mode': []}]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_request(self.ws, '请求', self.model(raw))

    def test_ambiguous_request_clarifies_without_airflow(self):
        plan = parse_request(self.ws, '帮我处理一下', self.model({'action': 'clarify', 'question': '请指定材料目录和目标岗位'}))
        with patch('resume_flow.natural.AirflowClient') as api:
            result = execute_request(self.ws, plan, request_id='req1')
            api.assert_not_called()
        self.assertEqual(result['state'], 'needs_input')

    def test_export_requires_existing_human_confirmation_even_in_dry_run(self):
        plan = parse_request(self.ws, '导出 run1', self.model({'action': 'export', 'run_key': 'run1'}))
        with self.assertRaises(ValueError), patch('resume_flow.natural.AirflowClient') as api:
            execute_request(self.ws, plan, request_id='req1', dry_run=True)
        api.assert_not_called()

    def test_dry_run_does_not_contact_airflow_and_request_id_fixes_export_key(self):
        plan = parse_request(self.ws, '整理 demo', self.model({'action': 'prepare', 'case_id': 'demo'}))
        with patch('resume_flow.natural.AirflowClient') as api:
            result = execute_request(self.ws, plan, request_id='req1', dry_run=True)
        api.assert_not_called()
        self.assertEqual(result['dag_run_id'], 'nl-req1')

    def test_invalid_status_dag_rejected(self):
        with self.assertRaises(ValueError):
            parse_request(self.ws, '状态', self.model({'action': 'status', 'dag_id': 'other', 'dag_run_id': 'run'}))

    def test_dry_run_and_validation_never_log_prompt_or_secrets(self):
        plan = parse_request(self.ws, '整理 demo', self.model({'action': 'prepare', 'case_id': 'demo'}))
        self.assertNotIn('text', execute_request(self.ws, plan, 'r1', dry_run=True))

    def test_env_loads_only_allowed_keys_without_expansion_or_override(self):
        from resume_flow.config import load_env
        path = self.ws / '.env'
        path.write_text('DEEPSEEK_API_KEY="literal-$(command)"\nAIRFLOW_API_USERNAME=from-file # note\nPATH=evil\n', encoding='utf-8')
        with patch.dict(os.environ, {'AIRFLOW_API_USERNAME': 'existing'}, clear=True):
            load_env(path)
            self.assertEqual(os.environ['AIRFLOW_API_USERNAME'], 'existing')
            self.assertEqual(os.environ['DEEPSEEK_API_KEY'], 'literal-$(command)')
            self.assertNotIn('PATH', os.environ)

    def test_explicit_api_credentials_override_initializer_aliases(self):
        from resume_flow.config import load_env
        path = self.ws / '.env'
        path.write_text('_AIRFLOW_WWW_USER_USERNAME=initializer\nAIRFLOW_API_USERNAME=api-user\n', encoding='utf-8')
        with patch.dict(os.environ, {}, clear=True):
            load_env(path)
            self.assertEqual(os.environ['AIRFLOW_API_USERNAME'], 'api-user')


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.runs = {}
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.handle_request()

            def do_POST(self):
                self.handle_request()

            def handle_request(self):
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
                parent.requests.append((self.command, self.path, body, self.headers.get('Authorization')))
                status, result = 200, {}
                if self.path == '/auth/token':
                    result = {'access_token': 'fake-token'}
                elif self.headers.get('Authorization') != 'Bearer fake-token':
                    status = 401
                elif self.path.endswith('/taskInstances'):
                    result = {'task_instances': [{'task_id': 'snapshot_materials', 'state': 'skipped'}]}
                elif self.path.endswith('/dagRuns') and self.command == 'POST':
                    key = body['dag_run_id']
                    if key in parent.runs:
                        status = 409
                    else:
                        parent.runs[key] = dict(body, state='queued')
                    result = parent.runs[key]
                elif '/dagRuns/' in self.path:
                    key = self.path.rsplit('/', 1)[-1]
                    status = 200 if key in parent.runs else 404
                    result = parent.runs.get(key, {})
                else:
                    result = {'is_paused': False}
                encoded = json.dumps(result).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.client = AirflowClient(base_url=f'http://127.0.0.1:{self.server.server_port}', username='user', password='secret')

    def test_jwt_trigger_idempotency_conflict_and_status(self):
        conf = {'case_id': 'demo'}
        run = self.client.trigger('resume_prepare', 'nl-r1', conf)
        self.assertEqual(run['state'], 'queued')
        self.assertIsNone(self.requests[1][2]['logical_date'])
        self.assertEqual(self.client.trigger('resume_prepare', 'nl-r1', conf)['state'], 'queued')
        with self.assertRaises(ValueError):
            self.client.trigger('resume_prepare', 'nl-r1', {'case_id': 'other'})
        result = self.client.status('resume_prepare', 'nl-r1')
        self.assertEqual(result['tasks'][0]['state'], 'skipped')

    def test_client_rejects_unknown_dag_and_missing_run(self):
        with self.assertRaises(ValueError):
            self.client.trigger('other', 'r1', {})
        with self.assertRaisesRegex(ValueError, '404'):
            self.client.status('resume_prepare', 'absent')

    def test_credentials_are_not_sent_to_remote_plain_http(self):
        with self.assertRaises(ValueError):
            AirflowClient(base_url='http://example.com', username='u', password='p')


if __name__ == '__main__':
    unittest.main()
