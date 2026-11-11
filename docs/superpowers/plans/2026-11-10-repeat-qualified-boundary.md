# 扩容正确性、稳定性与可复现性前置验证

> Inline execution under existing continuous authorization. No paid APIs, no source/output rewriting, no commits, no delegation.

**Goal:** 确保此次所扩充的正确性稳定性可复现性前提下探索边界。
**Scope:** 169是当前原文去重候选池，其中163为历史来源；本次新增6项必须先重复验证，不能将一次smoke当稳定资格。主业务原CourseDock和所有硬要求不降低。
**Architecture:** 冻结新增6项原文、原业务小用例、脚本、模型/接口配置。每项新seed101/102/103三次实际执行，再以seed101原输入进行一次复现。全部worker/隔离judge请求/响应和失败保留。预先判据为原三条标准、原source核心与硬检查；直接内容复核所有24项，独立Python检查代码/数学。复现报告功能一致性及字节是否相同，两者分开。不保证有限样本下未来绝对稳定。

- [x] 核对新目标与中断现场；B100三次完成原自动2/3，直接复核两个自动成功均否决，实际0/3；140r1保留为中断，不静默重启。
- [x] 复用qualify/LocalAPI搭建最小冻结重复队列；先验证候选隔离、重复分母、同seed同输入与断点保护，不引入预写业务答案。
- [x] 执行6项x4次共24次，不隐式重试；同seed复现不是第4个独立随机样本。逐项直接复核/代码检查，并列原自动判定。
- [x] 只将通过前置门槛者纳入“重复验证池”，原169候选池和所有不稳定结果保留。若无新增可稳定资格，先修正实际执行缺陷，不以注册量宣称完成。
- [ ] 固定输入、候选顺序、配对seed，在重复验证池上建立低档正确基线、逐级扩容及边界附近重复；上下文对照为独立新组。旧B不拼接新成功率。
- [ ] 导出可复现实验包/命令、逐项哈希、成功与失败前后证据、原因与改进、条件性边界及局限；完成审计后才宣布目标达成。

## Ledger

- 主模型唯一qwen3.5:9b、Ollama0.33.1；32k、GPU24、legacy0.2非思考、truncate=false/shift=false。新增来源来源hash与原163前缀保留。计划来源资格容器使用typed-worker，与E原untyped分组，不混为同配置稳定率。
- 新主任务审查发现原窄规则未覆盖的UI推断和MIT限制错误。本地裁判错误仍是研究问题；不得仅凭自动true宣布正确。

- 冻结重复队列已实现，6个有意义回归先红后绿，整套102测试通过；未完成试次拒绝静默重启，失败计分母，同seed复现单列非独立抽样。实际24次已开始，唯一live handle11590。模型manifestdigest已重新核实。
- 现有两个完成试次逐文复核均正确，原自动一真一假；静态代码解释的裁判把1+3=4判false又在错误文字中承认正确，追加逐标准证据纠正，原判保留。README准确保留未知许可和无配置变量。任何来源尚未结束全部四次，不计重复资格。

- 24/24资格结束且逐项直接复核。原自动11/24，实际内容16/24；47真实native响应，46正常、1长度失败。三个独立seed成功数依次code3/3、docs3/3、async0/3、requirements3/3、prompt1/3、ADR2/3；六个同seed复现请求/正文哈希均一致，但失败复现不算正确。仅code/docs/requirements通过4/4门槛，工作候选池166，原169库保留。
- 主任务新C组预先冻结：原请求、六标准、原facts键值全部不变，额外将未提供的端口默认/界面/服务URL/导出入口/安装命令/Python最低版本显式列未知，并加入OSI官方MIT许可参考。其目的为事实完整性改进，不提供业务正文或预设DAG；C输入与旧B不同，成绩分组，不能将改善单独归因于数量。后续C内部仅改变候选N和配对seed。
- 准备启动C32四档40/100/140/166各3，固定顺序/seed=repeat/32k/16轮/严格CSV+原事实反馈/独立终验。所有自动成功仍需逐文复核；前置源资格不能替代整体编排稳定性。

- 新增前置复现包已交付至deliverables/skill-extension-repro-20261110.zip，541770字节，SHA256 b856c47d794ccb83444b5e707e6bd3d761fa8169d70c0243d9fbab18178a840c。另一路径校验372文件哈希、历史audit和CLI导入通过；不把打包核验称新模型试次。主任务边界复现包仍待实际结果，不以此前置包宣告整个目标完成。
- 当前唯一推理任务为C32，live handle14825，40/100/140/166各3。11590已exit0（24/24），84499已因用户此前暂停exit1。当前40r1在途，不重启。下一轮继续轮询14825并直接复核自动成功；根据实测加密边界和单列40k完整任务对照。

