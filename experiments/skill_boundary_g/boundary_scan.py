"""Frozen expanded-library boundary observations; no weakening of business gates."""
import argparse
import copy
import hashlib
from pathlib import Path
import re
import shutil
from local_qualification import extend_registry,validate_verdict
from progressive import run_one
from incremental import stage_passes
from runner import BASE,read,save


def validate_calibration(root):
    ledger=read(root/'ledger.json');protocol=read(root/'protocol.json')
    results=ledger.get('results',[]);planned=ledger.get('planned',0)
    if (ledger.get('status')!='all_cases_finished' or planned<5
            or ledger.get('completed')!=planned or len(results)!=planned
            or ledger.get('matched')!=planned
            or any(type(r.get('predicted_passed')) is not bool or r.get('error')
                   or r.get('predicted_passed') is not r.get('expected_passed')
                   or r.get('matches_expected') is not True for r in results)
            or protocol.get('backend')!='local' or protocol.get('thinking')!='off'
            or protocol.get('model_input_view_version')!='f-stable-logical-v1'
            or protocol.get('sampling')!='qwen-recommended'):
        raise ValueError('fact-evidence review needs complete successful known-case calibration')
    for name in ['semantic_review.py','progressive.py','local_api.py','calibrate_semantic_review.py','extended_release_facts.py','release_fact_issues.py','reference_store.py','planner_receipts.py','incremental.py']:
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest():
            raise ValueError('review implementation differs from calibrated version')
    return True


def validate_extension(original,rows,loader=read):
    if len(rows)<len(original) or rows[:len(original)]!=original:raise ValueError('original registry prefix changed')
    extend_registry(original,rows[len(original):])
    for row in rows[len(original):]:
        proof=loader(Path(row['local_qualification_evidence']))
        if (proof.get('backend')!='local' or proof.get('error')
                or proof.get('source_sha256')!=row['sha256'] or proof.get('tool_name')!=row['tool_name']):
            raise ValueError('unproven new callable Skill')
        review=loader(Path(row['agent_review_evidence']))['reviews'][row['tool_name']]
        if (review.get('decision')!='include' or not review.get('reason')
                or review.get('source_sha256')!=row['sha256']
                or review.get('artifact_sha256')!=proof.get('artifact_sha256')
                or row.get('artifact_sha256')!=proof.get('artifact_sha256')):
            raise ValueError('new Skill not accepted by direct source/case/artifact review')
        actual=loader(Path(row['local_qualification_evidence']).parent/'artifact.json')
        if (actual.get('status')!='done' or not isinstance(actual.get('artifact'),str)
                or hashlib.sha256(actual['artifact'].encode()).hexdigest()!=proof['artifact_sha256']
                or not all(proof.get('deterministic_checks',{}).values())
                or not validate_verdict(review.get('manual_verdict'),actual['artifact'])):
            raise ValueError('direct review lacks matching actual evidence or hard checks')
        if proof.get('passed') is not True and review.get('overrides_automatic_verdict') is not True:
            raise ValueError('automatic rejection must be explicitly adjudicated, never silently promoted')
    return True


def summarize_stage(size,results,repeats,case_id):
    return {'size':size,'passed':sum(r['passed'] for r in results),'completed':len(results),'planned':repeats,
        'fully_passed':stage_passes(results,[case_id],repeats),'results':copy.deepcopy(results)}


