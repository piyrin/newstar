# 验证记录

日期：2026-11-03。结论：专用镜像已构建并部署；虚构材料的离线模式和真实 DeepSeek 模式均已通过两个 DAG 的真实 Celery 执行、Word/PDF 导出、自动检查与整页视觉检查。密钥已生效，用户本人材料与正式简历尚未提供/验收。

## 已验证

- 30 项 unittest 在本机及实际简历工作容器中均通过：快照隔离与重试、ID 越界、材料大小限制、坏文件与不支持格式、DOCX 段落、真实文本 PDF 提取、扫描 PDF OCR 路由、OCR 后端缺失报告、快照改动检测，以及真实模型模式下内置虚构材料仍保持 synthetic=true。
- 事实引用必须存在于输入片段，事实值/引用片段需来自原文；项目个人贡献、OCR、姓名冲突和缺失字段进入待确认项；模型对整个片段不提取事实也会显式报告。
- DeepSeek HTTP 请求的离线响应测试覆盖正常 JSON、空白、截断、有限重试、密钥不进入请求正文；另外已完成下述真实 API 验收，二者独立记录。
- 人工审阅：选择三种模板，问题未处理则阻止，明确省略的姓名/联系方式不能继续使用，正文/模板/材料变化使确认失效；批准失败后返回新版本供继续编辑。
- 导出输入快照、缺少确认拒绝、后端失败报告（CLI 和 DAG 分步路径）、真实空白/超页 PDF 被检查器拒绝、视觉验收要求产物摘要完整且未改动。
- 使用 Airflow 3.3.2 的实际 DagBag 解析器导入两个 DAG，import_errors 为空；数据库确认两个 DAG 均保持暂停，schedule=None，只手动触发。
- 实际本机运行：内置虚构材料 → 快照 → 提取 → 离线事实 → 草稿 → 审阅包；真实浏览器页面完成选择、保存及明确确认，样例标记 synthetic。
- 虚构运行 `demo-celery-20261103` 已经真实 CeleryExecutor 完成准备阶段五个任务，全部 success、try_number=1。
- 对该虚构版本执行测试确认后，`demo-celery-export-20261103` 经真实 CeleryExecutor 完成导出阶段四个任务，全部 success、try_number=1。
- 实际生成 `resume.docx`、由其经 LibreOffice 同源转换的 `resume.pdf`、`page-1.png`。检查器 ok=true、errors=[]、pages=1、PDF 可提取文字数 122。用 Documents 标准 renderer 接入同源 PDF 再渲染并查看整页，未发现中文缺字、重叠或异常分页；只给此虚构版本写入测试视觉确认，CLI 状态为 final。
- 未确认运行 `demo-unapproved-20261103` 的真实 Celery 负向测试符合预期：verify_and_freeze 首次失败、不重试，三个下游任务 upstream_failed，未生成导出目录。Airflow 中这条红色记录是有意验证保护机制。
- 在新镜像中运行 `tests/integration_resume_runtime.py`，实际图片 OCR、扫描 PDF OCR、DOCX 和文本 PDF 四条路径均读到“测试同学”，保留定位信息。图片 OCR 将“省级一等奖”识别成“省级一等次”，扫描 PDF 版本正确；这项差异如实记录，不能把 OCR 当作奖项核实。
- 专用镜像 `newstar-airflow-resume:3.3.2` 构建完成，`python -m pip check` 无依赖错误；七个运行服务均 healthy，DAG 导入错误列表为 []。
- Compose 两文件合并 `config --quiet` 检查通过，Python 编译与 JavaScript 语法检查通过。保留所有既有未提交内容，未提交/推送 Git。

测试命令：

```powershell
# 本次使用 Codex 依赖工具返回的 Python；普通开发可用按 README 配置的 venv。
python -m unittest discover -s tests -v
python -m compileall -q airflow/dags/resume_flow airflow/dags/resume_workflows.py
node --check airflow/dags/resume_flow/web/app.js
```

## 历史阻碍与剩余未验收项

