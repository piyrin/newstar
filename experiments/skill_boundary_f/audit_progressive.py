"""Recompute physical evidence, exact dependencies and the promotion gate offline."""
import argparse
import hashlib
import json
from pathlib import Path
from runner import read, save
from progressive import physical_checks, qualified
from incremental import stage_passes
from business_evidence import validate_event_evidence
from reference_store import model_reference,model_feedback


def observed_stages(series,ledger,case_ids,repeats,include_incomplete=False):
    stages=[s for s in ledger['stages'] if s.get('results')] if include_incomplete else list(ledger['stages'])
    if not include_incomplete:return stages
    committed={s['size'] for s in stages}
    for folder in sorted(series.glob('n[0-9][0-9][0-9]')):
        size=int(folder.name[1:])
        if size in committed:continue
        results=[read(p) for p in sorted(folder.glob('*/summary.json'))]
        if not results:continue
        stages.append({'size':size,'results':results,'passed':sum(r['passed'] for r in results),
            'planned':len(case_ids)*repeats,'fully_passed':stage_passes(results,case_ids,repeats),
            'pending_stage_record':True})
    return sorted(stages,key=lambda s:s['size'])


def audit(series,include_incomplete=False):
    ledger=read(series/'series.json'); protocol=read(series/'protocol.json')
    assert protocol.get('model_input_view_version')=='f-stable-logical-v1', 'F audit requires an explicitly versioned F run'
    assert protocol.get('worker_source_scope')=='post-source-v1', 'F worker source scope missing'
    registry=read(series/'registry.json'); source={r['tool_name']:r for r in registry}
    for row in registry:
        assert hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()==row['sha256'], row['tool_name']
    checked_nodes=0; checked_files=set(); responses=0; replayed_responses=0; usage={}; stages=[]
    cases=read(series/'fixtures.json')
    observed=observed_stages(series,ledger,[c['id'] for c in cases],protocol['repeats'],include_incomplete)
    for stage in observed:
        results=[]
        for result in stage['results']:
            folder=series/f"n{stage['size']:03}"/f"{result['case']}-r{result['repeat']}"
            assert read(folder/'summary.json')==result
            profile=protocol.get('semantic_review_profile','legacy')
            assert result.get('semantic_review_profile','legacy')==profile
            assert result.get('model_input_view_version')=='f-stable-logical-v1'
            assert result.get('worker_source_scope')=='post-source-v1'
            case=read(folder/'case.json'); assert case==next(c for c in cases if c['id']==case['id'])
            if protocol.get('server_truncate') is False:
                for request in folder.rglob('*.request.json'):
                    payload=read(request)
                    if payload.get('model')!=protocol['model']:continue
                    assert payload.get('truncate') is False and payload.get('shift') is False
                    if protocol.get('paired_seeds'):assert payload['options'].get('seed')==result['repeat']
                    if result['passed']:
                        raw=read(request.with_name(request.name.replace('.request.json','.native.json')))
                        assert raw.get('done') is True and raw.get('done_reason')=='stop'
                        assert raw.get('prompt_eval_count',0)+raw.get('eval_count',0)<payload['options']['num_ctx']
            nodes=read(folder/'dag.json') if (folder/'dag.json').exists() else []
            references={}; depths={}
            for n in nodes:
                record=read(folder/'artifacts'/(n['id']+'.json'))
                stem=n.get('execution_request_stem',f"skill-{n['id']}")
                req=read(folder/(stem+'.request.json'))
                body=json.loads(req['messages'][1]['content'])
                assert body['facts']==case['facts']
                expected=[references[r] for r in n['input_reference_ids']]
                model_expected=[model_reference(r) for r in expected] if protocol.get('reference_payload')=='content-once' else expected
                assert body['actual_upstream_artifacts']==model_expected
                assert n['depends_on']==list(dict.fromkeys(r['producer_node_id'] for r in expected))
                assert n['depth']==1+max((depths[p] for p in n['depends_on']),default=0)
                original=Path(source[n['skill']]['path']).read_text(encoding='utf-8',errors='replace')
                assert original in req['messages'][0]['content']
                if protocol.get('planner_artifacts')=='receipts':
                    from planner_receipts import receipt_result
                    assert read(folder/(stem+'.planner-result.json'))==receipt_result(record)
                    raw_output=read(folder/(stem+'.response.json'))['choices'][0]['message']['content']
                    document=next(r for r in record['outputs'] if r['kind']=='document')
                    assert document['content']==raw_output, 'stored body must be the actual model output, without host rewriting'
                for ref in record['outputs']:
                    assert Path(ref['path']).read_text(encoding='utf-8-sig')==ref['content']
                    assert ref['reference_id'] not in references
                    for file in ref['files']:
                        assert hashlib.sha256(Path(file['path']).read_bytes()).hexdigest()==file['sha256']
                        checked_files.add(file['path'])
                    references[ref['reference_id']]=ref
                depths[n['id']]=n['depth']; checked_nodes+=1
            assert result['nodes']==len(nodes)
            assert result['actual_skills']==len({n['skill'] for n in nodes})
            assert result['chain']==max(depths.values(),default=0)
            combo=len({n['skill'] for n in nodes})>=2 and any(n['depends_on'] for n in nodes)
            assert result['combination_evidence']==combo
            if protocol.get('visible_unsupported_feedback'):
                attempts=read(folder/'skill-attempts.json') if (folder/'skill-attempts.json').exists() else []
                assert len(attempts)==result['skill_call_attempts']
                failure_states={'unsupported','execution_error'} if protocol.get('attempt_failure_scope')=='unsupported-and-execution-errors' else {'unsupported'}
                assert sum(a['status'] in failure_states for a in attempts)==result['failed_skill_calls']
                assert len({a['skill'] for a in attempts})==result['attempted_skills']
                assert {a.get('node_id') for a in attempts if a['status']=='done'}=={n['id'] for n in nodes}
                assert len({a['execution_request_stem'] for a in attempts})==len(attempts)
            if result['passed']:
                manifest=read(folder/'manifest.json'); selected={}
                for item in manifest['deliverables']:
                    for ident in item['reference_ids']:selected[ident]=references[ident]
                hard=physical_checks(case,selected,check_csv_shape='csv_assets_rectangular' in result['physical_checks'],strict_feedback_csv=protocol.get('strict_feedback_csv',False),strict_release_facts=protocol.get('strict_release_facts',False),strict_blank_csv=profile=='fact-evidence',extended_release_claims=profile=='fact-evidence')
                if 'actual_skill_composition' in result['physical_checks']:
                    hard['actual_skill_composition']=combo
                if (folder/'business-evidence.json').exists():
                    hard.update(validate_event_evidence(case['facts'],'\n\n'.join(r['content'] for r in selected.values()),read(folder/'business-evidence.json')))
                assert result['physical_checks']==hard and all(hard.values())
                assert qualified(read(folder/'verdict.json')) and combo
                if profile=='fact-evidence':
                    from semantic_review import review_input,resolve_evidence
                    payload,lines=review_input(case,selected)
                    assert read(folder/'semantic-review-input.json')==payload
                    assert read(folder/'semantic-evidence.json')==resolve_evidence(read(folder/'verdict.json'),case,lines)
                    req=read(folder/'verifier.request.json')
                    review_thinks=protocol.get('semantic_review_thinking','all')=='all'
                    assert req['think'] is review_thinks
                    assert req['options']['temperature']==(1.0 if review_thinks else 0.7)
                    assert req['options']['presence_penalty']==1.5
                    assert json.loads(req['messages'][1]['content'])==payload
                if protocol.get('visible_review_required'):
                    reviews=read(folder/'control-calls.json')
                    assert len(reviews)==result['review_calls']
                    assert any(r['feedback']['passed'] and {i for d in r['manifest']['deliverables'] for i in d['reference_ids']}==set(selected) for r in reviews)
            for path in folder.rglob('*.response.json'):
                responses+=1
                replay_path=path.with_name(path.name.replace('.response.json','.replay.json'))
                if replay_path.exists():
                    from resume_local import relocate
                    replay=read(replay_path);old=Path(replay['source'])
                    assert replay['new_model_call'] is False and replay['request_verified'] is True
                    assert read(path)==read(old)
                    old_trial=Path(result['resumed_from'])
                    request_path=path.with_name(path.name.replace('.response.json','.request.json'))
                    old_request=old.with_name(old.name.replace('.response.json','.request.json'))
                    assert relocate(read(request_path),folder.resolve(),old_trial.resolve())==read(old_request)
                    replayed_responses+=1
                for key,value in read(path).get('usage',{}).items():
                    if type(value) is int:usage[key]=usage.get(key,0)+value
            initial=folder/'planner-00.request.json'
            if not initial.exists():
                assert not result['passed'] and not nodes and result['error']=='network batch stopped after unavailable balance'
                results.append(result)
                continue
            first=read(initial)
            controls={'submit_deliverables'}
            if protocol.get('native_control_tools',1)>=2:controls.add('review_deliverables')
            if protocol.get('planner_artifacts')=='receipts':
                controls.add('read_artifacts')
                reads=read(folder/'artifact-reads.json') if (folder/'artifact-reads.json').exists() else []
                assert len(reads)==result['artifact_read_calls']
                for event in reads:
                    assert event['reference_ids'] and all(i in references for i in event['reference_ids'])
                # Verify what the model actually received, not only a saved sidecar.
                requests=sorted(folder.glob('planner-*.request.json'))
                history=read(requests[-1])['messages'];seen_receipts=set();seen_reads=[];seen_reviews=[]
                for message in history:
                    name=message.get('tool_name');content=message.get('content','')
                    if message['role']=='user':
                        try:wrapped=json.loads(content)
                        except (ValueError,TypeError):continue
                        if not isinstance(wrapped,dict) or wrapped.get('kind')!='actual_tool_result':continue
                        name=wrapped['name'];content=wrapped['content']
                    elif message['role']!='tool':continue
                    try:payload=json.loads(content)
                    except (ValueError,TypeError):continue
                    if not isinstance(payload,dict):continue
                    if payload.get('planner_view'):
                        node=next(n for n in nodes if n['id']==payload['producer_node_id'])
                        stem=node.get('execution_request_stem',f"skill-{node['id']}")
                        assert payload==read(folder/(stem+'.planner-result.json'))
                        seen_receipts.add(node['id'])
                    if name=='read_artifacts' and 'outputs' in payload:
                        ids=[r['reference_id'] for r in payload['outputs']]
                        assert payload['outputs']==[model_reference(references[i]) for i in ids]
                        seen_reads.append(ids)
                    if name=='review_deliverables' and 'physical_checks' in payload:
                        seen_reviews.append(payload)
                if result['passed']:
                    assert seen_receipts=={n['id'] for n in nodes}
                    assert seen_reads==[r['reference_ids'] for r in reads]
                    reviews=read(folder/'control-calls.json')
                    for review in reviews:
                        assert review['model_feedback']==model_feedback(review['feedback'],list(references.values()))
                    assert seen_reviews==[r['model_feedback'] for r in reviews]
            if protocol.get('planner_transport')=='schema-constrained-json':
                ts=read(folder/'planner-00.tools.json')
                assert 'tools' not in first and json.dumps(ts,ensure_ascii=False) in first['messages'][0]['content']
                for plan_path in folder.glob('planner-*.plan.json'):
                    plan=read(plan_path)
                    response_path=plan_path.with_name(plan_path.name.replace('.plan.json','.response.json'))
                    response=read(response_path)
                    actual=[{'name':c['function']['name'],'arguments':json.loads(c['function']['arguments'])}
                        for c in response['choices'][0]['message']['tool_calls']]
                    assert actual==plan['calls']
                    native_path=plan_path.with_name(plan_path.name.replace('.plan.json','.native.json'))
                    assert json.loads(read(native_path)['message']['content'])==plan
            else:ts=first['tools']
            assert len(ts)==stage['size']+len(controls)
            if protocol.get('candidate_order')=='frozen':
                assert [t['function']['name'] for t in ts[:stage['size']]]==[r['tool_name'] for r in registry[:stage['size']]]
            assert {t['function']['name'] for t in ts}=={r['tool_name'] for r in registry[:stage['size']]}|controls
            for t in ts:
                name=t['function']['name']
                if name in controls:continue
                if protocol.get('exposure')!='on-call':
                    assert Path(source[name]['path']).read_text(encoding='utf-8',errors='replace') in t['function']['description']
                else:assert source[name]['description'] in t['function']['description']
            results.append(result)
        full=stage_passes(results,[c['id'] for c in cases],protocol['repeats'])
        assert full==stage['fully_passed']
        assert sum(x['passed'] for x in results)==stage['passed']
        assert stage['planned']==len(cases)*protocol['repeats']
        stages.append({'size':stage['size'],'passed':stage['passed'],'planned':stage['planned'],
            'completed_trials':len(results),'fully_passed':full,'pending_stage_record':stage.get('pending_stage_record',False),
            'actual_skills_range':[min(x['actual_skills'] for x in results),max(x['actual_skills'] for x in results)],
            'nodes_range':[min(x['nodes'] for x in results),max(x['nodes'] for x in results)],
            'chain_range':[min(x['chain'] for x in results),max(x['chain'] for x in results)]})
    if not protocol.get('continue_after_failure'):
        for stage in ledger['stages'][:-1]:assert stage['fully_passed']
    report={'series':str(series),'stages':stages,'checked_nodes':checked_nodes,
            'checked_extra_files':len(checked_files),'model_responses':responses,
            'replayed_responses':replayed_responses,'new_model_responses':responses-replayed_responses,
            'usage':usage,'audit_passed':True}
    save(series/('audit-partial.json' if include_incomplete else 'audit.json'),report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('series',type=Path);p.add_argument('--include-incomplete',action='store_true');a=p.parse_args()
    print(json.dumps(audit(a.series,a.include_incomplete),ensure_ascii=False,indent=2))
