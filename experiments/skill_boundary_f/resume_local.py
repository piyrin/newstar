"""Continue an executor-aborted local trial, replaying exact saved calls only.

Replay reconstructs the original 16-round loop; cached calls consume their original
rounds. Only output-root relocation is normalized. No old choice is regenerated.
"""
import argparse
import json
from pathlib import Path
import shutil
from local_api import LocalAPI
from runner import BASE,read,save
from progressive import run_one,stage_passes


def relocate(value,source,target):
    if isinstance(value,dict):return {k:relocate(v,source,target) for k,v in value.items()}
    if isinstance(value,list):return [relocate(v,source,target) for v in value]
    if isinstance(value,str):
        value=value.replace(json.dumps(str(source),ensure_ascii=False)[1:-1],json.dumps(str(target),ensure_ascii=False)[1:-1])
        return value.replace(str(source),str(target))
    return value


class ReplayLocalAPI(LocalAPI):
    def __init__(self,origin,target,**kwargs):
        super().__init__(**kwargs)
        self.origin=Path(origin);self.target=Path(target);self.replayed_calls=0;self.new_calls=0

    def call(self,messages,path,tools=None,json_mode=False,max_tokens=2600):
        path=Path(path);old=self.origin/path.relative_to(self.target)
        request=old.with_suffix('.request.json');response=old.with_suffix('.response.json')
        if request.exists():
            if not response.exists():raise ValueError('incomplete saved call; refusing hidden reroll')
            body=self.build_request(messages,tools,json_mode,max_tokens)
            if relocate(body,self.target,self.origin)!=read(request):
                raise ValueError('saved request mismatch; refusing changed replay')
            raw=read(response)
            if raw['choices'][0]['finish_reason'] not in {'stop','tool_calls'}:
                raise ValueError('incomplete saved response; refusing hidden reroll')
            save(path.with_suffix('.request.json'),body);save(path.with_suffix('.response.json'),raw)
            if old.with_suffix('.native.json').exists():shutil.copyfile(old.with_suffix('.native.json'),path.with_suffix('.native.json'))
            save(path.with_suffix('.replay.json'),{'source':str(response),'new_model_call':False,'request_verified':True,
                'only_normalization':'output root relocation'})
            self.replayed_calls+=1
            msg=raw['choices'][0]['message']
            return (json.loads(msg['content']) if json_mode else msg),raw.get('usage',{})
        self.new_calls+=1
        return super().call(messages,path,tools,json_mode,max_tokens)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--origin',required=True);parser.add_argument('--target',required=True)
    args=parser.parse_args();origin=BASE/'progressive'/args.origin;target=BASE/'progressive'/args.target
    protocol=read(origin/'protocol.json')
    if protocol['backend']!='local':raise ValueError('paid APIs prohibited in continuation')
    old_trial=origin/'n010'/'event-r1';old_summary=read(old_trial/'summary.json')
    if old_summary['error']!="'str' object has no attribute 'get'":raise ValueError('not the diagnosed executor interruption')
    target.mkdir(parents=True,exist_ok=False)
    for name in ['registry.json','fixtures.json','local-model-show.json','LOCAL_PROTOCOL.md','PROGRESSIVE_PROTOCOL.md']:
        if (origin/name).exists():shutil.copyfile(origin/name,target/name)
    for name in ['progressive.py','local_api.py','reference_store.py','business_evidence.py','incremental.py','runner.py','resume_local.py']:
        shutil.copyfile(Path(__file__).parent/name,target/name)
    protocol.update(resumed_from=str(origin),executor_correction='manifest shapes rejected visibly; no coercion or extra rounds',
        continuation_original_rounds=16,continuation_cached_planner_rounds=12,continuation_remaining_planner_rounds=4)
    save(target/'protocol.json',protocol)
    rows=read(target/'registry.json');cases=read(target/'fixtures.json')
    ledger={'prefix':args.target,'resumed_from':str(origin),'last_fully_passed_size':None,'stages':[],'status':'running'}
    save(target/'series.json',ledger)
    for size in protocol['sizes']:
        if size>len(rows):ledger['status']='pool_exhausted';break
        jobs=[(case,repeat) for case in cases for repeat in [1,2]]
        if protocol['critical_first']:jobs.sort(key=lambda j:({'event':0,'competition':1}.get(j[0]['id'],2),cases.index(j[0]),j[1]))
        save(target/f'n{size:03}-planned-jobs.json',[{'case':c['id'],'repeat':r} for c,r in jobs])
        results=[]
        for case,repeat in jobs:
            trial=target/f'n{size:03}'/f"{case['id']}-r{repeat}"
            replay=ReplayLocalAPI(old_trial,trial,context=protocol['local_context'],thinking=protocol['thinking'],
                sampling=protocol['local_sampling']) if size==10 and case['id']=='event' and repeat==1 else None
            result=run_one(target,rows[:size],case,repeat,variant=protocol['variant'],schema_ids=protocol['schema_ids'],
                backend='local',local_context=protocol['local_context'],exposure=protocol['exposure'],
                local_thinking=protocol['thinking'],local_sampling=protocol['local_sampling'],replay_api=replay)
            if replay:
                result.update(resumed_from=str(old_trial),replayed_calls=replay.replayed_calls,new_calls=replay.new_calls,
                    independent_new_trial=False,original_summary=old_summary)
                save(trial/'summary.json',result)
            results.append(result)
            if not result['passed'] and protocol['fail_fast']:break
        passed=stage_passes(results,[c['id'] for c in cases],2)
        ledger['stages'].append({'size':size,'passed':sum(r['passed'] for r in results),'planned':len(jobs),
            'completed':len(results),'fully_passed':passed,'results':results})
        if passed:ledger['last_fully_passed_size']=size
        else:ledger.update(status='stopped_at_failed_stage',first_failed_size=size)
        save(target/'series.json',ledger)
        print('STAGE',size,'passed',sum(r['passed'] for r in results),'executed',len(results),'planned',len(jobs),'PROMOTE' if passed else 'STOP',flush=True)
        if not passed:break
    else:ledger['status']='all_planned_sizes_passed'
    save(target/'series.json',ledger)


if __name__=='__main__':main()
