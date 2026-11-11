# DeepSeek 十次准确率执行计划

使用 executing-plans 执行，按 requesting-code-review 对结果做独立复核。

目标为166个候选Skill下，DeepSeek完整原任务十次已验证正确率。沿用已完成的一次正式云端结果，再补九次。用户此次要求将API测试扩大至十次基线。

冻结166份真实原源、完整CourseDock任务、原六标准、F实现、已配置deepseek-flash、temperature0.2、thinking disabled、legacy自动审查、16轮预算、原生工具调用及真实依赖。API未设置随机seed，试次编号表示独立运行序号。最终采用所有实际最终文件直接和独立审查，通过数除以10。未知或未解决歧义未计入正确数，原始失败保留。基础设施中断时如实记录完成数量。

- [x] 冻结已有一次原始结果及当前裁定、来源、用例、源码与审计适配哈希。
- [x] 执行九次新完整任务，单并发，原失败不覆盖。
- [x] 审计每份实际原源、全文上游、DAG、原生回复与费用用量。
- [x] 阅读全部自动正例的最终实文件，按原六标准核验并独立复核。
- [x] 汇总十次准确率、逐次K/节点/链长、失败位置、配置及实际API用量。
- [x] 完成当前报告及可核查证据归档。

新增入口为 `tmp/skill-boundary-v2/run_deepseek_ten_20261111.py`，已有一次云端观测在 `boundary-166-deepseek-once-20261111-network-recovery`，新九次在 `boundary-166-deepseek-ten-supplement-20261111`。沿用之前已经核验的四个公开仓库Skill原源以及虚构业务材料范围，API认证密钥只在认证头使用。

最终9/10已验证正确，1次歧义未计通过。独立全文复核覆盖43个最终引用和20份CSV，与当前裁定一致。新增9次主进程61399已exit0，audit通过。合计119新回复、2455281tokens。最终ZIP及异目录离线核验均通过，回执保存在deepseek-ten-delivery-verification-20261111.json。
