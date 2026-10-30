"""Offline synthetic fixtures only; real original Center and identity execution."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_community_wechat_registration as identity_fixture
from scripts.pr122_customer_core import canonical,digest
from scripts.community_merchant_onboarding import MerchantOnboarding
from scripts.community_platform_reviewer_admission import ReviewerAdmission

class Admission(unittest.TestCase):
    def setUp(self):
        self.fx=identity_fixture.NativeConsumer(); self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.c=self.fx.c
        self.c.db.execute("UPDATE projects SET owner='system_community_platform' WHERE id='project1'")
        from scripts.community_mini_center_identity import CenterIdentity
        from scripts.community_mini_login import MiniGateway
        self.fx.i=CenterIdentity(self.c,self.fx.i.runtime,self.fx.i.appid,self.fx.fx.scenes)
        self.fx.i.configure_registration(['shop1'])
        self.fx.g=MiniGateway(self.fx.i.runtime,self.fx.i,self.fx.fx.provider)
        self.token=self.fx.login();self.uid=self.c.session(self.token)
        self.service=ReviewerAdmission(self.c,self.fx.i)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'plan.json'
        self.snapshot=self.service.inspect('project1',self.uid)
        self.plan=dict(version=1,action='GRANT',role='REVIEWER',request_id='admission1',project='project1',uid=self.uid,
                       expected_revision=0,snapshot=self.snapshot,
                       approval=dict(owner_message_id='SYNTHETIC_OWNER_MESSAGE',owner_body_sha256='a'*64))
        self.business=object.__new__(MerchantOnboarding)
        self.business.center=self.c;self.business.reviewers={self.uid:'project1'}
    def apply(self, plan=None, approved=True):
        p=self.plan if plan is None else plan
        self.path.write_bytes(canonical(p));self.path.chmod(0o600)
        sha=digest(canonical(p))
        # Explicit synthetic owner adapter, never production authority.
        return self.service.apply_protected(str(self.path),sha,lambda supplied,metadata:approved and supplied==sha)
    def revoke(self):
        p=copy.deepcopy(self.plan);p.update(action='REVOKE',request_id='revoke1',expected_revision=1)
        return self.apply(p)
    def test_original_reviewer_and_consumer_preserved(self):
        before=self.c.db.execute("SELECT payload FROM projects WHERE id='project1'").fetchone()[0]
        with self.assertRaises(PermissionError):self.business._reviewer(self.uid)
        self.assertEqual(self.apply()['status'],'GRANTED')
        self.business._reviewer(self.uid)
        self.assertEqual(self.fx.i.resolve(self.token,'shop1',self.c.now()).role,'CUSTOMER')
        self.assertEqual(self.c.db.execute("SELECT payload FROM projects WHERE id='project1'").fetchone()[0],before)
        self.assertEqual(self.c.session(self.token),self.uid)
        with self.assertRaises(PermissionError):self.c.project(self.uid,'project2',('REVIEWER',))
    def test_owner_denied_and_plan_sha(self):
        with self.assertRaises(PermissionError):self.apply(approved=False)
        with self.assertRaises(PermissionError):self.service.apply_protected(str(self.path),'0'*64,lambda *a:True)
        self.assertEqual(self.service.query('admission1')['status'],'NOT_FOUND')
    def test_repeat_conflict_and_revoked_replay(self):
        self.apply();self.assertEqual(self.apply()['revision'],1)
        p=copy.deepcopy(self.plan);p['approval']['owner_message_id']='different'
        with self.assertRaises(ValueError):self.apply(p)
        self.revoke()
        with self.assertRaises(PermissionError):self.business._reviewer(self.uid)
        result=self.apply();self.assertEqual(result['status'],'REVOKED');self.assertTrue(result['superseded'])
        self.assertEqual(self.fx.i.resolve(self.token,'shop1',self.c.now()).role,'CUSTOMER')
    def test_fresh_request_cannot_duplicate_grant(self):
        self.apply();p=copy.deepcopy(self.plan);p.update(request_id='duplicate',expected_revision=1)
        with self.assertRaises(ValueError):self.apply(p)
    def test_account_epoch_drift(self):
        self.c.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?',(self.uid,))
        with self.assertRaises(ValueError):self.apply()
    def test_project_drift(self):
        self.c.db.execute("UPDATE projects SET revision=revision+1 WHERE id='project1'")
        with self.assertRaises(ValueError):self.apply()
    def test_provider_revocation(self):
        self.c.db.execute("UPDATE links SET active=0 WHERE channel='WECHAT_MINI' AND user_id=?",(self.uid,))
        with self.assertRaises(PermissionError):self.apply()
    def test_consumer_revocation(self):
        self.c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_WECHAT_CONSUMER_V1' AND user_id=?",(self.uid,))
        with self.assertRaises(PermissionError):self.apply()
    def test_unmanaged_member_never_overwritten(self):
        self.c.db.execute('INSERT INTO members VALUES(?,?,?,1)',('project1',self.uid,'EDITOR'))
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.c.db.execute('SELECT role FROM members WHERE user_id=?',(self.uid,)).fetchone()[0],'EDITOR')
    def test_audit_crash_rolls_back_all(self):
        with patch.object(self.c,'audit',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.apply()
        self.assertEqual(self.service.query('admission1')['status'],'NOT_FOUND')
        self.assertIsNone(self.c.db.execute('SELECT 1 FROM members WHERE user_id=?',(self.uid,)).fetchone())
        self.assertEqual(self.apply()['revision'],1)
    def test_commit_response_loss_is_query_only_replay(self):
        self.apply() # Treat response as lost; query then replay never changes revision/audit.
        n=self.c.db.execute('SELECT count(*) FROM audit').fetchone()[0]
        self.assertEqual(self.service.query('admission1')['revision'],1)
        self.apply();self.assertEqual(self.c.db.execute('SELECT count(*) FROM audit').fetchone()[0],n)
    def test_revoke_after_session_and_project_expired(self):
        self.apply()
        # Advance fixture clock beyond original project expiry, not project contents.
        expiry=self.snapshot['project']['expires']
        with patch.object(self.c,'clock',return_value=expiry+1):
            self.assertEqual(self.revoke()['status'],'REVOKED')
    def test_member_drift_query_holds(self):
        self.apply();self.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.uid,))
        with self.assertRaises(ValueError):self.service.query('admission1')
    def test_regrant_requires_new_confirmation_revision(self):
        self.apply();self.revoke();p=copy.deepcopy(self.plan);p.update(request_id='admission2',expected_revision=2)
        self.assertEqual(self.apply(p)['revision'],3);self.business._reviewer(self.uid)
    def test_process_crash_before_audit_has_no_partial_commit(self):
        child=os.fork()
        if child==0:
            with patch.object(self.c,'audit',side_effect=lambda *a:os._exit(73)):
                self.apply()
            os._exit(74)
        _,status=os.waitpid(child,0)
        self.assertEqual(os.waitstatus_to_exitcode(status),73)
        self.assertEqual(self.service.query('admission1')['status'],'NOT_FOUND')
        self.assertIsNone(self.c.db.execute('SELECT 1 FROM members WHERE user_id=?',(self.uid,)).fetchone())
        self.assertEqual(self.apply()['revision'],1)
    def test_wrong_realm_and_tenant(self):
        self.c.db.execute("UPDATE projects SET owner='human_owner' WHERE id='project1'")
        with self.assertRaises(PermissionError):self.apply()
        self.c.db.execute("UPDATE projects SET owner='system_community_platform',tenant='tenant2' WHERE id='project1'")
        with self.assertRaises(PermissionError):self.apply()
    def test_protected_file_permissions_and_role(self):
        self.path.write_bytes(canonical(self.plan));self.path.chmod(0o644)
        with self.assertRaises(PermissionError):
            self.service.apply_protected(str(self.path),digest(canonical(self.plan)),lambda *a:True)
        p=copy.deepcopy(self.plan);p['role']='OWNER'
        with self.assertRaises(PermissionError):self.apply(p)
    def test_wrong_uid(self):
        p=copy.deepcopy(self.plan);p['uid']=self.fx.fx.uid2
        with self.assertRaises(ValueError):self.apply(p)
    def test_missing_prior_request_prevents_revoke(self):
        self.apply()
        self.c.db.execute("DELETE FROM links WHERE channel='COMMUNITY_PLATFORM_REVIEWER_REQUEST_V1' AND subject_idx='admission1'")
        with self.assertRaises(ValueError):self.revoke()
        self.business._reviewer(self.uid)
    def test_consumer_scope_store_drift_rejected_even_fresh_inspect(self):
        row=self.c.db.execute("SELECT * FROM links WHERE channel='COMMUNITY_WECHAT_CONSUMER_V1' AND user_id=?",(self.uid,)).fetchone()
        value=json.loads(self.c.decrypt(row['payload'],'community-wechat-consumer'))
        value['scope']['store_id']='wrong_store'
        self.c.db.execute("UPDATE links SET payload=? WHERE channel=? AND subject_idx=? AND project=?",
            (self.c.encrypt(canonical(value),'community-wechat-consumer'),row['channel'],row['subject_idx'],row['project']))
        with self.assertRaises(PermissionError):self.service.inspect('project1',self.uid)
    def test_no_nested_transaction(self):
        with self.c.tx():
            with self.assertRaises(ValueError):self.apply()

if __name__=='__main__':unittest.main()
