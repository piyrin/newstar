import json
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid
import runner
import resume_guard

class GuardCorrection(unittest.TestCase):
    def response(self,status):
        out=runner.BASE/'offline-tests'/str(uuid.uuid4());out.mkdir(parents=True)
        p=out/'skill'
        answer={'status':status,'artifact':'name,session\n','limitations':[]}
        runner.save(p.with_suffix('.response.json'),{'choices':[{'message':{'content':json.dumps(answer)}}],'usage':{}})
        return p,answer

    def test_accepts_valid_short_csv_without_changing_model_output(self):
        p,expected=self.response('done')
        with patch.object(resume_guard,'OriginalWorker',side_effect=RuntimeError('unsupported or empty deliverable: []')):
            answer,_=resume_guard.corrected_worker(None,None,None,None,None,p)
        self.assertEqual(answer,expected)
        self.assertTrue(p.with_suffix('.guard-correction.json').exists())

    def test_does_not_override_actual_unsupported_status(self):
        p,_=self.response('unsupported')
        with patch.object(resume_guard,'OriginalWorker',side_effect=RuntimeError('unsupported or empty deliverable: []')):
            with self.assertRaises(RuntimeError):resume_guard.corrected_worker(None,None,None,None,None,p)

    def test_replay_only_relocates_paths_even_inside_json_strings(self):
        old=Path('C:/experiment/old');new=Path('C:/experiment/new')
        value={'text':json.dumps({'path':str(new/'A001.csv')}),'fact':120}
        expected={'text':json.dumps({'path':str(old/'A001.csv')}),'fact':120}
        self.assertEqual(resume_guard.relocate(value,new,old),expected)

if __name__=='__main__':unittest.main()
