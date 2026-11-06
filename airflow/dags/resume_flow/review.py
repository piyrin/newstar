"""Explicit, content-bound human review. Local HTTP UI never calls a model."""
import hmac
import copy
import json
import re
import secrets
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .storage import digest, file_hash, inside, read_json, review_dir, run_dir, verify_sources, write_json
from .workflow import validate_resume
from .vendor import build_resume as renderer
from .drafts import ensure_active


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_selection(value):
    if not isinstance(value, dict) or value.get('schema_version') != 1:
        raise ValueError('请先选择模板')
    for key, choices in [('template_id', ('classic', 'minimal', 'technical')),
                         ('mode', ('print', 'digital')), ('paper', ('A4', 'Letter'))]:
        if value.get(key) not in choices:
            raise ValueError('模板选择无效：' + key)


def prepare_review(workspace: Path, run_key: str) -> str:
    directory, target = run_dir(workspace, run_key), review_dir(workspace, run_key)
    bundle = read_json(directory / 'facts.json')
    target.mkdir(parents=True, exist_ok=True)
    # Retries must not erase a user's edits or decisions.
    for name, data in [('resume.json', read_json(directory / 'resume.draft.json')),
                       ('questions.json', bundle['questions'])]:
        if not (target / name).exists():
            write_json(target / name, data)
    lines = ['# 待确认项', '', '请在本机审阅页处理问题；此文件只作阅读。', '']
    lines.extend(f"- {q['id']}：{q['text']}" for q in bundle['questions'])
    (directory / 'questions.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    facts = ['# 事实与来源', '']
    facts.extend(f"- {f['id']} [{f['field']}] {f['value']}\n  来源：{f['source']} / {f['location']}\n  原文：{f['quote']}\n  状态：{f['status']}；归属：{f['ownership']}"
                 for f in bundle['facts'])
    (directory / 'facts.md').write_text('\n'.join(facts) + '\n', encoding='utf-8')
    write_json(directory / 'status.json', {'state': 'waiting_input' if bundle['questions'] else 'waiting_review',
                                          'synthetic': bundle['synthetic']})
    return run_key


def current_state(workspace, run_key):
    ensure_active(workspace, run_key)
    folder = review_dir(workspace, run_key)
    bundle = read_json(run_dir(workspace, run_key) / 'facts.json')
    state = {'run_key': run_key, 'synthetic': bundle['synthetic'], 'facts': bundle['facts'],
             'resume': read_json(folder / 'resume.json'), 'questions': read_json(folder / 'questions.json'),
             'selection': read_json(folder / 'selection.json') if (folder / 'selection.json').exists() else None}
    # Keep the original revision format compatible with already-open reviews.
    if state['resume'].get('photo') == 'photo.jpg':
        state['photo_hash'] = file_hash(folder / 'photo.jpg')
    state['revision'] = digest(state)
    state['question_groups'] = question_groups(state['questions'], state['facts'])
    state['form_fields'] = form_fields(state['resume'])
    return state


def question_groups(questions, facts):
    by_id = {fact['id']: fact for fact in facts}
    grouped = {}
    for question in questions:
        related = [by_id[fid] for fid in question['fact_ids'] if fid in by_id]
        sources = tuple(sorted({fact['source'] for fact in related}))
        text = question['text']
        material = re.match(r'^材料问题[：:]\s*(.+?)[：:]', text)
        if material and not sources:
            sources = (material[1],)
        kind = 'material' if material else 'ocr' if 'OCR' in text or '对照原图' in text else text
        key = (kind, sources)
        if key not in grouped:
            source = '、'.join(sources)
            grouped[key] = {'id': question['id'], 'text': question['text'], 'source': source,
                            'sourcefile': source, 'question_ids': [], 'questions': [],
                            'fact_ids': [], 'facts': [], 'messages': []}
        group = grouped[key]
        if text not in group['messages']:
            group['messages'].append(text)
        group['question_ids'].append(question['id'])
        group['questions'].append(question)
        for fact in related:
            if fact['id'] not in group['fact_ids']:
                group['fact_ids'].append(fact['id'])
                group['facts'].append(fact)
    for group in grouped.values():
        for field in ('resolution', 'note'):
            values = {question.get(field, '') for question in group['questions']}
            group[field] = next(iter(values)) if len(values) == 1 else ''
    return list(grouped.values())


def contact_field(contact):
    label = contact.get('label', '').lower()
    if label in ('邮箱', '电子邮箱', 'email', 'e-mail'):
        return 'email'
    if label in ('电话', '手机', '联系电话', '手机号', 'phone', 'mobile'):
        return 'phone'
    if label in ('主页', '个人主页', '网站', 'website', 'homepage'):
        return 'website'
    if label in ('意向', '意向城市', '期望城市', 'location'):
        return 'location'
    return None


EDUCATION_FIELDS = ('school', 'college', 'major', 'degree', 'start', 'end', 'gpa', 'courses')


def education_item(resume):
    sections = [section for section in resume.get('sections', [])
                if section.get('title', '').strip() in ('教育背景', '教育经历', 'Education')]
    for section in sections:
        for item in section.get('items', []):
            if isinstance(item.get('education_fields'), dict):
                return section, item
    for section in sections:
        if section.get('items'):
            return section, section['items'][0]
    return (sections[0] if sections else None), None


def education_values(item):
    fields = dict.fromkeys(EDUCATION_FIELDS, '')
    if item is None:
        return fields
    explicit = item.get('education_fields', item)
    for key in fields:
        if isinstance(explicit.get(key), str):
            fields[key] = explicit[key]
    if 'education_fields' in item:
        return fields
    # Older drafts store free text. Extract only explicit labelled values.
    labels = {'学校': 'school', '院校': 'school', '学院': 'college', '专业': 'major',
              '学历': 'degree', '学位': 'degree', '入学时间': 'start', '毕业时间': 'end',
              '预计毕业': 'end', 'GPA': 'gpa', '主修课程': 'courses'}
    for line in item.get('paragraphs', []):
        match = re.fullmatch(r'\s*([^：:]+)[：:]\s*(.*?)\s*', line)
        if match and match[1] in labels and not fields[labels[match[1]]]:
            fields[labels[match[1]]] = match[2]
    title = item.get('title', '')
    if not fields['school'] and re.search(r'(大学|学院|学校|University|College)$', title):
        fields['school'] = title
    return fields


def form_fields(resume):
    values = {'website': '', 'location': ''}
    for contact in resume.get('contact', []):
        field = contact_field(contact)
        if field in values and not values[field]:
            values[field] = contact.get('value', '')
    values['availability'] = '\n'.join(resume.get('availability', []))
    values['education'] = education_values(education_item(resume)[1])
    return values


def apply_education(resume, manual):
    section, item = education_item(resume)
    fields = education_values(item)
    updated = dict(fields, **{key: value.strip() for key, value in manual.items()})
    if updated == fields:
        return
    if not any(updated.values()):
        if item is not None:
            section['items'].remove(item)
            if not section['items']:
                resume['sections'].remove(section)
        return
    if section is None:
        section = {'title': '教育背景', 'items': []}
        resume.setdefault('sections', []).insert(0, section)
    if item is None:
        item = {}
        section['items'].insert(0, item)
    title = updated['school']
    date = ' — '.join(value for value in (updated['start'], updated['end']) if value)
    details = ' · '.join(updated[key] for key in ('college', 'major', 'degree') if updated[key])
    paragraphs = [details] if details else []
    if updated['gpa']:
        paragraphs.append('GPA ' + updated['gpa'])
    if updated['courses']:
        paragraphs.append('主修课程 ' + updated['courses'])
    if not paragraphs:
        paragraphs = [title or date]
        if title:
            title = ''
        else:
            date = ''
    item.update(title=title, subtitle='', date=date, paragraphs=paragraphs,
                education_fields=updated, fact_ids=[], user_entered=True)


def apply_manual_inputs(previous, resume, manual):
    allowed = ('name', 'email', 'phone', 'headline', 'website', 'location', 'availability', 'education')
    if not isinstance(manual, dict) or any(key not in allowed for key in manual):
        raise ValueError('手填信息结构无效')
    if any(not isinstance(value, str) for key, value in manual.items() if key != 'education'):
        raise ValueError('手填信息必须是文字，留空请填写空字符串')
    if 'education' in manual:
        education = manual['education']
        if (not isinstance(education, dict) or any(key not in EDUCATION_FIELDS for key in education)
                or any(not isinstance(value, str) for value in education.values())):
            raise ValueError('教育信息结构无效，字段必须是文字')
    for field in ('name', 'headline'):
        if field in manual:
            resume[field] = manual[field].strip()
        if resume.get(field) != previous.get(field):
            resume[field + '_user_entered'] = True
            if field == 'name':
                resume['name_fact_ids'] = []
        elif field == 'name':
            resume['name_fact_ids'] = previous.get('name_fact_ids', [])
    contacts = resume.get('contact', [])
    if not isinstance(contacts, list) or any(not isinstance(c, dict) for c in contacts):
        raise ValueError('联系方式结构无效')
    for field, label in [('email', '邮箱'), ('phone', '电话'), ('website', '主页'), ('location', '意向')]:
        if field not in manual:
            continue
        existing = next((c for c in contacts if contact_field(c) == field), {})
        contacts = [c for c in contacts if contact_field(c) != field]
        value = manual[field].strip()
        if value:
            contact = dict(existing, label=existing.get('label', label), value=value)
            if value != existing.get('value'):
                contact.pop('url', None)
            contacts.append(contact)
    for contact in contacts:
        old = next((c for c in previous.get('contact', [])
                    if c.get('value') == contact.get('value') and c.get('label') == contact.get('label')), None)
        if old is not None:
            contact['fact_ids'] = old.get('fact_ids', [])
        else:
            contact.update(fact_ids=[], user_entered=True)
    resume['contact'] = contacts
    if 'availability' in manual:
        resume['availability'] = [line.strip() for line in manual['availability'].splitlines() if line.strip()]
        if resume['availability'] != previous.get('availability', []):
            resume['availability_user_entered'] = True
    if 'education' in manual:
        apply_education(resume, manual['education'])


def save_review(workspace, run_key, payload):
    state = current_state(workspace, run_key)
    if payload.get('revision') != state['revision']:
        raise ValueError('审阅内容已变化，请刷新页面后再保存')
    if not isinstance(payload.get('resume'), dict) or not isinstance(payload.get('questions'), list):
        raise ValueError('审阅数据结构无效')
    questions = copy.deepcopy(payload['questions'])
    resume = copy.deepcopy(payload['resume'])
    apply_manual_inputs(state['resume'], resume, payload.get('manual_inputs', {}))
    bundle = read_json(run_dir(workspace, run_key) / 'facts.json')
    baseline = bundle['questions']
    if len(questions) != len(baseline):
        raise ValueError('不可删除待确认问题，请选择核实或省略')
    for original, item in zip(baseline, questions):
        if not isinstance(item, dict):
            raise ValueError('问题处理方式无效')
        if any(item.get(k) != original[k] for k in ('id', 'text', 'fact_ids')):
            raise ValueError('不可替换原始问题或关联事实')
        if item.get('resolution') not in ('', 'confirmed', 'omitted') or not isinstance(item.get('note'), str):
            raise ValueError('问题处理方式无效')
        if original['text'] == '缺少联系方式，请补充至少一种联系方式。' and not original['fact_ids']:
            has_contact = any(str(c.get('value', '')).strip() for c in resume['contact'])
            item['resolution'] = 'confirmed' if has_contact else 'omitted'
            choices = ('用户选择填写联系方式。', '用户选择暂留空，稍后自行填写联系方式。')
            # Retain any old user explanation without accumulating generated notes on retries.
            notes = [line for line in item['note'].splitlines() if line not in choices]
            item['note'] = '\n'.join([choices[0] if has_contact else choices[1], *notes])
        elif item['resolution'] == 'confirmed' and not item['note'].strip():
            item['note'] = '用户已明确核实本项列示的相关事实及本人贡献。' if '个人贡献' in item['text'] else '用户已明确核实本项列示的相关事实。'
    # Confirming repository facts must also adopt a missing project into the
    # body. Re-saving an already confirmed review preserves deliberate removal.
    from .project_edit import adopt_project_items, group_project_facts
    previous = {question['id']: question for question in state['questions']}
    changed = {fid for question in questions if question['resolution'] == 'confirmed'
               and previous[question['id']].get('resolution') != 'confirmed'
               for fid in question['fact_ids']}
    confirmed = {fid for question in questions if question['resolution'] == 'confirmed'
                 for fid in question['fact_ids']}
    omitted = {fid for question in questions if question['resolution'] == 'omitted'
               for fid in question['fact_ids']}
    confirmed -= omitted
    projects = [group for group in group_project_facts(bundle['facts'])
                if any(fact['id'] in changed for fact in group)
                and all(fact['id'] in confirmed for fact in group)]
    if projects:
        segments = read_json(run_dir(workspace, run_key) / 'extracted.json')['segments']
        sources = {fact['source'] for group in projects for fact in group}
        texts = {source: '\n'.join(segment['text'] for segment in segments if segment['source'] == source)
                 for source in sources}
        resume = adopt_project_items(resume, [fact for group in projects for fact in group], texts)
    for section in resume['sections']:
        for item in section['items']:
            if item.get('pending_contribution') and set(item.get('fact_ids', [])).issubset(confirmed):
                item.pop('pending_contribution', None)
    validate_selection(payload.get('selection'))
    folder = review_dir(workspace, run_key)
    write_json(folder / 'resume.json', resume)
    write_json(folder / 'questions.json', questions)
    write_json(folder / 'selection.json', payload['selection'])
    return current_state(workspace, run_key)


def approval_content(workspace, run_key):
    ensure_active(workspace, run_key)
    manifest = verify_sources(workspace, run_key)
    directory, folder = run_dir(workspace, run_key), review_dir(workspace, run_key)
    files = [directory / 'extracted.json', directory / 'facts.json', directory / 'resume.draft.json',
             folder / 'resume.json', folder / 'questions.json', folder / 'selection.json']
    if read_json(folder / 'resume.json').get('photo') == 'photo.jpg':
        files.append(folder / 'photo.jpg')
    try:
        hashes = {p.name + ('/review' if p.parent == folder else '/run'): file_hash(p) for p in files}
    except FileNotFoundError:
        raise ValueError('审阅文件或模板选择缺失') from None
    return {'snapshot_hash': manifest['snapshot_hash'], 'hashes': hashes,
            'template_version': renderer.TEMPLATE_VERSION}


def approve(workspace: Path, run_key: str):
    folder = review_dir(workspace, run_key)
    before = approval_content(workspace, run_key)
    state = current_state(workspace, run_key)
    validate_resume(state['resume'])
    validate_selection(state['selection'])
    baseline = read_json(run_dir(workspace, run_key) / 'facts.json')['questions']
    questions = state['questions']
    if [q['id'] for q in questions] != [q['id'] for q in baseline]:
        raise ValueError('待确认清单被删改，请保留全部问题')
    for original, item in zip(baseline, questions):
        if any(item.get(k) != original[k] for k in ('text', 'fact_ids')):
            raise ValueError('问题原文或事实关联被修改')
        if item.get('resolution') not in ('confirmed', 'omitted'):
            raise ValueError('请逐项核实或省略')
        if item['resolution'] == 'omitted':
            if not item.get('note', '').strip():
                raise ValueError('省略问题时请填写原因')
            omitted = set(item['fact_ids'])
            if omitted.intersection(state['resume'].get('name_fact_ids', [])):
                raise ValueError('姓名仍引用已省略的事实，请先修改姓名及其来源')
            facts = {f['id']: f for f in state['facts']}
            for fid in omitted:
                fact = facts.get(fid)
                if fact and fact['field'] == 'name' and state['resume']['name'] == fact['value']:
                    raise ValueError('已省略的姓名仍出现在正文')
                if fact and fact['field'] in ('email', 'phone'):
                    if any(c.get('value') == fact['value'] for c in state['resume']['contact']):
                        raise ValueError('已省略的联系方式仍出现在正文')
            for contact in state['resume']['contact']:
                if omitted.intersection(contact.get('fact_ids', [])):
                    raise ValueError('联系方式仍引用已省略的事实')
            for section in state['resume']['sections']:
                for entry in section['items']:
                    if omitted.intersection(entry.get('fact_ids', [])):
                        raise ValueError('正文仍引用已省略的事实，请先移除相关内容')
    if before != approval_content(workspace, run_key):
        raise ValueError('确认期间内容发生变化，请重试')
    record = {'schema_version': 1, 'content_hash': digest(before), 'approved_at': now(),
              'synthetic': state['synthetic'], 'statement': '本人已核实正文及问题处理，确认模板，允许导出。'}
    write_json(folder / 'approval.json', record)
    return record


def verify_approval(workspace: Path, run_key: str):
    path = review_dir(workspace, run_key) / 'approval.json'
    if not path.exists():
        raise ValueError('尚未明确确认正文与模板，不能导出')
    record = read_json(path)
    if record.get('content_hash') != digest(approval_content(workspace, run_key)):
        raise ValueError('材料、正文、问题处理或模板已变化，请重新确认')
    return record


def get_status(workspace, run_key):
    bundle = read_json(run_dir(workspace, run_key) / 'facts.json')
    questions = read_json(review_dir(workspace, run_key) / 'questions.json')
    pending = sum(q.get('resolution') not in ('confirmed', 'omitted') or
                  (q.get('resolution') == 'omitted' and not q.get('note', '').strip())
                  for q in questions)
    status = {'state': 'waiting_input' if pending else 'waiting_review',
              'run_key': run_key, 'synthetic': bundle['synthetic'], 'pending_questions': pending}
    try:
        approval = verify_approval(workspace, run_key)
    except (ValueError, OSError):
        return status
    status['state'] = 'approved'
    outputs = inside(workspace, 'outputs')
    reports = sorted(outputs.glob('*/report.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in reports:
        if not path.resolve().is_relative_to(outputs.resolve()):
            continue
        if not (path.parent / 'input.json').exists():
            continue
        inputs = read_json(path.parent / 'input.json')
        if inputs.get('run_key') != run_key or inputs.get('approval_hash') != approval['content_hash']:
            continue
        report = read_json(path)
        status.update({'state': report['state'], 'export_key': path.parent.name})
        accepted = path.parent / 'visual-acceptance.json'
        if accepted.exists() and read_json(accepted).get('report_hash') == digest(report):
            hashes = report.get('artifact_hashes', {})
            if hashes and all(file_hash(inside(path.parent, name)) == expected for name, expected in hashes.items()):
                status['state'] = 'final'
            else:
                status['state'] = 'failed'
        break
    return status


def make_server(workspace: Path, run_key: str, port=0):
    current_state(workspace, run_key)
    from .portal import make_portal
    return make_portal(workspace, port=port, fixed_run_key=run_key)
