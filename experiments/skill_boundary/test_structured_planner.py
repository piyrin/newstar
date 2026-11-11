import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from progressive import make_tools,ordered_registry
from local_api import LocalAPI
from structured_planner import StructuredPlannerAPI,plan_schema,plain_history


class StructuredPlannerTests(unittest.TestCase):
    def test_schema_keeps_all_candidates_and_exact_dynamic_references(self):
        tools=make_tools(ordered_registry()[:100],['DOC-001','FILE-001-01'],'controls-only','on-call')
        schema=plan_schema(tools)
        branches=schema['properties']['calls']['items']['anyOf']
        self.assertEqual(len(branches[0]['properties']['name']['enum']),100)
        self.assertEqual(branches[1]['properties']['name']['enum'],['submit_deliverables','review_deliverables'])
        self.assertEqual(branches[1]['properties']['arguments']['properties']['deliverables']['items']['properties']['reference_ids']['items']['enum'],['DOC-001','FILE-001-01'])

    def test_native_history_converted_without_losing_choices_or_tool_body(self):
        calls=[{'id':'call1','function':{'name':'planning','arguments':'{"request":"原要求","artifact_ids":[]}'}}]
        messages=[{'role':'assistant','content':'','tool_calls':calls},{'role':'tool','tool_call_id':'call1','content':'真实完整产物'}]
        converted=plain_history(messages)
        self.assertEqual(json.loads(converted[0]['content'])['calls'][0]['arguments']['request'],'原要求')
        self.assertEqual(json.loads(converted[1]['content'])['content'],'真实完整产物')
        self.assertIn('tool_calls',messages[0])

    def test_generated_plan_is_decoded_without_changing_arguments(self):
        tools=make_tools(ordered_registry()[:10],[],'controls-only','on-call')
        plan={'calls':[{'name':'planning','arguments':{'request':'自主子任务','artifact_ids':[]}}]}
        with tempfile.TemporaryDirectory() as directory,patch.object(LocalAPI,'call',return_value=(plan,{'total_tokens':1})) as call:
            api=StructuredPlannerAPI();msg,_=api.call([{'role':'system','content':'原系统'},{'role':'user','content':'原需求'}],Path(directory)/'planner-00',tools=tools)
            self.assertEqual(json.loads(msg['tool_calls'][0]['function']['arguments']),plan['calls'][0]['arguments'])
            self.assertIsInstance(call.call_args.kwargs['json_mode'],dict)
            self.assertIsNone(call.call_args.kwargs['tools'])

if __name__=='__main__':unittest.main()
