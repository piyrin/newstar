import sys
import tempfile
import threading
import json
import urllib.request
import urllib.error
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow' / 'dags'))
from resume_flow.storage import snapshot, run_dir, review_dir, read_json, write_json
from resume_flow.extract import extract_run
from resume_flow.workflow import collect_facts, draft_resume
from resume_flow.sample import SAMPLE_TEXT
from resume_flow.review import prepare_review, approve, verify_approval, make_server, save_review


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        source = self.ws / 'inputs' / 'demo'
        source.mkdir(parents=True)
        (source / 'profile.md').write_text(SAMPLE_TEXT, encoding='utf-8')
        snapshot(self.ws, 'demo', 'run1', '开发实习')
        extract_run(self.ws, 'run1')
        collect_facts(self.ws, 'run1', 'offline')
        draft_resume(self.ws, 'run1', 'offline')
        prepare_review(self.ws, 'run1')

    def choose(self, style='classic'):
        write_json(review_dir(self.ws, 'run1') / 'selection.json',
                   {'schema_version': 1, 'template_id': style, 'mode': 'print', 'paper': 'A4'})

    def test_preview_not_approval_and_requires_selection(self):
        with self.assertRaises(ValueError):
            verify_approval(self.ws, 'run1')
        with self.assertRaises(ValueError):
            approve(self.ws, 'run1')
        self.choose()
        approve(self.ws, 'run1')
        self.assertTrue(verify_approval(self.ws, 'run1')['synthetic'])

    def test_all_styles_supported_and_modified_files_invalidate(self):
        for style in ['classic', 'minimal', 'technical']:
            self.choose(style)
            approve(self.ws, 'run1')
            verify_approval(self.ws, 'run1')
        path = review_dir(self.ws, 'run1') / 'resume.json'
        data = read_json(path)
        data['name'] = '改过的姓名'
        write_json(path, data)
        with self.assertRaises(ValueError):
            verify_approval(self.ws, 'run1')

    def test_unresolved_questions_block(self):
        self.choose()
        path = review_dir(self.ws, 'run1') / 'questions.json'
        write_json(path, [{'id': 'q-test', 'text': '核实奖项', 'fact_ids': [], 'resolution': '', 'note': ''}])
        with self.assertRaises(ValueError):
            approve(self.ws, 'run1')

    def test_changed_template_and_sources_invalidate(self):
        self.choose()
        approve(self.ws, 'run1')
        self.choose('technical')
        with self.assertRaises(ValueError):
            verify_approval(self.ws, 'run1')
        approve(self.ws, 'run1')
        (run_dir(self.ws, 'run1') / 'sources' / 'profile.md').write_text('changed', encoding='utf-8')
        with self.assertRaises(ValueError):
            verify_approval(self.ws, 'run1')

    def test_local_server_requires_token_and_get_does_not_save(self):
        server, token = make_server(self.ws, 'run1')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_port}'
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(url + '/api/state')
        req = urllib.request.Request(url + '/api/state', headers={'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(req) as response:
            state = json.load(response)
        self.assertEqual(state['resume']['name'], '虚构同学')
        self.assertFalse((review_dir(self.ws, 'run1') / 'approval.json').exists())
        state['selection'] = {'schema_version': 1, 'template_id': 'minimal', 'mode': 'print', 'paper': 'A4'}
        req = urllib.request.Request(url + '/api/approve', json.dumps(state).encode(),
                                     {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            self.assertTrue(json.load(response)['ok'])
        verify_approval(self.ws, 'run1')

    def test_omitted_name_and_contact_cannot_remain_in_resume(self):
        self.choose()
        for field, value in [('name', '虚构同学'), ('email', 'student@example.com')]:
            with self.subTest(field=field):
                base = run_dir(self.ws, 'run1') / 'facts.json'
                bundle = read_json(base)
                fid = next(f['id'] for f in bundle['facts'] if f['field'] == field)
                q = {'id': 'q-omit', 'text': '省略这个事实', 'fact_ids': [fid], 'resolution': '', 'note': ''}
                bundle['questions'] = [q]
                write_json(base, bundle)
                write_json(review_dir(self.ws, 'run1') / 'questions.json',
                           [dict(q, resolution='omitted', note='不属于本人')])
                with self.assertRaises(ValueError):
                    approve(self.ws, 'run1')

    def test_failed_approval_returns_fresh_state_for_retry(self):
        server, token = make_server(self.ws, 'run1')
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_port}'
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
        with urllib.request.urlopen(urllib.request.Request(url + '/api/state', headers=headers)) as response:
            state = json.load(response)
        original = state['resume']['contact']
        state['resume']['contact'] = []
        state['selection'] = {'schema_version': 1, 'template_id': 'minimal', 'mode': 'print', 'paper': 'A4'}
        req = urllib.request.Request(url + '/api/approve', json.dumps(state).encode(), headers)
        try:
            urllib.request.urlopen(req)
            self.fail('expected missing-contact error')
        except urllib.error.HTTPError as error:
            state = json.load(error)['state']
        state['resume']['contact'] = original
        req = urllib.request.Request(url + '/api/approve', json.dumps(state).encode(), headers)
        with urllib.request.urlopen(req) as response:
            self.assertTrue(json.load(response)['ok'])

    def test_status_changes_when_approved_and_when_modified(self):
        from resume_flow.review import get_status
        self.choose()
        self.assertEqual(get_status(self.ws, 'run1')['state'], 'waiting_review')
        approve(self.ws, 'run1')
        self.assertEqual(get_status(self.ws, 'run1')['state'], 'approved')
        self.choose('minimal')
        self.assertEqual(get_status(self.ws, 'run1')['state'], 'waiting_review')


if __name__ == '__main__':
    unittest.main()
