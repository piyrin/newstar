"""Incremental material checks and human-approved export; heavy imports in tasks."""
import hashlib
import os
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import Param, dag, task, get_current_context


def workspace():
    return Path(os.environ.get('RESUME_WORKSPACE', '/opt/airflow/resume_workspace'))


def invoke(function, *args):
    from airflow.sdk.exceptions import AirflowFailException
    try:
        return function(workspace(), *args)
    except ValueError as error:
        # User/configuration problems need intervention, not task-level retries.
        raise AirflowFailException(str(error)) from None


@dag(dag_id='resume_prepare', schedule='*/30 * * * *',
     start_date=pendulum.datetime(2026, 1, 1, tz='Asia/Shanghai'), catchup=False,
     max_active_runs=1, is_paused_upon_creation=True, tags=['newstar', 'resume'],
     default_args={'owner': 'newstar', 'retries': 1, 'retry_delay': timedelta(seconds=10),
                   'execution_timeout': timedelta(minutes=45)},
     params={'case_id': Param(os.environ.get('RESUME_DEFAULT_CASE', 'demo'), type='string', pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$'),
             'run_key': Param('', type='string', pattern=r'^$|^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$'),
             'target': Param(os.environ.get('RESUME_DEFAULT_TARGET', ''), type='string', maxLength=200),
             'jd': Param('', type='string', maxLength=20000),
             'mode': Param(os.environ.get('RESUME_DEFAULT_MODE', 'deepseek'), enum=['deepseek', 'offline'], type='string')},
     doc_md='每半小时检查材料与岗位配置；已成功整理的相同版本跳过，下游不调用模型。更新后生成独立审阅包，导出仍需人工确认。offline 仅支持内置虚构样例。')
def resume_prepare():
    @task
    def snapshot_materials():
        from airflow.sdk.exceptions import AirflowSkipException
        from resume_flow.incremental import prepare_version
        context = get_current_context()
        params = context['params']
        result = invoke(prepare_version, params['case_id'], params['run_key'],
                        params['target'], params['jd'], params['mode'])
        from resume_flow.storage import digest, inside, write_json
        write_json(inside(workspace(), 'requests', digest(context['run_id']) + '.json'),
                   {'dag_id': 'resume_prepare', **result})
        print(result)
        if result['skip']:
            raise AirflowSkipException(result['reason'] + '；run_key=' + result['run_key'])
        return result['run_key']

    @task
    def extract_materials(key):
        from resume_flow.extract import extract_run
        return invoke(extract_run, key)

    @task
    def organize_facts(key):
        from resume_flow.workflow import collect_facts
        return invoke(collect_facts, key, get_current_context()['params']['mode'])

    @task
    def write_draft(key):
        from resume_flow.workflow import draft_resume
        return invoke(draft_resume, key, get_current_context()['params']['mode'])

    @task
    def publish_review(key):
        from resume_flow.review import prepare_review
        from resume_flow.incremental import finish_version
        invoke(prepare_review, key)
        return invoke(finish_version, key)

    publish_review(write_draft(organize_facts(extract_materials(snapshot_materials()))))


@dag(dag_id='resume_export', schedule=None,
     start_date=pendulum.datetime(2026, 1, 1, tz='Asia/Shanghai'), catchup=False,
     max_active_runs=1, is_paused_upon_creation=True, tags=['newstar', 'resume'],
     default_args={'owner': 'newstar', 'retries': 1, 'retry_delay': timedelta(seconds=10),
                   'execution_timeout': timedelta(minutes=10)},
     params={'run_key': Param('demo-run', type='string', pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$'),
             'export_key': Param('', type='string', pattern=r'^$|^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$')},
     doc_md='必须先在本机审阅页确认正文与模板。验证确认 → 冻结版本 → Word → 同源 PDF → 自动检查与页面预览。完成后仍需视觉验收。')
def resume_export():
    @task
    def verify_and_freeze():
        from resume_flow.export import freeze_export
        context = get_current_context()
        params = context['params']
        key = params['export_key'] or 'e-' + hashlib.sha256(context['run_id'].encode()).hexdigest()[:24]
        return invoke(freeze_export, params['run_key'], key)

    @task
    def render_word(key):
        from resume_flow.export import create_docx, run_export_step
        return invoke(run_export_step, key, create_docx)

    @task
    def export_pdf(key):
        from resume_flow.export import convert_pdf, run_export_step
        return invoke(run_export_step, key, convert_pdf)

    @task
    def check_pages(key):
        from resume_flow.export import check_and_render, run_export_step
        return invoke(run_export_step, key, check_and_render)

    check_pages(export_pdf(render_word(verify_and_freeze())))


resume_prepare()
resume_export()
