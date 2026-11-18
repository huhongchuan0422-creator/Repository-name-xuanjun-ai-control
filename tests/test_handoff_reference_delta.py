"""Isolated host issuance tests; fake identities and backup are not production."""
import copy, json, unittest
import test_handoff_host_delta as host_fixtures
from task_center_handoff_host import REQUIRED_CONTEXT

class ReferenceDelta(unittest.TestCase):
    def setUp(self):
        self.fixture=host_fixtures.HostDelta();self.fixture.setUp()
        self.host=self.fixture.host;self.db=self.fixture.db;self.auth=self.fixture.auth
    def tearDown(self):self.fixture.tearDown()
    def issue(self,session='alice',parent=None):
        return self.host.issue_reference(session,'task-1','attempt-1',1,parent)
    def request(self,ref):
        return dict(ref,task_id='task-1',attempt_id='attempt-1',action='PROPOSE',causation='NONE',snapshot_digest='a'*64,backup_manifest_sha256='b'*64,checked=sorted(REQUIRED_CONTEXT),provider_ref='fixture-only')
    def test_issued_reference_records_and_preserves_request(self):
        ref=self.issue();v=self.request(ref);original=copy.deepcopy(v)
        self.assertEqual(self.host.record('alice',v)['state'],'RECORDED')
        self.assertEqual(v,original)
        self.assertEqual(self.host.read_receipt('bob','task-1','attempt-1',ref['event_id'])['handoff_id'],ref['handoff_id'])
    def test_unknown_and_cross_subject_rejected_without_echo_or_writes(self):
        ref=self.issue();base=self.request(ref)
        for field in ('handoff_id','event_id','backup_cycle_id','provider_ref'):
            request=copy.deepcopy(base);request[field]='examplevalue123';before=self.db.total_changes
            with self.assertRaises(ValueError) as error:self.host.record('alice',request)
            self.assertNotIn('examplevalue123',str(error.exception));self.assertEqual(self.db.total_changes,before)
        with self.assertRaises(ValueError):self.host.record('bob',base)
        with self.assertRaises(ValueError):self.host.issue_reference('alice','task-1','wrong-attempt',1)
        with self.assertRaises(ValueError):self.host.issue_reference('alice','task-1','attempt-1',1,'examplevalue123')
        other=copy.copy(self.host);other.tenant_id='other'
        with self.assertRaises(ValueError):other.issue_reference('alice','task-1','attempt-1',1,ref['event_id'])
        self.assertEqual(self.db.execute("SELECT count(*) FROM outbox").fetchone()[0],0)
    def test_registered_reference_cannot_cross_real_task(self):
        ref=self.issue()
        self.db.execute("INSERT INTO tasks SELECT 'task-2',attempt_id,authority_state,authority_valid_until,fence,epoch,resource_scope_json,resource_scope_digest,last_trusted_time FROM tasks WHERE task_id='task-1'")
        self.db.execute("INSERT INTO gateway_task_metadata VALUES('task-2','tenant-1','demo-project')")
        self.db.execute("INSERT INTO resource_claims SELECT 'task-2',resource_key,attempt_id,fence,epoch,state FROM resource_claims WHERE task_id='task-1'")
        self.db.commit()
        with self.assertRaises(ValueError):self.host.issue_reference('alice','task-2','attempt-1',1,ref['event_id'])
        request=self.request(ref);request['task_id']='task-2'
        with self.assertRaises(ValueError):self.host.record('alice',request)
        with self.assertRaises(ValueError):self.host.read_receipt('bob','task-2','attempt-1',ref['event_id'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],0)

    def test_blocked_alerts_only_after_registered_reference(self):
        ref=self.issue();value=self.request(ref)
        self.db.execute("INSERT INTO writer_operations VALUES('task-1','UNKNOWN')");self.db.commit()
        self.assertEqual(self.host.record('alice',value)['reason'],'UNKNOWN_EFFECTS_RECONCILIATION_REQUIRED')
        self.assertEqual(self.host.record('alice',value)['reason'],'UNKNOWN_EFFECTS_RECONCILIATION_REQUIRED')
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)
        self.assertEqual(self.host.read_receipt('alice','task-1','attempt-1',ref['event_id'])['alert_delivery'],'UNKNOWN')
        self.db.execute('DELETE FROM writer_operations');self.db.execute("UPDATE model_assignments SET role_version='wrong'");self.db.commit()
        self.assertEqual(self.host.record('alice',value)['reason'],'NOT_CONNECTED')
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],2)
        self.assertFalse(self.db.execute("SELECT 1 FROM events WHERE kind LIKE 'AUTHENTICATED_HANDOFF_%'").fetchone())

    def test_issue_http_requires_session_csrf_and_real_formal_provider(self):
        import io
        from types import SimpleNamespace
        from task_center_app import build_handler
        from task_center_handoff_host import FormalHandoffIdentityProvider
        class Sessions:
            tenant_id='tenant-1';COOKIE='session'
            def get(self,token):return 'alice' if token=='good' else None
            def verify_csrf(self,session,token):return token=='csrf'
        class Identity(FormalHandoffIdentityProvider):
            def is_formal_session(self,session):return session=='alice'
        handler=build_handler(self.fixture.path,b'0'*32,'tenant-1','viewer',identity_provider=Identity(),session_store=Sessions(),handoff_host=self.host)
        def post(cookie,csrf,body):
            h=handler.__new__(handler);h.command='POST';h.path='/api/admin/handoff-reference';h.server=SimpleNamespace(server_port=8765)
            raw=json.dumps(body).encode();h.headers={'Host':'localhost:8765','Cookie':'session='+cookie,'X-CSRF-Token':csrf,'Content-Length':str(len(raw))};h.rfile=io.BytesIO(raw);out=[]
            h._send=lambda status,data,kind,extra_headers=None:out.append((status,json.loads(data)));h.do_POST();return out[0]
        value={'task_id':'task-1','attempt_id':'attempt-1','handoff_version':1}
        self.assertEqual(post('bad','csrf',value)[0],401);self.assertEqual(post('good','bad',value)[0],403)
        status,ref=post('good','csrf',value);self.assertEqual(status,200)
        self.assertEqual(self.host.record('alice',self.request(ref))['state'],'RECORDED')
        value['parent_event_id']='examplevalue123';status,body=post('good','csrf',value)
        self.assertEqual(status,409);self.assertNotIn('examplevalue123',json.dumps(body))

    def test_old_unregistered_and_mismatched_history_not_read(self):
        ref=self.issue();request=self.request(ref)
        request['handoff_id']='examplevalue123'
        self.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',('task-1','attempt-1','handoff-host:'+ref['event_id'],'AUTHENTICATED_HANDOFF_PROPOSE',1000,'PHASE_EXECUTION','HOST_AUTHENTICATED',json.dumps(request)))
        self.db.commit()
        with self.assertRaises(ValueError) as error:self.host.read_receipt('bob','task-1','attempt-1',ref['event_id'])
        self.assertNotIn('examplevalue123',str(error.exception))
        with self.assertRaises(ValueError):self.host.read_receipt('bob','task-1','attempt-1','examplevalue123')
    def test_child_reference_bound_to_same_handoff_and_actor(self):
        first=self.issue();self.host.record('alice',self.request(first))
        child=self.issue('bob',first['event_id'])
        value=self.request(child);value.update(action='RECEIVE',causation=first['event_id'])
        self.assertEqual(self.host.record('bob',value)['state'],'RECORDED')
        self.assertEqual(child['handoff_id'],first['handoff_id'])
        with self.assertRaises(ValueError):self.host.issue_reference('alice','task-1','attempt-1',2,first['event_id'])

if __name__=='__main__':unittest.main()