- C40r1已结束原自动通过，实际K3/节点4/链4；逐文复核最终DOC004出现“无外部数据泄露风险”，原facts本地留存不能支持零风险保证，追加内容否决。并未新增要求用户去安全扫描，只需不编造该保证。该失败是语义而非数量资源失败，不能冒称40上限；仍完成其余预定试次，观察当前全局编排稳定性。

- 后续需重点处理整体语义裁判可靠性：当前C40r1六项自动全true但漏检零泄露风险保证。不能据其自动分数报稳定率或数量上限。若C后续继续出现此类漏检，应在独立新版本尝试事实逐项证据/本地思考型审阅（保留原16轮与业务需求、所有候选曝光、未改写正文），并用已知真假样例校准后再开新组；不能热改当前C或把父代理离线否决混称模型在线自纠错。

- C40r2实际五个CSV附件均经独立csv解析，共8处4列/5空字段不匹配。最终manifest只列DOC，附件通过DOC.files交付；复核遍历实际附件，而非只找显式FILE引用。源检查legacy跳过全空字段记录；后续严格profile区分空物理行/字段记录，保留旧兼容默认。

- C40阶段三次结束原自动2/3、直接正确性0/3；r3 K5/8节点/最长链8，耗尽原16轮。因已确证验收缺口，在该阶段结束后中断14825（exit1），新开始100r1留为未完成；stop-checkpoint.json明确原计划12、完成3，未测试高档不冒充结果。目标保持active，未暂停或缩小主任务。
- 新semantic_review.py完整保留原文并编号（包含经DOC.files交付但未显式列FILE的实际附件），六个固定证据槽位引用实际行ID/facts键；host只核对引用，不改正文或代写业务答案。可选fact-evidence profile使用本地隔离thinking=all/qwen-recommended审阅和严格全CSV字段记录列数，legacy默认兼容，当前/旧数据可继续审计。
- 关键回归（伪造/缺失证据、附件读取、空物理行vs错误列数、传输失败不算正确拒绝、校准不完整/代码不一致禁止开新组）先红后绿；全111离线测试通过。C旧组完整已结束部分17节点/10附件/54真实正常响应审计通过，物理审计不恢复否决分数。
- 5个已知样例已冻结（1正4反），gold不进入模型payload；这是定向诊断，不是独立泛化集或主业务试次。新calibrate_semantic_review.py已启动；必须查看真实匹配/错误和逐标准证据，全部通过且实现哈希一致时boundary_scan才允许fact-evidence新组。当前唯一本地推理为该校准，主扩容暂不并行。

- 校准A结束2/5（1正正确、3语义误收、1CSV规则正确拒绝）；实际thinking字段非空仍不足以正确判断，原记录不改。扩展规则新增UI/URL、MIT限制、零风险三类，并修复未知限定语位于同句后半的边界；对应回归红→绿，全115项通过。
- 校准B结束5/5，由4个程序拒绝+1个实际模型接受组成，不能宣称5/5模型语义准确率。实际新请求与A正例逐字相同，判定相同，native created_at不同。B环境重新核实Ollama0.33.1/9B模型digest不变；validate_calibration实查B可用、A不可用，关键5个实现文件hash锁定。
- 当前唯一推理：D32前缀boundary-repeatqualified-166-d32，live handle77050；10/40/100/140/166各3，共15计划。C14825已exit1，校准A10181/B53920均exit0，不再作为活进程轮询。来源166不变；新增3的重复资格不能替代整体编排稳定率。
- 后续：轮询77050，逐文复核所有自动成功并检查profile实际接口/行证据/严格CSV反馈；建立真实正确基线后在退化区间加密，再做相同主任务与目录/seed的40k完整业务对照。若当前组无稳定基线，应定位具体执行/裁判原因而非报N上限。

- D真实在途控制已观察到严格CSV列数拒绝；其中一次组合条件已满足仍因附件列数错被拒绝，验证新版门槛实际在线生效，不只是离线测试。该观察不是试次通过，整体结果仍待summary/逐文复核。尚无当前profile的稳定上限。

- D10r1最终失败：review003输入7655 token，think=true生成6296 token仍无finalcontent，done_reason=length；未触及32k上下文，不能据此报N上限。直接检查candidate另见DOC001:L24以加粗标签声称默认端口4177，DOC002:L32又说默认未知；整体保持失败。已停止owned77050（exit1），仅完成1/15、0通过，r2部分保留，高档未运行；series/status与stop-checkpoint已标明。
- 新版改动：审阅器thinking=off，仍Qwen推荐非思考采样（0.7/presence1.5），规划/工人不变；同一窄默认端口规则支持Markdown加粗/代码标记/表格。回归先红后绿，全部115项通过。审计读取旧protocol缺失字段时仍按all解释，不能把旧D误当新版。校准锁增加release_fact_issues.py，合计6实现文件。
- 既有5个校准原文不变，追加真实D10失败候选为第6已知反例；预先gold与原文hash冻结于semantic-calibration-inputs-b，不给模型gold。校准C（非思考）启动；仍为定向已知例而非独立泛化集。后续按单档三次＋直接复核推进，避免基线不正确仍跑高档。

