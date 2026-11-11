> 历史协议副本：下文记录早期配置，不能作为当前 F 的执行配置或成绩。当前 F 协议与在途验证见 [VARIANT_F.md](VARIANT_F.md)；实际配置以各新运行目录的 protocol.json 为准。当前是单个完整 CourseDock 用例、100/166 各三个 seed、32k/40k 分组、三个控制工具、on-call 全候选说明曝光，非下文旧任务族或全文曝光配置。

# 本地模型零API费用配置

用户明确要求允许本地模型、禁止付费API。自该指令起，不再调用DeepSeek；历史分数保留，余额中断不是Skill数量上限。

当前硬件实查：RTX5060 Laptop GPU，8151MiB；内存31.8GiB。已有Ollama0.33.1和qwen3.5:9b，模型digest6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7，GGUF Q4_K_M，约9.7B参数；本地模型元数据标称context262144。未下载模型。服务只监听127.0.0.1:11434，OLLAMA_NO_CLOUD=1；启用Flash Attention、q8_0 KV缓存、单并发。

本地运行器仅接受loopback HTTP地址，禁用外部代理，无凭证、无远端回退，拒绝cloud模型标签。使用Ollama原生/api/chat；工具参数对象/工具结果tool_name与原生格式互转，输出仍是实际模型function calling。temperature0.2，presence_penalty0，think=false，运行context32768。发现服务日志截断提示即否决结果，不把截断后偶然成功当有效证据。

本地曝光配置为on-call：所有N项原始名称、说明与接口同时暴露；不预先检索缩小候选；选中Skill执行时加载完整原文和实际上游。与云端全文同时曝光配置分列，不混算上限。Skill候选N、实际种类K、业务DAG节点及最长链分别报告，两个审阅/提交控制工具不计Skill。

先运行一次5候选发布材料工程预检，不能将单次预检冒称稳定档。工程预检通过后，正式本地新系列从覆盖完整业务的10候选起，六例各两次12/12。各档全过才晋级，试次错误保留。沿用实际CSV、精确命令、逐字数值证据、事实一致性、至少两个Skill及实际上游依赖、可见审阅修订与隔离终验；同一试次最多16轮规划，不隐式重抽。无效提交的拒绝会作为可见工具反馈返回，仍消耗原轮数，不能跳过审阅或让错误结果通过。

推荐本地命令：

```powershell
python experiments/skill_boundary/progressive.py --prefix local-unique --backend local --local-context 32768 --exposure on-call --variant grounded --schema-ids controls-only --suite broad --sizes 10 15 20 30 40 60 80 100 120 140 163
```

本地仍受实际推理速度、内存、上下文和模型能力限制；没有新的实测前，不声称已经通过100或163。163只是现有来源库规模。官方接口参考：https://docs.ollama.com/api/chat 与 https://docs.ollama.com/capabilities/tool-calling 。

## 本地B修正配置

local-qwen-a完成8/12，其中6次发布材料通过、活动两次未过；其余4次因已确认的取证器问题而停止。旧文件、失败和中止均保留，不能称10档通过，也不能把此结果当Skill数量上限。

local-qwen-b仍从10起，原六例各两次、16轮规划预算与全部业务约束不变，12次全部重新运行，不混用A的成功样本。修正如下：

- 取证器只选实际原文行号，程序读取逐字原文；本地JSON Schema只允许现有行号。仍按原始facts检查明确分配人数、容量、时长/窗口/不重叠和费用。支付状态待选项不是已发生付款，明确的实际支出声明仍拦截。
- 所有最终CSV的非空行须与表头列数一致且语法可解析，不同结构表不得混进一个CSV。给规划器原要求对应的失败解释，不给本用例排期或预算答案。
- 工具结果只发送一份完整正文，去掉值完全相同的artifact兼容别名；磁盘记录保留原始兼容字段，原文、上下游全文均不裁剪。
- Skill拒绝/空交付明确作为unsupported反馈，无虚构文件。规划器可在原预算内选择其他Skill；不覆盖已失败调用，尝试ID与成功产物节点ID分开，单列尝试数及失败数。只有真实成功产物参与原组合/依赖标准。

这些是独立版本，不回写A的判定。新代码49项离线回归通过；本地行号提取另在原有不可变文件上校准，该校准不算新业务试次或规模成绩。

## 本地C控制循环

B首个试次只调用一种Skill后用普通文本结束，未审阅、未提交，失败；B共完成1/12、0通过，随后因控制循环缺陷中止，不算上限。C同一完整六例、工具顺序、模型、32k上下文、16轮及12/12门槛，从10全部重跑。

C每轮提供从真实已完成节点推导的状态：成功Skill种类、真实依赖边、可用引用、已通过审阅的引用集合及剩余轮数。该状态不决定使用哪个Skill、不指定DAG、不提供业务答案，原始用户需求与全部候选仍完整保留。状态逐轮落盘。

提前普通文本结束、混用控制/业务调用、非法参数或引用会得到可见执行器拒绝反馈，原回复保留、该轮计入原预算；只有实际成功产物参与业务组合和节点计数。协议拒绝、unsupported尝试均另报，不冒充成功。最终仍需原要求硬检查、可见审阅及隔离终验。49项回归覆盖提前结束、非法引用、混合控制调用、未审先提交、unsupported改选，均不会生成虚构成功产物。

## 本地D思考与精确反馈

