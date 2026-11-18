"""Tampered historical rows are rejected without changing the isolated DB."""
import copy, hashlib, io, json, unittest
from types import SimpleNamespace
import test_handoff_reference_delta as fixture
from task_center_app import build_handler
from task_center_handoff_host import FormalHandoffIdentityProvider

class ReadSafetyDelta(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ReferenceDelta();self.f.setUp();self.db=self.f.db;self.host=self.f.host
        self.ref=self.f.issue();self.host.record('alice',self.f.request(self.ref))
        self.key='handoff-host:'+self.ref['event_id']
        self.raw=self.db.execute('SELECT payload_json FROM events WHERE event_id=?',(self.key,)).fetchone()[0]
    def tearDown(self):self.f.tearDown()
    def snapshot(self):return hashlib.sha256('\n'.join(self.db.iterdump()).encode()).hexdigest()
    def tamper(self,key,value):
        doc=json.loads(self.raw);doc[key]=value
        self.db.execute('UPDATE events SET payload_json=? WHERE event_id=?',(json.dumps(doc),self.key));self.db.commit()
    def test_reject_unsafe_checked_and_other_returned_fields_without_mutation(self):
        for field,value in [('checked',['examplevalue123']),('checked',['SOURCE','SOURCE']),('checked','SOURCE'),('backup_state','examplevalue123'),('backup_cycle_at','examplevalue123'),('action','examplevalue123'),('provider_ref','examplevalue123'),('backup_manifest_sha256','examplevalue123')]:
            self.tamper(field,value);before=self.snapshot()
            with self.assertRaises(ValueError) as error:self.host.read_receipt('bob','task-1','attempt-1',self.ref['event_id'])
            self.assertNotIn('examplevalue123',str(error.exception));self.assertEqual(before,self.snapshot())
        self.db.execute('UPDATE events SET payload_json=? WHERE event_id=?',(self.raw,self.key));self.db.commit()
        self.assertEqual(self.host.read_receipt('bob','task-1','attempt-1',self.ref['event_id'])['state'],'HISTORICAL_RECORDED')
    def test_history_payload_enums_cannot_leak(self):
        ref=self.f.issue();self.f.auth.backup={'state':'INCOMPLETE','missing':['RESTORE'],'cycle_at':990};self.host.record('alice',self.f.request(ref))
        row=self.db.execute("SELECT event_id,payload_json FROM events WHERE kind='SUPERVISION_ACTION'").fetchone();original=json.loads(row[1])
        for key,value in [('missing',['examplevalue123']),('missing',['RESTORE','RESTORE']),('state','examplevalue123'),('reason','examplevalue123')]:
            item=copy.deepcopy(original);item[key]=value
            self.db.execute('UPDATE events SET payload_json=? WHERE event_id=?',(json.dumps(item),row[0]));self.db.commit();before=self.snapshot()
            with self.assertRaises(ValueError) as error:self.host.read_receipt('bob','task-1','attempt-1',ref['event_id'])
            self.assertNotIn('examplevalue123',str(error.exception));self.assertEqual(before,self.snapshot())
    def test_protected_get_does_not_echo_unsafe_history(self):
        class Sessions:
            tenant_id='tenant-1';COOKIE='session'
            def get(self,token):return 'alice' if token=='good' else None
            def verify_csrf(self,session,token):return token=='good'
        class Identity(FormalHandoffIdentityProvider):
            def is_formal_session(self,session):return session=='alice'
        handler=build_handler(self.f.fixture.path,b'0'*32,'tenant-1','viewer',identity_provider=Identity(),session_store=Sessions(),handoff_host=self.host)
        def read(cookie):
            h=handler.__new__(handler);h.command='GET';h.path='/api/admin/handoff-event?task_id=task-1&attempt_id=attempt-1&event_id='+self.ref['event_id'];h.server=SimpleNamespace(server_port=8765);h.headers={'Host':'localhost:8765','Cookie':'session='+cookie};out=[]
            h._send=lambda status,data,kind,extra_headers=None:out.append((status,data));h.do_GET();return out[0]
        self.assertEqual(read('good')[0],200);self.assertEqual(read('bad')[0],401)
        self.tamper('checked',['examplevalue123']);before=self.snapshot();status,body=read('good')
        self.assertEqual(status,404);self.assertNotIn(b'examplevalue123',body);self.assertEqual(before,self.snapshot())

if __name__=='__main__':unittest.main()
