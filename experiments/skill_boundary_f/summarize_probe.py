"""Render observed single-case results with scope and denominators kept explicit."""
import argparse
from pathlib import Path
from runner import BASE,REPO,read


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prefix',default='local-single-receipts-native-c')
    parser.add_argument('--confirmation',action='append',default=[]);args=parser.parse_args()
    series=BASE/'progressive'/args.prefix;ledger=read(series/'series.json');protocol=read(series/'protocol.json')
    if protocol.get('full_task_family') is not False:raise ValueError('not an exploratory single-case series')
    review=read(series/'effective-review.json') if (series/'effective-review.json').exists() else None
    invalid=set(review.get('invalidated_sizes',[])) if review else set()
    largest=ledger['largest_passing_single_case_size']
    lines=['# 本地固定任务单例逐级扩容结果','',
        '每档为同一个CourseDock发布材料任务的一次真实本地试次。这里的1/1不代表完整六类12/12，也不代表统计上已经稳定；不同配置不拼接成绩。',
        '',f"系列：`{args.prefix}`；状态：`{ledger['status']}`。",
        f"当前最大已通过的单例候选规模：**{largest if largest is not None else '尚无完成档位'}**。这是该场景的已测通过规模，不是模型普遍硬上限。",'',
        '| 候选N | 通过/计划 | 实际成功Skill种类K | 业务DAG节点 | 最长链(节点) | 读取/审阅次数 | 结果 |',
        '|---:|---:|---:|---:|---:|---:|---|']
    for stage in ledger['stages']:
        r=stage['results'][0]
        status='通过' if r['passed'] else (r.get('error') or '业务验收未过')
        passed=stage['passed']
        if stage['size'] in invalid:passed=0;status='自动误判，原始产物复核不通过'
        lines.append(f"| {stage['size']} | {passed}/{stage['planned']} | {r['actual_skills']} | {r['nodes']} | {r['chain']} | {r.get('artifact_read_calls',0)}/{r['review_calls']} | {status.replace('|','/')} |")
    if review:lines+=['','本组旧自动晋级链已因误判作废；较高档的有效产物仅作独立观察。effective-review.json与strict-feedback-csv-recheck.json保留原判及否决证据。']
    scan_rule='逐档独立记录失败与成功，失败不计通过；不把首次失败当数量硬上限。' if protocol.get('continue_after_failure') else '失败不会计为通过；下一档不在失败后自动启动。'
    lines+=['','每次均要求：至少两种真实Skill及实际依赖、实体/CSV/命令检查、可见审阅、正式提交及独立终验。'+scan_rule,
        '',f"模型：`{protocol['model']}`；上下文：`{protocol['local_context']}`；曝光：`{protocol['exposure']}`；规划：`{protocol['planner_transport']}`；产物视图：`{protocol.get('planner_artifacts','full')}`。", 
        '原文完整按需加载，所有候选原始说明同时可见。读取/审阅/提交三个控制工具不计Skill或业务节点；工人和终验读取完整实际产物。仅本地推理，没有付费API调用。',
        '',f"原始证据：`{series}`。审计以该目录`audit.json`或`audit-partial.json`为准，未完成试次不提前进入本表。",
        '', '历史完整六类实验经升级CSV规则复查：云端typed-broad-f的10档为11/12（原自动12/12撤回）；本地local-qwen-c为8/12（原9/12）。旧D/E的10档同为11/12。当前没有完整六类12/12的已确认稳定上限；本表固定单例不得替代该结论。','']
    if protocol.get('strict_feedback_csv'):lines+=['修正版逐一检查最终文档、嵌套代码片段和附件里的反馈CSV，任何虚构记录或错误字段都阻止通过；单独另交一份空模板不能绕过检查。','']
    if (series/'render-recheck').exists():
        lines[2:2]=['> 后续正确性复核：旧Ollama默认可能静默裁剪历史，下表保留原业务评分，不能据此认定全过程输入未裁剪。新truncate=false/shift=false组另列，详见《Skill边界实验补测-20261109》。','']
    if (series/'release-claims-recheck.json').exists():
        lines[2:2]=['> 追加事实核验已发现部分旧终稿含未获facts支持的默认端口等断言，原自动通过不能当最终正确性通过；首次163的原正面复核已追加撤销。最新167候选池边界扫描见《Skill边界补测阶段记录-20261109-2》。','']
    if args.confirmation:
        lines+=['## 最高规模的独立重复试验','',
            '下表的新复测均重新调用本地模型，不重放或复制旧产物。合计把原探索样例只算一次。成功率为本次端到端观测，包含上下文资源失败；不代表通用能力或长期保证。','',
            '| 候选N | 新复测通过/完成 | 连同首次探索 | 合计观测成功率 | 状态 |',
            '|---:|---:|---:|---:|---|']
        failure_notes=[]
        for prefix in args.confirmation:
            target=BASE/'progressive'/prefix;confirmed=read(target/'series.json');cp=read(target/'protocol.json')
            for field in ['model','backend','local_context','exposure','local_planner','local_sampling','local_gpu_layers','planner_artifacts','strict_feedback_csv','short_circuit_hard_failure','native_control_tools']:
                if cp.get(field)!=protocol.get(field):raise ValueError('different configuration cannot be pooled: '+field)
            if read(target/'fixtures.json')!=read(series/'fixtures.json'):raise ValueError('different task cannot be pooled')
            c=confirmed.get('confirmation')
            if not c:
                lines.append('| '+str(cp['sizes'][0])+' | 待完成 | 待完成 | 待完成 | '+confirmed['status']+' |');continue
            content_review=read(target/'content-review.json') if (target/'content-review.json').exists() else {}
            denied=[r for r in content_review.get('reviews',[]) if r.get('original_automatic_passed') is True and r.get('effective_passed') is False]
            if denied:
                upper=c['combined_passed']-len(denied)
                lines.append(f"| {c['candidate_skills']} | 复核{c['fresh_passed']-len(denied)}/{c['fresh_trials']} | 至多{upper}/{c['combined_trials']}，首次探索待内容复核 | 原自动成功率撤回 | content-review.json保留否决证据 |")
            else:
                rate=100*c['combined_passed']/c['combined_trials']
                lines.append(f"| {c['candidate_skills']} | 原自动{c['fresh_passed']}/{c['fresh_trials']} | 原自动{c['combined_passed']}/{c['combined_trials']} | 原自动{rate:.1f}% | 输入与内容复核另列，不称新严格组稳定率 |")
            failures=[{'repeat':r['repeat'],'error':r['error']} for s in confirmed['stages'] for r in s['results'] if not r['passed']]
            if failures:failure_notes+=['',f"{c['candidate_skills']}候选失败记录：`{failures}`。原始证据：`{target}`。",'']
        lines+=failure_notes
    output=REPO/'docs/Skill单例逐级扩容结果-20261109.md';output.write_text('\n'.join(lines),encoding='utf-8');print(output)


if __name__=='__main__':main()
