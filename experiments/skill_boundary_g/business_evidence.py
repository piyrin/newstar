"""Quote-grounded extraction plus deterministic checks for event numeric constraints."""
import json
import re


def number_in(value, quote):
    numbers=re.findall(r'(?<![\d.])\d[\d,]*(?:\.\d+)?(?![\d.])',quote)
    return any(float(n.replace(',',''))==value for n in numbers)


def minutes(value):
    h,m=map(int,value.split(':'));return h*60+m


def resolve_line_evidence(text,raw):
    lines={f'L{i:04d}':line for i,line in enumerate(text.splitlines(),1)}
    def quote(ident):
        if ident in [None,'']:return ''
        if ident not in lines:raise ValueError('unknown source line ID: '+str(ident))
        return lines[ident]
    result={'schema_version':'line_ids_v2','sessions':[],
            'unsupported_actual_spend_claims':[quote(i) for i in raw.get('unsupported_actual_spend_claim_line_ids',[])]}
    for s in raw.get('sessions',[]):
        result['sessions'].append({'start':s.get('start'),'end':s.get('end'),'allocated_people':s.get('allocated_people'),
            'quote':quote(s.get('time_line_id')),'people_quote':quote(s.get('people_line_id'))})
    for key in ['total','remaining']:
        entry=raw.get(key) or {}
        result[key]={'value':entry.get('value'),'quote':quote(entry.get('line_id'))}
    return result


def verified_actual_spend_claims(text):
    actual=re.compile(r'实际(?:发生|支出|费用|付款|支付|金额)|已(?:经)?(?:支付|付款|花费|支出)|actual\s+(?:cost|amount)|amount\s+paid',re.I)
    unknown=re.compile(r'待填|待确认|未知|未提供|未发生|尚未|未支付|不代表|不等于|不得|不可|不能|不要|\[|\]',re.I)
    claims=[];header=None
    for line in text.splitlines():
        cleaned=re.sub(r'待支付\s*[/／]\s*已支付|已支付\s*[/／]\s*待支付','[付款状态待选]',line)
        cells=[c.strip().replace('**','') for c in cleaned.strip().strip('|').split('|')]
        if cleaned.strip().startswith('|'):
            if all(re.fullmatch(r'[:\-\s]+',c or ' ') for c in cells):continue
            if header is None or any(actual.search(c) for c in cells) and not any(re.search(r'\d',c) for c in cells):
                header=cells
            elif header and len(header)==len(cells):
                for h,v in zip(header,cells):
                    if actual.search(h) and re.search(r'\d',v) and not unknown.search(v) and '计划' not in v and '预计' not in v:
                        claims.append(line);break
        else:header=None
        for i,cell in enumerate(cells):
            if not actual.search(cell) or unknown.search(cell):continue
            state=bool(re.search(r'实际发生|已(?:经)?(?:支付|付款|花费|支出)',cell))
            own_number=bool(re.search(r'\d',cell))
            next_value=cells[i+1] if i+1<len(cells) else ''
            adjacent_number=bool(re.search(r'\d',next_value)) and not unknown.search(next_value)
            if own_number or adjacent_number or (state and re.search(r'\d',cleaned)):
                claims.append(line);break
    return list(dict.fromkeys(claims))


def event_constraint_issues(facts,evidence):
    issues=[];sessions=evidence.get('sessions',[]);counts=[];intervals=[]
    start,end=re.split('[—–-]',facts['time_window'])
    for index,s in enumerate(sessions,1):
        q=s.get('quote','');n=s.get('allocated_people')
        if type(n) is not int:issues.append({'session':index,'error':'未明确分配人数','quote':q})
        else:
            counts.append(n)
            if not 0<n<=facts['room_capacity']:issues.append({'session':index,'allocated_people':n,'maximum_capacity':facts['room_capacity'],'quote':q})
        try:
            a,b=minutes(s['start']),minutes(s['end']);intervals.append((a,b,index))
            if b-a!=facts['session_minutes']:issues.append({'session':index,'actual_minutes':b-a,'required_minutes':facts['session_minutes'],'quote':q})
            if not minutes(start)<=a<b<=minutes(end):issues.append({'session':index,'actual_time':[s['start'],s['end']],'required_window':facts['time_window'],'quote':q})
        except (KeyError,ValueError,TypeError):issues.append({'session':index,'error':'缺少可核对的明确起止时间','quote':q})
    if not sessions:issues.append({'error':'未提供实际采用的明确场次安排'})
    if sum(counts)!=facts['registered_people']:issues.append({'allocated_total':sum(counts),'required_total':facts['registered_people']})
    ordered=sorted(intervals)
    for a,b in zip(ordered,ordered[1:]):
        if a[1]>b[0]:issues.append({'overlapping_sessions':[a[2],b[2]]})
    c=facts['costs'];total=c['venue_yuan']+c['photography_yuan']+facts['registered_people']*(c['materials_per_person_yuan']+c['snacks_per_person_yuan'])
    for key,expected in [('total',total),('remaining',facts['budget_yuan']-total)]:
        observed=(evidence.get(key) or {}).get('value')
        if observed!=expected:issues.append({'budget_field':key,'observed':observed,'required_from_original_facts':expected})
    return issues


def payment_option_or_plan(line):
    # A list of possible states is not a statement that a payment happened.
    cleaned=re.sub(r'待支付\s*[/／]\s*已支付|已支付\s*[/／]\s*待支付','[付款状态待选]',line)
    if cleaned!=line and not re.search(r'实际(?:支出|费用|付款|支付)|已(?:支付|花费|支出)',cleaned):return True
    return '计划支出' in line and not re.search(r'实际|已支付|已花费|已支出',line)


