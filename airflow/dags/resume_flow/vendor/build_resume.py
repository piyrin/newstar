"""Render approved resume data as an editable DOCX. Does not verify claims."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from docx import Document
from docx.shared import Mm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT

TEMPLATE_VERSION = 'reference-20261105-v2'


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
    if photo:
        photo = (source.parent / photo).resolve()
        if not photo.is_relative_to(source.parent):
            raise ValueError('Photo must be inside the resume directory')
        if not photo.is_file():
            raise FileNotFoundError(photo)
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = (Mm(210), Mm(297)) if data.get('paper', 'A4') == 'A4' else (Mm(215.9), Mm(279.4))
    section.top_margin = section.bottom_margin = Mm(13)
    section.left_margin = section.right_margin = Mm(15)
    font = data.get('font', 'Microsoft YaHei')
    headfont = font if style == 'technical' else data.get('heading_font', 'SimSun')
    for name in ['Normal', 'Title', 'Subtitle', 'Heading 1', 'Heading 2']:
        st = doc.styles[name]
        st.font.name, st.font.size = font, Pt(10.5)
        st.font.color.rgb = RGBColor(0, 0, 0)
        rf = st.element.get_or_add_rPr().get_or_add_rFonts()
        for attr in ['ascii', 'hAnsi', 'eastAsia', 'cs']:
            rf.set(qn('w:' + attr), font)
        pf = st.paragraph_format
        pf.line_spacing = Pt(15)
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

    def borderless(table):
        borders = OxmlElement('w:tblBorders')
        for edge in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
            el = OxmlElement('w:' + edge)
            el.set(qn('w:val'), 'nil')
            borders.append(el)
        table._tbl.tblPr.append(borders)

    def shade(properties, fill):
        node = OxmlElement('w:shd')
        node.set(qn('w:fill'), fill)
        properties.append(node)

    def rule(p, edge, color, size=4, space=3):
        properties = p._p.get_or_add_pPr()
        borders = properties.find(qn('w:pBdr'))
        if borders is None:
            borders = OxmlElement('w:pBdr')
            properties.append(borders)
        node = OxmlElement('w:' + edge)
        for key, value in [('val', 'single'), ('sz', str(size)), ('space', str(space)), ('color', color)]:
            node.set(qn('w:' + key), value)
        borders.append(node)

    def layout_table(parent, widths, fill=None, padding=0):
        table = parent.add_table(rows=1, cols=len(widths))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        borderless(table)
        for column, cell, width in zip(table.columns, table.rows[0].cells, widths):
            column.width = cell.width = int(width)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            margins = OxmlElement('w:tcMar')
            for edge in ('top', 'bottom', 'left', 'right'):
                node = OxmlElement('w:' + edge)
                node.set(qn('w:w'), str(padding))
                node.set(qn('w:type'), 'dxa')
                margins.append(node)
            cell._tc.get_or_add_tcPr().append(margins)
            if fill:
                shade(cell._tc.get_or_add_tcPr(), fill)
        return table

    width = section.page_width - section.left_margin - section.right_margin
    ink = '253044' if style == 'technical' else '25272A'
    muted = '586780' if style == 'technical' else '444444'
    contacts = [c for c in data.get('contact', []) if c.get('value')]
    contacts += [{'value': value} for value in data.get('availability', []) if value]
    # The first two references keep identity and two-column metadata side by side.
    identity_width = Mm(46) if contacts and style != 'technical' else width - (Mm(28) if photo else 0)
    widths = ([Mm(28)] if photo else []) + [identity_width]
    if contacts and style != 'technical':
        widths.append(width - sum(widths))
    table = layout_table(doc, widths)
    if photo:
        from PIL import Image
        with Image.open(photo) as image:
            ratio = image.height / image.width
        photo_width = min(Mm(22), Mm(30) / ratio)
        p = table.cell(0, 0).paragraphs[0]
        # Exact text line heights clip inline portraits in Word and LibreOffice.
        p.paragraph_format.line_spacing = 1.0
        p.add_run().add_picture(str(photo), width=int(photo_width))
    identity = table.cell(0, 1 if photo else 0)
    p = identity.paragraphs[0]
    p.style = 'Title'
    p.paragraph_format.line_spacing = Pt(29)
    p.paragraph_format.space_after = Pt(3)
    if style == 'technical':
        rule(p, 'left', '253044', 14, 5)
        p.paragraph_format.left_indent = Mm(5)
    add_run(p, data['name'], size=25 if style == 'technical' else 23, bold=True, color=ink)
    if data.get('headline'):
        p = para(parent=identity)
        if style == 'technical':
            p.paragraph_format.left_indent = Mm(5)
        add_run(p, data['headline'], size=10, color=muted)

    if contacts:
        contact_parent = doc if style == 'technical' else table.cell(0, len(widths) - 1)
        if style == 'technical':
            p = para(after=1)
            p.paragraph_format.line_spacing = Pt(5)
        contact_width = width if style == 'technical' else widths[-1]
        columns = min(3 if style == 'technical' else 2, len(contacts))
        if contact_parent is not doc:
            metadata = contact_parent.add_table(rows=1, cols=columns)
            metadata.autofit = False
            borderless(metadata)
        else:
            metadata = layout_table(doc, [contact_width / columns] * columns, 'F7F9FC', 70)
        for column in metadata.columns:
            column.width = int(contact_width / columns)
        for index, contact in enumerate(contacts):
            if index and index % columns == 0:
                metadata.add_row()
            cell = metadata.cell(index // columns, index % columns)
            cell.width = int(contact_width / columns)
            if style == 'technical':
                shade(cell._tc.get_or_add_tcPr(), 'F7F9FC')
                borders = OxmlElement('w:tcBorders')
                for edge in ('top', 'bottom', 'left', 'right'):
                    node = OxmlElement('w:' + edge)
                    for key, value in [('val', 'single'), ('sz', '12'), ('color', 'FFFFFF')]:
                        node.set(qn('w:' + key), value)
                    borders.append(node)
                cell._tc.get_or_add_tcPr().append(borders)
            p = cell.paragraphs[0]
            p.paragraph_format.line_spacing = Pt(16)
            label = contact.get('label', '')
            if label:
                add_run(p, label + '  ', size=8.5, color=muted)
            link(p, contact['value'], contact.get('url'))
        if contact_parent is not doc:
            for p in contact_parent.paragraphs:
                p.paragraph_format.line_spacing = Pt(1)
                p.paragraph_format.space_after = Pt(0)

    for group in data['sections']:
        if not group.get('title') or not isinstance(group.get('items'), list):
            raise ValueError('Each section requires title and items')
        if not group['items']:
            continue
        p = doc.add_paragraph(style='Heading 1')
        pf = p.paragraph_format
        pf.space_before, pf.space_after = Pt(12), Pt(7)
        pf.line_spacing, pf.keep_with_next = Pt(19), True
        add_run(p, group['title'], size=12, bold=True, family=headfont, color=ink)
        if style == 'minimal':
            shade(p._p.get_or_add_pPr(), 'E7E7E7')
            rule(p, 'left', '25272A', 12, 8)
            pf.left_indent = Mm(3)
        else:
            rule(p, 'bottom', 'E3E7ED' if style == 'technical' else '888888')
            if style == 'technical':
                rule(p, 'left', '253044', 16, 6)
                pf.left_indent = Mm(2)
        skills = '技能' in group['title'] or 'skill' in group['title'].lower()
        bullets = skills or '项目' in group['title'] or 'project' in group['title'].lower()
        body = doc
        if style == 'technical' and skills:
            card = layout_table(doc, [width], 'FAFBFE', 95)
            body = card.cell(0, 0)
            empty = body.paragraphs[0]
            empty.paragraph_format.line_spacing = Pt(1)
        item_color = muted if style == 'technical' else '25272A'
        for index, item in enumerate(group['items']):
            if skills and not any(item.get(key) for key in ('subtitle', 'date', 'url', 'highlights')):
                p = para(before=2 if index else 0, after=1, parent=body)
                p.paragraph_format.line_spacing = Pt(14)
                if item.get('title'):
                    add_run(p, item['title'] + '  ', size=10, bold=True, color=ink)
                add_run(p, ' / '.join(item.get('paragraphs', [])), size=10, color=item_color)
                continue
            if any(item.get(key) for key in ('title', 'subtitle', 'date')):
                meta = layout_table(body, [width * .43, width * .32, width * .25]) if body is doc else None
                if meta is not None:
                    for col, key in enumerate(('title', 'subtitle', 'date')):
                        p = meta.cell(0, col).paragraphs[0]
                        p.paragraph_format.space_before = Pt(7 if index else 0)
                        p.paragraph_format.space_after = Pt(3)
                        p.paragraph_format.keep_with_next = True
                        if col == 2:
                            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                            if style == 'technical' and item.get(key):
                                shade(p._p.get_or_add_pPr(), 'F7F9FC')
                        if col == 1 and style == 'technical' and item.get(key):
                            rule(p, 'left', 'DDE3EC', 4, 6)
                        if item.get(key):
                            add_run(p, item[key], size=10 if col == 0 else 9.5,
                                    bold=col == 0, color=ink if col == 0 else muted)
                else:
                    p = para(after=3, keep=True, parent=body)
                    add_run(p, '  '.join(item[key] for key in ('title', 'subtitle', 'date') if item.get(key)),
                            size=10, bold=True, color=ink)
            if item.get('url'):
                p = para(after=3, keep=True, parent=body)
                link(p, '项目地址', item['url'])
            for value in item.get('paragraphs', []):
                p = para(after=2, parent=body)
                add_run(p, ('·  ' if bullets else '') + value, size=10, color=item_color)
                if bullets:
                    p.paragraph_format.left_indent = Mm(2)
                    p.paragraph_format.first_line_indent = Mm(-2)
                elif style == 'technical':
                    rule(p, 'left', 'DDE3EC', 4, 7)
            for highlight in item.get('highlights', []):
                p = para(after=2, parent=body)
                p.paragraph_format.left_indent = Mm(2)
                p.paragraph_format.first_line_indent = Mm(-2)
                add_run(p, '·  ', size=10, color=item_color)
                if isinstance(highlight, str):
                    add_run(p, highlight, size=10, color=item_color)
                else:
                    if highlight.get('label'):
                        add_run(p, highlight['label'] + '：', size=10, bold=True, color=item_color)
                    add_run(p, highlight.get('text', ''), size=10, color=item_color)
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
