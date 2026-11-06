import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow' / 'dags'))
from resume_flow import prompts
from resume_flow.storage import digest, snapshot, run_dir, read_json, write_json
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

    def test_pdf_whitespace_is_aligned_back_to_exact_source(self):
        segment = dict(SEGMENTS[0], text='姓名：虚构\n同学；技能：Py thon')
        facts, _ = validate_facts({'facts': [self.fact(quote='姓名：虚构同学')]}, [segment])
        self.assertEqual(facts[0]['value'], '虚构\n同学')
        self.assertEqual(facts[0]['quote'], '姓名：虚构\n同学')
        self.assertIn(facts[0]['value'], facts[0]['quote'])
        self.assertIn(facts[0]['quote'], segment['text'])

    def test_invalid_model_facts_are_repaired_once_and_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            source = ws / 'inputs/personal/profile.md'
            source.parent.mkdir(parents=True)
            source.write_text(SEGMENTS[0]['text'], encoding='utf-8')
            snapshot(ws, 'personal', 'run1')
            extract_run(ws, 'run1')
            with patch('resume_flow.workflow.DeepSeekClient') as client:
                client.return_value.complete.side_effect = [
                    {'facts': [self.fact(value='不存在', quote='姓名：虚构同学')]},
                    {'facts': [self.fact()]}]
                collect_facts(ws, 'run1')
                self.assertEqual(client.return_value.complete.call_count, 2)
            bundle = read_json(run_dir(ws, 'run1') / 'facts.json')
            self.assertEqual(bundle['facts'][0]['value'], '虚构同学')
            with patch('resume_flow.workflow.DeepSeekClient') as client:
                collect_facts(ws, 'run1')
                client.return_value.complete.assert_not_called()

    def test_unverified_candidates_become_questions_without_discarding_valid_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            source = ws / 'inputs/personal/profile.md'
            source.parent.mkdir(parents=True)
            source.write_text(SEGMENTS[0]['text'], encoding='utf-8')
            snapshot(ws, 'personal', 'run1')
            extract_run(ws, 'run1')
            output = {'facts': [self.fact(), self.fact(field='award', value='国赛一等奖', quote='国赛一等奖')]}
            with patch('resume_flow.workflow.DeepSeekClient') as client:
                client.return_value.complete.return_value = output
                collect_facts(ws, 'run1')
                self.assertEqual(client.return_value.complete.call_count, 2)
            bundle = read_json(run_dir(ws, 'run1') / 'facts.json')
            self.assertEqual([f['value'] for f in bundle['facts']], ['虚构同学'])
            self.assertTrue(any('来源校验' in q['text'] for q in bundle['questions']))

    def test_correction_cannot_silently_drop_valid_or_unresolved_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            source = ws / 'inputs/personal/profile.md'
            source.parent.mkdir(parents=True)
            source.write_text(SEGMENTS[0]['text'] + '；技能：Python', encoding='utf-8')
            snapshot(ws, 'personal', 'run1')
            extract_run(ws, 'run1')
            with patch('resume_flow.workflow.DeepSeekClient') as client:
                client.return_value.complete.side_effect = [
                    {'facts': [self.fact(), self.fact(field='award', value='国赛一等奖', quote='国赛一等奖')]},
                    {'facts': [self.fact(field='skill', value='Python', quote='技能：Python')]}]
                collect_facts(ws, 'run1')
            bundle = read_json(run_dir(ws, 'run1') / 'facts.json')
            self.assertEqual({f['field'] for f in bundle['facts']}, {'name', 'skill'})
            self.assertTrue(any('来源校验' in q['text'] for q in bundle['questions']))

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


