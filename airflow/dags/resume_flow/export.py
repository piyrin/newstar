"""Freeze reviewed inputs, export a single DOCX to PDF and render every page."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .review import now, verify_approval
from .storage import digest, file_hash, inside, read_json, review_dir, validate_id, write_json
from .vendor.build_resume import build_resume
from .vendor.check_resume import check, compact


def output_dir(workspace, export_key):
    return inside(workspace, 'outputs', validate_id(export_key))


def freeze_export(workspace, run_key, export_key):
    approval = verify_approval(workspace, run_key)
    folder, review = output_dir(workspace, export_key), review_dir(workspace, run_key)
    if (folder / 'input.json').exists():
        saved = read_json(folder / 'input.json')
        if saved['run_key'] != run_key or saved['approval_hash'] != approval['content_hash']:
            raise ValueError('导出标识已用于另一个确认版本，请使用新的导出标识')
        verify_export_input(folder)
        return export_key
    folder.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.export-', dir=folder.parent))
    try:
        for name in ('resume.json', 'selection.json', 'questions.json'):
            (temporary / name).write_bytes((review / name).read_bytes())
        if verify_approval(workspace, run_key) != approval:
            raise ValueError('复制期间确认版本改变，请重新导出')
        hashes = {p.name: file_hash(p) for p in temporary.iterdir()}
        write_json(temporary / 'input.json', {'run_key': run_key, 'approval_hash': approval['content_hash'],
                                              'synthetic': approval['synthetic'], 'input_hashes': hashes})
        os.rename(temporary, folder)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return export_key


def verify_export_input(folder):
    record = read_json(folder / 'input.json')
    if any(file_hash(inside(folder, name)) != expected for name, expected in record['input_hashes'].items()):
        raise ValueError('已冻结的导出输入被改动，请创建新版本')
    return record


def create_docx(workspace, export_key):
    folder = output_dir(workspace, export_key)
    verify_export_input(folder)
    with tempfile.TemporaryDirectory(prefix='.docx-', dir=folder) as tmp:
        path = Path(tmp) / 'resume.docx'
        build_resume(folder / 'resume.json', path, selection=folder / 'selection.json')
        os.replace(path, folder / 'resume.docx')
    return export_key


def convert_pdf(workspace, export_key):
    folder = output_dir(workspace, export_key)
    verify_export_input(folder)
    executable = os.environ.get('RESUME_SOFFICE') or shutil.which('libreoffice') or shutil.which('soffice')
    if not executable:
        raise RuntimeError('缺少 LibreOffice，请使用简历专用运行镜像')
    with tempfile.TemporaryDirectory(prefix='.pdf-', dir=folder) as tmp:
        target = Path(tmp)
        profile = (target / 'profile').resolve().as_uri()
        subprocess.run([executable, '-env:UserInstallation=' + profile, '--headless',
                        '--convert-to', 'pdf', '--outdir', str(target), str((folder / 'resume.docx').resolve())],
                       check=True, timeout=120, capture_output=True)
        converted = target / 'resume.pdf'
        if not converted.is_file() or not converted.stat().st_size:
            raise RuntimeError('LibreOffice 未生成有效 PDF')
        os.replace(converted, folder / 'resume.pdf')
    return export_key


def check_and_render(workspace, export_key):
    from docx import Document
    from docx.oxml.ns import qn
    folder = output_dir(workspace, export_key)
    record = verify_export_input(folder)
    doc = Document(folder / 'resume.docx')
    required = [''.join(t.text or '' for t in p.iter(qn('w:t')))
                for p in doc._element.body.iter(qn('w:p'))]
    required = [text for text in required if compact(text)]
    report = check(folder / 'resume.docx', folder / 'resume.pdf', max_pages=1, required=required)
    report.update({'synthetic': record['synthetic'], 'state': 'failed', 'export_key': export_key})
    write_json(folder / 'report.json', report)
    if not report['ok']:
        raise ValueError('文件检查未通过：' + '；'.join(report['errors']))
    executable = os.environ.get('RESUME_PDFTOPPM') or shutil.which('pdftoppm')
    if not executable:
        raise RuntimeError('缺少 pdftoppm，不能生成页面预览')
    with tempfile.TemporaryDirectory(prefix='.render-', dir=folder) as tmp:
        subprocess.run([executable, '-scale-to', '1600', '-png', str(folder / 'resume.pdf'),
                        str(Path(tmp) / 'page')], check=True, timeout=120, capture_output=True)
        pages = sorted(Path(tmp).glob('page-*.png'))
        if len(pages) != report['pages']:
            raise RuntimeError('页面渲染数量不匹配')
        for i, page in enumerate(pages, 1):
            os.replace(page, folder / f'page-{i}.png')
    artifacts = [folder / 'resume.docx', folder / 'resume.pdf']
    artifacts += [folder / f'page-{i}.png' for i in range(1, report['pages'] + 1)]
    report.update({'state': 'waiting_visual', 'artifact_hashes': {p.name: file_hash(p) for p in artifacts},
                   'checked_at': now(), 'approval_hash': record['approval_hash']})
    write_json(folder / 'report.json', report)
    return export_key


def export_resume(workspace, run_key, export_key):
    freeze_export(workspace, run_key, export_key)
    run_export_step(workspace, export_key, create_docx)
    run_export_step(workspace, export_key, convert_pdf)
    return run_export_step(workspace, export_key, check_and_render)


def run_export_step(workspace, export_key, function):
    folder = output_dir(workspace, export_key)
    try:
        return function(workspace, export_key)
    except Exception as error:
        report = read_json(folder / 'report.json') if (folder / 'report.json').exists() else {}
        report.update({'state': 'failed', 'ok': False, 'failure_type': type(error).__name__})
        write_json(folder / 'report.json', report)
        raise


def accept_visual(workspace, export_key):
    folder = output_dir(workspace, export_key)
    report = read_json(folder / 'report.json')
    if not report.get('ok') or report.get('state') != 'waiting_visual':
        raise ValueError('自动检查尚未通过，不能确认最终版本')
    expected_names = {'resume.docx', 'resume.pdf'} | {f'page-{i}.png' for i in range(1, report['pages'] + 1)}
    if set(report.get('artifact_hashes', {})) != expected_names:
        raise ValueError('产物摘要不完整')
    for name, expected in report['artifact_hashes'].items():
        if file_hash(inside(folder, name)) != expected:
            raise ValueError('验收前文件被修改，请重新导出检查')
    record = {'state': 'final', 'report_hash': digest(report), 'accepted_at': now(),
              'synthetic': report.get('synthetic', False), 'statement': '已逐页查看并确认排版。'}
    write_json(folder / 'visual-acceptance.json', record)
    return record