1. **Docker 旧阻碍已解除**：此前引擎管道不可用、启动退出码 1；用户启动 Docker 后，本轮已完成镜像构建、DAG 导入、Celery 与容器导出验证。没有重装、重置或改动 Docker 数据。
2. **Windows 本机仍无 LibreOffice**：第一次本机导出和 renderer 失败记录保留。部署镜像已包含并实际验证 LibreOffice、Noto CJK、Poppler、Tesseract，容器导出可用；不依赖 Windows 安装 LibreOffice。
3. **真实 DeepSeek 已通过虚构样例验证**：第一次因密钥未配置而仅离线验证；用户在本机填入真实密钥后，容器已加载配置，使用 deepseek-flash 成功调用事实整理和草稿生成。只发送内置虚构材料，不输出密钥或发送用户个人资料。该结果不代表任意材料与模型输出都无需复核。
4. **真实材料尚未整理**：没有生成或验收用户本人简历。当前验证产物均为明确标注的虚构测试，不能用测试确认代替用户真实确认。

## 可复查的运行证据

宿主机共享工作区（均被 Git 忽略）：

- `airflow/resume_workspace/verification/dag-runs.json`：直接从 DagRun/TaskInstance 核对的三次运行、任务状态与尝试次数。
- `airflow/resume_workspace/verification/runtime-tools.json`：真实工具、字体路径、OCR 原始文本与识别差异。
- `airflow/resume_workspace/outputs/demo-celery-export-20261103/`：Word、PDF、页面 PNG、自动检查与测试视觉确认记录。
- `airflow/logs/resume-image-build.log`、`resume-compose-up.log`、`resume-prepare-celery.log`、`resume-export-celery.log`、`resume-export-unapproved.log`、`resume-unit-container.log`：构建、部署和执行日志。

准备运行 ID：`manual__2026-11-03T13:13:33.386733+00:00`；导出成功运行 ID：`manual__2026-11-03T13:15:11.658997+00:00`；预期失败运行 ID：`manual__2026-11-03T13:17:53.918739+00:00`。ID 内时间为 UTC。

下次运行环境验证可将 `tests/integration_resume_runtime.py` 复制至简历 worker 的 `/tmp` 并执行；只创建临时虚构材料，不调用模型。

## 剩余步骤

放入用户真实材料，核对个人贡献、岗位方向、正文和模板，单独确认与验收；不复用测试确认。

## 真实 DeepSeek 接入验证（2026-11-03 后续）

- 用户在被 Git 忽略的本机 `.env` 填写密钥后，仅检查非空与是否已替换占位符，不打印值；重新加载 Compose 环境，七个运行服务均 healthy。
- 以 `case_id=demo`、`mode=deepseek`、`run_key=demo-deepseek-20261103` 执行 resume_prepare：5 个任务均 success、try_number=1；真实模型提取 5 条逐字可核对的事实，生成 3 个简历栏目，无待补充问题。
- 阅读核对这些虚构事实与正文后，仅对该虚构版本做测试确认；`export_key=demo-deepseek-export-20261103` 的 resume_export 四个任务均 success、try_number=1。
- PDF 自动报告为 ok=true、errors=[]、pages=1、可提取字符数 142。接入 Documents 标准 renderer 重新渲染同源 PDF 并查看整页，无缺字、重叠或异常分页；该虚构版本已写入测试视觉确认，状态 final。
- 修复一处样例元数据：synthetic 不再仅由 offline 模式决定，内置虚构材料即使经真实 DeepSeek 处理也保留 synthetic=true；新增回归测试先失败后通过，全部 30 项测试在本机与容器通过。
- 原始运行证据：`airflow/resume_workspace/verification/deepseek-runs.json`；新版本产物：`airflow/resume_workspace/outputs/demo-deepseek-export-20261103/`；日志：`airflow/logs/resume-prepare-deepseek.log`、`resume-export-deepseek.log`、`resume-unit-deepseek.log`。
- 准备运行 ID：`manual__2026-11-03T13:34:23.429495+00:00`；导出运行 ID：`manual__2026-11-03T13:36:41.824443+00:00`。ID 内时间为 UTC。

## 独立审阅处理

审阅指出三项重要问题（批准失败后页面版本失效、已省略身份仍被采用、模型零事实遗漏未报告），均补了先失败后通过的回归测试并修复。状态滞留与 DAG 分步导出缺少失败报告也已修复并测试。

审阅未判断的环境运行、真实 API、OCR/字体/PDF 视觉质量和个人材料真实性，分别按上述独立验收处理，未用单元测试结果代替。
