import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from runner import save
from local_api import LocalAPI
from resume_local import ReplayLocalAPI


class LocalContinuationTests(unittest.TestCase):
    def test_exact_request_replayed_and_changed_request_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);origin=root/'old';target=root/'new'
            api=ReplayLocalAPI(origin,target)
            messages=[{'role':'user','content':str(origin/'artifacts'/'STEP-001.md')}]
            body=api.build_request(messages)
            response={'choices':[{'message':{'role':'assistant','content':'unchanged'},'finish_reason':'stop'}],'usage':{}}
            save(origin/'planner-00.request.json',body);save(origin/'planner-00.response.json',response)
            with patch.object(LocalAPI,'call',side_effect=AssertionError('must not call model')):
                msg,_=api.call([{'role':'user','content':str(target/'artifacts'/'STEP-001.md')}],target/'planner-00')
                self.assertEqual(msg['content'],'unchanged')
                with self.assertRaisesRegex(ValueError,'request mismatch'):
                    api.call([{'role':'user','content':'different choice'}],target/'planner-00')
            self.assertEqual(api.replayed_calls,1)

    def test_old_request_without_complete_response_is_not_rerolled(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);origin=root/'old';target=root/'new';api=ReplayLocalAPI(origin,target)
            save(origin/'planner-00.request.json',api.build_request([]))
            with patch.object(LocalAPI,'call',side_effect=AssertionError('must not reroll')):
                with self.assertRaisesRegex(ValueError,'incomplete saved call'):
                    api.call([],target/'planner-00')

if __name__=='__main__':unittest.main()