def line_evidence_schema(text):
    ids=[f'L{i:04d}' for i,_ in enumerate(text.splitlines(),1)]
    ref={'type':['string','null'],'enum':ids+[None]}
    def obj(properties):return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
    scalar=obj({'value':{'type':['number','null']},'line_id':ref})
    session=obj({'start':{'type':'string'},'end':{'type':'string'},'allocated_people':{'type':['integer','null']},
                 'time_line_id':ref,'people_line_id':ref})
    return obj({'sessions':{'type':'array','items':session},'total':scalar,'remaining':scalar,
        'unsupported_actual_spend_claim_line_ids':{'type':'array','items':{'type':'string','enum':ids}}})


def validate_event_evidence(facts,text,evidence):
    grounded=True; sessions_ok=True; intervals=[]; counts=[]
    sessions=evidence.get('sessions',[])
    start,end=re.split('[—–-]',facts['time_window'])
    try:
        for s in sessions:
            quote=s['quote'];people_quote=s.get('people_quote',quote)
            count=s['allocated_people']
            grounded &= bool(quote) and quote in text and bool(people_quote) and people_quote in text
            grounded &= s['start'] in quote and s['end'] in quote and type(count) is int and number_in(count,people_quote)
            a,b=minutes(s['start']),minutes(s['end']);intervals.append((a,b));counts.append(count)
            sessions_ok &= b-a==facts['session_minutes'] and minutes(start)<=a<b<=minutes(end)
            sessions_ok &= 0<count<=facts['room_capacity']
        sessions_ok &= bool(sessions) and sum(counts)==facts['registered_people']
        sessions_ok &= all(a[1]<=b[0] for a,b in zip(sorted(intervals),sorted(intervals)[1:]))
        costs=facts['costs'];people=facts['registered_people']
        total=costs['venue_yuan']+costs['photography_yuan']+people*(costs['materials_per_person_yuan']+costs['snacks_per_person_yuan'])
        budget_ok=True
        for name,expected in [('total',total),('remaining',facts['budget_yuan']-total)]:
            entry=evidence[name];q=entry['quote']
            grounded &= bool(q) and q in text and number_in(entry['value'],q)
            budget_ok &= entry['value']==expected
    except (KeyError,TypeError,ValueError):
        grounded=False;sessions_ok=False;budget_ok=False
    # Detect the observed failure directly, regardless of an extractor's omission.
    pattern=r'(?:实际(?:支出|费用|付款|支付)(?:合计|总额)?|已(?:支付|花费|支出))\s*[:：|]\s*[*￥¥\s]*(\d[\d,]*(?:\.\d+)?)'
    observed=bool(re.search(pattern,text))
    claims=evidence.get('unsupported_actual_spend_claims')
    if evidence.get('schema_version')=='line_ids_v1' and isinstance(claims,list):
        claims=[q for q in claims if not(q in text and payment_option_or_plan(q))]
    no_actual=not observed and claims==[]
    if evidence.get('schema_version')=='line_ids_v2':no_actual=not verified_actual_spend_claims(text)
    return {'event_quotes_grounded':bool(grounded),'event_feasible_explicit_allocation':bool(sessions_ok),
            'event_budget_from_facts':bool(budget_ok),'event_no_unverified_actual_spend':no_actual}


def extract_event_evidence(api,selected,path):
    text='\n\n'.join(r['content'] for r in selected.values())
    numbered='\n'.join(f'L{i:04d}|{line}' for i,line in enumerate(text.splitlines(),1))
    prompt=('只抽取输入带行号的实际最终材料已经明确写出的内容，不计算标准答案，不补全计划，不把容量上限当作分配人数。'
        '只选择真实行号，由程序读取原文；不要复制、改写或缩写引文。找不到证据时行号填null，不编造行号。'
        'sessions只记录最终采用的场次；start/end用HH:MM，allocated_people仅取材料明确分配/建议分配的人数，'
        '实际采用的场次表中，“人数/安排人数”列可表示分配人数；“人数上限/容量”列才是容量，不能混淆。'
        '只说容量却没分配人数就返回null。time_line_id选含该场起止时间的行；people_line_id选含该场明确分配人数的行。'
        'total取预计/计划支出合计，不是预算上限；remaining取预计结余，分别选数值与对应行号。'
        'unsupported_actual_spend_claim_line_ids仅选明确宣称已发生付款/实际支出的行；“待支付/已支付”待选项、空模板、计划支出不算已付款。'
        'JSON: {"sessions":[{"start":"HH:MM","end":"HH:MM","allocated_people":整数或null,"time_line_id":"L0001或null","people_line_id":"L0001或null"}],'
        '"total":{"value":数值或null,"line_id":"L0001或null"},"remaining":{"value":数值或null,"line_id":"L0001或null"},'
        '"unsupported_actual_spend_claim_line_ids":["真实行号"]}。只返回紧凑JSON。')
    mode=line_evidence_schema(text) if getattr(api,'supports_json_schema',False) else True
    result,_=api.call([{'role':'system','content':prompt},{'role':'user','content':numbered}],path,json_mode=mode,max_tokens=1800)
    resolved=resolve_line_evidence(text,result)
    resolved['model_actual_spend_claim_candidates']=resolved['unsupported_actual_spend_claims']
    resolved['unsupported_actual_spend_claims']=verified_actual_spend_claims(text)
    return text,resolved
