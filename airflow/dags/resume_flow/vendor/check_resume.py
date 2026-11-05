"""Check resume file freshness and text. Visual QA is still required."""
import argparse
import json
import re
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn
from pypdf import PdfReader


def compact(text):
    return re.sub(r'\s+', '', text)


def check(docx_path, pdf_path, max_pages=1, required=(), forbidden=()):
    source, pdf = Path(docx_path), Path(pdf_path)
    errors = []
    if not source.is_file() or not pdf.is_file():
        return {'ok': False, 'errors': ['Both DOCX and PDF must exist']}
    if pdf.stat().st_mtime + 1 < source.stat().st_mtime:
        errors.append('PDF is older than DOCX')
    doc = Document(source)
    texts = []
    # Traverse XML so table contents and hyperlink text are included in order.
    for p in doc._element.body.iter(qn('w:p')):
        texts.append(''.join(el.text or '' for el in p.iter(qn('w:t'))))
    word_text = '\n'.join(texts)
    reader = PdfReader(pdf)
    pdf_text = '\n'.join(p.extract_text() or '' for p in reader.pages)
    if len(reader.pages) > max_pages:
        errors.append(f'Page budget exceeded: {len(reader.pages)} > {max_pages}')
    if not compact(pdf_text):
        errors.append('PDF has no extractable text')
    for kind, text in [('DOCX', word_text), ('PDF', pdf_text)]:
        norm = compact(text)
        for phrase in required:
            if compact(phrase) not in norm:
                errors.append(f'{kind} missing required text: {phrase}')
        for phrase in forbidden:
            if compact(phrase) in norm:
                errors.append(f'{kind} contains forbidden text: {phrase}')
    pdf_links = 0
    for page in reader.pages:
        for ref in page.get('/Annots', []):
            if ref.get_object().get('/Subtype') == '/Link':
                pdf_links += 1
    return {
        'ok': not errors, 'errors': errors, 'pages': len(reader.pages),
        'docx_links': sum(rel.reltype.endswith('/hyperlink') for rel in doc.part.rels.values()),
        'pdf_links': pdf_links,
        'pdf_text_characters': len(pdf_text),
        'visual_review_required': True,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('docx', type=Path)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--max-pages', type=int, default=1)
    parser.add_argument('--require', action='append', default=[])
    parser.add_argument('--forbid', action='append', default=[])
    args = parser.parse_args()
    result = check(args.docx, args.pdf, args.max_pages, args.require, args.forbid)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['ok'] else 1)
