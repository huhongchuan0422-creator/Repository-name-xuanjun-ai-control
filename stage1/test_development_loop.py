import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import Future

from development_loop import DevelopmentLoop
from execution_ledger import ExecutionLedger


SCHEMA = '''CREATE TABLE tasks(id TEXT PRIMARY KEY,kind TEXT,state TEXT,depends TEXT,lease_owner TEXT,lease_until REAL,fence INTEGER,checkpoint TEXT,updated REAL);
CREATE TABLE approvals(task_id TEXT PRIMARY KEY,decision TEXT,requested_at REAL,decided_at REAL);
CREATE TABLE events(id INTEGER PRIMARY KEY,task_id TEXT,event TEXT,created REAL,details TEXT);'''


class InlineExecutor:
    def submit(self, fn, claim):
        result=Future()
        try:result.set_result(fn(claim))
        except Exception as exc:result.set_exception(exc)
        return result
    def shutdown(self, wait=False):
        pass


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=os.path.join(self.temp.name,'state.sqlite')
        self.now=100
        with sqlite3.connect(self.db) as db:
            db.executescript(SCHEMA)
            for ident,deps in [('one','[]'),('two','["one"]'),('human','[]')]:
                state='WAITING_HUMAN' if ident=='human' else 'PENDING'
                db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',(ident,'CODEX_EXEC',state,deps,None,None,1,'{}',100))
        self.ledger=ExecutionLedger(self.db,['owner/repo'],clock=lambda:self.now)
        for ident in ('one','two','human'):
            self.ledger.register_spec(ident,{'repo':'owner/repo','type':'CODEX_EXEC','prompt':'approved test task','heavy':True,'timeout_seconds':60,'base_sha':'a'*40},'owner',True)
        self.calls=[]

    def tearDown(self):
        self.temp.cleanup()

    def state(self, ident):
        with sqlite3.connect(self.db) as db:
            return db.execute('SELECT state FROM tasks WHERE id=?',(ident,)).fetchone()[0]

    def test_complete_and_automatically_dispatch_next_dependency(self):
        outer=self
        class Pipeline:
            def run(self, claim):
                outer.calls.append(claim['task_id'])
                outer.ledger.finish(claim['task_id'],claim['worker_id'],claim['fence'],'DONE',effects='known')
                return {'state':'DONE','production_pass':False}
        loop=DevelopmentLoop(self.ledger,lambda _:Pipeline(),'test',max_workers=1,executor=InlineExecutor())
        self.assertEqual(loop.tick()['dispatched'],1)
        self.assertEqual(self.calls,['one'])
        self.assertEqual(loop.tick()['dispatched'],1)
        self.assertEqual(self.calls,['one','two'])
        loop.tick()
        self.assertEqual(self.state('human'),'WAITING_HUMAN')
        self.assertEqual(loop.tick()['active'],0)
        loop.close()

    def test_ci_wait_continues_same_lease_and_checkpoint(self):
        outer=self
        class Pipeline:
            def run(self, claim):
                outer.calls.append(claim)
                if len(outer.calls)==1:
                    cp={'phase':'CI_WAIT'}
                    outer.ledger.checkpoint(claim['task_id'],claim['worker_id'],claim['fence'],cp)
                    return {'state':'RUNNING','checkpoint':cp}
                outer.ledger.finish(claim['task_id'],claim['worker_id'],claim['fence'],'DONE',effects='known')
                return {'state':'DONE'}
        loop=DevelopmentLoop(self.ledger,lambda _:Pipeline(),'test',max_workers=1,clock=lambda:self.now,executor=InlineExecutor())
        loop.tick();loop.tick()
        self.assertEqual(len(self.calls),1)
        self.now+=6;loop.tick()
        self.assertEqual(self.calls[0]['fence'],self.calls[1]['fence'])
        self.assertEqual(self.calls[1]['checkpoint'],{'phase':'CI_WAIT'})
        loop.close()

    def test_exception_quarantines_one_task_and_independent_work_continues(self):
        class Pipeline:
            def run(self, claim):
                raise RuntimeError('sensitive exception must not persist')
        loop=DevelopmentLoop(self.ledger,lambda _:Pipeline(),'test',max_workers=1,executor=InlineExecutor())
        loop.tick();loop.tick()
        self.assertEqual(self.state('one'),'WAITING_HUMAN')
        self.assertEqual(self.state('two'),'PENDING')
        loop.close()


if __name__=='__main__':unittest.main()