C全12次结束为9/12，活动两次及竞赛一次未过，未启动15。68个实际节点、83份附件离线核验通过，仅证明证据一致，不代表业务全过。活动时长/时间窗口不满足，坏CSV旧ID反复保留，修订循环耗尽预算。旧数据保留，不据此声称10是模型硬上限。

D保留同一六例、同一库顺序、同一16轮规划及12/12完整晋级条件。配置变化单列：规划器和Skill工人think=true，额外4096个生成token预算用于本地思考，JSON验收/取证think=false；仍为Qwen3.5:9b、32k、q8 KV、单并发、无付费API。思考内容不当业务产物，不补写最终答案；原始native响应及使用量保留。

明确文件不可变契约：修改总是生成新ID，旧CSV不会随说明文档改变；反馈给出具体CSV引用/行号/列数差异和实际场次分钟数、窗口差异等由原始输入计算的约束，不提供预写交付或固定DAG。实际付款判定使用文字/表格实际金额列的证据，空白实际列或支付状态待选项不代表付款，明确“实际发生”记录仍会拦截。新证据版本line_ids_v2；旧判定不回写。

先跑活动与竞赛，再跑其余原用例，仍为六例各两次共12。fail-fast只减少失败档未执行部分：一旦有失败该档立刻停止且不得晋级；报告已完成/计划数，未执行不算成功，也不把部分结果冒称完整稳定率。只有完整12/12时继续15、20等档。54项离线回归含失败即停/不晋级、精确行诊断及思考模式分离。

```powershell
python experiments/skill_boundary/progressive.py --prefix local-new --backend local --local-context 32768 --local-thinking planner-worker --exposure on-call --variant grounded --schema-ids controls-only --critical-first --fail-fast --suite broad --sizes 10 15 20 30 40 60 80 100 120 140 163
```

## 本地E推荐采样对照

D首个活动试次在expense-accounting工人的11096生成token上限内只有思考、无正文，失败即停；只执行1/12、0通过，其余未执行，不是数量上限。D保留的采样为temperature0.2、presence_penalty0；Qwen官方模型卡对通用思考建议temperature1.0、top_p0.95、top_k20、min_p0、presence_penalty1.5、repetition_penalty1.0，并说明presence penalty可减少无休止重复。原结果不回写。

E从10重新运行同一批完整12次，其他D约束保持；按官方通用模式采样：思考用1.0/0.95，非思考用0.7/0.8（temperature/top_p），两者presence1.5、top_k20、min_p0、repeat_penalty1。仍仅本地，32k是实际硬件配置，不声称完全复刻模型卡的长上下文环境。思考/采样配置单列，不与旧C/D混算。错误执行尝试明确计execution_error，不隐式重试，不当成功节点。56项离线回归通过。

官方来源：https://huggingface.co/Qwen/Qwen3.5-9B#best-practices

## 受约束规划协议对照

新增可选--local-planner structured，默认native不变。structured模式所有N候选名称、原说明及接口同时完整可见，规划器使用本地JSON Schema生成calls数组；Schema由实际工具自动生成，不预设选项子集、业务答案或DAG。程序只解码模型实际生成的名称和参数，参数错误仍会被拒绝。原始native响应、plan和实际调用一并存档审计，不将结构化解码称为Ollama原生function calling。

此模式规划器非思考，工人保持所选thinking配置；其他原始事实、实体/语义验收、16轮预算、12/12标准不变。不同协议结果单列，不能混算。local-qwen-schema-a从10重新测试六例各两次。

schema-a在第三工人未完成时中止调整资源，不能算完整失败档。schema-core-a关闭全部思考，显式--local-gpu-layers 24、32k，--allow-small-baseline允许从5候选建立基线；六类原任务及每类两次不变，仍12/12才晋级。未通过的基线不是数量硬上限。该组完整记录12次，不在首个失败处跳过其余预定试次。

后续core-a中止调整产物上下文架构，实际并未完成12次，按interruption.json记录，不沿用上句计划为已完成结果。

## 当前修正版单例探索

local-single-receipts-native-b固定CourseDock案例、每档一次探索，明确与完整六类12/12分开。原生调用、legacy采样、off、GPU24层、32k、receipts。新增--strict-feedback-csv逐一检查所有最终反馈CSV及文档中的嵌套/可复制片段，不能用一份正确空模板掩盖另一份填有虚构记录的CSV。原A30/100误判已否决，120只保留独立观察，原自动晋级链作废。72项离线回归通过。

```powershell
python experiments/skill_boundary/probe_scale.py --prefix 新修正版系列 --local-planner native --local-sampling legacy --planner-artifacts receipts --strict-feedback-csv --sizes 20 30 40 60 80 100 120 140 163
```

```powershell
python experiments/skill_boundary/progressive.py --prefix local-new-core --backend local --local-context 32768 --local-thinking off --local-sampling qwen-recommended --local-planner structured --local-gpu-layers 24 --exposure on-call --variant grounded --schema-ids controls-only --critical-first --suite broad --allow-small-baseline --sizes 5 10 15 20 30 40 60 80 100 120 140 163
```

```powershell
python experiments/skill_boundary/progressive.py --prefix local-new --backend local --local-context 32768 --local-thinking planner-worker --local-sampling qwen-recommended --exposure on-call --variant grounded --schema-ids controls-only --critical-first --fail-fast --suite broad --sizes 10 15 20 30 40 60 80 100 120 140 163
```
