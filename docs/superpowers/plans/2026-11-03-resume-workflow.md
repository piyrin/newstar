# Resume Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从本机原始材料生成可追溯、经用户确认后导出的个人简历。

**Architecture:** Python 模块负责快照、解析、模型请求、校验、审阅与导出。两个 Airflow DAG 调用这些模块；共享目录传文件，XCom 只传标识。DeepSeek 真实接口与离线样例严格分开。

**Tech Stack:** Python、Airflow TaskFlow、python-docx、pypdf、Pillow、Tesseract、LibreOffice、Poppler、标准库 HTTP 服务。

**Spec:** `docs/superpowers/specs/2026-11-03-resume-workflow-design.md`（用户已批准）

## Global Constraints

- 第一版手动触发，不自动投递或发布。
- 所有个人材料、密钥、运行产物不进 Git；样例必须为虚构。
- 来源可追溯，不编造经历、量化效果或个人贡献。
- 正文、事实处理、模板或材料变化使确认失效。
- PDF 必须由同一份 DOCX 导出；自动检查与最终视觉验收分开。
- 保留当前未提交内容，不自动提交或推送；在当前允许写入的工作区实施。

## Review Focus

- 输入目录含路径穿越、符号链接或超大材料：拒绝越界并报告限制。
- 模型返回不存在的引用、空响应、截断或结构错误：不接受为正常事实。
- 一部分材料解析失败、团队贡献不明或姓名缺失：列入审阅问题，禁止未经处理导出。
- 确认后的源文件、模板、正文或产物被改动：摘要失效，阻止错误版本导出/验收。
- 中文 OCR 与字体不可用、超过一页、转换失败：报告真实错误，不伪称通过。

## Files and Interfaces

`airflow/dags/resume_flow/` 为可导入包：`storage.py`（快照和原子文件）、`extract.py`（解析）、`llm.py`（DeepSeek）、`workflow.py`（事实/文案）、`review.py`（确认和本机 UI）、`export.py`（同源导出）、`cli.py`（命令）、`vendor/`（有出处的简历脚本）。

`airflow/dags/resume_workflows.py` 定义两个 DAG。`airflow/resume/` 保存 Dockerfile、依赖、虚构样例、CLI 包装器及操作说明。`tests/` 使用 unittest 及合成文件。独立 Compose override 显式启用简历运行镜像，不改变当前教学环境默认镜像。

### Task 1: 快照与材料提取

- [ ] 写 `tests/test_resume_storage_extract.py`，断言快照隔离/幂等、拒绝越界、坏文件不阻断其他文件，DOCX/PDF 分页定位、OCR 缺失如实报告。
- [ ] 运行 `python -m unittest discover -s tests -p test_resume_storage_extract.py -v`，确认实现不存在导致失败。
- [ ] 实现 `snapshot(workspace: Path, case_id: str, run_key: str, target: str, jd: str) -> str`、`extract_run(workspace: Path, run_key: str) -> str`；JSON/路径由 storage 统一校验。
- [ ] 同一测试命令通过；补充实际工具的合成 PDF/图片集成提取验证。

### Task 2: DeepSeek 与事实/草稿

- [ ] 写 `tests/test_resume_workflow.py`，覆盖错误引用、缺项、歧义贡献、矛盾、模型空白/截断/重试上限与离线数据标记。
- [ ] 运行对应 unittest 文件，观察失败后实现 `DeepSeekClient.complete(system: str, payload: dict) -> dict`、`collect_facts(workspace, run_key, mode) -> str`、`draft_resume(workspace, run_key, mode) -> str`。
- [ ] 一次文件/分段请求限制、总调用限制、片段摘要保留、来源片段验证。草稿使用 fact ID，程序映射为排版 JSON，姓名等从事实而非模型自由填充。
- [ ] 测试通过，真实 API 需本机密钥后独立验收。

### Task 3: 审阅与确认

- [ ] 写 `tests/test_resume_review.py`，覆盖未解决问题、三种模板选择、确认摘要失效和预览不批准。
- [ ] 观察失败后实现 `prepare_review(workspace, run_key)`、`approve(workspace, run_key)`、`verify_approval(workspace, run_key)`。
- [ ] 实现仅监听 127.0.0.1 且带令牌的本机审阅/模板页面：显示来源、草稿、问题处理与模板；显式确认，预览不保存。CLI 提供等价操作。
- [ ] 测试通过，并以合成审阅数据测试 UI 请求与确认。

### Task 4: 文档导出与检查

