"""Synthetic original HTTP -> Center -> planner integration; no real objects."""
import copy, hashlib, json, unittest, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import test_community_merchant_onboarding as fixture
from scripts.community_wechat_sp_readonly import PartnerOrderReader
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_mini_http import serve
from scripts.pr122_customer_core import canonical
from scripts.community_onboarding_reapply import current

class ReapplyHTTP(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.MerchantAdmissionJourney();self.fx.setUp()
        self.s=self.fx.service;self.c=self.fx.fx.center
        self.app=self.fx.draft();self.owner=self.fx.fx.uid1
        w=self.fx.reviewer
        self.other=self.s.dispatch(w['token'],w['csrf'],dict(operation='save',params=dict(application=None,revision=0,fields=self.fx.fields,entity_type='ENTERPRISE',category='GENERAL',delegated=False)))
        self.reader=PartnerOrderReader.__new__(PartnerOrderReader);self.reader._mchid='999999'
        self.s.wechat_applyment=WechatApplyment(self.s,self.reader)
        self.targets=[]
        for alias,owner,app,scope in [('test1',self.owner,self.app,('t1','m1','s1')),('test2',self.fx.fx.uid2,self.other,('t1','m2','s2'))]:
            application=app['application'];epoch=self.c.db.execute('SELECT epoch FROM accounts WHERE id=?',(owner,)).fetchone()[0]
            self.targets.append(dict(alias=alias,owner_ref=owner,application_ref=application,scope=scope,old_provider_ref='888888'))
            record=dict(version=1,state='TO_BE_SIGNED',provider_sp_mchid='888888',business_code=alias,applyment_id='123' if alias=='test1' else '456',profile={})
            self.s.wechat_applyment._save(application,owner,record)
            rh=hashlib.sha256(canonical(record)).hexdigest()
            obs=dict(record_digest=rh,sync_error=None,provider_state='APPLYMENT_STATE_FINISHED',provider_query_signature_sha256='a'*64,
                binding=dict(owner=owner,application=application,provider_merchant='888888',business_code=record['business_code'],applyment_id=record['applyment_id'],active=True),
                merchant_binding=dict(owner=owner,application=application,business_code=record['business_code'],applyment_id=record['applyment_id'],account_epoch=epoch,record_digest=rh,signature_sha256='a'*64,sub_mchid='777777'))
            self.c.db.execute("INSERT INTO links VALUES('COMMUNITY_WECHAT_OBSERVATION',?,?,?,?,1)",(application,owner,application,self.c.encrypt(canonical(obs),'wechat-observation:'+application)))
        self.clear=True;self.enabled=True;self.effect='synthetic-confirmed-effect'
        def authority(c,application):
            self.assertTrue(c.db.in_transaction)
            t=next(t for t in self.targets if t['application_ref']==application)
            epoch=c.db.execute('SELECT epoch FROM accounts WHERE id=?',(t['owner_ref'],)).fetchone()[0]
            return dict(targets=copy.deepcopy(self.targets),new_provider_ref='999999',dots_effect_ref=self.effect,enabled=self.enabled,
                reconciliation=dict(owner_ref=t['owner_ref'],application_ref=application,scope=t['scope'],financial_clear=self.clear,receipt_ref='synthetic-clear'),
                account_epoch=epoch,login_identity_ref='synthetic-original-login')
        self.s.reapply_authority=authority
        self.params=dict(application=self.app['application'],expected_version=1,idempotency_key='synthetic_request_0001')
    def tearDown(self):self.fx.tearDown()
    def call(self,op='reapply_release',params=None,review=True):return self.fx.call(op,self.params if params is None else params,review)
    def test_preview_repeat_history_and_new_current(self):
        before=self.s._load(self.app['application'],self.owner)[2]
        schema=[tuple(r) for r in self.c.db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')]
        self.assertEqual(self.call('reapply_preview')['status'],'PREVIEW');self.assertIsNone(current(self.s,self.owner))
        receipt=self.call()['receipt'];again=self.call()['receipt'];self.assertTrue(again['replay'])
        self.assertEqual(again['request_digest'],receipt['request_digest'])
        self.assertEqual(self.s._load(self.app['application'],self.owner)[2],before)
        self.assertEqual(self.c.db.execute("SELECT count(*) FROM audit WHERE event='MERCHANT_TEST_REAPPLY_RELEASE'").fetchone()[0],1)
        listing=self.fx.call('mine');self.assertIsNone(listing['current_cursor']['application'])
        self.assertIn(self.app['application'],[a['application'] for a in listing['applications']])
        new=self.fx.draft();cursor=current(self.s,self.owner)
        self.assertEqual((cursor['application'],cursor['generation']),(new['application'],2))
        self.assertEqual(new['wechat_submerchant_state'],'NOT_VERIFIED')
        self.assertIsNone(self.s.wechat_applyment._read(new['application']))
        self.assertEqual(schema,[tuple(r) for r in self.c.db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')])
        with self.assertRaisesRegex(ValueError,'ALREADY_HAS_APPLICATION'):self.call()
        with self.assertRaisesRegex(PermissionError,'HISTORICAL_GENERATION'):self.fx.draft(self.app)
        with self.assertRaisesRegex(PermissionError,'SERVICE_MERCHANT_CHANGED'):self.s.wechat_applyment._provider_domain(self.s.wechat_applyment._read(self.app['application']))
    def test_financial_effect_disabled_scope_session_denied(self):
        for field,value in [('clear',False),('effect',''),('enabled',False)]:
            previous=getattr(self,field);setattr(self,field,value)
            with self.assertRaises(ValueError):self.call()
            self.assertIsNone(current(self.s,self.owner));setattr(self,field,previous)
        with self.assertRaises(PermissionError):self.call(review=False)
        for field in ('financial_clear','provider','dots_effect_ref'):
            with self.assertRaises(ValueError):self.call(params=dict(self.params,**{field:True}))
        with self.assertRaises(PermissionError):self.s.dispatch(self.fx.reviewer['token'],'',dict(operation='reapply_release',params=self.params))
    def test_stale_conflict_unknown_and_changed_old_evidence(self):
        with self.assertRaisesRegex(ValueError,'VERSION_CONFLICT'):self.call(params=dict(self.params,expected_version=7))
        self.call()
        with self.assertRaisesRegex(ValueError,'REPLAY_RECEIPT'):self.call(params=dict(self.params,idempotency_key='another_request_0002'))
        r=self.s.wechat_applyment._read(self.app['application']);r['state']='SUBMISSION_UNKNOWN'
        self.s.wechat_applyment._save(self.app['application'],self.owner,r)
        with self.assertRaisesRegex(ValueError,'OBSERVATION'):self.call()
    def test_audit_failure_and_new_save_failure_preserve_draft(self):
        with patch.object(self.c,'audit',side_effect=RuntimeError('synthetic audit failure')):
            with self.assertRaises(RuntimeError):self.call()
        self.assertIsNone(current(self.s,self.owner))
        self.call();before=self.s._load(self.app['application'],self.owner)[2]
        with self.assertRaises(ValueError):self.fx.draft(fields=dict(self.fx.fields,contact=123))
        self.assertIsNone(current(self.s,self.owner)['application'])
        self.assertEqual(before,self.s._load(self.app['application'],self.owner)[2])
        new=self.fx.draft();self.assertEqual(current(self.s,self.owner)['application'],new['application'])
    def test_both_exact_targets_and_wrong_owner(self):
        self.call();self.call(params=dict(self.params,application=self.other['application'],idempotency_key='synthetic_request_0002'))
        self.assertIsNone(current(self.s,self.fx.fx.uid2)['application'])
        self.targets[0]['owner_ref']=self.fx.fx.uid2
        with self.assertRaisesRegex(ValueError,'EXACT_TEST_OWNER'):self.call()
    def test_unknown_other_submission_and_new_provider_contamination(self):
        ghost='ma_'+'a'*32
        self.s.wechat_applyment._save(ghost,self.owner,dict(state='SUBMISSION_UNKNOWN'))
        with self.assertRaisesRegex(ValueError,'UNKNOWN_SUBMISSION'):self.call()
        self.c.db.execute("DELETE FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=?",(ghost,))
        self.call();new=self.fx.draft()
        self.s.wechat_applyment._save(new['application'],self.owner,dict(version=1,state='NOT_SUBMITTED',profile={},provider_sp_mchid='888888'))
        with self.assertRaisesRegex(PermissionError,'CURRENT_GENERATION_PROVIDER_MISMATCH'):
            self.fx.call('read',dict(application=new['application']))
    def test_current_login_epoch_and_exact_reconciliation_scope(self):
        self.targets[0]['scope']=('t1','m1','wrong')
        original=self.s.reapply_authority
        def wrong_scope(c,application):
            result=original(c,application);result['reconciliation']['scope']=('t1','m1','s1');return result
        self.s.reapply_authority=wrong_scope
        with self.assertRaisesRegex(ValueError,'RECONCILIATION_SCOPE'):self.call()
        self.s.reapply_authority=original
        self.c.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?',(self.owner,))
        with self.assertRaisesRegex(ValueError,'FINISHED_PROOF'):self.call()
    def test_original_http_preview_release_and_policy_injection(self):
        server=serve(self.fx.fx.gateway,onboarding=self.s);server.timeout=2
        def http(body):
            req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/merchant/onboarding',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Cookie':'__Host-xj_customer='+self.fx.reviewer['token'],'X-CSRF-Token':self.fx.reviewer['csrf']})
            try:
                with urllib.request.urlopen(req,timeout=3) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as e:return e.code,json.load(e)
        try:
            with ThreadPoolExecutor(1) as pool:
                for op,params in [('reapply_preview',self.params),('reapply_release',self.params),('reapply_release',dict(self.params,financial_clear=True))]:
                    future=pool.submit(http,dict(operation=op,params=params));server.handle_request();status,result=future.result()
                    if 'financial_clear' in params:self.assertGreaterEqual(status,400)
                    else:self.assertEqual(status,200,result);self.assertIn('receipt',result['result'])
        finally:server.server_close()
