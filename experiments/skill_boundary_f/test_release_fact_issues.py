import unittest
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock
from release_fact_issues import release_fact_issues


class SuppliedReleaseFacts(unittest.TestCase):
    def setUp(self):
        self.facts={'quickstart':['python -m coursedock serve --port 4177'],'features':['按课程搜索'],
            'feedback_fields':['issue_id','course','description','status'],'license':'MIT'}

    def issues(self,text,facts=None):
        return release_fact_issues(facts or self.facts,{'DOC-1':{'content':text}})

    def test_explicit_port_does_not_prove_package_default(self):
        self.assertTrue(self.issues('启动服务（默认端口 4177）'))
        self.assertTrue(self.issues('- **默认端口**: 4177 (通过 `--port` 参数指定)'))
        self.assertTrue(self.issues('| **默认端口** | `4177` |'))
        self.assertFalse(self.issues('- **默认端口**: 未知；给定命令指定4177。'))
        self.assertFalse(self.issues('按给定命令指定端口4177；默认端口未知。'))
        self.assertFalse(self.issues('不是默认端口4177；命令显式指定该端口。'))
        self.assertFalse(self.issues('Default port:4177',{**self.facts,'default_port':4177}))

    def test_does_not_turn_suggestions_or_limitations_into_asserted_features(self):
        self.assertTrue(self.issues('课程搜索支持按课程名称、标签或内容片段快速检索。'))
        self.assertFalse(self.issues('未确认是否支持标签搜索；不要宣称支持。'))
        self.assertFalse(self.issues('建议在未来评估标签搜索，目前仅确认按课程搜索。'))

    def test_known_unprovided_metadata_and_public_policy_are_rejected(self):
        self.assertTrue(self.issues('Next Review,2025-02-01,Status,已发布'))
        self.assertTrue(self.issues('All feedback data is considered public under the MIT license.'))
        self.assertFalse(self.issues('维护流程为建议，状态待确认；反馈保留在本机。'))

    def test_real_review_gate_exposes_the_issue_and_does_not_accept_a_semantic_pass(self):
        from progressive import suite,evaluate_delivery,review_diagnostics
        with TemporaryDirectory() as directory:
            root=Path(directory);case=suite('release')[0]
            body='默认端口4177\n'+'\n'.join(case['facts']['quickstart'])+'\n```csv\nissue_id,course,description,status\n```'
            doc=root/'draft.md';doc.write_text(body,encoding='utf-8')
            csv=root/'feedback.csv';csv.write_text('issue_id,course,description,status\n',encoding='utf-8')
            selected={'DOC-1':{'path':str(doc),'content':body,'artifact':body,'files':[{'path':str(csv),'format':'csv','sha256':hashlib.sha256(csv.read_bytes()).hexdigest()}]}}
            api=Mock();hard,verdict=evaluate_delivery(api,case,selected,root/'review',strict_release_facts=True,short_circuit_hard_failure=True)
            self.assertFalse(hard['no_observed_unprovided_release_claims']);api.call.assert_not_called()
            self.assertIn('not_evaluated',verdict)
            self.assertTrue((root/'review/release-fact-issues.json').exists())
            self.assertTrue(any('指定端口' in x for x in review_diagnostics(hard)))


if __name__=='__main__':unittest.main()
