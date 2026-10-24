"""Locked original-schema observation, with no cloud or server side effects."""
import hashlib
import json
import sqlite3
import sys
import tempfile
import os
import unittest
from unittest import mock
from pathlib import Path

HERE=Path(__file__).parent.resolve()
sys.path[:0]=[str(HERE/'reused-6825'),str(HERE/'new19-source')]
from pr17_c53_r2_host_backend_candidate import R2HostBackend
from pr17_c53_r2_authority_adapter import ExistingRequestAuthority
from pr17_b5_deployment_composition import OriginalComposition
from production.cloud_connection.queue import canonical, Queue
from production.cloud_connection.fixed_actions import ApprovedObjectsPolicy
import pr17_c53_r2_review_transaction as c53

class Protected:
    def __init__(self, items):
        self.items=items;self.expected_db=None;self.identity_calls=0
    def read(self,path):return self.items[path],(1,2)
    def database_identity(self,st):
        self.identity_calls+=1
        if self.expected_db is None or (st.st_dev,st.st_ino)!=self.expected_db:
            raise RuntimeError('ORIGINAL_DB_PIN_MISMATCH')

class ReaderTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=str(Path(temp.name)/'queue.sqlite')
        self.writer=Queue(self.path,'b'*64,[332398908]);self.addCleanup(self.writer.close)
        self.db=self.writer.db
        os.chmod(self.path,0o600)
        catalog={'schema':1,'project':'other-project','approval_ref':'fixture-only',
                 'source_commit':'a'*40,'executor_sha256':'b'*64,'target':'uk',
                 'valid_from':1,'valid_until':1000,'recipients':['fixture-recipient'],
                 'objects':[{'ref':'old-object','root_ref':'old-root','relative_path':'file.bin',
                             'bytes':1,'sha256':hashlib.sha256(b'x').hexdigest()}]}
        policy={'project':'other-project','max_objects':1,'max_object_bytes':1,
                'max_total_bytes':1,'recipients':['fixture-recipient'],'root_refs':['old-root']}
        binding={'schema':1,'catalog':catalog,'catalog_sha256':hashlib.sha256(canonical(catalog).encode()).hexdigest(),
                 'policy':policy,'roots':{'old-root':['/tmp/fixture-old-root',1002]},
                 'recipient_id':'fixture-recipient','requests':{'old-object':'old-request'},
                 'execution_user':'fixture','execution_uid':1002,'reader_sha256':'c'*64}
        raw=canonical(binding).encode();pin=hashlib.sha256(raw).hexdigest()
        self.policy=ApprovedObjectsPolicy(raw,pin)
        self.hook=c53.binder.BIND
        cfg=canonical({'approved_objects':{'metadata_ref':self.hook,'metadata_sha256':pin}}).encode()
        self.backend=object.__new__(R2HostBackend)
        b=self.backend;b.db=self.db;b.lock_fd=7;b.worker_stopped=True;b.verified_original_db=True
        b.expected_ids=tuple('new-%02d'%i for i in range(19))
        b.spec={'source':{'target_code_pin':'b'*64}}
        b.legacy=Protected({c53.CONFIGS[0]:cfg,self.hook:raw})
        st=os.stat(self.path);b.legacy.expected_db=(st.st_dev,st.st_ino)
        b.frozen_baselines={c53.CONFIGS[0]:cfg}
        self.old={'schema':1,'request_id':'old-request','project':'other-project',
                  'target':'uk','operation':'fetch_approved_object','executor_sha256':'b'*64,
                  'arguments':{'manifest_sha256':binding['catalog_sha256'],'object_ref':'old-object',
                               'recipient_id':'fixture-recipient'},'expires_unix':50}

    def insert(self,request,state='READY',digest=None,raw=None):
        raw=canonical(request) if raw is None else raw
        self.db.execute('INSERT INTO connection_jobs VALUES(?,?,?,?,?,?,NULL,NULL)',
                        (request['request_id'],request['project'],raw,digest or hashlib.sha256(raw.encode()).hexdigest(),332398908,state))

    def observe(self):
        return self.backend.observe_cross_project_old_policy_dependency(self.backend.expected_ids,c53.PROJ)

    def precheck(self):
        return self.backend.observe_prestart_old_policy_dependency(
            self.backend.expected_ids,c53.PROJ,self.path)

    def test_active_old_fetch_and_terminal_history(self):
        self.insert(self.old)
        with self.assertRaisesRegex(Exception,'OLD_POLICY_LOCKED_DEPENDENCY'):
            self.observe()
        self.db.execute("UPDATE connection_jobs SET state='SUCCESS'")
        self.assertEqual(self.observe()['dependent_active'],0)

    def test_precheck_and_later_locked_change(self):
        completed=dict(self.old,request_id='completed-old')
        self.insert(completed,'SUCCESS')
        self.backend.lock_fd=None;self.backend.worker_stopped=False
        self.assertEqual(self.precheck()['phase'],'PRECHECK_OBSERVATION')
        self.assertGreaterEqual(self.backend.legacy.identity_calls,3)
        self.insert(self.old,'DISPATCHING')
        with self.assertRaisesRegex(Exception,'OLD_POLICY_PRECHECK_DEPENDENCY'):
            self.precheck()
        self.backend.lock_fd=7;self.backend.worker_stopped=True
        with self.assertRaisesRegex(Exception,'OLD_POLICY_LOCKED_DEPENDENCY'):
            self.observe()

    def test_missing_database_does_not_create(self):
        self.backend.lock_fd=None;self.backend.worker_stopped=False
        missing=self.path+'.missing'
        with self.assertRaises(Exception):
            self.backend.observe_prestart_old_policy_dependency(
                self.backend.expected_ids,c53.PROJ,missing)
        self.assertFalse(os.path.lexists(missing))

    def test_wal_without_sidecars_holds_before_ro_connect(self):
        self.db.execute('PRAGMA journal_mode=WAL')
        self.writer.close()
        self.backend.lock_fd=None;self.backend.worker_stopped=False
        self.assertFalse(os.path.lexists(self.path+'-wal'))
        with self.assertRaisesRegex(Exception,'OLD_POLICY_PRECHECK_WAL_READER_MARK_UNKNOWN'):
            self.precheck()
        self.assertFalse(os.path.lexists(self.path+'-wal'))
        self.assertFalse(os.path.lexists(self.path+'-shm'))

    def test_live_wal_holds_without_shm_read_mark(self):
        self.db.execute('PRAGMA journal_mode=WAL')
        self.insert(dict(self.old,request_id='terminal'),'SUCCESS')
        paths=[self.path,self.path+'-wal',self.path+'-shm']
        self.assertTrue(all(os.path.isfile(p) for p in paths))
        before={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
        self.backend.lock_fd=None;self.backend.worker_stopped=False
        with self.assertRaisesRegex(Exception,'OLD_POLICY_PRECHECK_WAL_READER_MARK_UNKNOWN'):
            self.precheck()
        self.assertEqual(before,{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths})

    def test_wrong_original_db_pin_rejected_before_read(self):
        self.backend.legacy.expected_db=(0,0)
        self.backend.lock_fd=None;self.backend.worker_stopped=False
        with self.assertRaisesRegex(Exception,'ORIGINAL_DB_PIN_MISMATCH'):
            self.precheck()

    def test_same_path_replaced_db_rejected(self):
        self.writer.close()
        os.rename(self.path,self.path+'.retained')
        replacement=Queue(self.path,'b'*64,[332398908]);self.addCleanup(replacement.close)
        os.chmod(self.path,0o600)
        self.backend.lock_fd=None;self.backend.worker_stopped=False
        with self.assertRaisesRegex(Exception,'ORIGINAL_DB_PIN_MISMATCH'):
            self.precheck()

    def test_identity_check_exception_holds(self):
        self.backend.legacy.database_identity=lambda st: (_ for _ in ()).throw(
            RuntimeError('ORIGINAL_DB_IDENTITY_UNAVAILABLE'))
        self.backend.lock_fd=None;self.backend.worker_stopped=False
        with self.assertRaisesRegex(Exception,'ORIGINAL_DB_IDENTITY_UNAVAILABLE'):
            self.precheck()

    def test_oversized_body_rejected_by_aggregate_before_classification(self):
        raw='x'*20227
        self.insert(self.old,raw=raw)
        self.backend.lock_fd=None;self.backend.worker_stopped=False
        with self.assertRaisesRegex(Exception,'OLD_POLICY_SCAN_BUDGET_UNKNOWN'):
            self.precheck()

    def test_absolute_scan_deadline_rejects_progress(self):
        self.insert(dict(self.old,request_id='terminal'),'SUCCESS')
        self.backend.lock_fd=None;self.backend.worker_stopped=False
        with mock.patch('pr17_c53_r2_host_backend_candidate.time.monotonic',
                        side_effect=[0,6,6,6,6,6]):
            with self.assertRaisesRegex(Exception,'OLD_POLICY_SCAN_DEADLINE_UNKNOWN'):
                self.precheck()

    def test_live_unknown_fetch_or_bad_hash_holds(self):
        unknown=dict(self.old,request_id='not-in-old-binding')
        self.insert(unknown,'UNKNOWN')
        self.backend.lock_fd=None;self.backend.worker_stopped=False
        with self.assertRaisesRegex(Exception,'OLD_POLICY_FETCH_BINDING_UNKNOWN'):
            self.precheck()
        self.db.execute("UPDATE connection_jobs SET state='SUCCESS' WHERE request_id=?",
                        (unknown['request_id'],))
        self.insert(self.old,'READY',digest='0'*64)
        with self.assertRaisesRegex(Exception,'OLD_POLICY_REQUEST_HASH_UNKNOWN'):
            self.precheck()

    def test_bounded_complete_scan_never_reports_partial_zero(self):
        self.backend.lock_fd=None;self.backend.worker_stopped=False
        request=dict(self.old,operation='probe',arguments={})
        rows=[]
        for i in range(10001):
            item=dict(request,request_id='probe-%05d'%i)
            raw=canonical(item)
            rows.append((item['request_id'],item['project'],raw,
                         hashlib.sha256(raw.encode()).hexdigest(),332398908,'READY'))
        self.db.executemany('INSERT INTO connection_jobs '
            '(request_id,project,request_json,request_sha,actor_id,state) VALUES (?,?,?,?,?,?)',rows)
        with self.assertRaisesRegex(Exception,'OLD_POLICY_SCAN_BUDGET_UNKNOWN'):
            self.precheck()

    def test_actual_authority_preflight_calls_a_not_just_callable(self):
        self.backend.lock_fd=None;self.backend.worker_stopped=False
        authority=object.__new__(ExistingRequestAuthority)
        original=object.__new__(OriginalComposition)
        original.test_only=False
        authority.original=original
        authority.request_ids=self.backend.expected_ids
        authority.precheck_old_policy_reader=lambda ids,project:self.precheck()
        authority.receiver_conflict_reader=lambda *args: (_ for _ in ()).throw(
            AssertionError('receiver must not be reached after A failure'))
        self.insert(self.old,'UNKNOWN')
        with mock.patch.object(ExistingRequestAuthority,'_bound_original',return_value=original), \
             mock.patch.object(OriginalComposition,'preflight',return_value=True):
            with self.assertRaisesRegex(Exception,'OLD_POLICY_PRECHECK_DEPENDENCY'):
                authority.preflight_original_capabilities()

    def test_unknown_fetch_and_bad_digest_hold(self):
        request=dict(self.old,request_id='unknown')
        self.insert(request,'UNKNOWN')
        with self.assertRaisesRegex(Exception,'OLD_POLICY_FETCH_BINDING_UNKNOWN'):self.observe()
        self.db.execute('DROP TRIGGER connection_no_delete')
        self.db.execute('DELETE FROM connection_jobs')
        self.insert(self.old,digest='0'*64)
        with self.assertRaisesRegex(Exception,'OLD_POLICY_REQUEST_HASH_UNKNOWN'):self.observe()

    def test_other_fixed_operation_and_lock_change(self):
        probe=dict(self.old,request_id='probe-one',operation='probe',arguments={})
        self.insert(probe)
        self.assertEqual(self.observe()['dependent_active'],0)
        self.backend.lock_fd=None
        with self.assertRaisesRegex(Exception,'OLD_POLICY_LOCK_OR_DB_UNKNOWN'):self.observe()

    def test_source_change_and_incomplete_rows_hold(self):
        self.backend.legacy.items[self.hook]=b'changed'
        with self.assertRaisesRegex(Exception,'OLD_POLICY_SOURCE_CHANGED'):self.observe()
        self.backend.legacy.items[self.hook]=canonical(self.policy.binding).encode()
        self.insert(self.old)
        self.db.execute('DROP TRIGGER connection_no_rebind')
        self.db.execute("UPDATE connection_jobs SET request_json='{}'")
        with self.assertRaisesRegex(Exception,'OLD_POLICY_REQUEST_HASH_UNKNOWN'):self.observe()

    def test_change_during_locked_observation_never_returns_zero(self):
        base=self.backend.legacy
        db=self.db
        request=dict(self.old)
        class ChangingProtected:
            def __init__(self):self.reads=0
            def read(self,path):
                if path==c53.CONFIGS[0]:
                    self.reads+=1
                    if self.reads==2:
                        raw=canonical(request)
                        db.execute('INSERT INTO connection_jobs VALUES(?,?,?,?,?,?,NULL,NULL)',
                            (request['request_id'],request['project'],raw,
                             hashlib.sha256(raw.encode()).hexdigest(),332398908,'UNKNOWN'))
                return base.read(path)
        self.backend.legacy=ChangingProtected()
        with self.assertRaisesRegex(Exception,'OLD_POLICY_QUEUE_CHANGED'):self.observe()

if __name__=='__main__':unittest.main()
