"""Evidence collection, validation, and editable resume drafts."""
import re
import os
from pathlib import Path

from . import prompts
from .llm import DeepSeekClient
from .project_edit import adopt_project_items
from .storage import digest, file_hash, read_json, run_dir, verify_sources, write_json

FIELDS = {'name', 'email', 'phone', 'education', 'skill', 'project', 'award', 'availability', 'other'}


def question(text, fact_ids=()):
    return {'id': 'q-' + digest([text, list(fact_ids)])[:12], 'text': text,
            'fact_ids': list(fact_ids), 'resolution': '', 'note': ''}


def source_span(value, source):
    """Resolve formatting-only whitespace differences to an exact source span."""
    if not isinstance(value, str) or not value.strip():
        return None
    if value in source:
        return value
    positions = [i for i, char in enumerate(source) if not char.isspace() and char not in '\u200b\ufeff']
    compact_source = ''.join(source[i] for i in positions)
    compact_value = ''.join(char for char in value if not char.isspace() and char not in '\u200b\ufeff')
    if not compact_value:
        return None
    start = compact_source.find(compact_value)
    if start < 0:
        return None
    return source[positions[start]:positions[start + len(compact_value) - 1] + 1]


def validate_facts(data: dict, segments: list) -> tuple[list, list]:
    if not isinstance(data, dict) or not isinstance(data.get('facts'), list) or len(data['facts']) > 300:
        raise ValueError('事实输出结构无效或超过 300 项')
    sources = {s['id']: s for s in segments}
    facts, questions, seen = [], [], set()
    for raw in data['facts']:
        if not isinstance(raw, dict) or not isinstance(raw.get('field'), str) or raw['field'] not in FIELDS:
            raise ValueError('事实字段不符合约定')
        segment_id = raw.get('segment_id')
        segment = sources.get(segment_id) if isinstance(segment_id, str) else None
        value, quote = raw.get('value'), raw.get('quote')
        if not segment or not isinstance(value, str) or not value.strip() or len(value) > 3000:
            raise ValueError('事实引用不存在或事实值无效')
        quote = source_span(quote, segment['text'])
        value = source_span(value, quote) if quote is not None else None
        if quote is None or value is None or len(value) > 3000:
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


def reconcile_responses(responses, segment):
    accepted, rejected, issues = [], [], []
    for response in responses:
        candidates = response.get('facts') if isinstance(response, dict) else None
        if not isinstance(candidates, list) or len(candidates) > 300:
            issues.append({'source': segment['source'], 'reason': f"{segment['location']} / {segment['id']} 模型事实结构未通过校验，请核对原文。"})
            continue
        for index, candidate in enumerate(candidates, 1):
            try:
                facts, _ = validate_facts({'facts': [candidate]}, [segment])
                accepted.extend(facts)
            except ValueError:
                rejected.append((index, candidate))
    facts, _ = validate_facts({'facts': accepted}, [segment])
    resolved = {(fact['field'], fact['value']) for fact in facts}
    seen = set()
    for index, candidate in rejected:
        field = candidate.get('field') if isinstance(candidate, dict) else None
        field = field if isinstance(field, str) and field in FIELDS else '未知字段'
        value = candidate.get('value') if isinstance(candidate, dict) else None
        canonical = source_span(value, segment['text'])
        identity = (field, digest(value))
        if (field, canonical) in resolved or identity in seen:
            continue
        seen.add(identity)
        issues.append({'source': segment['source'], 'reason': f"{segment['location']} / {segment['id']} 第{index}项 {field} 未通过来源校验，请核对原文并补充或省略。"})
    return facts, issues


