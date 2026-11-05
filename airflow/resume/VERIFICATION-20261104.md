# 2026-11-04：增量检查与自然语言入口验证

使用内置虚构 demo；没有修改或确认用户个人材料。当前 `resume_prepare` 已启用，每半小时检查默认 demo；`resume_export` 保持手动、无 schedule。自动检查自己的目录需按 README 配置案例与岗位。

## 实际运行

- 真实 DeepSeek 将中文需求解析成 `resume_prepare` + case/target/mode；随后通过本机 Airflow JWT 与 REST `/api/v2` 提交。
- `nl-verify-natural-20261104-trigger`：五个任务最终 success，经实际 Celery 执行器完成。整理阶段刻意使用 offline 虚构样例，入口的请求解析使用真实 DeepSeek，二者分别记录。
- `nl-verify-natural-20261104-repeat`：再次通过真实 DeepSeek 解析同一需求并提交；首任务及四个下游均 skipped，后四项 try_number=0，未再次整理或起草。
- 真实模型还解析了导出请求：`nl-verify-natural-20261104-export` 对此前已确认的虚构版本 `demo-deepseek-20261103` 运行，四个任务均 success。新产物目录为 `outputs/nl-a82435ff2b37c86fd82e8919d06b8f8a/`；未将本次自动检查当作用户视觉验收。
- 自动调度 `scheduled__2026-11-04T00:30:00+00:00` 五个任务成功；后续 `scheduled__2026-11-04T01:00:00+00:00` 经失败恢复后首任务和全部下游 skipped。UTC 标识对应北京时间 08:30、09:00，不能将 logical date 当成实际任务开始时间。
- 实际 Airflow 3.3.2 DagBag 扫描只发现 `first_workflow`、`resume_prepare`、`resume_export`，import_errors=[]。

## 发现并修复的问题

1. 辅助模块含 Airflow 相关字符串后被扫描为 DAG，引发相对导入错误。新增 `.airflowignore` 排除 `resume_flow/`，真实文件发现列表与 DagBag 解析均确认修复。
2. 历史本机样例文件对容器不可读，最初使版本复用扫描失败。可选历史记录读取失败现在只输出版本名警告并继续检查，不影响当前材料；当前版本快照读取失败仍明确失败。补了先失败后通过的回归测试。通过 API 清除这次虚构运行的失败任务后，使用最新 DAG 重新执行成功；原日志保留，首任务 try_number=3。

## 可复查证据

- `resume_workspace/verification/natural-20261104.json`：真实模型解析后提交的请求摘要、运行 ID 和最终任务状态。
- `resume_workspace/verification/scheduled-20261104.json`：自动调度的运行与任务状态。
- Airflow `logs/dag_id=resume_prepare/run_id=nl-verify-natural-20261104-trigger/`：失败、定位、恢复记录。
- `tests/integration_natural_runtime.py`：仅用于本项目虚构样例的显式集成脚本；常规测试不调用真实模型。

全量单元测试覆盖原有文档流程及内容判重、文件删除/改名、JD/岗位/模式变化、失败重试、历史成功复用、旧文件权限异常、模型白名单与澄清、人工确认保护、JWT/REST 触发、请求冲突幂等和状态查询。

最终本机 `.venv` 全量 51 项 unittest 通过，Python 编译及 Compose `config --quiet` 通过，实际 `airflow dags list-import-errors` 无记录。额外在真实 worker 连续调用两次内容判重，均复用相同成功版本并 skip；已命名的手动成功版本及迁移后的旧版本也由回归测试保证持续复用。

剩余范围：用户本人真实材料、真实简历最终视觉验收及本人录屏讲解需由用户完成。
