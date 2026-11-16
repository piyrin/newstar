import unittest
import uuid
from audit_progressive import observed_stages
from runner import BASE,save

class PartialEvidenceSnapshot(unittest.TestCase):
    def test_planned_empty_stage_is_not_treated_as_completed_evidence(self):
        root=BASE/'offline-tests'/str(uuid.uuid4());root.mkdir(parents=True)
        planned={'size':167,'passed':0,'planned':3,'results':[],'fully_passed':False}
        self.assertEqual(observed_stages(root,{'stages':[planned]},['dock'],3,True),[])

    def test_partial_success_never_becomes_a_passed_level(self):
        root=BASE/'offline-tests'/str(uuid.uuid4())
        for repeat in [1,2]:save(root/f'n010/dock-r{repeat}/summary.json',{'case':'dock','repeat':repeat,'passed':True})
        stages=observed_stages(root,{'stages':[]},['dock','ledger','club','event','recruit','competition'],2,True)
        self.assertEqual(len(stages),1)
        self.assertEqual(stages[0]['passed'],2);self.assertEqual(stages[0]['planned'],12)
        self.assertFalse(stages[0]['fully_passed']);self.assertTrue(stages[0]['pending_stage_record'])

    def test_committed_level_is_not_added_twice(self):
        root=BASE/'offline-tests'/str(uuid.uuid4())
        save(root/'n010/dock-r1/summary.json',{'case':'dock','repeat':1,'passed':True})
        stages=observed_stages(root,{'stages':[{'size':10,'results':[]}]},['dock'],2,True)
        self.assertEqual(len(stages),1)

if __name__=='__main__':unittest.main()
