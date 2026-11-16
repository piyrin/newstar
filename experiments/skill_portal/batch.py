"""Run explicitly authorized ten-trial cohorts through the Web/Airflow entry point."""
import argparse
import json
from pathlib import Path
import sys
import time
import urllib.request

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'airflow/dags'))
from resume_flow import skill_jobs
from resume_flow.storage import read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-job', required=True)
    args = parser.parse_args()
    workspace = REPO / 'airflow/resume_workspace'
    path = skill_jobs.root(workspace) / 'batches/deepseek-20261113.json'
    groups = [{'size': size, 'jobs': [f'deepseek-20261113-n{size}-{r:02}' for r in range(1, 11)]}
              for size in (100, 180)]
    groups[0]['jobs'][0] = args.first_job
    protocol = {'name': 'deepseek-20261113', 'groups': groups, 'planned': 20,
        'status': 'running', 'started_at': time.time(), 'planner_rounds': 16,
        'backend': 'deepseek', 'model': 'deepseek-flash', 'temperature': 0.2,
        'thinking': 'disabled', 'semantic_review_profile': 'legacy',
        'candidate_order': 'frozen', 'exposure': 'on-call', 'hidden_model_retries': 0,
        'content_review': 'pending direct review of every final artifact against original six criteria',
        'scope': 'Two new ten-trial cohorts. First N100 submitted with real browser. Remaining trials use the same Web endpoint and Airflow DAG. Historical N166 cohort remains separate.'}
    if path.exists():
        protocol = read_json(path)
        groups = protocol['groups']
    skill_jobs.write_json(path, protocol)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = 'http://127.0.0.1:8765'

    def call(route, payload=None):
        session = urllib.request.Request(base + '/api/session', headers={'X-Resume-Portal': '1'})
        with opener.open(session, timeout=60) as response:
            token = json.load(response)['token']
        body = json.dumps(payload).encode('utf-8') if payload else None
        request = urllib.request.Request(base + route, body,
            {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        with opener.open(request, timeout=90) as response:
            return json.load(response)

    request_text = read_json(skill_jobs.root(workspace) / 'catalog.json')['case']['request']
    for group in groups:
        for job_id in group['jobs']:
            target = skill_jobs.folder(workspace, job_id)
            # The endpoint deduplicates by request ID, including after a network
            # failure between creating job.json and triggering the DagRun.
            call('/api/skills/start', {'request_id': job_id, 'request': request_text,
                'size': group['size'], 'backend': 'deepseek', 'accept_api_cost': True})
            print('Ensured submission', job_id, flush=True)
            while True:
                state_path = target / 'execution.json'
                state = read_json(state_path) if state_path.exists() else {}
                if state.get('phase') in skill_jobs.TERMINAL:
                    detail = call('/api/skills/job?job_id=' + job_id)
                    if detail.get('airflow', {}).get('state') in ('success', 'failed'):
                        break
                time.sleep(10)
            print('Finished', job_id, state.get('phase'),
                  detail.get('airflow', {}).get('state'), flush=True)
    skill_jobs.write_json(path, {**protocol, 'status': 'finished', 'ended_at': time.time()})
    print('All 20 complete-task attempts archived. Content review pending.', flush=True)


if __name__ == '__main__':
    main()