def collect_segment(client, segment, directory):
    identity = {'segment': segment, 'prompt': prompts.FACTS,
                'model': os.environ.get('DEEPSEEK_MODEL', 'deepseek-flash')}
    fingerprint = digest({**identity, 'version': 2})
    path = directory / 'model-facts' / (segment['id'] + '.json')
    if path.exists():
        saved = read_json(path)
        if saved.get('fingerprint') == fingerprint:
            facts, _ = validate_facts(saved['output'], [segment])
            return facts, saved['issues']
        if saved.get('fingerprint') == digest({**identity, 'version': 1}):
            # Reconcile earlier checkpoints locally without resending materials.
            responses = []
            for attempt in (1, 2):
                response_path = path.with_name(segment['id'] + f'-attempt-{attempt}.json')
                if response_path.exists():
                    responses.append(read_json(response_path))
            if responses:
                facts, issues = reconcile_responses(responses, segment)
                write_json(path, {'fingerprint': fingerprint, 'output': {'facts': facts}, 'issues': issues})
                return facts, issues
    payload, responses = {'segments': [segment]}, []
    for attempt in range(2):
        result = client.complete(prompts.FACTS, payload)
        responses.append(result)
        write_json(path.with_name(segment['id'] + f'-attempt-{attempt + 1}.json'), result)
        try:
            validate_facts(result, [segment])
            break
        except ValueError as error:
            payload = {'segments': [segment], 'previous_response': result, 'validation_error': str(error),
                       'correction': '重新逐字提取。quote 必须从原文连续复制，value 必须从 quote 连续复制，保留空格与换行。不能核对的候选请删除。只返回修正后的 facts JSON。'}
    facts, issues = reconcile_responses(responses, segment)
    write_json(path, {'fingerprint': fingerprint, 'output': {'facts': facts}, 'issues': issues})
    return facts, issues


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
            facts, validation_issues = collect_segment(client, segment, directory)
            output['facts'].extend(facts)
            issues.extend(validation_issues)
            if not facts:
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
    contacts = data.get('contact', [])
    if not isinstance(contacts, list) or any(not isinstance(c, dict) or
                                            not isinstance(c.get('value'), str) for c in contacts):
        raise ValueError('联系方式结构无效')
    if data.get('photo') not in (None, '', 'photo.jpg'):
        raise ValueError('照片引用无效，请重新上传')
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
    extracted = read_json(directory / 'extracted.json')
    fingerprint = digest({'version': 2, 'facts': bundle, 'config': manifest['config'],
                          'extracted': extracted,
                          'mode': mode, 'prompt': prompts.DRAFT,
                          'model': os.environ.get('DEEPSEEK_MODEL', 'deepseek-flash')})
    draft_path = directory / 'resume.draft.json'
    checkpoint_path = directory / 'model-draft.json'
    try:
        checkpoint = read_json(checkpoint_path)
        if (isinstance(checkpoint, dict) and checkpoint.get('fingerprint') == fingerprint
                and draft_path.is_file() and checkpoint.get('output_sha256') == file_hash(draft_path)):
            return run_key
    except (OSError, ValueError):
        pass
    # Invalidate before rebuilding so failures cannot revive an earlier checkpoint.
    checkpoint_path.unlink(missing_ok=True)
    usable = [f for f in bundle['facts'] if f['status'] == 'source_text' and f['ownership'] != 'unknown']
    # Project descriptions are grouped deterministically from repository sources.
    # Unknown ownership remains a review question and never enters model prose.
    narrative = [f for f in usable if f['field'] not in ('name', 'email', 'phone', 'other', 'project')]
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
    projects = [fact for fact in bundle['facts']
                if fact['field'] == 'project' and fact['status'] == 'source_text']
    sources = {}
    for segment in extracted['segments']:
        if segment.get('method') != 'ocr':
            source = segment['source']
            sources[source] = sources.get(source, '') + '\n' + segment['text']
    resume = adopt_project_items(resume, projects, sources)
    project_ids = {fact['id'] for fact in projects if fact['ownership'] == 'unknown'}
    for section in resume['sections']:
        for item in section['items']:
            if project_ids.intersection(item.get('fact_ids', [])):
                item['pending_contribution'] = True
                if not item['paragraphs']:
                    item['paragraphs'] = ['项目描述与本人贡献待补充确认。']
    write_json(draft_path, resume)
    write_json(checkpoint_path, {'fingerprint': fingerprint, 'output_sha256': file_hash(draft_path)})
    return run_key
