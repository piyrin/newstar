"""Explicit container integration check; synthetic fixtures only, no model calls.

Copy this file to /tmp and run it in the resume worker after building the image.
It intentionally is not part of the dependency-light unittest discovery suite.
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from pypdf import PdfReader

from resume_flow.extract import extract_file
from resume_flow.storage import write_json


def main():
    tools = {name: shutil.which(name) for name in ('libreoffice', 'tesseract', 'pdftoppm', 'fc-match')}
    assert all(tools.values()), tools
    languages = subprocess.check_output(['tesseract', '--list-langs'], text=True)
    assert 'chi_sim' in languages and 'eng' in languages
    font_path = subprocess.check_output(['fc-match', '-f', '%{file}', 'Noto Sans CJK SC'], text=True).strip()
    root = Path(os.environ['RESUME_WORKSPACE']) / 'verification'
    root.mkdir(parents=True, exist_ok=True)
    result = {'synthetic': True, 'tools': tools, 'font': font_path, 'checks': {}}
    with tempfile.TemporaryDirectory(prefix='runtime-fixtures-', dir=root) as temporary:
        directory = Path(temporary)
        image = Image.new('RGB', (1600, 600), 'white')
        painter = ImageDraw.Draw(image)
        font = ImageFont.truetype(font_path, 64)
        painter.text((60, 60), '姓名：测试同学', fill='black', font=font)
        painter.text((60, 180), '奖项：省级一等奖', fill='black', font=font)
        painter.text((60, 310), 'SYNTHETIC CERTIFICATE 2026', fill='black', font=font)
        image.save(directory / 'certificate.png')
        image.save(directory / 'scan.pdf', resolution=150)
        doc = Document()
        doc.add_paragraph('虚构材料：测试同学，示例大学。')
        doc.save(directory / 'profile.docx')
        subprocess.run(['libreoffice', '-env:UserInstallation=' + (directory / 'profile').as_uri(),
                        '--headless', '--convert-to', 'pdf', '--outdir', str(directory),
                        str(directory / 'profile.docx')], check=True, capture_output=True, timeout=120)
        for name, expected_method in [('certificate.png', 'ocr'), ('scan.pdf', 'ocr'),
                                      ('profile.docx', 'docx'), ('profile.pdf', 'pdf')]:
            segments = list(extract_file(directory / name))
            text = '\n'.join(text for _, text, _ in segments)
            assert '测试同学' in text.replace(' ', ''), (name, text)
            assert all(method == expected_method for _, _, method in segments), (name, segments)
            result['checks'][name] = {'ok': True, 'method': expected_method,
                                     'locations': [location for location, _, _ in segments], 'text': text}
            if expected_method == 'ocr':
                # A live OCR engine is not a guarantee of exact certificate wording.
                # Keep the observed mismatch instead of hiding it or treating it as a verified award.
                result['checks'][name]['requires_human_review'] = True
                result['checks'][name]['award_exact_match'] = '一等奖' in text.replace(' ', '')
        assert len(PdfReader(directory / 'profile.pdf').pages) == 1
    write_json(root / 'runtime-tools.json', result)
    print(json.dumps({'synthetic': True, 'checks': {name: data['ok'] for name, data in result['checks'].items()}},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
