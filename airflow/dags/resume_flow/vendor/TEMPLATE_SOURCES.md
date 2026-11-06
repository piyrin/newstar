# 简历版式来源与约定

本项目的 `classic`、`minimal`、`technical` 是可编辑 DOCX 版式及网页预览。2026-11-05 按用户提供的三张截图重建布局，图中的人物、姓名、联系方式与经历仅作排版参考。

早期版式曾参考以下职业中心的信息层级，当前三套布局以用户截图为依据。

- [Harvard College Bullet Point Resume Template](https://careerservices.fas.harvard.edu/resources/bullet-point-resume-template/)：提供 Word、可访问 Word 与 Google Docs 模板入口。
- [MIT CAPD Sample resumes](https://capd.mit.edu/resources/sample-resumes/)：提供不同年级、职业方向的样例，其中包括含项目经历的本科生简历。

实现差异：

| 标识 | 版式 | 文字阅读顺序 |
| --- | --- | --- |
| classic | 图一“细线标题”，左侧照片与姓名、右侧双列基本信息、全宽正文和栏目细横线 | 抬头、联系信息、原始栏目顺序 |
| minimal | 图二“灰条标题”，相同抬头、灰底栏目条与黑色左竖线、全宽正文 | 抬头、联系信息、原始栏目顺序 |
| technical | 图三“浅色卡片”，照片与姓名在顶部、联系信息标签、浅色技能区、蓝灰文字和左竖线标题 | 抬头、联系信息、原始栏目顺序 |

三种版式都支持可选照片与空联系方式，保留 `sections`、条目、段落和亮点的原有顺序。条目支持名称、职责和日期同排，过长时换行。纸质模式保留可抄写地址，电子模式保留超链接。Word/PDF 的浅色卡片以可编辑表格底色实现，边角为矩形，网页采用圆角。最终分页由同一份生成 DOCX 导出的 PDF 决定。

当前模板版次为 `reference-20261105-v1`。人工确认摘要绑定此版次，模板升级后需要重新确认。冻结的导出输入记录模板版次，旧冻结版本重新生成时会要求新确认和新导出标识。

网页 DOM 契约：`.paper.<template>` 下为 `.resume-header`（内含 `.resume-identity` 和 `.resume-contact`）、`.resume-body`（内含按原序排列的 `.resume-section`）；姓名为 `h3`，栏目为 `h4`，联系信息段落为 `.contact`，岗位为 `.headline`。`template.css` 需在 `style.css` 之后加载。