class DraftCheckpointTests(unittest.TestCase):
    def prepare(self, workspace, mode='deepseek'):
        from resume_flow.sample import SAMPLE_TEXT
        from resume_flow.workflow import offline_facts
        source = workspace / 'inputs/demo/profile.md'
        source.parent.mkdir(parents=True)
        source.write_text(SAMPLE_TEXT, encoding='utf-8')
        snapshot(workspace, 'demo', 'run1', target='开发实习', jd='Python')
        extract_run(workspace, 'run1')
        directory = run_dir(workspace, 'run1')
        segments = read_json(directory / 'extracted.json')['segments']
        with patch('resume_flow.workflow.DeepSeekClient') as client:
            client.return_value.complete.return_value = offline_facts(segments)
            collect_facts(workspace, 'run1', mode)
        facts = read_json(directory / 'facts.json')['facts']
        skill = next(f for f in facts if f['field'] == 'skill')
        self.output = {'sections': [{'title': '专业技能', 'items': [
            {'title': '', 'paragraphs': [skill['value']], 'fact_ids': [skill['id']]}]}]}
        return directory

    def test_duplicate_draft_preserves_bytes_and_timestamp_without_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            directory = self.prepare(workspace)
            with patch('resume_flow.workflow.DeepSeekClient') as client:
                client.return_value.complete.return_value = self.output
                draft_resume(workspace, 'run1')
            path = directory / 'resume.draft.json'
            original = path.read_bytes()
            os.utime(path, ns=(1_000_000_000, 1_000_000_000))
            with patch('resume_flow.workflow.DeepSeekClient', side_effect=AssertionError('duplicate model call')):
                self.assertEqual(draft_resume(workspace, 'run1'), 'run1')
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(path.stat().st_mtime_ns, 1_000_000_000)
            self.assertTrue(read_json(directory / 'facts.json')['synthetic'])

    def test_relevant_input_changes_rebuild_draft(self):
        for change in ('facts', 'questions', 'target', 'jd', 'prompt', 'model'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                workspace = Path(tmp)
                directory = self.prepare(workspace)
                with patch('resume_flow.workflow.DeepSeekClient') as client:
                    client.return_value.complete.return_value = self.output
                    draft_resume(workspace, 'run1')
                    if change in ('facts', 'questions'):
                        path = directory / 'facts.json'
                        bundle = read_json(path)
                        if change == 'facts':
                            bundle['facts'][0]['value'] = '另一个虚构同学'
                        else:
                            bundle['questions'].append({'text': '新增核对问题'})
                        write_json(path, bundle)
                    if change in ('target', 'jd'):
                        path = directory / 'manifest.json'
                        manifest = read_json(path)
                        manifest['config'][change] = '新岗位要求'
                        manifest['snapshot_hash'] = digest({k: v for k, v in manifest.items() if k != 'snapshot_hash'})
                        write_json(path, manifest)
                    with patch('resume_flow.workflow.prompts.DRAFT', 'new prompt' if change == 'prompt' else prompts.DRAFT), \
                         patch.dict(os.environ, {'DEEPSEEK_MODEL': 'changed-model'} if change == 'model' else {}):
                        draft_resume(workspace, 'run1')
                    self.assertEqual(client.return_value.complete.call_count, 2)

    def test_missing_or_tampered_draft_rebuilds(self):
        for missing in (False, True):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as tmp:
                workspace = Path(tmp)
                directory = self.prepare(workspace)
                with patch('resume_flow.workflow.DeepSeekClient') as client:
                    client.return_value.complete.return_value = self.output
                    draft_resume(workspace, 'run1')
                    path = directory / 'resume.draft.json'
                    if missing:
                        path.unlink()
                    else:
                        path.write_text('{"tampered": true}', encoding='utf-8')
                    draft_resume(workspace, 'run1')
                    self.assertEqual(client.return_value.complete.call_count, 2)
                    self.assertEqual(read_json(path)['sections'], self.output['sections'])

    def test_failed_rebuild_does_not_accept_restored_old_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            directory = self.prepare(workspace)
            with patch('resume_flow.workflow.DeepSeekClient') as client:
                client.return_value.complete.return_value = self.output
                draft_resume(workspace, 'run1')
                path = directory / 'resume.draft.json'
                original = path.read_bytes()
                path.write_text('{}', encoding='utf-8')
                client.return_value.complete.side_effect = ValueError('model failed')
                with self.assertRaisesRegex(ValueError, 'model failed'):
                    draft_resume(workspace, 'run1')
                path.write_bytes(original)
                client.return_value.complete.side_effect = None
                draft_resume(workspace, 'run1')
                self.assertEqual(client.return_value.complete.call_count, 3)

    def test_missing_or_malformed_checkpoint_rebuilds(self):
        for saved in (None, '{invalid', '[]', '{}'):
            with self.subTest(saved=saved), tempfile.TemporaryDirectory() as tmp:
                workspace = Path(tmp)
                directory = self.prepare(workspace)
                with patch('resume_flow.workflow.DeepSeekClient') as client:
                    client.return_value.complete.return_value = self.output
                    draft_resume(workspace, 'run1')
                    path = directory / 'model-draft.json'
                    if saved is None:
                        path.unlink()
                    else:
                        path.write_text(saved, encoding='utf-8')
                    draft_resume(workspace, 'run1')
                    self.assertEqual(client.return_value.complete.call_count, 2)
                    self.assertEqual(read_json(directory / 'resume.draft.json')['sections'], self.output['sections'])

    def test_rebuild_still_validates_evidence_before_saving_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            directory = self.prepare(workspace)
            with patch('resume_flow.workflow.DeepSeekClient') as client:
                client.return_value.complete.return_value = self.output
                draft_resume(workspace, 'run1')
                path = directory / 'resume.draft.json'
                original = path.read_bytes()
                self.output['sections'][0]['items'][0]['paragraphs'] = ['提升999倍']
                with patch.dict(os.environ, {'DEEPSEEK_MODEL': 'changed-model'}):
                    with self.assertRaisesRegex(ValueError, '无证据的数字'):
                        draft_resume(workspace, 'run1')
                self.assertEqual(path.read_bytes(), original)
                self.assertFalse((directory / 'model-draft.json').exists())

    def test_cached_draft_still_checks_snapshot_and_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            directory = self.prepare(workspace)
            with patch('resume_flow.workflow.DeepSeekClient') as client:
                client.return_value.complete.return_value = self.output
                draft_resume(workspace, 'run1')
            with self.assertRaisesRegex(ValueError, '混用'):
                draft_resume(workspace, 'run1', 'offline')
            (directory / 'sources/profile.md').write_text('changed', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '快照已改动'):
                draft_resume(workspace, 'run1')

    def test_offline_draft_is_cached_without_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            directory = self.prepare(workspace, 'offline')
            with patch('resume_flow.workflow.DeepSeekClient', side_effect=AssertionError('offline model call')):
                draft_resume(workspace, 'run1', 'offline')
                path = directory / 'resume.draft.json'
                os.utime(path, ns=(1_000_000_000, 1_000_000_000))
                draft_resume(workspace, 'run1', 'offline')
            self.assertEqual(path.stat().st_mtime_ns, 1_000_000_000)

    def test_unknown_projects_appear_as_grouped_pending_candidates_after_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            directory = self.prepare(workspace)
            path = directory / 'facts.json'
            bundle = read_json(path)
            bundle['facts'].extend([
                {'id': 'p1', 'field': 'project', 'value': 'WeatherAgent',
                 'source': 'weather.md', 'status': 'source_text', 'ownership': 'unknown'},
                {'id': 'p2', 'field': 'project', 'value': '支持天气查询',
                 'source': 'weather.md', 'status': 'source_text', 'ownership': 'unknown'},
                {'id': 'p3', 'field': 'project', 'value': 'OCR 项目',
                 'source': 'ocr.pdf', 'status': 'ocr_unverified', 'ownership': 'unknown'}])
            write_json(path, bundle)
            extracted = read_json(directory / 'extracted.json')
            extracted['segments'].append({'id': 's2', 'source': 'weather.md', 'method': 'text',
                'text': '项目名称 WeatherAgent\n## 来源文件 README.md\n# 天气助手\n支持天气查询'})
            write_json(directory / 'extracted.json', extracted)
            with patch('resume_flow.workflow.DeepSeekClient') as client:
                client.return_value.complete.return_value = self.output
                draft_resume(workspace, 'run1')
                payload = client.return_value.complete.call_args.args[1]
                self.assertFalse(any(f['field'] == 'project' for f in payload['facts']))
            resume = read_json(directory / 'resume.draft.json')
            self.assertEqual([s['title'] for s in resume['sections']], ['专业技能', '项目经历'])
            projects = resume['sections'][1]['items']
            self.assertEqual(len(projects), 1)
            self.assertEqual(projects[0]['title'], '天气助手')
            self.assertEqual(projects[0]['paragraphs'], ['支持天气查询'])
            self.assertEqual(projects[0]['fact_ids'], ['p1', 'p2'])
            self.assertTrue(projects[0]['pending_contribution'])
            self.assertEqual(read_json(path), bundle)

    def test_old_semantic_checkpoint_is_rebuilt(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            directory = self.prepare(workspace)
            manifest = read_json(directory / 'manifest.json')
            write_json(directory / 'resume.draft.json', {'old': True})
            from resume_flow.storage import file_hash
            fingerprint = digest({'version': 1, 'facts': read_json(directory / 'facts.json'),
                'config': manifest['config'], 'mode': 'deepseek', 'prompt': prompts.DRAFT,
                'model': os.environ.get('DEEPSEEK_MODEL', 'deepseek-flash')})
            write_json(directory / 'model-draft.json', {'fingerprint': fingerprint,
                'output_sha256': file_hash(directory / 'resume.draft.json')})
            with patch('resume_flow.workflow.DeepSeekClient') as client:
                client.return_value.complete.return_value = self.output
                draft_resume(workspace, 'run1')
                client.return_value.complete.assert_called_once()


if __name__ == '__main__':
    unittest.main()
