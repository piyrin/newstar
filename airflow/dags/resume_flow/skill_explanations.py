"""Recording explanations bound to exact archived files and line numbers."""
import csv
from .storage import inside, file_hash


def excerpt(target, report, suffix, needle, label, radius=2):
    candidates = [item for item in report['files'] if item['name'].endswith(suffix)]
    for item in candidates:
        path = inside(target, item['name'])
        if not path.is_file() or file_hash(path) != item['sha256']:
            return {'label': label, 'verified': False, 'error': '原文件缺失或摘要变化，请重新核验'}
        lines = path.read_text(encoding='utf-8-sig').splitlines()
        match = next((i for i, line in enumerate(lines) if needle in line), None)
        if match is not None:
            return {'label': label, 'verified': True, 'name': item['name'],
                'sha256': item['sha256'], 'line': match + 1,
                'lines': [{'number': i + 1, 'text': lines[i], 'focus': i == match}
                          for i in range(max(0, match - radius), min(len(lines), match + radius + 1))]}
    return {'label': label, 'verified': False, 'error': '归档文件中未找到指定原句，请重新核验'}


EXAMPLES = {
    'e4cac5475d144e79922e85a309a4803f': {
        'title': '默认端口与支持范围断言错误', 'verdict': '内容复核未通过第1、4、6项',
        'standard': '只确认facts列出的功能与限制。default_port=null，显式指定4177无法确定默认值。各份终稿须保持事实一致。',
        'reason': 'STEP-001第25至27行的三项功能、第37至39行的三项限制和版本许可符合facts，但第29行把所有未列出的能力都排除在支持范围外，扩大了限制。STEP-002第21、31行的命令准确，第51行却把未知默认端口写成“不是默认值”。实际CSV只有一行四列表头。STEP-004第3、40至50、62至73行明确标注建议并给出流转、职责与建议时限，但第105行声称上游没有把4177当作默认端口，与STEP-002的否定断言及STEP-001第69行的未知口径不一致。本次按六项标准为未通过、通过、通过、未通过、通过、未通过。',
        'speech': '这次四个交付文件已经提前逐份复核。命令和CSV通过，反馈方案明确标为建议。问题在功能说明将未列出的能力统一排除，上手说明又把未知默认端口写成不是默认值。后续文档未正确反映上游断言，因此本次内容复核未通过。',
        'evidence': [('case.json', '"default_port"', '原始事实 · 默认端口未知'),
                     ('STEP-001.md', '未列出的能力不在本版本的支持范围内', '功能说明第29行 · 扩大限制'),
                     ('STEP-002.md', '不是默认值', '上手说明第51行 · 默认端口否定断言'),
                     ('STEP-003-1.csv', 'issue_id,course,description,status', '实际CSV · 四列表头'),
                     ('STEP-004.md', '未将其当作安装命令、默认端口或服务 URL', '建议方案第105行 · 上游一致性说明')]},
    '9b8f3372659244daa71c3a182b3394f7': {
        'title': '默认端口断言错误', 'verdict': '内容复核未通过第4、6项',
        'standard': 'default_port=null，只知道命令显式传入--port 4177，默认值与4177的关系保持未知。',
        'reason': '本次实际N180、K3、4个业务节点、最长链2。DOC-002第27行把4177写成“不是默认端口”，DOC-004第122行继续沿用该断言。原facts没有默认端口信息，因此本次归档完成后，内容复核仍判未通过。',
        'speech': '这次是我从网页提交的真实单次演示。180个候选中实际调用3种Skill，生成4个业务节点，最长链2。Airflow五步和自动核验已经完成。继续对照终稿发现，默认端口未知却被写成4177不是默认端口，因此这次内容复核未通过。接下来我打开已经复核正确的样例，展示六项标准如何全部满足。',
        'evidence': [('case.json', '"default_port"', '原始事实 · 默认端口未知'),
                     ('STEP-002.md', '**不是**默认端口', 'DOC-002第27行 · 问题断言'),
                     ('STEP-004.md', '非默认端口', 'DOC-004第122行 · 后续沿用')]},
    'history-local-32768-170-1': {
        'title': 'N170 · 输入超出上下文容量', 'verdict': '输入34162 tokens，超过32768容量',
        'standard': '本地这组固定32768上下文，输入包含候选工具、历史消息和读取的全文。',
        'reason': '该次请求随历史和引用读取增长到34162 tokens，服务返回HTTP400。另两次N170分别发生内容错误与输出容量耗尽，因此该组三次均未通过，机制各有记录。',
        'speech': '这个170候选样例的失败原因直接写在原始错误里，输入34162超过32768。170这一组三次都未通过，但具体原因分别是输入超限、内容错误和输出空间耗尽。我把机制和数量观测一起报告。',
        'evidence': [('summary.json', '34162', '原始超限错误')]},
    'history-local-32768-5-2': {
        'title': 'N5 · 功能与限制扩写错误', 'verdict': '未通过第1、4项内容标准',
        'standard': '原facts只给出材料留在本机和不支持PDF OCR。联网要求、一般PDF文本处理能力均未给出。',
        'reason': '“无需联网”补出了网络要求的否定结论。“无法直接处理PDF文件”又把PDF OCR不支持扩大为一般PDF文件处理不支持。该次自动通过，内容复核否决。',
        'speech': '这里先看原始事实，只说明材料留在本机和不支持PDF OCR。再看终稿第38、45行，模型写成无需联网、无法直接处理PDF。这两条超出给定事实，所以我把这次记为内容失败。它只有5个候选，说明内容失败在小规模也会发生。',
        'evidence': [('case.json', '"privacy"', '原始事实'),
                     ('case.json', 'PDF OCR', '原始事实 · 明确不支持PDF OCR'),
                     ('STEP-005.md', '无需联网', '问题原句 · DOC-005'),
                     ('STEP-005.md', '无法直接处理 PDF', '问题原句 · PDF能力范围'),
                     ('content-review-20261111.json', 'DOC-005:L38', '原内容复核定位')]},
    'history-local-32768-60-3': {
        'title': 'N60 · 修订后的引用错误', 'verdict': '未完成正式提交，16轮规划预算耗尽',
        'standard': '反馈CSV只允许issue_id、course、description、status四列表头，无数据行。修订后提交清单须指向正确版本。',
        'reason': '旧CSV的第二行“,,,,”会解析成5个空字段。STEP-007已经生成只有表头的正确新文件，但最后一次审查清单仍含DOC-001至DOC-006，这些文档隐含的旧CSV继续被校验并报错。运行最后没有正式manifest。',
        'speech': '这里对照旧文件和修订文件。旧CSV第二行有4个逗号，解析成5列，表头只有4列。新文件已经修好，但审查清单还保留旧文档，它们附带的错误CSV也进入校验。后面审查仍未通过，16轮用完，所以新文件生成并没有让完整任务成功。',
        'evidence': [('STEP-001-3.csv', ',,,,', '旧CSV · 第二行5列'),
                     ('STEP-007-raw.csv', 'issue_id,course,description,status', '修订CSV · 只有表头'),
                     ('control-calls.json', '"DOC-007"', '最后一次审查仍包含旧文档', 10),
                     ('summary.json', 'planner budget exhausted', '执行终点 · 预算耗尽')]},
    'history-local-32768-170-2': {
        'title': 'N170 · 未知服务地址补造', 'verdict': '自动通过，内容复核未通过第4、6项',
        'standard': '原facts中service_url和web_management_ui均为null。给定serve命令只明确--port 4177。',
        'reason': '终稿一面承认URL未知，一面指示访问http://localhost:4177，补造了协议、主机和可访问入口。F检查遗漏“访问”措辞，独立G副本增加了该措辞的检出。',
        'speech': '先看service_url为null。终稿第42行却让读者访问localhost地址，端口参数无法证明这个URL。自动审查放过了它，我按未知保持未知这条标准判失败。后续G改进能检出同一句，但整体任务正确率收益还需要新对照。',
        'evidence': [('case.json', '"service_url"', '原始事实 · 服务地址未知'),
                     ('STEP-002.md', '请直接访问本地服务地址', '终稿第42行 · 具体地址断言'),
                     ('content-review-20261112.json', 'DOC-002:L42', '内容复核定位')]},
    'history-local-40960-166-1': {
        'title': '40k · 后续输入再次超限', 'verdict': '运行输入41226 tokens，超过40960容量',
        'standard': '当前配置的上下文容量为40960 tokens，每次请求必须容纳目录、消息历史与本次输入。',
        'reason': '增加容量让前面的失败位置继续执行，该完整任务随后生成8个节点、最长链4，历史继续增长后再次超限。100与166的40k完整任务各1/3正确。',
        'speech': '容量改为40k后，前面可以继续，但这条完整任务后来输入增长到41226，仍超过40960。这里有8个业务节点、最长链4。我能证明这次恢复是局部的，当前数据没有显示完整任务正确率提升。',
        'evidence': [('summary.json', '41226', '原始HTTP400错误与输入容量')]},
    'history-context-controls-20261112': {
        'title': '容量改进与审查改进的直接证据', 'verdict': '同一32849-token输入，32k两次失败、40k两次返回',
        'standard': '容量对照固定原输入、模型、seed与采样，仅改变options.num_ctx。G测试固定同一错误原句，检查F/G的检出差异。',
        'reason': '32k请求报32849大于32768。40k返回原生审阅工具调用。这组只检验当前请求能否继续。G对同一历史错误句从0项检出变为1项检出，两项改进的整体业务收益仍待完整受控测量。',
        'speech': '这组固定同一输入，只增加上下文容量。两次32k都报错，两次40k都返回审阅调用，所以这一步容量故障可以恢复。下面G的原句回归又显示旧检查漏掉的地址现在能检出。完整任务的结果还要结合40k后续超限样例解释。',
        'evidence': [('ctx32768-r1/summary.json', '32849', '32k第1次 · 原错误'),
                     ('ctx32768-r2/summary.json', '32849', '32k第2次 · 原错误'),
                     ('ctx40960-r1/summary.json', '32849', '40k第1次 · 实际输入'),
                     ('ctx40960-r2/summary.json', '32849', '40k第2次 · 实际输入'),
                     ('historical-line-reproduction.json', '"f": []', 'G原句回归 · F漏检与G检出', 6)]},
    'deepseek-20261113-n100-07': {
        'title': 'DeepSeek · 默认端口断言错误', 'verdict': '自动通过，内容复核未通过第4项',
        'standard': 'default_port=null，只知道命令显式传入--port 4177。默认值与4177的关系保持未知。',
        'reason': '“4177不是默认端口”断言默认值与4177不同，原facts没有这个信息。保留“无法据此确定默认端口”才能符合原标准。',
        'speech': '这里default_port是null。模型知道命令写了4177，却又写4177不是默认端口。未知无法推出不相等，因此即使自动通过，我仍把这次判为内容失败。',
        'evidence': [('case.json', '"default_port"', '原始事实 · 默认端口未知'),
                     ('STEP-002.md', '4177 不是默认端口', '终稿问题原句')]},
    'deepseek-20261113-n180-08': {
        'title': 'DeepSeek · 安装方式断言错误', 'verdict': '自动通过，内容复核未通过第4项',
        'standard': 'installation_command=null，安装方式未知。',
        'reason': '终稿把安装方式未知写成pip、uv等均不适用。未知无法证明这些方式不可用。',
        'speech': '原facts没有安装命令。终稿第17行却排除pip、uv，这把未知写成了否定结论，所以我按第4项判失败。180候选在这一批也有正确任务，当前观察到的是内容错误，数量稳定失败点还没有测出。',
        'evidence': [('case.json', '"installation_command"', '原始事实 · 安装命令未知'),
                     ('STEP-002.md', '均不适用', '终稿第17行 · 安装方式否定')]},
    'deepseek-20261113-n100-09': {
        'title': 'DeepSeek · 建议规则冲突', 'verdict': '内容复核未通过第5、6项',
        'standard': '用户要求给出可用、明确标为建议、跨文档一致的反馈流转方案。',
        'reason': '同一方案第2节把new直接closed是否允许留待决定，第3节却直接允许这个跳转。读者无法从同一方案得到一致的操作规则。',
        'speech': '建议本身可以设计，但规则要一致。这里前面说new直接closed需项目方决定，后面的步骤表却允许直接closed。这是同一建议方案的规则冲突，因此这次也没有计入正确。',
        'evidence': [('STEP-004.md', '需由项目方决定', '第2节 · 直接关闭尚待决定'),
                     ('STEP-004.md', '可直接更新为 `closed`', '第3节 · 已允许直接关闭')]},
}


