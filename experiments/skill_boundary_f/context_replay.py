"""Fresh exact-input context controls, diagnostic only; never new business passes."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
import urllib.error
import urllib.request
from runner import BASE,REPO,read,save


def context_variant(source,context):
    if context<1024 or context>65536:raise ValueError('context outside controlled local range')
    target=copy.deepcopy(source);target['options']['num_ctx']=context
    return target


def input_digest(body):
    stable=copy.deepcopy(body);stable['options'].pop('num_ctx',None)
    return hashlib.sha256(json.dumps(stable,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def classify_resource(raw,runtime_log):
    if re.search(r'truncating input prompt|input is too long|context shift,|truncated\s*=\s*1',runtime_log,re.I):
        return 'context_failure'
    if raw.get('done') is not True or raw.get('done_reason')!='stop':return 'incomplete_response'
    return 'complete_response_without_detected_truncation'


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',required=True,type=Path);p.add_argument('--prefix',required=True)
    p.add_argument('--contexts',nargs='+',type=int,default=[32768,40960]);p.add_argument('--repeats',type=int,default=2)
    args=p.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',args.prefix) or args.repeats<2:raise ValueError('invalid diagnostic protocol')
    source=read(args.request)
    if source.get('model')!='qwen3.5:9b' or source.get('stream') is not False:raise ValueError('only frozen existing local input')
    root=BASE/'context-controls'/args.prefix;root.mkdir(parents=True,exist_ok=False)
    save(root/'source-request.json',source);shutil.copyfile(Path(__file__),root/'context_replay.py')
    save(root/'protocol.json',{'scope':'fresh repeated inference on exact frozen input; no tools executed, no business pass',
        'source_request':str(args.request.resolve()),'input_digest_without_context':input_digest(source),
        'contexts':args.contexts,'repeats':args.repeats,'only_changed_field':'options.num_ctx',
        'endpoint':'http://127.0.0.1:11434/api/chat','paid_api':False})
    log=REPO/'tmp/skill-boundary-local/ollama-stderr.log'
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));results=[]
    for repeat in range(1,args.repeats+1):
        for context in args.contexts:
            body=context_variant(source,context);folder=root/f'ctx{context}-r{repeat}';folder.mkdir()
            save(folder/'request.json',body);offset=log.stat().st_size
            result={'context':context,'repeat':repeat,'status':'running','input_digest':input_digest(body)}
            save(root/'state.json',{'status':'running','current':result,'results':results})
            request=urllib.request.Request('http://127.0.0.1:11434/api/chat',
                json.dumps(body,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
            start=time.monotonic()
            try:
                with opener.open(request,timeout=1800) as response:raw=json.load(response)
                save(folder/'native.json',raw)
                with log.open('rb') as stream:stream.seek(offset);runtime=stream.read().decode('utf-8',errors='replace')
                (folder/'runtime.log').write_text(runtime,encoding='utf-8')
                result.update(status=classify_resource(raw,runtime),prompt_tokens=raw.get('prompt_eval_count'),
                    completion_tokens=raw.get('eval_count'),done=raw.get('done'),done_reason=raw.get('done_reason'))
            except urllib.error.HTTPError as exc:
                detail=exc.read(4096).decode('utf-8',errors='replace')
                result.update(status='context_failure' if exc.code==400 and 'context' in detail.lower() else 'transport_failure',
                    http_status=exc.code,error=detail)
                save(folder/'error.json',result)
            except Exception as exc:result.update(status='transport_failure',error=type(exc).__name__+': '+str(exc))
            result['seconds']=time.monotonic()-start;save(folder/'summary.json',result);results.append(result)
            save(root/'state.json',{'status':'running','results':results});print('CONTEXT_CONTROL',result,flush=True)
    save(root/'state.json',{'status':'finished','results':results})


if __name__=='__main__':main()
