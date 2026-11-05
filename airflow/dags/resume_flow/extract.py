"""Extract text locally. OCR output always remains unverified evidence."""
import subprocess
import tempfile
from pathlib import Path

from .storage import inside, run_dir, verify_sources, write_json


def ocr_image(path: Path) -> str:
    from PIL import Image
    with Image.open(path) as image:
        if image.width * image.height > 25_000_000:
            raise ValueError('图片超过 2500 万像素')
        image.verify()
    result = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'chi_sim+eng'],
                            capture_output=True, timeout=90, check=True)
    return result.stdout.decode('utf-8').strip()


def ocr_pdf_page(path: Path, page: int) -> str:
    with tempfile.TemporaryDirectory(prefix='resume-ocr-') as tmp:
        prefix = Path(tmp) / 'page'
        subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-scale-to', '2400',
                        '-singlefile', '-png', str(path), str(prefix)],
                       capture_output=True, timeout=90, check=True)
        return ocr_image(prefix.with_suffix('.png'))


def extract_file(path: Path):
    suffix = path.suffix.lower()
    if suffix in ('.txt', '.md'):
        yield 'text', path.read_text(encoding='utf-8-sig'), 'text'
    elif suffix == '.docx':
        from docx import Document
        doc = Document(path)
        for i, paragraph in enumerate(doc.paragraphs, 1):
            if paragraph.text.strip():
                yield f'paragraph:{i}', paragraph.text, 'docx'
        for i, table in enumerate(doc.tables, 1):
            for j, row in enumerate(table.rows, 1):
                yield f'table:{i}/row:{j}', ' | '.join(c.text for c in row.cells), 'docx'
    elif suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError('不支持加密 PDF')
        if len(reader.pages) > 30:
            raise ValueError('PDF 超过 30 页，请拆分')
        for i, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ''
            if len(text.strip()) < 12:
                yield f'page:{i}', ocr_pdf_page(path, i), 'ocr'
            else:
                yield f'page:{i}', text, 'pdf'
    elif suffix in ('.png', '.jpg', '.jpeg'):
        yield 'image:1', ocr_image(path), 'ocr'
    else:
        raise ValueError('不支持此文件格式')


def extract_run(workspace: Path, run_key: str) -> str:
    manifest = verify_sources(workspace, run_key)
    directory = run_dir(workspace, run_key)
    segments, issues = [], list(manifest['issues'])
    for item in manifest['files']:
        before = len(segments)
        try:
            for location, text, method in extract_file(inside(directory / 'sources', item['source'])):
                text = text.strip()
                if not text:
                    issues.append({'source': item['source'], 'reason': f'{location} 未提取到文字'})
                for start in range(0, len(text), 5000):
                    if len(segments) >= 120:
                        raise ValueError('总片段超过 120 个，请拆分材料')
                    segments.append({'id': f's{len(segments)+1:04}', 'source': item['source'],
                                     'location': location, 'offset': start, 'method': method,
                                     'text': text[start:start + 5000]})
            if len(segments) == before:
                issues.append({'source': item['source'], 'reason': '无可读取文字'})
        except Exception as error:
            # No exception body: third-party parser errors can include private file text.
            reason = str(error) if isinstance(error, ValueError) else type(error).__name__
            issues.append({'source': item['source'], 'reason': reason})
    write_json(directory / 'extracted.json', {'snapshot_hash': manifest['snapshot_hash'],
                                             'segments': segments, 'issues': issues})
    return run_key
