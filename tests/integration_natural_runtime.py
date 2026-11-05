"""Opt-in real DeepSeek -> Airflow integration, exclusively using synthetic demo.

Run from the repo with the documented venv. Never prints credentials.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'airflow/dags'))
from resume_flow.config import load_env
from resume_flow.airflow_api import AirflowClient
from resume_flow.natural import parse_request, execute_request
from resume_flow.storage import write_json, read_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['trigger', 'repeat', 'status', 'enable', 'retry', 'scheduled', 'export', 'retry-scheduled'])
    args = parser.parse_args()
    load_env(ROOT / 'airflow/.env')
    # Same defaults as this project's official Compose initializer.
    init = {}
    for line in (ROOT / 'airflow/.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            if k.strip() in ('_AIRFLOW_WWW_USER_USERNAME', '_AIRFLOW_WWW_USER_PASSWORD'):
                init[k.strip()] = v.strip().strip('\"\'')
    os.environ.setdefault('AIRFLOW_API_USERNAME', init.get('_AIRFLOW_WWW_USER_USERNAME', 'airflow'))
    os.environ.setdefault('AIRFLOW_API_PASSWORD', init.get('_AIRFLOW_WWW_USER_PASSWORD', 'airflow'))
    ws = ROOT / 'airflow/resume_workspace'
    evidence = ws / 'verification/natural-20261104.json'
    api = AirflowClient()
    if args.action == 'enable':
        # Authorised schedule activation; preserve export's manual confirmation.
        result = api._send('PATCH', '/api/v2/dags/resume_prepare', {'is_paused': False})
        print({'dag_id': result.get('dag_id'), 'is_paused': result.get('is_paused')})
        return
    if args.action == 'retry':
        result = api._send('POST', '/api/v2/dags/resume_prepare/dagRuns/nl-verify-natural-20261104-trigger/clear',
                           {'dry_run': False, 'only_failed': True, 'run_on_latest_version': True})
        print({'state': 'cleared_failed_tasks', 'response_type': type(result).__name__})
        return
    if args.action == 'scheduled':
        runs = api._send('GET', '/api/v2/dags/resume_prepare/dagRuns?order_by=-run_after&limit=10')
        observations = []
        for run in runs['dag_runs']:
            if run.get('run_type') == 'scheduled':
                result = api.status('resume_prepare', run['dag_run_id'])
                observations.append(result)
                print(result)
        write_json(ws / 'verification/scheduled-20261104.json', observations)
        return
    if args.action == 'retry-scheduled':
        runs = api._send('GET', '/api/v2/dags/resume_prepare/dagRuns?order_by=-run_after&limit=10')
        for run in runs['dag_runs']:
            if run.get('run_type') == 'scheduled' and run['state'] == 'failed' and '2026-11-04' in run['dag_run_id']:
                api._send('POST', '/api/v2/dags/resume_prepare/dagRuns/' + run['dag_run_id'] + '/clear',
                          {'dry_run': False, 'only_failed': True, 'run_on_latest_version': True})
                print({'cleared': run['dag_run_id']})
        return
    if args.action in ('trigger', 'repeat', 'export'):
        request = ('请导出已经人工确认的 demo-deepseek-20261103 审阅版本为 Word 和 PDF。' if args.action == 'export' else
                   '请将 demo 材料整理成任务三集成验证岗位的简历草稿，使用 offline 离线样例模式。')
        plan = parse_request(ws, request)
        valid = (plan['action'] == 'export' and plan['conf']['run_key'] == 'demo-deepseek-20261103' if args.action == 'export' else
                 plan['action'] == 'prepare' and plan['conf']['case_id'] == 'demo' and plan['conf']['mode'] == 'offline')
        if not valid:
            raise ValueError('真实模型未正确解析虚构验证请求')
        result = execute_request(ws, plan, 'verify-natural-20261104-' + args.action, api=api)
        state = read_json(evidence) if evidence.exists() else {}
        state[args.action] = result
        write_json(evidence, state)
        print(result)
    else:
        data = read_json(evidence)
        for name in ('trigger', 'repeat', 'export'):
            if name in data:
                result = api.status(data[name]['plan']['dag_id'], data[name]['dag_run_id'])
                data[name]['observed'] = result
                print(result)
        write_json(evidence, data)


if __name__ == '__main__':
    main()
