import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CommunityAdminOwnerThreeAcceptance(unittest.TestCase):
    def test_contract_requires_same_page_no_default_form_and_data_isolation(self):
        contract = json.loads((ROOT / "deploy/community-preview/community-admin-ui-contract.json").read_text())
        navigation = contract["reviewer_navigation"]
        self.assertEqual(navigation["navigation_mode"], "SAME_DOCUMENT_PANEL")
        self.assertEqual(navigation["route_switch_method"], "HISTORY_REPLACE_STATE_NO_DOCUMENT_NAVIGATION")
        self.assertEqual(navigation["default_form_policy"], "HIDDEN_UNTIL_EXPLICIT_ACTION")
        self.assertEqual(navigation["entry_data_policy"], "SELECTED_ENTRY_ONLY")
        self.assertEqual(navigation["required_entry_count"], 17)
        entry = navigation["merchant_review_workspace_entry"]
        self.assertEqual(entry["navigation"], "TOP_DOCUMENT_UNCHANGED")
        self.assertEqual(entry["rendering"], "ON_DEMAND_SAME_WORKSPACE_PANEL")
        self.assertEqual(entry["standalone_review_chrome"], "HIDDEN_WHEN_EMBEDDED")
        self.assertEqual(entry["covered_entries"], ["商家审核", "待审核商家数", "商家入驻审核", "入驻审核"])

    def test_reviewer_navigation_is_current_page_only_and_field_complete(self):
        script = (ROOT / "demos/community-stage/onboarding.js").read_text()
        self.assertIn("['申请编号','商家名称','门店名称','主体类型','联系人','经营类目','申请状态','微信进件','申请分账比例','操作']", script)
        self.assertIn("keyword.placeholder='申请编号、商家名称、门店名称、联系人、经营类目、申请状态'", script)
        self.assertIn("const groups=[['总览'", script)
        self.assertNotIn("['积分商城'", script)
        self.assertNotIn("['交易与分账'", script)
        self.assertNotIn("真实列表、状态和操作须由该入口的原权限与接口回读后显示", script)

    def test_selected_entry_hides_review_data_and_starts_without_a_form(self):
        script = (ROOT / "demos/community-stage/onboarding.js").read_text()
        styles = (ROOT / "demos/community-stage/onboarding.css").read_text()
        self.assertIn("$('detail').hidden=true", script)
        self.assertIn("renderReviewList($('applications'),[],async()=>{})", script)
        self.assertIn(".review-list-table", styles)
        self.assertIn("#status:empty", styles)
        self.assertNotIn("localPage.append(localHeading,localStatus,", script)


if __name__ == "__main__":
    unittest.main()
