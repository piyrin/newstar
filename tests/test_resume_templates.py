"""Template layouts must differ without dropping or reordering approved content."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from docx import Document
from docx.oxml.ns import qn

SCRIPT = Path(__file__).resolve().parents[1] / 'airflow/dags/resume_flow/vendor/build_resume.py'
spec = importlib.util.spec_from_file_location('resume_template_builder', SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ResumeTemplateTests(unittest.TestCase):
    def test_skill_category_and_content_share_a_compact_paragraph(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / 'resume.json'
            source.write_text(json.dumps({'name': '虚构同学', 'sections': [
                {'title': '技能', 'items': [{'title': '编程与框架',
                    'paragraphs': ['Python', 'FastAPI']}]}]}, ensure_ascii=False), encoding='utf-8')
            for style in ('classic', 'minimal', 'technical'):
                output = folder / (style + '.docx')
                builder.build_resume(source, output, style=style)
                doc = Document(output)
                paragraphs = [''.join(p.itertext()) for p in doc.element.body.iter(qn('w:p'))]
                self.assertTrue(any('编程与框架' in p and 'Python / FastAPI' in p for p in paragraphs))

    def test_distinct_layouts_preserve_all_approved_text_and_section_order(self):
        data = {
            'name': '张同学', 'headline': '后端实习',
            'contact': [{'label': '邮箱', 'value': 'student@example.test'}],
            'availability': ['每周三天'],
            'sections': [
                {'title': '项目经历', 'items': [{'title': '流水线项目', 'date': '2025',
                    'subtitle': '个人实现', 'paragraphs': ['实现可重试任务'],
                    'highlights': [{'label': '校验', 'text': '保留审核记录'}]}]},
                {'title': '教育经历', 'items': [{'title': '示例大学',
                    'paragraphs': ['计算机专业']}]}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'resume.json'
            source.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            docs = {}
            for style in ('classic', 'minimal', 'technical'):
                output = Path(tmp) / f'{style}.docx'
                builder.build_resume(source, output, style=style)
                doc = docs[style] = Document(output)
                # Traverse XML so sidebar text is checked as well as body paragraphs.
                text = '\n'.join(doc.element.body.itertext())
                for expected in ('张同学', '后端实习', 'student@example.test', '每周三天',
                                 '流水线项目', '2025', '个人实现', '实现可重试任务',
                                 '校验：', '保留审核记录', '示例大学', '计算机专业'):
                    self.assertIn(expected, text, style)
                self.assertLess(text.index('项目经历'), text.index('教育经历'))
            # The references all use a full-width body with metadata in the header.
            for style, doc in docs.items():
                header_xml = doc.tables[0]._tbl.xml
                if style == 'technical':
                    header_xml += doc.tables[1]._tbl.xml
                self.assertIn('student@example.test', header_xml)
                self.assertNotIn('项目经历', doc.tables[0]._tbl.xml)
                self.assertFalse(list(doc.element.body.iter(qn('w:cantSplit'))))
            headings = {style: [p for p in doc.paragraphs if p.style.name == 'Heading 1']
                        for style, doc in docs.items()}
            self.assertTrue(list(headings['classic'][0]._p.iter(qn('w:bottom'))))
            self.assertEqual(next(headings['minimal'][0]._p.iter(qn('w:shd'))).get(qn('w:fill')), 'E7E7E7')
            self.assertTrue(list(headings['minimal'][0]._p.iter(qn('w:left'))))
            self.assertTrue(list(headings['technical'][0]._p.iter(qn('w:left'))))
            self.assertNotEqual(docs['classic'].element.body.xml, docs['technical'].element.body.xml)

    def test_card_skills_and_photo_are_not_clipped_by_fixed_line_height(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            Image.new('RGB', (120, 160), 'gray').save(folder / 'photo.jpg')
            source = folder / 'resume.json'
            source.write_text(json.dumps({'name': '张同学', 'photo': 'photo.jpg', 'contact': [],
                'sections': [{'title': '专业技能', 'items': [{'paragraphs': ['Python 和 SQL']}]}]}), encoding='utf-8')
            output = folder / 'card.docx'
            builder.build_resume(source, output, style='technical')
            doc = Document(output)
            self.assertEqual(len(doc.inline_shapes), 1)
            self.assertAlmostEqual(doc.inline_shapes[0].height / doc.inline_shapes[0].width, 4 / 3, places=2)
            photo_paragraph = next(p for p in doc.element.body.iter(qn('w:p')) if list(p.iter(qn('w:drawing'))))
            spacing = next(photo_paragraph.iter(qn('w:spacing')))
            self.assertEqual(spacing.get(qn('w:lineRule')), 'auto')
            self.assertIn('FAFBFE', doc.element.body.xml)


if __name__ == '__main__':
    unittest.main()
