# Incremental Skill Boundary Implementation Plan

> **For agentic workers:** Execute inline with superpowers:executing-plans. This continues the authorized experiment; do not spawn agents or commit/push.

**Goal:** 从5个覆盖发布材料任务的Skill开始，只在同一级全部6次完整通过后扩大到10、15、20及更高规模。

**Architecture:** 新建串行扩容驱动器，复用已验证来源库、原生function calling与文件导出。Skill工人返回原始文本，Python构造工具结果，去掉已确认出错的“正文再包模型JSON”环节。三个发布资料变体各两轮，最终交付单决定验收对象；旧稿保留但不因已修正的旧稿否定最终版。

**Tech Stack:** Python标准库、已有DeepSeek配置、现有163项本地能力库。

**Spec:** 当前用户“不能通过不算”“逐渐往大扩展”，以及本计划下述冻结协议。

## Global Constraints

- 每级6/6才能扩大；失败和错误不删、不抽成功样本、不隐式重试。
- 新任务族是原项目发布需求的3个资料变体，不与过去四类需求成功率混算。
- 全部原始Skill同时暴露；每次执行按所选原文方法处理；不预设角色、顺序或DAG。
- 判据仅来自用户业务要求，保留未知值可通过；可审阅草稿不被擅自要求可对外发布。
- 冻结资料、验收项、代码与嵌套工具库；正文、CSV、实际引用均保存。
- 资源不足与接口问题独立分类，不能当成模型数量上限。

## Review Focus

- 5/6、缺失试次或重复同一变体不能晋级。
- 正确的短CSV和带换行正文不得被接口格式误拦。
- 只验收最终列出的真实产物；最终答复本身不能补写交付。
- 未知仓库链接/数据不能被补造，建议不能伪装事实。
- 失败后不创建下一规模的任务。

## Tasks

- [x] Task 1: Add tested stage gate, exact CSV/command checks, final-deliverable selection and raw-text Skill adapter in `experiments/skill_boundary/incremental.py`; test with `test_incremental.py` before real calls. RED: missing module; GREEN:6 new tests and17 total tests passed.
- [x] Task 2: Freeze 3 release fixtures, pool ordering and rubric; execute 5→10→15→20→… sequentially while every prior stage has6/6, recording all outcomes and stopping at the first failed stage. baseline:5级6/6，10级5/6，未创建15级。
- [x] Task 2b: 独立bounded对照仅约束自增材料/无必要修订，同资料、同6/6门槛、同16轮预算，从5重新运行。B组5、10级各6/6，15级5/6后停止，未创建20级。
- [x] Task 3: Audit saved actual tool requests, deliverables and dependencies; report last fully passed size, failed next stage and limitations. 已核验30试次、210节点、107额外文件；19项回归测试通过。当前全过级10，下一档15未过，不称硬上限10。

## Execution Ledger

- Ruling: 使用当前工作区新增独立实验文件，不移动现有Skill材料、密钥配置或修改简历产品源文件；原有未提交文件保留，不自动提交。
- Previous root cause confirmed:4 observed JSON-control-character failures were all in the model-generated Skill-body JSON wrapper. New workers return raw text; host code serializes the tool result.
- Active series:`tmp/skill-boundary-v2/incremental/gradual-20261109-a/`，5起步、仅6/6晋级。
- Root cause evidence:baseline n010/ledger-r1在A011自增REVIEW.md、A015自增INDEX.md，随后A016—A019仅为这些文件做交叉同步，未提交最终清单，16轮后停止。不能将该失败直接归因于工具数量上限。
- Ruling:新增独立bounded对照，不提高预算/降低正确性，不复用失败系列成功样本；只有本新系列各级6/6才能继续。旧数据不覆盖。
- Current-source review tightened contradictory verifier handling:all six check booleans pluserrors=[] required. All actual promoted baseline verdicts already haderrors=[]，对既有判定无影响；冻结旧代码保留。
- Final review:驱动器确实先等整档6次再晋级；A无15目录、B无20目录；B15失败为实际存在附件A003-1.csv的文件名被误当作登记ID，未做模糊修正。两组资料及工具顺序逐字节一致。报告：`docs/Skill严格逐级扩容-20261109.md`。
