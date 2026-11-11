import json
import unittest
from render_context_audit import validate_rendered_tools


class RenderedExposure(unittest.TestCase):
    def setUp(self):
        self.tool={'type':'function','function':{'name':'real_skill','description':'Original description',
            'parameters':{'type':'object','properties':{'ids':{'type':'array','maxItems':0}}}}}

    def test_all_names_and_descriptions_must_reach_the_actual_rendered_prompt(self):
        text='<tools>\n'+json.dumps(self.tool)+'\n</tools>'
        self.assertEqual(validate_rendered_tools({'tools':[self.tool]},text),{'count':1,'schema_differences':[]})
        with self.assertRaises(ValueError):validate_rendered_tools({'tools':[self.tool]},'<tools>\n</tools>')

    def test_serializer_schema_changes_are_reported_instead_of_claiming_byte_identity(self):
        changed=json.loads(json.dumps(self.tool));del changed['function']['parameters']['properties']['ids']['maxItems']
        text='<tools>\n'+json.dumps(changed)+'\n</tools>'
        self.assertEqual(validate_rendered_tools({'tools':[self.tool]},text)['schema_differences'],['real_skill'])


if __name__=='__main__':unittest.main()