- 校准C已结束6/6：5规则拒绝＋1本地正例接受，正例736生成token/48.7s/stop，think=false，输入6865；不能称模型6/6泛化准确率。代码哈希门槛实查通过。新E32仅10档3次已启动，owned27961；全部旧D/C/校准已停止/结束。接下来先完整复核E10再扩展同版本高档。

- E10r1已失败：12节点/K5/最长链7，6次显式正文读取、2次未过审阅，planner15请求33906token超过32768，HTTP400且truncate/shift=false。没有隐藏截断、没有正式提交，不算通过。r2继续真实新请求。该失败定位是修订/读取历史上下文，不是N10硬上限。
- 四个审阅前工人请求和输出在D/E完全相同，但native created_at各不同，保存paired-worker-reproduction.json，证明真实同输入复现；不是独立seed稳定样本。新版E第一审阅确实拒绝原加粗默认端口断言。
- 当前166份原文bytes SHA及166名称/规范化hash唯一性重新验证通过，current-source-integrity.json；该检查仅证明来源完整性，非全部语义资格或整体能力。已准备主复现包一次性生成脚本，要求E全部试次结束后才打包，不把在途快照作为最终结果。

- E10r2自动通过（K4/5节点/链2），但直接最终复核否决：DOC004:L18/L41将web_management_ui:null变成“无Web管理界面”，DOC005重复该断言，同时DOC001又列为未知。父复核在模型verdict结束前已留逐行证据，最终正文hash与该candidate一致；root content-review-20261110.json和effective-status已写，保留rawsummary。当前原自动1/2、实际0/2，r3继续。证据引用格式正确不能保证事实推断成立，不把校准6/6称普遍语义准确率。
- 方法澄清：完成每档并直接复核后继续更大N；目录扩展同时引入更合适能力，成功率并不必然单调，因此不能以N10不全过作为停止高档或“上限10”的依据。本次新增来源3项的4/4资格门槛未降低，主业务各档失败照常计数、不给稳定性假结论。保持E实现/输入/顺序与seed，下一档40，随后根据实际结果逐档扩展。

- E10全部结束：raw2/3、effective0/3。r3 K5/6节点/链2，两处“无需额外隐私协议”无facts支持，逐行父复核否决。完整证据审计23节点/14附件/54真实响应/0重放通过，但不能恢复正确率。旧27961已结束，工具会话不可用但series明确all_boundary_trials_finished。
- 用户再次继续时主机服务已离线；N40原e32-n40三次均local URLError且0模型响应，保留基础设施失败分母。没有沿用旧进程假定live。重启仅loopback/NO_CLOUD/FlashAttn/q8KV/parallel1本地服务，后台launcher28272，日志追加保留；实查版本0.33.1和模型digest一致。新独立e32-n40b组三次启动，唯一推理handle66990。下一步复核40b、按相同版本逐档扩大；原故障组不拼接作N上限。

- E10复现包已生成并验证：795文件、2762910bytes、SHA256633ad4fb15f60d20c8c138930365ba992c9398d7b63228884e37f5a22bfdd0d7；另一路径verify_bundle/rerun_local --verify-only及ZIP内部hash/testzip全部通过，无推理重放冒充新试次。该包仅E10阶段。
- 本地服务修复后发现powershell5/pwsh追加已有日志产生UTF16，40b66990与40c84374均主动exit1/部分保留，series和stopcheckpoint已记，没有结果晋级。最终改PythonPopen直接ab原生字节追加日志，无Shell编码；服务pid25056，raw-log-service.json记录日志起始offset。实际ready=true预检（22/6token）结束exit0且新日志无NUL/UTF8可解码。此次旧服务遗留llama-server38660/30400已精确终止，当前只有43752，显存回落5786MiB。没有改保护代码，因此calibrationC仍有效。
- 新唯一live推理19289：boundary-repeatqualified-166-e32-expanded，40/100/140/166各3，独立12次；当前40r1。后续继续轮询19289，直接复核所有rawpositive，保存有效分数；阶段结果仍无可靠数量上限。勿再轮询旧27961/66990/84374/57194，它们已结束/中断。

