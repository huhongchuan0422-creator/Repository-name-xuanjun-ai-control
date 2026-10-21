import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from production.cloud_connection.queue import Queue, Hold
from production.cloud_connection.action_binding import prepare, SEALED_REQUEST


class ActionBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/root')
        self.q=Queue(str(Path(self.tmp.name)/'queue.sqlite'),'a'*64,{332398908})
        self.b={'schema':1,'action_ref':'website-fixed-baseline','project':'pr122','target':'domestic',
                'operation':'website_baseline_collect','source_commit':'b'*40,
                'adapter_path':'tools/pr122_static_baseline_readonly.py','adapter_sha256':'c'*64,
                'input_manifest_sha256':'d'*64,'plan_sha256':'e'*64,'approval_ref':'offline-fixture',
                'execution_identity':'root','valid_from':100,'valid_until':100+18000}
        self.bind()
    def tearDown(self): self.q.close(); self.tmp.cleanup()
    def bind(self):
        self.raw=json.dumps(self.b,sort_keys=True).encode(); self.sha=hashlib.sha256(self.raw).hexdigest()
        self.request={'request_id':'fixed-action','project':'pr122','target':'domestic',
                      'operation':'project_fixed_action','arguments':{'binding_sha256':self.sha}}
        self.q.db.execute('INSERT INTO connection_jobs VALUES(?,?,?,?,?,?,?,?)',
                          ('fixed-action','pr122',json.dumps(self.request),'f'*64,332398908,'READY',None,None))
    def plan(self,**kw):
        return prepare(self.q.db,kw.get('raw',self.raw),kw.get('sha',self.sha),
                       kw.get('request_id','fixed-action'),kw.get('actor',332398908),kw.get('now',101))
    def test_preparation_is_not_dispatch_or_permission(self):
        r=self.plan(); self.assertFalse(r['dispatch_permitted'])
        self.assertEqual(r['installation_permission'],'NOT_ISSUED')
        self.assertEqual(self.q.inspect('fixed-action')['state'],'READY')
    def test_other_fixed_operations_cannot_rebind_existing_job(self):
        from production.cloud_connection.action_binding import OPERATIONS
        for operation in OPERATIONS:
            if operation == self.b['operation']:
                self.assertFalse(self.plan()['dispatch_permitted'])
                continue
            b=dict(self.b,operation=operation); raw=json.dumps(b,sort_keys=True).encode()
            # Wrong original binding cannot be silently rebound to another action.
            with self.assertRaisesRegex(Hold,'SCOPE'): self.plan(raw=raw,sha=hashlib.sha256(raw).hexdigest())
    def test_arbitrary_shell_and_flags_rejected(self):
        for key,value in [('command','sudo arbitrary'),('approved',True),('retry',True)]:
            b=dict(self.b); b[key]=value; raw=json.dumps(b).encode()
            with self.assertRaises(Hold): self.plan(raw=raw,sha=hashlib.sha256(raw).hexdigest())
    def test_missing_or_mismatched_original_job(self):
        with self.assertRaisesRegex(Hold,'REQUIRED'): self.plan(request_id='missing')
        with self.assertRaisesRegex(Hold,'ENROLLMENT'): self.plan(sha='0'*64)
    def test_unknown_without_invoke_never_dispatches(self):
        self.q.db.execute("UPDATE connection_jobs SET state='UNKNOWN'")
        self.assertEqual(self.plan()['next'],'HOLD_ORIGINAL_TRANSACTION_RECONCILIATION')
    def test_unknown_with_invoke_queries_original_only(self):
        self.q.db.execute("UPDATE connection_jobs SET state='UNKNOWN',invoke_id='t-original'")
        r=self.plan(); self.assertEqual(r['next'],'QUERY_ORIGINAL_INVOKE_ONLY')
        self.assertEqual(r['invoke_id'],'t-original'); self.assertFalse(r['dispatch_permitted'])
    def test_success_is_not_replayed(self):
        self.q.db.execute("UPDATE connection_jobs SET state='SUCCESS',invoke_id='t-original'")
        self.assertEqual(self.plan()['next'],'DONE_NO_REPLAY')
    def test_failed_uses_original_recovery_gate(self):
        self.q.db.execute("UPDATE connection_jobs SET state='FAILED'")
        self.assertEqual(self.plan()['next'],'HOLD_ORIGINAL_RECOVERY_POLICY')
    def test_wrong_actor_and_sealed_request(self):
        with self.assertRaises(Hold): self.plan(actor=18598789888)
        with self.assertRaisesRegex(Hold,'SEALED'): self.plan(request_id=SEALED_REQUEST)
    def test_expiry_and_no_new_ledger(self):
        with self.assertRaisesRegex(Hold,'WINDOW'): self.plan(now=18100)
        before=self.q.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        self.plan()
        self.assertEqual(before,self.q.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
