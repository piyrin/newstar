"""Exploratory single-case scaling, explicitly separate from 12/12 full-family results."""
import argparse
from pathlib import Path
import shutil
from progressive import ordered_registry,run_one,suite
from runner import BASE,read,save


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prefix',required=True)
    parser.add_argument('--sizes',nargs='+',type=int,default=[5,10,15,20,30,40,60,80,100,120,140,163])
    parser.add_argument('--local-planner',choices=['native','structured'],default='structured')
    parser.add_argument('--local-sampling',choices=['legacy','qwen-recommended'],default='qwen-recommended')
    parser.add_argument('--planner-artifacts',choices=['full','receipts'],default='full')
    parser.add_argument('--strict-feedback-csv',action='store_true')
    parser.add_argument('--continue-after-failure',action='store_true',help='independent observations, never promote a failed scale')
    parser.add_argument('--short-circuit-hard-failure',action='store_true')
    args=parser.parse_args();rows=ordered_registry();case=suite('release')[0]
    if args.sizes!=sorted(set(args.sizes)) or args.sizes[0]<5 or args.sizes[-1]>len(rows):raise ValueError('invalid nested candidate sizes')
    series=BASE/'progressive'/args.prefix;series.mkdir(parents=True,exist_ok=False)
    for name in ['progressive.py','local_api.py','structured_planner.py','planner_receipts.py','feedback_csv.py','reference_store.py','business_evidence.py','incremental.py','runner.py','probe_scale.py','LOCAL_PROTOCOL.md','PROGRESSIVE_PROTOCOL.md']:
        shutil.copyfile(Path(__file__).parent/name,series/name)
    save(series/'registry.json',rows);save(series/'fixtures.json',[case])
    protocol={'scope':'exploratory single release case only; never full-family stability or a universal upper limit',
        'suite':'single-release-case','full_task_family':False,'sizes':args.sizes,'repeats':1,'promotion':'1/1 fixed-case observation only',
        'planner_rounds':16,'native_control_tools':3 if args.planner_artifacts=='receipts' else 2,'visible_review_required':True,'exposure':'on-call','backend':'local',
        'local_context':32768,'reference_payload':'content-once','numeric_evidence':'line_ids_v2','csv_shape_check':True,
        'visible_unsupported_feedback':True,'attempt_failure_scope':'unsupported-and-execution-errors','controller_state_feedback':True,
        'visible_protocol_recovery':True,'model':'qwen3.5:9b','local_sampling':args.local_sampling,'thinking':'off',
        'local_planner':args.local_planner,'planner_transport':'schema-constrained-json' if args.local_planner=='structured' else 'native-tool-calling',
        'planner_artifacts':args.planner_artifacts,'local_gpu_layers':24,'hidden_retries':0,
        'strict_feedback_csv':args.strict_feedback_csv,
        'continue_after_failure':args.continue_after_failure,'short_circuit_hard_failure':args.short_circuit_hard_failure,
        'parallel_other_experiment':'local-qwen-schema-core-a; Ollama generation serialized by OLLAMA_NUM_PARALLEL=1'}
    save(series/'protocol.json',protocol)
    ledger={'prefix':args.prefix,'scope':protocol['scope'],'largest_passing_single_case_size':None,'stages':[],'status':'running'}
    save(series/'series.json',ledger)
    for size in args.sizes:
        save(series/f'n{size:03}-planned-jobs.json',[{'case':case['id'],'repeat':1}])
        result=run_one(series,rows[:size],case,1,variant='grounded',schema_ids='controls-only',backend='local',
            local_context=32768,exposure='on-call',local_thinking='off',local_sampling=args.local_sampling,local_planner=args.local_planner,local_gpu_layers=24,planner_artifacts=args.planner_artifacts,strict_feedback_csv=args.strict_feedback_csv,short_circuit_hard_failure=args.short_circuit_hard_failure)
        result['measurement_scope']='single fixed-case observation, not 12/12 full-family qualification'
        save(series/f'n{size:03}'/f"{case['id']}-r1"/'summary.json',result)
        ledger['stages'].append({'size':size,'passed':int(result['passed']),'completed':1,'planned':1,'fully_passed':result['passed'],'results':[result]})
        if result['passed']:ledger['largest_passing_single_case_size']=size
        else:
            ledger.setdefault('first_failed_probe_size',size);ledger.setdefault('failed_probe_sizes',[]).append(size)
            if not args.continue_after_failure:ledger['status']='stopped_at_failed_probe'
        save(series/'series.json',ledger)
        print('EXPLORATORY',size,'PASS' if result['passed'] else 'FAIL','NOT_FULL_FAMILY_SCORE',flush=True)
        if not result['passed'] and not args.continue_after_failure:break
    else:ledger['status']='all_planned_single_case_probes_completed' if ledger.get('failed_probe_sizes') else 'all_available_planned_single_case_probes_passed'
    save(series/'series.json',ledger)


if __name__=='__main__':main()