- 19289确认live；E32扩容已结束40全部0/3（budget/context33477/budget），100r1context33462失败。前4项offlineaudit通过31节点/24附件/88新模型回复。源/正文/上下游/真实DAG完整，未计语义通过。
- 100r2rawtrue K3/3节点/链2；完整全部最终正文及3CSV读后否决：Skill metadata的WHOISABHISHEKADHIKARI作者被当成项目所有者，在3份终稿沿用。source原文第7/source_repo和第10/author同名，已存root content-review-20261110.json的source_trace/sha/逐行引文与终稿hash。实际100当前0/2，r3在途，保持旧自动分数。
- 已准备tmp/skill-boundary-v2/run-calibration-context40.py，冻结同6案例且仅context40960、同9B/24GPU/off/recommended/seed1；不会改保护代码或当前E模型请求。待19289全部结束才启动，成功后以N100/3次完整新业务作40k对照。后续可单独验证Skill metadata与业务facts的来源隔离提示，不能删原文/填项目负责人/混合版本分数。

- 100r3真实终局rawtrue K2/2节点/链2、1次审阅、0显式读取、1协议拒绝反馈后仍原16轮内提交。完整2文档+2实际CSV直接检查六条通过；parent-content-review实际写在trial根（当时root semantic-review-input已生成），最终同hash断言通过后存content-review-20261110.json effective=true。当前100raw2/3 effective1/3，40effective0/3；largest_verified_single_success_scale=100，largest_all_three=None，不冒称稳定上限。
- 40/100六项完整audit通过36节点/29附件/106真回复/0重放；初始100业务+3控制实际tools103已核实。成功证据包169文件，661450bytes，SHA25675973153c096b64ffd5a2e89fa969a48ded21a1bf6412245ce54df91bc7d9fca；ZIP逐项hash/testzip通过，来源100原文完整。E10重跑环境可用--sizes100（实际命令参数分开写--sizes 100）。该成功仍需新鲜整轮同seed复现，不把已知正例复现混入独立seed稳定率。
- 活跃19289已进入后续140/166；保留现有所有失败分母。下一步跟踪两档、逐文复核rawpositive，随后准备100/seed3的32k实际新试次复现与已预注册40k独立完整业务对照。目标尚未达成，不调用complete。

- E140r1已失败context34837>32768；r2rawtrue K3/3节点/链2，完整3文档+3CSV直接读取后，以3处作者身份污染＋3处未知UI/URL被称不可用否决。parent-content-review所在位置由rglob实际定位且唯一；终稿hash与候选一致后rootcontent-review置effectivefalse。140当前raw1/2 effective0/2，r3在途。八项审计42节点/34附件/125新回复/0重放通过。
- 后续改为更完整复现：N100原三个seed均重新整轮执行，不只选已知成功seed3，旧1/3不改分母，不称新独立抽样。已新增followup-preregistration.json冻结所有当前运行py哈希及原fixture/registrySHA；check-followup-inputs.py实际检查通过。run-e-followups.ps1仅在baseline all_boundary_trials_finished后启动，顺序32k新三次→离线审计→已准备40k六例校准→40k完整N100三次→审计。任何目录存在或校准门槛失败即停止，保留全部记录，不重启。后续需启动该脚本并逐文复核所有rawpositive；当前尚未启动，唯一live19289。

- 140r3rawtrue K2/4节点/链3：先同一projectbrief3节点经visible组合拒绝，再选另一Skill修订，组合是真实满足；但4最终文档完整父检查发现DOC00375/76及DOC004167/168未有facts支持的serve监听/仅本地访问/无外连断言，候选parentreview在review002保存，正式终稿同hash后否决。140最终raw2/3 effective0/3。九项audit通过46节点/37附件/137真回复/0重放。
- 166r1已真实初始正常返回，tools169=166+3，prompt28781，余3987；当前4节点，唯一live19289。保存五档initial-exposure-measurements.json：10/40/100/140/166初始prompt3498/8339/18013/24465/28781。其仅为输入实测，不是业务成功。
- 40k对照在任何followup运行前正式扩为100和166各3（新prefixboundary-repeatqualified-166-e40-expanded），以检验166真实任务而非仅较小100；原prereg不改，新增followup-amendment-include166.json固定原preregSHA/改动理由/时间。PS入口与后续audit路径已同步新prefix及sizes100166；checker新增原prereghash核对，实际再次验证所有代码/原fixtures/registry/原preregSHA通过。尚未启动followups，需待19289 authoritative terminal。

