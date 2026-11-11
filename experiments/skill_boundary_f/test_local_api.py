import json
import unittest
from local_api import LocalAPI, native_messages, normalize_message

class LocalBackendContract(unittest.TestCase):
    def test_seed_can_be_paired_across_sizes_without_changing_legacy_default(self):
        messages=[{'role':'user','content':'fixed input'}]
        self.assertNotIn('seed',LocalAPI().build_request(messages)['options'])
        self.assertEqual(LocalAPI(seed=3).build_request(messages)['options']['seed'],3)
        with self.assertRaises(ValueError):LocalAPI(seed=True)
    def test_server_cannot_silently_prune_or_shift_the_supplied_history(self):
        request=LocalAPI().build_request([{'role':'user','content':'完整历史'}])
        self.assertIs(request.get('truncate'),False)
        self.assertIs(request.get('shift'),False)

    def test_gpu_headroom_is_explicit_and_does_not_change_default_requests(self):
        messages=[{'role':'user','content':'local'}]
        self.assertNotIn('num_gpu',LocalAPI().build_request(messages)['options'])
        self.assertEqual(LocalAPI(gpu_layers=24).build_request(messages)['options']['num_gpu'],24)
        with self.assertRaises(ValueError):LocalAPI(gpu_layers=-2)
    def test_qwen_recommended_sampling_is_mode_specific(self):
        api=LocalAPI(thinking='planner-worker',sampling='qwen-recommended')
        messages=[{'role':'user','content':'本地'}]
        thinking=api.build_request(messages)['options'];direct=api.build_request(messages,json_mode=True)['options']
        self.assertEqual((thinking['temperature'],thinking['top_p'],thinking['presence_penalty']),(1.0,0.95,1.5))
        self.assertEqual((direct['temperature'],direct['top_p'],direct['presence_penalty']),(0.7,0.8,1.5))
    def test_thinking_profile_leaves_json_judging_non_thinking(self):
        api=LocalAPI(thinking='planner-worker')
        messages=[{'role':'user','content':'本地测试'}]
        planner=api.build_request(messages,tools=[],max_tokens=5000)
        judge=api.build_request(messages,json_mode=True,max_tokens=1800)
        self.assertTrue(planner['think']);self.assertGreater(planner['options']['num_predict'],5000)
        self.assertFalse(judge['think']);self.assertEqual(judge['options']['num_predict'],1800)
    def test_remote_or_paid_endpoint_is_rejected(self):
        for endpoint in ['https://api.deepseek.com','http://example.com:11434','http://127.0.0.1.example.com:11434']:
            with self.assertRaises(ValueError):LocalAPI(endpoint=endpoint)

    def test_native_history_preserves_argument_objects_and_tool_names(self):
        history=[{'role':'assistant','content':None,'tool_calls':[{'id':'call-1','type':'function','function':{'name':'csv_export','arguments':'{"artifact_ids":[]}'}}]},
                 {'role':'tool','tool_call_id':'call-1','content':'真实产物'}]
        result=native_messages(history)
        self.assertEqual(result[0]['tool_calls'][0]['function']['arguments'],{'artifact_ids':[]})
        self.assertEqual(result[1]['tool_name'],'csv_export')
        self.assertEqual(result[1]['content'],'真实产物')

    def test_native_response_becomes_real_function_call_without_fabricating_content(self):
        msg=normalize_message({'role':'assistant','content':'','tool_calls':[{'function':{'name':'csv_export','arguments':{'request':'导出','artifact_ids':[]}}}]},'planner-00')
        self.assertEqual(msg['content'],'')
        self.assertEqual(json.loads(msg['tool_calls'][0]['function']['arguments'])['request'],'导出')

if __name__=='__main__':unittest.main()
