"""Evidence collection, validation, and editable resume drafts."""
import re
from pathlib import Path

from . import prompts
from .llm import DeepSeekClient
from .storage import digest, read_json, run_dir, verify_sources, write_json

FIELDS = {'name', 'email', 'phone', 'education', 'skill', 'project', 'award', 'availability', 'other'}


def question(text, fact_ids=()):
    return {'id': 'q-' + digest([text, list(fact_ids)])[:12], 'text': text,
            'fact_ids': list(fact_ids), 'resolution': '', 'note': ''}


def validate_facts(data: dict, segments: list) -> tuple[list, list]:
    if not isinstance(data, dict) or not isinstance(data.get('facts'), list) or len(data['facts']) > 300:
        raise ValueError('事实输出结构无效或超过 300 项')
    sources = {s['id']: s for s in segments}
    facts, questions, seen = [], [], set()
    for raw in data['facts']:
        if not isinstance(raw, dict) or raw.get('field') not in FIELDS:
            raise ValueError('事实字段不符合约定')
        segment = sources.get(raw.get('segment_id'))
        value, quote = raw.get('value'), raw.get('quote')
        if not segment or not isinstance(value, str) or not value.strip() or len(value) > 3000:
            raise ValueError('事实引用不存在或事实值无效')
        if not isinstance(quote, str) or quote not in segment['text'] or value not in quote:
            raise ValueError('事实值或引用片段不在原材料中')
        key = (raw['field'], value, segment['id'])
        if key in seen:
            continue
        seen.add(key)
        fid = f'f{len(facts)+1:04}'
        fact = {'id': fid, 'field': raw['field'], 'value': value, 'segment_id': segment['id'],
                'quote': quote, 'source': segment['source'], 'location': segment['location'],
                'status': 'ocr_unverified' if segment['method'] == 'ocr' else 'source_text',
                'ownership': 'unknown' if raw['field'] == 'project' else 'not_applicable'}
        facts.append(fact)
        if fact['field'] == 'project':
            questions.append(question('请确认项目中的个人贡献，材料不能自动证明作者归属。', [fid]))
        if fact['status'] == 'ocr_unverified':
            questions.append(question('请对照原图核实 OCR 文字。', [fid]))
    for field in ('name', 'email', 'phone'):
        candidates = [f for f in facts if f['field'] == field]
        if len({f['value'] for f in candidates}) > 1:
            questions.append(question(f'{field} 存在冲突，请保留正确值并省略错误值。',
                                      [f['id'] for f in candidates]))
    if not any(f['field'] == 'name' for f in facts):
        questions.append(question('缺少姓名，请补充姓名及依据。'))
    if not any(f['field'] in ('email', 'phone') for f in facts):
        questions.append(question('缺少联系方式，请补充至少一种联系方式。'))
    if not any(f['field'] in ('education', 'project', 'skill') for f in facts):
        questions.append(question('缺少教育、项目或技能材料，请补充核心经历。'))
    return facts, questions


def offline_facts(segments):
    from .sample import SAMPLE_TEXT
    if len(segments) != 1 or segments[0]['text'] != SAMPLE_TEXT.strip():
        raise ValueError('offline 仅允许随项目提供的原样虚构材料，不能处理个人资料')
    facts = []
    for line in SAMPLE_TEXT.strip().splitlines()[1:]:
        field, value = line.split('：', 1)
        facts.append({'field': field, 'value': value, 'quote': line,
                      'segment_id': segments[0]['id'], 'ownership': 'not_applicable'})
    return {'facts': facts}


def collect_facts(workspace: Path, run_key: str, mode: str = 'deepseek') -> str:
    verify_sources(workspace, run_key)
    directory = run_dir(workspace, run_key)
    extracted = read_json(directory / 'extracted.json')
    issues = list(extracted['issues'])
    segments = extracted['segments']
    if mode == 'offline':
        output = offline_facts(segments)
    elif mode == 'deepseek':
        output = {'facts': []}
        client = DeepSeekClient() if segments else None
        for segment in segments[:24]:
            result = client.complete(prompts.FACTS, {'segments': [segment]})
            # Validate per request before merging; a model may cite only what it received.
            validate_facts(result, [segment])
            output['facts'].extend(result['facts'])
            if not result['facts']:
                issues.append({'source': segment['source'], 'reason': f"{segment['location']} / {segment['id']} 未整理出事实，请人工核对该片段"})
        if len(segments) > 24:
            issues.append({'source': 'model_budget', 'reason': f'24 次调用上限，另有 {len(segments)-24} 个片段未整理'})
    else:
        raise ValueError('模式必须为 deepseek 或 offline')
    facts, questions = validate_facts(output, segments)
    for issue in issues:
        questions.append(question(f"材料问题：{issue['source']}：{issue['reason']}，请补充或明确省略。"))
    from .sample import SAMPLE_TEXT
    synthetic = mode == 'offline' or (len(segments) == 1 and segments[0]['text'] == SAMPLE_TEXT.strip())
    bundle = {'mode': mode, 'synthetic': synthetic, 'snapshot_hash': extracted['snapshot_hash'],
              'facts': facts, 'questions': questions}
    write_json(directory / 'facts.json', bundle)
    return run_key


