"""Fresh repetitions at an observed single-case boundary. No reuse as new trials."""
import argparse
from pathlib import Path
import shutil
from progressive import run_one,stage_passes
from runner import BASE,read,save


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',default='local-single-receipts-native-c')
    parser.add_argument('--prefix',required=True);parser.add_argument('--size',type=int);parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args();source=BASE/'progressive'/args.source;prior=read(source/'series.json');config=read(source/'protocol.json')
    if prior['status']=='running':raise ValueError('source exploration still running; wait for its actual boundary')
    if config['backend']!='local' or config.get('full_task_family') is not False:raise ValueError('only the local single-case experiment can be confirmed here')
    size=args.size or prior['largest_passing_single_case_size']
    stage=next(s for s in prior['stages'] if s['size']==size);original=stage['results'][0]
    if args.repeats<2:raise ValueError('at least two fresh repetitions required')
    rows=read(source/'registry.json');cases=read(source/'fixtures.json')
    if len(cases)!=1:raise ValueError('confirmation must retain the exact same fixed case')
    target=BASE/'progressive'/args.prefix;target.mkdir(parents=True,exist_ok=False)
    for name in ['registry.json','fixtures.json','local-model-show.json','LOCAL_PROTOCOL.md','PROGRESSIVE_PROTOCOL.md']:
        if (source/name).exists():shutil.copyfile(source/name,target/name)
    for name in ['progressive.py','local_api.py','structured_planner.py','planner_receipts.py','feedback_csv.py','reference_store.py','business_evidence.py','incremental.py','runner.py','confirm_probe.py']:
        shutil.copyfile(Path(__file__).parent/name,target/name)
    config.update(scope='fresh repeated fixed-case confirmation only, not the six-case full family',sizes=[size],repeats=args.repeats,
        promotion='report all fresh repetitions; failed trials retained',source_exploration=str(source),
        original_trial=str(source/f'n{size:03}'/f"{cases[0]['id']}-r{original['repeat']}"),parallel_other_experiment=None)
    save(target/'protocol.json',config)
    ledger={'prefix':args.prefix,'scope':config['scope'],'status':'running','stages':[],'source_exploration':str(source)}
    save(target/'series.json',ledger);results=[]
    for repeat in range(1,args.repeats+1):
        result=run_one(target,rows[:size],cases[0],repeat,variant=original['variant'],schema_ids=original['schema_ids'],
            backend='local',local_context=config['local_context'],exposure=config['exposure'],local_thinking=config['thinking'],
            local_sampling=config['local_sampling'],local_planner=config['local_planner'],local_gpu_layers=config['local_gpu_layers'],
            planner_artifacts=config.get('planner_artifacts','full'),strict_feedback_csv=config.get('strict_feedback_csv',False),
            short_circuit_hard_failure=config.get('short_circuit_hard_failure',False))
        results.append(result)
    fresh=sum(r['passed'] for r in results);all_fresh=stage_passes(results,[cases[0]['id']],args.repeats)
    ledger.update(status='confirmation_finished',stages=[{'size':size,'passed':fresh,'completed':len(results),
        'planned':args.repeats,'fully_passed':all_fresh,'results':results}],
        confirmation={'candidate_skills':size,'fresh_passed':fresh,'fresh_trials':args.repeats,'original_passed':bool(original['passed']),
            'combined_passed':fresh+int(original['passed']),'combined_trials':args.repeats+1,
            'note':'original and fresh trials have separate paths; original counted once, never replayed as a new sample'})
    save(target/'series.json',ledger);print(ledger['confirmation'],flush=True)


if __name__=='__main__':main()
