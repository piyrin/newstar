> 历史协议副本：下文记录早期配置，不能作为当前 F 的执行配置或成绩。当前 F 协议与在途验证见 [VARIANT_F.md](VARIANT_F.md)；实际配置以各新运行目录的 protocol.json 为准。当前是单个完整 CourseDock 用例、100/166 各三个 seed、32k/40k 分组、三个控制工具、on-call 全候选说明曝光，非下文旧任务族或全文曝光配置。

# 多 Skill 自主编排实验

本模块替代此前固定八角色的目录匹配试验。最新完整任务族协议见 [PROGRESSIVE_PROTOCOL.md](PROGRESSIVE_PROTOCOL.md)。

**当前入口为`progressive.py`**：三套发布材料、活动筹备、志愿者招募、竞赛待办共六例，各两次，只有本档12/12才晋级。全部候选集合同时暴露（全文或原始说明模式分列），模型自主选择与组合，选中Skill执行其完整原文，真实文档和附件使用明确引用。审阅与提交两个控制工具单独计数。推荐缓存配置将动态引用枚举放在末尾控制工具中，后端精确校验不变。

**用户最新要求：只用本地模型，禁止付费API。** 当前默认backend=local；本地协议见[LOCAL_PROTOCOL.md](LOCAL_PROTOCOL.md)。本地on-call配置会同时暴露所有原始名称/说明，选中再载入全文；与历史云端全文同时曝光成绩分列。

```powershell
python experiments/skill_boundary/progressive.py --prefix unique-local-suite --backend local --local-context 32768 --local-thinking planner-worker --local-sampling qwen-recommended --exposure on-call --suite broad --variant grounded --schema-ids controls-only --critical-first --fail-fast --sizes 10 15 20 30 40 60 80 100 120 140 163
python experiments/skill_boundary/audit_progressive.py tmp/skill-boundary-v2/progressive/unique-local-suite
```

以下`incremental.py`与`runner.py`说明保留用于复现历史，不能代替最新完整任务族或门槛。

最新E配置先跑活动/竞赛，首个失败即停止该档并保留未执行数量；只有完整12/12才能晋级。规划与Skill执行启用本地思考，JSON取证/终验保持非思考；使用官方通用模式采样推荐而非旧0.2/0采样。错误反馈指出具体CSV引用/行列或场次时长/窗口，引用不可变，修订需要新ID。配置与旧C组9/12及D生成超限分列，禁止把部分完成当作通过档。

**历史发布任务族入口**：`incremental.py`，规则见 [严格逐级扩容协议](INCREMENTAL_PROTOCOL.md)。从5开始，仅本级三个资料变体各两次、6/6全部通过才扩大。它使用原始文本Skill输出与最终版本验收，遇到失败级停止。旧`runner.py benchmark`的各规模并行试验及7/8门槛只保留用于复现历史结果，不能冒充新要求。

```powershell
python experiments/skill_boundary/incremental.py --prefix unique-gradual-run
```

## 实现

1. 从固定版本的真实Skill原文筛选支持本地文本、材料分析与文档交付的候选。
2. 逐项运行最小功能用例；独立验收请求检查原始能力、输入和实际交付，人工复核排除不充分的测试。
3. 每项通过能力注册为独立原生function tool；输入为子任务及上游产物ID。
4. 模型只接收自然语言业务需求和事实，自行选择工具、参数、顺序及依赖。
5. 工具执行完整Skill方法，实际保存产物；后续调用读取被引用的实际产物。
6. 从调用关系生成DAG。以独立验收加确定性检查评估实际交付，失败保留，不用最终答复补齐文档。

原生工具调用是运行器自己的接口；这些来源Skill没有安装到Codex全局技能目录。库范围限定为原文支持且实测过的本地能力，不宣称验证了这些Skill的所有模式或外部服务。

## 文件

- `runner.py`：筛选、单项验证、工具执行器、自主编排与固定任务集。
- `progressive.py`：当前完整任务族严格逐级驱动，真实产物、可见审阅/修订、独立终验、12/12晋级。
- `reference_store.py`：文档与附件的精确引用及原子登记。
- `business_evidence.py`：逐字业务证据提取及活动人数/时间/费用的Python检查。
- `audit_progressive.py`：离线核验源哈希、原文暴露、真实上下游、实体、DAG与晋级。
- `incremental.py`：历史发布任务族驱动器，原始正文交付、最终版本验收、6/6晋级。
- `summarize.py`：只读汇总实际记录，无网络调用。
- `resume_guard.py`：保留原结果，重放完全相同的已保存模型响应，从执行器误拦短CSV的位置继续，不重抽此前模型选择。
- `test_checks.py`：CSV、命令等验收器回归测试。
- `test_executor.py`：离线测试替身验证依赖传递和非法引用拦截，不计入模型实验结果。

依赖标准Python库，复用项目已有DeepSeek配置，不打印密钥。真实调用会产生费用。

```powershell
# 单项验证有缓存；recover只续跑此前因余额不足中断的项目
python experiments/skill_boundary/runner.py qualify
python experiments/skill_boundary/runner.py recover

# 0表示当前全部通过条目；不同实验必须使用新prefix
python experiments/skill_boundary/runner.py benchmark --prefix new-run --sizes 20 60 100 128 0 --trials 2
python experiments/skill_boundary/summarize.py new-run
python -m unittest discover -s experiments/skill_boundary -p "test_*.py"
```

本轮实测摘要使用：`python experiments/skill_boundary/summarize.py native-v2 --guard-prefix native-v2-guard`。原始40次与8次执行器纠错续跑分列，续跑不是独立新增试次。当前代码已移除错误的80字最短产物限制，并可将CSV工具返回的纯CSV文本单独落盘；冻结快照保留实验当时的版本，不回写旧证据。

`files`表示额外导出的CSV/JSON/HTML，不包含始终保存的主Markdown文档。当前代码另返回`document_path`明确主文档位置；历史原始证据不能因`files=[]`就判断没有落盘。这是自动验收中需要复核的误判来源之一。

证据保存于 `D:/code/newstar/tmp/skill-boundary-v2/`，包括来源清单、资格用例与产物、人工排除理由、冻结代码/协议/工具库，以及逐轮请求、响应、实际文档、DAG和验收。

## 计数与限制

N是通过本地功能测试、且实际向模型暴露的工具数量；K是当轮实际使用的不同Skill数。调用次数、DAG节点数与最长依赖链另报，不混用。

旧`runner.py`的原生工具描述+调用时完整原文加载为默认；`--full`是其全文同时曝光对照。最新`progressive.py`始终全文同时曝光。不得将不同模式结果混为一个上限。

旧`runner.py`每规模四类任务各两次，7/8为历史门槛；最新完整任务族为六例各两次、12/12才晋级。若全库仍通过，只能确认可达规模，不能把库大小冒充模型能力上限。若小库也有失败，要定位原因，不能把偶发失败自动归因为Skill数量。
