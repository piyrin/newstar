import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow' / 'dags'))
from resume_flow.storage import snapshot, run_dir, read_json
from resume_flow.extract import extract_run
from resume_flow.llm import DeepSeekClient
from resume_flow.workflow import validate_facts, collect_facts, draft_resume


SEGMENTS = [{'id': 's0001', 'text': '姓名：虚构同学；开发了资料整理工具',
             'source': 'profile.md', 'location': 'text', 'method': 'text'}]


class FactsTests(unittest.TestCase):
    def fact(self, **extra):
        return dict({'field': 'name', 'value': '虚构同学', 'segment_id': 's0001',
                     'quote': '姓名：虚构同学', 'ownership': 'not_applicable'}, **extra)

    def test_bad_reference_and_fabrication_rejected(self):
        for fact in [self.fact(segment_id='missing'), self.fact(quote='不存在的原文'),
                     self.fact(value='另一个同学')]:
            with self.assertRaises(ValueError):
                validate_facts({'facts': [fact]}, SEGMENTS)

    def test_contribution_requires_human_and_conflict_is_question(self):
        data = {'facts': [self.fact(), self.fact(field='project', value='开发了资料整理工具',
                                                quote='开发了资料整理工具', ownership='user')]}
        facts, questions = validate_facts(data, SEGMENTS)
        self.assertEqual(facts[1]['ownership'], 'unknown')
        self.assertTrue(any('个人贡献' in q['text'] for q in questions))
        self.assertTrue(any('联系' in q['text'] for q in questions))

    def test_conflicting_names_flagged(self):
        segments = SEGMENTS + [dict(SEGMENTS[0], id='s0002', text='姓名：另一位同学')]
        _, questions = validate_facts({'facts': [self.fact(), self.fact(value='另一位同学',
                                    segment_id='s0002', quote='姓名：另一位同学')]}, segments)
        self.assertTrue(any('冲突' in q['text'] for q in questions))

    @patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-secret'})
    def test_blank_and_truncated_retried_but_never_accepted(self):
        for content, finish in [('   ', 'stop'), ('{}', 'length')]:
            body = json.dumps({'choices': [{'message': {'content': content},
                                          'finish_reason': finish}]}).encode()
            with patch('urllib.request.urlopen', side_effect=lambda *a, **k: io.BytesIO(body)) as mock:
                with self.assertRaises(ValueError):
                    DeepSeekClient(retries=1, backoff=0).complete('JSON', {})
                self.assertEqual(mock.call_count, 2)

    @patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-secret'})
    def test_client_checks_json_and_does_not_put_secret_in_body(self):
        body = json.dumps({'choices': [{'message': {'content': '{"facts":[]}'},
                                       'finish_reason': 'stop'}]}).encode()
        with patch('urllib.request.urlopen', return_value=io.BytesIO(body)) as request:
            self.assertEqual(DeepSeekClient().complete('JSON', {}), {'facts': []})
            self.assertNotIn(b'test-secret', request.call_args.args[0].data)

    def test_offline_cannot_process_personal_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            source = ws / 'inputs' / 'personal'
            source.mkdir(parents=True)
            (source / 'me.md').write_text('姓名：真实资料', encoding='utf-8')
            snapshot(ws, 'personal', 'run1')
            extract_run(ws, 'run1')
            with self.assertRaises(ValueError):
                collect_facts(ws, 'run1', 'offline')

    def test_zero_fact_material_must_be_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            source = ws / 'inputs' / 'personal'
            source.mkdir(parents=True)
            (source / 'profile.md').write_text('姓名：虚构同学；邮箱：student@example.com；技能：Python', encoding='utf-8')
            (source / 'z_award.md').write_text('省级一等奖', encoding='utf-8')
            snapshot(ws, 'personal', 'run1')
            extract_run(ws, 'run1')
            facts = [self.fact(), self.fact(field='email', value='student@example.com', quote='邮箱：student@example.com'),
                     self.fact(field='skill', value='Python', quote='技能：Python')]
            with patch('resume_flow.workflow.DeepSeekClient') as client:
                client.return_value.complete.side_effect = [{'facts': facts}, {'facts': []}]
                collect_facts(ws, 'run1')
            bundle = read_json(run_dir(ws, 'run1') / 'facts.json')
            self.assertTrue(any('z_award.md' in q['text'] for q in bundle['questions']))

    def test_deepseek_sample_stays_marked_synthetic(self):
        from resume_flow.sample import SAMPLE_TEXT
        from resume_flow.workflow import offline_facts
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            source = ws / 'inputs' / 'demo'
            source.mkdir(parents=True)
            (source / 'profile.md').write_text(SAMPLE_TEXT, encoding='utf-8')
            snapshot(ws, 'demo', 'live-sample')
            extract_run(ws, 'live-sample')
            segments = read_json(run_dir(ws, 'live-sample') / 'extracted.json')['segments']
            with patch('resume_flow.workflow.DeepSeekClient') as client:
                client.return_value.complete.return_value = offline_facts(segments)
                collect_facts(ws, 'live-sample', 'deepseek')
            bundle = read_json(run_dir(ws, 'live-sample') / 'facts.json')
            self.assertEqual(bundle['mode'], 'deepseek')
            self.assertTrue(bundle['synthetic'])


if __name__ == '__main__':
    unittest.main()
