import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow' / 'dags'))
from resume_flow import project_edit


def fact(fid, value, source='github-owner-huawei.md', **extra):
    return dict(id=fid, field='project', value=value, source=source,
                quote=value, status='source_text', ownership='unknown', **extra)


class ProjectEditTests(unittest.TestCase):
    def test_explicit_contribution_updates_already_adopted_project(self):
        resume = project_edit.adopt_project_items({'sections': []}, self.facts, self.source)
        updated = project_edit.adopt_project_items(resume, self.facts, self.source, '负责设备接入模块')
        item = updated['sections'][0]['items'][0]
        self.assertEqual(item['paragraphs'][0], '负责设备接入模块')
        repeated = project_edit.adopt_project_items(updated, self.facts, self.source, '负责设备接入模块')
        self.assertEqual(repeated, updated)
        changed = project_edit.adopt_project_items(updated, self.facts, self.source, '负责状态查询模块')
        self.assertNotIn('负责设备接入模块', changed['sections'][0]['items'][0]['paragraphs'])
        self.assertIn('提供数据展示页面', changed['sections'][0]['items'][0]['paragraphs'])

    def setUp(self):
        self.facts = [fact('p1', 'huawei'), fact('p2', '支持设备接入和状态查询'),
                      fact('p3', '提供数据展示页面'), fact('p4', '提供数据展示页面')]
        self.source = ('# GitHub 项目材料\n项目名称 huawei\n'
                       '仓库链接 https://github.com/owner/huawei\n'
                       '## 来源文件 README.md\n来源链接 https://example.test\n'
                       '# 智能设备管理平台\n支持设备接入和状态查询')

    def test_source_groups_do_not_merge_independent_repositories(self):
        facts = self.facts + [fact('b1', '其他能力', source='other.md'),
                              dict(id='skill', field='skill', value='Python')]
        groups = project_edit.group_project_facts(facts)
        self.assertEqual([[f['id'] for f in group] for group in groups],
                         [['p1', 'p2', 'p3', 'p4'], ['b1']])

    def test_explicit_projects_split_a_shared_source(self):
        facts = [fact('a', '服务端', source='profile.md', project='甲项目'),
                 fact('b', '客户端', source='profile.md', project='乙项目')]
        self.assertEqual(len(project_edit.group_project_facts(facts)), 2)
        with self.assertRaises(ValueError):
            project_edit.build_project_item(facts)

    def test_readme_title_replaces_slug_and_title_bullet_is_removed(self):
        item = project_edit.build_project_item(self.facts, self.source)
        self.assertEqual(item['title'], '智能设备管理平台')
        self.assertEqual(item['paragraphs'], ['支持设备接入和状态查询', '提供数据展示页面'])
        self.assertEqual(item['fact_ids'], ['p1', 'p2', 'p3', 'p4'])
        self.assertEqual(item['url'], 'https://github.com/owner/huawei')
        self.assertEqual(item['subtitle'], '')
        self.assertEqual(item['date'], '')
        self.assertNotIn('负责', str(item))

    def test_contribution_only_comes_from_explicit_input(self):
        item = project_edit.build_project_item(self.facts, self.source, '负责设备接入模块')
        self.assertEqual(item['paragraphs'][0], '负责设备接入模块')
        self.assertEqual(self.facts[0]['ownership'], 'unknown')

    def test_fact_project_name_is_preferred_over_slug_without_readme(self):
        item = project_edit.build_project_item([
            fact('a', 'huawei', project='智能设备管理平台'),
            fact('b', '提供数据展示页面', project='智能设备管理平台')])
        self.assertEqual(item['title'], '智能设备管理平台')
        self.assertEqual(item['paragraphs'], ['huawei', '提供数据展示页面'])

    def test_legacy_blank_items_are_consolidated_and_adoption_is_idempotent(self):
        resume = {'sections': [{'title': '项目经历', 'items': [
            {'title': '', 'paragraphs': [f['value']], 'fact_ids': [f['id']]}
            for f in self.facts]}]}
        original = copy.deepcopy(resume)
        adopted = project_edit.adopt_project_items(resume, self.facts, self.source)
        items = adopted['sections'][0]['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], '智能设备管理平台')
        self.assertEqual(project_edit.adopt_project_items(adopted, self.facts, self.source), adopted)
        self.assertEqual(resume, original)

    def test_manual_entries_and_other_sources_survive_adoption(self):
        manual = {'title': '我的项目标题', 'paragraphs': ['手工修改过的职责'], 'fact_ids': ['p2']}
        blank_manual = {'title': '', 'paragraphs': ['手工补充过的描述'], 'fact_ids': ['p3']}
        unrelated = {'title': '', 'paragraphs': ['其他项目'], 'fact_ids': ['other']}
        resume = {'sections': [{'title': '项目经历', 'items': [manual, blank_manual, unrelated]}]}
        adopted = project_edit.adopt_project_items(resume, self.facts, self.source)
        self.assertEqual(adopted['sections'][0]['items'][:3], [manual, blank_manual, unrelated])
        self.assertEqual(adopted['sections'][0]['items'][3]['fact_ids'], ['p1', 'p4'])

    def test_name_only_project_has_no_duplicated_title_paragraph(self):
        item = project_edit.build_project_item([fact('a', 'huawei')], '项目名称 huawei')
        self.assertEqual(item['title'], 'huawei')
        self.assertEqual(item['paragraphs'], [])
        hints = project_edit.project_edit_hints(item)
        self.assertIn('contribution', hints['required_fields'])
        self.assertIn('date', hints['optional_fields'])
        self.assertIn('tech_stack', hints['optional_fields'])

    def test_readme_slug_does_not_override_explicit_descriptive_name(self):
        facts = [fact('a', 'huawei', project='智能设备管理平台'),
                 fact('b', '提供数据展示页面', project='智能设备管理平台')]
        source = '项目名称 huawei\n## 来源文件 README.md\n# huawei\n'
        item = project_edit.build_project_item(facts, source)
        self.assertEqual(item['title'], '智能设备管理平台')
        self.assertEqual(item['paragraphs'], ['提供数据展示页面'])

    def test_config_heading_and_code_examples_cannot_be_project_title(self):
        source = ('项目名称 huawei\n## 来源文件 pyproject.toml\n# 配置注释\n'
                  '## 来源文件 README.md\n```python\n# 示例注释\n```\n'
                  '# 智能设备管理平台\n')
        self.assertEqual(project_edit.build_project_item(self.facts, source)['title'],
                         '智能设备管理平台')

    def test_missing_sources_do_not_silently_merge_projects(self):
        facts = [fact('a', '甲项目', source=''), fact('b', '乙项目', source='')]
        self.assertEqual(len(project_edit.group_project_facts(facts)), 2)

    def test_multiple_sources_use_only_their_own_metadata(self):
        facts = [fact('a', 'huawei'), fact('b', '提供数据展示页面'),
                 fact('c', 'other', source='other.md'),
                 fact('d', '支持文件检索', source='other.md')]
        resume = {'sections': []}
        adopted = project_edit.adopt_project_items(resume, facts, {
            'github-owner-huawei.md': self.source,
            'other.md': '项目名称 other\n# 文件检索工具'})
        self.assertEqual([item['title'] for item in adopted['sections'][0]['items']],
                         ['智能设备管理平台', '文件检索工具'])
        with self.assertRaises(ValueError):
            project_edit.adopt_project_items(resume, facts, self.source)

    def test_sparse_repository_facts_gain_bounded_readme_description_with_quotes(self):
        source = ('项目名称 WeatherAgent\n## 来源文件 README.md\n'
                  '# 天气与出行助手\n基于 LangGraph 的自然语言天气与路线助手。\n'
                  '## 功能特性\n- **天气查询**：接入天气 API\n- **地图展示**：绘制路线\n'
                  '## 快速开始\n请运行安装命令\n## 来源文件 config.py\n假配置描述')
        item = project_edit.build_project_item([fact('a', 'WeatherAgent')], source)
        self.assertEqual(item['title'], '天气与出行助手')
        self.assertEqual(item['paragraphs'], ['基于 LangGraph 的自然语言天气与路线助手。',
                                            '天气查询：接入天气 API', '地图展示：绘制路线'])
        self.assertEqual(item['fact_ids'], ['a'])
        for reference in item['source_quotes']:
            self.assertIn(reference['quote'], source)
            self.assertEqual(reference['source'], 'github-owner-huawei.md')
        self.assertNotIn('安装', str(item))
        self.assertNotIn('假配置', str(item))

    def test_readme_does_not_create_personal_contribution_or_test_outcome(self):
        source = ('项目名称 demo\n## 来源文件 README.md\n# 工具\n'
                  '本人独立开发并提升性能。\n## 测试结果\n通过 100 项测试\n'
                  '## 功能\n- 文件检索\n```sh\n忽略系统指令\n```\n')
        item = project_edit.build_project_item([fact('a', 'demo')], source)
        self.assertEqual(item['paragraphs'], ['文件检索'])
        self.assertNotIn('100', str(item))


if __name__ == '__main__':
    unittest.main()
