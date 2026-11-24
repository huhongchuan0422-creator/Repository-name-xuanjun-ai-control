"""Only synthetic identities, original Center and provider-login/entry services."""
import hashlib
import unittest
from dataclasses import replace
from unittest.mock import patch
import test_community_wechat_registration as fixtures
from scripts.pr122_customer_core import canonical
from scripts import community_mini_exact_release as release
from scripts.community_mini_login import LoginUnavailable
from scripts.community_merchant_onboarding import MerchantOnboarding
from scripts.community_mini_merchant import MiniMerchant

class ExactMiniRelease(unittest.TestCase):
    def setUp(self):
        self.fx=fixtures.NativeConsumer();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.c,self.i=self.fx.c,self.fx.i
        self.old_token=self.fx.login('initial_native');self.uid=self.c.session(self.old_token)
        self.fx.fx.provider.exchange.return_value=dict(appid=self.i.appid,openid='other_test_native')
        self.other_token=self.fx.login('other_native');self.other_uid=self.c.session(self.other_token)
        self.fx.fx.provider.exchange.return_value=dict(appid=self.i.appid,openid='new_customer_openid')
        self.targets=[]
        for uid,app in [(self.uid,'fixture_app_1'),(self.other_uid,'fixture_app_2')]:
            row=self.c.db.execute("SELECT * FROM links WHERE channel='WECHAT_MINI' AND user_id=?",(uid,)).fetchone()
            t=release.Target(app,uid,row['subject_idx'],row['project'],release.version(row));self.targets.append(t)
            value=dict(business_code='fixture_code_'+app,applyment_id='fixture_apply_'+app,provider_sp_mchid='fixture_provider')
            obs=dict(record_digest=hashlib.sha256(canonical(value)).hexdigest(),provider_state='APPLYMENT_STATE_FINISHED',sync_error=None,binding=dict(owner=uid,application=app,active=True,business_code=value['business_code'],applyment_id=value['applyment_id'],provider_merchant=value['provider_sp_mchid']))
            self.c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)',('COMMUNITY_WECHAT_APPLYMENT',app,uid,app,self.c.encrypt(canonical(value),'wechat-applyment:'+app)))
            self.c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)',('COMMUNITY_WECHAT_OBSERVATION',app,uid,app,self.c.encrypt(canonical(obs),'wechat-observation:'+app)))
        self.targets=tuple(self.targets)
        self.scope=patch.object(release,'AUTHORIZED_REFS',frozenset(release.application_ref(t.application) for t in self.targets));self.scope.start();self.addCleanup(self.scope.stop)
        self.service=release.ExactRelease(self.c,self.targets);self.t=self.targets[0];self.key='fixture_exact_release_1'
        self.before=self.history()

    def history(self):
        return [tuple(r) for r in self.c.db.execute("SELECT * FROM links WHERE channel NOT IN ('WECHAT_MINI','WECHAT_MINI_SESSION',?) ORDER BY channel,subject_idx,project",(release.CHANNEL,))]

    def row(self):
        return self.c.db.execute("SELECT * FROM links WHERE channel='WECHAT_MINI' AND subject_idx=?",(self.t.subject,)).fetchone()

    def test_exact_release_keeps_history_other_subject_and_replay(self):
        other=self.c.db.execute("SELECT * FROM links WHERE channel='WECHAT_MINI' AND user_id=?",(self.other_uid,)).fetchone()
        result=self.service.release(self.t,self.key);self.assertEqual(result['state'],'RELEASED')
        self.assertEqual(self.row()['active'],0);self.assertEqual(self.before,self.history())
        self.assertEqual(tuple(other),tuple(self.c.db.execute("SELECT * FROM links WHERE channel='WECHAT_MINI' AND user_id=?",(self.other_uid,)).fetchone()))
        changes=self.c.db.total_changes;self.assertEqual(self.service.release(self.t,self.key),result);self.assertEqual(changes,self.c.db.total_changes)
        with self.assertRaises(PermissionError):self.i.applicant_context(self.old_token)
        self.assertEqual(self.i.applicant_context(self.other_token)[0],self.other_uid)
        with self.assertRaises(PermissionError):self.service.release(self.t,'another_release_key')
        self.assertEqual(self.c.check_integrity()['integrity'],'PASS')

    def test_both_exact_objects_release_independently(self):
        for n,t in enumerate(self.targets):
            result=self.service.release(t,self.key+str(n))
            self.assertEqual(result['safe_id'],release.application_ref(t.application))
            self.assertEqual(result['state'],'RELEASED')
        self.assertEqual(self.c.db.execute("SELECT count(*) FROM links WHERE channel='WECHAT_MINI' AND subject_idx IN (?,?) AND active=0",tuple(t.subject for t in self.targets)).fetchone()[0],2)
        self.assertEqual(self.before,self.history())

    def test_restore_before_login_exact_and_idempotent(self):
        self.service.release(self.t,self.key);result=self.service.restore(self.t,self.key)
        self.assertEqual(result['state'],'RESTORED');self.assertEqual(release.version(self.row()),self.t.version)
        self.assertEqual(self.service.restore(self.t,self.key),result)
        self.assertEqual(self.i.applicant_context(self.old_token)[0],self.uid)
        self.assertEqual(self.c.session(self.fx.login('restored_login')),self.uid)
        self.assertEqual(self.before,self.history())

    def test_verified_fresh_login_original_mini_entry_no_old_route(self):
        self.service.release(self.t,self.key);fresh=self.fx.login('fresh_verified_login');uid=self.c.session(fresh)
        self.assertNotEqual(uid,self.uid);self.assertEqual(self.row()['user_id'],uid)
        self.assertEqual(self.i.applicant_context(fresh)[0],uid)
        with self.assertRaises(PermissionError):self.i.applicant_context(self.old_token)
        onboarding=MerchantOnboarding(self.c,{self.fx.fx.uid2:'project1'});entry=MiniMerchant(self.i,onboarding)
        result=entry.dispatch(fresh,'',dict(operation='onboarding',params=dict(operation='mine',params={})))
        self.assertEqual(result,dict(applications=[],next_cursor=None))
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM members WHERE user_id=?',(uid,)).fetchone()[0],0)
        self.assertEqual(self.c.session(self.fx.login('repeat_fresh')),uid)
        self.assertEqual(self.service.release(self.t,self.key)['state'],'CONSUMED')
        with self.assertRaisesRegex(PermissionError,'CONSUMED'):self.service.restore(self.t,self.key)
        # Original account marker and provider/application/history bytes survive.
        for old in self.before:
            self.assertIn(old,self.history())
        self.assertEqual(self.c.check_integrity()['integrity'],'PASS')

    def test_stale_cas_wrong_subject_and_scope_fail_without_writes(self):
        for t in [replace(self.t,version='0'*64),replace(self.t,owner=self.other_uid),replace(self.t,subject=self.targets[1].subject),replace(self.t,project='wrong_project')]:
            with self.subTest(t=t):
                policy=(t,self.targets[1])
                with self.assertRaises(PermissionError):release.ExactRelease(self.c,policy).release(t,self.key)
                self.assertEqual(release.version(self.row()),self.t.version)
        with self.assertRaises(PermissionError):release.ExactRelease(self.c,(self.t,))
        with self.assertRaises(PermissionError):self.service.release(replace(self.t,application='not_authorized'),self.key)

    def test_changed_finished_evidence_denied(self):
        self.c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_WECHAT_OBSERVATION' AND project=?",(self.t.application,))
        with self.assertRaises(PermissionError):self.service.release(self.t,self.key)
        self.assertEqual(release.version(self.row()),self.t.version)

    def test_release_audit_failure_rolls_back(self):
        with patch.object(self.c,'audit',side_effect=OSError('synthetic audit failure')):
            with self.assertRaises(OSError):self.service.release(self.t,self.key)
        self.assertEqual(release.version(self.row()),self.t.version)
        self.assertIsNone(release._receipt(self.c,self.t.subject,self.t.project))

    def test_new_login_audit_failure_preserves_pending_release_and_account_count(self):
        self.service.release(self.t,self.key);before=self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0]
        audit=self.c.audit
        def fail(project,actor,event,obj):
            if event=='COMMUNITY_CONSUMER_REGISTERED':raise OSError('synthetic login audit failure')
            return audit(project,actor,event,obj)
        with patch.object(self.c,'audit',side_effect=fail):
            with self.assertRaises(LoginUnavailable):self.fx.login('fresh_failed_audit')
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0],before)
        self.assertEqual(self.row()['active'],0);self.assertEqual(release._receipt(self.c,self.t.subject,self.t.project)['state'],'RELEASED')
        fresh=self.fx.login('retry_new_code');self.assertNotEqual(self.c.session(fresh),self.uid)

    def test_provider_failure_does_not_consume_release(self):
        self.service.release(self.t,self.key);self.fx.fx.provider.exchange.side_effect=TimeoutError()
        with self.assertRaises(LoginUnavailable):self.fx.login('provider_unknown')
        self.assertEqual(self.row()['active'],0);self.assertEqual(release._receipt(self.c,self.t.subject,self.t.project)['state'],'RELEASED')

    def test_shared_project_subject_is_not_broadly_unlinked(self):
        row=self.row();self.c.db.execute("INSERT INTO links VALUES('WECHAT_MINI',?,?,?,?,1)",(self.t.subject,self.uid,'other_project',row['payload']))
        with self.assertRaisesRegex(PermissionError,'SINGLE_PROJECT'):self.service.release(self.t,self.key)
        self.assertEqual(self.row()['active'],1)

    def test_disabled_registration_or_changed_released_link_denies_fresh_login(self):
        self.service.release(self.t,self.key);saved=self.i.registration;self.i.registration={}
        with self.assertRaises(LoginUnavailable):self.fx.login('disabled_registration')
        self.i.registration=saved
        self.c.db.execute("UPDATE links SET payload=? WHERE channel='WECHAT_MINI' AND subject_idx=?",(self.c.encrypt(b'{}','wechat-mini-link'),self.t.subject))
        with self.assertRaises(LoginUnavailable):self.fx.login('changed_release')
        with self.assertRaises(PermissionError):self.service.restore(self.t,self.key)
