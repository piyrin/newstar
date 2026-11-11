"""Check every delivered feedback CSV, including nested or unexported snippets."""
import csv
import io
from pathlib import Path
import re


def placeholder(value):
    value=value.strip()
    return (not value or value.upper() in {'TBD','TODO'} or value.startswith(('待填','填写','待确认'))
        or bool(re.fullmatch(r'<[^<>]+>|\{\{[^{}]+\}\}|\[填写[^\[\]]*\]',value)))


def feedback_csv_issues(facts,selected):
    expected=facts.get('feedback_fields')
    if not expected:return []
    canonical={f.lower() for f in expected};issues=[];seen=set()
    for ident,ref in selected.items():
        sources=[(ref['path'],ref['content'])]
        for file in ref.get('files',[]):
            if file['format']=='csv':sources.append((file['path'],Path(file['path']).read_text(encoding='utf-8-sig')))
        for path,text in sources:
            key=(ident,path)
            if key in seen:continue
            seen.add(key);lines=text.splitlines();position=0
            while position<len(lines):
                line=lines[position].strip().lstrip('\ufeff')
                try:header=next(csv.reader([line],strict=True))
                except (csv.Error,StopIteration):position+=1;continue
                names=[c.strip().lower() for c in header]
                if not names or names[0] not in canonical or len(set(names)&canonical)<min(2,len(expected)):
                    position+=1;continue
                start=position;position+=1;block=[line]
                while position<len(lines) and lines[position].strip() and not lines[position].strip().startswith('```'):
                    block.append(lines[position]);position+=1
                issue={'reference_id':ident,'path':path,'header_line':start+1}
                try:rows=list(csv.reader(io.StringIO('\n'.join(block)),strict=True))
                except csv.Error as exc:
                    issues.append({**issue,'error':'invalid feedback CSV','details':str(exc)});continue
                if rows[0]!=expected:issue.update(error='feedback field order differs from facts',expected_header=expected,actual_header=rows[0])
                bad=[]
                for row_number,row in enumerate(rows[1:],2):
                    if not any(c.strip() for c in row):continue
                    acceptable=len(row)==len(expected) and all(placeholder(value) or (i==len(expected)-1 and value in facts.get('statuses',[])) for i,value in enumerate(row))
                    if not acceptable:bad.append({'row':row_number,'values':row})
                if bad:issue.update(error='feedback template contains non-placeholder data rows',data_rows=len(bad),examples=bad[:2])
                if 'error' in issue:issues.append(issue)
    return issues
