# 第三轮 · Dr.Spider 与 Agent

2026 年 11 月 16 日更新。已开始必做任务的数据集入门，完成官方数据下载、来源校验、初步盘点与一条标准 SQL 的只读执行。基线配置、模型预测和 Agent 实现进入后续步骤。

[返回项目导航](../README.md) · [知识准备路线](学习路线.md) · [数据概览与第一课](数据概览与第一课.md)

当前先推进任务1，按[任务1逐步完成指南](任务1逐步完成指南.md)从 SQL 小练习、读取真实样本、运行抽样基线，逐步完成实验表、五类问题分析与代码阅读记录。指南包含对应学习网址、可运行例子和结果检查方法。

用户希望在本周五前完成两项任务，每天约可投入 3 小时。按周四 11 月 19 日晚完成核心交付倒排，具体学习、实现与验收步骤见[周五前学习与实现计划](周五前学习与实现计划.md)。

## 收到的任务要求

通知最初指定 `ymxiong/rsi-data`，用户随后补充 `ymxiong/rsi-data-visual`。当前两个入口分别核对，通知中的地址按最初版本列出。

> 任务1（必做，满分5分）
>
> 论文同学分析至少一个数据集，学习书写第一个实验表，基线跑起来，分门别类理清数据集里的问题，至少5种问题，具体分析哪个数据集由熊博士安排。熟悉 https://github.com/ymxiong/rsi-data ，下一步需要在其中验证Agent。
>
> 任务2（本周选做，第4周必做，本周做拿满分，下周做减半。任选其一，如果本周有同学做了，下周则删去）
>
> 启动 https://github.com/ymxiong/rsi-data ，实现一个单数据表Agent（5分），实现Agent与Agent组织后生成SQL（5分）。

用户已明确需要弄清楚的数据集为 **Dr.Spider**，现已授权开始第一个任务，希望接受分步指导，并在过程中补齐缺漏知识。用户基本没学过 SQL，教学从关系表与基本查询开始。

## 必做任务的交付理解

| 要求 | 后续需要形成的结果 | 当前状态 |
| --- | --- | --- |
| 分析至少一个数据集 | 讲清 Dr.Spider 的任务、来源、组成、输入输出和适用场景 | 已下载校验，完成规模与配对标识初查，开始学习样本 |
| 基线跑起来 | 一套可复现的模型或系统配置、实际预测与评测结果 | 待确定基线并运行 |
| 学习书写第一个实验表 | 清晰呈现实验设置、样本量、指标和实际结果 | 待学习并生成真实结果 |
| 至少五种问题 | 分类定义、真实样例、表现与原因分析 | 已列出五类扰动作为学习起点，待结合真实模型错误分析 |
| 熟悉项目代码 | 理解项目入口、数据与 Agent 接口 | 已读取 rsi-data 的 dev_main 根目录、包配置与提交信息 |

这里将交付物展开为便于后续学习的检查项，具体提交格式、基线选择和评测要求仍需结合熊博士安排。

## Dr.Spider 的定位

