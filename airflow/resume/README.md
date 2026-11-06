# 从原始材料制作自己的简历

## 从 Airflow 主流程开始

直接触发 `resume_prepare`。新建案例可留空，或填写 `5` 这样的新名称。主流程先执行 `open_material_page` 发布专用页面，再在 `await_materials` 等待网页提交。导入文件或GitHub并点击“提交材料并继续”后，同一次运行继续 `snapshot_materials → extract_materials → organize_facts → write_draft → publish_review`。

已有材料时直接进入处理。需要先打开网页更新材料时，勾选触发参数“先打开材料填写页”。材料页中“结束本次等待”可结束对应的等待运行。自动打开浏览器依赖本机引导程序，工作台同时列出等待材料的入口。

材料等待允许16个活动运行。归档、提取、整理、起草和发布使用单槽 `resume_preparation` 池，起草结果绑定输入摘要缓存。初始化新环境后创建该池。

```powershell
& $dockerExe compose -f docker-compose.yaml -f docker-compose.resume.yaml exec -T airflow-worker airflow pools set resume_preparation 1 "Serial resume preparation tasks"
```

定时运行使用 `RESUME_DEFAULT_CASE` 配置的案例进行检查。重复且已处理的材料会复用原有审阅包，首次上传与材料提交为独立的明确步骤。

## 完善信息与管理草稿

审阅页提供姓名、求职方向、手机、邮箱、主页、意向城市、实习时间及学校、院系、专业、学历、起止时间、GPA、课程表单。可选信息按实际情况留空，填写后同步正文与预览。项目、技能等内容可在独立编辑项中修改，高级JSON保留完整数据入口。

“需要你补充或核对”显示简短清单。同一材料的同类校验问题合并，原始问题、引用事实与处理记录保存在折叠依据中。项目经本人核实后可整理为项目条目，名称、职责或技术栈、时间、链接与正文分别编辑。

近期草稿每行显示材料案例、更新时间和删除按钮。删除采用 `resume_workspace/deleted_drafts/<run_key>.json` 标记，可在“已删除草稿”恢复。操作会结束精确关联的等待运行，Airflow中主动结束的运行记为failed。正在进行材料解析、模型调用或文件生成时会提示稍后重试。恢复后可重新审阅并提交生成。

参考文档补充的手填内容与原始材料事实分开保存，修改后的内容需重新确认。修改前的审阅版本可保存在对应 `reviews/<run_key>/history/`。

## 推荐入口：本机简历工作台

打开 **http://localhost:8765**。服务已加入 Compose，Docker/Airflow 启动后会自动运行，无需每次在 VS Code 启动审阅服务或手动触发导出。

1. 在“导入你的材料”拖入或选择多份文件，选择案例或新建案例，点击“导入到本机”。同名更新保留旧版备份，支持 TXT/MD/DOCX/PDF/PNG/JPG，每文件5MB、每案例20MB/100文件。也可以继续使用 `resume_workspace/inputs/<case_id>/` 目录。
2. 选择材料案例，填写目标岗位，点击“开始整理”。`demo + offline` 仅用于原样虚构演示；真实材料使用 DeepSeek。
3. 页面显示整理进度。完成后在近期草稿点击“进入审阅”。从 Airflow 触发也可以回到工作台查看，`publish_review` 日志会打印直接审阅链接。
4. 按材料分组核对事实，处理问题，修改正文。姓名、邮箱、手机和目标方向可在独立输入框填写，邮箱、手机与照片可留空。可上传 PNG/JPG 照片，最多2MB、1000万像素。核实项目后可点击“采用已核实项目到正文”。选择细线标题、灰条标题或浅色卡片，实际分页以 PDF 为准。
5. 点击“确认并继续生成Word/PDF”，明确确认当前正文/模板。工作台自动安排同一个 `resume_prepare` DAG 的导出运行，复用准备结果，执行冻结、Word、PDF和页面检查。
6. 在“05 / 导出与下载”查看进度、失败信息、输出目录、Word/PDF 下载按钮和所有页面预览。逐页核实后可勾选并确认最终版本。

