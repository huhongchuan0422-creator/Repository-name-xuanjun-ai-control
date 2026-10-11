import os
import sqlite3
import tempfile
import unittest
from owner_update_router import process


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.temp.name,'state.sqlite')
        self.request = 'a'*32
        with sqlite3.connect(self.db) as db:
            db.executescript('CREATE TABLE tasks(id TEXT PRIMARY KEY,state TEXT,fence INTEGER);CREATE TABLE approvals(task_id TEXT,decision TEXT);CREATE TABLE owner_callback_requests(request_id TEXT,task_id TEXT,fence INTEGER,owner_id TEXT,owner_chat TEXT,expires_at REAL,consumed INTEGER);')
            db.execute('INSERT INTO tasks VALUES(?,?,?)', ('task','WAITING_HUMAN',4))
            db.execute('INSERT INTO approvals VALUES(?,?)', ('task','PENDING'))
            db.execute('INSERT INTO owner_callback_requests VALUES(?,?,?,?,?,?,?)', (self.request,'task',4,'123','123',1000,0))
        self.update = {'update_id':17,'message':{'chat':{'id':123,'type':'private'},'from':{'id':123},'text':'/approve '+self.request}}
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def callback(self, event):
        self.calls.append(event)
        return {'accepted':True}

    def run_update(self):
        return process(self.db,self.update,'123','123',self.callback,now=100)

    def test_owner_approve_and_reject_exact_event(self):
        self.assertEqual(self.run_update()['status'],'ACCEPTED')
        self.assertEqual(self.calls[0]['task_id'],'task')
        self.assertEqual(self.calls[0]['fence'],4)
        self.update['message']['text']='/reject '+self.request
        self.assertEqual(self.run_update()['status'],'ACCEPTED')
        self.assertEqual(self.calls[-1]['decision'],'REJECT')

    def test_customer_and_forged_owner_remain_customer(self):
        self.update['message']['text']='normal customer question'
        self.assertEqual(self.run_update()['route'],'CUSTOMER')
        self.update['message']['text']='/approve '+self.request
        self.update['message']['from']['id']=999
        self.assertEqual(self.run_update()['route'],'CUSTOMER')
        self.assertEqual(self.calls,[])

    def test_owner_invalid_command_does_not_enter_customer(self):
        self.update['message']['text']='/approve expired extra'
        self.assertEqual(self.run_update(),{'route':'OWNER','status':'REJECTED','reason':'INVALID_COMMAND'})
        self.assertEqual(self.calls,[])

    def test_invalid_update_id_does_not_forward(self):
        self.update['update_id']=True
        self.assertEqual(self.run_update()['status'],'REJECTED')
        self.assertEqual(self.calls,[])

    def test_stale_fence_used_expired_wrong_bound_chat(self):
        for query in ["UPDATE tasks SET fence=5", "UPDATE owner_callback_requests SET consumed=1", "UPDATE owner_callback_requests SET expires_at=100", "UPDATE owner_callback_requests SET owner_chat='999'"]:
            with sqlite3.connect(self.db) as db:
                db.execute('UPDATE tasks SET fence=4')
                db.execute("UPDATE owner_callback_requests SET consumed=0,expires_at=1000,owner_chat='123'")
                db.execute(query)
            self.assertEqual(self.run_update()['status'],'REJECTED')
        self.assertEqual(self.calls,[])

    def test_callback_failure_requires_retry_not_customer(self):
        def fail(event):
            raise RuntimeError('sensitive exception')
        result=process(self.db,self.update,'123','123',fail,now=100)
        self.assertEqual(result,{'route':'OWNER','status':'RETRY','reason':'CALLBACK_UNCONFIRMED'})


if __name__=='__main__':
    unittest.main()
