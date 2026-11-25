"""Original authenticated gateway/onboarding/SQLite; synthetic signer and image only."""
import base64
import copy
import unittest
from scripts.community_mini_merchant import MiniMerchant
from scripts.community_mini_direct_ocr import SIGNED, CHANNEL, DirectOcrSelectionChanged
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_wechat_sp_readonly import PartnerOrderReader
import test_community_merchant_onboarding as fixture

PNG=b'\x89PNG\r\n\x1a\nSYNTHETIC IMAGE ONLY; NOT A REAL CARD'
class DirectBankProof(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.MerchantAdmissionJourney();self.fx.setUp();self.addCleanup(self.fx.tearDown)
        self.service=self.fx.service
        self.service.wechat_applyment=WechatApplyment(self.service,PartnerOrderReader.__new__(PartnerOrderReader),submission_enabled=False)
        self.app=self.fx.draft()
        self.fx.call('wechat_save',dict(application=self.app['application'],expected_version=0,profile={
            'contact_info':{},'subject_info':{},'business_info':{},'settlement_info':{},'bank_account_info':{}}))
        self.app=self.fx.call('read',{'application':self.app['application']})
        self.api=MiniMerchant(self.fx.fx.identity,self.service)
        self.token=self.fx.fx.token()
        self.calls=[]
        def signer(request):
            self.calls.append(copy.deepcopy(request))
            return {'headers':{'authorization':'ACS3-HMAC-SHA256 Credential=SYNTHETIC,SignedHeaders='+SIGNED+',Signature='+'a'*64,
                'content-type':'application/octet-stream','x-acs-action':request['action'],
                'x-acs-content-sha256':request['digest'],'x-acs-date':request['signed_at'],
                'x-acs-signature-nonce':request['nonce'],'x-acs-version':'2021-07-07'}}
        self.service.direct_ocr_signer=signer
        self.p=dict(application=self.app['application'],revision=self.app['revision'],provider_version=1,
            kind='bank_card',digest='b'*64,size=len(PNG),intent_key='mini-ocr-direct-synthetic-selection-01')
    def call(self,op,p,token=None):
        return self.api.dispatch(token or self.token,'',{'operation':'onboarding','params':{'operation':op,'params':p}})
    def upload(self,p=None):
        p=p or self.p
        return self.call('upload',dict(application=p['application'],revision=p['revision'],kind='bank_card',
            content_base64=base64.b64encode(PNG).decode(),expires_at=None,direct_ocr_binding=p))
    def test_save_first_signature_accepts_only_its_own_exact_single_revision_advance(self):
        saved=self.upload();signed=self.call('direct_ocr_sign',self.p)
        self.assertEqual(saved['direct_ocr_receipt']['intent_key'],self.p['intent_key'])
        self.assertEqual(saved['revision'],self.p['revision']+1)
        self.assertEqual(signed['headers']['x-acs-action'],'RecognizeBankCard')
        self.assertEqual(self.calls[0]['host'],'ocr-api.cn-hangzhou.aliyuncs.com')
        self.assertEqual(self.calls[0]['subject'],self.fx.fx.uid1)
        self.assertEqual(self.call('direct_ocr_sign',self.p),signed)
        self.assertEqual(len(self.calls),1)
    def test_signature_first_photo_save_is_independent_and_no_fields_are_auto_saved(self):
        signed=self.call('direct_ocr_sign',self.p);saved=self.upload()
        self.assertEqual(signed['headers']['x-acs-content-sha256'],self.p['digest'])
        self.assertEqual(saved['direct_ocr_receipt']['provider_version'],1)
        before=self.fx.call('wechat_read',{'application':self.p['application']})
        self.assertEqual(before['profile']['bank_account_info'],{})
        # A separate explicit human edit/save goes through the original provider
        # draft API, not the proof endpoint or a client-claimed OCR confirmation.
        profile=copy.deepcopy(before['profile']);profile['bank_account_info']={'account_number':'0000000000000000','account_bank':'Synthetic Test Bank'}
        self.fx.call('wechat_save',dict(application=self.p['application'],expected_version=before['version'],profile=profile))
        read=self.fx.call('wechat_read',{'application':self.p['application']})
        self.assertEqual(read['profile']['bank_account_info'],profile['bank_account_info'])
        self.assertEqual(read['version'],before['version']+1)
    def test_signer_failure_never_retries_and_does_not_prevent_photo_save(self):
        def fail(request):self.calls.append(request);raise TimeoutError('PRIVATE_PROVIDER_TEXT')
        self.service.direct_ocr_signer=fail
        with self.assertRaisesRegex(ValueError,'DIRECT_OCR_SIGN_RESULT_UNKNOWN'):self.call('direct_ocr_sign',self.p)
        saved=self.upload();self.assertIn('bank_card',saved['materials'])
        with self.assertRaisesRegex(DirectOcrSelectionChanged,'RESULT_UNKNOWN'):self.call('direct_ocr_sign',self.p)
        self.assertEqual(len(self.calls),1)
    def test_wrong_owner_and_invalid_bindings_never_reach_signer(self):
        other=self.fx.fx.token('other-code','openid2')
        with self.assertRaises(PermissionError):self.call('direct_ocr_sign',self.p,other)
        for change in ({'kind':'public_ocr'},{'digest':'not-a-digest'},{'size':0},{'provider_version':2},{'revision':self.p['revision']+1}):
            with self.subTest(change=change),self.assertRaises((ValueError,PermissionError)):
                self.call('direct_ocr_sign',dict(self.p,**change))
        self.assertEqual(self.calls,[])
    def test_unrelated_edit_replacement_provider_or_withdrawal_cannot_reuse_selection(self):
        self.upload()
        for change in ({'digest':'c'*64},{'kind':'business_license'},{'provider_version':2}):
            with self.subTest(change=change),self.assertRaises(DirectOcrSelectionChanged):self.call('direct_ocr_sign',dict(self.p,**change))
        current=self.fx.call('read',{'application':self.p['application']})
        self.fx.draft(current)
        with self.assertRaisesRegex(DirectOcrSelectionChanged,'SOURCE_CHANGED'):self.call('direct_ocr_sign',self.p)
        self.assertEqual(self.calls,[])
    def test_expired_selection_and_duplicate_unknown_save_are_not_reissued(self):
        self.upload()
        with self.assertRaises(DirectOcrSelectionChanged):self.upload()
        self.fx.fx.stage.now+=61
        with self.assertRaisesRegex(DirectOcrSelectionChanged,'EXPIRED'):self.call('direct_ocr_sign',self.p)
        self.assertEqual(self.calls,[])
    def test_revocation_during_signing_is_rechecked_before_headers_return(self):
        original=self.service.direct_ocr_signer
        def revoke(request):
            result=original(request)
            self.fx.fx.center.db.execute("UPDATE links SET active=0 WHERE channel='WECHAT_MINI'")
            return result
        self.service.direct_ocr_signer=revoke
        with self.assertRaises(PermissionError):self.call('direct_ocr_sign',self.p)
        self.assertEqual(len(self.calls),1)
    def test_wrong_action_signature_is_rejected_and_photo_can_still_save(self):
        original=self.service.direct_ocr_signer
        def wrong(request):
            result=original(request);result['headers']['x-acs-action']='RecognizeBusinessLicense';return result
        self.service.direct_ocr_signer=wrong
        with self.assertRaisesRegex(ValueError,'PROOF_INVALID'):self.call('direct_ocr_sign',self.p)
        self.assertIn('bank_card',self.upload()['materials'])
    def test_revoked_selection_record_cannot_be_recreated_or_resigned(self):
        self.call('direct_ocr_sign',self.p)
        self.fx.fx.center.db.execute('UPDATE links SET active=0 WHERE channel=? AND project=?',(CHANNEL,self.p['application']))
        with self.assertRaisesRegex(DirectOcrSelectionChanged,'REVOKED'):self.call('direct_ocr_sign',self.p)
        with self.assertRaisesRegex(DirectOcrSelectionChanged,'REVOKED'):self.upload()
        self.assertEqual(len(self.calls),1)

    def test_expired_proof_does_not_block_photo_or_extend_signing_authority(self):
        self.call('direct_ocr_sign',self.p)
        self.fx.fx.stage.now+=61
        saved=self.upload()
        self.assertIn('bank_card',saved['materials'])
        with self.assertRaisesRegex(DirectOcrSelectionChanged,'EXPIRED'):self.call('direct_ocr_sign',self.p)
        self.assertEqual(len(self.calls),1)

    def test_provider_change_during_signing_rejects_returned_proof(self):
        original=self.service.direct_ocr_signer
        def change(request):
            result=original(request)
            self.fx.call('wechat_save',dict(application=self.p['application'],expected_version=1,
                profile={'contact_info':{},'subject_info':{},'business_info':{},'settlement_info':{},'bank_account_info':{}}))
            return result
        self.service.direct_ocr_signer=change
        with self.assertRaisesRegex(DirectOcrSelectionChanged,'SOURCE_CHANGED'):self.call('direct_ocr_sign',self.p)
        self.assertEqual(len(self.calls),1)

    def test_withdrawn_application_cannot_reuse_an_existing_signature(self):
        self.call('direct_ocr_sign',self.p)
        self.fx.fx.center.db.execute("UPDATE onboarding SET status='WITHDRAWN' WHERE application=?",(self.p['application'],))
        with self.assertRaises(DirectOcrSelectionChanged):self.call('direct_ocr_sign',self.p)
        self.assertEqual(len(self.calls),1)

    def test_original_host_signer_hook_is_startup_only_and_cannot_replace_authority(self):
        from types import SimpleNamespace
        from scripts.community_platform_host import PlatformHost
        host=PlatformHost.__new__(PlatformHost)
        host.application=SimpleNamespace(server=None,onboarding=SimpleNamespace())
        signer=lambda request:None
        self.assertEqual(host.configure_applicant_direct_ocr_signer(signer),'APPLICANT_DIRECT_OCR_SIGNER_CONFIGURED')
        self.assertIs(host.application.onboarding.direct_ocr_signer,signer)
        with self.assertRaises(ValueError):host.configure_applicant_direct_ocr_signer(signer)
        host.application.server=object()
        with self.assertRaises(PermissionError):host.configure_applicant_direct_ocr_signer(signer)

    def test_original_http_binding_failure_is_local_400_not_account_revocation(self):
        import json,urllib.request,urllib.error
        from concurrent.futures import ThreadPoolExecutor
        from scripts.community_mini_http import serve
        server=serve(self.fx.fx.gateway,onboarding=self.service);self.addCleanup(server.server_close)
        body=json.dumps({'operation':'onboarding','params':{'operation':'direct_ocr_sign','params':dict(self.p,provider_version=2)}}).encode()
        def call():
            request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/mini/merchant',body,
                headers={'Content-Type':'application/json','X-Community-Session':self.token})
            try:
                with urllib.request.urlopen(request,timeout=3) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as error:return error.code,json.load(error)
        with ThreadPoolExecutor(1) as worker:
            task=worker.submit(call);server.handle_request();status,value=task.result()
        self.assertEqual((status,value),(400,{'error':'INVALID_REQUEST'}))
        self.assertEqual(self.fx.fx.identity.applicant_context(self.token)[0],self.fx.fx.uid1)
        self.assertIn('bank_card',self.upload()['materials'])
        self.assertEqual(self.calls,[])

    def test_original_health_reports_only_contract_and_signer_presence_not_credentials(self):
        import json,urllib.request
        from concurrent.futures import ThreadPoolExecutor
        from scripts.community_mini_http import serve
        server=serve(self.fx.fx.gateway,onboarding=self.service);self.addCleanup(server.server_close)
        def call():
            with urllib.request.urlopen('http://127.0.0.1:'+str(server.server_port)+'/community/health',timeout=3) as response:
                return json.load(response)
        with ThreadPoolExecutor(1) as worker:
            task=worker.submit(call);server.handle_request();result=task.result()
        self.assertEqual(result['mini_direct_ocr_contract'],'ORIGINAL_SELECTION_DIGEST_V1')
        self.assertIs(result['mini_direct_ocr_signer_configured'],True)
        self.assertFalse(any('secret' in key.lower() or key in ('headers','authorization','signer') for key in result))
        self.assertEqual(self.calls,[])

    def test_real_http_native_bank_direct_photo_and_manual_save_readback(self):
        import json,os,pathlib,subprocess,tempfile,time
        from scripts.community_mini_http import serve
        server=serve(self.fx.fx.gateway,onboarding=self.service);server.timeout=.05
        self.addCleanup(server.server_close)
        with tempfile.TemporaryFile(mode='w+') as output:
            child=subprocess.Popen(['node','tests/community_mini_bank_direct_http.cjs'],cwd=pathlib.Path(__file__).resolve().parents[1],
                env=dict(os.environ,COMMUNITY_TEST_ORIGIN='http://127.0.0.1:'+str(server.server_port)),stdout=output,stderr=output)
            try:
                deadline=time.monotonic()+15
                while child.poll() is None and time.monotonic()<deadline:server.handle_request()
                if child.poll() is None:child.kill();child.wait();self.fail('SYNTHETIC_BANK_DIRECT_HTTP_TIMEOUT')
                output.seek(0);raw=output.read();self.assertEqual(child.returncode,0,raw)
                receipt=json.loads(raw);self.assertTrue(receipt['human_save_readback']);self.assertTrue(receipt['fields_unchanged_before_human'])
                self.assertEqual(receipt['cloud_calls'],1);self.assertEqual(receipt['formal_submissions'],0)
                self.assertEqual(len(self.calls),1)
            finally:
                if child.poll() is None:child.kill();child.wait()

    def test_no_signer_means_no_cloud_authority_but_photo_still_saves(self):
        del self.service.direct_ocr_signer
        with self.assertRaisesRegex(ValueError,'SIGNER_UNAVAILABLE'):self.call('direct_ocr_sign',self.p)
        self.assertIn('bank_card',self.upload()['materials'])
        self.assertEqual(self.calls,[])

if __name__=='__main__':unittest.main()
