"""Interactive entry point: open materials page, wait, then trigger preparation."""
import os
from pathlib import Path

import pendulum
from airflow.sdk import Param, dag, task
from airflow.providers.standard.sensors.python import PythonSensor
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator


def material_submission_ready(intake_id):
    from resume_flow.intake import intake_ready
    return intake_ready(Path(os.environ.get('RESUME_WORKSPACE', '/opt/airflow/resume_workspace')), intake_id)


@dag(dag_id='resume_start', schedule=None,
     start_date=pendulum.datetime(2026, 1, 1, tz='Asia/Shanghai'), catchup=False,
     max_active_runs=16, is_paused_upon_creation=True, tags=['newstar', 'resume', '开始制作'],
     params={'case_id': Param('', type='string', pattern=r'^$|^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$',
                              title='材料案例（可留空）', description='留空自动建立本次材料入口，触发前无需创建文件夹。'),
             'target': Param('', type='string', maxLength=200, title='目标岗位（可在网页填写）'),
             'jd': Param('', type='string', maxLength=20000, format='multiline', title='岗位要求（可选）'),
             'mode': Param('deepseek', type='string', enum=['deepseek', 'offline'], title='整理方式')},
     doc_md='新建简历请触发本入口。本机引导程序会打开材料页，也可打开[工作台](http://localhost:8765)的待提交入口。上传文件或导入GitHub后点击“提交材料并继续”，await_materials通过后自动触发resume_prepare。等待材料独立于制作队列，最长24小时。')
def resume_start():
    @task
    def open_material_page():
        from airflow.sdk import get_current_context
        from resume_flow.intake import open_intake
        context = get_current_context()
        return open_intake(Path(os.environ.get('RESUME_WORKSPACE', '/opt/airflow/resume_workspace')),
                           'resume_start', context['run_id'], dict(context['params']))['id']

    @task
    def read_submission(intake_id):
        from resume_flow.intake import get_intake
        return get_intake(Path(os.environ.get('RESUME_WORKSPACE', '/opt/airflow/resume_workspace')), intake_id)['conf']

    intake_id = open_material_page()
    waiting = PythonSensor(task_id='await_materials', python_callable=material_submission_ready,
                           op_kwargs={'intake_id': intake_id}, mode='reschedule',
                           poke_interval=10, timeout=86400, soft_fail=True)
    intake_id >> waiting
    conf = read_submission(intake_id)
    waiting >> conf
    TriggerDagRunOperator(task_id='start_prepare', trigger_dag_id='resume_prepare',
                          trigger_run_id='intake-{{ ti.xcom_pull(task_ids="open_material_page") }}',
                          conf=conf, skip_when_already_exists=True)


resume_start()