- [ ] 写 `tests/test_resume_export.py`，覆盖无确认拒绝、失效确认拒绝、页数与文字缺失失败、最终视觉验收绑定产物摘要。
- [ ] 观察失败后适配已有 resume-maker 排版器/检查器到 vendor 并标明来源，使用 LibreOffice 同源转换、Poppler 全页渲染；失败保留检查报告。
- [ ] 实现 `export_resume(workspace, run_key, export_key)` 与 `accept_visual(workspace, export_key)`；独立导出快照防止并发修改。
- [ ] 合成资料走通 DOCX/PDF/PNG，逐页看图；缺少后端时先完成逻辑测试，补齐依赖再验证真实导出。

### Task 5: DAG、部署与交付

- [ ] 写 DAG 结构/轻量集成测试，观察新增 DAG 未存在的失败。
- [ ] 实现 `resume_prepare` 与 `resume_export`、CLI、Dockerfile、Compose override、虚构材料初始化器和说明。
- [ ] 跑全部测试、编译、Compose 配置检查、DAG 导入与实际执行器两阶段合成测试；依赖/权限阻碍如实记录，继续其他验证。
- [ ] 一次独立最终代码审阅，修复重要问题并补回归测试；更新 README、计划与验证记录，不自动提交。

## Execution ledger

- Ruling: 用户已明确“开始”，按已批准设计连续实施，不重复请求计划或执行方式确认；本轮由主代理实施，最后独立审阅。
- Ruling: 当前 .git 为只读且工作区已有未提交内容，直接在当前授权目录工作，不创建 worktree 或提交，避免搬动既有材料；代价是改动同处一个工作区，用文件范围与状态检查区分。
- Pre-flight: Tasks 1–5 统一 workspace/run_key；事实记录以 segment_id 和原文片段引用；审阅内容摘要是导出唯一输入。
- Task 1: 代码与本机解析测试完成；真实中文 OCR 待运行镜像可用后验收。
- Task 2: 模型适配与事实/草稿离线测试完成；真实 DeepSeek 未配置密钥，保持未验收。
- Task 3: 确认逻辑与实际浏览器操作完成；只对虚构样例作测试确认。
- Task 4: 导出与检查代码完成；DOCX 实际生成，PDF 后端缺失，自动检查失败路径已验证。最终 PDF 与视觉验收未完成。
- Task 5: DAG/镜像/Compose/CLI/文档已实现；配置与语法通过，Docker 启动退出码 1 阻止真实 DAG/Celery 与镜像构建验收。
- Final: fixed 批准失败页面 revision、明确省略的身份信息、零事实片段遗漏 — 新增回归测试均 RED→GREEN。
- Final: Ruling: 将状态滞留与 DAG 分步失败报告提升为应修复问题 — 用户依赖这些结果查进度和定位失败，已新增回归测试并修复 — 代价是增加状态计算与统一步骤包装。
- Final: Ruling: 不扩展成 Docker 重装/数据迁移修复任务 — 启动与只读诊断已尝试，继续系统修复可能影响已有环境；明确保留容器验收未完成 — 代价是用户需先恢复 Docker 才能验证部署。
- Final: reviewer 未判断的 API、容器、OCR/PDF 与真实资料验收保留为独立待办，详见 airflow/resume/VERIFICATION.md；未合并、未推送。
- 2026-11-03 continuation: 用户报告 Docker 已启动并明确本轮只做离线验证。镜像构建/部署、29 项容器测试、真实 DagBag 导入、两个 Celery 成功 DAG（5+4 任务）、未确认导出负向测试、真实 OCR/文档读取、同源单页 Word/PDF 与整页视觉检查均完成。仅对虚构样例写测试视觉确认。
- 2026-11-03 continuation: 真实图片 OCR 对“奖”有一处误识别，扫描 PDF 的对应内容正确；保留原始输出，集成检查验证读取路径与人工复核状态，不承诺 OCR 逐字正确。未修改生产代码；真实 DeepSeek 与本人材料仍待用户准备。
- 2026-11-03 API continuation: 用户已在本机填写密钥；已加载容器配置，内置虚构材料经真实 deepseek-flash 完成事实整理、草稿和导出两阶段，9 个 Celery 任务均 success 且首次通过，单页 PDF 自动/视觉检查通过。
- 2026-11-03 API continuation: 修复真实 API 模式下内置虚构样例丢失 synthetic 标记的问题，新增回归测试 RED→GREEN，本机及容器 30 项测试全通过。仅虚构版本做测试确认，不代表批准用户真实简历；个人材料仍待提供。
