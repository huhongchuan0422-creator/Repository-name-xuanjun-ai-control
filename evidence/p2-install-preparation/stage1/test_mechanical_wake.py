import json
import os
import sqlite3
import tempfile
import unittest

from mechanical_wake import MechanicalWakeController
import owner_dashboard


class Adapter(object):
    def __init__(self):
        self.calls = []
        self.writer = {'state': 'RUNNING', 'same_attempt': True,
                       'fence_stale': False}
    def recover_intake(self, context):
        self.calls.append(('intake', context)); return {'state': 'RECEIVED'}
    def inspect_writer(self, context):
        self.calls.append(('inspect', context)); return dict(self.writer)
    def resume_original(self, context):
        self.calls.append(('resume', context)); return {'state': 'RESUME_REQUESTED'}
    def controlled_recovery(self, context):
        self.calls.append(('recover', context)); return {'state': 'RECOVERY_STARTED'}


class WakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = os.path.join(self.temp.name, 'ledger.sqlite')
        db = sqlite3.connect(self.path)
        db.executescript("""
          CREATE TABLE tasks(id TEXT PRIMARY KEY,state TEXT,fence INTEGER,
            lease_owner TEXT,lease_until REAL,checkpoint TEXT,updated REAL);
          CREATE TABLE supervised_runs(task_id TEXT PRIMARY KEY,spec_hash TEXT,
            executor TEXT,run_id TEXT,session_id TEXT,workdir TEXT,artifact TEXT,
            dispatched_at REAL,start_deadline REAL,progress_deadline REAL,
            result_deadline REAL,native_state TEXT,accepted_at REAL,started_at REAL,
            last_progress REAL,terminal_receipt TEXT,effects TEXT,budget_key TEXT,
            budget_spent INTEGER,writer_fence INTEGER,writer_epoch INTEGER,
            start_receipt TEXT,resume_generation INTEGER,resume_base_fence INTEGER,
            status TEXT,checkpoint TEXT,checkpoint_version INTEGER,
            checkpoint_hash TEXT);
        """)
        db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?)",
                   ('T','RUNNING',3,'worker',9999,json.dumps({'phase':'P'}),0))
        db.execute("INSERT INTO supervised_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          ('T','s','e','attempt-1','session-1','w','a',0,300,900,1800,
           'DISPATCHED',None,None,None,None,'NONE','b',0,None,None,None,0,None,
           'DISPATCHED',json.dumps({'phase':'P'}),0,'h'))
        db.commit(); db.close()
        self.now = [0.0]; self.adapter = Adapter()
        self.value = MechanicalWakeController(self.path, lambda:self.now[0], self.adapter)

    def test_five_minute_intake_recovery_is_idempotent(self):
        self.now[0] = 300
        self.assertEqual(self.value.evaluate('T')['state'], 'RECEIVED')
        self.assertEqual(self.value.evaluate('T')['state'], 'HEALTHY_OR_NOT_DUE')
        self.assertEqual([c[0] for c in self.adapter.calls], ['intake'])
        state = owner_dashboard.snapshot(self.path, now=300)
        self.assertEqual(state['wake_timeline'][0]['threshold_seconds'], 300)
        self.assertEqual(state['wake_timeline'][0]['result'], {'state':'RECEIVED'})

    def test_fifteen_minute_resumes_only_same_live_writer(self):
        db=sqlite3.connect(self.path);db.execute(
          "UPDATE supervised_runs SET accepted_at=10,started_at=10,last_progress=10")
        db.commit();db.close();self.now[0]=910
        result=self.value.evaluate('T')
        self.assertEqual(result['state'],'RESUME_REQUESTED')
        self.assertEqual([c[0] for c in self.adapter.calls],['inspect','resume'])

    def test_thirty_minute_takeover_requires_stopped_and_stale_fence(self):
        db=sqlite3.connect(self.path);db.execute(
          "UPDATE supervised_runs SET accepted_at=10,started_at=10,last_progress=10")
        db.commit();db.close();self.now[0]=1810
        self.adapter.writer={'state':'STOPPED','same_attempt':True,'fence_stale':True}
        self.assertEqual(self.value.evaluate('T')['state'],'RECOVERY_STARTED')
        self.assertEqual([c[0] for c in self.adapter.calls],['inspect','recover'])

    def test_thirty_minute_live_writer_holds_without_takeover(self):
        db=sqlite3.connect(self.path);db.execute(
          "UPDATE supervised_runs SET accepted_at=10,started_at=10,last_progress=10")
        db.commit();db.close();self.now[0]=1810
        result=self.value.evaluate('T')
        self.assertEqual(result['state'],'HOLD_WRITER_OR_FENCE_NOT_PROVEN')
        self.assertEqual([c[0] for c in self.adapter.calls],['inspect'])


if __name__ == '__main__': unittest.main()
