# 项目文件夹导航

整理日期为 2026 年 11 月 16 日。

## 按轮次进入

- [第一轮 · Airflow 与简历工作流](01-airflow-resume/README.md)
- [第二轮 · Skill 扩容与编排](02-skill-orchestration/README.md)
- [第三轮 · Dr.Spider 与 Agent 任务澄清](03-dr-spider/README.md)

## 现有目录的用途

| 目录或文件 | 用途 | 对应轮次 |
| --- | --- | --- |
| `airflow/` | Docker Compose、DAG、工作台和简历生成流程 | 第一轮、第二轮共用 |
| `experiments/skill_boundary/` | 早期 Skill 数量边界实验 | 第二轮 |
| `experiments/skill_boundary_f/` | F 版本实验协议、执行与复核 | 第二轮 |
| `experiments/skill_boundary_g/` | G 版本审查改进与对照协议 | 第二轮 |
| `experiments/skill_portal/` | Skill 工作台与 Airflow 执行桥 | 第二轮 |
| `tests/` | 现有工作流和实验平台测试 | 第一轮、第二轮 |
| `docs/` | 实验报告、口播稿、图表、历史设计与计划 | 主要为第二轮 |
| `output/` | 网页验收、实验汇总与复核结果 | 主要为第二轮 |
| `deliverables/` | 历史证据包、压缩包及解压目录 | 第二轮 |
| `tmp/` | 排错材料、截图、原始实验记录与上下文对照 | 第一轮、第二轮 |
| `airflow/resume_workspace/` | 本地简历材料、审阅版本与产物 | 第一轮 |
| `airflow/logs/` | Airflow 运行日志 | 第一轮、第二轮 |
| `.venv/` | 本地 Python 环境 | 现有项目共用 |
| `docker-junction-tools.ps1`、`repair-docker-paths.ps1` | Docker 路径处理脚本 | 现有环境 |
| `tasks/` | 按轮次组织的任务入口与学习准备材料 | 三轮 |

## 本次整理方式

本次采用按轮次建立目录入口的方式，集中标明每轮的要求、源码、报告和证据位置。原始报告与实验文件之间存在路径引用，`tmp/` 中也保存了复核材料。后续物理迁移这些目录时，需要同时核对程序路径、文档链接和证据清单。

本次新增三个轮次目录及第三轮知识准备路线，并在根 README 增加统一入口。历史材料的完成状态按已保存记录描述，当前服务健康和本人课程提交状态需分别核实。

## 第三轮后续资料放置约定

任务说明与学习记录先集中在 `tasks/03-dr-spider/`。项目入口已按用户更正为 `ymxiong/rsi-data-visual`。待开始实际实验时，再根据该项目的目录和依赖安排代码、数据与结果位置。外部代码版本、数据版本、基线配置和评测方式会在开始实验时记录。
