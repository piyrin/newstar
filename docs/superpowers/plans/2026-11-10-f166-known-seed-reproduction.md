# F166 known-seed reproduction implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. Preserve the running F queue and its frozen runtime; no delegation or commits.

**Goal:** 对刚通过完整内容复核的 F32 N166/seed3 在全新目录执行一次相同配置的完整任务，明确验证功能是否复现及请求/输出是否逐字相同。

**Architecture:** 新增临时预注册和独立启动入口，不修改 F 的 Python 实现。原 F32/F40 串行队列结束且 handle62447 终止后，加载原完整用例与166来源，以 local_seed=3 重跑一次；单试次目录 repeat=1 只作为独立复现组的索引，不改变模型 seed。保存全部请求、响应、实际产物和独立内容复核。

**Tech Stack:** Python standard library, existing frozen F runner, loopback Ollama0.33.1/Qwen3.5:9b.

**Spec:** docs/Skill编排实现与汇报说明-20261110.md；用户要求“确保此次所扩充的正确性稳定性可复现性前提下 探索边界”。

## Global constraints

- 不使用付费 API，不下载新模型；原全部facts、六标准、166候选、16轮及完整源/上游不变。
- 原 E/F 分数和失败保留；已知seed重跑不新增独立随机样本，不与原三次合并成功率。
- 不重放、不隐藏重试、不强制原路线或修改业务输出；复现失败如实记录。
- F 运行源码及校准hash仍须一致，先等62447权威终止，禁止并发模型试验。
- 临时入口位于 tmp/skill-boundary-v2；仅记录和调用冻结实现。现有隔离 F 副本保持，当前连续实验不另迁移工作区。

## Review focus

- 单试次索引1可能被误用为seed1：启动边界必须实际传seed3，全部真实请求逐项核验seed3。
- 改context、源文件、原正确产物或实现hash：预检拒绝，不自动“修正”。
- 前一队列未结束：入口拒绝，verify-only允许做离线核验但不运行模型。
- 新轨迹可能不同：报告差异，不以强制原DAG/替换旧响应伪造可复现。
- 同seed成功不证明普遍稳定：单列复现组和原三seed正确率。

## Tasks

- [x] 写入不可覆盖的预注册，固定原成功试次、seed3、context32768、模型digest、原请求/最终产物/全部运行实现hash。
- [x] 实现隔离复现入口及verify-only；用离线门槛测试核验错seed、错context和未结束队列均不能发起模型调用。
- [x] 62447终止后实际运行一次，保留成功或失败；执行原F物理/来源审计，核验每次真实请求的seed及零重放。
- [x] 直接复核全最终正文和实际附件，比较原/新请求字节、规范化调用和正文；不同则解释，不改原记录。
- [ ] 将F32、F40及复现结果、源/配置/实现和明确局限纳入最终复现包，哈希及异目录验证后完成整体验收审计。

Ruling: 只新增原最大已知正确规模的一个已知seed复现，而不另加三个独立样本或重抽直到成功；这是可复现性验证，不估计总体稳定率。当前模型队列不变。

门槛验证：7项离线测试通过，初始缺入口6项失败、另加“已结束但无完整audit不能启动”回归先红后绿。实际调度边界捕获确认repeat索引1仍向冻结runner传local_seed3/32768/166和原完整用例。verify-only禁止网络实查；入口、测试及原预注册hash已另行冻结，原F实现未改。这里只证明入口防错，未运行已知seed复现。

实际结果：39382已exit0，完整已知166/seed3新目录重跑正确，2节点/2附件/10真实新回复且无重放。新终稿89行、旧85行，全部六标准通过；首worker请求逐字相同但输出不同，功能复现成立、位级轨迹复现不成立，原因未隔离。原各档1/3不变。剩余联合导出与交付审计。
