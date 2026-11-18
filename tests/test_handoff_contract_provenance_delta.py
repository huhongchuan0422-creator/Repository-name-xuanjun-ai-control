"""Contract downgrade negatives on isolated DB; never production data."""
import copy, hashlib, json, unittest
import test_handoff_role_integration_delta as fixture
from task_center_handoff_host import LEGACY_CONTEXT

class ContractProvenanceDelta(unittest.TestCase):
    def setUp(self):
        self.f=fixture.RoleHostDelta();self.f.setUp();self.host=self.f.host;self.db=self.f.db
        self.req=self.f.req('task-2','fixture-ui');self.f.auth.backup={'state':'INCOMPLETE','missing':['ARTIFACT'],'cycle_at':990};self.host.record('alice',self.req)
        self.f.auth.backup={'state':'COMPLETE','missing':[],'cycle_at':990};self.host.record('alice',self.req)
        self.key='handoff-host:'+self.req['event_id'];self.raw=self.db.execute('SELECT payload_json FROM events WHERE event_id=?',(self.key,)).fetchone()[0]
    def tearDown(self):self.f.tearDown()
    def dump(self):return hashlib.sha256('\n'.join(self.db.iterdump()).encode()).hexdigest()
    def test_remove_contract_or_artifact_cannot_downgrade(self):
        for removed in (('contract_id','contract_version','contract_sha256'),('contract_id',),('contract_version',),('contract_sha256',),()):
            doc=json.loads(self.raw)
            for k in removed:del doc[k]
            doc['checked']=sorted(LEGACY_CONTEXT)
            self.db.execute('UPDATE events SET payload_json=? WHERE event_id=?',(json.dumps(doc),self.key));self.db.commit();before=self.dump()
            with self.assertRaises(ValueError):self.host.read_receipt('bob','task-2','attempt-1',self.req['event_id'])
            self.assertEqual(before,self.dump())
        self.db.execute('UPDATE events SET payload_json=? WHERE event_id=?',(self.raw,self.key));self.db.commit()
        self.assertEqual(self.host.read_receipt('bob','task-2','attempt-1',self.req['event_id'])['state'],'HISTORICAL_RECORDED')
    def test_protected_route_rejects_missing_contract_without_mutation(self):
        from types import SimpleNamespace
        from task_center_app import build_handler
        from task_center_handoff_host import FormalHandoffIdentityProvider
        class Sessions:
            tenant_id='tenant-1';COOKIE='session'
            def get(self,token):return 'alice' if token == 'good' else None
            def verify_csrf(self,session,token):return token == 'good'
        class Identity(FormalHandoffIdentityProvider):
            def is_formal_session(self,session):return session=='alice'
        handler=build_handler(self.f.f.path,b'0'*32,'tenant-1','viewer',identity_provider=Identity(),session_store=Sessions(),handoff_host=self.host)
        def get():
            h=handler.__new__(handler);h.command='GET';h.path='/api/admin/handoff-event?task_id=task-2&attempt_id=attempt-1&event_id='+self.req['event_id'];h.server=SimpleNamespace(server_port=8765);h.headers={'Host':'localhost:8765','Cookie':'session='+'good'};out=[]
            h._send=lambda status,data,kind,extra_headers=None:out.append((status,data));h.do_GET();return out[0]
        self.assertEqual(get()[0],200)
        doc=json.loads(self.raw)
        for key in ('contract_id','contract_version','contract_sha256'):del doc[key]
        doc['checked']=sorted(LEGACY_CONTEXT)
        self.db.execute('UPDATE events SET payload_json=? WHERE event_id=?',(json.dumps(doc),self.key));self.db.commit();before=self.dump()
        status,body=get();self.assertEqual(status,404);self.assertNotIn(b'contract-',body);self.assertEqual(before,self.dump())

    def test_ambiguous_unmarked_history_is_held_without_mutation(self):
        self.db.execute('DELETE FROM events WHERE event_id=?',('handoff-contract:'+self.req['event_id'],))
        self.db.execute("DELETE FROM events WHERE kind='SUPERVISION_ACTION'")
        for downgrade in (False,True):
            doc=json.loads(self.raw)
            if downgrade:
                for k in ('contract_id','contract_version','contract_sha256'):del doc[k]
                doc['checked']=sorted(LEGACY_CONTEXT)
            self.db.execute('UPDATE events SET payload_json=? WHERE event_id=?',(json.dumps(doc),self.key));self.db.commit();before=self.dump()
            with self.assertRaisesRegex(ValueError,'HISTORICAL_RECONCILIATION_REQUIRED'):
                self.host.read_receipt('bob','task-2','attempt-1',self.req['event_id'])
            self.assertEqual(before,self.dump())

    def test_unmarked_history_with_independent_matching_contract_alert(self):
        self.db.execute('DELETE FROM events WHERE event_id=?',('handoff-contract:'+self.req['event_id'],));self.db.commit()
        self.assertEqual(self.host.read_receipt('bob','task-2','attempt-1',self.req['event_id'])['state'],'HISTORICAL_RECORDED')

    def test_existing_bound_alert_prevents_downgrade_without_new_marker(self):
        self.db.execute('DELETE FROM events WHERE event_id=?',('handoff-contract:'+self.req['event_id'],))
        doc=json.loads(self.raw)
        for k in ('contract_id','contract_version','contract_sha256'):del doc[k]
        doc['checked']=sorted(LEGACY_CONTEXT)
        self.db.execute('UPDATE events SET payload_json=? WHERE event_id=?',(json.dumps(doc),self.key));self.db.commit()
        with self.assertRaises(ValueError):self.host.read_receipt('bob','task-2','attempt-1',self.req['event_id'])

if __name__=='__main__':unittest.main()
