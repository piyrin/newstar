"""Narrow checks for observed invented claims, alongside full semantic/content review."""
import re


def release_fact_issues(facts,selected):
    if not {'quickstart','feedback_fields'}<=facts.keys():return []
    issues=[];feature_text=' '.join(facts.get('features',[]))
    def add(ident,index,line,kind,reason):
        issues.append({'reference_id':ident,'line':index,'quote':line,'kind':kind,'reason':reason})
    def asserted(line,match):
        context=line[max(0,match.start()-18):match.end()]
        return not re.search(r'不是|并非|未确认|未知|不支持|建议|未来|\bnot\b|unknown|proposed|suggest',context,re.I)
    for ident,ref in selected.items():
        for index,line in enumerate(ref.get('content','').splitlines(),1):
            port_text=re.sub(r'[*_`]', '', line)
            port=re.search(r'(?:默认(?:监听)?端口\s*(?:为|是|[:：|])?\s*|default\s+port\s*(?:is|[:：|])?\s*)(\d+)',port_text,re.I)
            if port and asserted(port_text,port) and str(facts.get('default_port'))!=port[1]:
                add(ident,index,line,'unprovided_default_port','给定命令显式指定端口，不证明软件默认端口；默认值未提供，不可声称。')
            tags=re.search(r'(?:支持[^\n]{0,35}(?:标签|tags)[^\n]{0,35}(?:搜索|检索|search)|(?:按|by)[^\n]{0,25}(?:标签|tags)[^\n]{0,25}(?:搜索|检索|search))',line,re.I)
            if tags and asserted(line,tags) and '标签' not in feature_text and 'tags' not in feature_text.lower():
                add(ident,index,line,'unprovided_tag_search','facts只明确按课程搜索，未提供标签搜索；不可扩充产品能力。')
            date=re.search(r'Next\s+Review\s*,\s*(\d{4}-\d{2}-\d{2})',line,re.I)
            if date and str(facts.get('next_review_date'))!=date[1]:
                add(ident,index,line,'unprovided_review_date','未提供下一复审日期，不能将模板示例日期填成事实。')
            published=re.search(r'(?:^|,)\s*Status\s*,\s*(?:已发布|published)(?:,|$)',line,re.I)
            if published and facts.get('published') is not True:
                add(ident,index,line,'unprovided_published_state','只制作本地材料，没有提供已发布状态或实际发布证据。')
            public=re.search(r'feedback[^.\n]{0,100}(?:considered|is|are)[^.\n]{0,30}\bpublic\b',line,re.I)
            if public and asserted(line,public) and facts.get('feedback_policy_public') is not True:
                add(ident,index,line,'unprovided_feedback_public_policy','软件MIT许可不能替代未提供的反馈公开/隐私政策。')
    return issues
