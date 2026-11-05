"""Render approved resume data as an editable DOCX. Does not verify claims."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from docx import Document
from docx.shared import Mm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT


def build_resume(source, output, style=None, mode=None, force=False, selection=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    picked = {}
    if selection:
        picked = json.loads(Path(selection).read_text(encoding='utf-8-sig'))
        if picked.get('schema_version') != 1 or picked.get('template_id') not in ('classic','minimal','technical') or picked.get('mode') not in ('print','digital') or picked.get('paper') not in ('A4','Letter'):
            raise ValueError('Invalid saved template selection')
    style = style or picked.get('template_id','classic')
    mode = mode or picked.get('mode','print')
    if style not in ('classic', 'minimal', 'technical') or mode not in ('print', 'digital'):
        raise ValueError('Unknown style or mode')
    if output == source or output.suffix.lower() != '.docx':
        raise ValueError('Output must be a separate .docx file')
    if output.exists() and not force:
        raise FileExistsError(f'Refusing to overwrite {output}; use --force explicitly')
    data = json.loads(source.read_text(encoding='utf-8-sig'))
    if picked:
        data['paper'] = picked['paper']
    if not isinstance(data.get('name'), str) or not data['name'].strip():
        raise ValueError('name must be non-empty')
    if not isinstance(data.get('sections'), list) or not data['sections']:
        raise ValueError('sections must be a non-empty list')
    if data.get('paper', 'A4') not in ('A4', 'Letter'):
        raise ValueError('paper must be A4 or Letter')
    photo = data.get('photo')
    if photo and style != 'classic':
        photo = None  # These layouts intentionally omit photos; preserve source data.
    if photo:
        photo = (source.parent / photo).resolve()
        if not photo.is_file():
            raise FileNotFoundError(photo)
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = (Mm(210), Mm(297)) if data.get('paper', 'A4') == 'A4' else (Mm(215.9), Mm(279.4))
    section.top_margin = section.bottom_margin = Mm(15)
    section.left_margin = section.right_margin = Mm(17)
    font = data.get('font', 'Microsoft YaHei')
    headfont = data.get('heading_font', 'SimSun' if style == 'classic' else font)
    for name in ['Normal', 'Title', 'Subtitle', 'Heading 1', 'Heading 2']:
        st = doc.styles[name]
        st.font.name, st.font.size = font, Pt(10.5)
        st.font.color.rgb = RGBColor(0, 0, 0)
        rf = st.element.get_or_add_rPr().get_or_add_rFonts()
        for attr in ['ascii', 'hAnsi', 'eastAsia', 'cs']:
            rf.set(qn('w:' + attr), font)
        pf = st.paragraph_format
        pf.line_spacing = Pt(16)
        pf.space_before = pf.space_after = Pt(0)
        pf.widow_control = True
    # Clear inherited decoration, including Word theme title rules.
    for border in list(doc.styles.element.iter(qn('w:pBdr'))):
        border.getparent().remove(border)

    def add_run(p, text, size=10.5, bold=False, family=None, color='000000'):
        r = p.add_run(str(text))
        r.font.name, r.font.size, r.font.bold = family or font, Pt(size), bold
        r.font.color.rgb = RGBColor.from_string(color)
        rf = r._element.get_or_add_rPr().get_or_add_rFonts()
        for attr in ['ascii', 'hAnsi', 'eastAsia', 'cs']:
            rf.set(qn('w:' + attr), family or font)
        return r

    def link(p, value, url):
        if not url:
            add_run(p, value, size=9.5)
            return
        scheme = urlsplit(url).scheme.lower()
        if scheme not in ('https', 'http', 'mailto', 'tel'):
            raise ValueError(f'Unsupported link scheme: {scheme}')
        if mode == 'print':
            value = url.removeprefix('https://').removeprefix('http://') if scheme in ('https', 'http') else value
            add_run(p, value, size=9.5)
            return
        hl = OxmlElement('w:hyperlink')
        hl.set(qn('r:id'), p.part.relate_to(url, RT.HYPERLINK, is_external=True))
        r, pr = OxmlElement('w:r'), OxmlElement('w:rPr')
        fonts = OxmlElement('w:rFonts')
        for attr in ['ascii', 'hAnsi', 'eastAsia']:
            fonts.set(qn('w:' + attr), font)
        pr.append(fonts)
        for tag, val in [('sz', '19'), ('color', '000000')]:
            el = OxmlElement('w:' + tag)
            el.set(qn('w:val'), val)
            pr.append(el)
        r.append(pr)
        t = OxmlElement('w:t')
        t.text = str(value)
        r.append(t)
        hl.append(r)
        p._p.append(hl)

    def para(text='', before=0, after=0, keep=False, parent=None):
        p = (parent or doc).add_paragraph()
        pf = p.paragraph_format
        pf.space_before, pf.space_after = Pt(before), Pt(after)
        pf.keep_with_next, pf.keep_together = keep, True
        if text:
            add_run(p, text)
        return p

    header = doc
    if photo:
        table = doc.add_table(rows=1, cols=2)
        table.autofit = False
        table.columns[0].width = Mm(26)
        table.columns[1].width = section.page_width - section.left_margin - section.right_margin - Mm(26)
        borders = OxmlElement('w:tblBorders')
        for edge in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
            el = OxmlElement('w:' + edge)
            el.set(qn('w:val'), 'nil')
            borders.append(el)
        table._tbl.tblPr.append(borders)
        table.cell(0, 0).paragraphs[0].add_run().add_picture(str(photo), width=Mm(22))
        header = table.cell(0, 1)
        # Reuse the required first cell paragraph for the name.
        p = header.paragraphs[0]
    else:
        p = doc.add_paragraph()
    p.style = 'Title'
    p.paragraph_format.line_spacing = Pt(31)
    p.paragraph_format.space_after = Pt(3)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if style == 'minimal' else WD_ALIGN_PARAGRAPH.LEFT
    add_run(p, data['name'], size=24, bold=True, family=headfont)
    if data.get('headline'):
        p = para(after=3, parent=header)
        add_run(p, data['headline'], size=11)
    for contact in data.get('contact', []):
        if not contact.get('value'):
            continue
        p = para(parent=header)
        add_run(p, contact.get('label', '') + '  ', size=9.5, color='444444')
        link(p, contact['value'], contact.get('url'))
    for value in data.get('availability', []):
        if value:
            p = para(parent=header)
            add_run(p, value, size=9.5)
    for group in data['sections']:
        if not group.get('title') or not isinstance(group.get('items'), list):
            raise ValueError('Each section requires title and items')
        if not group['items']:
            continue
        p = doc.add_paragraph(style='Heading 1')
        pf = p.paragraph_format
        pf.space_before, pf.space_after = Pt(11), Pt(5)
        pf.line_spacing, pf.keep_with_next = Pt(18), True
        add_run(p, group['title'], size=12, bold=True, family=headfont)
        if style != 'minimal':
            border = OxmlElement('w:pBdr')
            bottom = OxmlElement('w:bottom')
            for key, val in [('val', 'single'), ('sz', '4'), ('space', '3'), ('color', '888888')]:
                bottom.set(qn('w:' + key), val)
            border.append(bottom)
            p._p.get_or_add_pPr().append(border)
        for index, item in enumerate(group['items']):
            if item.get('title'):
                p = para(before=7 if index else 0, after=2, keep=True)
                add_run(p, item['title'], size=11, bold=True)
            if item.get('date'):
                p = para(keep=True)
                add_run(p, item['date'], size=9.5, color='444444')
            if item.get('subtitle'):
                p = para(after=2, keep=True)
                add_run(p, item['subtitle'], size=9.5, color='444444')
            if item.get('url'):
                p = para(after=3, keep=True)
                link(p, '项目地址', item['url'])
            for value in item.get('paragraphs', []):
                para(value, after=2)
            for highlight in item.get('highlights', []):
                p = para(after=2)
                if isinstance(highlight, str):
                    add_run(p, highlight)
                else:
                    if highlight.get('label'):
                        add_run(p, highlight['label'] + '：', bold=True)
                    add_run(p, highlight.get('text', ''))
    doc.core_properties.title = data['name'] + ' 简历'
    doc.core_properties.author = data['name']
    doc.core_properties.last_modified_by = data['name']
    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--style', choices=['classic', 'minimal', 'technical'])
    parser.add_argument('--mode', choices=['print', 'digital'])
    parser.add_argument('--selection', type=Path, help='Confirmed template-selection.json from the chooser')
    parser.add_argument('--force', action='store_true', help='Explicitly replace an existing DOCX')
    args = parser.parse_args()
    result = build_resume(args.source, args.output, args.style, args.mode, args.force,args.selection)
    selected = json.loads(args.selection.read_text(encoding='utf-8-sig')) if args.selection else {}
    print(json.dumps({'docx': str(result), 'style': args.style or selected.get('template_id','classic'), 'mode': args.mode or selected.get('mode','print')}, ensure_ascii=False))
