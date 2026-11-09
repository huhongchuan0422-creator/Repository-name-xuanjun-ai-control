"""Owner submission through the original encrypted service, synthetic signed wire only."""
import copy
import unittest
from unittest.mock import patch
import test_community_applyment_rejection_recovery as recovery
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_wechat_sp_readonly import PartnerOrderReader


class ApplicantApplyment(unittest.TestCase):
    setUpClass = classmethod(recovery.RejectionRecovery.setUpClass.__func__)
    call = recovery.RejectionRecovery.call
    response = recovery.RejectionRecovery.response
    read = recovery.RejectionRecovery.read
    attempts = recovery.RejectionRecovery.attempts
    signed_wire = recovery.RejectionRecovery.signed_wire
    wire_response = recovery.RejectionRecovery.wire_response
    query_data = recovery.RejectionRecovery.query_data

    def setUp(self):
        self.fx = recovery.fixture.MerchantAdmissionJourney()
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        app = self.fx.draft(sales_scenes_type=['SALES_SCENES_MINI_PROGRAM'])
        for kind in app['required_materials']:
            app = self.fx.upload(app, kind)
        self.application = app['application']
        self.center = self.fx.fx.center
        self.reader = PartnerOrderReader.__new__(PartnerOrderReader)
        self.reader._mchid = '1900000123'
        self.reader._public = self.public
        self.service = WechatApplyment(self.fx.service, self.reader, submission_enabled=True)
        self.fx.service.wechat_applyment = self.service
        boundary = patch('scripts.community_wechat_applyment.request',
                         side_effect=AssertionError('Unscripted provider IO forbidden'))
        self.provider = boundary.start()
        self.addCleanup(boundary.stop)
        for kind, media in [('business_license','media-license'),('identity_front','media-front'),
                            ('identity_back','media-back'),('mini_program_screenshot','media-mini')]:
            with self.response({'media_id':media}):
                self.call('wechat_media', kind=kind)
        self.call('wechat_save', expected_version=0, profile=copy.deepcopy(recovery.profile()))
        self.provider.reset_mock()

    def apply(self):
        return self.call('wechat_apply', expected_version=self.read()['version'])

    def signed_apply(self):
        with self.wire_response(self.signed_wire({'applyment_id':123456789})) as fetch:
            result = self.apply()
        self.assertEqual(fetch.call_count, 1)
        return result

    def test_owner_draft_without_either_internal_approval_receives_signed_ack(self):
        self.assertEqual(self.call('read')['status'], 'DRAFT')
        self.assertEqual(self.read()['state'], 'DRAFT')
        result = self.signed_apply()
        self.assertEqual(result['state'], 'SUBMITTED_TO_PROVIDER')
        self.assertEqual(result['applyment_id'], '123456789')
        self.assertNotIn('reviewer', result)
        self.assertEqual(len(self.attempts()), 1)

    def test_other_identity_including_reviewer_cannot_use_owner_apply_or_status(self):
        for op, params in [('wechat_apply', {'expected_version':self.read()['version']}), ('wechat_status', {})]:
            with self.subTest(op=op), self.assertRaises(PermissionError):
                self.call(op, review=True, **params)
        self.provider.assert_not_called()
        self.assertEqual(self.attempts(), [])

    def test_withdrawn_application_cannot_send(self):
        app = self.call('read')
        self.call('withdraw', revision=app['revision'])
        with self.assertRaises(PermissionError):
            self.apply()
        self.provider.assert_not_called()
        self.assertEqual(self.attempts(), [])

    def test_revoked_session_cannot_send(self):
        self.center.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?', (self.fx.fx.uid1,))
        with self.assertRaises(PermissionError):
            self.apply()
        self.provider.assert_not_called()
        self.assertEqual(self.attempts(), [])

    def test_repeated_success_does_not_post_again(self):
        self.signed_apply()
        self.provider.reset_mock()
        with self.assertRaises(PermissionError):
            self.apply()
        self.provider.assert_not_called()
        self.assertEqual(len(self.attempts()), 1)

    def test_unknown_response_records_intent_and_never_reposts(self):
        with self.response(error=TimeoutError('Synthetic lost reply')):
            with self.assertRaises(TimeoutError):
                self.apply()
        self.assertEqual(self.read()['state'], 'SUBMISSION_UNKNOWN')
        self.provider.reset_mock()
        with self.assertRaises(PermissionError):
            self.apply()
        self.provider.assert_not_called()
        self.assertEqual(len(self.attempts()), 1)

    def test_owner_status_verifies_signed_response_and_exposes_official_state(self):
        self.signed_apply()
        wire = self.signed_wire(self.query_data('APPLYMENT_STATE_AUDITING'))
        with self.wire_response(wire) as fetch:
            result = self.call('wechat_status')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(result['provider_state'], 'APPLYMENT_STATE_AUDITING')
        self.assertTrue(result['provider_query_signature_sha256'])
        self.assertEqual(self.call('read')['wechat_submerchant_state'], 'APPLYMENT_STATE_AUDITING')

    def test_owner_status_rejects_tampered_wire_without_updating_result(self):
        self.signed_apply()
        before = copy.deepcopy(self.read())
        headers, raw = self.signed_wire(self.query_data('APPLYMENT_STATE_AUDITING'))
        with self.wire_response((headers,raw+b' ')):
            with self.assertRaises((PermissionError,ValueError)):
                self.call('wechat_status')
        self.assertEqual(self.read(), before)

    def test_original_reviewer_execute_still_requires_both_approvals(self):
        with self.assertRaisesRegex(PermissionError,'SEPARATE_INTERNAL_AND_PLATFORM_APPROVAL_REQUIRED'):
            self.call('wechat_execute', expected_version=self.read()['version'])
        self.provider.assert_not_called()
        self.assertEqual(self.attempts(), [])

    def test_unknown_submission_recovers_with_owner_signed_get_not_new_post(self):
        with self.response(error=TimeoutError('Synthetic lost reply')):
            with self.assertRaises(TimeoutError):
                self.apply()
        with self.wire_response(self.signed_wire(self.query_data('APPLYMENT_STATE_AUDITING'))) as fetch:
            result = self.call('wechat_status')
        # Same-business signed query recovers the owner's first unknown submission.
        self.assertEqual(result['state'], 'SUBMITTED_TO_PROVIDER')
        self.assertEqual(result['submission_recovery_receipt']['business_code'], result['business_code'])
        self.assertEqual(result['provider_state'], 'APPLYMENT_STATE_AUDITING')
        self.assertEqual(result['applyment_id'], '123456789')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.args[0].get_method(), 'GET')
        self.assertEqual(len(self.attempts()), 1)

    def test_inflight_second_owner_submit_cannot_duplicate_post(self):
        def concurrent_click(*args, **kwargs):
            with self.assertRaises(PermissionError):
                self.apply()
        with self.response({'applyment_id':123456789}, hook=concurrent_click):
            result = self.apply()
        self.assertEqual(result['state'], 'SUBMITTED_TO_PROVIDER')
        self.assertEqual(self.provider.call_count, 1)
        self.assertEqual(len(self.attempts()), 1)

    def test_original_instance_capability_gate_is_not_bypassed(self):
        self.service.enabled = False
        with self.assertRaisesRegex(PermissionError, 'REAL_MERCHANT_SUBMISSION_GATE_CLOSED'):
            self.apply()
        self.provider.assert_not_called()
        self.assertEqual(self.attempts(), [])

    def owner_signed_status(self, state, **extra):
        with self.wire_response(self.signed_wire(self.query_data(state, **extra))):
            return self.call('wechat_status')

    def test_owner_apply_freezes_original_draft_without_platform_approval(self):
        before = self.call('read')
        result = self.signed_apply()
        current = self.call('read')
        self.assertEqual(current['status'], 'SUBMITTED')
        self.assertGreater(current['revision'], before['revision'])
        self.assertTrue(result['applicant_direct_submission'])
        self.assertNotIn('reviewer', result)
        self.assertFalse(current['payment_enabled'])
        self.assertNotEqual(current['opening_state'], 'OPENED')

    def test_signed_rejection_unlocks_owner_correction_and_reuses_business_code(self):
        first = self.signed_apply()
        code = first['business_code']
        rejected = self.owner_signed_status('APPLYMENT_STATE_REJECTED')
        platform = self.call('read')
        self.assertEqual(rejected['state'], 'CORRECTION')
        self.assertEqual(platform['status'], 'CORRECTION_REQUIRED')
        events = self.center.db.execute(
            "SELECT actor,event FROM onboarding_events WHERE application=? AND event='WECHAT_OFFICIAL_CORRECTION'",
            (self.application,)).fetchall()
        self.assertEqual([tuple(row) for row in events], [(self.fx.fx.uid1,'WECHAT_OFFICIAL_CORRECTION')])
        self.assertNotIn('reviewer', rejected)
        changed = copy.deepcopy(rejected['profile'])
        changed['business_info']['merchant_shortname'] = 'Corrected Owner Shop'
        saved = self.call('wechat_save', expected_version=rejected['version'], profile=changed)
        self.assertEqual(saved['correction_receipt'], rejected['correction_receipt'])
        second = self.signed_apply()
        self.assertEqual(second['business_code'], code)
        self.assertEqual(second['profile']['business_info']['merchant_shortname'], 'Corrected Owner Shop')
        self.assertEqual(second['applyment_id'], first['applyment_id'])
        self.assertEqual(self.call('read')['status'], 'SUBMITTED')
        self.assertTrue(second['applicant_direct_submission'])
        self.assertNotIn('reviewer', second)
        self.assertNotIn('correction_receipt', second)
        self.assertEqual(self.attempts(), sorted([code,code+':revision:'+str(saved['version'])]))
        self.assertEqual(len(second['consumed_rejections']), 1)

    def test_other_identity_query_cannot_unlock_owner_platform_correction(self):
        self.signed_apply()
        before = self.call('read')
        self.provider.reset_mock()
        with self.assertRaises(PermissionError):
            self.call('wechat_status', review=True)
        self.provider.assert_not_called()
        self.assertEqual(self.call('read')['status'], 'SUBMITTED')
        self.assertEqual(self.call('read')['revision'], before['revision'])
        self.assertEqual(self.center.db.execute(
            "SELECT count(*) FROM onboarding_events WHERE application=? AND event='WECHAT_OFFICIAL_CORRECTION'",
            (self.application,)).fetchone()[0], 0)

    def test_official_finish_does_not_approve_platform_or_enable_payments(self):
        self.signed_apply()
        result = self.owner_signed_status('APPLYMENT_STATE_FINISHED', sub_mchid='1900000999')
        self.assertEqual(result['provider_state'], 'APPLYMENT_STATE_FINISHED')
        self.assertEqual(result['provider_sub_mchid'], '1900000999')
        view = self.call('read')
        self.assertEqual(view['wechat_submerchant_state'], 'APPLYMENT_STATE_FINISHED')
        self.assertEqual(view['status'], 'SUBMITTED')
        self.assertFalse(view['payment_enabled'])
        self.assertNotEqual(view['opening_state'], 'OPENED')

    def test_signed_rejection_also_unlocks_in_review_original_platform(self):
        self.signed_apply()
        platform = self.call('read')
        # Real original reviewer starts review; no approval is granted.
        self.fx.call('review', dict(application=self.application, revision=platform['revision'],
                                   action='BEGIN_REVIEW', note='Synthetic review started'), True)
        self.assertEqual(self.call('read')['status'], 'IN_REVIEW')
        self.owner_signed_status('APPLYMENT_STATE_REJECTED')
        self.assertEqual(self.call('read')['status'], 'CORRECTION_REQUIRED')

    def test_tampered_rejection_does_not_unlock_platform_or_create_correction_event(self):
        self.signed_apply()
        before = self.call('read')
        headers, raw = self.signed_wire(self.query_data('APPLYMENT_STATE_REJECTED'))
        with self.wire_response((headers, raw+b' ')):
            with self.assertRaises((PermissionError,ValueError)):
                self.call('wechat_status')
        self.assertEqual(self.call('read')['status'], 'SUBMITTED')
        self.assertEqual(self.call('read')['revision'], before['revision'])
        self.assertNotIn('correction_receipt', self.read())
        self.assertEqual(self.center.db.execute(
            "SELECT count(*) FROM onboarding_events WHERE application=? AND event='WECHAT_OFFICIAL_CORRECTION'",
            (self.application,)).fetchone()[0], 0)
