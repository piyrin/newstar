"""Inspect saved evidence only; no network or model calls."""
import argparse
import csv
import io
import json
from pathlib import Path
from runner import BASE,read,save

def summarize(prefix,guard_prefix=None):
    config=read(BASE/'frozen'/prefix/'settings.json')
    expected=len(config['tasks'])*config['trials']
    raw_runs=[read(p) for p in sorted((BASE/'runs').glob(prefix+'-n*/summary.json'))]
    corrections={}
    if guard_prefix:
        corrections={r['origin_run_id']:r for p in (BASE/'runs').glob(guard_prefix+'-n*/summary.json')
                     if (r:=read(p)).get('origin_run_id')}
    runs=[corrections.get(r['run_id'],r) for r in raw_runs]
    table=[]
    for size in config['sizes']:
        xs=[r for r in runs if r['skills_available']==size]
        per_task={t:sum(r['passed'] for r in xs if r['task']==t) for t in config['tasks']}
        passed=sum(r['passed'] for r in xs)
        stable=len(xs)==expected and passed/expected>=0.875 and all(per_task.values())
        table.append({'skills':size,'planned':expected,'completed':len(xs),'passed':passed,
          'raw_passed':sum(r['passed'] for r in raw_runs if r['skills_available']==size),
          'guard_resumes':sum(r.get('origin_run_id') is not None for r in xs),
          'business_passed':sum(r['business_passed'] for r in xs),'pass_rate':passed/expected,
          'stable_threshold_met':stable,'per_task_success':per_task,
          'actual_skill_range':[min((r['actual_distinct_skills'] for r in xs),default=0),max((r['actual_distinct_skills'] for r in xs),default=0)],
          'node_range':[min((r['dag_nodes'] for r in xs),default=0),max((r['dag_nodes'] for r in xs),default=0)],
          'chain_range':[min((r['longest_dependency_chain_nodes'] for r in xs),default=0),max((r['longest_dependency_chain_nodes'] for r in xs),default=0)]})
    failures=[]
    for r in runs:
        if r['passed']:continue
        directory=BASE/'runs'/r['run_id'];verdict=read(directory/'verdict.json') if (directory/'verdict.json').exists() else {}
        failures.append({'run':r['run_id'],'errors':r['errors'],'business_errors':verdict.get('errors',[]),
                         'checks':r.get('deterministic_checks',{}),'combination_evidence':r['combination_evidence']})
    result={'prefix':prefix,'guard_prefix':guard_prefix,'complete':len(runs)==expected*len(config['sizes']),'table':table,'failures':failures,
      'largest_observed_success_pool':max((r['skills_available'] for r in runs if r['passed']),default=None),
      'largest_pool_meeting_small_sample_stability_threshold':max((x['skills'] for x in table if x['stable_threshold_met']),default=None)}
    save(BASE/(prefix+('-corrected' if guard_prefix else '')+'-summary.json'),result)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('prefix');ap.add_argument('--guard-prefix')
    args=ap.parse_args();summarize(args.prefix,args.guard_prefix)
