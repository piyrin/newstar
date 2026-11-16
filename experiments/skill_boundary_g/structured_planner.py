"""Local schema-constrained planner; choices and DAG still come from the model."""
import copy
import json
from local_api import LocalAPI
from runner import save


def plan_schema(tools):
    groups={}
    for tool in tools:
        fn=tool['function'];key=json.dumps(fn['parameters'],sort_keys=True,ensure_ascii=False)
        if key not in groups:groups[key]={'names':[],'parameters':fn['parameters']}
        groups[key]['names'].append(fn['name'])
    branches=[{'type':'object','properties':{'name':{'type':'string','enum':g['names']},
        'arguments':copy.deepcopy(g['parameters'])},'required':['name','arguments'],'additionalProperties':False}
        for g in groups.values()]
    return {'type':'object','properties':{'calls':{'type':'array','minItems':1,'items':{'anyOf':branches}}},
        'required':['calls'],'additionalProperties':False}


def plain_history(messages):
    result=[];names={}
    for message in messages:
        m=copy.deepcopy(message)
        if m.get('tool_calls'):
            calls=[]
            for c in m.pop('tool_calls'):
                fn=c['function'];names[c['id']]=fn['name']
                calls.append({'name':fn['name'],'arguments':json.loads(fn['arguments'])})
            m['content']=json.dumps({'calls':calls},ensure_ascii=False)
        if m['role']=='tool':
            m={'role':'user','content':json.dumps({'kind':'actual_tool_result','name':names[m['tool_call_id']],
                'content':m['content']},ensure_ascii=False)}
        result.append(m)
    return result


class StructuredPlannerAPI(LocalAPI):
    def call(self,messages,path,tools=None,json_mode=False,max_tokens=2600):
        if tools is None:return super().call(messages,path,json_mode=json_mode,max_tokens=max_tokens)
        history=plain_history(messages)
        history[0]['content']+='\n本轮从以下完整候选清单自主选择，输出符合Schema的JSON调用计划。执行器仅执行你的选择，不代写业务内容。'
        history[0]['content']+='\n候选清单（名称、完整原说明、参数）：\n'+json.dumps(tools,ensure_ascii=False)
        schema=plan_schema(tools)
        save(path.with_suffix('.tools.json'),tools)
        # Constrained planning is deliberately non-thinking; raw Skill workers
        # retain the configured thinking profile. This is a separate experiment.
        plan,usage=super().call(history,path,tools=None,json_mode=schema,max_tokens=max_tokens)
        if not isinstance(plan,dict) or not isinstance(plan.get('calls'),list) or not plan['calls']:
            raise ValueError('invalid structured plan; no repaired or invented call')
        available={t['function']['name'] for t in tools};calls=[]
        for i,c in enumerate(plan['calls']):
            if not isinstance(c,dict) or c.get('name') not in available or not isinstance(c.get('arguments'),dict):
                raise ValueError('invalid structured call; no automatic repair')
            calls.append({'id':f'local-{path.name}-{i}','type':'function','function':{'name':c['name'],
                'arguments':json.dumps(c['arguments'],ensure_ascii=False)}})
        message={'role':'assistant','content':'','tool_calls':calls}
        save(path.with_suffix('.plan.json'),plan)
        response_path=path.with_suffix('.response.json')
        if response_path.exists():
            from runner import read
            raw=read(response_path);save(path.with_suffix('.structured-raw.json'),raw)
            raw['choices']=[{'message':message,'finish_reason':'tool_calls'}]
            raw['planner_transport']='schema-constrained-json'
            save(response_path,raw)
        return message,usage
