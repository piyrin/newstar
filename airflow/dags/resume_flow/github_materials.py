"""Import bounded GitHub repository evidence through the public contents API."""
import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from .airflow_api import NoRedirect
from .materials import import_materials
from .storage import digest, inside, read_json, validate_id, write_json

CONFIG_FILES = {'package.json', 'pyproject.toml', 'requirements.txt', 'go.mod', 'Cargo.toml',
                'pom.xml', 'build.gradle', 'CMakeLists.txt', 'environment.yml'}


class GitHubReader:
    def __init__(self):
        self.token = os.environ.get('GITHUB_TOKEN', '')
        self.opener = urllib.request.build_opener(NoRedirect())

    def get(self, path):
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'newstar-resume-workflow'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        request = urllib.request.Request('https://api.github.com' + path, headers=headers)
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read(2_000_001)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise ValueError('仓库或分支不存在，私有仓库需要服务端配置 GITHUB_TOKEN') from None
            raise ValueError(f'GitHub HTTP {error.code}，请检查访问权限或稍后重试') from None
        except (urllib.error.URLError, OSError):
            raise ValueError('GitHub 连接失败或超时，请稍后重试') from None
        if len(raw) > 2_000_000:
            raise ValueError('GitHub 响应超过大小限制')
        try:
            return json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise ValueError('GitHub 返回了无效内容') from None


def repository_url(value):
    if not isinstance(value, str) or len(value) > 500:
        raise ValueError('请填写 GitHub 仓库链接')
    url = urllib.parse.urlsplit(value.strip())
    if (url.scheme != 'https' or url.hostname != 'github.com' or url.username or url.password
            or url.port not in (None, 443)):
        raise ValueError('请填写 https://github.com/用户名/仓库名')
    parts = url.path.strip('/').split('/')
    if len(parts) != 2:
        raise ValueError('请填写仓库首页链接，分支请填写在分支输入框')
    owner, repo = parts[0], parts[1].removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', owner) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', repo) or repo in ('.', '..'):
        raise ValueError('GitHub 用户名或仓库名无效')
    return owner, repo


def decode_file(response):
    if not isinstance(response, dict) or response.get('encoding') != 'base64' or response.get('size', 0) > 64_000:
        raise ValueError('文件超过64KB或无法读取文本')
    try:
        content = base64.b64decode(''.join(response['content'].split()), validate=True)
        if len(content) > 64_000:
            raise ValueError('文件超过64KB')
        return content.decode('utf-8-sig')
    except (KeyError, ValueError, UnicodeDecodeError):
        raise ValueError('文件不是可读取的 UTF-8 文本或超过64KB') from None


def import_github(workspace, payload, reader=None):
    case_id, request_id = validate_id(payload.get('case_id')), validate_id(payload.get('request_id'))
    owner, repo = repository_url(payload.get('url'))
    ref, contribution = payload.get('ref', ''), payload.get('contribution', '')
    if not isinstance(ref, str) or (ref and not re.fullmatch(r'[A-Za-z0-9_./-]{1,120}', ref)):
        raise ValueError('分支名称无效')
    if not isinstance(contribution, str) or len(contribution) > 10000:
        raise ValueError('本人贡献说明最多10000字')
    fingerprint = digest({'case_id': case_id, 'owner': owner, 'repo': repo, 'ref': ref, 'contribution': contribution})
    record_path = inside(workspace, 'github_imports', request_id + '.json')
    if record_path.is_file():
        saved = read_json(record_path)
        if saved['fingerprint'] != fingerprint:
            raise ValueError('此请求标识已用于不同仓库参数，请重新提交')
        if saved.get('result'):
            return saved['result']
    else:
        client = reader or GitHubReader()
        base = '/repos/' + owner + '/' + repo
        metadata = client.get(base)
        branch = ref or metadata['default_branch']
        branch_data = client.get(base + '/branches/' + urllib.parse.quote(branch, safe=''))
        commit = branch_data['commit']['sha']
        if not re.fullmatch(r'[0-9a-fA-F]{40}', commit):
            raise ValueError('GitHub 没有返回有效版本标识')
        query = '?ref=' + commit
        entries = client.get(base + '/contents' + query)
        if not isinstance(entries, list):
            raise ValueError('仓库目录响应无效')
        issues, documents, total = [], [], 0
        try:
            readme = client.get(base + '/readme' + query)
            text = decode_file(readme)
            documents.append((readme.get('path', 'README.md'), text))
            total += len(text.encode())
        except ValueError as error:
            issues.append('README ' + str(error))
        for entry in entries:
            name = entry.get('name')
            if entry.get('type') != 'file' or name not in CONFIG_FILES:
                continue
            if entry.get('size', 0) > 64_000:
                issues.append(name + ' 超过64KB，已跳过')
                continue
            if len(documents) >= 9 or total + entry.get('size', 0) > 200_000:
                issues.append(name + ' 超过本次读取上限，已跳过')
                continue
            try:
                text = decode_file(client.get(base + '/contents/' + urllib.parse.quote(name, safe='') + query))
                documents.append((name, text))
                total += len(text.encode())
            except ValueError as error:
                issues.append(name + ' ' + str(error))
        repository = 'https://github.com/' + owner + '/' + repo
        lines = ['# GitHub 项目材料', '', '仓库链接 ' + repository, '固定版本 ' + commit,
                 '分支 ' + branch, '项目名称 ' + str(metadata.get('name') or repo),
                 '项目简介 ' + str(metadata.get('description') or ''), '', '## 本人贡献说明',
                 contribution or '本人贡献尚未填写，需人工核实。', '', '## 根目录文件']
        lines.extend('- ' + str(entry.get('name', '')) for entry in entries[:100])
        if len(entries) > 100:
            issues.append('目录展示前100项')
        for path, text in documents:
            source_url = repository + '/blob/' + commit + '/' + urllib.parse.quote(path, safe='/')
            lines.extend(['', '## 来源文件 ' + path, '来源链接 ' + source_url, '', text])
        lines.extend(['', '## 导入说明', '本材料为仓库内容快照，本人贡献需单独核实。'])
        lines.extend('- ' + issue for issue in issues)
        content = '\n'.join(lines).encode('utf-8')
        repository_key = owner.lower() + '/' + repo.lower()
        filename = 'github-' + (owner.lower() + '-' + repo.lower())[:100] + '-' + digest(repository_key)[:12] + '.md'
        legacy_name = 'github-' + (owner + '-' + repo)[:110] + '.md'
        legacy_path = inside(workspace, 'inputs', case_id, legacy_name)
        if legacy_path.is_file():
            header = legacy_path.read_text(encoding='utf-8').splitlines()[:10]
            if ('仓库链接 ' + repository).casefold() in [line.casefold() for line in header]:
                filename = legacy_name
        file_payload = {'case_id': case_id, 'request_id': request_id,
                        'files': [{'name': filename, 'content_base64': base64.b64encode(content).decode()}]}
        saved = {'fingerprint': fingerprint, 'payload': file_payload, 'repository': repository,
                 'commit': commit, 'issues': issues,
                 'sources': [{'path': path, 'sha256': hashlib.sha256(text.encode()).hexdigest()} for path, text in documents]}
        write_json(record_path, saved)
    imported = import_materials(workspace, saved['payload'])
    result = {**imported, 'repository': saved['repository'], 'commit': saved['commit'], 'issues': saved['issues']}
    write_json(record_path, {**saved, 'result': result})
    return result
