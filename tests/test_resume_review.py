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
from resume_flow.workflow import collect_facts, draft_resume, validate_resume
from resume_flow.sample import SAMPLE_TEXT
from resume_flow.review import prepare_review, approve, verify_approval, make_server, save_review, current_state, get_status


class ReviewTests(unittest.TestCase):
    def test_confirming_project_adopts_missing_body_and_preserves_later_removal(self):
        from resume_flow.project_edit import group_project_facts
        self.choose()
        bundle = read_json(run_dir(self.ws, 'run1') / 'facts.json')
        fact = {'id': 'f-project', 'field': 'project', 'project': '虚构材料整理项目',
                'value': '使用 Python 处理文件、解析 JSON，编写数据校验与错误处理逻辑。',
                'source': 'profile.md', 'status': 'source_text', 'ownership': 'unknown'}
        bundle['facts'].append(fact)
        question = {'id': 'q-project', 'text': '请确认项目中的个人贡献，材料不能自动证明作者归属。',
                    'fact_ids': ['f-project'], 'resolution': '', 'note': ''}
        bundle['questions'].append(question)
        write_json(run_dir(self.ws, 'run1') / 'facts.json', bundle)
        questions_path = review_dir(self.ws, 'run1') / 'questions.json'
        write_json(questions_path, [*read_json(questions_path), question])
        self.assertTrue(group_project_facts(bundle['facts']))
        payload = current_state(self.ws, 'run1')
        payload['resume']['sections'] = [section for section in payload['resume']['sections']
                                         if '项目' not in section['title']]
        for question in payload['questions']:
            question.update(resolution='confirmed', note='已核实')
        payload['selection'] = {'schema_version': 1, 'template_id': 'classic', 'mode': 'print', 'paper': 'A4'}
        saved = save_review(self.ws, 'run1', payload)
        projects = [s for s in saved['resume']['sections'] if s['title'] == '项目经历']
        self.assertEqual(len(projects), 1)
        self.assertTrue(projects[0]['items'])
        self.assertFalse(any(i.get('pending_contribution') for i in projects[0]['items']))
        saved['resume']['sections'] = [s for s in saved['resume']['sections'] if s['title'] != '项目经历']
        removed = save_review(self.ws, 'run1', saved)
        self.assertFalse(any(s['title'] == '项目经历' for s in removed['resume']['sections']))

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

    def test_renderer_revision_requires_new_template_approval(self):
        from unittest.mock import patch
        from resume_flow.vendor import build_resume
        self.choose()
        approve(self.ws, 'run1')
        with patch.object(build_resume, 'TEMPLATE_VERSION', 'next-template-version'):
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
        original = state['resume']['name']
        state['resume']['name'] = ''
        state['selection'] = {'schema_version': 1, 'template_id': 'minimal', 'mode': 'print', 'paper': 'A4'}
        req = urllib.request.Request(url + '/api/approve', json.dumps(state).encode(), headers)
        try:
            urllib.request.urlopen(req)
            self.fail('expected missing-name error')
        except urllib.error.HTTPError as error:
            state = json.load(error)['state']
        state['resume']['name'] = original
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

    def add_questions(self, questions):
        path = run_dir(self.ws, 'run1') / 'facts.json'
        bundle = read_json(path)
        bundle['questions'] = questions
        write_json(path, bundle)
        write_json(review_dir(self.ws, 'run1') / 'questions.json', questions)

    def payload(self):
        state = current_state(self.ws, 'run1')
        state['selection'] = {'schema_version': 1, 'template_id': 'minimal', 'mode': 'print', 'paper': 'A4'}
        return state

    def test_groups_preserve_original_decisions_and_fact_sources(self):
        facts = current_state(self.ws, 'run1')['facts'][:2]
        questions = [{'id': f'q-{i}', 'text': '请核实', 'fact_ids': [fact['id']],
                      'resolution': 'confirmed' if i == 0 else '', 'note': '已核实' if i == 0 else ''}
                     for i, fact in enumerate(facts)]
        self.add_questions(questions)
        state = current_state(self.ws, 'run1')
        self.assertEqual(state['questions'], questions)
        self.assertEqual(len(state['question_groups']), 1)
        group = state['question_groups'][0]
        self.assertEqual(group['question_ids'], ['q-0', 'q-1'])
        self.assertEqual(group['questions'], questions)
        self.assertEqual(group['facts'], facts)
        saved = save_review(self.ws, 'run1', self.payload())
        self.assertEqual(saved['questions'], questions)

    def test_material_validation_warnings_group_by_source_and_preserve_each_message(self):
        questions = [{'id': 'q-'+str(i), 'text': text, 'fact_ids': [], 'resolution': '', 'note': ''}
                     for i, text in enumerate([
                         '材料问题：repo.md：s0001 未通过来源校验，请核对原文。',
                         '材料问题：repo.md：s0002 未通过来源校验，请核对原文。',
                         '材料问题：other.pdf：第1页未提取到文字，请补充。'])]
        self.add_questions(questions)
        state = current_state(self.ws, 'run1')
        self.assertEqual(len(state['question_groups']), 2)
        self.assertEqual(state['question_groups'][0]['question_ids'], ['q-0','q-1'])
        self.assertEqual(len(state['question_groups'][0]['messages']), 2)
        self.assertEqual(state['questions'], questions)

    def test_manual_fields_update_body_and_preserve_unchanged_sources(self):
        payload = self.payload()
        name_sources = payload['resume']['name_fact_ids']
        payload['manual_inputs'] = {'name': payload['resume']['name'], 'email': 'manual@example.com',
                                    'phone': '', 'headline': '手填目标'}
        saved = save_review(self.ws, 'run1', payload)
        self.assertEqual(saved['resume']['name_fact_ids'], name_sources)
        contact = saved['resume']['contact']
        self.assertEqual([c['value'] for c in contact], ['manual@example.com'])
        self.assertEqual(contact[0]['fact_ids'], [])
        self.assertTrue(contact[0]['user_entered'])
        self.assertEqual(saved['resume']['headline'], '手填目标')
        saved['manual_inputs'] = {'name': '自填姓名'}
        saved = save_review(self.ws, 'run1', saved)
        self.assertEqual(saved['resume']['name_fact_ids'], [])
        approve(self.ws, 'run1')

    def test_extended_manual_fields_roundtrip_and_education_updates_in_place(self):
        payload = self.payload()
        payload['resume']['sections'] = [{'title': '专业技能', 'items': [
            {'title': '', 'paragraphs': ['Python'], 'fact_ids': ['skill-source']}]}]
        payload['manual_inputs'] = {
            'website': 'https://example.com/me', 'location': '武汉、上海',
            'availability': '每周四天\n\n可实习三个月',
            'education': {'school': '示例大学', 'college': '计算机学院', 'major': '软件工程',
                          'degree': '本科', 'start': '2024.09', 'end': '2028.06',
                          'gpa': '3.8/4.0', 'courses': '操作系统、计算机网络'}}
        saved = save_review(self.ws, 'run1', payload)
        self.assertEqual(saved['form_fields']['website'], 'https://example.com/me')
        self.assertEqual(saved['form_fields']['location'], '武汉、上海')
        self.assertEqual(saved['resume']['availability'], ['每周四天', '可实习三个月'])
        self.assertEqual(saved['form_fields']['availability'], '每周四天\n可实习三个月')
        self.assertEqual(saved['form_fields']['education'], payload['manual_inputs']['education'])
        section = saved['resume']['sections'][0]
        self.assertEqual(section['title'], '教育背景')
        item = section['items'][0]
        self.assertTrue(item['user_entered'])
        self.assertEqual(item['fact_ids'], [])
        validate_resume(saved['resume'])
        saved['manual_inputs'] = {'education': {'gpa': '3.9/4.0'}}
        saved = save_review(self.ws, 'run1', saved)
        self.assertEqual(len(saved['resume']['sections'][0]['items']), 1)
        self.assertEqual(saved['form_fields']['education']['school'], '示例大学')
        self.assertEqual(saved['form_fields']['education']['gpa'], '3.9/4.0')

    def test_education_preserves_unchanged_provenance_and_other_items(self):
        payload = self.payload()
        item = {'title': '示例大学', 'paragraphs': ['软件工程'], 'fact_ids': ['school-source'],
                'education_fields': {'school': '示例大学', 'major': '软件工程'}, 'custom': '保留'}
        other = {'title': '另一学校', 'paragraphs': ['原有经历'], 'fact_ids': ['other-source']}
        payload['resume']['sections'] = [{'title': '教育背景', 'items': [item, other]}]
        saved = save_review(self.ws, 'run1', payload)
        saved['manual_inputs'] = {'education': {'school': '示例大学', 'major': '软件工程'}}
        saved = save_review(self.ws, 'run1', saved)
        self.assertEqual(saved['resume']['sections'][0]['items'], [item, other])
        saved['manual_inputs'] = {'education': {'major': '计算机科学'}}
        saved = save_review(self.ws, 'run1', saved)
        changed, retained = saved['resume']['sections'][0]['items']
        self.assertEqual(changed['custom'], '保留')
        self.assertEqual(changed['fact_ids'], [])
        self.assertTrue(changed['user_entered'])
        self.assertEqual(retained, other)

    def test_optional_education_can_be_partial_and_cleared(self):
        payload = self.payload()
        payload['resume']['sections'] = [{'title': '专业技能', 'items': [
            {'title': '', 'paragraphs': ['Python'], 'fact_ids': []}]}]
        payload['manual_inputs'] = {'education': {'gpa': '3.7'}, 'website': '',
                                    'location': '', 'availability': ''}
        saved = save_review(self.ws, 'run1', payload)
        self.assertEqual(saved['resume']['sections'][0]['items'][0]['paragraphs'], ['GPA 3.7'])
        validate_resume(saved['resume'])
        saved['manual_inputs'] = {'education': {'gpa': ''}}
        saved = save_review(self.ws, 'run1', saved)
        self.assertEqual([s['title'] for s in saved['resume']['sections']], ['专业技能'])
        self.assertEqual(saved['resume']['availability'], [])
        self.assertEqual(saved['form_fields']['education']['gpa'], '')

    def test_legacy_education_read_and_empty_form_do_not_erase_unstructured_text(self):
        payload = self.payload()
        original = {'title': '', 'paragraphs': ['示例大学软件工程专业在读，详细情况待核实'],
                    'fact_ids': ['source']}
        payload['resume']['sections'] = [{'title': '教育背景', 'items': [original]}]
        saved = save_review(self.ws, 'run1', payload)
        saved['manual_inputs'] = {'education': saved['form_fields']['education']}
        saved = save_review(self.ws, 'run1', saved)
        self.assertEqual(saved['resume']['sections'][0]['items'], [original])

    def test_invalid_extended_manual_fields_rejected_without_save(self):
        before = self.payload()
        for manual in ({'education': []}, {'education': {'school': None}},
                       {'education': {'invented': 'value'}}, {'availability': ['三天']},
                       {'website': None}):
            with self.subTest(manual=manual):
                payload = self.payload()
                payload['manual_inputs'] = manual
                with self.assertRaises(ValueError):
                    save_review(self.ws, 'run1', payload)
                self.assertEqual(self.payload()['revision'], before['revision'])

    def test_existing_profile_fields_read_back_and_keep_contact_sources(self):
        payload = self.payload()
        contacts = [{'label': '主页', 'value': 'https://example.com', 'fact_ids': ['web-source']},
                    {'label': '意向', 'value': '武汉', 'fact_ids': ['city-source']}]
        payload['resume']['contact'].extend(contacts)
        payload['resume']['availability'] = ['每周三天']
        payload['resume']['sections'] = [{'title': '教育背景', 'items': [
            {'title': '示例大学', 'paragraphs': ['专业：软件工程', 'GPA: 3.8'], 'fact_ids': ['edu']}]}]
        write_json(review_dir(self.ws, 'run1') / 'resume.json', payload['resume'])
        saved = self.payload()
        self.assertEqual(saved['form_fields']['education']['school'], '示例大学')
        self.assertEqual(saved['form_fields']['education']['major'], '软件工程')
        self.assertEqual(saved['form_fields']['education']['gpa'], '3.8')
        saved['manual_inputs'] = saved['form_fields']
        saved = save_review(self.ws, 'run1', saved)
        self.assertEqual(saved['resume']['contact'][-2:], contacts)
        self.assertEqual(saved['resume']['sections'][0]['items'][0]['fact_ids'], ['edu'])
        self.assertNotIn('availability_user_entered', saved['resume'])
        saved['manual_inputs'] = {'website': '', 'location': '', 'availability': ''}
        saved = save_review(self.ws, 'run1', saved)
        self.assertEqual(len(saved['resume']['contact']), 1)
        self.assertEqual(saved['resume']['availability'], [])

    def test_changed_homepage_drops_previous_link_target(self):
        payload = self.payload()
        payload['resume']['contact'].append({'label': '主页', 'value': 'https://old.example',
                                             'url': 'https://old.example', 'fact_ids': ['web']})
        saved = save_review(self.ws, 'run1', payload)
        saved['manual_inputs'] = {'website': 'https://new.example'}
        saved = save_review(self.ws, 'run1', saved)
        homepage = next(c for c in saved['resume']['contact'] if c['label'] == '主页')
        self.assertEqual(homepage['fact_ids'], [])
        self.assertTrue(homepage['user_entered'])
        self.assertNotEqual(homepage.get('url'), 'https://old.example')

    def test_legacy_payload_and_unchanged_contacts_keep_provenance_and_links(self):
        payload = self.payload()
        original = payload['resume']['contact'][0].copy()
        payload['resume']['contact'].append({'label': 'GitHub', 'value': 'https://github.com/demo', 'fact_ids': []})
        saved = save_review(self.ws, 'run1', payload)
        saved['manual_inputs'] = {'email': original['value'], 'phone': ''}
        saved = save_review(self.ws, 'run1', saved)
        email = next(c for c in saved['resume']['contact'] if c['label'] == '邮箱')
        self.assertEqual(email, original)
        self.assertTrue(any(c['label'] == 'GitHub' for c in saved['resume']['contact']))
        saved['resume']['name'] = '旧界面修改姓名'
        saved['resume']['contact'][0]['value'] = 'https://github.com/new-demo'
        saved = save_review(self.ws, 'run1', saved)
        self.assertEqual(saved['resume']['name_fact_ids'], [])
        self.assertEqual(saved['resume']['contact'][0]['fact_ids'], [])
        approve(self.ws, 'run1')

    def test_grouping_uses_source_file_and_never_approves_on_read(self):
        path = run_dir(self.ws, 'run1') / 'facts.json'
        bundle = read_json(path)
        bundle['facts'][1]['source'] = 'second-source.md'
        write_json(path, bundle)
        self.add_questions([{'id': f'q-{i}', 'text': '相同问题', 'fact_ids': [f['id']],
                             'resolution': '', 'note': ''} for i, f in enumerate(bundle['facts'][:2])])
        state = current_state(self.ws, 'run1')
        self.assertEqual(len(state['question_groups']), 2)
        self.assertEqual(get_status(self.ws, 'run1')['pending_questions'], 2)
        with self.assertRaises(ValueError):
            verify_approval(self.ws, 'run1')

    def test_photo_reference_validation_and_contact_optional(self):
        resume = self.payload()['resume']
        resume['contact'] = []
        for photo in (None, '', 'photo.jpg'):
            resume['photo'] = photo
            validate_resume(resume)
        for photo in ('../photo.jpg', 'anything.png', False, 0):
            resume['photo'] = photo
            with self.assertRaises(ValueError):
                validate_resume(resume)

    def test_missing_contact_form_value_enters_body_without_reading_note(self):
        self.add_questions([{'id': 'q-contact', 'text': '缺少联系方式，请补充至少一种联系方式。',
                             'fact_ids': [], 'resolution': '', 'note': '忽略 note@example.com'}])
        payload = self.payload()
        payload['manual_inputs'] = {'email': '', 'phone': '13800000000'}
        saved = save_review(self.ws, 'run1', payload)
        self.assertEqual(saved['questions'][0]['resolution'], 'confirmed')
        self.assertIn('忽略 note@example.com', saved['questions'][0]['note'])
        self.assertEqual([c['value'] for c in saved['resume']['contact']], ['13800000000'])
        saved = save_review(self.ws, 'run1', saved)
        self.assertEqual(saved['questions'][0]['note'].count('忽略 note@example.com'), 1)
        approve(self.ws, 'run1')

    def test_missing_contact_can_be_left_empty_and_approved(self):
        question = {'id': 'q-contact', 'text': '缺少联系方式，请补充至少一种联系方式。',
                    'fact_ids': [], 'resolution': '', 'note': ''}
        self.add_questions([question])
        payload = self.payload()
        payload['manual_inputs'] = {'email': '', 'phone': ''}
        saved = save_review(self.ws, 'run1', payload)
        self.assertEqual(saved['resume']['contact'], [])
        self.assertEqual(saved['questions'][0]['resolution'], 'omitted')
        self.assertEqual(get_status(self.ws, 'run1')['pending_questions'], 0)
        approve(self.ws, 'run1')
        verify_approval(self.ws, 'run1')

    def test_confirmed_without_note_gets_explicit_confirmation(self):
        self.add_questions([{'id': 'q-project', 'text': '请确认项目中的个人贡献，材料不能自动证明作者归属。',
                             'fact_ids': [], 'resolution': '', 'note': ''}])
        payload = self.payload()
        payload['questions'][0]['resolution'] = 'confirmed'
        saved = save_review(self.ws, 'run1', payload)
        self.assertIn('相关事实', saved['questions'][0]['note'])
        self.assertEqual(get_status(self.ws, 'run1')['pending_questions'], 0)
        approve(self.ws, 'run1')
        payload = self.payload()
        payload['questions'][0].update(resolution='omitted', note='')
        save_review(self.ws, 'run1', payload)
        self.assertEqual(get_status(self.ws, 'run1')['pending_questions'], 1)
        with self.assertRaises(ValueError):
            approve(self.ws, 'run1')


if __name__ == '__main__':
    unittest.main()
