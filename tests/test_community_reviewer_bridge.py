import unittest
from email.message import Message
import test_community_wechat_registration as fixture
from scripts.community_merchant_onboarding import MerchantOnboarding
from scripts.community_web_session import WebSession
from scripts.community_reviewer_web_bridge import ReviewerWebBridge

ORIGIN='https://uk.wenwenwenyiyiyi.work'
class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.NativeConsumer();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.c,self.i=self.fx.c,self.fx.i
        self.mini=self.fx.login();self.uid=self.c.session(self.mini)
        # TEST ONLY fixture: grant is NOT part of the bridge or production API.
        self.c.db.execute("INSERT INTO members VALUES('project1',?,'REVIEWER',1)",(self.uid,))
        self.onboarding=MerchantOnboarding(self.c,{self.uid:'project1'})
        self.web=WebSession(self.c,onboarding=self.onboarding)
        self.b=ReviewerWebBridge(self.i,self.web,'shop1',ORIGIN)
        self.start()
    def start(self):
        self.start_result,self.cookie=self.b.begin(origin=ORIGIN,source='127.0.0.1')
        self.challenge=self.start_result['challenge']
        self.kw=dict(browser=self.cookie.split(';')[0].split('=',1)[1],csrf=self.start_result['csrf'],origin=ORIGIN)
    def confirm(self):return self.b.confirm(self.challenge,self.mini,verification=self.start_result['verification'],action='CONFIRM_THIS_BROWSER')
    def call(self,action):return self.b.browser(self.challenge,action=action,**self.kw)
    def test_real_provider_only_original_web_session(self):
        before=self.c.db.execute('SELECT count(*) FROM members').fetchone()[0]
        self.assertEqual(self.b.describe(self.challenge,self.mini)['origin'],ORIGIN)
        self.confirm();result,cookie=self.call('FINISH')
        headers=Message();headers['Cookie']=cookie.split(';')[0];headers['X-CSRF-Token']=result['csrf']
        check,_=self.web.dispatch('/community/session/check',headers,{},'127.0.0.1')
        self.assertTrue(check['reviewer']);self.assertEqual(check['user_id'],self.uid)
        self.assertEqual(before,self.c.db.execute('SELECT count(*) FROM members').fetchone()[0])
        self.assertNotIn('token',result);self.assertIn('Max-Age=3600',cookie)
        self.assertEqual(self.c.check_integrity()['integrity'],'PASS')
    def test_pending_cannot_finish_expiry_and_late_confirm(self):
        self.assertEqual(self.call('FINISH')[0]['state'],'PENDING')
        self.fx.fx.stage.now+=600
        self.assertEqual(self.call('FINISH')[0]['state'],'EXPIRED')
        with self.assertRaises(PermissionError):self.confirm()
    def test_cancel_before_confirm_and_repeat_cancel(self):
        self.assertEqual(self.call('CANCEL')[0]['state'],'CANCELLED')
        with self.assertRaises(PermissionError):self.confirm()
        self.assertEqual(self.call('CANCEL')[0]['state'],'CANCELLED')
        self.assertEqual(self.call('FINISH')[0]['state'],'CANCELLED')
    def test_response_loss_and_serial_race_exactly_one_session(self):
        self.confirm();self.confirm()
        before=self.c.db.execute('SELECT count(*) FROM sessions').fetchone()[0]
        _,cookie=self.call('FINISH') # simulate discarded network reply
        for _ in range(3):
            result,again=self.call('FINISH');self.assertIsNone(again);self.assertNotIn('csrf',result)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM sessions').fetchone()[0],before+1)
        self.call('CANCEL') # cancellation winning after issuance invalidates late response
        with self.assertRaises(PermissionError):self.c.session(cookie.split(';')[0].split('=',1)[1])
    def test_wrong_browser_csrf_origin_confirmation(self):
        for key in ('browser','csrf','origin'):
            args=dict(self.kw);args[key]='x'*43
            with self.assertRaises(PermissionError):self.b.browser(self.challenge,action='FINISH',**args)
        with self.assertRaises(PermissionError):self.b.confirm(self.challenge,self.mini,verification='wrong',action='CONFIRM_THIS_BROWSER')
        with self.assertRaises(PermissionError):self.b.confirm(self.challenge,self.mini,verification=self.start_result['verification'],action='AUTO')
        self.assertEqual(self.call('QUERY')[0]['state'],'PENDING')
    def test_live_revocation_at_finish_and_after_issue(self):
        self.confirm()
        self.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.uid,))
        with self.assertRaises(PermissionError):self.call('FINISH')
        self.c.db.execute('UPDATE members SET active=1 WHERE user_id=?',(self.uid,))
        result,cookie=self.call('FINISH')
        self.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.uid,))
        with self.assertRaises(PermissionError):self.onboarding._reviewer(self.uid)
        headers=Message();headers['Cookie']=cookie.split(';')[0];headers['X-CSRF-Token']=result['csrf']
        self.assertFalse(self.web.dispatch('/community/session/check',headers,{},'127.0.0.1')[0]['reviewer'])
    def test_epoch_provider_consumer_mini_session_revocation(self):
        self.confirm()
        self.c.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?',(self.uid,))
        with self.assertRaises(PermissionError):self.call('FINISH')
    def test_provider_unlink_denied(self):
        self.confirm();self.c.db.execute("UPDATE links SET active=0 WHERE channel='WECHAT_MINI' AND user_id=?",(self.uid,))
        with self.assertRaises(PermissionError):self.call('FINISH')
    def test_consumer_scope_revocation_denied(self):
        self.confirm();self.c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_WECHAT_CONSUMER_V1' AND user_id=?",(self.uid,))
        with self.assertRaises(PermissionError):self.call('FINISH')
    def test_mini_logout_denied(self):
        self.confirm();self.c.logout(self.mini)
        with self.assertRaises(PermissionError):self.call('FINISH')
    def test_no_role_no_grant_and_host_mapping_required(self):
        self.c.db.execute('DELETE FROM members WHERE user_id=?',(self.uid,))
        with self.assertRaises(PermissionError):self.confirm()
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM members WHERE user_id=?',(self.uid,)).fetchone()[0],0)
    def test_transaction_rollback_does_not_consume_or_issue(self):
        self.confirm()
        audit=self.c.audit
        def fail(*args):raise RuntimeError('synthetic audit failure')
        self.c.audit=fail
        with self.assertRaises(RuntimeError):self.call('FINISH')
        self.c.audit=audit
        self.assertEqual(self.call('QUERY')[0]['state'],'CONFIRMED')
        self.assertIsNotNone(self.call('FINISH')[1])
    def test_restart_retains_one_use_response_loss_state(self):
        self.confirm();self.call('FINISH')
        self.fx.fx.reopen();self.c=self.fx.fx.center;self.i=self.fx.fx.identity
        self.i.configure_registration(['shop1'])
        self.web=WebSession(self.c,onboarding=MerchantOnboarding(self.c,{self.uid:'project1'}))
        self.b=ReviewerWebBridge(self.i,self.web,'shop1',ORIGIN)
        result,cookie=self.call('FINISH')
        self.assertEqual(result['state'],'ISSUED');self.assertIsNone(cookie);self.assertNotIn('csrf',result)
    def test_host_projection_and_project_expiry_rechecked(self):
        self.confirm();self.onboarding.reviewers.clear()
        with self.assertRaises(PermissionError):self.call('FINISH')
        self.onboarding.reviewers[self.uid]='project1'
        self.c.db.execute("UPDATE projects SET expires=? WHERE id='project1'",(self.c.now(),))
        with self.assertRaises(PermissionError):self.call('FINISH')
    def test_different_confirming_account_cannot_replace_first(self):
        self.confirm()
        self.fx.fx.provider.exchange.return_value=dict(appid=self.i.appid,openid='second_provider_only')
        other=self.fx.login('different_code');uid=self.c.session(other)
        self.c.db.execute("INSERT INTO members VALUES('project1',?,'REVIEWER',1)",(uid,))
        self.onboarding.reviewers[uid]='project1'
        with self.assertRaisesRegex(PermissionError,'CONFIRMATION_CONFLICT'):
            self.b.confirm(self.challenge,other,verification=self.start_result['verification'],action='CONFIRM_THIS_BROWSER')
        self.assertEqual(self.call('FINISH')[0]['user_id'],self.uid)
    def test_two_real_sqlite_transactions_race_only_one_issuance(self):
        # Fault/concurrency stress on disposable original DB, not a second production writer.
        import concurrent.futures, threading
        from scripts.pr122_customer_core import Center
        from scripts.community_mini_center_identity import CenterIdentity
        self.confirm();barrier=threading.Barrier(2)
        before=self.c.db.execute('SELECT count(*) FROM sessions').fetchone()[0]
        def finish():
            c=Center(self.fx.fx.tmp.name,{'testkey':b'k'*32},'testkey',clock=lambda:self.fx.fx.stage.now,mail_ready=True)
            try:
                i=CenterIdentity(c,self.fx.fx.stage.api,self.i.appid,self.fx.fx.scenes);i.configure_registration(['shop1'])
                b=ReviewerWebBridge(i,WebSession(c,onboarding=MerchantOnboarding(c,{self.uid:'project1'})),'shop1',ORIGIN)
                barrier.wait(timeout=5)
                return b.browser(self.challenge,action='FINISH',**self.kw)
            finally:c.db.close()
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            a=pool.submit(finish);b=pool.submit(finish);results=[a.result(),b.result()]
        self.assertEqual(sum(cookie is not None for _,cookie in results),1)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM sessions').fetchone()[0],before+1)
    def test_exact_scene_consumer_revocation_not_masked_by_other_scene(self):
        from scripts.community_mini_center_identity import CenterIdentity
        from scripts.community_mini_login import MiniGateway
        from scripts.community_saas_phase2 import Principal
        second=Principal('tenant1','CUSTOMER')
        self.i.runtime.bindings[second]=dict(self.i.runtime.bindings[self.fx.fx.stage.customer],store_id='second_store')
        scenes=dict(self.fx.fx.scenes,shop2=dict(project='project1',principal=second))
        i=CenterIdentity(self.c,self.i.runtime,self.i.appid,scenes);i.configure_registration(['shop1','shop2'])
        self.fx.fx.provider.exchange.return_value=dict(appid=i.appid,openid='two_scene_customer')
        mini=MiniGateway(self.fx.fx.stage.api,i,self.fx.fx.provider).login({'code':'two_scene_code'})['session_token']
        uid=self.c.session(mini)
        self.c.db.execute("INSERT INTO members VALUES('project1',?,'REVIEWER',1)",(uid,))
        b=ReviewerWebBridge(i,WebSession(self.c,onboarding=MerchantOnboarding(self.c,{uid:'project1'})),'shop2',ORIGIN)
        started,cookie=b.begin(origin=ORIGIN,source='127.0.0.1')
        b.confirm(started['challenge'],mini,verification=started['verification'],action='CONFIRM_THIS_BROWSER')
        key=self.c.idx('community-consumer:'+uid+':shop2')
        self.c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_WECHAT_CONSUMER_V1' AND subject_idx=?",(key,))
        with self.assertRaises(PermissionError):i._resolve(mini,'shop2')
        with self.assertRaises(PermissionError):b.browser(started['challenge'],browser=cookie.split(';')[0].split('=',1)[1],csrf=started['csrf'],origin=ORIGIN,action='FINISH')
if __name__=='__main__':unittest.main()
