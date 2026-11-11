"""Narrow, versioned checks for observed unsupported release-document claims."""
import re


def extended_release_fact_issues(facts, selected):
    if 'feedback_fields' not in facts:
        return []
    issues=[]
    def qualified(line, match):
        prefix=re.split(r'[。；;，,]',line[:match.start()])[-1][-32:]
        suffix=re.split(r'[。；;，,]',line[match.end():])[0][:32]
        return not re.search(r'未提供|未给定|未说明|未确认|未知|待确认|无法|不能证明|不能保证|不证明|不代表|并非|不是|建议|未来|如有|若有|如果|假设|\bunknown\b|\bproposed\b|\bif\b',prefix+match.group(0)+suffix,re.I)
    for ident, ref in selected.items():
        for number,line in enumerate(ref.get('content','').splitlines(),1):
            found=[]
            ui=re.search(r'(?:管理界面|Web\s*(?:界面|UI)|图形界面)[^\n]{0,50}(?:导出|export)',line,re.I)
            if ui and qualified(line,ui) and not facts.get('export_ui_or_cli_entrypoint'):
                found.append(('unprovided_export_interface','给定导出能力不证明已有管理界面或具体导出入口；该入口未提供。'))
            url=re.search(r'(?:浏览器|browser)[^\n]{0,45}(?:https?://(?:localhost|127\.0\.0\.1)[^\s`)>]*|localhost:\d+)',line,re.I)
            if url and qualified(line,url) and not facts.get('service_url'):
                found.append(('unprovided_browser_url','serve命令与端口参数不证明浏览器协议、绑定地址或UI入口；service_url未知。'))
            ban=re.search(r'MIT[^\n]{0,60}(?:不修改源码分发|(?:不得|禁止|不允许|不能)\s*(?:修改源(?:代码|码)|分发修改)|(?:may not|cannot)\s+(?:modify|redistribute))',line,re.I)
            if ban and qualified(line,ban) and facts.get('license','').upper()=='MIT':
                # A negation inside the clause can explicitly reject the alleged ban.
                if not re.search(r'并非|不是|不意味着',line[ban.start():ban.end()]):
                    found.append(('unprovided_mit_restriction','给定MIT许可没有该源码修改/分发禁令；不能为许可补造限制。'))
            risk=re.search(r'(?:无|不存在)[^\n]{0,12}(?:数据|信息)[^\n]{0,10}泄露风险|(?:zero|no)\s+(?:external\s+)?(?:data\s+)?(?:leakage\s+)?risk',line,re.I)
            if risk and qualified(line,risk) and facts.get('zero_leakage_risk') is not True:
                found.append(('unprovided_zero_risk_guarantee','本地留存不能支持零泄露风险保证；该保证未由facts提供。'))
            for kind,reason in found:
                issues.append({'reference_id':ident,'line':number,'quote':line,'kind':kind,'reason':reason})
    return issues
