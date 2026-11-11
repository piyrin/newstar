"""Compare default versus unpruned server-rendered inputs; no generation/tool execution."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import urllib.request
from runner import read,save


def validate_rendered_tools(body,text):
    expected=body.get('tools') or []
    if not expected:return {'count':0,'schema_differences':[]}
    block=text.split('<tools>',1)[1].split('</tools>',1)[0]
    actual=[json.loads(line) for line in block.splitlines() if line.strip()]
    if len(actual)!=len(expected):raise ValueError('rendered tool count differs')
    differences=[]
    for a,b in zip(expected,actual):
        for key in ['name','description']:
            if a['function'][key]!=b['function'][key]:raise ValueError('tool name/description did not reach rendered prompt')
        if a['function']['parameters']!=b['function']['parameters']:differences.append(a['function']['name'])
    return {'count':len(actual),'schema_differences':differences}


def render(opener,body,path,resume=False):
    body=copy.deepcopy(body);body['_debug_render_only']=True
    request_file=path.with_suffix('.request.json');response_file=path.with_suffix('.response.json')
    if resume and response_file.exists():
        assert read(request_file)==body, 'cached render request differs from frozen input'
        return read(response_file)['_debug_info']['rendered_template']
    save(request_file,body)
    req=urllib.request.Request('http://127.0.0.1:11434/api/chat',json.dumps(body,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
    with opener.open(req,timeout=180) as response:raw=json.load(response)
    save(path.with_suffix('.response.json'),raw)
    text=raw['_debug_info']['rendered_template']
    if not text:raise ValueError('missing rendered input evidence')
    return text


def audit(series,resume=False):
    ledger=read(series/'series.json');target=series/'render-recheck';target.mkdir(exist_ok=resume)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));trials=[]
    for stage in ledger['stages']:
        for result in stage['results']:
            name=f"n{stage['size']:03}/{result['case']}-r{result['repeat']}";folder=series/name;observations=[]
            for req_path in sorted(folder.rglob('*.request.json')):
                body=read(req_path)
                if body.get('model')!='qwen3.5:9b' or not isinstance(body.get('messages'),list):continue
                stem=req_path.name.removesuffix('.request.json');out=target/name/req_path.relative_to(folder).parent/stem
                original=render(opener,body,out.with_name(out.name+'-default'),resume)
                # Input rendering never generates tokens; keep shift unchanged so
                # both renders use the same runner configuration and only pruning differs.
                strict=copy.deepcopy(body);strict['truncate']=False
                complete=render(opener,strict,out.with_name(out.name+'-unpruned-input-only'),resume)
                exposure=validate_rendered_tools(body,original)
                assert validate_rendered_tools(body,complete)==exposure
                observations.append({'request':str(req_path),'same_rendered_input':original==complete,
                    'rendered_tool_exposure':exposure,
                    'default_chars':len(original),'unpruned_chars':len(complete),
                    'default_sha256':hashlib.sha256(original.encode()).hexdigest(),
                    'unpruned_sha256':hashlib.sha256(complete.encode()).hexdigest()})
            changed=[o for o in observations if not o['same_rendered_input']]
            r={'trial':name,'original_passed':result['passed'],'checked_requests':len(observations),
                'changed_requests':changed,'observations':observations,
                'no_server_history_pruning_verified':bool(observations) and not changed}
            trials.append(r);save(target/'report.json',{'status':'running','trials':trials})
            print('RENDER_AUDIT',name,'requests',len(observations),'changed',len(changed),flush=True)
    report={'status':'finished','scope':'render-only input/history integrity; not fresh business passes or output-shift audit',
        'trials':trials,'checked_requests':sum(r['checked_requests'] for r in trials),
        'trials_with_changed_rendered_input':sum(bool(r['changed_requests']) for r in trials)}
    save(target/'report.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('series',type=Path);p.add_argument('--resume',action='store_true');a=p.parse_args();r=audit(a.series,a.resume)
    print({k:v for k,v in r.items() if k!='trials'})
