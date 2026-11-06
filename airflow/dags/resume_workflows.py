"""Incremental material checks and human-approved export; heavy imports in tasks."""
import hashlib
import os
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import Param, dag, task, get_current_context
from airflow.providers.standard.sensors.python import PythonSensor


def workspace():
    return Path(os.environ.get('RESUME_WORKSPACE', '/opt/airflow/resume_workspace'))


def materials_submitted(entry):
    from resume_flow.intake import entry_ready
    from airflow.sdk.exceptions import AirflowSkipException
    try:
        return entry_ready(workspace(), entry)
    except ValueError as error:
        raise AirflowSkipException(str(error)) from None


def invoke(function, *args):
    from airflow.sdk.exceptions import AirflowFailException, AirflowException
    from resume_flow.drafts import DraftBusyError
    try:
        guarded = {'extract_run', 'collect_facts', 'draft_resume', 'prepare_review',
                   'finish_version', 'freeze_run_export', 'freeze_export'}
        if function.__name__ in guarded:
            from resume_flow.drafts import draft_guard, ensure_active
            with draft_guard(workspace(), args[0], timeout=30):
                ensure_active(workspace(), args[0])
                return function(workspace(), *args)
        return function(workspace(), *args)
    except DraftBusyError as error:
        raise AirflowException(str(error)) from None
    except ValueError as error:
        # User/configuration problems need intervention, not task-level retries.
        raise AirflowFailException(str(error)) from None


def review_approved(version, dag_run_id):
    from airflow.sdk.exceptions import AirflowSkipException
    from resume_flow.approval_wait import await_run_approval
    from resume_flow.drafts import is_deleted
    if version.get('deleted') or (version.get('run_key') and is_deleted(workspace(), version['run_key'])):
        raise AirflowSkipException('草稿已删除，本次运行结束')
    if version.get('scheduled_unchanged'):
        raise AirflowSkipException('定时检查未发现材料变化，沿用已有审阅运行')
    approved = await_run_approval(workspace(), version['run_key'], dag_run_id)
    if not approved:
        print('等待人工审阅。请在本次运行的工作台确认，确认后本次运行继续导出。')
    return approved


@dag(dag_id='resume_prepare', schedule='*/30 * * * *',
     start_date=pendulum.datetime(2026, 1, 1, tz='Asia/Shanghai'), catchup=False,
     max_active_runs=16, is_paused_upon_creation=True, tags=['newstar', 'resume'],
     default_args={'owner': 'newstar', 'retries': 1, 'retry_delay': timedelta(seconds=10),
                   'execution_timeout': timedelta(minutes=45)},
     params={'case_id': Param('', type='string', pattern=r'^$|^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$',
                             title='材料案例（新建可留空）', description='新案例会打开材料页并等待提交。留空自动建立本次案例。'),
             'upload_materials': Param(False, type='boolean', title='先打开材料填写页',
                                       description='已有材料时也先打开网页补充；新案例会自动进入材料页。'),
             'run_key': Param('', type=['null', 'string'], pattern=r'^$|^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$',
                              title='材料版本 run_key（可留空）', description='留空自动检查当前材料并确定版本。手动填写会固定该标识的材料快照。'),
             'target': Param(os.environ.get('RESUME_DEFAULT_TARGET', ''), type=['null', 'string'], maxLength=200,
                             title='目标岗位 target（可选）', description='例如 Python 后端实习。留空生成通用草稿。'),
             'jd': Param('', type=['null', 'string'], maxLength=20000, format='multiline',
                         title='岗位要求 jd（可选）', description='粘贴招聘岗位说明，没有则留空。个人材料放入案例文件夹。'),
             'mode': Param(os.environ.get('RESUME_DEFAULT_MODE', 'deepseek'), enum=['deepseek', 'offline'], type='string',
                           title='处理模式 mode', description='offline 仅接受原样虚构 demo。deepseek 使用真实模型，会发送提取文字。')},
     doc_md='从本DAG开始新建简历。open_material_page发布本次专用网页，await_materials等待导入材料并提交，随后在同一次运行继续归档、提取、整理和起草。await_review使用reschedule模式等待人工审阅，网页确认后同一次运行继续导出，等待上限7天。每半小时检查默认案例，未变化时沿用已有审阅运行。材料处理使用单槽resume_preparation池，等待节点释放工作进程。')
