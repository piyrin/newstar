"""One local context ablation probe. Never a Skill-capacity or suite score."""
from datetime import datetime
import json
from local_api import LocalAPI
from runner import BASE,read,save


def main():
    case=next(c for c in read(BASE/'progressive/local-qwen-schema-core-a/fixtures.json') if c['id']=='event')
    out=BASE/'diagnostics/local-short-event-a';out.mkdir(parents=True,exist_ok=False)
    schema={'type':'object','properties':{
        'sessions':{'type':'array','items':{'type':'object','properties':{'start':{'type':'string'},'end':{'type':'string'},'people':{'type':'integer'}},'required':['start','end','people'],'additionalProperties':False}},
        'total':{'type':'number'},'remaining':{'type':'number'}},'required':['sessions','total','remaining'],'additionalProperties':False}
    api=LocalAPI(context=32768,thinking='off',sampling='qwen-recommended',gpu_layers=24)
    save(out/'protocol.json',{'purpose':'context ablation only; not a full task, no Skills selected, not a capacity score',
        'model':api.model,'thinking':False,'context':32768,'gpu_layers':24,'paid_api':False,'hidden_retries':0})
    answer,_=api.call([{'role':'system','content':'根据用户给定facts计算，不引入额外硬条件。仅输出JSON。'},
        {'role':'user','content':json.dumps({'request':'仅给出满足facts的明确场次安排、预计总费用和余额。每场时长必须等于session_minutes；不能修改其他已给事实。','facts':case['facts']},ensure_ascii=False)}],out/'probe',json_mode=schema,max_tokens=700)
    facts=case['facts'];cost=facts['costs'];sessions=answer['sessions']
    minute=lambda s:datetime.strptime(s,'%H:%M').hour*60+datetime.strptime(s,'%H:%M').minute
    start,end=map(minute,facts['time_window'].split('—'))
    intervals=[(minute(s['start']),minute(s['end'])) for s in sessions]
    expected=cost['venue_yuan']+cost['photography_yuan']+(cost['materials_per_person_yuan']+cost['snacks_per_person_yuan'])*facts['registered_people']
    checks={'complete_allocation':sum(s['people'] for s in sessions)==facts['registered_people'],
        'capacity':all(0<s['people']<=facts['room_capacity'] for s in sessions),
        'durations':all(b-a==facts['session_minutes'] for a,b in intervals),
        'window':all(start<=a<b<=end for a,b in intervals),
        'nonoverlap':all(b<=c for (_,b),(c,_) in zip(sorted(intervals),sorted(intervals)[1:])),
        'budget':answer['total']==expected and answer['remaining']==facts['budget_yuan']-expected}
    result={'diagnostic_only':True,'not_skill_capacity_score':True,'answer':answer,'checks':checks,'passed_probe':all(checks.values())}
    save(out/'result.json',result);print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
