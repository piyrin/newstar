"""Bounded input snapshots and atomic, local artifact storage."""
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path


def validate_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value):
        raise ValueError('标识仅允许 1–80 位英文字母、数字、下划线和短横线')
    return value


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(root: Path, *parts: str) -> Path:
    root = Path(root).resolve()
    candidate = root.joinpath(*parts)
    if not candidate.resolve().is_relative_to(root):
        raise ValueError('路径越出工作目录')
    return candidate


def run_dir(workspace: Path, run_key: str) -> Path:
    return inside(workspace, 'runs', validate_id(run_key))


def review_dir(workspace: Path, run_key: str) -> Path:
    return inside(workspace, 'reviews', validate_id(run_key))


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path: Path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.write-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def snapshot(workspace: Path, case_id: str, run_key: str, target: str = '', jd: str = '',
             max_bytes: int = 5_000_000) -> str:
    validate_id(case_id)
    destination = run_dir(workspace, run_key)
    config = {'case_id': case_id, 'target': target, 'jd': jd}
    if len(target) > 200 or len(jd) > 20000:
        raise ValueError('岗位方向或 JD 超过长度限制')
    if (destination / 'manifest.json').exists():
        if read_json(destination / 'manifest.json')['config'] != config:
            raise ValueError('相同运行标识不能更换输入配置，请使用新标识')
        verify_sources(workspace, run_key)
        return run_key
    source = inside(workspace, 'inputs', case_id)
    if not source.is_dir():
        raise ValueError('材料目录不存在，请先放入材料')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.snapshot-', dir=destination.parent))
    files, issues, total, seen = [], [], 0, 0
    try:
        for directory, dirs, names in os.walk(source, followlinks=False):
            dirs.sort()
            for name in list(dirs):
                directory_path = Path(directory) / name
                if directory_path.is_symlink() or name.startswith('.'):
                    dirs.remove(name)
                    issues.append({'source': directory_path.relative_to(source).as_posix(),
                                   'reason': '已跳过链接或隐藏目录'})
            for name in sorted(names):
                path = Path(directory) / name
                relative = path.relative_to(source).as_posix()
                seen += 1
                if seen > 100:
                    raise ValueError('材料超过 100 个文件，请拆分案例')
                if path.is_symlink() or name.startswith('.'):
                    issues.append({'source': relative, 'reason': '已跳过链接或隐藏文件'})
                    continue
                size = path.stat().st_size
                if size > max_bytes or total + size > 20_000_000:
                    issues.append({'source': relative, 'reason': '文件或总材料超过大小限制'})
                    continue
                data = path.read_bytes()
                if len(data) > max_bytes or total + len(data) > 20_000_000:
                    raise ValueError('复制期间文件大小变化，请重试新运行')
                target_path = inside(temporary, 'sources', relative)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(data)
                total += len(data)
                files.append({'source': relative, 'bytes': len(data),
                              'sha256': hashlib.sha256(data).hexdigest()})
        manifest = {'schema_version': 1, 'config': config, 'files': files, 'issues': issues}
        manifest['snapshot_hash'] = digest(manifest)
        write_json(temporary / 'manifest.json', manifest)
        os.rename(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return run_key


def verify_sources(workspace: Path, run_key: str) -> dict:
    directory = run_dir(workspace, run_key)
    manifest = read_json(directory / 'manifest.json')
    if digest({k: v for k, v in manifest.items() if k != 'snapshot_hash'}) != manifest['snapshot_hash']:
        raise ValueError('材料清单摘要不匹配')
    for item in manifest['files']:
        if file_hash(inside(directory / 'sources', item['source'])) != item['sha256']:
            raise ValueError('材料快照已改动，请使用新的运行')
    return manifest
