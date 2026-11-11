import unittest
from context_replay import context_variant, input_digest, classify_resource


class ExactContextControl(unittest.TestCase):
    def test_only_context_changes_and_messages_tools_sampling_stay_exact(self):
        source={'model':'local','messages':[{'role':'user','content':'完整正文'}],'tools':[{'name':'a'}],
            'options':{'num_ctx':32768,'temperature':0.2,'num_predict':1200},'stream':False}
        target=context_variant(source,40960)
        self.assertEqual(target['messages'],source['messages']);self.assertEqual(target['tools'],source['tools'])
        self.assertEqual(target['options']['num_predict'],1200)
        self.assertEqual(input_digest(source),input_digest(target))
        self.assertEqual(source['options']['num_ctx'],32768)

    def test_truncation_cannot_be_labelled_success_even_when_api_returns_stop(self):
        raw={'done':True,'done_reason':'stop','prompt_eval_count':32000,'eval_count':100}
        self.assertEqual(classify_resource(raw,'truncated = 1'),'context_failure')
        self.assertEqual(classify_resource(raw,'truncating input prompt'),'context_failure')
        self.assertEqual(classify_resource(raw,'truncated = 0'),'complete_response_without_detected_truncation')
        self.assertEqual(classify_resource({**raw,'done_reason':'length'},''),'incomplete_response')


if __name__=='__main__':unittest.main()
