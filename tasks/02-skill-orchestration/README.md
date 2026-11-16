# 第二轮 · Skill 扩容与自主编排

[返回项目导航](../README.md)

## 任务脉络

已有选题为“Skill 做多”，提交准备按基础档与进阶档组织。主要内容包括逐步扩容候选库、自主编排、重复实验、产物正确性复核、失败定位和改进尝试。

## 优先阅读

| 目的 | 入口 |
| --- | --- |
| 了解实现原理与录屏步骤 | [进阶档实现原理与录屏详解](../../docs/第二次任务进阶档实现原理与录屏详解-20261112.md) |
| 查看要求、录屏与表单填写 | [提交核对与填写稿](../../docs/第二次任务今晚提交核对与填写稿-20261112.md) |
| 查看进阶档补齐证据 | [进阶档补齐验收](../../docs/第二次任务进阶档补齐验收-20261112.md) |
| 启动和使用 Skill 工作台 | [工作台说明](../../experiments/skill_portal/README.md) |
| 查看网页修复及后续两组实验 | [2026-11-13 补测报告](../../docs/Skill网页修复与DeepSeek补测-20261113.md) |
| 核对补测机器可读结果 | [补测汇总](../../output/skill-web-20261113/results.json) |
| 查看继续探索边界的阶段记录 | [后续批次进度记录](../../output/boundary-campaign-20261113/进度.md) |

## 源码与材料位置

- 实验实现分别位于 [早期版本](../../experiments/skill_boundary/README.md)、[F 版本](../../experiments/skill_boundary_f/README.md)和[G 版本说明](../../experiments/skill_boundary_g/VARIANT_G.md)。
- 网页集成位于 `experiments/skill_portal/`、`airflow/dags/skill_experiment.py` 和 `airflow/dags/resume_flow/`。
- 历史报告集中在 `docs/`，图表位于 `docs/figures/`，历史设计与计划位于 `docs/superpowers/`。
- 验收与复核汇总位于 `output/skill-advanced-20261112/`、`output/skill-web-20261113/` 和 `output/boundary-campaign-20261113/`。
- 原始实验记录主要位于 `tmp/skill-boundary-v2/`，历史复现包位于 `deliverables/`。

## 阅读实验结果时的口径

2026 年 11 月 13 日网页补测的汇总文件记录，DeepSeek 在 N100 和 N180 各完成十次，内容复核正确数分别为 2/10 和 3/10，两组自动核验均为 10/10。歧义样本保留在分母内，汇总字段 `stable_failure_count_established` 为 `false`。这些数字对应该次网页补测，其他历史批次需要查看各自配置与复核记录。[补测汇总](../../output/skill-web-20261113/results.json)

继续探索数量边界的批次另有进度记录。该记录存在未完成和待复核项，引用前需对照原始结果及最终复核文件确认。本人录屏、上传和正式课程提交的状态也需按实际完成情况填写。[阶段记录](../../output/boundary-campaign-20261113/进度.md)

第三轮将继续沿用记录配置、保存原始输出、复核最终结果、逐类分析失败的实验习惯。
