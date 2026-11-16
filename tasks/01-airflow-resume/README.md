# 第一轮 · Airflow 与简历工作流

[返回项目导航](../README.md)

## 任务脉络

1. 部署 Airflow，理解 DAG、Task、任务依赖、调度、监控与异常处理。
2. 集成 Skill，将简历材料整理、人工审阅和文件生成接入工作流。
3. 接入大模型，通过自然语言触发工作流和查询运行状态。

## 从这些文件进入

| 目的 | 入口 |
| --- | --- |
| 查看原始阶段清单 | [根 README](../../README.md) |
| 学习第一个 DAG 与失败重试 | [Airflow 入门说明](../../airflow/README.md) |
| 使用简历工作流与自然语言入口 | [简历工作流说明](../../airflow/resume/README.md) |
| 查看最初真实执行与文档验收 | [2026-11-03 验证记录](../../airflow/resume/VERIFICATION.md) |
| 查看自然语言入口与调度验证 | [2026-11-04 验证记录](../../airflow/resume/VERIFICATION-20261104.md) |
| 查看网页材料入口、审阅与导出改进 | [2026-11-05 验证记录](../../airflow/resume/VERIFICATION-20261105.md) |
| 查看本人录屏与提交准备材料 | [验收口播稿](../../airflow/resume/验收口播与表单填写稿.md) |

源码主要位于 `airflow/dags/`、`airflow/dags/resume_flow/` 和 `airflow/resume/`。个人材料和产物位于 `airflow/resume_workspace/`，运行日志位于 `airflow/logs/`。

## 状态与第三轮可复用知识

历史记录包含环境部署、真实模型调用、DAG 执行、人工审阅与 Word/PDF 导出验证。本人掌握程度、真实材料核实和课程提交完成情况需结合实际操作确认。本次整理依据已有文件，当前服务状态需在使用时检查。

第三轮可复用 Python 脚本、API 调用、输入输出记录、运行日志和失败定位的经验。后续学习 Agent 时，将结合实际代码说明其模型决策、工具调用与任务调度分别由谁负责。
