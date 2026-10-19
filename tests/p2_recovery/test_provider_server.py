"""Management backend tests. Synthetic signed isolation is NEVER UK evidence."""
import base64
import copy
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_recovery as fixture
r=fixture.r
ROOT=Path(__file__).resolve().parents[2]
def load(name):
    spec=importlib.util.spec_from_file_location(name,str(ROOT/'production/p2_recovery'/name))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
e=load('executor.py');e.r=r
s=load('provider_server.py');s.r=r;s.e=e

class ProviderTests(unittest.TestCase):
    setUpClass=classmethod(fixture.RecoveryTests.setUpClass.__func__)
    tearDownClass=classmethod(fixture.RecoveryTests.tearDownClass.__func__)
    write=fixture.RecoveryTests.write
    signed=fixture.RecoveryTests.signed
    def setUp(self):
        fixture.RecoveryTests.setUp(self)
        self.ref=self.source
        self.body['issued_utc']=int(time.time())-1
        self.body['expires_utc']=int(time.time())+20
        self.probe={'schema':1,'operation':'recovery_apply',
            'request_sha256':r.sha(r.canonical(self.request)),'challenge':'b'*32}
        self.reservation={'old_authority_id':self.request['old_authority_id'],
            'authority_id':self.request['new_authority_id'],'epoch':8,'fence':8,
            'writer_id':self.request['writer_id'],'grant_id':self.request['new_grant_id'],
            'database':self.request['target_database'],'plan_sha256':self.ref['sha256'],'exclusive':True}
        self.path=self.root+'/management-reservations.sqlite3'
        s.Reservations.initialize(self.path)
        self.journal=s.Reservations(self.path);self.addCleanup(self.journal.close)
        self.adapter=self.write('adapter.py',b'raise RuntimeError("NO_LIVE_CONTROL_PLANE")\n')
    def sign(self,body):
        return {role:base64.b64encode(subprocess.check_output(['/usr/bin/openssl','dgst',
            '-sha256','-sign',self.private[role]],input=r.canonical(body),
            stderr=subprocess.DEVNULL)).decode('ascii') for role in r.ROLES}
    def response(self):
        body={'schema':1,'probe':copy.deepcopy(self.probe),'issued_utc':int(time.time())-1,
            'expires_utc':int(time.time())+20,'packet':self.signed(),
            'reservation':copy.deepcopy(self.reservation)}
        return {'body':body,'signatures':self.sign(body)}
    def backend(self):
        return s.Backend(self.request,self.public,self.ref,self.body['restoration'],self.journal,self.adapter)
    def handle(self):
        response=self.response()
        with mock.patch.object(s,'adapter_query',return_value=response):return self.backend().handle(self.probe)
    def test_real_signed_backend_commits(self):
        self.handle()
        self.assertEqual(self.journal.db.execute('SELECT count(*) FROM reservations').fetchone(),(1,))
    def test_restart_exact_reentry_no_second_reservation(self):
        self.handle();self.journal.close();self.journal=s.Reservations(self.path)
        self.addCleanup(self.journal.close);self.handle()
        self.assertEqual(self.journal.db.execute('SELECT count(*) FROM reservations').fetchone(),(1,))
    def test_gate_requires_committed_reservation(self):
        self.probe['operation']='execution_gate'
        with self.assertRaises(r.Hold):self.handle()
    def test_gate_after_apply(self):
        self.handle();self.probe['operation']='execution_gate';self.handle()
    def test_conflicting_grant_rejected(self):
        self.handle();self.request['new_grant_id']='another-grant'
        self.probe['request_sha256']=r.sha(r.canonical(self.request))
        self.body['request_sha256']=self.probe['request_sha256']
        self.reservation['grant_id']=self.request['new_grant_id']
        with self.assertRaises(r.Hold):self.handle()
    def test_second_writer_lock(self):
        with self.assertRaises(OSError):s.Reservations(self.path)
    def test_unknown_never_commits(self):
        self.body['history']['unknown_effects']=['UNKNOWN']
        with self.assertRaises(r.Hold):self.handle()
        self.assertEqual(self.journal.db.execute('SELECT count(*) FROM reservations').fetchone(),(0,))
    def test_fence_conflict(self):
        self.reservation['fence']=9
        with self.assertRaises(r.Hold):self.handle()
    def test_numeric_true_rejected(self):
        self.reservation['exclusive']=1
        with self.assertRaises(r.Hold):self.handle()
    def test_bad_signature(self):
        response=self.response();response['signatures']['owner']='AAAA'
        with mock.patch.object(s,'adapter_query',return_value=response):
            with self.assertRaises(r.Hold):self.backend().handle(self.probe)
    def test_challenge_replay(self):
        response=self.response();self.probe['challenge']='c'*32
        with mock.patch.object(s,'adapter_query',return_value=response):
            with self.assertRaises(r.Hold):self.backend().handle(self.probe)
    def test_source_change(self):
        self.request['source_commit']='a'*40
        with self.assertRaises(r.Hold):self.handle()
    def test_no_automatic_initialization(self):
        path=self.root+'/absent.sqlite3'
        with self.assertRaises(OSError):s.Reservations(path)
        self.assertFalse(os.path.exists(path))
    def test_existing_journal_not_overwritten(self):
        with self.assertRaises(r.Hold):s.Reservations.initialize(self.path)
    def test_non_journal_rejected(self):
        path=self.root+'/authority.sqlite3';self.write('authority.sqlite3',b'')
        with self.assertRaises((r.Hold,sqlite3.Error)):s.Reservations(path)
    def test_directory_fsync_failure_no_reply_and_restart_reconciles(self):
        with mock.patch.object(s.os,'fsync',side_effect=OSError('fsync')):
            with self.assertRaises(OSError):self.handle()
        # Durable SQLite may have committed: do not assume failure means absent.
        self.journal.close();self.journal=s.Reservations(self.path)
        self.addCleanup(self.journal.close);self.handle()
        self.assertEqual(self.journal.db.execute('SELECT count(*) FROM reservations').fetchone(),(1,))
    def test_conflict_never_calls_adapter(self):
        self.handle();self.request['new_grant_id']='different-grant'
        self.probe['request_sha256']=r.sha(r.canonical(self.request))
        with mock.patch.object(s,'adapter_query') as adapter:
            with self.assertRaises(r.Hold):self.backend().handle(self.probe)
            adapter.assert_not_called()
    def test_stale_sidecar_retained(self):
        self.journal.close()
        self.write('management-reservations.sqlite3-wal',b'UNRECONCILED')
        with self.assertRaises(r.Hold):s.Reservations(self.path)
        self.assertEqual(Path(self.path+'-wal').read_bytes(),b'UNRECONCILED')
    def test_adapter_real_isolated_execution(self):
        ref=self.write('ok.py',b'import json\nprint(json.dumps({"operation":P2_MANAGEMENT_REQUEST["probe"]["operation"]}))\n')
        self.assertEqual(s.adapter_query(ref,{'probe':self.probe}),{'operation':'recovery_apply'})
    def test_adapter_sha_refused(self):
        ref=dict(self.adapter);ref['sha256']='0'*64
        with self.assertRaises(r.Hold):s.adapter_query(ref,{})
    def test_adapter_failure_is_hold(self):
        with self.assertRaises(r.Hold):s.adapter_query(self.adapter,{})
    def test_adapter_output_bound(self):
        ref=self.write('large.py',b'print("x"*300000)\n')
        with self.assertRaises(r.Hold):s.adapter_query(ref,{})
    def test_adapter_timeout(self):
        ref=self.write('slow.py',b'import time\ntime.sleep(10)\n')
        with self.assertRaises(r.Hold):s.adapter_query(ref,{})

if __name__=='__main__':unittest.main(verbosity=2)
