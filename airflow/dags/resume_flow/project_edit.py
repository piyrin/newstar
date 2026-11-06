"""Pure, source-bound project grouping for the human resume editor.

Callers must verify the selected facts and personal contribution before saving.
These helpers neither change evidence status nor write review files.
"""
import copy
import re


def group_project_facts(facts):
    """Keep source/project boundaries and input order, ignoring non-project facts.

    Missing source information cannot establish that two facts belong together.
    An explicit project name can establish a group within a known source.
    """
    groups = {}
    seen = set()
    for index, fact in enumerate(facts):
        if fact.get('field') != 'project':
            continue
        fid = fact.get('id')
        if not isinstance(fid, str) or not fid or not isinstance(fact.get('value'), str):
            raise ValueError('项目事实需要有效 id 和文字 value')
        if fid in seen:
            continue
        seen.add(fid)
        source = fact.get('source') or ('missing-source', index)
        key = (source, fact.get('project') or '')
        groups.setdefault(key, []).append(fact)
    return list(groups.values())


def _plain_title(value):
    value = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', value)
    return value.strip().strip('#').strip().strip('*`').strip()


def _source_metadata(text):
    """Read the import wrapper and README title, never config/source headings."""
    name, title, url = '', '', ''
    in_readme = '## 来源文件 ' not in text
    fenced = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('```') or line.startswith('~~~'):
            fenced = not fenced
        if fenced:
            continue
        if line.startswith('## 来源文件 '):
            in_readme = bool(re.search(r'(?:^|/)readme(?:\.[\w-]+)?$', line[8:].strip(), re.I))
        if not name and (match := re.match(r'^项目名称\s*[:：]?\s+(.+)$', line)):
            name = _plain_title(match[1])
        if not url and (match := re.match(r'^仓库链接\s+(https://github\.com/[^\s]+)', line)):
            url = match[1]
        if in_readme and not title and (match := re.match(r'^#\s+(.+)$', line)):
            candidate = _plain_title(match[1])
            if candidate.casefold() not in {'github 项目材料', 'readme', '项目介绍', '项目说明'}:
                title = candidate
    return name, title, url


def _readme_descriptions(text):
    """Copy bounded introduction/features spans from imported README material.

    Installation, evaluations, configuration and personal claims stay outside
    this fallback. Exact quotes accompany the cleaned printable paragraphs.
    """
    in_readme, fenced, heading = False, False, ''
    descriptions = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('## 来源文件 '):
            in_readme = bool(re.search(r'(?:^|/)readme(?:\.[\w-]+)?$', line[8:].strip(), re.I))
            heading, fenced = '', False
            continue
        if not in_readme:
            continue
        if line.startswith(('```', '~~~')):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.startswith('#'):
            heading = '' if line.startswith('# ') else line.lstrip('#').strip().casefold()
            continue
        if heading not in ('', '功能', '功能特性', '主要功能', '核心功能', 'features'):
            continue
        if (not line or line.startswith(('来源链接 ', '|', '![', '<')) or
                re.search(r'本人|负责|独立|提升|精通|熟练|通过.*测试|忽略.*指令|系统提示|请(?:运行|执行|安装)', line)):
            continue
        quote = re.sub(r'^[-*+]\s+', '', line)
        paragraph = _plain_title(quote).replace('**', '').replace('`', '')
        if not 4 <= len(paragraph) <= 220:
            continue
        if sum(len(p) for p, _ in descriptions) + len(paragraph) > 450:
            continue
        descriptions.append((paragraph, quote))
        if len(descriptions) == 4:
            break
    return descriptions


