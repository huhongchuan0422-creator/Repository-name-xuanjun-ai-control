import unittest
from pathlib import Path

from scripts.community_wechat_applyment import (
    official_signing_url,
    provider_workflow,
    provider_workflow_view,
)


class WechatWorkflow(unittest.TestCase):
    def test_every_official_state_has_the_expected_operator_bucket(self):
        expected = {
            'APPLYMENT_STATE_AUDITING': 'PENDING_REVIEW',
            'APPLYMENT_STATE_TO_BE_CONFIRMED': 'PENDING_CONFIRMATION',
            'APPLYMENT_STATE_TO_BE_SIGNED': 'PENDING_CONFIRMATION',
            'APPLYMENT_STATE_SIGNING': 'OPENING',
            'APPLYMENT_STATE_EDITTING': 'CORRECTION_OR_REJECTION',
            'APPLYMENT_STATE_REJECTED': 'CORRECTION_OR_REJECTION',
            'APPLYMENT_STATE_CANCELED': 'EXCEPTION',
            'APPLYMENT_STATE_FINISHED': 'COMPLETED',
        }
        self.assertEqual({state: provider_workflow(state) for state in expected}, expected)

    def test_unsubmitted_is_not_misreported_as_provider_review(self):
        for state in (None, 'NOT_SUBMITTED', 'NOT_VERIFIED'):
            self.assertEqual(provider_workflow(state), 'PENDING_SUBMISSION')
        self.assertEqual(provider_workflow('NEW_PROVIDER_STATE'), 'EXCEPTION')

    def test_completed_leaves_default_todo_and_signed_link_is_actionable_only_when_due(self):
        proof = {'signed_at': 1, 'signature_sha256': 'a' * 64}
        due = provider_workflow_view({
            'provider_state': 'APPLYMENT_STATE_TO_BE_CONFIRMED',
            'provider_sign_url': 'https://pay.weixin.qq.com/public/apply4ec_sign/s?x=1',
            'provider_sign_url_proof': proof,
        })
        self.assertFalse(due['completed'])
        self.assertTrue(due['sign_action_available'])
        finished = provider_workflow_view({
            'provider_state': 'APPLYMENT_STATE_FINISHED',
            'provider_sign_url': 'https://pay.weixin.qq.com/public/apply4ec_sign/s?x=1',
            'provider_sign_url_proof': proof,
        })
        self.assertTrue(finished['completed'])
        self.assertFalse(finished['sign_action_available'])

    def test_only_verified_wechat_payment_signing_route_is_accepted(self):
        good = 'https://pay.weixin.qq.com/public/apply4ec_sign/s?token=abc'
        self.assertEqual(official_signing_url(good), good)
        for value in (
            'http://pay.weixin.qq.com/public/apply4ec_sign/s?token=abc',
            'https://example.org/public/apply4ec_sign/s?token=abc',
            'https://pay.weixin.qq.com/public/other?token=abc',
            'https://pay.weixin.qq.com/public/apply4ec_sign/s',
            'https://pay.weixin.qq.com/public/apply4ec_sign/s?token=abc#fragment',
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                official_signing_url(value)

    def test_management_ui_defaults_to_todo_and_uses_only_the_existing_query_operation(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / 'demos/community-stage/onboarding.js').read_text()
        markup = (root / 'demos/community-stage/onboarding.html').read_text()
        styles = (root / 'demos/community-stage/onboarding.css').read_text()
        self.assertIn("['ACTIVE','微信待办（默认）']", script)
        self.assertIn("app.wechat_provider_workflow?.bucket!=='COMPLETED'", script)
        self.assertIn("await request('wechat_query',{application})", script)
        self.assertIn('},300000)', script)
        self.assertIn("bucket==='PENDING_CONFIRMATION'", script)
        self.assertIn('r.provider_sign_url&&r.provider_sign_url_proof', script)
        self.assertIn('复制微信实名确认链接', script)
        self.assertIn('<div id="wechatState"></div>', markup)
        self.assertIn('grid-template-columns:minmax(0,720px)', styles)


if __name__ == '__main__':
    unittest.main()