- 166r1rawtrue，K5/5节点/链2；原始5最终文档＋实际CSV全部直接读取后否决：DOC00135/36将未知Web/导出界面断言没有并给出未提供CLI/API交互，FAQ DOC0057/14沿用。rootcontent-review已存4条真实引文、最终hash/effectivefalse；166当前effective0/1，剩2在途，singleverifiedmax仍100。不能称166无法注册/工具API硬上限：实际169工具暴露、原生调用和正式提交都已运行，只是业务语义错。
- 十项完整offlineaudit通过51节点/38附件/149新模型回复/0重放；19289仍live。保护代码与后续冻结hash仍未改变，后续32k全3seed复现＋40k六案例校准＋100/166各3完整业务待baseline全部结束才启动。

- 166r2已失败，K2/2节点/链2，1次read、1次review、1协议调用拒绝后，planner请求33103>32768，HTTP400，不算成功。rootfailure-diagnosis/effective-status已更新，baseline共11/12完成，1660/2，仅seed3在途。最长链计节点（root1），100成功链2=1边，报告已明确，失败节点不得称正确有效步骤。单次100成功实际dag/输入DOC+FILE图已加入报告帮助录屏说明，非预写路线。

- 19289已exit0，E32扩容全部12结束。166r3rawtrue K2/2节点/链2，实际product-design-harness→copy-editing；完整最终103行文档＋CSV文本读取后，pipinstall命令/未知UI→无UI/未知导出→CLIonly三处明确无依据断言否决。最终四档raw0/2/2/2与effective0/1/0/0（各分母3），所有6rawpositive均复核，无pendingpositive，largest_single_verified100、largest3of3None。
- 完整audit通过55节点/42附件/166实际模型回复/0重放，响应166与候选166不可混用。新增来源3项重复audit-finalSHA06b7...再次按registry repeat_audit_sha核实全匹配，各3不同seed＋1同seed资格仍通过，未把另3失败来源纳入池。
- followups已在baseline allfinished＋原handle terminal后启动PS，唯一livehandle6160；控制脚本已打印冻结全部运行py/fixture/registry+原preregSHA通过，当前e32-n100-repro/r1在途；后续串行六例D40校准＋e40-expanded100/166各3及audit。不要轮询已terminal19289，当前目标未完成。
- 新完整32k复现包skill-boundary-e32-full-repro-20261110.zip已生成，4946171bytes，SHA256d661fc9e52456875bc96d04947412efa201e58a2ec4d2ecaf3b2b9c71569cab2，1535files。ZIP内部全hash/testzip；复制tmp/.../full-main-repro-relocation-check后verify_bundle与rerun_local --verify-only均exit0。保留E10和100成功单例旧包不覆盖。当前包只含已结束E32全部12，不含在途后续结果。

- 6160已完成fresh32kN100repro/r1，失败context33430；原r1context33462，节点K4/6/链4→K5/5/链5，不能声称整轨迹逐字复现。实际逐请求核对：planner00requestSHA完全相同c8a033...，raw message only工具随机ID不同，normalized message相同；worker001requestSHA3f168.../正文相同，时间不同，非复制。planner01请求只run绝对路径变（analysis-only双转义路径替换后一致），normalized model message不同。已存reproduction-comparison.json，不能把原始工具ID差异当推理差异，也不能把context后续结果单因归于context，路径为已观察输入扰动。
- 新发现提示后续可做隔离实验：保留实际物理文件和全正文，在模型视图使用稳定逻辑产物路径，消除与业务无关的run目录差异；仅属候选改进，不对当前冻结E代码或在途6160热改，不要求跨硬件位级确定性。当前第一整轮复现仍失败不晋级，原E32正确1001/3不变。下一步继续6160的seed2/3，随后D40校准和100/166各3，逐文复核所有rawpositive。


## E40完整业务与F下一组（2026-11-10追加）

E40的100/166各3次正常结束，唯一串行6160已exit0。68条新模型响应、20个实际产物节点、16个附件经原E物理/来源审计通过；这不是语义正确证明。所有6个原自动正例现已直接阅读全文和实际CSV：N100仅seed3正确（K3、节点3、最长依赖链2节点）；N166三个均错误。有效结果100为1/3，166为0/3；与E32、相同seed复现组分别报告，不拼分母。

N100/seed1的未知Web界面/导出入口被说成无UI/CLI；seed2把Skill作者WHOISABHISHEKADHIKARI当成项目Owner。N166/seed1仍补造UI/导出入口及无专职团队；seed2把本机留存推成“无外部服务依赖”；seed3同时补造pip install coursedock、无Web界面及仅CLI。逐字行证据、完整最终文档hash和实际CSV解析写入各trial的content-review-20261110.json，effective-status-20261110.json单列有效分数。原自动summary/series不改，因此不能把原series中的fully_passed当最终内容正确率。

