# 第一个 Airflow 工作流

代码：[dags/first_workflow.py](dags/first_workflow.py)。适配当前部署的 Airflow 3.3.2，使用官方 [TaskFlow API](https://airflow.apache.org/docs/apache-airflow/3.3.2/tutorial/taskflow.html)。不需要额外安装 Python 依赖或重新构建镜像。

## 工作流做什么

```text
prepare_data → process_data → save_result
读取整数列表     计算平方和       写入 JSON 文件
```

- **DAG**：整个工作流，名称为 `first_workflow`。
- **Task**：工作流中的一个步骤；上游成功后，下游才会执行。
- **XCom**：传递任务间的少量数据。这里把上游返回值作为下游参数，TaskFlow 会自动建立依赖和传值。
- **Dag Run**：一次完整运行，各次运行的状态、日志和结果相互区分。

默认输入是 `[1, 2, 3, 4, 5]`，平方列表为 `[1, 4, 9, 16, 25]`，总和为 `55`。

## 在页面上操作

1. 打开 <http://localhost:8080>，使用已有账户登录。
2. 在 DAG 列表中搜索 `first_workflow`；新文件需要等待 DAG processor 完成扫描。
3. 点击触发按钮（Trigger），保留默认参数，执行一次。如果页面要求先启用 DAG，再打开启用开关。
4. 打开这次运行的 Graph / Grid 视图，查看三个任务的状态；点击任务进入 Logs 查看中文日志。
5. 在宿主机 `D:\code\newstar\airflow\logs\first_workflow\results\` 查看 JSON 结果文件。文件名由运行 ID 的哈希生成，文件内容保留原始 `run_id`。

DAG 初次发现时为暂停状态；启用后按**北京时间每天 09:00**自动调度。`catchup=False` 不会补跑自开始日期以来的全部历史任务；启用时仍可能立即产生一次到期运行。只做手动练习时，练习结束后可暂停 DAG。

## 练习失败和重试

手动触发时可修改 `numbers` 和 `failure_mode`。每个任务最多重试 2 次，两次尝试之间等待 10 秒；实际等待时间还受调度影响。

| 参数 | 预期行为 |
| --- | --- |
| `failure_mode=none` | 默认模式，三个任务成功 |
| `failure_mode=once` | `process_data` 第一次故意报错，自动重试后成功，继续保存结果 |
| `failure_mode=always` | `process_data` 三次尝试均失败，`save_result` 为 `upstream_failed`，本次运行没有结果文件 |

推荐第二次运行使用 `numbers=[2,3,4]`、`failure_mode=once`，成功后平方和应为 `29`。观察处理任务从运行到等待重试、再次运行、成功的过程；第一次尝试的日志中会出现演示用的 `ValueError`。

整数列表不能为空，最多 100 项，每项限制在 -10000 到 10000 之间；触发参数会进行校验。

## 从 PowerShell 验证

在此电脑上 Docker 可执行文件的路径如下；如果已配置 PATH，也可以直接使用 `docker`。

```powershell
Set-Location D:\code\newstar\airflow
$dockerExe = 'D:\docker\anzhuang\DockerDesktop\resources\bin\docker.exe'

# 默认成功路径：直接测试一个完整 Dag Run。
& $dockerExe compose exec -T airflow-scheduler airflow dags test first_workflow -f /opt/airflow/dags/first_workflow.py

# 使用实际 Celery 执行器，验证工作节点与首次失败后的重试。
& $dockerExe compose exec -T airflow-scheduler airflow dags test first_workflow -f /opt/airflow/dags/first_workflow.py --use-executor -c '{"numbers":[2,3,4],"failure_mode":"once"}'

# 故意让任务最终失败：用于查看重试耗尽和上游失败状态。
& $dockerExe compose exec -T airflow-scheduler airflow dags test first_workflow -f /opt/airflow/dags/first_workflow.py -c '{"failure_mode":"always"}'
```

`dags test` 会创建真实的运行记录和结果文件，但并不等同于验证每天 09:00 的定时触发。命令正常退出也不能单独证明运行成功，应同时检查最终 Dag Run 和各任务状态。

若页面没有出现 DAG，先检查 `airflow-dag-processor` 是否健康，并查看导入错误：

```powershell
& $dockerExe compose exec -T airflow-scheduler airflow dags list-import-errors
& $dockerExe compose logs --tail 80 airflow-dag-processor
```

## 后续扩展

完成此练习后，下一步选择实际 Skill 或应用场景，把 `process_data` 中的示例计算替换为实际调用。当前工作流用于学习 Airflow，尚未接入实际 Skill 和大模型。

## 已验证结果（2026-11-02）

已在当前 Airflow 3.3.2 容器中实际执行，并读取运行记录核对状态与尝试次数：

| 模式 | 运行结果 | `process_data` 尝试次数 | 保存任务 |
| --- | --- | --- | --- |
| `none` | `success`，平方和 `55` | 1 | `success`，JSON 已核对 |
| `once`（CeleryExecutor） | `success`，平方和 `29` | 2 | `success`，JSON 已核对 |
| `always` | 预期的 `failed` | 3 | `upstream_failed`，未执行 |

`dags list-import-errors` 未发现导入错误。重试与持续失败的测试日志保存在 `logs/verification/`，该目录随运行日志被 Git 忽略。页面操作及每天 09:00 的自动调度尚未实测，DAG 保持暂停状态。页面中会保留上述三次测试记录，其中红色运行是有意制造的失败演示。
