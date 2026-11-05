import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow' / 'dags'))
from resume_flow.storage import read_json, write_json, review_dir
from resume_flow.review import approve
from resume_flow.export import freeze_export, export_resume, accept_visual, output_dir
import test_resume_review as review_tests


class ExportTests(unittest.TestCase):
    setUp = review_tests.ReviewTests.setUp
    choose = review_tests.ReviewTests.choose
    def test_requires_approval_and_frozen_export_keeps_content(self):
        with self.assertRaises(ValueError):
            freeze_export(self.ws, 'run1', 'export1')
        self.choose()
        approve(self.ws, 'run1')
        freeze_export(self.ws, 'run1', 'export1')
        resume = read_json(output_dir(self.ws, 'export1') / 'resume.json')
        self.assertEqual(resume['name'], '虚构同学')
        path = review_dir(self.ws, 'run1') / 'resume.json'
        changed = read_json(path)
        changed['name'] = 'changed'
        write_json(path, changed)
        with self.assertRaises(ValueError):
            freeze_export(self.ws, 'run1', 'export1')

    def test_export_backend_error_recorded_as_failure(self):
        self.choose()
        approve(self.ws, 'run1')
        with patch('resume_flow.export.convert_pdf', side_effect=RuntimeError('missing backend')):
            with self.assertRaises(RuntimeError):
                export_resume(self.ws, 'run1', 'export1')
        report = read_json(output_dir(self.ws, 'export1') / 'report.json')
        self.assertEqual(report['state'], 'failed')

    def test_visual_accept_rejects_unchecked_or_changed_files(self):
        directory = output_dir(self.ws, 'export1')
        directory.mkdir(parents=True)
        write_json(directory / 'report.json', {'state': 'failed', 'ok': False})
        with self.assertRaises(ValueError):
            accept_visual(self.ws, 'export1')
        (directory / 'resume.docx').write_bytes(b'docx')
        (directory / 'resume.pdf').write_bytes(b'pdf')
        (directory / 'page-1.png').write_bytes(b'png')
        write_json(directory / 'report.json', {'state': 'waiting_visual', 'ok': True,
                    'artifact_hashes': {'resume.docx': 'invalid'}, 'pages': 1})
        with self.assertRaises(ValueError):
            accept_visual(self.ws, 'export1')

    def test_dag_style_step_failure_is_reported(self):
        from resume_flow.export import run_export_step
        self.choose()
        approve(self.ws, 'run1')
        freeze_export(self.ws, 'run1', 'export1')
        with self.assertRaises(RuntimeError):
            run_export_step(self.ws, 'export1', lambda *_: (_ for _ in ()).throw(RuntimeError('backend')))
        self.assertEqual(read_json(output_dir(self.ws, 'export1') / 'report.json')['state'], 'failed')

    def test_real_pdf_over_page_budget_or_missing_text_fails(self):
        from pypdf import PdfWriter
        from resume_flow.export import create_docx, check_and_render
        self.choose()
        approve(self.ws, 'run1')
        freeze_export(self.ws, 'run1', 'export1')
        create_docx(self.ws, 'export1')
        directory = output_dir(self.ws, 'export1')
        for pages in (1, 2):
            writer = PdfWriter()
            for _ in range(pages):
                writer.add_blank_page(width=595, height=842)
            with (directory / 'resume.pdf').open('wb') as stream:
                writer.write(stream)
            with self.assertRaises(ValueError):
                check_and_render(self.ws, 'export1')
            report = read_json(directory / 'report.json')
            self.assertFalse(report['ok'])
            self.assertEqual(report['state'], 'failed')
            self.assertTrue(any('extractable text' in e for e in report['errors']))
            if pages == 2:
                self.assertTrue(any('Page budget' in e for e in report['errors']))


if __name__ == '__main__':
    unittest.main()