当前已知是：候选库166可以全部展示并执行动态选择；最大逐文验证的单次成功规模100。没有任何当前主业务规模达到三个seed全部正确，稳定边界尚未确定。166不是已证实的正确上限，100也不是理论上限；语义错误与32k上下文溢出必须分开。

F是独立协议组，保留全部原需求、facts、六标准、源SKILL全文、166候选、候选顺序、16轮和严格验收。仅消除模型可见的实际run目录扰动（包括真实错误反馈），并在源全文后明确Skill作者不是项目Owner、null保持未知。主机不修业务答案、不固定Skill或DAG。两项输入改动一起测试，不能宣称单因素因果。原E仍冻结。

F五项新增回归原E全部失败，F整套120项离线测试通过，涵盖实际控制器消息、跨目录等价视图、真实附件读取/篡改拒绝、完整源与facts、无输出修补。离线替身不计业务成功。先核对预注册全部F源码hash，再启动62447串行F32独立校准→N100/166各三次→审计→F40独立校准→同两档各三次→审计。所有自动正例继续逐文复核。F真实结果尚未完成，目标继续进行。


E40与同seed复现的新独立交付：deliverables/skill-boundary-e40-followup-repro-20261110.zip，3990108字节，SHA256 e244e590fc77446cc83f65a49a43bdac77a45bcb2865d1efd4949fbc3aa095b0。1215清单文件在ZIP内逐项校验，并实际解压至另一目录e40-followup-relocation-check，verify_bundle和rerun_local --verify-only都通过，不产生新模型调用。默认真实重跑为原完整100/166各三次、40960上下文，本地版本/digest预检；旧E32主包原字节保留。历史请求绝对路径完整保留供追溯，不能承诺E跨目录逐字复现。

F32真实校准已6/6标签匹配，其中5个规则拒绝+1个本地模型接受；没有将其称为6次模型正确判断或业务成功。当前62447已进入F32 N100/seed1原完整业务，32k/24GPU、全部原候选与标准，最终正确率尚未产生。


F32首个N100/seed1已完成：原自动true，K3/节点3/最长链3节点，12条全新模型回复。实际来源/完整上游/实际规划回执/读取/审阅反馈传输经F partial audit通过；模型实际收到artifact逻辑路径，原物理文件仍可读、完整原source与facts保留。全文直接复核仍否决：DOC001和DOC002 L18均把“不支持PDF OCR”扩大为“无法直接处理PDF文件或进行光学字符识别”，前半是额外未给定的产品限制。L56搜索接口措辞有歧义，不用于该否决。两个文档逐个匹配实际文件，正文hash相同；第三文档和实际CSV均仅正确表头。F指令改进未消除所有事实漂移。当前仅完成1/3，N100不能报完整阶段0/3或稳定性改善，原自动记录不改；62447继续其余预注册试次。


F32 N100/seed2完整结束，原自动通过且最终全文直接复核通过：实际K3、节点4、最长链4节点；其中一个是被替换的错误草稿，不能把四节点称四个独立正确步骤。初次review指出DOC001 L40默认端口4177无依据，模型在原16轮内调用project-brief生成DOC004，最终manifest排除旧DOC001，DOC004 L41基于default_port:null说明未指定默认值。两次可见review、一次无效提交拒绝均保留；没有隐藏重试或主机修补。三份最终文档及两份实际CSV已逐项读取/hash和字段核验，六标准的真实行证据写入content-review-20261110.json。文档中“未定义（default_port为null）”在此facts上下文解释为输入未指定，不作“软件确定没有默认值”的断言；该解释已明确记入复核记录。

当前F32 N100完成2/3，自动2次true、内容正确1次；不能用部分观测声称整个档1/3或稳定改善。两个完成试次的真实F审计共7节点、3附件、28新模型回复、0重放通过，原文/完整上游/实际路径视图/审阅消息均相符。62447继续N100/seed3及后续166/40k，原预注册不变。

新增《Skill编排实现与汇报说明-20261110.md》集中给出真实实现、已完成E矩阵、N/K/节点/链口径、来源限制、失败例、复现命令与本人录屏展示顺序；F复制来的早期README/协议统一标明历史配置，防止误用旧六任务族、两个控制工具或全文曝光描述。F全部冻结Python源码hash仍通过检查，当前模型实验不受文档整理影响。


F32 N100三次已全部结束，自动3/3、内容复核1/3，仅seed2正确。seed3最终DOC002 L73把无云同步推成全部维护必须本地，L106把建议未来审查日期填为Last Reviewed，L108又填Published。具体2025-06-01来自planner生成的子请求，原facts与原knowledge-base源文均没有该日期，不能误称为源模板逐字污染；已经保存原请求hash、源hash及逐字链路。工人接到了原facts但仍将规划器自增数据当成项目事实。

