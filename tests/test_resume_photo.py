import base64
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow/dags'))
from PIL import Image
from resume_flow.photos import save_photo
from resume_flow.review import approve, verify_approval, current_state, save_review
from resume_flow.export import freeze_export, create_docx, output_dir
from docx import Document
import test_resume_review as review_tests


class PhotoTests(unittest.TestCase):
    setUp = review_tests.ReviewTests.setUp
    choose = review_tests.ReviewTests.choose

    def photo(self, color):
        image = Image.new('RGB', (120, 160), color)
        output = io.BytesIO()
        image.save(output, format='PNG')
        return {'name': 'portrait.png', 'content_base64': base64.b64encode(output.getvalue()).decode(),
                'revision': current_state(self.ws, 'run1')['revision']}

    def test_optional_photo_is_frozen_rendered_and_invalidates_approval_when_changed(self):
        state = save_photo(self.ws, 'run1', self.photo('gray'))
        self.assertEqual(state['resume']['photo'], 'photo.jpg')
        for style in ('classic', 'minimal', 'technical'):
            self.choose(style)
            approve(self.ws, 'run1')
            freeze_export(self.ws, 'run1', style)
            self.assertTrue((output_dir(self.ws, style) / 'photo.jpg').is_file())
            create_docx(self.ws, style)
            self.assertEqual(len(Document(output_dir(self.ws, style) / 'resume.docx').inline_shapes), 1)
        save_photo(self.ws, 'run1', self.photo('white'))
        with self.assertRaises(ValueError):
            verify_approval(self.ws, 'run1')
        state = save_photo(self.ws, 'run1', {'remove': True, 'revision': current_state(self.ws, 'run1')['revision']})
        self.assertFalse(state['resume'].get('photo'))

    def test_photo_rejects_invalid_image(self):
        with self.assertRaises(ValueError):
            save_photo(self.ws, 'run1', {'content_base64': base64.b64encode(b'not an image').decode(),
                                      'revision': current_state(self.ws, 'run1')['revision']})

    def test_stale_photo_upload_cannot_refresh_old_text_revision(self):
        old_photo = self.photo('gray')
        state = current_state(self.ws, 'run1')
        state['resume']['headline'] = '另一页面的新正文'
        state['selection'] = {'schema_version': 1, 'template_id': 'classic', 'mode': 'print', 'paper': 'A4'}
        save_review(self.ws, 'run1', state)
        with self.assertRaises(ValueError):
            save_photo(self.ws, 'run1', old_photo)
        self.assertEqual(current_state(self.ws, 'run1')['resume']['headline'], '另一页面的新正文')


if __name__ == '__main__':
    unittest.main()