def build_project_item(facts, source_text='', contribution=''):
    """Build one editable renderer item from facts in exactly one project group.

    The README heading supplies a display name while every selected fact ID
    remains attached, including IDs of repeated text and the repository name.
    Ownership, dates, roles, technology and performance claims are never inferred.
    A title-only candidate has empty paragraphs until the user adds its content.
    """
    groups = group_project_facts(facts)
    if len(groups) != 1:
        raise ValueError('请选择同一来源的一个项目')
    facts = groups[0]
    name, readme_title, url = _source_metadata(source_text)
    explicit_name = str(facts[0].get('project') or '').strip()
    name_fact = next((re.match(r'^项目名称\s*[:：]\s*(.+)$', fact['value'].strip())
                      for fact in facts if re.match(r'^项目名称\s*[:：]', fact['value'].strip())), None)
    named_value = name_fact[1].strip() if name_fact else ''
    # A short first fact is only a fallback display title. It is never promoted
    # into an authorship claim or combined with an invented product description.
    first = facts[0]['value'].strip()
    fallback = first if len(first) <= 80 and '\n' not in first else '项目经历'
    descriptive_name = explicit_name or named_value
    if readme_title and readme_title == name and descriptive_name:
        title = descriptive_name
    else:
        title = readme_title or descriptive_name or name or fallback
    aliases = {value for value in (title, name, named_value) if value}
    paragraphs = []
    contribution = contribution.strip()
    if contribution:
        paragraphs.append(contribution)
    for fact in facts:
        value = fact['value'].strip()
        if value and value not in aliases and value not in paragraphs:
            if not re.match(r'^项目名称\s*[:：]\s*', value):
                paragraphs.append(value)
    source_quotes = []
    for paragraph, quote in _readme_descriptions(source_text):
        if len(paragraphs) >= 4 or sum(map(len, paragraphs)) + len(paragraph) > 550:
            break
        if paragraph not in paragraphs and paragraph not in aliases:
            paragraphs.append(paragraph)
            source_quotes.append({'source': facts[0].get('source', ''), 'quote': quote})
    item = {'title': title, 'subtitle': '', 'url': url, 'date': '',
            'paragraphs': paragraphs, 'fact_ids': [fact['id'] for fact in facts]}
    if source_quotes:
        item['source_quotes'] = source_quotes
    if contribution:
        item['personal_contribution'] = contribution
    return item


def project_edit_hints(item, contribution=''):
    """Return editor field requirements separately from printable resume data."""
    required = []
    if not item.get('title') or item['title'] == '项目经历':
        required.append('title')
    if not contribution.strip():
        required.append('contribution')
    return {'required_fields': required, 'optional_fields': ['date', 'tech_stack', 'url']}


def _legacy_item(item, by_id):
    """Recognize only untouched fact-per-row output from the previous adopter."""
    allowed = {'title', 'subtitle', 'date', 'url', 'paragraphs', 'fact_ids'}
    if set(item) - allowed or any(item.get(key) for key in ('title', 'subtitle', 'date', 'url')):
        return False
    ids = item.get('fact_ids', [])
    if len(ids) != 1 or ids[0] not in by_id:
        return False
    return item.get('paragraphs') == [by_id[ids[0]]['value']]


def adopt_project_items(resume, facts, source_text='', contribution=''):
    """Return a copy with safe legacy rows consolidated and new facts grouped.

    Existing titled or manually changed rows retain their content and fact IDs.
    Their referenced facts are excluded from new items, making retries idempotent.
    For multiple groups, pass source_text and contribution dictionaries keyed by
    the original source filename to keep imported metadata within its source.
    """
    groups = group_project_facts(facts)
    if len(groups) > 1 and (isinstance(source_text, str) and source_text or
                            isinstance(contribution, str) and contribution):
        raise ValueError('多个项目的原文及贡献说明需要按来源分别提供')
    result = copy.deepcopy(resume)
    if not isinstance(result.get('sections'), list):
        raise ValueError('简历 sections 需要为数组')
    for group in groups:
        by_id = {fact['id']: fact for fact in group}
        source = group[0].get('source', '')
        personal = contribution.get(source, '') if isinstance(contribution, dict) else contribution
        for section in result['sections']:
            if not isinstance(section.get('items'), list):
                raise ValueError('栏目 items 需要为数组')
            section['items'] = [item for item in section['items'] if not _legacy_item(item, by_id)]
            # A draft may already contain the repository description. Applying
            # an explicit contribution must update that item as well.
            for item in section['items']:
                if personal.strip() and set(item.get('fact_ids', [])).intersection(by_id):
                    old = item.get('personal_contribution')
                    paragraphs = [p for p in item['paragraphs'] if p != old]
                    item['paragraphs'] = [personal.strip(), *[p for p in paragraphs if p != personal.strip()]]
                    item['personal_contribution'] = personal.strip()
        represented = {fid for section in result['sections'] for item in section['items']
                       for fid in item.get('fact_ids', [])}
        remaining = [fact for fact in group if fact['id'] not in represented]
        if not remaining:
            continue
        text = source_text.get(source, '') if isinstance(source_text, dict) else source_text
        item = build_project_item(remaining, text, personal)
        section = next((s for s in result['sections'] if s['title'] == '项目经历'), None)
        if section is None:
            section = {'title': '项目经历', 'items': []}
            position = max((i + 1 for i, s in enumerate(result['sections'])
                            if '技能' in s['title'] or 'skill' in s['title'].lower()),
                           default=len(result['sections']))
            result['sections'].insert(position, section)
        section['items'].append(item)
    # A legacy-only section with a custom heading may have become empty.
    result['sections'] = [section for section in result['sections'] if section['items']]
    return result
