"""Loopback-only Ollama backend. No credentials, cloud fallback, downloads or API fees."""
import copy
import json
import re
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
from runner import REPO, save


def native_messages(messages):
    result=[];names={}
    for original in messages:
        m=copy.deepcopy(original);m['content']=m.get('content') or ''
        if m.get('tool_calls'):
            calls=[]
            for i,c in enumerate(m['tool_calls']):
                fn=c['function'];names[c['id']]=fn['name']
                args=fn['arguments']
                calls.append({'type':'function','function':{'index':i,'name':fn['name'],
                    'arguments':json.loads(args) if isinstance(args,str) else args}})
            m['tool_calls']=calls
        if m['role']=='tool':
            m['tool_name']=names[m.pop('tool_call_id')]
        result.append(m)
    return result


def normalize_message(raw,ident):
    message={'role':'assistant','content':raw.get('content') or ''}
    if raw.get('tool_calls'):
        message['tool_calls']=[{'id':f'local-{ident}-{i}','type':'function','function':{
            'name':c['function']['name'],'arguments':json.dumps(c['function']['arguments'],ensure_ascii=False)}}
            for i,c in enumerate(raw['tool_calls'])]
    return message


class LocalAPI:
    supports_json_schema=True
    def __init__(self,endpoint='http://127.0.0.1:11434',model='qwen3.5:9b',context=32768,thinking='off',sampling='legacy',gpu_layers=None,seed=None):
        parsed=urllib.parse.urlparse(endpoint)
        if parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost','::1'} or parsed.username or parsed.password:
            raise ValueError('local backend accepts loopback HTTP endpoints only')
        if ':cloud' in model or model.endswith('-cloud'):
            raise ValueError('cloud model tags prohibited')
        if thinking not in {'off','planner-worker','all'}:raise ValueError('unknown local thinking profile')
        if sampling not in {'legacy','qwen-recommended'}:raise ValueError('unknown sampling profile')
        if gpu_layers is not None and (type(gpu_layers) is not int or gpu_layers<0):raise ValueError('GPU layer count must be nonnegative')
        self.gpu_layers=gpu_layers
        if seed is not None and (type(seed) is not int or seed<0):raise ValueError('seed must be a nonnegative integer')
        self.seed=seed
        self.endpoint=endpoint.rstrip('/');self.model=model;self.context=context;self.thinking=thinking;self.sampling=sampling
        self.log=REPO/'tmp/skill-boundary-local/ollama-stderr.log'

    def build_request(self,messages,tools=None,json_mode=False,max_tokens=2600):
        thinking=self.thinking=='all' or (self.thinking=='planner-worker' and not json_mode)
        body={'model':self.model,'messages':native_messages(messages),'think':thinking,'stream':False,
              'truncate':False,'shift':False,
              'keep_alive':'10m','options':{'num_ctx':self.context,'num_predict':max_tokens+(4096 if thinking else 0),'temperature':0.2,'presence_penalty':0}}
        if self.sampling=='qwen-recommended':
            body['options'].update(temperature=1.0 if thinking else 0.7,top_p=0.95 if thinking else 0.8,
                top_k=20,min_p=0.0,presence_penalty=1.5,repeat_penalty=1.0)
        if self.gpu_layers is not None:body['options']['num_gpu']=self.gpu_layers
        if self.seed is not None:body['options']['seed']=self.seed
        if tools is not None:body['tools']=tools
        if json_mode:body['format']=json_mode if isinstance(json_mode,dict) else 'json'
        return body

    def call(self,messages,path,tools=None,json_mode=False,max_tokens=2600):
        body=self.build_request(messages,tools,json_mode,max_tokens)
        save(path.with_suffix('.request.json'),body)
        offset=self.log.stat().st_size if self.log.exists() else 0
        start=time.monotonic()
        req=urllib.request.Request(self.endpoint+'/api/chat',json.dumps(body,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
        # Explicitly bypass external proxies; this transport never leaves loopback.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req,timeout=1800) as response:raw=json.load(response)
        except urllib.error.HTTPError as e:
            detail=e.read(4096).decode('utf-8',errors='replace')
            save(path.with_suffix('.error.json'),{'http_status':e.code,'message':detail,'local_only':True})
            raise RuntimeError(f'local HTTP {e.code}: {detail[:700]}') from None
        except Exception as e:
            save(path.with_suffix('.error.json'),{'error_type':type(e).__name__,'local_only':True})
            raise RuntimeError('local '+type(e).__name__) from None
        save(path.with_suffix('.native.json'),raw)
        duration=time.monotonic()-start
        if self.log.exists():
            with self.log.open('rb') as stream:stream.seek(offset);new_log=stream.read().decode('utf-8',errors='replace')
            if re.search(r'truncating input prompt|input is too long|context shift,|truncated\s*=\s*1',new_log,re.I):
                save(path.with_suffix('.error.json'),{'error':'context_truncation_detected','local_only':True})
                raise RuntimeError('local context truncation detected; result invalid, not an orchestration limit')
        msg=normalize_message(raw['message'],path.name)
        usage={'prompt_tokens':raw.get('prompt_eval_count',0),'completion_tokens':raw.get('eval_count',0)}
        usage['total_tokens']=sum(usage.values())
        normalized={'model':raw.get('model'),'choices':[{'message':msg,'finish_reason':'tool_calls' if msg.get('tool_calls') else raw.get('done_reason')}],
                    'usage':usage,'local_only':True,'seconds':duration,'num_ctx':self.context}
        save(path.with_suffix('.response.json'),normalized)
        if raw.get('done_reason')!='stop':raise RuntimeError('incomplete local response: '+str(raw.get('done_reason')))
        return (json.loads(msg['content']) if json_mode else msg),usage
