"""Export only positive smoke tests also accepted by explicit direct inspection."""
import argparse
from pathlib import Path
from runner import read,save
from local_qualification import extend_registry
from boundary_scan import validate_extension


def export(batch,review_file,output):
    original=read(batch/'original.json');ledger=read(batch/'ledger.json')
    candidates=read(batch/'candidates.json')[:ledger['completed']]
    reviews=read(review_file)['reviews'];accepted=[];excluded=[];pending=[]
    for row in candidates:
        summary=batch/row['tool_name']/'summary.json';proof=read(summary);name=row['tool_name'];r=reviews.get(name)
        if not r:pending.append(name);continue
        if r.get('source_sha256')!=row['sha256'] or r.get('artifact_sha256')!=proof.get('artifact_sha256'):
            raise ValueError('review does not match immutable source/artifact: '+name)
        if r['decision']=='exclude':excluded.append(name);continue
        if r['decision']!='include':raise ValueError('unknown review decision')
        accepted.append({**row,'local_qualification_evidence':str(summary.resolve()),'artifact_sha256':proof['artifact_sha256'],
            'agent_review_evidence':str(review_file.resolve())})
    rows=extend_registry(original,accepted);validate_extension(original,rows);save(output,rows)
    report={'original':len(original),'automatic_new':ledger['passed'],'reviewed_new':len(accepted),
        'excluded':excluded,'pending_review':pending,'total':len(rows),'registry':str(output.resolve())}
    save(output.with_suffix('.review-summary.json'),report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--batch',required=True,type=Path);p.add_argument('--reviews',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);a=p.parse_args();print(export(a.batch,a.reviews,a.output))
