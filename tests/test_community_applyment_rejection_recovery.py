"""Rejected applyment recovery against the real encrypted Center and review flow.

All accounts, documents and provider responses are synthetic. Only the already
verified transport boundary is replaced; no provider request leaves this test.
"""
import base64
import contextlib
import copy
import hashlib
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import test_community_merchant_onboarding as fixture
from test_community_applyment_conditions import profile
from scripts.community_merchant_onboarding import MerchantOnboarding
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_wechat_sp_readonly import PartnerOrderReader
from scripts.pr122_customer_core import canonical


class RejectionRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public = cls.private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)

    def setUp(self):
        self.fx = fixture.MerchantAdmissionJourney()
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.platform = self.fx.review(self.fx.complete(), 'APPROVE')
        self.application = self.platform['application']
        self.center = self.fx.fx.center
        self.reader = PartnerOrderReader.__new__(PartnerOrderReader)
        self.reader._mchid = '1900000123'
        self.reader._public = self.public
        self.service = WechatApplyment(self.fx.service, self.reader, submission_enabled=True)
        self.fx.service.wechat_applyment = self.service
        boundary = patch('scripts.community_wechat_applyment.request',
                         side_effect=AssertionError('Unscripted provider request forbidden'))
        self.provider = boundary.start()
        self.addCleanup(boundary.stop)
        self.profile = profile()
        for kind, media_id in (('business_license', 'media-license'),
                               ('identity_front', 'media-front'),
                               ('identity_back', 'media-back')):
            with self.response(dict(media_id=media_id)):
                uploaded = self.call('wechat_media', kind=kind)
            self.assertEqual(uploaded['media_id'], media_id)
        self.provider.reset_mock()

    def call(self, operation, review=None, **params):
        if review is None:
            review = operation in ('wechat_query', 'wechat_execute', 'wechat_review',
                                   'wechat_review_read')
        return self.fx.call(operation, dict(application=self.application, **params), review)

    @contextlib.contextmanager
    def response(self, data=None, digest='a' * 64, hook=None, error=None):
        def returned(*args, **kwargs):
            if hook:
                hook(*args, **kwargs)
            if error is not None:
                raise error
            return copy.deepcopy(data), digest
        previous = self.provider.side_effect
        self.provider.side_effect = returned
        try:
            yield
        finally:
            self.provider.side_effect = previous

    def read(self):
        return self.service._read(self.application)

    def replace_record(self, record):
        # A competing valid writer/fault injection; production paths stay intact.
        with self.center.tx():
            self.service._save(self.application, self.fx.fx.uid1, record)

    def approve(self, revised_profile=None):
        prior = self.read()
        saved = self.call('wechat_save', expected_version=prior['version'] if prior else 0,
                          profile=copy.deepcopy(revised_profile or self.profile))
        pending = self.call('wechat_submit_review', expected_version=saved['version'])
        return self.call('wechat_review', expected_version=pending['version'],
                         decision='INTERNAL_APPROVED', opinion='Synthetic independent review')

    def execute(self, applyment_id=123456789, hook=None, error=None):
        with self.response(dict(applyment_id=applyment_id), hook=hook, error=error):
            return self.call('wechat_execute', expected_version=self.read()['version'])

    def query(self, state='APPLYMENT_STATE_REJECTED', digest='b' * 64, hook=None, **extra):
        data = dict(business_code=self.read()['business_code'], applyment_state=state,
                    audit_detail=[dict(field='merchant_shortname', reject_reason='Synthetic correction')])
        data.update(extra)
        with self.response(data, digest, hook):
            return self.call('wechat_query')

    def submitted(self):
        self.approve()
        return self.execute()

    def attempts(self):
        return [r[0] for r in self.center.db.execute(
            "SELECT event_id FROM events WHERE channel='WECHAT_APPLYMENT_ATTEMPT' ORDER BY event_id")]

    def test_full_same_code_correction_independent_review_and_finish(self):
        first = self.submitted()
        code = first['business_code']
        self.assertEqual(code, 'ap' + hashlib.sha256(canonical(
            [self.reader._mchid, self.application, first['version']])).hexdigest()[:30])
        self.assertEqual(self.attempts(), [code])
        payload = self.provider.call_args.args[3]
        self.assertEqual(payload['business_code'], code)
        encrypted = payload['contact_info']['contact_name']
        self.assertNotEqual(encrypted, self.profile['contact_info']['contact_name'])
        self.assertEqual(self.private.decrypt(base64.b64decode(encrypted), padding.OAEP(
            mgf=padding.MGF1(hashes.SHA1()), algorithm=hashes.SHA1(), label=None)).decode(),
            self.profile['contact_info']['contact_name'])
        correction = self.query()
        self.assertEqual(correction['state'], 'CORRECTION')
        self.assertEqual(correction['version'], first['version'] + 1)
        changed = copy.deepcopy(self.profile)
        changed['business_info']['merchant_shortname'] = 'Corrected Synthetic Shop'
        saved = self.call('wechat_save', expected_version=correction['version'], profile=changed)
        self.assertEqual(saved['business_code'], code)
        self.assertEqual(saved['correction_receipt'], correction['correction_receipt'])
        self.assertEqual(saved['applyment_id'], first['applyment_id'])
        with self.assertRaises(PermissionError):
            self.call('wechat_execute', expected_version=saved['version'])
        pending = self.call('wechat_submit_review', expected_version=saved['version'])
        with self.assertRaises(PermissionError):
            self.call('wechat_review', review=False, expected_version=pending['version'],
                      decision='INTERNAL_APPROVED', opinion='No self-review')
        reviewed = self.call('wechat_review', expected_version=pending['version'],
                             decision='INTERNAL_APPROVED', opinion='Rechecked correction')
        second = self.execute()
        self.assertEqual(second['business_code'], code)
        self.assertNotIn('correction_receipt', second)
        self.assertEqual(self.provider.call_args.args[3]['business_info']['merchant_shortname'],
                         'Corrected Synthetic Shop')
        self.assertEqual(self.attempts(), sorted([code, code + ':revision:' + str(reviewed['version'])]))
        self.query('APPLYMENT_STATE_AUDITING')
        finished = self.query('APPLYMENT_STATE_FINISHED', sub_mchid='1900000999')
        self.assertEqual(finished['provider_sub_mchid'], '1900000999')
        view = self.fx.call('read', dict(application=self.application))
        self.assertFalse(view['payment_enabled'])
        self.assertEqual(view['wechat_submerchant_state'], 'APPLYMENT_STATE_FINISHED')
        self.assertEqual(self.center.check_integrity()['integrity'], 'PASS')

    def test_unknown_cannot_edit_review_or_replay_before_rejected_query(self):
        self.approve()
        with self.assertRaises(TimeoutError):
            self.execute(error=TimeoutError('Synthetic transport uncertainty'))
        unknown = self.read()
        self.assertEqual(unknown['state'], 'SUBMISSION_UNKNOWN')
        self.assertNotIn('correction_receipt', unknown)
        self.provider.reset_mock()
        for operation, params in (
                ('wechat_save', dict(profile=self.profile)),
                ('wechat_submit_review', {}), ('wechat_execute', {})):
            with self.subTest(operation=operation), self.assertRaises(PermissionError):
                self.call(operation, expected_version=unknown['version'], **params)
        self.provider.assert_not_called()
        observed = self.query('APPLYMENT_STATE_AUDITING')
        self.assertEqual(observed['state'], 'SUBMISSION_UNKNOWN')
        correction = self.query()
        self.assertEqual(correction['version'], unknown['version'] + 1)
        self.approve()
        retried = self.execute()
        self.assertEqual(retried['business_code'], unknown['business_code'])
        self.assertEqual(len(self.attempts()), 2)

    def test_unverified_query_failure_does_not_open_correction(self):
        submitted = self.submitted()
        with self.response(error=PermissionError('Synthetic signature verification failure')):
            with self.assertRaises(PermissionError):
                self.call('wechat_query')
        self.assertEqual(self.read(), submitted)
        self.assertNotIn('correction_receipt', self.read())

    def test_duplicate_rejection_does_not_increment_or_duplicate_attempt(self):
        self.submitted()
        first = self.query()
        second = self.query(digest='c' * 64)
        self.assertEqual(second['state'], 'CORRECTION')
        self.assertEqual(second['version'], first['version'])
        self.assertEqual(second['correction_receipt'], first['correction_receipt'])
        self.assertEqual(len(self.attempts()), 1)

    def test_three_successive_correction_cycles_reuse_code_with_distinct_intents(self):
        first = self.submitted()
        code = first['business_code']
        expected = [code]
        for cycle in range(3):
            self.fx.fx.stage.now += 61
            correction = self.query(digest=str(cycle + 1) * 64)
            self.assertEqual(correction['state'], 'CORRECTION')
            changed = copy.deepcopy(self.profile)
            changed['business_info']['merchant_shortname'] = 'Synthetic revision ' + str(cycle)
            approved = self.approve(changed)
            expected.append(code + ':revision:' + str(approved['version']))
            result = self.execute()
            self.assertEqual(result['business_code'], code)
            self.assertNotIn('correction_receipt', result)
        self.assertEqual(self.attempts(), sorted(expected))

    def test_query_rejects_new_version_committed_during_network_call(self):
        submitted = self.submitted()
        competing = dict(submitted, version=submitted['version'] + 1)
        with self.assertRaisesRegex(ValueError, 'APPLYMENT_CHANGED'):
            self.query(hook=lambda *a, **k: self.replace_record(competing))
        self.assertEqual(self.read(), competing)

    def test_query_rejects_same_version_profile_change_during_network_call(self):
        submitted = self.submitted()
        competing = copy.deepcopy(submitted)
        competing['profile']['business_info']['merchant_shortname'] = 'Concurrent draft'
        with self.assertRaisesRegex(ValueError, 'APPLYMENT_CHANGED'):
            self.query(hook=lambda *a, **k: self.replace_record(competing))
        self.assertEqual(self.read(), competing)

    def test_execute_response_cannot_overwrite_new_reserved_version(self):
        approved = self.approve()
        def race(*args, **kwargs):
            competing = self.read()
            self.assertEqual(competing['state'], 'SUBMISSION_UNKNOWN')
            competing['version'] += 1
            self.replace_record(competing)
        with self.assertRaisesRegex(ValueError, 'APPLYMENT_SUBMISSION_RACE_QUERY_EXISTING_ONLY'):
            self.execute(hook=race)
        self.assertEqual(self.read()['version'], approved['version'] + 1)
        self.assertEqual(self.read()['state'], 'SUBMISSION_UNKNOWN')
        self.assertNotIn('applyment_id', self.read())
        self.assertEqual(len(self.attempts()), 1)

    def test_execute_response_cannot_overwrite_rejection_opened_by_query(self):
        self.approve()
        def race(*args, **kwargs):
            self.query()
        with self.assertRaisesRegex(ValueError, 'APPLYMENT_SUBMISSION_RACE_QUERY_EXISTING_ONLY'):
            self.execute(hook=race)
        self.assertEqual(self.read()['state'], 'CORRECTION')
        self.assertIn('correction_receipt', self.read())
        self.assertNotIn('applyment_id', self.read())

    def test_duplicate_execute_is_blocked_while_first_request_is_in_flight(self):
        self.approve()
        def duplicate(*args, **kwargs):
            with self.assertRaises(PermissionError):
                self.call('wechat_execute', expected_version=self.read()['version'])
        self.provider.reset_mock()
        self.execute(hook=duplicate)
        self.assertEqual(self.provider.call_count, 1)
        self.assertEqual(len(self.attempts()), 1)
        with self.assertRaises(PermissionError):
            self.call('wechat_execute', expected_version=self.read()['version'])
        self.assertEqual(self.provider.call_count, 1)

    def test_reviewer_revoked_during_query_cannot_persist_rejection(self):
        submitted = self.submitted()
        def revoke(*args, **kwargs):
            self.center.db.execute('UPDATE members SET active=0 WHERE user_id=?', (self.fx.fx.uid2,))
        with self.assertRaises(PermissionError):
            self.query(hook=revoke)
        self.assertEqual(self.read(), submitted)

    def test_reviewer_session_revoked_during_execute_leaves_consumed_unknown(self):
        self.approve()
        def revoke(*args, **kwargs):
            self.center.logout(self.fx.reviewer['token'])
        with self.assertRaises(PermissionError):
            self.execute(hook=revoke)
        self.assertEqual(self.read()['state'], 'SUBMISSION_UNKNOWN')
        self.assertNotIn('applyment_id', self.read())
        self.assertEqual(len(self.attempts()), 1)

    def test_revocation_before_reservation_prevents_provider_call(self):
        approved = self.approve()
        original = self.service._encrypt
        def encrypt_then_revoke(value, key=None):
            result = original(value, key)
            if key is None:
                self.center.db.execute('UPDATE members SET active=0 WHERE user_id=?', (self.fx.fx.uid2,))
            return result
        self.provider.reset_mock()
        with patch.object(self.service, '_encrypt', side_effect=encrypt_then_revoke):
            with self.assertRaises(PermissionError):
                self.call('wechat_execute', expected_version=approved['version'])
        self.provider.assert_not_called()
        self.assertEqual(self.read(), approved)
        self.assertEqual(self.attempts(), [])

    def test_wrong_business_code_or_unknown_provider_state_cannot_unlock(self):
        submitted = self.submitted()
        for state, extra, message in (
                ('APPLYMENT_STATE_REJECTED', {'business_code': 'other_application'}, 'BINDING_MISMATCH'),
                ('APPLYMENT_STATE_NEW_UNDOCUMENTED', {}, 'UNKNOWN_PROVIDER_APPLICATION_STATE')):
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, message):
                self.query(state, **extra)
            self.assertEqual(self.read(), submitted)

    def test_recovery_receipt_must_bind_same_business_code_and_digest(self):
        self.submitted()
        self.query()
        approved = self.approve()
        for receipt in (None, {}, dict(approved['correction_receipt'], business_code='another'),
                        dict(approved['correction_receipt'], response_sha256='not-a-digest')):
            candidate = dict(approved, correction_receipt=receipt)
            self.replace_record(candidate)
            self.provider.reset_mock()
            with self.assertRaisesRegex(PermissionError, 'SIGNED_PROVIDER_REJECTION_REQUIRED'):
                self.call('wechat_execute', expected_version=candidate['version'])
            self.provider.assert_not_called()
        self.assertEqual(len(self.attempts()), 1)

    def test_finished_identity_and_terminal_status_cannot_be_reassigned(self):
        self.submitted()
        finished = self.query('APPLYMENT_STATE_FINISHED', sub_mchid='1900000999')
        for state, mchid, error in (
                ('APPLYMENT_STATE_FINISHED', '1900000888', 'IMMUTABLE_PROVIDER_SUBMERCHANT_CONFLICT'),
                ('APPLYMENT_STATE_REJECTED', '1900000999', 'TERMINAL_PROVIDER_APPLYMENT_STATE_CONFLICT')):
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, error):
                self.query(state, sub_mchid=mchid)
            self.assertEqual(self.read(), finished)

    def test_stale_and_boolean_versions_cannot_edit_corrected_application(self):
        old = self.submitted()
        correction = self.query()
        self.provider.reset_mock()
        for version in (old['version'], True, str(correction['version'])):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, 'VERSION_CONFLICT'):
                self.call('wechat_save', expected_version=version, profile=self.profile)
        self.provider.assert_not_called()
        self.assertEqual(self.read(), correction)

    def test_correction_persists_encrypted_and_survives_database_reopen(self):
        first = self.submitted()
        corrected = self.query()
        ciphertext = self.center.db.execute(
            "SELECT payload FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT'").fetchone()[0]
        self.assertNotIn(first['business_code'].encode(), bytes(ciphertext))
        self.assertNotIn(self.profile['contact_info']['contact_name'].encode(), bytes(ciphertext))
        self.fx.fx.reopen()
        self.center = self.fx.fx.center
        self.fx.service = MerchantOnboarding(self.center, {self.fx.fx.uid2: 'project1'})
        self.service = WechatApplyment(self.fx.service, self.reader, submission_enabled=True)
        self.fx.service.wechat_applyment = self.service
        self.assertEqual(self.call('wechat_read'), corrected)
        approved = self.approve()
        submitted = self.execute()
        self.assertEqual(submitted['business_code'], first['business_code'])
        self.assertIn(first['business_code'] + ':revision:' + str(approved['version']), self.attempts())

    def test_existing_unsubmitted_internal_correction_flow_still_works(self):
        saved = self.call('wechat_save', expected_version=0, profile=self.profile)
        pending = self.call('wechat_submit_review', expected_version=saved['version'])
        correction = self.call('wechat_review', expected_version=pending['version'],
                               decision='CORRECTION', opinion='Synthetic internal correction')
        self.assertNotIn('business_code', correction)
        self.assertNotIn('correction_receipt', correction)
        self.approve()
        submitted = self.execute()
        self.assertEqual(self.attempts(), [submitted['business_code']])
        self.assertEqual(submitted['state'], 'SUBMITTED_TO_PROVIDER')

    def test_reused_legacy_attempt_is_not_replayed_even_with_old_approved_record(self):
        approved = self.approve()
        first = self.execute()
        self.replace_record(approved)
        self.provider.reset_mock()
        with self.assertRaisesRegex(PermissionError, 'QUERY_EXISTING_APPLICATION_ONLY'):
            self.call('wechat_execute', expected_version=approved['version'])
        self.provider.assert_not_called()
        self.assertEqual(self.attempts(), [first['business_code']])

    def test_reused_corrected_revision_is_not_replayed_from_old_approved_record(self):
        first = self.submitted()
        self.query()
        approved = self.approve()
        self.execute()
        self.replace_record(approved)
        self.provider.reset_mock()
        with self.assertRaisesRegex(PermissionError, 'QUERY_EXISTING_APPLICATION_ONLY'):
            self.call('wechat_execute', expected_version=approved['version'])
        self.provider.assert_not_called()
        self.assertEqual(self.attempts(), sorted([
            first['business_code'], first['business_code'] + ':revision:' + str(approved['version'])]))

    def assert_current_provider_state_blocks_correction(self, state):
        self.submitted()
        self.query()
        self.approve()
        advanced = self.query(state)
        attempts = self.attempts()
        self.provider.reset_mock()
        with self.assertRaises(PermissionError):
            self.call('wechat_execute', expected_version=advanced['version'])
        self.provider.assert_not_called()
        self.assertEqual(self.attempts(), attempts)
        self.assertEqual(self.read(), advanced)

    def test_new_auditing_query_invalidates_permission_to_overwrite_rejected_application(self):
        self.assert_current_provider_state_blocks_correction('APPLYMENT_STATE_AUDITING')

    def test_new_finished_query_invalidates_permission_to_overwrite_rejected_application(self):
        self.assert_current_provider_state_blocks_correction('APPLYMENT_STATE_FINISHED')

    def test_platform_material_metadata_race_before_reservation_prevents_provider_call(self):
        approved = self.approve()
        original = self.service._encrypt
        def encrypt_then_change_meta(value, key=None):
            result = original(value, key)
            if key is None:
                owner, meta, _ = self.fx.service._load(self.application, self.fx.fx.uid2, True)
                meta['category'] = 'FOOD'
                with self.center.tx():
                    self.fx.service._meta(self.application, owner, meta)
            return result
        self.provider.reset_mock()
        with patch.object(self.service, '_encrypt', side_effect=encrypt_then_change_meta):
            with self.assertRaisesRegex(ValueError, 'WECHAT_APPLYMENT_CHANGED'):
                self.call('wechat_execute', expected_version=approved['version'])
        self.provider.assert_not_called()
        self.assertEqual(self.read(), approved)
        self.assertEqual(self.attempts(), [])

    def test_correction_does_not_bypass_closed_submission_gate(self):
        self.submitted()
        self.query()
        approved = self.approve()
        self.service.enabled = False
        self.provider.reset_mock()
        with self.assertRaisesRegex(PermissionError, 'REAL_MERCHANT_SUBMISSION_GATE_CLOSED'):
            self.call('wechat_execute', expected_version=approved['version'])
        self.provider.assert_not_called()
        self.assertEqual(self.read(), approved)
        self.assertEqual(len(self.attempts()), 1)

    def test_correction_requires_media_bound_to_current_original_application(self):
        self.submitted()
        self.query()
        changed = copy.deepcopy(self.profile)
        changed['subject_info']['business_license_info']['license_copy'] = 'other-application-media'
        approved = self.approve(changed)
        self.provider.reset_mock()
        with self.assertRaisesRegex(PermissionError, 'CURRENT_ORIGINAL_APPLICATION_MEDIA_REQUIRED'):
            self.call('wechat_execute', expected_version=approved['version'])
        self.provider.assert_not_called()
        self.assertEqual(self.read(), approved)
        self.assertEqual(len(self.attempts()), 1)

    def test_timed_out_replacement_does_not_reopen_from_previous_rejection(self):
        first = self.submitted()
        self.assertFalse(first['replacement_submission'])
        rejected = self.query()
        self.approve()
        with self.assertRaises(TimeoutError):
            self.execute(error=TimeoutError('Synthetic replacement uncertainty'))
        unknown = self.read()
        self.assertEqual(unknown['state'], 'SUBMISSION_UNKNOWN')
        self.assertTrue(unknown['replacement_submission'])
        self.assertNotIn('correction_receipt', unknown)
        for digest in (rejected['provider_response_sha256'], 'd' * 64):
            current = self.query(digest=digest)
            self.assertEqual(current['state'], 'SUBMISSION_UNKNOWN')
            self.assertEqual(current['version'], unknown['version'])
            self.assertNotIn('correction_receipt', current)
        self.provider.reset_mock()
        for operation, params in (
                ('wechat_save', dict(profile=self.profile)),
                ('wechat_submit_review', {}), ('wechat_execute', {})):
            with self.subTest(operation=operation), self.assertRaises(PermissionError):
                self.call(operation, expected_version=unknown['version'], **params)
        self.provider.assert_not_called()
        self.assertEqual(len(self.attempts()), 2)

    def test_unknown_replacement_may_observe_completion_but_never_replay(self):
        first = self.submitted()
        self.query()
        self.approve()
        with self.assertRaises(TimeoutError):
            self.execute(error=TimeoutError('Synthetic replacement uncertainty'))
        unknown = self.read()
        result = self.query('APPLYMENT_STATE_FINISHED', sub_mchid='1900000999')
        self.assertEqual(result['business_code'], first['business_code'])
        self.assertEqual(result['version'], unknown['version'])
        self.assertEqual(result['provider_state'], 'APPLYMENT_STATE_FINISHED')
        self.assertEqual(result['provider_sub_mchid'], '1900000999')
        self.assertNotIn('correction_receipt', result)
        self.provider.reset_mock()
        with self.assertRaises(PermissionError):
            self.call('wechat_execute', expected_version=result['version'])
        self.provider.assert_not_called()
        self.assertEqual(len(self.attempts()), 2)


if __name__ == '__main__':
    unittest.main()
