"""Writer authority signs caller-selected target, not a verified receipt."""
import hashlib, sqlite3, tempfile, os, unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from development_authority import authority_payload, canonical_bytes, sign_payload, verify_envelope, SQLiteReplayGuard

class HandoffAuthorityContractGap(unittest.TestCase):
    def test_target_is_not_receipt_evidence(self):
        db=sqlite3.connect(':memory:'); db.row_factory=sqlite3.Row
        db.execute('''CREATE TABLE tasks (task_id TEXT, resource_scope_json TEXT, resource_scope_digest TEXT, state TEXT, authority_state TEXT, authority_valid_until REAL, last_trusted_time REAL, spec_sha256 TEXT, checkpoint_sha256 TEXT, owner TEXT, entry TEXT, authority_caller_id TEXT, authority_run_id TEXT, authority_session_id TEXT, authority_gateway_id TEXT, attempt_id TEXT, lease_id TEXT, fence INTEGER, epoch INTEGER, authority_lock_provider_id TEXT, old_fence_invalidated INTEGER)''')
        db.execute('CREATE TABLE resource_claims (resource_key TEXT,task_id TEXT,attempt_id TEXT,fence INTEGER,epoch INTEGER,state TEXT)')
        scope=hashlib.sha256(canonical_bytes(['repo'])).hexdigest()
        db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('task-1','["repo"]',scope,'RUNNING','VALID',2000,1000,'spec','checkpoint','owner','WORK','caller','run','session','gateway','attempt-1','lease-1',1,1,'lock',0))
        db.execute('INSERT INTO resource_claims VALUES (?,?,?,?,?,?)',('repo','task-1','attempt-1',1,1,'VALID'))
        request={'task_id':'task-1','request_id':'nonce-1','service_id':'reader-1','purpose':'STATUS_QUERY','target_sha256':'e'*64}
        trust={'issuer':'formal-issuer','instance_id':'provider-1','version':'3.0.1'}
        payload=authority_payload(db,request,trust,now=1001.0); db.close()
        self.assertTrue(payload['authority']['authorized']); self.assertEqual(payload['request']['target_sha256'],'e'*64)
        expected=dict(trust,service_id='reader-1',task_id='task-1',attempt_id='attempt-1',lease_id='lease-1',fence=1,epoch=1,resource_scope_digest=scope,request_id='nonce-1',purpose='STATUS_QUERY',target_sha256='e'*64,now=1002.0,max_age=5.0)
        key=Ed25519PrivateKey.generate()
        with tempfile.TemporaryDirectory() as root:
            guard=SQLiteReplayGuard(os.path.join(root,'replay.db'))
            try: verified=verify_envelope(sign_payload(payload,'anchor-1',key),key.public_key(),{'anchor_id':'anchor-1'},expected,guard)
            finally: guard.close()
        self.assertNotIn('tenant_id',verified); self.assertNotIn('receipt',verified); self.assertNotIn('handoff',verified); self.assertNotIn('role_id',verified['writer']); self.assertIn('session_id',verified['writer'])

if __name__=='__main__': unittest.main()
