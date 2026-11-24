"""Actual protected loader -> MiniApplication -> authenticated service -> signed wire.

Synthetic fixtures only. Real RSA verification and encrypted temporary Center;
all network fetches are blocked or explicitly supplied signed synthetic bytes.
Requires the existing full service Python dependency environment. No AST methods.
"""
import contextlib
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives import serialization
import test_community_applyment_rejection_recovery as recovery
from scripts.community_platform_host import _open_provider_reader,_open_applyment_readers
from scripts.community_mini_application import MiniApplication
from scripts.community_wechat_observer import ApplymentObserver
from scripts.community_provider_transport import request as verified_transport

NEW='1234563578'


class ActualReaderIntegration(unittest.TestCase):
    setUpClass=classmethod(recovery.RejectionRecovery.setUpClass.__func__)
    call=recovery.RejectionRecovery.call
    response=recovery.RejectionRecovery.response
    read=recovery.RejectionRecovery.read
    approve=recovery.RejectionRecovery.approve
    execute=recovery.RejectionRecovery.execute
    submitted=recovery.RejectionRecovery.submitted
    attempts=recovery.RejectionRecovery.attempts
    query_data=recovery.RejectionRecovery.query_data
    signed_wire=recovery.RejectionRecovery.signed_wire
    replace_record=recovery.RejectionRecovery.replace_record

    def setUp(self):
        recovery.RejectionRecovery.setUp(self)
        self.network_guard=patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('REAL_NETWORK_FORBIDDEN'))
        self.network_guard.start();self.addCleanup(self.network_guard.stop)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def write(self,name,value):
        p=self.root/name;p.write_text(json.dumps(value));p.chmod(0o600);return str(p)

    def install_synthetic_registry_through_actual_host_entry(self):
        private=self.private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
        config=dict(sp_mchid=self.reader._mchid,merchant_serial='ABCD',private_key_pem=private,public_key_id='PUB_KEY_ID_SYNTHETIC',public_key_pem=self.public.decode())
        legacy=_open_provider_reader(self.write('old-reader.json',config),self.center.now)
        config=dict(config,sp_mchid=NEW)
        self.new_path=self.write('new-reader.json',config)
        registry=self.write('registry.json',dict(version=1,submission_provider=NEW,additional_readers={NEW:self.new_path}))
        additional,default=_open_applyment_readers(registry,legacy,self.center.now)
        # Recompose the original synthetic onboarding instance before a listener,
        # exactly through the production MiniApplication method, not a helper copy.
        application=MiniApplication.__new__(MiniApplication)
        application.server=None;application.onboarding=self.fx.service
        self.fx.service.wechat_applyment=None
        self.service=application.configure_wechat_applyment(legacy,submission_enabled=True,provider_readers=additional,submission_provider=default)
        self.reader=legacy;self.new=additional[NEW];self.registry_path=registry
        self.assertIs(self.fx.service.wechat_applyment,self.service)
        self.assertIs(self.service.reader,legacy)
        return application

    @contextlib.contextmanager
    def verified_reply(self,reader,data):
        previous=self.provider.side_effect
        self.provider.side_effect=verified_transport
        try:
            with patch.object(reader,'_fetch',return_value=self.signed_wire(data)) as fetch:
                yield fetch
        finally:self.provider.side_effect=previous

    def prepare_new_unbound_profile(self):
        for kind,media in [('business_license','media-license'),('identity_front','media-front'),('identity_back','media-back'),('mini_program_screenshot','media-mini')]:
            with self.response({'media_id':media}):self.call('wechat_media',kind=kind)
        self.call('wechat_save',expected_version=0,profile=copy.deepcopy(self.profile))
        self.assertIsNone(self.read().get('provider_sp_mchid'))
        self.assertFalse(self.read().get('business_code'))

    def owner_submit(self):
        web=self.fx.applicant
        actor=lambda:self.center.session(web['token'],web['csrf'])
        platform=self.call('read')
        return self.fx.service.dispatch(web['token'],web['csrf'],{
            'operation':'wechat_submit_review','params':{'application':self.application,
            'expected_version':self.read()['version'],'application_revision':platform['revision']}},
            _mini_submission=True,_mini_reauthorize=actor)

    def test_existing_accepted_record_signed_query_and_sign_url_stay_legacy(self):
        self.submitted();before=copy.deepcopy(self.read())
        self.install_synthetic_registry_through_actual_host_entry()
        data=self.query_data('APPLYMENT_STATE_TO_BE_SIGNED',sign_url='https://pay.weixin.qq.com/public/apply4ec_sign/s?synthetic=1')
        with patch.object(self.new,'_fetch',side_effect=AssertionError('WRONG_PROVIDER')) as wrong:
            with self.verified_reply(self.reader,data) as fetch:result=self.call('wechat_query')
        self.assertEqual(fetch.call_count,1);wrong.assert_not_called()
        self.assertEqual(result['provider_sp_mchid'],self.reader._mchid)
        self.assertEqual(result['provider_state'],'APPLYMENT_STATE_TO_BE_SIGNED')
        self.assertEqual(result['provider_sign_url'],data['sign_url'])
        self.assertEqual(result['applyment_id'],before['applyment_id'])

    def test_existing_unbound_draft_owner_entry_submits_under_new_reader(self):
        self.install_synthetic_registry_through_actual_host_entry();self.prepare_new_unbound_profile()
        with patch.object(self.reader,'_fetch',side_effect=AssertionError('LEGACY_FALLBACK')) as old:
            with self.verified_reply(self.new,{'applyment_id':3578001}) as fetch:result=self.owner_submit()
        self.assertEqual(fetch.call_count,1);old.assert_not_called()
        self.assertEqual(result['state'],'SUBMITTED_TO_PROVIDER')
        self.assertEqual(self.read()['provider_sp_mchid'],NEW)
        self.assertEqual(self.read()['applyment_id'],'3578001')
        self.assertEqual(len(self.attempts()),1)

    def test_unknown_provider_trace_refuses_network_or_record_migration(self):
        self.submitted();record=copy.deepcopy(self.read());record.pop('provider_sp_mchid');self.replace_record(record)
        self.install_synthetic_registry_through_actual_host_entry();before=copy.deepcopy(self.read());self.provider.reset_mock()
        with self.assertRaisesRegex(PermissionError,'OWNERSHIP_UNCONFIRMED'):self.call('wechat_query')
        self.provider.assert_not_called();self.assertEqual(self.read(),before)

    def test_pending_new_owner_intent_automatic_get_completion_uses_new_reader(self):
        self.install_synthetic_registry_through_actual_host_entry();self.prepare_new_unbound_profile()
        disabled=lambda:dict(version=1,enabled=False,interval_seconds=60,grants={})
        observer=ApplymentObserver(self.service,disabled,expected_project='project1')
        self.service.observer=observer;self.addCleanup(observer.close)
        with self.response(error=TimeoutError('SYNTHETIC_UNKNOWN')):
            with self.assertRaises(TimeoutError):self.owner_submit()
        self.assertEqual(self.read()['state'],'SUBMISSION_UNKNOWN')
        data=self.query_data('APPLYMENT_STATE_TO_BE_SIGNED',sign_url='https://pay.weixin.qq.com/public/apply4ec_sign/s?synthetic=2')
        wire=self.signed_wire(data)
        with patch.object(self.reader,'_fetch',side_effect=AssertionError('LEGACY_FALLBACK')) as old:
            with patch.object(self.new,'_fetch',return_value=wire) as fetch:
                with patch('scripts.community_owner_submit_recovery.request',side_effect=verified_transport):
                    worker=observer.owner_recovery;worker.service_actions()
                    self.assertIsNotNone(worker.pending)
                    worker.pending[1].result(timeout=3)
                    worker.service_actions()
        self.assertEqual(fetch.call_count,1);old.assert_not_called()
        self.assertEqual(self.read()['provider_sp_mchid'],NEW)
        self.assertEqual(self.read()['state'],'SUBMITTED_TO_PROVIDER')
        self.assertEqual(self.read()['provider_state'],'APPLYMENT_STATE_TO_BE_SIGNED')
        self.assertEqual(self.read()['provider_sign_url'],data['sign_url'])
        self.assertEqual(len(self.attempts()),1)


if __name__=='__main__':unittest.main()
