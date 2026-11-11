import unittest
from extended_release_facts import extended_release_fact_issues


class AdditionalKnownClaims(unittest.TestCase):
    def setUp(self):
        self.facts={'features':['本地Markdown课程笔记索引','按课程搜索','导出CSV索引'],
                    'feedback_fields':['issue_id','course','description','status'],
                    'license':'MIT','privacy':'材料留在本机'}

    def issues(self,text,facts=None):
        return extended_release_fact_issues(facts or self.facts,{'DOC-1':{'content':text}})

    def test_export_capability_does_not_prove_existing_ui_or_service_url(self):
        self.assertTrue(self.issues('导出数据：在管理界面或命令行中调用导出功能。'))
        self.assertTrue(self.issues('服务启动后，请在浏览器访问 http://localhost:4177 进行浏览和搜索。'))
        self.assertFalse(self.issues('管理界面和导出入口未知，暂未提供。'))
        self.assertFalse(self.issues('管理界面未提供导出入口。'))
        self.assertTrue(self.issues('管理界面导出CSV；默认端口未知。'))
        self.assertFalse(self.issues('如有浏览器界面，需先确认访问地址；本材料未提供URL。'))
        self.assertFalse(self.issues('在管理界面导出CSV。',{**self.facts,'export_ui_or_cli_entrypoint':'管理界面导出CSV'}))

    def test_mit_does_not_create_a_modified_source_distribution_ban(self):
        self.assertTrue(self.issues('遵守 MIT 协议，不修改源码分发。'))
        self.assertFalse(self.issues('MIT 允许使用、复制、修改和分发，需保留许可声明。'))
        self.assertFalse(self.issues('MIT 并非禁止修改源码分发。'))
        self.assertFalse(self.issues('贡献者无权直接修改官方仓库，可提交PR。'))

    def test_local_storage_is_not_a_zero_leakage_guarantee(self):
        self.assertTrue(self.issues('所有操作均在本地完成，无外部数据泄露风险。'))
        self.assertFalse(self.issues('本地留存不能证明无外部数据泄露风险。'))
        self.assertFalse(self.issues('材料留在本机；实际安全风险尚未评估。'))


if __name__=='__main__':unittest.main()