Dr.Spider 是基于 Spider 开发集构建的 Text-to-SQL 鲁棒性评测基准，相关论文发表于 ICLR 2023。Text-to-SQL 以自然语言问题和数据库信息为输入，目标是生成 SQL。Dr.Spider 通过有针对性的扰动，考察模型在输入或任务发生变化时的表现。[论文](https://arxiv.org/abs/2301.08881)

官方仓库说明包含 17 组扰动测试，其中数据库相关 3 组、自然语言问题相关 9 组、SQL 相关 5 组。每组提供扰动前后配对材料。后续需要结合每类定义和真实样例判断相应变化对问题、SQL 与数据库的影响。[官方数据说明](https://github.com/awslabs/diagnostic-robustness-text-to-sql/blob/main/README.md)

分析从官方分类入手理解模型困难，再根据实际错误形成问题分析。已初选表结构同义改名、表结构缩写、问题关键词改写、问题列名同义表达和排序方向改变五类，供逐项学习真实样本。作业中“至少五种问题”的最终口径需结合熊博士安排确认。

## 项目代码当前可核实状态

2026 年 11 月 16 日重新核对，`ymxiong/rsi-data` 已有代码，默认分支为 `dev_main`。分支顶端提交为 `bcdebdff352af9489d67f9f3b050daacc7a60e90`，提交日期为 2025 年 9 月 26 日。当前 GitHub 页面搜索快照仍显示先前空仓库内容，此处依据实时 GitHub 接口读取的目录与提交信息更新。[代码目录](https://github.com/ymxiong/rsi-data/tree/dev_main) [顶端提交](https://github.com/ymxiong/rsi-data/commit/bcdebdff352af9489d67f9f3b050daacc7a60e90)

根目录的 `package.json` 标明包名 `@horsecoder/visual-core`、版本 `0.3.12`、描述“可视化核心”，并包含 React、TypeScript、Rollup 和 Parcel 配置。已读取的目录包含 `src/VisualDiagram`、`demo` 和 `types`。依据这些内容，可以确认当前分支承载可视化核心代码；其与作业所需完整 Agent 系统的关系仍需继续核对。[包配置](https://github.com/ymxiong/rsi-data/blob/dev_main/package.json)

2026 年 11 月 16 日用户将项目入口更正为 `ymxiong/rsi-data-visual`。通过 GitHub 接口核对，新仓库为公开仓库，默认分支标为 `master`，目录读取返回 `This repository is empty.`。后续需要重新检查仓库更新。[指定仓库](https://github.com/ymxiong/rsi-data-visual)

用户同时提供了 Horsecoder 项目链接。当前网页工具无法访问该链接，代码内容、访问权限及其与 GitHub 仓库的对应关系待核实。[补充项目入口](http://git.horsecoder.com/horsecoder-user-product/com-horsecoder-platform-mall-umi-chat)

### 截图中的推送失败

截图显示，向 `ymxiong/rsi-data-visual` 推送时触发 GitHub Push Protection。被检测的类型为 npm Access Token，位置为提交 `306227f…` 的 `.npmrc` 第 4 行。这是截图提供的诊断信息，令牌有效性和该仓库本地历史尚待仓库维护者检查。

仓库维护者需要从所有包含该令牌的待推送提交中清理凭据，再重新推送。给当前文件新增删除提交或添加忽略规则后，历史提交仍需单独处理。[GitHub 处理说明](https://docs.github.com/en/code-security/how-tos/secure-your-secrets/work-with-leak-prevention/push-protection-on-the-command-line)

若确认为真实凭据，应由令牌所有者撤销旧令牌，后续需要认证时使用环境变量注入。npm 官方支持在 `.npmrc` 中使用 `${NPM_TOKEN}` 占位符。[撤销令牌](https://docs.npmjs.com/revoking-access-tokens/) [环境变量配置](https://docs.npmjs.com/using-private-packages-in-a-ci-cd-workflow/)

后续需确认完整应用、Agent 与 Dr.Spider 接口的实际所在仓库或分支。Dr.Spider 数据集分析可先依照官方数据独立推进。

## Agent 开发要求的暂定理解

| 要求 | 需要进一步弄清的内容 |
| --- | --- |
| 启动指定项目 | 正确仓库与分支、环境依赖、模型配置及可运行示例 |
| 单数据表 Agent，5 分 | Agent 如何获取某张表的信息、接收请求、使用工具并返回结果 |
| Agent 与 Agent 组织后生成 SQL，5 分 | 多个 Agent 的职责、协作协议、组织方式，以及 SQL 生成和验证流程 |

“单数据表 Agent”暂按围绕一张表工作的 Agent 理解。是否要求每张表各配置一个 Agent、是否需要跨表协作，以及最终是否执行 SQL，均待项目代码和老师口径明确。这里的描述用于澄清任务，具体架构后续结合代码讨论。

## 后续需要确认的事项

1. rsi-data 的可视化核心、rsi-data-visual 与 Horsecoder 应用之间的关系，以及完整 Agent 代码入口。
2. Dr.Spider 是否还需限定具体子集，以及“至少五种问题”的分类口径。
3. 指定或允许的基线模型、调用方式、评测指标和资源范围。
4. 任务2中“任选其一”的适用范围，两项 5 分的选择与组合方式。
5. “本周”“下周”“第4周”对应的具体截止日期，以及实际提交形式。

这些事项记录为后续确认点，当前通过官方数据集推进基础概念与样本理解。

## 后续指导方式

采用小步骤推进。每一步先解释概念，结合一个小例子检查理解，再安排相应操作，最后由用户复述并核对结果。知识点随任务引入，学习路线见同目录文件。后续从关系表、自然语言问题与 SQL 的对应关系开始，再逐步进入 Dr.Spider 和实验评测。
