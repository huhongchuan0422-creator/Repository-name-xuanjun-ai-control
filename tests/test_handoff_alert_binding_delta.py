"""Isolated adversarial history, never production data."""
import copy, hashlib, json, unittest
import test_handoff_reference_delta as fixture

class AlertBindingDelta(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ReferenceDelta();self.f.setUp();self.host=self.f.host;self.db=self.f.db
        self.ref=self.f.issue();self.request=self.f.request(self.ref)
        self.f.auth.backup={'state':'INCOMPLETE','missing':['RESTORE'],'cycle_at':990}
        self.host.record('alice',self.request)
        self.row=self.db.execute("SELECT event_id,payload_json FROM events WHERE kind='SUPERVISION_ACTION'").fetchone()
        self.original=json.loads(self.row[1])
        self.f.auth.backup={'state':'COMPLETE','missing':[],'cycle_at':990}
        self.host.record('alice',self.request)
    def tearDown(self):self.f.tearDown()
    def snapshot(self):return hashlib.sha256('\n'.join(self.db.iterdump()).encode()).hexdigest()
    def setrow(self,value):
        self.db.execute('UPDATE events SET payload_json=? WHERE event_id=?',(json.dumps(value),self.row[0]));self.db.commit()
    def test_wrong_same_event_evidence_and_impossible_combination_rejected(self):
        for key,value in [('snapshot_digest','c'*64),('backup_manifest_sha256','d'*64),('provider_ref','unregistered'),('reason','NOT_CONNECTED')]:
            doc=copy.deepcopy(self.original);doc[key]=value;self.setrow(doc);before=self.snapshot()
            with self.assertRaises(ValueError) as error:self.host.read_receipt('bob','task-1','attempt-1',self.ref['event_id'])
            self.assertNotIn('unregistered',str(error.exception));self.assertEqual(before,self.snapshot())
    def test_valid_incomplete_unknown_and_legacy_history(self):
        self.setrow(self.original)
        self.assertEqual(self.host.read_receipt('bob','task-1','attempt-1',self.ref['event_id'])['history'][0]['missing'],['RESTORE'])
        for reason in ('HANDOFF_CONTEXT_INCOMPLETE','NOT_CONNECTED','UNKNOWN_EFFECTS_RECONCILIATION_REQUIRED',None):
            doc=copy.deepcopy(self.original);doc['state']='UNKNOWN';doc['missing']=[]
            if reason is None:doc.pop('reason')
            else:doc['reason']=reason
            self.setrow(doc)
            self.assertEqual(self.host.read_receipt('bob','task-1','attempt-1',self.ref['event_id'])['history'][0]['backup_state'],'UNKNOWN')
    def test_distinct_event_cycles_keep_separate_valid_history(self):
        other=self.f.issue();request=self.f.request(other)
        request['backup_manifest_sha256']='c'*64;request['snapshot_digest']='d'*64
        self.f.auth.backup={'state':'INCOMPLETE','missing':['INSTALL_ENTRY'],'cycle_at':990}
        self.host.record('alice',request)
        first=self.host.read_receipt('bob','task-1','attempt-1',self.ref['event_id'])
        second=self.host.read_receipt('bob','task-1','attempt-1',other['event_id'])
        self.assertEqual(first['history'][0]['missing'],['RESTORE'])
        self.assertEqual(second['history'][0]['missing'],['INSTALL_ENTRY'])
        self.assertEqual(len(first['history']),1);self.assertEqual(len(second['history']),1)

    def test_protected_route_rejects_mismatched_history_without_mutation(self):
        from types import SimpleNamespace
        from task_center_app import build_handler
        from task_center_handoff_host import FormalHandoffIdentityProvider
        class Sessions:
            tenant_id='tenant-1';COOKIE='session'
            def get(self,token):return 'alice' if token == 'good' else None
            def verify_csrf(self,session,token):return token == 'good'
        class Identity(FormalHandoffIdentityProvider):
            def is_formal_session(self,session):return session=='alice'
        handler=build_handler(self.f.fixture.path,b'0'*32,'tenant-1','viewer',identity_provider=Identity(),session_store=Sessions(),handoff_host=self.host)
        def get():
            h=handler.__new__(handler);h.command='GET';h.path='/api/admin/handoff-event?task_id=task-1&attempt_id=attempt-1&event_id='+self.ref['event_id'];h.server=SimpleNamespace(server_port=8765);h.headers={'Host':'localhost:8765','Cookie':'session='+'good'};out=[]
            h._send=lambda status,data,kind,extra_headers=None:out.append((status,data));h.do_GET();return out[0]
        self.assertEqual(get()[0],200)
        doc=copy.deepcopy(self.original);doc['provider_ref']='unregistered';self.setrow(doc);before=self.snapshot()
        status,body=get();self.assertEqual(status,404);self.assertNotIn(b'unregistered',body);self.assertEqual(before,self.snapshot())

    def test_write_helper_rejects_impossible_combinations(self):
        with self.assertRaises(ValueError):self.host._alert_facts('NOT_CONNECTED','INCOMPLETE',['RESTORE'])
        with self.assertRaises(ValueError):self.host._alert_facts('UNKNOWN_EFFECTS_RECONCILIATION_REQUIRED','UNKNOWN',['RESTORE'])
        with self.assertRaises(ValueError):self.host._alert_facts('HANDOFF_CONTEXT_INCOMPLETE','INCOMPLETE',[])

if __name__=='__main__':unittest.main()
