"""Isolated merge regression only; fixtures are not registered formal sources."""
import os
import sqlite3
import tempfile
import unittest
from task_center_handoff_runtime import FormalSessionStore, HostIdentityProvider
from task_center_handoff_backend import CanonicalHandoffBackend
from task_center_provenance_consumer import GuardedProvenanceConsumer
from test_guarded_provenance_consumer_delta import Source


class InstalledProvenanceMerge(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=os.path.join(self.tmp.name,'isolated.sqlite')
        def connect():
            db=sqlite3.connect(self.path);db.row_factory=sqlite3.Row;return db
        self.connect=connect
        self.sessions=FormalSessionStore(connect,'tenant',clock=lambda:100)
        self.source=Source();self.roles=['TASK_CENTER_ADMIN']
        def mapper(binding):
            return dict(tenant_id=binding['tenant_id'],principal_id=binding['principal_id'],roles=list(self.roles))
        self.consumer=GuardedProvenanceConsumer(self.sessions,self.source,mapper,clock=lambda:100)
        db=connect()
        try:
            db.execute('CREATE TABLE authority_runtime_profile(singleton INTEGER,profile TEXT)')
            db.execute("INSERT INTO authority_runtime_profile VALUES(1,'FORMAL')");db.commit()
            self.backend=CanonicalHandoffBackend(self.sessions,self.consumer,'fixture-only',db,clock=lambda:100)
        finally:db.close()
        self.identity=HostIdentityProvider('tenant',self.backend,clock=lambda:100)
        self.sessions.bind_identity(self.identity)
    def login(self):
        identity,(token,csrf,expiry)=self.identity.guarded_login(self.sessions,'fixture','fixture')
        return token,self.sessions.get(token)
    def test_prefixed_canonical_session_and_live_management_context(self):
        token,session=self.login()
        self.assertTrue(session['session_hash'].startswith('formal:'))
        context=self.sessions.management_context(session,None)
        self.assertEqual(context.verify(context.context),'tenant')
        self.source.live=False
        self.assertIsNone(self.sessions.get(token))
        with self.assertRaisesRegex(ValueError,'CURRENT_FORMAL_MANAGEMENT_SESSION_REQUIRED'):
            context.verify(context.context)
    def test_mapper_role_change_and_logout_do_not_reuse_old_session(self):
        token,session=self.login();self.roles=['TASK_EXECUTOR']
        self.assertIsNone(self.sessions.get(token))
        self.roles=['TASK_CENTER_ADMIN'];self.sessions.revoke(token)
        self.assertFalse(self.identity.is_formal_session(session))
    def test_final_guard_failure_rolls_back_canonical_session(self):
        self.source.at_guard=lambda:setattr(self.source,'live',False)
        with self.assertRaisesRegex(ValueError,'FORMAL_PROVENANCE_UNAVAILABLE'):self.login()
        db=self.connect()
        try:self.assertEqual(db.execute('SELECT count(*) FROM task_center_sessions').fetchone()[0],0)
        finally:db.close()
    def test_test_only_profile_rejects_before_login_write(self):
        db=self.connect()
        try:db.execute("UPDATE authority_runtime_profile SET profile='TEST_ONLY'");db.commit()
        finally:db.close()
        with self.assertRaisesRegex(ValueError,'FORMAL_PROVENANCE_UNAVAILABLE'):self.login()
        db=self.connect()
        try:self.assertEqual(db.execute('SELECT count(*) FROM task_center_sessions').fetchone()[0],0)
        finally:db.close()

if __name__=='__main__':unittest.main()