物理文件保存于 `D:\code\newstar\airflow\resume_workspace\outputs\<export_key>\`，页面会显示完整目录。修改后需重新确认导出；下载区显示的是已经确认导出的版本。接口校验确认记录、文件归属和产物摘要，失败或未检查文件不作为成品提供。

主流程 `resume_prepare` 包含整理、发布审阅、确认检查、生成Word/PDF和页面检查。`await_review` 检查本次运行是否绑定有效人工确认。尚未确认时跳过后续导出并结束运行，工作台保留审阅待办。确认后自动创建绑定当前内容的新运行，复用准备结果并完成导出。人工审阅期间释放DAG运行名额，其他材料可以继续处理。旧版本草稿兼容独立 `resume_export`。工作台仅发布在 `127.0.0.1:8765`，主页面同源获取临时会话，接口要求令牌并校验 Host/Origin。

重复材料会跳过提取、事实整理和起草，`publish_review` 仍发布审阅链接。未绑定人工确认的检查运行会跳过后续导出，正常结束。确认绑定导出运行和内容摘要，修改后需要重新确认。网页导入仅发送到本机，DeepSeek模式开始整理时提取文字才发送给模型。旧文件备份位于 `resume_workspace/input_history/<case_id>/<request_id>/`。

管理服务：使用两个 Compose 文件执行 `up -d resume-portal`；排查时执行 `logs --tail 60 resume-portal`。模板来源见 [TEMPLATE_SOURCES.md](../dags/resume_flow/vendor/TEMPLATE_SOURCES.md)，本轮验证见 [VERIFICATION-20261105.md](VERIFICATION-20261105.md)。

`resume_prepare` 每半小时检查指定材料目录，也支持手动触发。网页确认后自动启动同一DAG的导出运行，`resume_export` 保留为旧版兼容入口。内置样例完全虚构，用来验证程序。用户导入的真实材料需逐项审阅后确认。

```text
resume_prepare: snapshot_materials → extract_materials → organize_facts → write_draft → publish_review → await_review
人工审阅: 核对原文 → 处理问题 → 修改正文 → 选模板 → 明确确认
同一运行继续: verify_and_freeze → render_word → export_pdf → check_pages
人工验收: 查看全部 page-N.png → 明确确认最终版
```

## 1. 运行环境

项目根目录为 `D:\code\newstar`，以下 Docker 命令在 `D:\code\newstar\airflow` 执行。沿用已有 Docker Desktop 与 Airflow 环境。新增专用镜像包含中文 OCR、LibreOffice、中文字体及 PDF 渲染工具；启用 override 才使用该镜像。

```powershell
Set-Location D:\code\newstar\airflow
$dockerExe = 'D:\docker\anzhuang\DockerDesktop\resources\bin\docker.exe'
& $dockerExe compose -f docker-compose.yaml -f docker-compose.resume.yaml config --quiet
& $dockerExe compose -f docker-compose.yaml -f docker-compose.resume.yaml build airflow-worker
& $dockerExe compose -f docker-compose.yaml -f docker-compose.resume.yaml up -d
```

后续管理也要带两个 `-f` 参数，以免把运行配置切回基础镜像。此操作会重建 Airflow 服务容器，已有数据库卷与教学 DAG 保留。首次构建需要网络下载依赖；不要执行 `down -v`。

## 2. 配置 DeepSeek

在已有且被忽略的 `airflow/.env` 中添加（保留原内容）：

```dotenv
DEEPSEEK_API_KEY=在本机填写你的密钥
DEEPSEEK_MODEL=deepseek-flash
```

之后用上述两个 Compose 文件执行 `up -d`，让环境配置生效。不要把密钥填在 DAG 参数、材料、聊天或代码中。Compose 的 `config` 不带 `--quiet` 会展开环境变量，不要公开其输出。

使用 DeepSeek 模式时，OCR/文件解析在本地执行，提取的文字及岗位要求发送给 DeepSeek。最终导出阶段不再发送正文给模型。接口基址固定为官方 `https://api.deepseek.com`，模型可配置。实际密钥和账户余额需用户准备；未配置时明确失败，不退回虚构结果。