def validate_resume(data: dict):
    if not isinstance(data, dict) or not isinstance(data.get('name'), str) or not data['name'].strip():
        raise ValueError('请补充有效姓名')
    if not isinstance(data.get('sections'), list) or not data['sections']:
        raise ValueError('简历至少需要一节经历或技能')
    if not any(c.get('value', '').strip() for c in data.get('contact', [])):
        raise ValueError('请补充至少一种联系方式')
    if data.get('photo'):
        raise ValueError('首版不支持照片，请先使用文字版模板')
    if len(str(data)) > 60000:
        raise ValueError('简历正文超过长度限制')
    for group in data['sections']:
        if not isinstance(group, dict) or not isinstance(group.get('title'), str) or not group['title'].strip():
            raise ValueError('栏目标题无效')
        if not isinstance(group.get('items'), list) or not group['items']:
            raise ValueError('栏目不能留空')
        for item in group['items']:
            if not isinstance(item, dict) or not isinstance(item.get('paragraphs'), list):
                raise ValueError('每条经历需要正文 paragraphs')
            if not item['paragraphs'] or not all(isinstance(p, str) and p.strip() for p in item['paragraphs']):
                raise ValueError('经历正文不能为空')


def draft_resume(workspace: Path, run_key: str, mode: str = 'deepseek') -> str:
    manifest = verify_sources(workspace, run_key)
    directory = run_dir(workspace, run_key)
    bundle = read_json(directory / 'facts.json')
    if bundle['mode'] != mode:
        raise ValueError('不能混用离线与真实模型结果')
    usable = [f for f in bundle['facts'] if f['status'] == 'source_text' and f['ownership'] != 'unknown']
    narrative = [f for f in usable if f['field'] not in ('name', 'email', 'phone', 'other')]
    sections = []
    if mode == 'offline':
        for field, title in [('education', '教育背景'), ('skill', '专业技能'), ('award', '奖项荣誉')]:
            items = [{'title': '', 'paragraphs': [f['value']], 'fact_ids': [f['id']]}
                     for f in narrative if f['field'] == field]
            if items:
                sections.append({'title': title, 'items': items})
    elif narrative:
        result = DeepSeekClient().complete(prompts.DRAFT, {'facts': narrative, 'target': manifest['config']['target'],
                                                          'jd': manifest['config']['jd']})
        sections = result.get('sections')
        if not isinstance(sections, list) or len(sections) > 10:
            raise ValueError('草稿 sections 无效')
        ids = {f['id']: f for f in narrative}
        for group in sections:
            if not isinstance(group, dict) or set(group) - {'title', 'items'}:
                raise ValueError('草稿栏目含不支持的字段')
            if not isinstance(group.get('items'), list):
                raise ValueError('草稿条目结构无效')
            for item in group['items']:
                if not isinstance(item, dict) or set(item) - {'title', 'paragraphs', 'fact_ids'}:
                    raise ValueError('草稿条目含不支持的字段')
                refs = item.get('fact_ids')
                if not isinstance(refs, list) or not refs or any(r not in ids for r in refs):
                    raise ValueError('草稿引用不存在或未确认的事实')
                evidence = '\n'.join(ids[r]['value'] for r in refs)
                text = str(item.get('title', '')) + ' '.join(item.get('paragraphs', []))
                if any(n not in evidence for n in re.findall(r'\d+(?:\.\d+)?', text)):
                    raise ValueError('草稿添加了无证据的数字')
                for term in ('独立', '提升', '生产部署', '熟练', '精通'):
                    if term in text and term not in evidence:
                        raise ValueError('草稿添加了未经证实的能力或成果')
    names = [f for f in usable if f['field'] == 'name']
    resume = {'name': names[0]['value'] if names else '',
              'name_fact_ids': [names[0]['id']] if names else [],
              'headline': manifest['config']['target'], 'paper': 'A4', 'font': 'Noto Sans CJK SC',
              'heading_font': 'Noto Sans CJK SC',
              'contact': [{'label': '邮箱' if f['field'] == 'email' else '电话', 'value': f['value'], 'fact_ids': [f['id']]}
                          for f in usable if f['field'] in ('email', 'phone')], 'sections': sections}
    write_json(directory / 'resume.draft.json', resume)
    return run_key
