"""Airflow execution of host-native, source-frozen Skill composition tasks."""
import os
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import Param, dag, task, get_current_context
from airflow.providers.standard.sensors.python import PythonSensor


def workspace():
    return Path(os.environ.get('RESUME_WORKSPACE', '/opt/airflow/resume_workspace'))


def host_finished(job_id):
    from resume_flow.skill_jobs import execution_done
    return execution_done(workspace(), job_id)


@dag(dag_id='skill_experiment', schedule=None, catchup=False,
     start_date=pendulum.datetime(2026, 1, 1, tz='Asia/Shanghai'), max_active_runs=8,
     is_paused_upon_creation=False, tags=['newstar', 'skills', 'experiment'],
     default_args={'owner': 'newstar', 'retries': 1, 'retry_delay': timedelta(seconds=10)},
     params={'job_id': Param('', type='string', title='工作台实验标识')})
def skill_experiment():
    @task
    def validate_request():
        from resume_flow.skill_jobs import folder, config
        from resume_flow.storage import read_json, validate_id
        job_id = validate_id(get_current_context()['params']['job_id'])
        record = read_json(folder(workspace(), job_id) / 'job.json')
        config(record['config'])
        print('已验证网页实验请求', job_id, record['config']['backend'], record['config']['size'])
        return job_id

    @task
    def dispatch_to_host(job_id):
        from resume_flow.skill_jobs import enqueue
        print('提交到 Windows 单并发执行队列', job_id)
        return enqueue(workspace(), job_id)

    request = validate_request()
    queued = dispatch_to_host(request)
    waiting = PythonSensor(task_id='execute_skills', python_callable=host_finished,
                           op_args=[queued], mode='reschedule', poke_interval=15, timeout=14400)

    @task
    def verify_artifacts(job_id):
        from resume_flow.skill_jobs import collect_result, collect_failure, folder
        from resume_flow.storage import read_json
        state = read_json(folder(workspace(), job_id) / 'execution.json')
        if state['phase'] == 'failed':
            collect_failure(workspace(), job_id, state.get('error', '主机执行失败'))
            raise ValueError(state.get('error', '主机执行失败，请查看工作台日志'))
        result = collect_result(workspace(), job_id)
        print('实际产物归档', result['metrics'], '自动评估', result['automatic_passed'])
        if not result['automatic_passed']:
            raise ValueError(result.get('error') or '模型交付未通过自动核验，证据已归档到工作台')
        return job_id

    @task
    def publish_results(job_id):
        from resume_flow.skill_jobs import folder, write_json
        from resume_flow.storage import read_json
        path = folder(workspace(), job_id) / 'execution.json'
        write_json(path, {**read_json(path), 'published': True})
        print('结果已发布 http://localhost:8765/skills?job_id=' + job_id)

    verified = verify_artifacts(queued)
    waiting >> verified
    publish_results(verified)


skill_experiment()
