"""Only the stopped, locked original queue may prove prestart no-new-op."""
from pathlib import Path
import sqlite3
import sys
import unittest

HERE=Path(__file__).parent.resolve()
sys.path.insert(0,str(HERE/'reused-6825'))
sys.path.insert(0,str(HERE/'new19-source'))
from pr17_c53_r2_host_backend_candidate import R2HostBackend
from pr17_c53_r2_authority_adapter import ExistingRequestAuthority

JOB='/opt/xuanjun-cloud-connection/l2-c53-recovery-once'

class Existing:
    def __init__(self):self.present=set()
    def absent(self,path):
        if path in self.present:raise FileExistsError(path)

class CanonicalTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE connection_jobs(request_id TEXT)')
        self.db.execute('CREATE TABLE connection_outbox(request_id TEXT)')
        self.backend=object.__new__(R2HostBackend)
        b=self.backend;b.db=self.db;b.lock_fd=7;b.worker_stopped=True
        b.verified_original_db=True
        b.tried_start=False;b.window_open=False;b.reserved=True
        b.job=JOB;b.legacy=Existing()
        b.expected_ids=tuple('fixed-%02d'%i for i in range(19))
        b.bundle={'requests':[{'request_id':rid} for rid in b.expected_ids]}
        self.auth=object.__new__(ExistingRequestAuthority)
        self.auth.canonical_snapshot_reader=b.canonical_prestart_no_new_operations

    def test_qualifying_protected_db_is_narrow_positive(self):
        self.assertTrue(self.backend.canonical_prestart_no_new_operations())
        self.assertFalse(self.auth.canonical_state_unknown(JOB))
        self.assertTrue(self.auth.prove_no_new_operations_canonically(JOB))
        self.assertTrue(self.auth.canonical_state_unknown('/wrong'))

    def test_marker_or_original_row_or_outbox_fails_closed(self):
        b=self.backend
        b.legacy.present.add(JOB+'/NEW_WORKER_START_ATTEMPT.json')
        self.assertFalse(b.canonical_prestart_no_new_operations())
        b.legacy.present.clear()
        self.db.execute('INSERT INTO connection_jobs VALUES (?)',(b.expected_ids[0],))
        self.assertFalse(b.canonical_prestart_no_new_operations())
        self.db.execute('DELETE FROM connection_jobs')
        self.db.execute('INSERT INTO connection_outbox VALUES (?)',(b.expected_ids[1],))
        self.assertTrue(self.auth.canonical_state_unknown(JOB))
        self.assertFalse(self.auth.prove_no_new_operations_canonically(JOB))

    def test_missing_lock_db_or_start_attempt_fails_closed(self):
        b=self.backend
        for key,value in (('lock_fd',None),('tried_start',True),('worker_stopped',False),
                          ('db',None),('verified_original_db',False)):
            previous=getattr(b,key);setattr(b,key,value)
            self.assertFalse(b.canonical_prestart_no_new_operations(),key)
            setattr(b,key,previous)

if __name__=='__main__':unittest.main()
