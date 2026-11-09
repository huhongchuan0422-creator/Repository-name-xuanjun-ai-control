"""Synthetic real-Center media reuse and unknown-result regressions.

The sole provider transport is patched; no request can leave this test process.
"""
import json
import unittest
from unittest.mock import patch

import test_community_merchant_onboarding as fixtures
from scripts.community_wechat_applyment import WechatApplyment, WechatMediaPending
from scripts.community_wechat_sp_readonly import PartnerOrderReader


class MediaIdempotency(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.MerchantAdmissionJourney()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.c = self.f.fx.center
        self.reader = PartnerOrderReader.__new__(PartnerOrderReader)
        self.reader._mchid = '1900000123'
        self.service = WechatApplyment(self.f.service, self.reader, submission_enabled=True)
        self.f.service.wechat_applyment = self.service
        self.app = self.f.upload(self.f.draft(), 'business_license')
        transport = patch('scripts.community_wechat_applyment.request',
                          side_effect=AssertionError('Unscripted provider IO forbidden'))
        self.provider = transport.start()
        self.addCleanup(transport.stop)

    def send(self, app=None, review=False):
        return self.f.call('wechat_media', dict(
            application=(app or self.app)['application'], kind='business_license'), review)

    def success(self, media_id='synthetic-media-one'):
        self.provider.side_effect = None
        self.provider.return_value = ({'media_id': media_id}, 'a' * 64)
        return self.send()

    def count(self, table, channel):
        return self.c.db.execute('SELECT count(*) FROM ' + table + ' WHERE channel=?',
                                 (channel,)).fetchone()[0]

    def withdraw(self, app=None):
        app = app or self.app
        return self.f.call('withdraw', dict(application=app['application'], revision=app['revision']))

    def receipts(self):
        rows = self.c.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_WECHAT_MEDIA'").fetchall()
        return [json.loads(self.c.decrypt(row['payload'], 'wechat-media:' + row['subject_idx'])) for row in rows]

    def test_same_source_reuses_one_post_and_original_media_id(self):
        first = self.success()
        self.provider.side_effect = AssertionError('Duplicate provider IO forbidden')
        self.assertEqual(self.send(), first)
        self.assertEqual(self.provider.call_count, 1)
        self.assertEqual(self.count('links', 'COMMUNITY_WECHAT_MEDIA'), 1)
        self.assertEqual(self.count('events', 'WECHAT_MEDIA_ATTEMPT'), 1)
        self.assertEqual(self.provider.call_args.args[1:3], ('POST', '/v3/merchant/media/upload'))

    def test_timeout_persists_intent_and_repeated_calls_never_repost(self):
        self.provider.side_effect = TimeoutError('synthetic unknown result')
        for _ in range(3):
            with self.assertRaisesRegex(WechatMediaPending, 'WECHAT_MEDIA_RESULT_UNKNOWN'):
                self.send()
        self.assertEqual(self.provider.call_count, 1)
        self.assertEqual(self.count('events', 'WECHAT_MEDIA_ATTEMPT'), 1)
        self.assertEqual(self.count('links', 'COMMUNITY_WECHAT_MEDIA'), 0)

    def test_invalid_response_remains_unknown_without_retry(self):
        self.provider.side_effect = None
        self.provider.return_value = ({'media_id': ''}, 'a' * 64)
        for _ in range(2):
            with self.assertRaises(WechatMediaPending):
                self.send()
        self.assertEqual(self.provider.call_count, 1)
        self.assertEqual(self.receipts(), [])

    def test_inflight_second_request_is_blocked_by_committed_intent(self):
        def sent(*args, **kwargs):
            with self.assertRaises(WechatMediaPending):
                self.send()
            return {'media_id': 'synthetic-inflight-success'}, 'b' * 64
        self.provider.side_effect = sent
        self.assertEqual(self.send()['media_id'], 'synthetic-inflight-success')
        self.assertEqual(self.provider.call_count, 1)

    def test_success_before_profile_save_is_reusable_after_service_reopen(self):
        first = self.success()
        self.service = WechatApplyment(self.f.service, self.reader, submission_enabled=True)
        self.f.service.wechat_applyment = self.service
        self.provider.side_effect = AssertionError('No replay after frontend save interruption')
        self.assertEqual(self.send(), first)
        self.assertEqual(self.provider.call_count, 1)

    def test_replaced_original_material_has_distinct_receipt(self):
        first = self.success()
        self.app = self.f.upload(self.app, 'business_license', b'%PDF-second synthetic document')
        second = self.success('synthetic-media-two')
        self.assertNotEqual(first['source_sha256'], second['source_sha256'])
        self.assertEqual(second['media_id'], 'synthetic-media-two')
        self.assertEqual(self.provider.call_count, 2)
        self.assertEqual(self.count('links', 'COMMUNITY_WECHAT_MEDIA'), 2)

    def test_different_application_does_not_reuse_same_bytes(self):
        first = self.success()
        old = self.app['application']
        self.withdraw()
        self.app = self.f.upload(self.f.draft(), 'business_license')
        self.assertNotEqual(self.app['application'], old)
        second = self.success('synthetic-other-application')
        self.assertEqual(first['source_sha256'], second['source_sha256'])
        self.assertEqual(second['media_id'], 'synthetic-other-application')
        self.assertEqual(self.provider.call_count, 2)

    def test_changed_service_merchant_cannot_reuse_receipt(self):
        self.success()
        self.reader._mchid = '1900000999'
        self.assertEqual(self.success('synthetic-other-provider')['media_id'], 'synthetic-other-provider')
        self.assertEqual(self.provider.call_count, 2)
        self.assertEqual(self.count('links', 'COMMUNITY_WECHAT_MEDIA'), 2)

    def test_cached_receipt_does_not_bypass_withdrawal(self):
        self.success()
        self.withdraw()
        with self.assertRaisesRegex(PermissionError, 'WITHDRAWN_APPLICATION_READ_ONLY'):
            self.send()
        self.assertEqual(self.provider.call_count, 1)
        self.assertEqual(len(self.receipts()), 1)

    def test_cached_receipt_does_not_bypass_material_expiry(self):
        self.app = self.f.upload(self.app, 'business_license', expires_at=self.c.now() + 10)
        self.success()
        self.f.fx.stage.now += 11
        with self.assertRaisesRegex(ValueError, 'EXPIRED_PRIVATE_MATERIAL'):
            self.send()
        self.assertEqual(self.provider.call_count, 1)

    def test_cached_receipt_does_not_bypass_applicant_epoch_or_other_identity(self):
        self.success()
        with self.assertRaises(PermissionError):
            self.send(review=True)
        self.c.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?', (self.f.fx.uid1,))
        with self.assertRaises(PermissionError):
            self.send()
        self.assertEqual(self.provider.call_count, 1)

    def test_source_replaced_before_send_is_rejected_without_io(self):
        original = self.c.decrypt
        changed = False
        def decrypt(data, aad):
            nonlocal changed
            value = original(data, aad)
            if aad.startswith('object:') and not changed:
                changed = True
                self.app = self.f.upload(self.app, 'business_license', b'%PDF-new source during preflight')
            return value
        with patch.object(self.c, 'decrypt', side_effect=decrypt):
            with self.assertRaisesRegex(ValueError, 'ORIGINAL_PRIVATE_MATERIAL_CHANGED'):
                self.send()
        self.provider.assert_not_called()
        self.assertEqual(self.count('events', 'WECHAT_MEDIA_ATTEMPT'), 0)

    def test_sent_then_withdrawn_preserves_authentic_receipt_not_new_submission(self):
        def sent(*args, **kwargs):
            self.withdraw()
            return {'media_id': 'synthetic-response-after-withdrawal'}, 'c' * 64
        self.provider.side_effect = sent
        result = self.send()
        self.assertEqual(result['media_id'], 'synthetic-response-after-withdrawal')
        self.assertEqual(self.receipts()[0]['media_id'], result['media_id'])
        self.assertEqual(self.f.call('read', dict(application=self.app['application']))['status'], 'WITHDRAWN')
        with self.assertRaises(PermissionError):
            self.send()
        self.assertEqual(self.provider.call_count, 1)

    def test_sent_then_session_revoked_keeps_evidence_but_denies_return(self):
        def sent(*args, **kwargs):
            self.c.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?', (self.f.fx.uid1,))
            return {'media_id': 'synthetic-response-after-revocation'}, 'd' * 64
        self.provider.side_effect = sent
        with self.assertRaises(PermissionError):
            self.send()
        self.assertEqual(self.receipts()[0]['media_id'], 'synthetic-response-after-revocation')
        self.assertEqual(self.provider.call_count, 1)


if __name__ == '__main__':
    unittest.main()
