"""Recompute local qualification evidence without any model calls."""
import argparse
import hashlib
import json
from pathlib import Path
from local_qualification import validate_case, validate_verdict, extend_registry
from runner import read, save


def audit(root,partial=False,reviewed=False):
    ledger=read(root/'ledger.json');candidates=read(root/'candidates.json');original=read(root/'original.json')
    fixed=read(root/'fixed-cases.json') if (root/'fixed-cases.json').exists() else None
    protocol=read(root/'protocol.json')
    reviews=read(root/'agent-review.json')['reviews'] if reviewed else {}
    if not partial:assert ledger['status']=='finished', 'qualification batch is not terminal complete'
    assert len(ledger['results'])==ledger['completed']<=ledger['planned']==len(candidates)
    accepted=[];responses=0
    for index,result in enumerate(ledger['results']):
        row=candidates[index];folder=root/row['tool_name']
        assert read(folder/'summary.json')==result and result['tool_name']==row['tool_name']
        source=Path(row['path']).read_bytes()
        assert hashlib.sha256(source).hexdigest()==row['sha256']==result['source_sha256']
        direct=reviews.get(row['tool_name'],{})
        if (direct.get('decision')!='include' if reviewed else not result['passed']):continue
        text=source.decode('utf-8-sig');case=read(folder/'case.json');answer=read(folder/'artifact.json');verdict=read(folder/'verdict.json')
        actual_grade=direct['manual_verdict'] if reviewed else verdict
        assert validate_case(case,text) and answer['status']=='done' and validate_verdict(actual_grade,answer['artifact'])
        expected_hard={x:x.casefold() in answer['artifact'].casefold() for x in case.get('required_literals',[])}
        assert all(expected_hard.values())
        if (folder/'deterministic-checks.json').exists():
            assert read(folder/'deterministic-checks.json')==expected_hard==result['deterministic_checks']
        assert (folder/'artifact.md').read_text(encoding='utf-8')==answer['artifact']
        assert hashlib.sha256(answer['artifact'].encode()).hexdigest()==result['artifact_sha256']
        origins=[('case',case),('skill',answer),('judge',verdict)]
        if fixed is not None:
            assert case==fixed[row['name']]
            assert read(folder/'case-origin.json')['kind']=='fixed_source_grounded_case'
            assert not (folder/'case.request.json').exists(), 'fixed case must not be redesigned by the model'
            origins=[('skill',answer),('judge',verdict)]
        for stem,actual in origins:
            assert not (folder/(stem+'.error.json')).exists()
            req=read(folder/(stem+'.request.json'));native=read(folder/(stem+'.native.json'))
            normalized=read(folder/(stem+'.response.json'))
            assert req['model']=='qwen3.5:9b' and req['think'] is False and req['stream'] is False
            assert req['options']['num_ctx']==32768 and req['options']['num_gpu']==24
            if protocol.get('server_truncate') is False:assert req['truncate'] is False and req['shift'] is False
            assert native['done'] is True and native['done_reason']=='stop'
            assert json.loads(native['message']['content'])==actual
            assert json.loads(normalized['choices'][0]['message']['content'])==actual
            responses+=1
        assert text in read(folder/'skill.request.json')['messages'][0]['content']
        worker_input=json.loads(read(folder/'skill.request.json')['messages'][1]['content'])
        assert worker_input=={'request':case['request'],'facts':case['facts']}
        judge_input=json.loads(read(folder/'judge.request.json')['messages'][1]['content'])
        assert judge_input=={'source_skill':text,'case':case,'actual':answer}
        accepted.append({**row,'local_qualification_evidence':str(folder/'summary.json')})
    expanded=read(root/('reviewed-registry.json' if reviewed else 'expanded-registry.json'))
    expected=extend_registry(original,accepted)
    # Absolute evidence paths are compared after resolution to permit a relative audit CLI path.
    assert len(expanded)==len(expected)
    for a,b in zip(expanded,expected):
        a=dict(a);b=dict(b)
        if reviewed:
            a.pop('artifact_sha256',None);a.pop('agent_review_evidence',None)
        if 'local_qualification_evidence' in a:
            assert Path(a.pop('local_qualification_evidence')).resolve()==Path(b.pop('local_qualification_evidence')).resolve()
        assert a==b
    if not reviewed:assert ledger['passed']==len(accepted)
    else:
        from boundary_scan import validate_extension
        assert validate_extension(original,expanded)
    report={'status':ledger['status'],'audit_passed':True,'partial':partial,'completed':ledger['completed'],
        'planned':ledger['planned'],'qualified_new':len(accepted),'original':len(original),'expanded':len(expanded),
        'checked_positive_model_responses':responses,'reviewed':reviewed,
        'scope':'physical/provenance and exact quote audit; semantic judgement remains model-dependent'}
    label='audit-reviewed' if reviewed else 'audit'
    save(root/(label+('-partial' if partial else '')+'.json'),report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--partial',action='store_true');p.add_argument('--reviewed',action='store_true');a=p.parse_args()
    print(json.dumps(audit(a.root,a.partial,a.reviewed),ensure_ascii=False,indent=2))