def explain(target, record, report):
    example = EXAMPLES.get(record['job_id'])
    if example:
        evidence = [excerpt(target, report, *probe) for probe in example['evidence']]
        return {**{k: v for k, v in example.items() if k != 'evidence'}, 'evidence': evidence,
                'verified': all(item['verified'] for item in evidence)}
    if record['job_id'] in ('3df8e6e13ec348f886e6889007ead0d4',
                             'deepseek-20261113-n100-03', 'deepseek-20261113-n180-09'):
        final_report = {**report, 'files': [f for f in report['files'] if f['final']]}
        probes = [('MIT', '第1项 · 版本与许可'), ('课程笔记索引', '第1项 · 已知功能'),
                  ('PDF OCR', '第1项 · 已知限制'),
                  ('python -m coursedock index ./notes', '第2项 · 索引命令'),
                  ('python -m coursedock serve --port 4177', '第2项 · 启动命令'),
                  ('默认端口', '第4项 · 未知事实')]
        evidence = [excerpt(target, final_report, '.md', needle, label) for needle, label in probes]
        roles = {
            '3df8e6e13ec348f886e6889007ead0d4': ('STEP-002.md', '### 4.2 建议方案：维护职责'),
            'deepseek-20261113-n100-03': ('STEP-004.md', '## 3. 建议的维护职责分工'),
            'deepseek-20261113-n180-09': ('STEP-004.md', '## 4. 建议维护职责分工'),
        }
        evidence.append(excerpt(target, final_report, *roles[record['job_id']],
                                '第5项 · 建议职责', 8))
        csv_evidence = excerpt(target, final_report, '.csv', 'issue_id,course,description,status',
                               '第3项 · 实际CSV文件')
        evidence.append(csv_evidence)
        csv_correct = False
        if csv_evidence['verified']:
            path = inside(target, csv_evidence['name'])
            with path.open(encoding='utf-8-sig', newline='') as stream:
                rows = [row for row in csv.reader(stream) if row]
            csv_correct = rows == [['issue_id', 'course', 'description', 'status']]
        accepted = report['review']['state'] == 'accepted'
        return {'title': '六项内容复核与通过依据', 'verdict': report['review']['label'],
            'standard': '复核记录来源为Codex逐文核对，文件片段与行号对应本次归档原文。',
            'reason': report['review'].get('notes', ''),
            'speech': '我把正确分成六项检查。版本、功能限制和MIT对照原facts，两条命令逐字核对。这个CSV实际解析只有一行四列表头，没有数据行。默认端口和地址等未知项保持未知，流转和维护职责明确标为建议，最后核对文件之间一致。下方每段都来自本次真实文件。',
            'criteria': [{'title': title, 'passed': accepted and (csv_correct if i == 2 else True)}
                         for i, title in enumerate(['功能、限制、版本和许可', '两条命令逐字一致',
                             '实际CSV仅四列表头，无数据行', '未知事实保持未知',
                             '建议流转与维护职责可用', '跨文件事实一致'])],
            'evidence': evidence, 'verified': all(item['verified'] for item in evidence)}
    return {'title': '内容复核与运行证据', 'verdict': report['review']['label'],
            'standard': '按原六项标准，逐份核对正式提交文件。每项证据可从下方原文件打开。',
            'reason': report['review'].get('notes', '详细判定见本次内容审查原文件。'),
            'speech': '我先报告候选数量、实际调用种数、业务节点和最长链，再打开正式文件，按六项标准核对。',
            'evidence': [], 'verified': True}