def resume_prepare():
    @task
    def open_material_page():
        from resume_flow.intake import prepare_entry
        context = get_current_context()
        entry = invoke(prepare_entry, context['run_id'], dict(context['params']),
                       context['dag_run'].run_type == 'scheduled')
        print(entry)
        return entry

    @task(pool='resume_preparation')
    def snapshot_materials(entry):
        from resume_flow.incremental import prepare_version
        from resume_flow.intake import has_materials, entry_config
        params = invoke(entry_config, entry)
        fixed_snapshot = params['run_key'] and (workspace() / 'runs' / params['run_key'] / 'manifest.json').is_file()
        if not fixed_snapshot and not has_materials(workspace(), params['case_id']):
            result = {'run_key': '', 'skip': True, 'waiting_input': True,
                      'mode': params['mode'],
                      'reason': '材料尚未提交，请在工作台填写材料后继续'}
            print(result)
            return result
        result = invoke(prepare_version, params['case_id'], params['run_key'] or '',
                        params['target'] or '', params['jd'] or '', params['mode'])
        result['mode'] = params['mode']
        result['scheduled_unchanged'] = (result['skip']
                                         and get_current_context()['dag_run'].run_type == 'scheduled')
        from resume_flow.drafts import is_deleted
        if is_deleted(workspace(), result['run_key']):
            result.update(skip=True, deleted=True, reason='草稿已删除，可在工作台回收站恢复')
        print(result)
        return result

    @task(pool='resume_preparation')
    def extract_materials(version):
        from airflow.sdk.exceptions import AirflowSkipException
        from resume_flow.extract import extract_run
        if version['skip']:
            raise AirflowSkipException(version['reason'] + '；run_key=' + version['run_key'])
        return invoke(extract_run, version['run_key'])

    @task(pool='resume_preparation')
    def organize_facts(key, version):
        from resume_flow.workflow import collect_facts
        return invoke(collect_facts, key, version['mode'])

    @task(pool='resume_preparation')
    def write_draft(key, version):
        from resume_flow.workflow import draft_resume
        return invoke(draft_resume, key, version['mode'])

    @task(trigger_rule='none_failed', pool='resume_preparation')
    def publish_review(version):
        from resume_flow.review import prepare_review
        from resume_flow.incremental import finish_version
        from resume_flow.approval_wait import publish_review_request
        if version.get('deleted'):
            print('草稿已删除，本次运行结束')
            return ''
        if version.get('waiting_input'):
            print('等待材料填写：' + version.get('input_url', 'http://localhost:8765'))
            return ''
        key = version['run_key']
        if version.get('scheduled_unchanged'):
            print('定时检查材料未变化，保留已有的人工审阅入口')
            return key
        if not version['skip']:
            invoke(prepare_review, key)
            invoke(finish_version, key)
        context = get_current_context()
        from resume_flow.storage import read_json, run_dir
        params = {**dict(context['params']), **read_json(run_dir(workspace(), key) / 'manifest.json')['config'],
                  'mode': version['mode'], 'review_wait': 'reschedule'}
        return invoke(publish_review_request, version, context['run_id'], params)

    @task
    def verify_and_freeze(key):
        from resume_flow.approval_wait import freeze_run_export
        return invoke(freeze_run_export, key, get_current_context()['run_id'])

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

    entry = open_material_page()
    material_wait = PythonSensor(task_id='await_materials', python_callable=materials_submitted,
                                op_kwargs={'entry': entry}, mode='reschedule', poke_interval=10,
                                timeout=86400, soft_fail=True,
                                execution_timeout=timedelta(minutes=2))
    entry >> material_wait
    version = snapshot_materials(entry)
    material_wait >> version
    drafted = write_draft(organize_facts(extract_materials(version), version), version)
    published = publish_review(version)
    drafted >> published
    waiting = PythonSensor(task_id='await_review', python_callable=review_approved,
                           op_kwargs={'version': version, 'dag_run_id': '{{ run_id }}'},
                           mode='reschedule', poke_interval=10, timeout=604800,
                           retries=0, execution_timeout=timedelta(minutes=2))
    published >> waiting
    frozen = verify_and_freeze(published)
    waiting >> frozen
    check_pages(export_pdf(render_word(frozen)))


@dag(dag_id='resume_export', schedule=None,
     start_date=pendulum.datetime(2026, 1, 1, tz='Asia/Shanghai'), catchup=False,
     max_active_runs=1, is_paused_upon_creation=True, tags=['newstar', 'resume'],
     default_args={'owner': 'newstar', 'retries': 1, 'retry_delay': timedelta(seconds=10),
                   'execution_timeout': timedelta(minutes=10)},
     params={'run_key': Param('demo-run', type='string', pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$'),
             'export_key': Param('', type=['null', 'string'], pattern=r'^$|^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$',
                                 title='导出版本 export_key（可留空）', description='留空自动生成独立导出标识。')},
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
