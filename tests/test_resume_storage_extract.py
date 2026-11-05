import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow' / 'dags'))
from resume_flow.storage import snapshot, read_json, run_dir, validate_id
from resume_flow.extract import extract_run


class MaterialsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        self.inputs = self.ws / 'inputs' / 'demo'
        self.inputs.mkdir(parents=True)
        (self.inputs / 'profile.md').write_text('姓名：虚构同学\n学校：示例大学', encoding='utf-8')

    def test_snapshot_isolated_and_retry_stable(self):
        snapshot(self.ws, 'demo', 'run1', '开发实习', '')
        before = read_json(run_dir(self.ws, 'run1') / 'manifest.json')
        (self.inputs / 'profile.md').write_text('changed', encoding='utf-8')
        snapshot(self.ws, 'demo', 'run1', '开发实习', '')
        self.assertEqual(before, read_json(run_dir(self.ws, 'run1') / 'manifest.json'))
        extract_run(self.ws, 'run1')
        parsed = read_json(run_dir(self.ws, 'run1') / 'extracted.json')
        self.assertIn('虚构同学', parsed['segments'][0]['text'])

    def test_ids_cannot_escape(self):
        for value in ['../a', 'a/b', 'a\\b', '', '.', '中', 'a' * 100]:
            with self.assertRaises(ValueError):
                validate_id(value)

    def test_bad_files_reported_and_good_text_kept(self):
        (self.inputs / 'bad.pdf').write_bytes(b'not a pdf')
        (self.inputs / 'old.doc').write_text('old', encoding='utf-8')
        snapshot(self.ws, 'demo', 'run1', '', '')
        extract_run(self.ws, 'run1')
        parsed = read_json(run_dir(self.ws, 'run1') / 'extracted.json')
        self.assertEqual(len(parsed['issues']), 2)
        self.assertIn('虚构同学', parsed['segments'][0]['text'])

    def test_docx_paragraph_and_pdf_page_locations(self):
        from docx import Document
        from pypdf import PdfWriter
        doc = Document()
        doc.add_paragraph('证书：示例奖项')
        doc.save(self.inputs / 'certificate.docx')
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with (self.inputs / 'scan.pdf').open('wb') as stream:
            writer.write(stream)
        snapshot(self.ws, 'demo', 'run1', '', '')
        with patch('resume_flow.extract.ocr_pdf_page', return_value='扫描证书内容'):
            extract_run(self.ws, 'run1')
        segments = read_json(run_dir(self.ws, 'run1') / 'extracted.json')['segments']
        self.assertTrue(any(s['location'] == 'paragraph:1' for s in segments))
        self.assertTrue(any(s['location'] == 'page:1' and s['method'] == 'ocr' for s in segments))

    def test_file_limit_is_explicit(self):
        snapshot(self.ws, 'demo', 'run1', '', '', max_bytes=2)
        manifest = read_json(run_dir(self.ws, 'run1') / 'manifest.json')
        self.assertEqual(len(manifest['issues']), 1)
        self.assertEqual(manifest['files'], [])

    def test_source_hash_tampering_detected(self):
        snapshot(self.ws, 'demo', 'run1', '', '')
        (run_dir(self.ws, 'run1') / 'sources' / 'profile.md').write_text('tampered', encoding='utf-8')
        with self.assertRaises(ValueError):
            extract_run(self.ws, 'run1')

    def test_text_pdf_is_read_with_page_reference(self):
        from pypdf import PdfWriter
        from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
        writer = PdfWriter()
        page = writer.add_blank_page(width=595, height=842)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                 NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        content = DecodedStreamObject()
        content.set_data(b'BT /F1 12 Tf 30 750 Td (Synthetic certificate text) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(content)
        with (self.inputs / 'text.pdf').open('wb') as stream:
            writer.write(stream)
        snapshot(self.ws, 'demo', 'run1')
        extract_run(self.ws, 'run1')
        segments = read_json(run_dir(self.ws, 'run1') / 'extracted.json')['segments']
        self.assertTrue(any(s['location'] == 'page:1' and s['method'] == 'pdf'
                            and 'Synthetic certificate text' in s['text'] for s in segments))

    def test_missing_ocr_is_reported_instead_of_fake_text(self):
        from PIL import Image
        Image.new('RGB', (100, 100), 'white').save(self.inputs / 'certificate.png')
        snapshot(self.ws, 'demo', 'run1')
        with patch('resume_flow.extract.subprocess.run', side_effect=FileNotFoundError('tesseract')):
            extract_run(self.ws, 'run1')
        extracted = read_json(run_dir(self.ws, 'run1') / 'extracted.json')
        self.assertTrue(any(i['source'] == 'certificate.png' for i in extracted['issues']))
        self.assertFalse(any(s['source'] == 'certificate.png' for s in extracted['segments']))


if __name__ == '__main__':
    unittest.main()
