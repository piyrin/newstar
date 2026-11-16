"""Recheck immutable single-case results; never generate or repair business data."""
import argparse
from feedback_csv import feedback_csv_issues
from runner import BASE,read,save


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prefix',default='local-single-receipts-native-a');args=parser.parse_args()
    folder=BASE/'progressive'/args.prefix
    if read(folder/'protocol.json').get('full_task_family') is not False:raise ValueError('single-case series only')
    original=folder/'automatic-series-before-review.json'
    ledger=read(original if original.exists() else folder/'series.json');results=[]
    for stage in ledger['stages']:
        result=stage['results'][0];trial=folder/('n%03d'%stage['size'])/(result['case']+'-r'+str(result['repeat']))
        issues=[]
        if result['passed']:
            nodes=read(trial/'dag.json')
            refs={r['reference_id']:r for node in nodes for r in read(trial/'artifacts'/(node['id']+'.json'))['outputs']}
            selected={i:refs[i] for d in read(trial/'manifest.json')['deliverables'] for i in d['reference_ids']}
            issues=feedback_csv_issues(read(trial/'case.json')['facts'],selected)
        results.append({'size':stage['size'],'automatic_passed':result['passed'],'effective_passed':result['passed'] and not issues,'issues':issues})
    save(folder/'strict-feedback-csv-recheck.json',{'status':'original artifacts rescored; no new model calls','results':results})
    review=read(folder/'effective-review.json') if (folder/'effective-review.json').exists() else {}
    review.update(invalidated_sizes=[r['size'] for r in results if not r['effective_passed']],
        effective_passing_sizes=[r['size'] for r in results if r['effective_passed']],recheck='strict-feedback-csv-recheck.json')
    save(folder/'effective-review.json',review)
    current=read(folder/'series.json');current['largest_passing_single_case_size']=max(review['effective_passing_sizes'],default=None)
    save(folder/'series.json',current)
    print([{'N':r['size'],'effective_passed':r['effective_passed'],'issues':len(r['issues'])} for r in results])


if __name__=='__main__':main()
