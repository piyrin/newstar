import json
import sys
import unittest
import uuid
from unittest.mock import patch
import probe_scale


class IndependentScaleScan(unittest.TestCase):
    def test_failed_scale_is_retained_and_not_promoted_but_larger_observation_runs(self):
        root=probe_scale.BASE/'offline-tests'/str(uuid.uuid4());root.mkdir(parents=True)
        called=[]
        def run(series,rows,case,repeat,**kwargs):
            called.append(len(rows));return {'case':case['id'],'repeat':repeat,'passed':len(rows)!=30}
        with patch.object(probe_scale,'BASE',root),patch.object(probe_scale,'ordered_registry',return_value=[{}]*40),patch.object(probe_scale,'run_one',side_effect=run),patch.object(sys,'argv',['probe','--prefix','scan','--continue-after-failure','--sizes','20','30','40']):
            probe_scale.main()
        ledger=json.loads((root/'progressive/scan/series.json').read_text(encoding='utf-8'))
        self.assertEqual(called,[20,30,40]);self.assertFalse(ledger['stages'][1]['fully_passed'])
        self.assertEqual(ledger['stages'][1]['passed'],0)
        self.assertEqual(ledger['largest_passing_single_case_size'],40)
        self.assertEqual(ledger['status'],'all_planned_single_case_probes_completed')

if __name__=='__main__':unittest.main()
