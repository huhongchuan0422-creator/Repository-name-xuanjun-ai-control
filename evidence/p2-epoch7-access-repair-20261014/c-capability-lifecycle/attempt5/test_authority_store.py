"""Real SQLite restart, concurrency, fencing and quota tests; local-only."""
import multiprocessing
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'runtime'),str(HERE/'original')]
from authority_store import AuthorityStore
from receipt_provider import Hold

def grant():
    return {'grant_id':'test_grant_attempt5','source_commit':'a'*40,'source_tree':'b'*40,
            'kit_sha256':'c'*64,'manifest_sha256':'d'*64,'target_host':'TEST_ONLY',
            'actor_id':'fixture','expires_utc':1000,'recovery_entry':'fixture',
            'approval_body_sha256':'e'*64,'max_attempts':5}
def claimant(path, name, queue):
    store=AuthorityStore(path,clock=lambda:100)
    try:store.lease(grant(),name);queue.put('HELD')
    except Hold:queue.put('HOLD')
    finally:store.close()

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();os.chmod(self.tmp.name,0o700)
        self.path=str(Path(self.tmp.name)/'authority.db');self.now=100
        self.store=AuthorityStore(self.path,initialize=True,clock=lambda:self.now)
        self.g=grant();self.store.register(self.g);self.token=self.store.lease(self.g,'writer')
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def consume(self,n):return self.store.consume(self.g,'attempt-'+str(n),n,'a'*64,self.token)
    def reconcile(self,n,outcome='NO_WRITE'):
        return self.store.reconcile(self.g,'attempt-'+str(n),outcome,'b'*64,self.token,lambda *args:True)
    def test_five_persistently_consumed(self):
        for n in range(1,6):self.assertEqual(self.consume(n),n);self.reconcile(n)
        with self.assertRaises(Hold):self.store.consume(self.g,'six',5,'a'*64,self.token)
    def test_success_stops_immediately(self):
        self.consume(1);self.reconcile(1,'SUCCESS')
        with self.assertRaises(Hold):self.consume(2)
    def test_unknown_stops(self):
        self.consume(1)
        with self.assertRaises(Hold):self.consume(2)
    def test_reopen_retains_consumption(self):
        self.consume(1);self.reconcile(1);self.store.close()
        self.store=AuthorityStore(self.path,clock=lambda:self.now)
        self.assertEqual(self.consume(2),2)
    def test_duplicate_rpc_does_not_consume_twice(self):
        self.consume(1);self.assertEqual(self.consume(1),1)
        self.assertEqual(self.store.db.execute('SELECT consumed FROM grants').fetchone()[0],1)
    def test_different_operation_conflict(self):
        self.consume(1)
        with self.assertRaises(Hold):self.store.consume(self.g,'attempt-1',1,'f'*64,self.token)
    def test_lost_lease_stops(self):
        self.now=131
        with self.assertRaises(Hold):self.consume(1)
    def test_expired_reacquisition_advances_fence(self):
        old=dict(self.token);self.now=131;self.token=self.store.lease(self.g,'writer')
        self.assertGreater(self.token['fence'],old['fence'])
        with self.assertRaises(Hold):self.store.consume(self.g,'old',1,'a'*64,old)
    def test_concurrent_writer_refused(self):
        with self.assertRaises(Hold):self.store.lease(self.g,'other')
    def test_two_processes_have_one_writer(self):
        self.now=131;self.store.close();self.store=AuthorityStore(self.path,clock=lambda:self.now)
        # Both child clocks observe the old lease as expired.
        self.store.db.execute('UPDATE grants SET expiry=99')
        context=multiprocessing.get_context('fork');q=context.Queue()
        ps=[context.Process(target=claimant,args=(self.path,'p'+str(i),q)) for i in range(2)]
        for p in ps:p.start()
        for p in ps:p.join(10);self.assertEqual(p.exitcode,0)
        self.assertEqual(sorted([q.get(timeout=2),q.get(timeout=2)]),['HELD','HOLD'])
    def test_unverified_reconciliation_refused(self):
        self.consume(1)
        with self.assertRaises(Hold):self.store.reconcile(self.g,'attempt-1','NO_WRITE','b'*64,self.token,lambda *args:False)
        with self.assertRaises(Hold):self.consume(2)
    def test_safe_checkpoint_allows_next(self):
        self.consume(1);self.reconcile(1,'SAFE_CHECKPOINT');self.assertEqual(self.consume(2),2)
    def test_no_automatic_database_recreation(self):
        with self.assertRaises(FileNotFoundError):AuthorityStore(str(Path(self.tmp.name)/'missing.db'))
    def test_symlink_refused(self):
        link=str(Path(self.tmp.name)/'link.db');os.symlink(self.path,link)
        with self.assertRaises(Hold):AuthorityStore(link)
    def test_wrong_mode_refused(self):
        os.chmod(self.path,0o644)
        with self.assertRaises(Hold):AuthorityStore(self.path)
        os.chmod(self.path,0o600)
    def test_same_approval_cannot_mint_fresh_quota(self):
        duplicate=dict(self.g);duplicate['grant_id']='different_grant_id'
        with self.assertRaises(sqlite3.IntegrityError):self.store.register(duplicate)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM grants').fetchone()[0],1)
    def test_source_binding_change_refused(self):
        changed=dict(self.g);changed['source_commit']='f'*40
        with self.assertRaises(Hold):self.store.lease(changed,'writer')
    def test_reinitialization_refused(self):
        with self.assertRaises(FileExistsError):AuthorityStore(self.path,initialize=True)
    def test_terminal_reconciliation_cannot_be_rewritten(self):
        self.consume(1);self.reconcile(1,'SUCCESS')
        with self.assertRaises(Hold):self.reconcile(1,'NO_WRITE')

if __name__=='__main__':unittest.main()
