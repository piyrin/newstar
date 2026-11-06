import base64
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow/dags'))
from resume_flow.github_materials import import_github, repository_url


class GithubImportTests(unittest.TestCase):
    def test_import_preserves_source_commit_and_retries_without_refetch(self):
        sha = 'a' * 40
        reader = Mock()
        encoded = lambda text: {'encoding': 'base64', 'size': len(text), 'content': base64.b64encode(text.encode()).decode(), 'path': 'README.md'}
        reader.get.side_effect = [{'default_branch': 'main', 'name': 'demo', 'description': '示例项目'},
                                 {'commit': {'sha': sha}},
                                 [{'name': 'pyproject.toml', 'type': 'file', 'size': 20}],
                                 encoded('Project demo README'), encoded('[project]\nname="demo"')]
        with tempfile.TemporaryDirectory() as tmp:
            payload = {'case_id': 'personal', 'request_id': 'git1', 'url': 'https://github.com/example/demo', 'contribution': '本人负责测试'}
            result = import_github(Path(tmp), payload, reader)
            self.assertEqual(result['commit'], sha)
            text = (Path(tmp) / 'inputs/personal' / result['files'][0]['stored_name']).read_text(encoding='utf-8')
            self.assertIn(sha, text)
            self.assertIn('本人负责测试', text)
            self.assertIn('Project demo README', text)
            self.assertEqual(import_github(Path(tmp), payload, reader), result)
            self.assertEqual(reader.get.call_count, 5)

    def test_only_github_repo_urls_are_accepted(self):
        for value in ('http://127.0.0.1/x/y', 'https://github.com@evil.test/a/b', 'https://github.com/a/b/tree/main', 'https://github.com/a/..'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                repository_url(value)
        self.assertEqual(repository_url('https://github.com/user/project.git'), ('user', 'project'))

    def test_different_owner_repo_combinations_keep_distinct_materials(self):
        with tempfile.TemporaryDirectory() as tmp:
            filenames = []
            for index, url in enumerate(('https://github.com/a-b/c', 'https://github.com/a/b-c')):
                reader = Mock()
                reader.get.side_effect = [{'default_branch': 'main', 'name': 'demo'}, {'commit': {'sha': 'a' * 40}}, [],
                                         {'encoding': 'base64', 'size': 6, 'content': base64.b64encode(b'README').decode()}]
                result = import_github(Path(tmp), {'case_id': 'projects', 'request_id': 'repo' + str(index), 'url': url}, reader)
                filenames.append(result['files'][0]['stored_name'])
            self.assertNotEqual(filenames[0], filenames[1])
            self.assertEqual(len(list((Path(tmp) / 'inputs/projects').glob('*.md'))), 2)


if __name__ == '__main__':
    unittest.main()
