# 排版工具来源

`build_resume.py` 与 `check_resume.py` 于 2026-11-03 从用户本机的 `resume-maker/scripts/` 复制，作为该 Skill 在 Airflow 中的可执行集成。原工具只负责排版和文件检查，事实审阅、来源追溯与用户确认由 `resume_flow` 实现。运行不依赖技能安装目录。

三种版式是本机 Skill 自有预设，不是第三方模板镜像。字体通过经确认的 JSON 配置为容器提供的 Noto Sans CJK SC；不修改原技能中的文件或存入个人数据。