def main():
    p=argparse.ArgumentParser();p.add_argument('--prefix',required=True);p.add_argument('--registry',required=True,type=Path)
    p.add_argument('--source',default='local-single-receipts-native-c');p.add_argument('--sizes',nargs='+',required=True,type=int)
    p.add_argument('--repeats',default=3,type=int);p.add_argument('--context',default=32768,type=int)
    p.add_argument('--release-fact-guard',action='store_true')
    p.add_argument('--candidate-order',choices=['shuffled','frozen'],default='shuffled')
    p.add_argument('--paired-seeds',action='store_true')
    p.add_argument('--semantic-review-profile',choices=['legacy','fact-evidence'],default='legacy')
    p.add_argument('--semantic-calibration',type=Path)
    a=p.parse_args()
    if a.semantic_review_profile=='fact-evidence':
        if a.semantic_calibration is None:raise ValueError('fact-evidence profile requires calibration evidence')
        validate_calibration(a.semantic_calibration)
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',a.prefix):raise ValueError('invalid prefix')
    source=BASE/'progressive'/a.source;original=read(source/'registry.json');rows=read(a.registry)
    validate_extension(original,rows)
    for row in rows:
        if hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()!=row['sha256']:raise ValueError('source content changed')
    if a.sizes!=sorted(set(a.sizes)) or min(a.sizes)<5 or max(a.sizes)>len(rows) or a.repeats<2:
        raise ValueError('invalid boundary sizes or repetition count')
    config=read(source/'protocol.json');cases=read(source/'fixtures.json')
    if len(cases)!=1 or config['backend']!='local' or config.get('full_task_family') is not False:
        raise ValueError('retain exact original single-case local protocol')
    config.update(scope='expanded callable library repeated boundary observations; not universal model limit',
        sizes=a.sizes,repeats=a.repeats,local_context=a.context,promotion='independent observations, every failure counted',
        source_exploration=str(source),expanded_registry_source=str(a.registry),continue_after_failure=True,
        parallel_other_experiment=None,server_truncate=False,server_shift=False,strict_release_facts=a.release_fact_guard,
        candidate_order=a.candidate_order,paired_seeds=a.paired_seeds)
    config.update(semantic_review_profile=a.semantic_review_profile,
        model_input_view_version='f-stable-logical-v1',worker_source_scope='post-source-v1',
        semantic_review_thinking='off' if a.semantic_review_profile=='fact-evidence' else None,
        strict_blank_csv_records=a.semantic_review_profile=='fact-evidence',
        semantic_calibration=str(a.semantic_calibration) if a.semantic_calibration else None)
    target=BASE/'progressive'/a.prefix;target.mkdir(parents=True,exist_ok=False)
    save(target/'protocol.json',config);save(target/'registry.json',rows);save(target/'fixtures.json',cases)
    for path in Path(__file__).parent.iterdir():
        if path.is_file() and (path.suffix=='.py' or path.name in ['LOCAL_PROTOCOL.md','PROGRESSIVE_PROTOCOL.md']):
            shutil.copyfile(path,target/path.name)
    ledger={'prefix':a.prefix,'scope':config['scope'],'status':'running','stages':[],
        'largest_passing_single_case_size':None,'largest_fully_passing_observed_size':None}
    save(target/'series.json',ledger);case=cases[0]
    for size in a.sizes:
        results=[];ledger['stages'].append(summarize_stage(size,results,a.repeats,case['id']))
        save(target/f'n{size:03}-planned-jobs.json',[{'case':case['id'],'repeat':r} for r in range(1,a.repeats+1)])
        save(target/'series.json',ledger)
        for repeat in range(1,a.repeats+1):
            result=run_one(target,rows[:size],case,repeat,variant='grounded',schema_ids='controls-only',backend='local',
                local_context=a.context,exposure=config['exposure'],local_thinking=config['thinking'],
                local_sampling=config['local_sampling'],local_planner=config['local_planner'],
                local_gpu_layers=config['local_gpu_layers'],planner_artifacts=config['planner_artifacts'],
                strict_feedback_csv=config['strict_feedback_csv'],short_circuit_hard_failure=config['short_circuit_hard_failure'],
                strict_release_facts=a.release_fact_guard,candidate_order=a.candidate_order,
                local_seed=repeat if a.paired_seeds else None,semantic_review_profile=a.semantic_review_profile)
            results.append(result);ledger['stages'][-1]=summarize_stage(size,results,a.repeats,case['id'])
            if result['passed']:ledger['largest_passing_single_case_size']=size
            save(target/'series.json',ledger)
            print('BOUNDARY',size,repeat,result['passed'],result.get('error'),flush=True)
        if ledger['stages'][-1]['fully_passed']:ledger['largest_fully_passing_observed_size']=size
    ledger['status']='all_boundary_trials_finished';save(target/'series.json',ledger)


if __name__=='__main__':main()