E32/F32 N100配对比较证实三个seed各自首个planner请求字节完全相同，首个规范化assistant正文/真实函数名参数也相同（忽略服务端随机调用ID）。首个worker请求只变更system末尾追加通用来源边界，完整原system为前缀，原facts/子任务/其他参数均相同；后续还叠加逻辑路径和生成历史变化。E32正确向量[false,false,true]，F32[false,true,false]，都为1/3，不能宣称总体稳定性提高或将变化仅归因于路径。比较写入comparison-e32-f32-n100.json。

完成三试次的F来源/物理/实际消息审计：9节点、5附件、37全新模型响应、0重放。实时loopback只读核对Ollama0.33.1及Qwen模型digest仍与F预注册相同，当前模型上下文32768；环境观测另存。62447已进入166/seed1，F32/40仍未完成。


F32 N166/seed1已明确终止失败：首请求166候选+3控制工具正常接受，prompt28781；后续planner02完整请求33582>32768被HTTP400拒绝，truncate/shift均false，无静默裁剪或重试。已生成K4/4节点，但全为并行根节点，链长1、依赖边0，未满足组合标准。failure-diagnosis.json保存错误与请求hash。该失败不证明166是内在路由上限，也不把四个节点写成正确执行链。F32当前N100已完成1/3正确，N166仅完成1/3且失败，剩余两次未计通过。43条新响应、13节点、6附件的完成试次partial audit通过；62447继续seed2，然后完成剩余32k与独立40k。


F32 N166/seed2已完成：原自动true，K2/2节点/链2；最终两文档和两CSV全部实际读取/hash复核后否决。DOC001 L23断言“无外部服务连接”，L91将web_management_ui:null解释为“确认仅通过CLI运行”。额外metadata CSV是知识库注册表，和反馈空模板字段不同；已完整解析，不把它的非空行误判为虚构反馈记录。仅两条确定的未支持产品断言即可否决。当前N166已完成2/3，两次均未正确通过（一次上下文失败、一次内容失败），第三次仍在运行，不提前写整档0/3。完成试次的F审计现为15节点、8附件、53条新响应、0重放；原自动分数完整保留。


F32两档6次全部结束，所有5个自动正例均完成全文/附件直接复核。N100自动3/3、实际1/3；N166自动2/3、实际1/3（seed3正确）。N166/seed3实际使用product-design-harness→copy-editing，完整DOC001被读取并生成真实优化版DOC002；K2、节点2、最长链2节点。最终仅交付DOC002与FILE002，85行文档及实际CSV读入/hash均匹配；六条原标准的逐字行证据已写入content-review-20261110.json。未知保持未知，流程/职责明确建议，未发现无依据UI/CLI-only、安装、负责人或网络保证。

最大已验证单次成功候选规模更新为166；当前仍无任何完成档达到3/3正确，稳定上限未建立。不得把166说成单次调用166种，或把F32这一正例说成重复可复现已证明。原F32全部17节点、10附件、63条全新响应、0重放最终审计通过，原自动结果仍保留。

F40独立校准六标签全部匹配（5规则拒绝+1模型接受），进入100/166各三次完整业务，仍由62447串行运行。新增已知seed复现计划及预注册：固定原F32 N166/seed3、相同32768/24GPU/全部166来源/原完整用例和16轮，等62447终止后在新目录一次真实重跑。单试次索引1但模型seed必须3，不计新独立seed，不重试直到成功。临时入口离线防错门槛已6项红→绿；尚未运行该复现。


F40 N100/seed1完整结束原自动true，但全文直接复核否决：仍把不支持PDF OCR扩大为不能处理PDF文件。实际全部最终文档/CSV哈希和F32同seed相同，正文再次实际读取，不是复制旧模型回复。12个模型请求的名称集合完全相同，逐项JSON比较确认唯一差异是options.num_ctx（32768→40960）；物理run目录已不进入这些模型payload。这是此次F路径规范化的可检查输入控制证据，不说明内容正确或普遍确定性。比较写入comparison-f32-f40-n100-s1.json。当前F40仅完成一个试次，不提前报整档正确率。

原最大单次成功166/seed3的独立复现入口已固定：7项离线防错测试通过（包含真实调用边界seed3、错误context、源码hash漂移、前置队列未结束、缺完整audit拒绝启动，以及无网络verify-only），与业务分数无关。预注册及入口/test字节已冻结；尚未开始新推理，等待当前62447全部结束。


