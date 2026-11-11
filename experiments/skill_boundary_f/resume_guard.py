"""Replay unchanged saved responses and resume only a proven executor false rejection.

A nonempty, valid 26-character CSV was rejected by the old arbitrary 80-character
minimum. This correction does not repair model JSON or reroll earlier model choices.
All original requests/responses/outcomes remain intact; new calls start at the boundary.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import runner

OriginalAPI=runner.API
OriginalWorker=runner.worker
ROOT=runner.BASE

def relocate(value,source,target):
    if isinstance(value,dict):return {k:relocate(v,source,target) for k,v in value.items()}
    if isinstance(value,list):return [relocate(v,source,target) for v in value]
    if isinstance(value,str):
        value=value.replace(json.dumps(str(source),ensure_ascii=False)[1:-1],json.dumps(str(target),ensure_ascii=False)[1:-1])
        return value.replace(str(source),str(target))
    return value

def short_rejection(directory):
    summary=runner.read(directory/'summary.json')
    if not any(e.startswith('unsupported or empty deliverable:') for e in summary['errors']):return False
    count=summary['dag_nodes']+1
    p=directory/f'skill-A{count:03}.response.json'
    if not p.exists():return False
    try:
        d=json.loads(runner.read(p)['choices'][0]['message']['content'])
        return d.get('status')=='done' and isinstance(d.get('artifact'),str) and 0<len(d['artifact'])<80
    except (ValueError,KeyError):return False

def corrected_worker(*args,**kwargs):
    try:return OriginalWorker(*args,**kwargs)
    except RuntimeError as error:
        if not str(error).startswith('unsupported or empty deliverable:'):raise
        path=args[5] if len(args)>5 else kwargs['path']
        raw=runner.read(path.with_suffix('.response.json'))
        answer=json.loads(raw['choices'][0]['message']['content'])
        artifact=answer.get('artifact')
        if answer.get('status')!='done' or not isinstance(artifact,str) or not artifact.strip():raise
        runner.save(path.with_suffix('.guard-correction.json'),{'reason':'removed arbitrary minimum length',
            'artifact_characters':len(artifact),'semantic_output_unchanged':True})
        return answer,raw.get('usage',{})

class ReplayAPI(OriginalAPI):
    origin_prefix=''
    target_prefix=''

    def call(self,messages,path,tools=None,json_mode=False,max_tokens=2600):
        origin_name=path.parent.name.replace(self.target_prefix,self.origin_prefix,1)
        origin_dir=ROOT/'runs'/origin_name
        original=origin_dir/path.name
        cached=original.with_suffix('.response.json')
        if not cached.exists():return super().call(messages,path,tools,json_mode,max_tokens)
        body={'model':self.model,'messages':messages,'temperature':0.2,'thinking':{'type':'disabled'},
              'stream':False,'max_tokens':max_tokens}
        if tools is not None:body.update(tools=tools,tool_choice='auto')
        if json_mode:body['response_format']={'type':'json_object'}
        old_body=runner.read(original.with_suffix('.request.json'))
        # Only output-directory relocation is normalized; task, tool, arguments and content must match.
        normalized=relocate(body,path.parent,origin_dir)
        if normalized!=old_body:raise RuntimeError('saved request mismatch; refusing silent replay')
        raw=runner.read(cached)
        runner.save(path.with_suffix('.request.json'),body)
        runner.save(path.with_suffix('.response.json'),raw)
        runner.save(path.with_suffix('.replay.json'),{'source':str(cached),'new_provider_call':False})
        choice=raw['choices'][0]
        if choice['finish_reason'] not in ['stop','tool_calls']:raise RuntimeError('cached response incomplete')
        msg=dict(choice['message']);msg.pop('reasoning_content',None)
        return (json.loads(msg['content']) if json_mode else msg),raw.get('usage',{})

def main():
    global runner,OriginalWorker
    ap=argparse.ArgumentParser();ap.add_argument('--origin',required=True);ap.add_argument('--target',required=True)
    a=ap.parse_args()
    # Use the archived implementation so later maintenance cannot alter replay inputs.
    archived=ROOT/'frozen'/a.origin/'runner.py'
    original_repo=runner.REPO
    spec=importlib.util.spec_from_file_location('historical_skill_boundary_runner',archived)
    historical=importlib.util.module_from_spec(spec);spec.loader.exec_module(historical)
    historical.REPO=original_repo;historical.BASE=ROOT
    runner=historical;OriginalWorker=historical.worker
    frozen=ROOT/'frozen'/a.target;frozen.mkdir(parents=True,exist_ok=True)
    for name in ['registry.json','settings.json','PROTOCOL.md','runner.py']:
        source=ROOT/'frozen'/a.origin/name
        if not (frozen/name).exists():shutil.copyfile(source,frozen/name)
    code=Path(__file__).read_bytes();code_hash=hashlib.sha256(code).hexdigest()
    versioned=frozen/f'guard-correction-{code_hash[:12]}.py'
    if not versioned.exists():versioned.write_bytes(code)
    if not (frozen/'guard-correction.py').exists():(frozen/'guard-correction.py').write_bytes(code)
    ReplayAPI.origin_prefix=a.origin;ReplayAPI.target_prefix=a.target
    runner.API=ReplayAPI;runner.worker=corrected_worker
    jobs=[]
    for directory in sorted((ROOT/'runs').glob(a.origin+'-n*')):
        if not (directory/'summary.json').exists() or not short_rejection(directory):continue
        s=runner.read(directory/'summary.json');target_name=s['run_id'].replace(a.origin,a.target,1)
        if (ROOT/'runs'/target_name/'summary.json').exists():continue
        jobs.append(s)
    def resume(s):
        full=runner.read(frozen/'settings.json').get('full',False)
        result=runner.run_task(s['skills_available'],s['task'],s['trial'],a.target,full=full)
        result.update(origin_run_id=s['run_id'],correction='nonempty short artifact accepted; prior responses replayed',
          correction_implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        runner.save(ROOT/'runs'/result['run_id']/'summary.json',result)
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(resume,jobs))
    all_results=[runner.read(p) for p in (ROOT/'runs').glob(a.target+'-n*/summary.json')]
    runner.save(ROOT/(a.target+'-aggregate.json'),{'origin':a.origin,'target':a.target,
      'resumed_count':len(all_results),'newly_resumed_count':len(results),'results':all_results})

if __name__=='__main__':main()
