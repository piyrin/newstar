"""Native Skill ladder with exact output references and frozen broad business cases."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import shutil
from runner import API, BASE, REPO, STOP_NETWORK, TASKS, read, save, schema, export_text_assets
from incremental import CORE, NEXT, fixtures, objective_checks, raw_worker, stage_passes,SkillUnavailable
from reference_store import ReferenceStore,model_reference
from business_evidence import extract_event_evidence, validate_event_evidence,event_constraint_issues
from local_api import LocalAPI
from planner_receipts import receipt_result
from feedback_csv import feedback_csv_issues

RELEASE_CRITERIA = [
    '功能、限制、版本和许可准确。', '给定两个上手命令准确。',
    '实际CSV空模板字段和顺序正确，没有虚构数据行。',
    '不编造仓库链接、下载量、证言或收益；未知保持未知。',
    '给出可用的反馈流转和维护职责，明确标为建议。', '最终材料之间没有上述事实矛盾。']

FACT_GUIDANCE = ('原始facts是事实唯一依据；上游产物是可能有错的草稿，只能辅助，不得覆盖facts。'
    '先核对上游的关键事实和数值约束，再使用其内容；发现冲突直接按facts纠正，不沿袭错误。'
    '不得把facts已明确给定的信息重新写成未知，不把自行添加的假设或额外条件当成用户硬要求。'
    '用户要求可用方案时，交付一个满足全部原始硬约束的明确建议方案；只列选项或把可推导结论搁置待决策不算完成。'
    '涉及资源/人数/时间的安排须明确写出实际建议分配量及合计，不能只给容量上限。'
    '计划、预算、预计费用与已发生的实际支出/实测结果必须区分；没有发生证据不可声称已经发生。'
    '需要真实CSV时，返回纯CSV正文或用独立csv代码块承载；Markdown表格不自动成为CSV文件。'
    '每个CSV只对应一张字段一致的表，不同字段结构的表应分开输出，不能把多种表混进一个CSV。')


def suite(kind):
    cases = fixtures()
    for c in cases:
        c['criteria'] = RELEASE_CRITERIA
    if kind == 'release':
        return cases
    for original in TASKS:
        if original['id'] == 'launch':
            continue
        c = copy.deepcopy(original)
        if c['id'] == 'event':
            c['facts']['cost_basis'] = '场地800元及摄影500元均为整场活动总费用；材料和点心按120人各一次计费。'
            c['criteria'] = [c['checks'][0], c['checks'][1], c['checks'][2],
                '实际提供可用活动安排和预算明细。', '实际提供报名说明及字段明确、符合隐私约束的记录模板。',
                '最终材料跨产物一致；不声称已发送、报名或执行外部操作。']
        elif c['id'] == 'recruit':
            c['criteria'] = [c['checks'][0], c['checks'][1], c['checks'][2],
                '未知报名期限和联系链接保持待确认，不编造。',
                '实际提供招募文案、岗位职责、候选人记录模板和新人上手说明。',
                '最终材料名额、每周时间、状态字段和流程相互一致。']
        else:
            c['criteria'] = [c['checks'][0], c['checks'][1],
                '实际提供学生本周报名待办，日期正确。',
                '实际提供负责人缺失核对单，并明确B的截止日期未知。',
                '实际提供提醒文案和字段明确的可用跟踪模板；文案和待办一致。', c['checks'][3]]
        cases.append(c)
    return cases


def ordered_registry():
    rows = read(BASE/'registry.json'); by = {r['tool_name']: r for r in rows}
    priority = CORE + ['events-activities', 'expense-accounting', 'candidate-talent-pool',
                       'onboarding-playbook', 'notification-reminder-hub'] + NEXT
    priority = list(dict.fromkeys(n for n in priority if n in by))
    if len(priority[:10]) < 10:
        raise ValueError('missing baseline Skills')
    return [by[n] for n in priority] + [r for r in rows if r['tool_name'] not in priority]


def make_tools(rows, ids, schema_ids='all', exposure='full',planner_artifacts='full'):
    item = {'type': 'string'}
    if ids:
        item['enum'] = ids
    tools = []
    for r in rows:
        t = schema(r, full=exposure=='full')
        prop = t['function']['parameters']['properties']['artifact_ids']
        prop.update(items=item if schema_ids=='all' else {'type':'string'}, description='本次读取的真实输出reference_id，文档和文件都可用；根任务为[]。')
        if not ids and schema_ids=='all':
            prop['maxItems'] = 0
        tools.append(t)
    tools.append({'type': 'function', 'function': {'name': 'submit_deliverables',
        'description': '完成用户全部要求后提交实际最终产物清单。只引用已返回的reference_id；不生成业务正文。此工具为提交控制，不是Skill。',
        'parameters': {'type': 'object', 'properties': {
            'deliverables': {'type': 'array', 'minItems': 1, 'items': {'type': 'object', 'properties': {
                'purpose': {'type': 'string'}, 'reference_ids': {'type': 'array', 'minItems': 1, 'items': item}},
                'required': ['purpose', 'reference_ids'], 'additionalProperties': False}},
            'unresolved': {'type': 'array', 'items': {'type': 'string'}}},
            'required': ['deliverables', 'unresolved'], 'additionalProperties': False}}})
    review=copy.deepcopy(tools[-1]);review['function']['name']='review_deliverables'
    review['function']['description']='审阅实际最终候选产物是否符合原始需求和事实，返回可核查错误；不生成或修订正文。提交前须审阅当前版本。此工具为控制工具，不是Skill。'
    tools.append(review)
    if planner_artifacts=='receipts':
        tools.append({'type':'function','function':{'name':'read_artifacts',
            'description':'显式读取已落盘真实产物的完整正文；不创建业务产物，不计业务Skill或节点。必须单独调用。',
            'parameters':{'type':'object','properties':{'reference_ids':{'type':'array','minItems':1,'items':item}},
                'required':['reference_ids'],'additionalProperties':False}}})
    return tools


def qualified(verdict):
    return (set(verdict.get('checks', {})) == {str(i) for i in range(1, 7)}
            and all(v is True for v in verdict['checks'].values()) and verdict.get('errors') == [])


def csv_asset_issues(selected,strict_blank_rows=False):
    issues=[];seen=set()
    for ident,ref in selected.items():
        for file in ref.get('files',[]):
            if file['format']!='csv' or file['path'] in seen:continue
            seen.add(file['path']);base={'reference_id':file.get('reference_id',ident),'path':file['path']}
            try:
                with Path(file['path']).open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream,strict=True))
                if not rows or not rows[0] or not any(c.strip() for c in rows[0]):
                    issues.append({**base,'row':1,'error':'CSV缺少有效表头'});continue
                for index,row in enumerate(rows[1:],2):
                    if (row if strict_blank_rows else any(c.strip() for c in row)) and len(row)!=len(rows[0]):
                        issues.append({**base,'row':index,'expected_columns':len(rows[0]),'actual_columns':len(row),'header':rows[0],'values':row})
            except csv.Error as exc:issues.append({**base,'error':str(exc)})
    return issues


def physical_checks(case, selected,check_csv_shape=False,strict_feedback_csv=False,strict_release_facts=False,strict_blank_csv=False,extended_release_claims=False):
    checks = {'persisted_outputs': bool(selected)}
    rectangular=True
    for ref in selected.values():
        if not Path(ref['path']).is_file():
            checks['persisted_outputs'] = False
        for file in ref.get('files', []):
            if hashlib.sha256(Path(file['path']).read_bytes()).hexdigest() != file['sha256']:
                checks['persisted_outputs'] = False
            if check_csv_shape and file['format']=='csv':
                try:
                    with Path(file['path']).open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream,strict=True))
                    rectangular &= bool(rows) and bool(rows[0]) and any(c.strip() for c in rows[0])
                    if rows:rectangular &= all(len(row)==len(rows[0]) for row in rows[1:] if any(c.strip() for c in row))
                except csv.Error:rectangular=False
    if check_csv_shape:checks['csv_assets_rectangular']=not csv_asset_issues(selected,strict_blank_rows=strict_blank_csv)
    if 'feedback_fields' in case['facts']:
        checks.update(objective_checks(case, selected))
        if strict_feedback_csv:checks['all_feedback_csvs_without_invented_rows']=not feedback_csv_issues(case['facts'],selected)
    if strict_release_facts:
        from release_fact_issues import release_fact_issues
        checks['no_observed_unprovided_release_claims']=not release_fact_issues(case['facts'],selected)
    if extended_release_claims:
        from extended_release_facts import extended_release_fact_issues
        checks['no_unprovided_interface_license_security_claims']=not extended_release_fact_issues(case['facts'],selected)
    return checks


def review_diagnostics(hard):
    explanations={
        'no_unprovided_interface_license_security_claims':'终稿出现未给定的UI/导出入口/浏览器URL、MIT修改分发禁令或零泄露风险保证。详见extended_fact_issues的真实引用和行号；只修订无依据断言，不能新增或降低用户要求。',
        'no_observed_unprovided_release_claims':'终稿有未被facts支持的具体断言，详见release_fact_issues。请用合适Skill修订；指定端口不等于默认端口，未知日期/发布状态/标签搜索/反馈公开政策不能补造。',
        'actual_skill_composition':'组合要求未满足：至少两种不同Skill，且至少一个后续业务节点必须读取并处理已有真实产物。不得空调用凑依赖。',
        'csv_file_exact_empty_template':'最终引用中缺少字段顺序准确的实际空CSV文件。Markdown表格不是CSV附件；已生成的正确FILE引用也需要列入最终清单。',
        'csv_assets_rectangular':'至少一份最终CSV的字段数与表头不符或语法无效，详见实际引用/行号/列数。空物理行与含逗号的空字段记录不同。旧文件和旧DOC中的CSV不会随新文件自动修复；须用Skill生成正确版本，最终只引用已修订文档及附件。',
        'all_feedback_csvs_without_invented_rows':'最终交付包含非空的反馈CSV或字段顺序不符。需要空模板，不附带虚构反馈记录；另一份空模板不能替代清理这些额外记录。请修订包含问题表格的文档及附件，终稿引用新版本；旧引用不可变。',
        'commands_exact':'最终文件没有完整保留facts给定的上手命令，请逐字核对facts，不自行拼写或添加模块名。',
        'event_quotes_grounded':'数值证据未能对应最终原文。请将实际采用的场次与预计预算写清楚，供程序按原文行号核对；不要只写模糊选项。',
        'event_feasible_explicit_allocation':'最终交付缺少满足原始人数合计、单场容量、每场时长、时间窗口且不重叠的明确场次分配。必须依据facts给出可行建议，不能仅列容量冲突或留待决策。',
        'event_budget_from_facts':'预计费用合计或结余未与facts的整场固定费用、按人费用和预算对应；预算上限与预计支出是不同数值，请分别明确。',
        'event_no_unverified_actual_spend':'没有付款证据，不能把预计费用声称为已发生支出。真实支付状态应保留待填写；待选状态不代表已经付款。'}
    return [explanations[k] for k,v in hard.items() if not v and k in explanations]


def evaluate_delivery(api,case,selected,out,nodes=None,strict_feedback_csv=False,short_circuit_hard_failure=False,strict_release_facts=False,semantic_review_profile='legacy',semantic_api=None):
    if semantic_review_profile not in {'legacy','fact-evidence'}:raise ValueError('unknown semantic review profile')
    strict_blank=semantic_review_profile=='fact-evidence'
    hard=physical_checks(case,selected,check_csv_shape=True,strict_feedback_csv=strict_feedback_csv,strict_release_facts=strict_release_facts,strict_blank_csv=strict_blank,extended_release_claims=strict_blank)
    if nodes is not None:
        hard['actual_skill_composition']=len({n['skill'] for n in nodes})>=2 and any(n['depends_on'] for n in nodes)
    if case['id']=='event':
        text,evidence=extract_event_evidence(api,selected,out/'business-extractor')
        save(out/'business-evidence.json',evidence)
        hard.update(validate_event_evidence(case['facts'],text,evidence))
        save(out/'constraint-issues.json',event_constraint_issues(case['facts'],evidence))
    save(out/'csv-issues.json',csv_asset_issues(selected,strict_blank_rows=strict_blank))
    if strict_feedback_csv:save(out/'feedback-csv-issues.json',feedback_csv_issues(case['facts'],selected))
    if strict_release_facts:
        from release_fact_issues import release_fact_issues
        save(out/'release-fact-issues.json',release_fact_issues(case['facts'],selected))
    if strict_blank:
        from extended_release_facts import extended_release_fact_issues
        save(out/'extended-fact-issues.json',extended_release_fact_issues(case['facts'],selected))
    if short_circuit_hard_failure and not all(hard.values()):
        verdict={'checks':{},'errors':[],'not_evaluated':'hard checks already rejected the candidate; semantic acceptance not granted'}
        save(out/'verdict.json',verdict)
        return hard,verdict
    if semantic_review_profile=='fact-evidence':
        from semantic_review import review
        verdict=review(semantic_api or api,case,selected,out)
        save(out/'verdict.json',verdict)
        return hard,verdict
    verdict,_=api.call([{'role':'system','content':
        '只根据原始用户要求、给定事实和实际最终交付验收。只看final_deliverables；旧稿不算最终交付。'
        '文档path是实际主文档；files仅是额外附件，files=[]不代表主文档不存在。'
        '未知日期/链接允许保留待确认，不添加对外发布就绪、审美或额外文档要求。'
        'CSV空白行或明确的填写占位符不是虚构业务记录；检查实际CSV附件，不要把辅助Markdown表格当作CSV数据。'
        '按照用户提供的六项criteria逐条检查，返回紧凑JSON：'
        '{"checks":{"1":bool,"2":bool,"3":bool,"4":bool,"5":bool,"6":bool},'
        '"errors":["未满足的原始要求与具体产物证据"]}。全部满足时errors=[]。'},
        {'role':'user','content':json.dumps({'user_request':case,'final_deliverables':[model_reference(r) for r in selected.values()],
            'physical_checks':hard},ensure_ascii=False)}],out/'verifier',json_mode=True,max_tokens=1800)
    save(out/'verdict.json',verdict)
    return hard,verdict


def reject_call(out,messages,call,reason,rejections):
    feedback={'status':'rejected','error':reason,'action':'根据原始要求修正调用；没有生成任何虚构产物。当前调用已占用规划轮数。'}
    rejections.append({'tool':call['function']['name'],'arguments':call['function']['arguments'],'feedback':feedback})
    save(out/'control-rejections.json',rejections)
    messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(feedback,ensure_ascii=False)})


def controller_state(rows,nodes,store,reviews,remaining):
    names=sorted({n['skill'] for n in nodes});edges=sum(len(n['depends_on']) for n in nodes)
    unmet=[]
    if len(names)<2:unmet.append('成功产物尚未来自至少两个不同Skill；同一Skill反复调用仍只算一种。')
    if not edges:unmet.append('尚无后续业务节点读取上游产物；合适业务工具的artifact_ids应引用相关真实ID，不能始终为空数组。')
    passed=[sorted({i for d in r['manifest']['deliverables'] for i in d['reference_ids']}) for r in reviews if r['feedback']['passed']]
    if not passed:unmet.append('尚无终稿引用集合通过review_deliverables审阅。')
    return {'candidate_skills':len(rows),'successful_skill_names':names,'completed_business_nodes':len(nodes),
        'actual_upstream_edges':edges,'available_reference_ids':store.ids(),'passed_review_reference_sets':passed,
        'remaining_planner_rounds':remaining,'requirements_not_met_yet':unmet,
        'action_rule':'继续选择合适业务工具完成原始用户需求；最终清单必须与某次已通过审阅的引用集合一致，再调用submit_deliverables。口头宣告不能替代实际调用。'}


def candidate_rows(rows,repeat,order='shuffled'):
    if order not in {'shuffled','frozen'}:raise ValueError('invalid candidate order')
    result=list(rows)
    if order=='shuffled':random.Random(repeat).shuffle(result)
    return result


def run_one(series, rows, case, repeat, variant='baseline', schema_ids='all', backend='local', local_context=32768, exposure='full',local_thinking='off',local_sampling='legacy', replay_api=None,local_planner='native',local_gpu_layers=None,planner_artifacts='full',strict_feedback_csv=False,short_circuit_hard_failure=False,strict_release_facts=False,candidate_order='shuffled',local_seed=None,semantic_review_profile='legacy'):
    if semantic_review_profile not in {'legacy','fact-evidence'}:raise ValueError('unknown semantic review profile')
    if semantic_review_profile=='fact-evidence' and (backend!='local' or replay_api is not None):
        raise ValueError('fact-evidence requires fresh local calls, no cloud or replay')
    if replay_api is not None and backend!='local':raise ValueError('replay continuation is local-only')
    api_class=LocalAPI
    if local_planner=='structured':
        if backend!='local':raise ValueError('structured planner is local-only')
        from structured_planner import StructuredPlannerAPI
        api_class=StructuredPlannerAPI
    api_options={'context':local_context,'thinking':local_thinking,'sampling':local_sampling,'gpu_layers':local_gpu_layers}
    if local_seed is not None:api_options['seed']=local_seed
    api = replay_api or (api_class(**api_options) if backend=='local' else API())
    semantic_api=(LocalAPI(context=local_context,thinking='off',sampling='qwen-recommended',
        gpu_layers=local_gpu_layers,seed=local_seed) if semantic_review_profile=='fact-evidence' else api)
    out = series/f'n{len(rows):03}'/f"{case['id']}-r{repeat}"
    out.mkdir(parents=True, exist_ok=False)
    shuffled = candidate_rows(rows,repeat,candidate_order)
    by_name = {r['tool_name']: r for r in shuffled}
    store = ReferenceStore(); nodes = []; manifest = None; hard = {}; verdict = {}; error = None; reviews=[];rejections=[];attempts=[];protocol_feedback=[]
    artifact_reads=[]
    save(out/'case.json', case)
    messages = [{'role': 'system', 'content':
        '根据用户业务需求自主选择Skill、拆分子任务并建立真实上游引用。没有固定角色或固定DAG。'
        '必须调用工具完成实际交付；Skill只做其能力范围内的子任务。不得发送或发布。'
        '本次是Skill组合实验：至少使用两个不同Skill，并让至少一个后续业务节点通过artifact_ids读取和处理已有真实产物。'
        '只并行生成互不相干的文档不算组合；依赖必须服务于实际用户交付，不做空调用充数。'
        '若Skill返回unsupported，表示该次请求未完成且没有产物，需按其他工具能力重新选择；不能把拒绝当成成功。'
        '输出均已落盘，工具会返回每份文档DOC-和附件FILE-的reference_id；引用时原样复制，不能从文件名猜ID。'
        '所有已有引用都不可变。修订总是创建新DOC/FILE引用，旧引用的内容永远不变；最终清单必须替换成修订后的新ID。只改说明文档不会改变旧CSV文件。'
        '需要上游内容时在artifact_ids中传入其reference_id，根任务用[]。最终单独调用submit_deliverables，'
        '清单只列准备交付的最终版本，不用最终答复临时补写正文。'
        '提交前先单独调用review_deliverables审阅当前候选终稿；有实际错误就选择适合Skill修订，'
        '随后审阅修订版，当前候选全部通过才提交。审阅、修订、再审均计入同一16轮预算。'
        '完成满足原始用户要求的最小完整交付。不要自行增加未请求的审阅指引、索引或文件清单再反复同步；'
        '只修复违反用户事实或要求的问题，不为重复措辞、自身列表或版本号继续调用。'
        '所有原始要求已有实际交付后立即提交。未知保持未知，建议标为建议。'},
        {'role': 'user', 'content': json.dumps({'request': case['request'], 'facts': case['facts']}, ensure_ascii=False)}]
    if variant == 'grounded':
        messages[0]['content'] += FACT_GUIDANCE + '提交前对最终交付逐项核对原始事实、约束与要求。'
    if planner_artifacts=='receipts':
        messages[0]['content']+='工具完成后返回真实产物回执，正文保持完整落盘，不把全部旧稿反复塞入规划上下文。需要检查正文可单独调用read_artifacts；后续业务Skill的artifact_ids仍自动获得完整上游正文。回执不是业务内容的替代品；审阅和终验读取完整实体。只输出当前一轮实际可执行的调用，不预写未来步骤或假设未来ID；依赖尚未返回结果的节点应在后续轮次调用。'
    try:
        for step in range(16):
            tools = make_tools(shuffled, store.ids(), schema_ids,exposure,planner_artifacts)
            state=controller_state(rows,nodes,store,reviews,16-step);save(out/f'controller-state-{step:02}.json',state)
            request_messages=[dict(m) for m in messages]
            request_messages[0]['content']+='\n执行器当前真实状态（不替代原始业务要求，不指定Skill或DAG）：\n'+json.dumps(state,ensure_ascii=False)
            msg, _ = api.call(request_messages, out/f'planner-{step:02}', tools=tools, max_tokens=5000)
            messages.append(msg); calls = msg.get('tool_calls') or []
            if not calls:
                feedback={'round':step,'kind':'missing_native_call','error':'这次答复没有原生工具调用，未执行或提交任何业务产物。请依据当前真实状态继续调用合适工具、审阅并正式提交。该轮已计入原16轮预算。'}
                protocol_feedback.append(feedback);save(out/'protocol-feedback.json',protocol_feedback)
                messages.append({'role':'user','content':'执行器反馈：'+json.dumps(feedback,ensure_ascii=False)})
                continue
            control_names={'review_deliverables','submit_deliverables'}|({'read_artifacts'} if planner_artifacts=='receipts' else set())
            if len(calls)>1 and any(c['function']['name'] in control_names for c in calls):
                for c in calls:reject_call(out,messages,c,'审阅/提交控制工具必须单独调用；本批未执行，也没有产生新产物。请分别调用。',rejections)
                continue
            if planner_artifacts=='receipts' and calls[0]['function']['name']=='read_artifacts':
                try:
                    args=json.loads(calls[0]['function']['arguments'])
                    if not isinstance(args,dict) or set(args)!={'reference_ids'} or not args['reference_ids']:raise ValueError('reference_ids must contain existing output IDs')
                    outputs=store.resolve(args['reference_ids'])
                except (ValueError,KeyError,TypeError) as exc:
                    reject_call(out,messages,calls[0],str(exc),rejections);continue
                artifact_reads.append({'round':step,'reference_ids':args['reference_ids']});save(out/'artifact-reads.json',artifact_reads)
                messages.append({'role':'tool','tool_call_id':calls[0]['id'],'content':json.dumps({'outputs':[model_reference(r) for r in outputs]},ensure_ascii=False)})
                continue
            if any(c['function']['name']=='review_deliverables' for c in calls):
                if len(calls)!=1:raise ValueError('review must be a separate call')
                try:
                    args=json.loads(calls[0]['function']['arguments']);candidate=store.select(args)
                except (ValueError,KeyError,TypeError) as exc:
                    reject_call(out,messages,calls[0],str(exc),rejections);continue
                review_out=out/'reviews'/f'review-{len(reviews)+1:03}'
                rh,rv=evaluate_delivery(api,case,candidate,review_out,nodes,strict_feedback_csv=strict_feedback_csv,short_circuit_hard_failure=short_circuit_hard_failure,strict_release_facts=strict_release_facts,semantic_review_profile=semantic_review_profile,semantic_api=semantic_api)
                feedback={'passed':all(rh.values()) and qualified(rv),'physical_checks':rh,
                    'semantic_checks':rv.get('checks',{}),'errors':rv.get('errors',[]),
                    'failed_constraints':[k for k,v in rh.items() if not v]}
                if (review_out/'business-evidence.json').exists():
                    feedback['quoted_numeric_evidence']=read(review_out/'business-evidence.json')
                feedback['csv_file_issues']=read(review_out/'csv-issues.json')
                if strict_feedback_csv:feedback['feedback_csv_issues']=read(review_out/'feedback-csv-issues.json')
                if strict_release_facts:feedback['release_fact_issues']=read(review_out/'release-fact-issues.json')
                if semantic_review_profile=='fact-evidence':feedback['extended_fact_issues']=read(review_out/'extended-fact-issues.json')
                if semantic_review_profile=='fact-evidence' and (review_out/'semantic-evidence.json').exists():
                    feedback['semantic_evidence']={k:v for k,v in read(review_out/'semantic-evidence.json').items() if not rv['checks'].get(k)}
                if (review_out/'constraint-issues.json').exists():feedback['constraint_issues']=read(review_out/'constraint-issues.json')
                if feedback['csv_file_issues']:
                    feedback['version_rule']='以上错误属于列出的具体FILE引用；旧ID不可变。请通过合适Skill生成修订文件，并用返回的新FILE ID替换终稿里的旧ID。'
                feedback['errors'].extend(review_diagnostics(rh))
                reviews.append({'manifest':args,'feedback':feedback,'evidence_dir':str(review_out)})
                save(out/'control-calls.json',reviews)
                messages.append({'role':'tool','tool_call_id':calls[0]['id'],'content':json.dumps(feedback,ensure_ascii=False)})
                continue
            if any(c['function']['name'] == 'submit_deliverables' for c in calls):
                if len(calls) != 1:
                    raise ValueError('submission must be a separate final call')
                try:
                    candidate_manifest=json.loads(calls[0]['function']['arguments'])
                    selected=store.select(candidate_manifest)
                except (ValueError,KeyError,TypeError) as exc:
                    reject_call(out,messages,calls[0],str(exc),rejections);continue
                final_ids=set(selected)
                if not any(r['feedback']['passed'] and {i for d in r['manifest']['deliverables'] for i in d['reference_ids']}==final_ids for r in reviews):
                    reject_call(out,messages,calls[0],'这些最终引用尚未通过review_deliverables审阅；请先审阅，若有错误用合适Skill读取已有产物修订，然后再审。',rejections)
                    continue
                manifest=candidate_manifest;save(out/'manifest.json',manifest)
                break
            for call in calls:
                try:
                    fn=call['function']['name'];args=json.loads(call['function']['arguments'])
                    if fn not in by_name or set(args)!={'request','artifact_ids'}:raise ValueError('工具不存在或参数字段不符，必须仅含request和artifact_ids。')
                    if not isinstance(args['request'],str) or not args['request'].strip():raise ValueError('Skill请求不能为空。')
                    upstream=store.resolve(args['artifact_ids']);parents=store.producers(args['artifact_ids'])
                except (ValueError,KeyError,TypeError) as exc:
                    reject_call(out,messages,call,str(exc),rejections);continue
                ident = f'STEP-{len(nodes)+1:03}'
                depth = 1 + max((a['depth'] for a in upstream), default=0)
                attempt={'id':f'CALL-{len(attempts)+1:03}','skill':fn,'request':args['request'],'input_reference_ids':args['artifact_ids'],'status':'started'}
                attempt['execution_request_stem']='skill-'+attempt['id'];attempts.append(attempt);save(out/'skill-attempts.json',attempts)
                try:
                    answer, _ = raw_worker(api, by_name[fn], args['request'], case['facts'], [model_reference(r) for r in upstream], out/attempt['execution_request_stem'],
                                          guidance=FACT_GUIDANCE if variant == 'grounded' else '')
                except SkillUnavailable as exc:
                    feedback={'status':'unsupported','reason':str(exc),'artifact_created':False,
                        'action':'这次调用没有完成，请按现有工具的能力选择其他合适Skill；不得引用不存在的产物。'}
                    attempt.update(status='unsupported',feedback=feedback);save(out/'skill-attempts.json',attempts)
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(feedback,ensure_ascii=False)})
                    continue
                except Exception as exc:
                    attempt.update(status='execution_error',error=str(exc)[:1000]);save(out/'skill-attempts.json',attempts)
                    raise
                folder = out/'artifacts'; folder.mkdir(exist_ok=True)
                doc = folder/(ident+'.md'); doc.write_text(answer['artifact'], encoding='utf-8')
                files = export_text_assets(out, ident, answer['artifact'], raw_csv=fn == 'csv-manual-export')
                result = store.register(ident, fn, doc, answer['artifact'], files, depth)
                nodes.append({'id': ident, 'skill': fn, 'input_reference_ids': args['artifact_ids'],
                    'depends_on': parents, 'depth': depth, 'request': args['request'],
                    'execution_request_stem':attempt['execution_request_stem'],
                    'output_reference_ids': [r['reference_id'] for r in result['outputs']]})
                attempt.update(status='done',node_id=ident);save(out/'skill-attempts.json',attempts)
                save(folder/(ident+'.json'), result); save(out/'dag.json', nodes)
                model_result={**result,'outputs':[model_reference(r) for r in result['outputs']]}
                if planner_artifacts=='receipts':model_result=receipt_result(result)
                save(out/(attempt['execution_request_stem']+'.planner-result.json'),model_result)
                messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(model_result, ensure_ascii=False)})
        if manifest is None:
            raise ValueError('planner budget exhausted')
        hard,verdict=evaluate_delivery(api,case,selected,out,nodes,strict_feedback_csv=strict_feedback_csv,short_circuit_hard_failure=short_circuit_hard_failure,strict_release_facts=strict_release_facts,semantic_review_profile=semantic_review_profile,semantic_api=semantic_api)
    except Exception as exc:
        error = str(exc)[:1000]
    combination = len({n['skill'] for n in nodes}) >= 2 and any(n['depends_on'] for n in nodes)
    passed = error is None and manifest is not None and bool(hard) and all(hard.values()) and qualified(verdict) and combination
    result = {'case': case['id'], 'repeat': repeat, 'skills': len(rows), 'control_tools': 3 if planner_artifacts=='receipts' else 2, 'review_calls':len(reviews), 'variant': variant, 'schema_ids':schema_ids,
        'planner_artifacts':planner_artifacts,'artifact_read_calls':len(artifact_reads),
        'strict_feedback_csv':strict_feedback_csv,
        'strict_release_facts':strict_release_facts,
        'semantic_review_profile':semantic_review_profile,
        'candidate_order':candidate_order,'local_seed':local_seed,
        'short_circuit_hard_failure':short_circuit_hard_failure,
        'backend':backend,'model':api.model,'exposure':exposure,'rejected_calls':len(rejections),
        'local_thinking':local_thinking if backend=='local' else None,
        'local_sampling':local_sampling if backend=='local' else None,
        'local_planner':local_planner if backend=='local' else None,
        'local_gpu_layers':local_gpu_layers if backend=='local' else None,
        'protocol_rejections':len(protocol_feedback),
        'skill_call_attempts':len(attempts),'failed_skill_calls':sum(a['status'] in {'unsupported','execution_error'} for a in attempts),
        'attempted_skills':len({a['skill'] for a in attempts}),
        'passed': passed, 'error': error, 'physical_checks': hard, 'semantic_checks': verdict.get('checks', {}),
        'combination_evidence': combination, 'actual_skills': len({n['skill'] for n in nodes}),
        'nodes': len(nodes), 'chain': max((n['depth'] for n in nodes), default=0),
        'time_utc': datetime.now(timezone.utc).isoformat()}
    save(out/'summary.json', result); print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def main():
    p = argparse.ArgumentParser(); p.add_argument('--prefix', required=True)
    p.add_argument('--suite', choices=['release', 'broad'], default='broad')
    p.add_argument('--variant', choices=['baseline','grounded'], default='baseline')
    p.add_argument('--schema-ids',choices=['all','controls-only'],default='all')
    p.add_argument('--backend',choices=['local','deepseek'],default='local')
    p.add_argument('--local-context',type=int,default=32768)
    p.add_argument('--local-thinking',choices=['off','planner-worker','all'],default='off')
    p.add_argument('--local-sampling',choices=['legacy','qwen-recommended'],default='legacy')
    p.add_argument('--local-planner',choices=['native','structured'],default='native')
    p.add_argument('--local-gpu-layers',type=int)
    p.add_argument('--planner-artifacts',choices=['full','receipts'],default='full')
    p.add_argument('--strict-feedback-csv',action='store_true')
    p.add_argument('--short-circuit-hard-failure',action='store_true')
    p.add_argument('--critical-first',action='store_true');p.add_argument('--fail-fast',action='store_true')
    p.add_argument('--exposure',choices=['full','on-call'],default='full')
    p.add_argument('--sizes', type=int, nargs='+', default=[10, 15, 20, 30, 40, 60, 80, 100, 120, 140, 163])
    p.add_argument('--allow-small-baseline',action='store_true',help='same full cases, test fewer candidate Skills to establish a passing baseline')
    a = p.parse_args(); rows = ordered_registry(); cases = suite(a.suite)
    minimum=2 if a.allow_small_baseline else (10 if a.suite == 'broad' else 5)
    if a.sizes != sorted(set(a.sizes)) or a.sizes[0] < minimum:
        raise ValueError('strictly increasing valid sizes required')
    series = BASE/'progressive'/a.prefix; series.mkdir(parents=True, exist_ok=False)
    for name in ['progressive.py', 'local_api.py', 'structured_planner.py','planner_receipts.py','feedback_csv.py', 'reference_store.py', 'business_evidence.py', 'incremental.py', 'runner.py', 'PROGRESSIVE_PROTOCOL.md']:
        shutil.copyfile(Path(__file__).parent/name, series/name)
    if a.backend=='local':
        shutil.copyfile(Path(__file__).parent/'LOCAL_PROTOCOL.md',series/'LOCAL_PROTOCOL.md')
        model_info=REPO/'tmp/skill-boundary-local/model-show.json'
        if model_info.exists():shutil.copyfile(model_info,series/'local-model-show.json')
    save(series/'registry.json', rows); save(series/'fixtures.json', cases)
    save(series/'protocol.json', {'sizes': a.sizes, 'suite': a.suite, 'variant':a.variant, 'schema_ids':a.schema_ids, 'repeats': 2,
        'promotion': f'{len(cases)*2}/{len(cases)*2} only', 'planner_rounds': 16,
        'native_control_tools': 3 if a.planner_artifacts=='receipts' else 2, 'visible_review_required':True, 'exposure':a.exposure,
        'planner_artifacts':a.planner_artifacts,
        'strict_feedback_csv':a.strict_feedback_csv,
        'short_circuit_hard_failure':a.short_circuit_hard_failure,
        'backend':a.backend,'local_context':a.local_context if a.backend=='local' else None,
        'reference_payload':'content-once','numeric_evidence':'line_ids_v2','csv_shape_check':True,
        'visible_unsupported_feedback':True,
        'attempt_failure_scope':'unsupported-and-execution-errors',
        'controller_state_feedback':True,'visible_protocol_recovery':True,
        'model':LocalAPI(context=a.local_context).model if a.backend=='local' else API().model,
        'temperature':'per-mode recommended' if a.backend=='local' and a.local_sampling=='qwen-recommended' else 0.2,
        'local_sampling':a.local_sampling,'thinking':a.local_thinking if a.backend=='local' else 'disabled',
        'local_planner':a.local_planner,'planner_transport':'schema-constrained-json' if a.local_planner=='structured' else 'native-tool-calling',
        'local_gpu_layers':a.local_gpu_layers,
        'allow_small_baseline':a.allow_small_baseline,
        'critical_first':a.critical_first,'fail_fast':a.fail_fast,'hidden_retries': 0})
    ledger = {'prefix': a.prefix, 'last_fully_passed_size': None, 'stages': [], 'status': 'running'}
    save(series/'series.json', ledger)
    for size in a.sizes:
        if size > len(rows):
            ledger['status'] = 'pool_exhausted'; break
        if STOP_NETWORK.is_set():
            ledger['status'] = 'resource_blocked'; break
        jobs = [(case, repeat) for case in cases for repeat in [1, 2]]
        if a.critical_first:jobs.sort(key=lambda j:({'event':0,'competition':1}.get(j[0]['id'],2),cases.index(j[0]),j[1]))
        save(series/f'n{size:03}-planned-jobs.json',[{'case':c['id'],'repeat':r} for c,r in jobs])
        def run(job):return run_one(series,rows[:size],*job,variant=a.variant,schema_ids=a.schema_ids,
            backend=a.backend,local_context=a.local_context,exposure=a.exposure,local_thinking=a.local_thinking,local_sampling=a.local_sampling,local_planner=a.local_planner,local_gpu_layers=a.local_gpu_layers,planner_artifacts=a.planner_artifacts,strict_feedback_csv=a.strict_feedback_csv,short_circuit_hard_failure=a.short_circuit_hard_failure)
        if a.fail_fast:
            results=[]
            for job in jobs:
                result=run(job);results.append(result)
                if not result['passed']:break
        else:
            with ThreadPoolExecutor(max_workers=1 if a.backend=='local' else 2) as pool:results=list(pool.map(run,jobs))
        passed = stage_passes(results, [c['id'] for c in cases], 2)
        stage = {'size': size, 'passed': sum(r['passed'] for r in results), 'planned': len(jobs),
                 'completed':len(results),
                 'fully_passed': passed, 'results': results}
        ledger['stages'].append(stage)
        if passed:
            ledger['last_fully_passed_size'] = size
        else:
            ledger['status'] = 'resource_blocked' if STOP_NETWORK.is_set() else 'stopped_at_failed_stage'
            ledger['first_failed_size'] = size
        save(series/'series.json', ledger)
        print('STAGE',size,'passed',stage['passed'],'executed',len(results),'planned',len(jobs),'PROMOTE' if passed else 'STOP',flush=True)
        if not passed:
            break
    else:
        ledger['status'] = 'all_planned_sizes_passed'
    save(series/'series.json', ledger)


if __name__ == '__main__':
    main()
