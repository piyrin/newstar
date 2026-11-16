# 第三轮 · Dr.Spider 与 Agent

2026 年 11 月 16 日整理。当前阶段为明确要求与安排后续学习。数据集分析、基线运行和 Agent 实现均待后续开始。

[返回项目导航](../README.md) · [后续知识准备路线](学习路线.md)

## 收到的任务要求

下列通知中的仓库地址已按用户最新更正更新为 `ymxiong/rsi-data-visual`。

> 任务1（必做，满分5分）
>
> 论文同学分析至少一个数据集，学习书写第一个实验表，基线跑起来，分门别类理清数据集里的问题，至少5种问题，具体分析哪个数据集由熊博士安排。熟悉 https://github.com/ymxiong/rsi-data-visual ，下一步需要在其中验证Agent。
>
> 任务2（本周选做，第4周必做，本周做拿满分，下周做减半。任选其一，如果本周有同学做了，下周则删去）
>
> 启动 https://github.com/ymxiong/rsi-data-visual ，实现一个单数据表Agent（5分），实现Agent与Agent组织后生成SQL（5分）。

用户已明确需要弄清楚的数据集为 **Dr.Spider**，希望后续接受分步指导，并在过程中补齐缺漏知识。本次授权范围为整理文件夹、查阅任务背景、明确要求与准备教学路线。

## 必做任务的交付理解

| 要求 | 后续需要形成的结果 | 当前状态 |
| --- | --- | --- |
| 分析至少一个数据集 | 讲清 Dr.Spider 的任务、来源、组成、输入输出和适用场景 | 待学习与分析 |
| 基线跑起来 | 一套可复现的模型或系统配置、实际预测与评测结果 | 待确定基线并运行 |
| 学习书写第一个实验表 | 清晰呈现实验设置、样本量、指标和实际结果 | 待学习并生成真实结果 |
| 至少五种问题 | 分类定义、真实样例、表现与原因分析 | 分类口径待明确 |
| 熟悉 rsi-data-visual | 理解项目入口、数据与 Agent 接口 | 当前 GitHub 仓库为空，另有待核实入口 |

这里将交付物展开为便于后续学习的检查项，具体提交格式、基线选择和评测要求仍需结合熊博士安排。

## Dr.Spider 的定位

Dr.Spider 是基于 Spider 开发集构建的 Text-to-SQL 鲁棒性评测基准，相关论文发表于 ICLR 2023。Text-to-SQL 以自然语言问题和数据库信息为输入，目标是生成 SQL。Dr.Spider 通过有针对性的扰动，考察模型在输入或任务发生变化时的表现。[论文](https://arxiv.org/abs/2301.08881)

官方仓库说明包含 17 组扰动测试，其中数据库相关 3 组、自然语言问题相关 9 组、SQL 相关 5 组。每组提供扰动前后配对材料。后续需要结合每类定义和真实样例判断相应变化对问题、SQL 与数据库的影响。[官方数据说明](https://github.com/awslabs/diagnostic-robustness-text-to-sql/blob/main/README.md)

后续分析可以从官方分类入手理解模型困难，再根据实际错误形成问题分析。作业中“至少五种问题”具体指扰动类型、模型失败类型，还是数据本身的质量问题，需要向熊博士核对。当前尚未选定五类或作出样本分析结论。

## rsi-data-visual 当前可核实状态

2026 年 11 月 16 日用户将项目入口更正为 `ymxiong/rsi-data-visual`。通过 GitHub 接口核对，新仓库为公开仓库，默认分支标为 `master`，目录读取返回 `This repository is empty.`。后续需要重新检查仓库更新。[指定仓库](https://github.com/ymxiong/rsi-data-visual)

用户同时提供了 Horsecoder 项目链接。当前网页工具无法访问该链接，代码内容、访问权限及其与 GitHub 仓库的对应关系待核实。[补充项目入口](http://git.horsecoder.com/horsecoder-user-product/com-horsecoder-platform-mall-umi-chat)

### 截图中的推送失败

截图显示，向 `ymxiong/rsi-data-visual` 推送时触发 GitHub Push Protection。被检测的类型为 npm Access Token，位置为提交 `306227f…` 的 `.npmrc` 第 4 行。这是截图提供的诊断信息，令牌有效性和该仓库本地历史尚待仓库维护者检查。

仓库维护者需要从所有包含该令牌的待推送提交中清理凭据，再重新推送。给当前文件新增删除提交或添加忽略规则后，历史提交仍需单独处理。[GitHub 处理说明](https://docs.github.com/en/code-security/how-tos/secure-your-secrets/work-with-leak-prevention/push-protection-on-the-command-line)

若确认为真实凭据，应由令牌所有者撤销旧令牌，后续需要认证时使用环境变量注入。npm 官方支持在 `.npmrc` 中使用 `${NPM_TOKEN}` 占位符。[撤销令牌](https://docs.npmjs.com/revoking-access-tokens/) [环境变量配置](https://docs.npmjs.com/using-private-packages-in-a-ci-cd-workflow/)

rsi-data-visual 的框架、依赖、Agent 架构、启动命令及 Dr.Spider 接口待获取代码后核实。

## Agent 开发要求的暂定理解

| 要求 | 需要进一步弄清的内容 |
| --- | --- |
| 启动 rsi-data-visual | 正确入口、环境依赖、模型配置及可运行示例 |
| 单数据表 Agent，5 分 | Agent 如何获取某张表的信息、接收请求、使用工具并返回结果 |
| Agent 与 Agent 组织后生成 SQL，5 分 | 多个 Agent 的职责、协作协议、组织方式，以及 SQL 生成和验证流程 |

“单数据表 Agent”暂按围绕一张表工作的 Agent 理解。是否要求每张表各配置一个 Agent、是否需要跨表协作，以及最终是否执行 SQL，均待项目代码和老师口径明确。这里的描述用于澄清任务，具体架构后续结合代码讨论。

## 后续需要确认的事项

1. rsi-data-visual 的可运行代码入口、分支，以及 Horsecoder 链接与该仓库的对应关系。
2. Dr.Spider 是否还需限定具体子集，以及“至少五种问题”的分类口径。
3. 指定或允许的基线模型、调用方式、评测指标和资源范围。
4. 任务2中“任选其一”的适用范围，两项 5 分的选择与组合方式。
5. “本周”“下周”“第4周”对应的具体截止日期，以及实际提交形式。

这些事项记录为后续确认点，当前先完成对任务结构和基础概念的理解。

## 后续指导方式

采用小步骤推进。每一步先解释概念，结合一个小例子检查理解，再安排相应操作，最后由用户复述并核对结果。知识点随任务引入，学习路线见同目录文件。后续从关系表、自然语言问题与 SQL 的对应关系开始，再逐步进入 Dr.Spider 和实验评测。
