"""第一个 DAG：准备数字 → 计算平方 → 保存 JSON 结果。"""

import hashlib
import json
import logging
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import Param, dag, get_current_context, task

logger = logging.getLogger(__name__)


@dag(
    dag_id="first_workflow",
    description="入门练习：任务依赖、参数传递、定时调度、日志与失败重试",
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Shanghai"),
    schedule="0 9 * * *",  # 北京时间每天 09:00
    catchup=False,  # 不补跑开始日期至今的历史任务
    max_active_runs=1,
    is_paused_upon_creation=True,
    default_args={
        "owner": "newstar",
        "retries": 2,  # 首次失败后，最多再试两次
        "retry_delay": timedelta(seconds=10),
        "execution_timeout": timedelta(minutes=2),
    },
    params={
        "numbers": Param(
            [1, 2, 3, 4, 5],
            type="array",
            items={"type": "integer", "minimum": -10000, "maximum": 10000},
            minItems=1,
            maxItems=100,
            title="待处理的整数列表",
        ),
        "failure_mode": Param(
            "none",
            type="string",
            enum=["none", "once", "always"],
            title="失败演示：none 正常 / once 首次失败 / always 持续失败",
        ),
    },
    tags=["newstar", "tutorial"],
    doc_md="""
### 第一个工作流
`prepare_data → process_data → save_result`

默认输入 `[1, 2, 3, 4, 5]`，输出平方列表及其总和 `55`。
任务间通过 TaskFlow / XCom 传递少量数据；每次运行的结果保存到
`/opt/airflow/logs/first_workflow/results/`（宿主机的 `airflow/logs/` 下）。

手动触发时，`failure_mode=once` 可演示失败后重试成功；
`failure_mode=always` 可演示重试耗尽后失败、下游无法执行。
启用 DAG 后按北京时间每天 09:00 调度，默认暂停。
""",
)
def first_workflow():
    @task
    def prepare_data() -> list[int]:
        """步骤一：读取触发参数，默认准备五个整数。"""
        numbers = get_current_context()["params"]["numbers"]
        logger.info("准备数据：%s", numbers)
        return numbers

    @task(multiple_outputs=False)
    def process_data(numbers: list[int]) -> dict:
        """步骤二：计算平方，并可选演示任务失败。"""
        context = get_current_context()
        mode = context["params"]["failure_mode"]
        attempt = context["ti"].try_number
        logger.info("开始处理，第 %s 次尝试，失败演示模式：%s", attempt, mode)
        if mode == "always" or (mode == "once" and attempt == 1):
            raise ValueError("演示异常：请观察任务日志和自动重试状态。")

        squares = [number * number for number in numbers]
        result = {
            "numbers": numbers,
            "squares": squares,
            "count": len(numbers),
            "total": sum(squares),
        }
        logger.info("处理结果：%s", result)
        return result

    @task
    def save_result(result: dict) -> str:
        """步骤三：每个 Dag Run 保存一份文件；重试时覆盖同一份结果。"""
        context = get_current_context()
        run_id = context["run_id"]
        # run_id 仅用于生成安全文件名，不直接拼入路径。
        filename = hashlib.sha256(run_id.encode("utf-8")).hexdigest() + ".json"
        directory = Path("/opt/airflow/logs/first_workflow/results")
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / filename
        payload = {"dag_id": "first_workflow", "run_id": run_id, **result}
        temporary = output.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output)
        logger.info("结果已保存：%s；平方和：%s", output, result["total"])
        return str(output)

    # 把上游返回值作为下游输入，Airflow 会自动建立依赖并通过 XCom 传值。
    save_result(process_data(prepare_data()))


first_workflow()