F40 N100/seed2完整结束并通过内容复核：K3/节点4/最长链4节点，保留原预算内的默认端口修订。新最终文档及两实际CSV全部重新读取并校验hash，完整原任务/facts/六标准与已接受的F32同seed完全一致；六条真实行证据逐项重新核对。F32/F40该seed的16个真实请求逐项仅num_ctx不同，所有最终正文hash相同，且16条新native响应created_at均不同于旧响应，未重放。该正确功能结果在40k重现，不和32k合并独立样本数，也不代替同配置166复现。当前F40完成2/6，N100本档仅结束2/3、一败一过，剩余仍在途。完成部分7节点、3附件、28新回复、0重放物理/来源审计通过。


F40 N100三次全部结束，原自动3/3、内容正确1/3，仅seed2正确；第三次仍保留本地维护绝对限制、Last Reviewed日期和Published状态三项无依据内容，已逐项核对当前真实行与实际文件。三个seed的全部12/16/9共37个模型请求，在F32/F40之间逐项仅num_ctx不同，最终正文hash及正确向量[false,true,false]均相同；这个受控对照没有显示100档正确率因32k→40k改善，不外推总体概率。37条真实新回复、9节点、5附件、0重放完成部分审计通过。F40 N166三次仍在运行，不能报整档；最大单次已验证166来自已结束F32/seed3，稳定上限和同配置166复现仍待后续。


2026-11-11追加：F40 N166/seed1已终止失败，8实际节点/K4/最长链4节点；先前32k拒绝的planner02完整请求33582 tokens在40k被真实接受，两个请求只差num_ctx，实际native prompt_eval_count33582且正常stop。随后review02仍指出DOC005 L44/DOC006 L46把指定端口写成默认端口，未修完；planner09完整请求41226>40960再遭明确拒绝。failure-diagnosis.json保存两类失败与实际请求hash，不能把走得更远称通过。

F40 N166/seed2已完整结束原自动true，当前全正文及实际反馈CSV/元数据CSV均读取/hash后仍否决：DOC001 L23无外部服务连接、L91把未知UI写成CLI-only。10个真实模型请求与F32同seed逐项只差num_ctx，所有最终正文hash相同，native timestamps均不同；这是全新调用而非重放。目前F40仅N166最后seed未结束，不能报整档0/3。完成部分19节点/10附件/64新回复/0重放审计通过。

F32六次独立证据包已生成deliverables/skill-boundary-f32-evidence-20261111.zip，2764914字节，SHA256 9fff87f63c01abcad15b9d60786fd8d6b083ed572f98e4967a731d93b58fec80；ZIP CRC、773个清单文件、全部166源SHA均已实查，并解压到另一个目录运行verify_bundle，全部通过且零模型调用。包含原全部6次成功/失败、实际源、校准、逐文复核及原始代码，历史路径保留；它是取证包，不声称新模型重跑或跨机器便携执行已完成。F40与已预注册166同seed复现不在此包最终结果范围，目标继续。


2026-11-11最终模型阶段：62447已exit0，F32/F40各100/166三次共12个完整主试次全部结束，10个自动正例全部经完整内容复核。两个context的N100/N166均为1/3正确；F40最后166/seed3也完整正确，85行文档与实际空CSV哈希和F32相同，10个请求仅num_ctx不同。F32最终审计17节点/10附件/63新回复；F40最终审计21节点/12附件/74新回复，均0重放。没有证明增加context改善这批正确率，也没有3/3稳定档。

预注册已知166/seed3新目录重跑已真正结束，唯一handle39382也exit0。单试次索引1、所有实际请求均模型seed3、context32768；原完整166候选/六标准/16轮/原实现未变。原自动true，新89行DOC002与实际空CSV经完整直接复核均正确，K2/节点2/链2，functional_reproduction_accepted=true；记录见content-review-20261111.json与effective-status-20261111.json。它不新增独立seed，不改原三seed的1/3。已知可重复的单次正确候选规模166，仍不能称166稳定上限或全166能力认证。

逐字轨迹未复现：初始planner请求字节相同且规范化首个函数/参数相同；首个worker请求SHA均6660ced1d4dfe59fc0b4cf431789c3ffde45d83753a42ed4eb63dd4d39b36c06，但模型正文先出现差异，后续输入随生成历史变化。原85行终稿SHA5d990f...，新89行SHAa580ec...；两稿都满足原任务。不能把该差异归因于随机tool-call ID或run目录；GPU/CPU数值、KV缓存或其他运行时状态尚未隔离，具体原因未证明。reproduction-content-diagnosis.json保存首个实际正文差异证据。

该重跑来源/真实上游/实际消息/文件/seed/终验审计通过：2节点、2附件、10全新模型回复、0重放。当前F两context与该重跑共147个新回复，统计仅作取证总量，不把各context或已知seed合并稳定率。全部模型推理已结束；剩余工作为联合复现包、可用新prefix入口、异目录核验与逐要求最终审计，目标暂不宣布完成。