参考：[官方入门](https://api-docs.deepseek.com/)、[JSON 输出](https://api-docs.deepseek.com/guides/json_mode/)。

## 3. 先跑虚构样例

初始化仅生成一份标明虚构的材料，不覆盖不同内容：

```powershell
& $dockerExe compose -f docker-compose.yaml -f docker-compose.resume.yaml exec -T airflow-worker python -m resume_flow.cli sample
```

在 Airflow 页面手动触发 `resume_prepare`，参数如下：

```json
{"case_id":"demo","run_key":"demo-run","target":"技术实习（虚构测试）","jd":"","mode":"offline"}
```

`offline` 只接受内置材料的原样内容，不能用于真实个人材料，不调用外部模型。五个任务成功后，审阅包位于宿主机 `airflow/resume_workspace/runs/demo-run/`，可编辑文件位于 `reviews/demo-run/`。

## 4. 在本机审阅并选择模板

审阅服务在 Windows 本机启动，仅监听 `127.0.0.1`。需要 Python 3.11+。仅审阅页面不需要 Word、OCR 或 Airflow Python 包；本机完整运行需安装 `requirements.txt` 中的依赖。

```powershell
Set-Location D:\code\newstar
python airflow/resume/resume_cli.py review --run-key demo-run
```

在浏览器打开命令打印的完整链接（含临时令牌）。页面显示事实来源、分组待确认项、基本信息表单、高级正文 JSON 与三种版式示意。姓名为必填项，邮箱、手机、目标方向和照片可留空。核心经历可补材料后重新整理，或在正文中补充经你核实的信息。JSON 的栏目顺序就是 Word 栏目顺序，改动后预览同步更新。

- 同一材料中的同类问题合并显示，展开的事实包含值、引用片段与来源。每组选择“已核实 / 已补充”或“明确省略”。核实说明可空，省略原因提供可编辑默认值。标记省略的事实若仍被正文 fact_ids 引用，必须先移除相应条目。
- 对于自动省略的团队项目/OCR 信息，先核实原文和本人职责。项目组可点击“采用已核实项目到正文”，再在高级正文中调整真实个人职责。通用处理说明单独保存，联系方式请填入基本信息表单。
- 选择 classic（细线标题）、minimal（灰条标题）或 technical（浅色卡片），以及纸张、纸质/电子模式。三种模板均支持可选照片，照片内容也绑定人工确认版本。
- “保存修改”不会允许导出。只有“确认正文并允许导出”才生成与材料、事实、问题处理、正文和模板摘要绑定的确认记录。
- 三套版式按用户提供的截图重建，均为全宽正文。Word/PDF 使用可编辑表格呈现浅色卡片，边角为矩形，网页保留圆角。模板版次更新后需重新确认导出。
- 关闭终端或 Ctrl+C 可停止服务。每次启动生成新令牌，旧令牌失效。不得把审阅服务暴露公网。

不用页面时，可编辑 `reviews/<run_key>/resume.json`、`questions.json`、`selection.json` 后执行：

```powershell
python airflow/resume/resume_cli.py approve --run-key demo-run --confirm
```

模板选择 JSON 示例（不要把该示例文件的存在视作真实用户确认）：

```json
{"schema_version":1,"template_id":"classic","mode":"print","paper":"A4"}
```

## 5. 导出与最终验收

在 Airflow 手动触发 `resume_export`：

```json
{"run_key":"demo-run","export_key":"demo-export"}
```

Word、由 Word 同源导出的 PDF、每页 PNG 和 `report.json` 保存到 `resume_workspace/outputs/demo-export/`。每版用不同 export_key；任务重试复用当前版本。确认后再修改正文、模板或上游材料会阻止导出，需重新确认；已占用的 export_key 不能换成新确认版本。

自动检查包括：文件存在、PDF 不旧于 DOCX、PDF 有文字、DOCX 段落在 PDF 中可查到、默认最多一页、页面渲染数量正确。超页时请精简内容，不靠极小字号硬塞。失败报告不能作为已验收结果。

所有页面看图确认中文字体、姓名联系方式、长行、标题、分页和边距后，再执行：

```powershell
python airflow/resume/resume_cli.py accept --export-key demo-export --confirm-all-pages
```

它生成绑定产物摘要的 `visual-acceptance.json`；自动通过的 `waiting_visual` 与人工确认的 `final` 分开。虚构样例确认只用于测试，不是用户真实简历的确认。

## 6. 放入自己的材料

创建 `airflow/resume_workspace/inputs/my-resume/` 并放入已整理的材料：

- `.txt` / `.md`：基本信息、教育经历、技能、项目说明、可选岗位要求。
- `.docx`：读取段落及表格行；页码不是 DOCX 的稳定结构，用段落/表格定位。
- `.pdf`：有文字层直接读取，文字很少的页面尝试 OCR。
- `.png` / `.jpg` / `.jpeg`：本地中英文 OCR；务必对照原图核实。

姓名需填写，联系方式和照片可按需要留空。目标岗位放 DAG 的 target，JD 可选。项目资料请写清本人负责部分。复杂表格、旧版 .doc、加密文档、压缩包不支持，报告中明确列出。

工作台首页另有“导入 GitHub 仓库”表单。选择材料案例，粘贴 `https://github.com/用户名/仓库名`，可填写分支和本人贡献说明，再点击导入。导入结果作为本机材料，之后点击“开始整理”。目前读取仓库基本信息、根目录文件清单、README 和常见依赖配置文件，记录固定 commit、文件链接及摘要。每文件64KB、最多9份文档、总计200KB，跳过内容会列在导入结果中。仓库内容与本人贡献需在审阅时核实。

公开仓库可直接读取。私有仓库需要在服务端配置有相应权限的 `GITHUB_TOKEN`，再重新创建 `resume-portal` 容器使环境变量生效。当前实际联网验证覆盖公开仓库，私有仓库尚未实测。

真实运行的参数示例：

```json
{"case_id":"my-resume","run_key":"my-resume-v1","target":"填写你的目标岗位","jd":"可留空","mode":"deepseek"}
```

文件/运行标识只用英文字母、数字、短横线和下划线。每次新材料用新 run_key；相同 run_key 重试始终读取旧快照。源材料、运行产物和密钥均被 Git 忽略，不自动上传或发布。

首版限制：每文件 5 MB、总计 20 MB、每案例 100 文件、PDF 30 页、图片 2500 万像素、120 段提取文字（每段 5000 字符）、最多整理 24 个片段（每次请求最多 2 次重试）再起草一次。超限/跳过写入问题清单；请拆分案例或精简材料，不默默截断成“已处理”。

## 7. 不依赖 Airflow 的本机测试

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r airflow/resume/requirements.txt
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe airflow/resume/resume_cli.py sample
.venv/Scripts/python.exe airflow/resume/resume_cli.py prepare --case-id demo --run-key demo-local --mode offline
.venv/Scripts/python.exe airflow/resume/resume_cli.py review --run-key demo-local
```

本机完整导出需要 LibreOffice 和 pdftoppm；可分别通过 `RESUME_SOFFICE`、`RESUME_PDFTOPPM` 指定可执行文件。OCR 需 PATH 中有 Tesseract（chi_sim+eng）和 pdftoppm。Docker 镜像包含这些依赖，推荐在容器导出。

## 8. 查错

- 页面看不到 DAG：检查 DAG processor、`airflow dags list-import-errors`，确认新增文件已同步。
- 整理失败：查看失败任务日志；HTTP 401/402 等需检查密钥或余额，网络临时错误才重试。
- 等待补充：看 `facts.md`、`questions.md` 与审阅页，不等于程序执行失败。
- 缺少 OCR/转换工具：使用上述专用镜像，基础教学镜像没有这些依赖。
- 无法导出：先确认材料、正文、全部问题与模板；有改动就重新确认并换 export_key。
- 任务成功不等于简历已验收：查看报告和全部页面，最后明确确认。

具体验证结果见 [验证记录](VERIFICATION.md)。2026-11-03 已构建并启用专用镜像，两个手动 DAG 经 Celery 的虚构成功路径共九个任务全部通过；Word/单页 PDF/页面渲染已核对。页面还会有一条刻意触发的未确认导出失败记录，用于验证阻断机制。两个 DAG 保持暂停。

真实中文 OCR 路径已执行，但测试图片中确实出现了错字；奖项、姓名、日期等仍需对照原图核实。用户随后填入密钥后，真实 DeepSeek 模式也已用内置虚构材料完成两阶段 Celery 执行与单页 Word/PDF 导出、检查；共 30 项容器测试通过。真实个人材料仍需单独核实与确认。

## 9. 定时检查材料更新（2026-11-04）

`resume_prepare` 的调度为北京时间每小时 `00`、`30` 分。启用 DAG 后定时检查，已成功处理的相同版本会让首任务和所有下游显示 `skipped`，不重复调用整理/起草模型。Dag Run 的 `success` 表示这次检查正常结束，不能据此认定又制作了一份简历。

- 比较相对路径、文件内容、目标岗位、JD、模型模式和流程版本；只改变文件修改时间不会重做。新增、删除、改名或内容变化均会重新判断。
- 只在成功发布审阅包后标记已处理；失败版本下次仍会重试。快照固定后，任务重试不读取后来改动的原材料。
- `run_key` 留空：自动产生 `inc-...` 内容版本，相同成功版本直接复用，包括可验证的旧成功版本。不同岗位/JD 是不同制作需求。
- 显式指定 `run_key`：该标识固定旧快照，不代表“重新读当前目录”；材料更新应留空或使用新标识。首次完整处理该显式版本后也会跳过重复运行。
- 人工改过的审阅正文不会被定时检查覆盖。新增草稿仍需单独审阅；不会自动沿用旧确认，也不会自动导出。
- 首版每次定时检查一个指定案例，不自动遍历所有材料目录；隐藏文件/目录与链接按原有快照规则跳过，超限或不支持内容仍按原有报告规则处理。

自动检查默认 `inputs/demo/`（虚构材料）。在 `airflow/.env` 配置自己的自动检查案例和岗位：

```dotenv
RESUME_DEFAULT_CASE=my-resume
RESUME_DEFAULT_TARGET=后端开发实习
RESUME_DEFAULT_MODE=deepseek
```

按第 1 节用两个 Compose 文件执行 `up -d` 使环境生效；确认材料已放好再启用。手动运行可覆盖这些参数。若要停止自动检查，在 Airflow 页面暂停 `resume_prepare`。

## 10. 自然语言入口（任务 3）

完整链路：中文需求 → 真实 DeepSeek 返回 JSON → 程序校验 → Airflow JWT 认证 → `/api/v2` 触发已有 DAG → 查询运行与任务状态。采用已有 DAG 的选择和参数编排，不动态生成或执行 Python 代码。

本机入口自动读取被忽略的 `airflow/.env` 中的 DeepSeek 和 Airflow API 配置，已有环境变量优先，不执行其中的命令。Airflow 登录默认沿用项目 Compose 初始化账户；自定义账户可填写 `AIRFLOW_API_USERNAME` / `AIRFLOW_API_PASSWORD`，或已有 `_AIRFLOW_WWW_USER_USERNAME` / `_AIRFLOW_WWW_USER_PASSWORD`；也支持 `AIRFLOW_API_TOKEN`。`AIRFLOW_API_URL` 默认 `http://localhost:8080`。凭证不发给模型。

```powershell
Set-Location D:\code\newstar

# 交互入口：支持根据前文补充信息，exit 结束。
.venv/Scripts/python.exe airflow/resume/resume_cli.py chat

# 只解析，不触发 Airflow（仍调用真实 DeepSeek）。
.venv/Scripts/python.exe airflow/resume/resume_cli.py ask "把 demo 材料整理成技术实习简历草稿，使用 offline 模式" --dry-run

# 提交制作请求；相同请求重试复用 request-id，不同需求换 ID。
.venv/Scripts/python.exe airflow/resume/resume_cli.py ask "把 demo 材料整理成技术实习简历草稿，使用 offline 模式" --request-id demo-nl-001

# 查询真实运行。输出 preparation.run_key 后，可用第 4 节命令审阅。
.venv/Scripts/python.exe airflow/resume/resume_cli.py airflow-status --dag-id resume_prepare --dag-run-id nl-demo-nl-001

# 也可以自然语言查询状态。
.venv/Scripts/python.exe airflow/resume/resume_cli.py ask "查询 resume_prepare 的 nl-demo-nl-001 运行状态"

# 把这里的示例标识换成你已经在审阅页确认的 run_key。
.venv/Scripts/python.exe airflow/resume/resume_cli.py ask "导出已确认的 my-resume-v1 版本为 Word 和 PDF" --request-id export-nl-001
```

`queued` 仅表示已经提交。继续查询直到成功/失败；`skipped` 表示材料没有需要重做的更新。准备任务日志也会打印可审阅的 `run_key`。自然语言信息不够时返回 `needs_input`，chat 中可继续补充；不支持的动作或模型非法字段会拒绝执行。仅支持整理、导出已确认版本、查询运行；调度变更仍使用配置。

导出请求不会替你执行“确认正文”。缺少确认或确认后有改动，程序会在调用 Airflow 前拒绝，DAG 内也会再验证。导出成功仍需查看 PDF 页面做最终视觉验收。

自然语言入口会向 DeepSeek 发送请求文本、现有案例标识和当前会话最近几条上下文；不会发送目录中的材料正文。真正执行 deepseek 整理时发送提取文字的范围沿用第 2 节说明。

接口依据：[Airflow 3 API 认证](https://airflow.apache.org/docs/apache-airflow/3.3.2/security/api.html)、[触发请求定义](https://github.com/apache/airflow/blob/3.3.2/airflow-core/src/airflow/api_fastapi/core_api/datamodels/dag_run.py)、[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)。实际结果见 [11 月 4 日验证记录](VERIFICATION-20261104.md)。
