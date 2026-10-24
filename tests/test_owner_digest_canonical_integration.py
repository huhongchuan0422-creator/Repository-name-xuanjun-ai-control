import json
import os
import sqlite3
import tempfile
import unittest
from five_support import load_dependencies, package


class OwnerDigestCanonicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.digest=staticmethod(load_dependencies()['owner_action_digest'].build_digest)
        package()
        import owner_dashboard
        cls.snapshot=staticmethod(owner_dashboard.snapshot)
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=os.path.join(self.tmp.name,'canonical.sqlite')
        self.db=sqlite3.connect(self.path);self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE tasks(id TEXT PRIMARY KEY,state TEXT,fence INTEGER,updated REAL,checkpoint TEXT,depends TEXT,lease_owner TEXT,lease_until REAL)')
    def add(self,name,state='WAITING_HUMAN',updated=1,checkpoint=None):
        if checkpoint is None:checkpoint=dict(phase='REVIEW',sha='a'*40,reason='OWNER_APPROVAL',secret='DO_NOT_EXPORT')
        self.db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)',(name,state,4,updated,json.dumps(checkpoint),'[]','fixture',200));self.db.commit()
    def test_full_human_queue_survives_recent_window(self):
        for i in range(5):self.add('human'+str(i))
        for i in range(20):self.add('auto'+str(i),'DONE',100)
        snap=self.snapshot(self.path,now=100,limit=2)
        self.assertEqual(len(snap['tasks']),2)
        value=self.digest(snap,100,limit=2)
        self.assertEqual(value['unique_count'],5);self.assertEqual(value['omitted_count'],3)
        self.assertEqual(value['status'],'VIEW_READY');self.assertNotIn('DO_NOT_EXPORT',repr(value))
    def test_actual_empty_groupby_missing_zero_is_hold(self):
        self.add('auto','DONE')
        snap=self.snapshot(self.path,now=100)
        self.assertNotIn('WAITING_HUMAN',snap['counts'])
        self.assertEqual(self.digest(snap,100)['status'],'HOLD')
        # No normalization here: shared caller must supply authoritative zero.
    def test_restart_reopen_keeps_digest(self):
        self.add('human')
        first=self.digest(self.snapshot(self.path,now=100),100)
        self.db.close();self.db=sqlite3.connect(self.path);self.addCleanup(self.db.close)
        second=self.digest(self.snapshot(self.path,now=101),101)
        self.assertEqual(first['digest_sha256'],second['digest_sha256'])
    def test_producer_redaction_removes_invalid_commit(self):
        self.add('human',checkpoint=dict(phase='REVIEW',commit='SECRET',reason='OWNER_APPROVAL'))
        value=self.digest(self.snapshot(self.path,now=100),100)
        self.assertEqual(value['status'],'HOLD');self.assertNotIn('SECRET',repr(value))
    def test_reason_only_never_ready(self):
        self.add('human',checkpoint=dict(reason='OWNER_APPROVAL'))
        self.assertEqual(self.digest(self.snapshot(self.path,now=100),100)['status'],'HOLD')
    def test_read_only_database_unchanged(self):
        self.add('human');before='\n'.join(self.db.iterdump())
        self.digest(self.snapshot(self.path,now=100),100)
        self.assertEqual(before,'\n'.join(self.db.iterdump()))
    def test_stale_actual_snapshot_holds(self):
        self.add('human')
        self.assertEqual(self.digest(self.snapshot(self.path,now=100),401)['status'],'HOLD')
