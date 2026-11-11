"""Traceable local-only qualification; new sources never overwrite the old library."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from local_api import LocalAPI
from runner import BASE, REPO, read, save


def case_schema(source):
    quotes=list(dict.fromkeys(line.strip() for line in source.splitlines()
        if 20<=len(line.strip())<=220 and not line.strip().startswith(('#','```','name:','source_'))))[:80]
    if not quotes:raise ValueError('no usable source evidence span')
    properties={
        'eligible':{'type':'boolean'},'request':{'type':'string','maxLength':500},
        'facts':{'type':'object'},'checks':{'type':'array','minItems':3,'maxItems':3,'items':{'type':'string'}},
        'scope':{'type':'string'},'boundary':{'type':'string'},'reason':{'type':'string'},
        'source_quote':{'type':'string','enum':quotes}}
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def judge_schema(actual):
    quotes=list(dict.fromkeys(line.strip() for line in actual.splitlines() if 5<=len(line.strip())<=500))[:100]
    if not quotes:raise ValueError('no usable actual artifact evidence span')
    evidence={'type':'object','properties':{'check':{'type':'string','enum':['1','2','3']},
        'quote':{'type':'string','enum':quotes}},'required':['check','quote'],'additionalProperties':False}
    props={'passed':{'type':'boolean'},'checks':{'type':'object','properties':{str(i):{'type':'boolean'} for i in range(1,4)},
        'required':['1','2','3'],'additionalProperties':False},'errors':{'type':'array','items':{'type':'string'}},
        'evidence':{'type':'array','minItems':3,'maxItems':3,'items':evidence}}
    return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}


def validate_case(case, source):
    return (isinstance(case,dict) and case.get('eligible') is True
        and isinstance(case.get('request'),str) and 0<len(case['request'])<=500
        and isinstance(case.get('facts'),dict) and bool(case['facts'])
        and len(json.dumps(case['facts'],ensure_ascii=False))<=2200
        and isinstance(case.get('checks'),list) and len(case['checks'])==3
        and all(isinstance(c,str) and c.strip() for c in case['checks'])
        and isinstance(case.get('scope'),str) and bool(case['scope'].strip())
        and isinstance(case.get('boundary'),str) and bool(case['boundary'].strip())
        and isinstance(case.get('source_quote'),str) and len(case['source_quote'])>=8
        and case['source_quote'] in source)


def validate_verdict(verdict, actual):
    if not (isinstance(verdict,dict) and verdict.get('passed') is True
            and isinstance(verdict.get('checks'),dict)
            and set(verdict['checks'])=={'1','2','3'}
            and all(v is True for v in verdict['checks'].values())
            and verdict.get('errors')==[] and isinstance(verdict.get('evidence'),list)):
        return False
    supported=set()
    for e in verdict['evidence']:
        if not isinstance(e,dict) or not isinstance(e.get('quote'),str) or not e['quote'].strip() or e['quote'] not in actual:
            return False
        supported.add(e.get('check'))
    return supported=={'1','2','3'}


def extend_registry(original, additions):
    result=[];seen={k:set() for k in ['tool_name','sha256','normalized_sha256']}
    for row in original+additions:
        for key in seen:
            value=row[key]
            if not value or value in seen[key]:raise ValueError('duplicate or absent '+key)
            seen[key].add(value)
        result.append(row)
    return result


def qualify(api,row,folder,fixed_case=None,typed_worker=False):
    folder.mkdir(parents=True,exist_ok=False)
    result={'name':row['name'],'tool_name':row['tool_name'],'passed':False,
        'source_sha256':row['sha256'],'source_url':row['source_url'],
        'evidence_dir':str(folder),'backend':'local','model':api.model,
        'scope':'one local smoke test only, not exhaustive certification'}
    try:
        data=Path(row['path']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('source hash changed')
        source=data.decode('utf-8-sig');save(folder/'source.json',row)
        case,_=(json.loads(json.dumps(fixed_case,ensure_ascii=False)),{}) if fixed_case is not None else api.call([{'role':'system','content':
            '为原始Skill设计一个最小的真实功能测试。只可用本地语言模型、给定文本和Python标准库；本次执行器仅生成文本/代码，不能运行脚本或访问云服务。'
            '若原Skill核心必须依赖未提供工具、网络、真实项目目录或服务账号，则eligible=false，不能换成写计划冒充其核心能力。'
            '若原文支持独立写作、解释、审查或设计，可用充分给定的小文档/代码片段作输入。数据全虚构，最多3条记录。'
            'request不超过300字，facts不超过1200字；必须有一个边界条件，3条可核查标准。'
            'request必须是终端用户要完成的业务工作，不要写成设计测试/验证技能的元任务。request与facts必须相互一致、输入充分；facts不得给出预设判断结论或答案。'
            '不要提供答案或预设角色/流程。输出JSON：eligible(bool),request(str),facts(object),checks(3个字符串),scope(str),'
            'boundary(str),source_quote(原文连续逐字引用，8到160字符，证明所测能力),reason(str)。'},
            {'role':'user','content':source}],folder/'case',json_mode=case_schema(source),max_tokens=1600)
        save(folder/'case.json',case)
        save(folder/'case-origin.json',{'kind':'fixed_source_grounded_case' if fixed_case is not None else 'local_model_designed_case',
            'case_sha256':hashlib.sha256(json.dumps(case,ensure_ascii=False,sort_keys=True).encode()).hexdigest()})
        if not validate_case(case,source):raise ValueError('ineligible or invalid source-grounded local case')
        answer,_=api.call([{'role':'system','content':
            '按下列原始Skill完成用户请求，仅用给定事实。本机执行器可以生成文本/代码，不能执行脚本、联网或使用外部账号。'
            '不具备主要所需能力时status=unsupported。不能以建议替代用户要求执行的核心操作，不得声称已运行、发送或上线。'
            '给出可直接核对的完整且精简产物。输出JSON：status(done/unsupported),artifact(str),limitations(array)。'
            '\n<SKILL>\n'+source+'\n</SKILL>'},
            {'role':'user','content':json.dumps({'request':case['request'],'facts':case['facts']},ensure_ascii=False)}],
            folder/'skill',json_mode=({'type':'object','properties':{'status':{'type':'string','enum':['done','unsupported']},
                'artifact':{'type':'string'},'limitations':{'type':'array','items':{'type':'string'}}},
                'required':['status','artifact','limitations'],'additionalProperties':False} if typed_worker else True),max_tokens=2300)
        save(folder/'artifact.json',answer)
        actual=answer.get('artifact')
        if answer.get('status')!='done' or not isinstance(actual,str) or not actual.strip():raise ValueError('unsupported or empty actual output')
        (folder/'artifact.md').write_text(actual,encoding='utf-8')
        verdict,_=api.call([{'role':'system','content':
            '独立严格验收原Skill一次实际执行。检查请求与原核心能力一致、3条标准和边界条件全部满足、没有编造事实/已执行证据。'
            '仅承诺或给计划而未交付用户需要的产物即失败。不要偏向通过。输出JSON：passed(bool),checks({"1":bool,"2":bool,"3":bool}),'
            'errors(array),evidence([{check:"1"/"2"/"3",quote:从实际artifact连续逐字引用的简短证据}])。每条必须有证据，引用不能改写。'},
            {'role':'user','content':json.dumps({'source_skill':source,'case':case,'actual':answer},ensure_ascii=False)}],
            folder/'judge',json_mode=judge_schema(actual),max_tokens=1300)
        save(folder/'verdict.json',verdict)
        required=case.get('required_literals',[])
        if not isinstance(required,list) or not all(isinstance(x,str) and x for x in required):raise ValueError('invalid hard-check literals')
        hard={x:x.casefold() in actual.casefold() for x in required};save(folder/'deterministic-checks.json',hard)
        result.update(passed=validate_verdict(verdict,actual) and all(hard.values()),checks=verdict.get('checks'),errors=verdict.get('errors'),
            deterministic_checks=hard,
            tested_scope=case['scope'],artifact_sha256=hashlib.sha256(actual.encode()).hexdigest())
    except Exception as exc:result['error']=str(exc)[:1000]
    save(folder/'summary.json',result)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--prefix',required=True);p.add_argument('--names',type=Path,required=True)
    p.add_argument('--cases',type=Path,help='pre-frozen source-grounded business cases; never generated or repaired by the worker')
    p.add_argument('--typed-worker',action='store_true',help='schema-constrain the existing status/text/limitations container; no constrained business answer')
    p.add_argument('--original',type=Path,default=BASE/'progressive/local-single-receipts-native-c/registry.json')
    args=p.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',args.prefix):raise ValueError('invalid prefix')
    target=BASE/'local-qualification'/args.prefix
    wanted=read(args.names);catalog=read(REPO/'tmp/skillfabri-spike/scale/registry.json')
    by={r['name']:r for r in catalog};original=read(args.original)
    fixed_cases=read(args.cases) if args.cases else None
    if fixed_cases is not None and any(n not in fixed_cases for n in wanted):raise ValueError('missing fixed case')
    candidates=[{**by[n],'tool_name':re.sub('[^a-zA-Z0-9_-]','_',n)[:110],
        'qualification_mode':'source-native local text/document capability only'} for n in wanted]
    extend_registry(original,candidates)
    if target.exists():
        if read(target/'candidates.json')!=candidates or read(target/'original.json')!=original:raise ValueError('resume inputs changed')
        if (target/'fixed-cases.json').exists()!=bool(args.cases):raise ValueError('case protocol changed')
        if args.cases and read(target/'fixed-cases.json')!=fixed_cases:raise ValueError('fixed cases changed during resume')
        if read(target/'protocol.json').get('typed_worker',False)!=args.typed_worker:raise ValueError('worker protocol changed during resume')
    else:
        target.mkdir(parents=True);save(target/'candidates.json',candidates);save(target/'original.json',original)
        if args.cases:shutil.copyfile(args.cases,target/'fixed-cases.json')
        for f in ['local_qualification.py','local_api.py']:shutil.copyfile(Path(__file__).parent/f,target/f)
        save(target/'protocol.json',{'backend':'local','model':'qwen3.5:9b','context':32768,'gpu_layers':24,
            'thinking':'off','sampling':'legacy','hidden_retries':0,'paid_api':False,
            'server_truncate':False,'server_shift':False,
            'case_source_evidence':'JSON Schema enum of actual source substrings; no fabricated quote repair',
            'judge_artifact_evidence':'JSON Schema enum of actual artifact substrings; no stitched or paraphrased quote repair',
            'case_origin':'fixed_source_grounded_business_cases' if args.cases else 'local_model_designed_cases',
            'typed_worker':args.typed_worker,
            'qualification':'source-grounded case, actual worker, isolated judge plus exact quote validation'})
    api=LocalAPI(gpu_layers=24);results=[];additions=[]
    for row in candidates:
        if (target/'STOP_AFTER_CURRENT').exists():
            save(target/'ledger.json',{'status':'stopped_after_current','planned':len(candidates),
                'completed':len(results),'passed':len(additions),'results':results})
            return
        folder=target/row['tool_name'];summary=folder/'summary.json'
        if summary.exists():r=read(summary)
        elif folder.exists():raise RuntimeError('partial attempt preserved; inspect before resuming: '+str(folder))
        else:r=qualify(api,row,folder,fixed_case=fixed_cases[row['name']] if fixed_cases is not None else None,typed_worker=args.typed_worker)
        results.append(r)
        if r['passed']:additions.append({**row,'local_qualification_evidence':str(summary)})
        save(target/'ledger.json',{'status':'running','planned':len(candidates),'completed':len(results),
            'passed':len(additions),'results':results})
        save(target/'expanded-registry.json',extend_registry(original,additions))
        print('LOCAL_QUALIFICATION',row['name'],r['passed'],r.get('error',''),flush=True)
    save(target/'ledger.json',{'status':'finished','planned':len(candidates),'completed':len(results),
        'passed':len(additions),'results':results})


if __name__=='__main__':main()
