# Skill 实验工作台与 Airflow 接入

在第一次实验的 8765 工作台增加 `/skills`，通过现有 Airflow API 触发 `skill_experiment`。

## 使用入口

- 工作台 `http://localhost:8765/skills`
- 本次真实验收 `http://localhost:8765/skills?job_id=3df8e6e13ec348f886e6889007ead0d4`
- 对应 Airflow `http://localhost:8080/dags/skill_experiment/runs/skill-3df8e6e13ec348f886e6889007ead0d4`

本次运行于 2026 年 11 月 12 日从真实浏览器提交，Airflow 五个任务全部成功。完整运行耗时 9 分 35 秒，实际 N166、K2、2 个业务节点、最长链 2 个节点。10 条全新本机模型回复、0 条重放、0 次新增付费 API 调用。最终正文与 CSV 经逐项内容检查，网页预览、实际下载、复核保存与重新打开均已实测。

## 启动

在项目根目录执行以下命令，使用已有 Docker Desktop 与 Compose 配置。

```powershell
Set-Location D:\code\newstar
& 'D:\docker\anzhuang\DockerDesktop\resources\bin\docker.exe' compose -f airflow/docker-compose.yaml -f airflow/docker-compose.resume.yaml up -d
& .\experiments\skill_portal\start_bridge.ps1
```

执行桥在 Windows 后台单并发运行，页面显示心跳。电脑重启后需再次启动执行桥。桥已在线时启动脚本直接返回。

2026年11月12日录制前复核确认八项Compose服务健康、DAG导入错误为空、执行桥在线。Ollama曾停止，已按原配置恢复，并核对0.33.1版本、模型摘要及32k/GPU24/seed3短推理。重新验收记录见 `docs/第二次任务今晚提交核对与填写稿-20261112.md` 第七节。

### 恢复已停止的Ollama

若电脑重启后模型服务离线，可在项目根目录执行以下已实测的后台启动方式。日志以二进制追加写入原文件。

```powershell
@'
import os, pathlib, subprocess, urllib.request
root = pathlib.Path.cwd()
try:
    with urllib.request.urlopen('http://127.0.0.1:11434/api/version', timeout=3) as response:
        print('Ollama online', response.read().decode())
except OSError:
    env = os.environ.copy()
    env.update(OLLAMA_HOST='127.0.0.1:11434', OLLAMA_MODELS=r'D:\ollama\models',
               OLLAMA_NO_CLOUD='1', OLLAMA_FLASH_ATTENTION='1',
               OLLAMA_KV_CACHE_TYPE='q8_0', OLLAMA_NUM_PARALLEL='1')
    logs = root / 'tmp/skill-boundary-local'
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / 'ollama-stdout.log').open('ab', buffering=0) as stdout:
        with (logs / 'ollama-stderr.log').open('ab', buffering=0) as stderr:
            process = subprocess.Popen([r'D:\ollama\app\ollama.exe', 'serve'],
                env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
    print('Ollama started, PID', process.pid)
'@ | .\.venv\Scripts\python.exe -X utf8 -
```

启动后用以下命令确认版本和已安装模型，再使用工作台。

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/version
(Invoke-RestMethod http://127.0.0.1:11434/api/tags).models | Select-Object name,digest
```

依赖当前工作区已有的 `deliverables/skill-boundary-ten-trial-repro-20261111/` 目录、Ollama 0.33.1、原 qwen3.5:9b digest 和实时服务日志。运行前验证冻结包、实际加载的全部 F 源码、166 份不同原源及本地模型身份。DeepSeek 使用已有本机 `.env` 配置，网页发起时需明确确认本次 API 费用。此次集成验收使用本地模型。

## 网页操作

1. 从原简历工作台点击“第二次实验 · Skill 自主编排”，或直接进入 `/skills`。
2. 保留原完整需求，选择 100/166/180 个候选、模型及本地 seed，点击“提交到 Airflow”。编辑需求后仍使用页面展开区显示的固定 facts 与六标准，该次作为独立新运行归档。
3. 查看同一运行的五个 Airflow 任务状态，点击对应链接进入 Airflow。
4. 完成后查看实际 Skill 调用依赖、N/K/节点/链长、自动结果和最终文件。
5. 预览或下载正文与 CSV，逐项核对六标准，保存带说明的复核记录。
6. 在历史筛选中查看原本地与 DeepSeek 十次结果。新运行与注入异常用例单独保存。

## 执行结构

```text
Web /skills
  → Airflow validate_request
  → dispatch_to_host 写共享队列
  → execute_skills reschedule sensor 等待
      Windows bridge → 冻结 F 运行器 → Ollama / 已确认费用的 DeepSeek
  → verify_artifacts 校验实际引用、正文及附件 SHA
  → publish_results
  → Web 查看、下载、六项复核
```

共享目录为 `airflow/resume_workspace/skill_experiments`，沿用现有 Compose 挂载。所有层共用一个 `job_id`。平台五个任务承担调度与归档，模型内部的实际 Skill 图由原生调用及不可变引用记录产生。

同一次提交使用幂等请求标识。桥用进程锁和持久 claim 避免重复推理，重启时核对存活子进程。执行失败保存错误和部分实文件，部分文件以非终稿身份提供受路径与哈希校验的预览下载。Windows/Docker 共享目录的短暂重命名冲突进行有界重试。

## 验收记录

`output/skill-airflow-web/verification.json` 保存真实运行与文件核验，`browser-verification.json` 保存真实浏览器下载、复核恢复和跨运行隔离检查，PNG 保存实际页面。原始模型请求、回复和文件保存在同一 job 目录。

`integration-negative-20261112` 与 `integration-partial-negative-20261112` 为明确标注的注入异常用例，均未调用模型。Airflow 中 `verify_artifacts` 失败并阻断 `publish_results`。后一用例还验证了中断诊断附件的网页预览与下载。它们不加入原十次分母。

另有 `integration-torn-dag-20261112` 桥恢复用例，手工构造截断 DAG 和已退出进程状态，验证损坏原文仍可下载，桥恢复后继续在线。该用例也未调用模型。

复核记录中的 Codex 集成验收说明保留了逐项检查依据，供本人录屏前再次核对。本人同步口播、视频上传及课程表单仍按实际完成情况填写。

## 2026年11月13日修复与新增测量

URL网络错误与Airflow状态传递已修复，正向网页提交及失败阻断均已实测。工作台新增基础档、进阶档的录屏点击路线和口播文本，多档历史记录、失败定位、容量与G审查改进证据可以直接预览。新增DeepSeek 100与180候选各十次，最终内容正确分别2/10和3/10，歧义包含在分母。详细口径与协议元数据更正见 `docs/Skill网页修复与DeepSeek补测-20261113.md`。

离线复查本轮20次完整任务可运行 `.\.venv\Scripts\python.exe -X utf8 experiments/skill_portal/verify_batch.py`，无新增模型调用。
