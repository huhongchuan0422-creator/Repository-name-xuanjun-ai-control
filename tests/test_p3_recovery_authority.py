"""TEST_ONLY signing keys and isolated SQLite recovery ownership fixtures."""
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from src.p3_admission_v2 import TrustStore,canonical
from src.p3_operation_kernel import RunnerOperationStore
from src.p3_recovery_authority import OWNERSHIP_MIGRATION, OwnershipStore, OwnershipGuard, HeartbeatLease

class RecoveryAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=os.path.join(self.tmp.name,'db')
        def connect():return sqlite3.connect(self.db,timeout=10)
        self.connect=connect
        db=connect();db.execute(OWNERSHIP_MIGRATION);db.execute("CREATE TABLE effects (state TEXT NOT NULL)");db.commit();db.close()
        self.keys={k:Ed25519PrivateKey.generate() for k in ('recovery','stop')}
        trust=TrustStore({k:(v.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw),k,'test-authority') for k,v in self.keys.items()}, {})
        self.now=1000
        self.store=OwnershipStore(connect,trust,lambda:self.now,stale_seconds=10)
        self.owner=self.store.claim_initial('operation','attempt',100)
    def sign(self,value,kind,domain):
        result=dict(value,key_id=kind);result['signature']=self.keys[kind].sign(domain+canonical(result)).hex();return result
    def admission(self,proof_kind):
        row=self.store.read('operation')
        value=dict(operation_id=row['operation_id'],attempt_id=row['attempt_id'],observed_owner_token=row['owner_token'],
                   observed_epoch=row['epoch'],observed_fence=row['fence'],observed_lease_expires_at=row['lease_expires_at'],
                   observed_heartbeat_seq=row['heartbeat_seq'],observed_heartbeat_at=row['heartbeat_at'],
                   authority_identity='test-authority',reason='test-owner-stop',proof_kind=proof_kind,
                   issued_at=self.now,expires_at=self.now+60)
        return self.sign(value,'recovery',b'P3-RECOVERY-ADMISSION-V2\x00')
    def stop(self):
        row=self.store.read('operation')
        value=dict(operation_id=row['operation_id'],attempt_id=row['attempt_id'],owner_token=row['owner_token'],
                   epoch=row['epoch'],fence=row['fence'],heartbeat_seq=row['heartbeat_seq'],
                   stopped_at=self.now,authority_identity='test-authority')
        return self.sign(value,'stop',b'P3-OWNER-STOP-V2\x00')
    def test_explicit_same_database_migration_is_idempotent(self):
        db=self.connect();db.execute('DROP TABLE p3_operation_ownership');db.commit();db.close()
        store=RunnerOperationStore(self.connect)
        store.migrate_ownership_schema();store.migrate_ownership_schema()
        db=self.connect();row=db.execute("SELECT name FROM sqlite_master WHERE name='p3_operation_ownership'").fetchone();db.close()
        self.assertEqual(('p3_operation_ownership',),row)

    def test_managed_heartbeat_advances_and_stops(self):
        heartbeat=HeartbeatLease(self.store,'operation',self.owner,100,.01).start()
        try:
            deadline=time.monotonic()+2
            while self.store.read('operation')['heartbeat_seq'] < 1 and time.monotonic()<deadline:
                time.sleep(.01)
            heartbeat.assert_live()
            self.assertGreaterEqual(self.store.read('operation')['heartbeat_seq'],1)
        finally:heartbeat.stop()
        with self.assertRaises(PermissionError):heartbeat.assert_live()

    def test_guard_rejects_matching_recovery_while_effect_lock_held(self):
        lockdir=os.path.join(self.tmp.name,'locks');os.mkdir(lockdir,0o700)
        path=os.path.join(lockdir,'guard')
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600);os.close(fd)
        directory=os.open(lockdir,os.O_RDONLY|os.O_DIRECTORY)
        guard=OwnershipGuard(self.store,directory,'guard')
        self.addCleanup(lambda:os.close(directory));self.addCleanup(guard.close)
        proof=self.admission('STOP_RECEIPT');stop=self.stop()
        entered=threading.Event();release=threading.Event();errors=[]
        def effect():
            try:
                with guard.with_exclusive_side_effect('operation',self.owner) as db:
                    entered.set();release.wait(5)
                    db.execute("INSERT INTO effects(state) VALUES ('SWITCHED')")
            except Exception as error:errors.append(str(error))
        thread=threading.Thread(target=effect);thread.start();self.assertTrue(entered.wait(5))
        before=self.store.read('operation')
        with self.assertRaisesRegex(PermissionError,'OWNERSHIP_LOCK_BUSY'):
            guard.claim_recovery(proof,stop)
        self.assertEqual(before,self.store.read('operation'))
        release.set();thread.join(5);self.assertEqual([],errors)
        claimed=guard.claim_recovery(proof,stop)
        self.assertEqual(2,claimed['epoch'])

    def test_guard_rejects_swapped_lock_inode(self):
        lockdir=os.path.join(self.tmp.name,'locks');os.mkdir(lockdir,0o700)
        path=os.path.join(lockdir,'guard')
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600);os.close(fd)
        directory=os.open(lockdir,os.O_RDONLY|os.O_DIRECTORY)
        guard=OwnershipGuard(self.store,directory,'guard')
        try:
            os.rename(path,path+'.old')
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600);os.close(fd)
            with self.assertRaisesRegex(PermissionError,'LOCK_FILE_IDENTITY_CHANGED'):
                with guard.with_exclusive_side_effect('operation',self.owner):pass
        finally:guard.close();os.close(directory)

    def test_active_owner_rejects_stale_claim_and_row_is_unchanged(self):
        before=self.store.read('operation');proof=self.admission('EXPIRED_STALE')
        with self.assertRaises(PermissionError):self.store.claim_recovery(proof)
        self.assertEqual(before,self.store.read('operation'))
    def test_expired_observation_with_changed_heartbeat_rejects(self):
        self.now=1050;self.assertTrue(self.store.heartbeat('operation',self.owner,0,5))
        self.now=1100;proof=self.admission('EXPIRED_STALE')
        self.now=1052;self.assertTrue(self.store.heartbeat('operation',self.owner,1,60))
        self.now=1100
        with self.assertRaises(PermissionError):self.store.claim_recovery(proof)
        self.assertEqual(2,self.store.read('operation')['heartbeat_seq'])
    def test_stale_lease_claim_fences_old_owner_before_rename(self):
        self.now=1200;new=self.store.claim_recovery(self.admission('EXPIRED_STALE'))
        self.assertEqual(2,new['epoch'])
        with self.assertRaises(PermissionError):
            with self.store.owner_effect_transaction('operation',self.owner):
                self.fail('old owner must not reach effect')
    def test_signed_stop_receipt_claims_and_rejects_tampering(self):
        admission=self.admission('STOP_RECEIPT');receipt=self.stop();bad=dict(receipt,signature='00'*64)
        with self.assertRaises(PermissionError):self.store.claim_recovery(admission,bad)
        recovered=self.store.claim_recovery(admission,receipt)
        self.assertEqual(2,recovered['epoch'])
        with self.assertRaises(PermissionError):
            with self.store.owner_effect_transaction('operation',self.owner):pass
    def test_only_new_recovery_owner_can_commit_fenced_journal_update(self):
        self.now=1200
        replacement=self.store.claim_recovery(self.admission('EXPIRED_STALE'))
        for denied in (self.owner,dict(replacement,fence='0'*64)):
            with self.assertRaises(PermissionError):
                with self.store.recovery_effect_transaction('operation',denied) as db:
                    db.execute("INSERT INTO effects (state) VALUES ('forged')")
        with self.store.recovery_effect_transaction('operation',replacement) as db:
            db.execute("INSERT INTO effects (state) VALUES ('RECONCILED')")
        db=self.connect();self.assertEqual([('RECONCILED',)],db.execute('SELECT state FROM effects').fetchall());db.close()

    def test_bad_admission_signature_and_extra_fields_rejected(self):
        self.now=1200;proof=self.admission('EXPIRED_STALE')
        with self.assertRaises(PermissionError):self.store.claim_recovery(dict(proof,signature='00'*64))
        with self.assertRaises(ValueError):self.store.claim_recovery(dict(proof,extra=True))
    def test_rename_lock_excludes_recovery_claim_until_commit(self):
        # TEST_ONLY signed stop evidence and a stable clock: the DB lock must
        # still serialize the claim against any in-flight effect.
        proof=self.admission('STOP_RECEIPT');stop=self.stop()
        inside=threading.Event();release=threading.Event();claimed=threading.Event();errors=[]
        src=os.path.join(self.tmp.name,'before');dst=os.path.join(self.tmp.name,'after')
        with open(src,'wb') as f:f.write(b'x')
        def old_owner():
            try:
                with self.store.owner_effect_transaction('operation',self.owner) as db:
                    inside.set();release.wait(5);os.rename(src,dst)
                    db.execute("INSERT INTO effects (state) VALUES ('SWITCHED')")
            except Exception as e:errors.append(type(e).__name__)
        thread=threading.Thread(target=old_owner);thread.start();self.assertTrue(inside.wait(5))
        def claim():
            try:self.store.claim_recovery(proof,stop);claimed.set()
            except Exception as e:errors.append(type(e).__name__)
        recovery=threading.Thread(target=claim);recovery.start();time.sleep(.1)
        self.assertFalse(claimed.is_set())
        release.set();thread.join(5);recovery.join(5)
        self.assertTrue(os.path.exists(dst));self.assertTrue(claimed.is_set())
        self.assertEqual([],errors)
        db=self.connect();self.assertEqual(('SWITCHED',),db.execute('SELECT state FROM effects').fetchone());db.close()
