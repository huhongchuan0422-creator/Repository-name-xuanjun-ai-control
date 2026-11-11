"""Ordinary bounded-I/O fixtures, not original PathGuard/M99/live acceptance."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import capture_session as session
import catalogue_binding as c
import existing_fd_controller as f
import migration_transaction as original
from test_runtime_controller import OriginalJournalFixture,FixtureBackend,approved_records,sealed_drain
from test_sqlite_wal_vfs import fixture,restored_rows


class FixtureIO:
    """Map only synthetic names into one ordinary temp directory, no path races."""
    def __init__(self,root):self.root=root;self.writes=0;self.valid=True
    def mapped(self,path):return self.root/str(path).lstrip('/')
    def check(self):return self.valid
    def exists(self,path):return self.mapped(path).exists()
    def read(self,path,limit):
        raw=self.mapped(path).read_bytes()
        if len(raw)>limit:raise ValueError('fixture bound')
        return raw
    def mkdir(self,path,**kwargs):self.writes+=1;self.mapped(path).mkdir(**kwargs)
    def write(self,path,raw,mode):
        self.writes+=1
        fd=os.open(self.mapped(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
        try:os.write(fd,raw);os.fsync(fd)
        finally:os.close(fd)
    def create_fd(self,path,mode):
        self.writes+=1
        return os.open(self.mapped(path),os.O_RDWR|os.O_CREAT|os.O_EXCL,mode)
    def sync(self,path):
        fd=os.open(self.mapped(path),os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)


class CaptureFixture(OriginalJournalFixture):
    def setUp(self):
        super().setUp()
        self.files=tempfile.TemporaryDirectory();self.fs=Path(self.files.name)
        self.io=FixtureIO(self.fs);main,wal,schema=fixture(17)
        self.dbpath=Path(self.cat['objects'][0]['path'])
        p=self.io.mapped(self.dbpath);p.parent.mkdir(parents=True);p.write_bytes(main)
        p.with_name(p.name+'-wal').write_bytes(wal)
        side=copy.deepcopy(self.cat['objects'][0]);side.update(id='wal',path=str(self.dbpath)+'-wal',inode=3)
        self.cat['objects'].append(side);self.cat['origins'][0]['objects'].append('wal')
        for record in self.cat['configurations'].values():record['data_objects'].append('wal')
        settings=copy.deepcopy(self.cat['objects'][0]);settings.update(id='settings',path='/opt/trading-system/runtime/settings.fixture',inode=4)
        self.cat['objects'].append(settings);self.cat['origins'][0]['objects'].append('settings')
        for record in self.cat['configurations'].values():record['data_objects'].append('settings')
        file=self.io.mapped(settings['path']);file.parent.mkdir(parents=True);file.write_bytes(b'ordinary-fixture-state')
        self.inventory=c.digest(self.cat)
        self.config={'schema':1,'writer_inventory_sha256':self.inventory,'epoch':7,'wal_sources':session.wal_source_manifest(),
          'jobs':[{'id':'database','kind':'SQLITE','source_id':'main','destination':'/var/lib/pr99-test-only/output','schema_sha256':schema,'wal_id':'wal','shm_id':None},
                  {'id':'settings','kind':'FILE','source_id':'settings','destination':'/var/lib/pr99-test-only/settings','schema_sha256':None,'wal_id':None,'shm_id':None}]}
        self.io.mapped('/var/lib/pr99-test-only').mkdir(parents=True)
        # Build a NEW ordinary fixture. No production claim or permit is touched.
        self.journal.close();os.close(self.txn_fd)
        for path in self.journal.path.iterdir():path.unlink()
        self.journal.path.rmdir()
        self.plan['bindings']['writer_inventory']=self.inventory
        self.plan['bindings']['final_manifest_contract']=c.digest(self.config)
        self.plan_digest=original.digest(self.plan)
        self.journal=original.Journal(self.root,'fixture-original');self.journal.claim(self.plan,self.plan_digest)
        self.txn_fd=os.open(self.journal.path,os.O_RDONLY|os.O_DIRECTORY)
        self.binding.update(plan_digest=self.plan_digest,writer_inventory_sha256=self.inventory,
            transaction_identity=[os.fstat(self.txn_fd).st_dev,os.fstat(self.txn_fd).st_ino],
            lock_identity=[os.fstat(self.journal.lock.fileno()).st_dev,os.fstat(self.journal.lock.fileno()).st_ino],
            extension_manifest_sha256=original.digest(f.extension_manifest()))
        self.controller=self.make_controller();self.req=original.request(self.plan,'inspect_protected',self.plan_digest)
        with patch.object(original,'source_manifest',return_value=self.plan['source_hashes']):first=self.controller.perform(self.req,self.dispatch,self.query)
        self.fence_req=original.request(self.plan,'fence_source',original.digest(first))
        self.proof_fd=os.open(self.root/'fence-evidence',os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
        self.capture_fd=os.open(self.root/'capture-evidence',os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
        self.backend=FixtureBackend();self.pending=0
        self.session=self.build()

    def build(self,config=None):
        with patch.object(session,'LinuxFenceBackend',return_value=self.backend):
            return session.CaptureSession(self.controller,self.cat,approved_records(self.cat),self.io,{},lambda:True,
                lambda inv,e:sealed_drain(self.controller,['portal'],self.pending),
                self.proof_fd,lambda:True,self.capture_fd,lambda:True,self.config if config is None else config)

    def tearDown(self):
        os.close(self.proof_fd);os.close(self.capture_fd);self.files.cleanup();super().tearDown()

    def fence(self):
        with patch.object(original,'source_manifest',return_value=self.plan['source_hashes']):
            proof=self.session.perform(self.fence_req)
        self.snapshot_req=original.request(self.plan,'final_snapshot',original.digest(proof))
        return proof

    def capture(self):
        with patch.object(original,'source_manifest',return_value=self.plan['source_hashes']):
            return self.session.perform(self.snapshot_req)


class SessionTests(CaptureFixture,unittest.TestCase):
    def test_original_journal_drain_fence_nonempty_wal_and_receipt_chain(self):
        self.fence();result=self.capture()
        self.assertEqual(result['status'],'SUCCEEDED')
        output=self.io.read('/var/lib/pr99-test-only/output/final.db',67108864)
        self.assertEqual(len(restored_rows(output)),17)
        saved=json.loads(os.pread(self.capture_fd,16385,0))
        self.assertTrue(saved['results']['database']['source_wal_captured'])
        self.assertEqual(self.io.read('/var/lib/pr99-test-only/settings',100),b'ordinary-fixture-state')
        self.assertEqual(saved['results']['settings']['class'],'FINAL_FENCED_FILE_CANDIDATE')
        self.assertEqual(self.controller.load()[1][-1]['receipt'],result)

    def test_pending_drain_writes_no_source_or_capture(self):
        self.pending=1
        with self.assertRaises(f.ControllerHold):self.fence()
        self.assertEqual(self.backend.calls,[]);self.assertEqual(self.io.writes,0)

    def test_snapshot_before_fence_has_no_effect(self):
        self.snapshot_req=original.request(self.plan,'final_snapshot',self.plan_digest)
        with self.assertRaises(f.ControllerHold):self.capture()
        self.assertEqual(self.io.writes,0)

    def test_partial_capture_does_not_recover_or_write_again(self):
        self.fence()
        with patch.object(session.wal,'snapshot_sqlite_with_original_io',side_effect=TimeoutError()) as recover:
            with self.assertRaises(f.ControllerHold):self.capture()
        count=self.io.writes
        with patch.object(session.wal,'snapshot_sqlite_with_original_io',side_effect=AssertionError('REPLAY')):
            with self.assertRaises(f.ControllerHold):self.capture()
        self.assertEqual(self.io.writes,count);self.assertEqual(recover.call_count,1)

    def test_durable_outputs_query_after_unrecorded_result_does_not_repeat_capture(self):
        self.fence()
        self.controller._append({'type':'INTENT','request':self.snapshot_req})
        direct=self.session._snapshot(self.snapshot_req)
        count=self.io.writes;calls=list(self.backend.calls)
        with patch.object(session.wal,'snapshot_sqlite_with_original_io',side_effect=AssertionError('REPLAY')):
            result=self.capture()
        self.assertEqual(result,direct);self.assertEqual(self.io.writes,count);self.assertEqual(self.backend.calls,calls)

    def test_output_tamper_during_pending_query_holds(self):
        self.fence();self.controller._append({'type':'INTENT','request':self.snapshot_req})
        self.session._snapshot(self.snapshot_req)
        out=self.io.mapped('/var/lib/pr99-test-only/output/final.db');out.chmod(0o600);out.write_bytes(b'partial')
        with self.assertRaises(f.ControllerHold):self.capture()

    def test_missing_guard_has_no_pathname_fallback(self):
        self.session.io=None
        with self.assertRaises(session.SessionHold):self.session.perform(self.fence_req)
        self.assertEqual(self.backend.calls,[])

    def test_mutated_capture_input_contract_rejected_before_effect(self):
        self.session.config['jobs'][0]['destination']='/tmp/wrong'
        with self.assertRaises(session.SessionHold):self.session.perform(self.fence_req)
        self.assertEqual(self.backend.calls,[])

    def test_changed_accepted_wal_code_rejected(self):
        with patch.object(session,'wal_source_manifest',return_value={}):
            with self.assertRaises(session.SessionHold):self.session.perform(self.fence_req)
        self.assertEqual(self.backend.calls,[])

    def test_revoked_dispatch_grant_prevents_snapshot(self):
        self.fence();self.allowed=False
        with self.assertRaises(f.ControllerHold):self.capture()
        self.assertEqual(self.io.writes,0)

    def test_unrelated_install_stage_not_exposed(self):
        with self.assertRaises(session.SessionHold):self.session.perform(original.request(self.plan,'start_owned',self.plan_digest))
        self.assertEqual(self.backend.calls,[])
