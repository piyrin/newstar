"""Content-addressed preparation; only a published review counts as processed."""
import os
import shutil
import uuid
import logging
from pathlib import Path

from .storage import digest, read_json, run_dir, snapshot, verify_sources, write_json

PIPELINE_VERSION = 1


def prepare_version(workspace: Path, case_id: str, run_key='', target='', jd='', mode='deepseek'):
    if mode not in ('deepseek', 'offline'):
        raise ValueError('模型模式无效')
    # Snapshot first: the digest describes exactly what the downstream tasks read.
    candidate = run_key or 'scan-' + uuid.uuid4().hex
    snapshot(workspace, case_id, candidate, target, jd)
    directory = run_dir(workspace, candidate)
    manifest = verify_sources(workspace, candidate)
    identity = {'snapshot_hash': manifest['snapshot_hash'], 'mode': mode,
                'pipeline_version': PIPELINE_VERSION}
    key = run_key or 'inc-' + digest(identity)
    # Reuse successful versions made before incremental checks were introduced.
    # Their facts bundle already records both the snapshot hash and model mode.
    if not run_key:
        for old in sorted((Path(workspace) / 'runs').iterdir()):
            if old == directory or not old.is_dir() or old.is_symlink():
                continue
            try:
                metadata = old / 'version.json'
                if metadata.exists():
                    if read_json(metadata) != identity:
                        continue
                    complete = old / 'incremental-complete.json'
                    if not complete.exists() or read_json(complete) != identity:
                        continue
                elif PIPELINE_VERSION == 1 and (old / 'facts.json').exists():
                    bundle = read_json(old / 'facts.json')
                    if bundle.get('snapshot_hash') != identity['snapshot_hash'] or bundle.get('mode') != mode:
                        continue
                else:
                    continue
                review = Path(workspace) / 'reviews' / old.name
                if (not (old / 'status.json').is_file()
                        or not all((review / name).is_file() for name in ('resume.json', 'questions.json'))):
                    continue
                verify_sources(workspace, old.name)
                if not metadata.exists():
                    write_json(metadata, identity)
                    finish_version(workspace, old.name)
            except (OSError, ValueError):
                logging.getLogger(__name__).warning('跳过无法复用的历史版本：%s', old.name)
                continue
            shutil.rmtree(directory)
            return {'run_key': old.name, 'skip': True, 'reason': '相同材料与配置已有成功审阅包，复用历史版本'}
    destination = run_dir(workspace, key)
    if not run_key:
        try:
            os.rename(directory, destination)
        except OSError:
            if not destination.is_dir():
                raise
            # Concurrent/manual requests may have already fixed the same version.
            if verify_sources(workspace, key)['snapshot_hash'] != manifest['snapshot_hash']:
                raise ValueError('版本标识冲突') from None
        finally:
            if directory.exists():
                shutil.rmtree(directory)
    metadata = destination / 'version.json'
    if (destination / 'facts.json').exists() and read_json(destination / 'facts.json').get('mode') != mode:
        raise ValueError('相同运行标识不能更换模型模式')
    if metadata.exists() and read_json(metadata) != identity:
        raise ValueError('相同运行标识不能更换模型模式或流程版本')
    write_json(metadata, identity)
    review = Path(workspace) / 'reviews' / key
    complete = destination / 'incremental-complete.json'
    skip = (complete.exists() and read_json(complete) == identity
            and all((review / name).exists() for name in ('resume.json', 'questions.json'))
            and (destination / 'status.json').exists())
    return {'run_key': key, 'skip': skip, 'reason': '材料与配置未变化，已完成整理' if skip else '新版本或上次未完成'}


def finish_version(workspace: Path, run_key: str):
    directory = run_dir(workspace, run_key)
    review = Path(workspace) / 'reviews' / run_key
    if not all((review / name).is_file() for name in ('resume.json', 'questions.json')) or not (directory / 'status.json').is_file():
        raise ValueError('审阅包尚未发布，不能标记为已处理')
    verify_sources(workspace, run_key)
    write_json(directory / 'incremental-complete.json', read_json(directory / 'version.json'))
    return run_key
