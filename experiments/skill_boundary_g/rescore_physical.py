"""Check historical passed trials against the additional physical CSV safeguards."""
import argparse
from runner import BASE,read,save
from progressive import physical_checks


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prefix',required=True);args=parser.parse_args()
    root=BASE/'progressive'/args.prefix;ledger=read(root/'series.json');stages=[]
    for stage in ledger['stages']:
        results=[]
        for old in stage['results']:
            checks={}
            if old['passed']:
                folder=root/('n%03d'%stage['size'])/(old['case']+'-r'+str(old['repeat']))
                refs={r['reference_id']:r for n in read(folder/'dag.json') for r in read(folder/'artifacts'/(n['id']+'.json'))['outputs']}
                selected={i:refs[i] for d in read(folder/'manifest.json')['deliverables'] for i in d['reference_ids']}
                checks=physical_checks(read(folder/'case.json'),selected,check_csv_shape=True,strict_feedback_csv=True)
            passed=old['passed'] and bool(checks) and all(checks.values())
            results.append({'case':old['case'],'repeat':old['repeat'],'original_passed':old['passed'],
                'upgraded_physical_checks':checks,'effective_passed':passed})
        stages.append({'size':stage['size'],'planned':stage['planned'],'completed':len(results),
            'effective_passed':sum(r['effective_passed'] for r in results),
            'effective_fully_passed':len(results)==stage['planned'] and all(r['effective_passed'] for r in results),'results':results})
    report={'source':str(root),'new_model_calls':0,'original_results_unchanged':True,'stages':stages}
    save(root/'upgraded-physical-recheck.json',report)
    print([{'N':s['size'],'passed':s['effective_passed'],'planned':s['planned'],'fully_passed':s['effective_fully_passed']} for s in stages])


if __name__=='__main__':main()
