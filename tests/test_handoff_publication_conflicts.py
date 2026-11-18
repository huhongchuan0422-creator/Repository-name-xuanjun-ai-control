"""HTTP publication conflict regressions; synthetic identities and backups."""
import copy, http.client, json, sqlite3, threading
from pathlib import Path
from test_handoff_ledger_host_bridge import MainChain
from task_center_app import make_server
from task_center_handoff_host import FormalHandoffIdentityProvider
from task_center_session_auth import SessionStore
from task_delivery_ledger.core import canonical

class PublicationConflicts(MainChain):
    def setup_server(self):
        class Identity(FormalHandoffIdentityProvider):
            def is_formal_session(self,session):return session.get('principal_id')=='alice'
        def connect():
            db=sqlite3.connect(self.path);db.row_factory=sqlite3.Row;return db
        self.sessions=SessionStore(connect,'tenant-1')
        self.token,self.csrf,_=self.sessions.create({'tenant_id':'tenant-1','principal_id':'alice','roles':['TASK_CENTER_ADMIN']})
        auth=self.auth.authenticate_and_authorize
        self.auth.authenticate_and_authorize=lambda session,action,binding:auth(session['principal_id'] if isinstance(session,dict) else session,action,binding)
        self.server=make_server(self.path,b'0123456789abcdef0123456789abcdef','tenant-1','viewer',port=0,identity_provider=Identity(),session_store=self.sessions,outbound_enabled=False,handoff_host=self.host,ledger_bridge=self.bridge)
        self.thread=threading.Thread(target=self.server.serve_forever);self.thread.start()
    def stop_server(self):
        self.server.shutdown();self.thread.join(3);self.server.server_close()
    def post(self,event):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            c.request('POST','/api/admin/handoff-event',json.dumps(event),{'Host':'localhost:%s'%self.server.server_port,'Cookie':self.sessions.COOKIE+'='+self.token,'X-CSRF-Token':self.csrf,'Content-Type':'application/json'})
            r=c.getresponse();return r.status,json.loads(r.read())
        finally:c.close()
    def test_current_outbox_conflict(self):
        self.setup_server()
        try:
            event=self.make('PROPOSE','p','NONE','alice')
            path=Path(self.bridge.root)/'outbox'/'tenant-ledger'/(event['event_id']+'.json')
            path.parent.mkdir(parents=True);path.write_bytes(b'{}')
            status,body=self.post(event);self.assertEqual(status,200);self.assertEqual(body['state'],'RECORDED')
            self.assertEqual(body['ledger_publication'],'CONFLICT')
            status,again=self.post(event);self.assertEqual(status,200);self.assertEqual(again['state'],'ALREADY_RECORDED');self.assertEqual(again['ledger_publication'],'CONFLICT')
            self.assertEqual(path.read_bytes(),b'{}')
        finally:self.stop_server()
    def test_other_event_conflict_current_published(self):
        self.setup_server()
        try:
            p=self.make('PROPOSE','p','NONE','alice');self.assertEqual(self.post(p)[1]['ledger_publication'],'PUBLISHED')
            old=Path(self.bridge.root)/'events'/'tenant-ledger'/(p['event_id']+'.json');old.write_bytes(b'{}')
            n=self.make('NOMINATE','n','p','alice');status,body=self.post(n)
            self.assertEqual(status,200);self.assertEqual(body['ledger_publication'],'PUBLISHED');self.assertNotIn('ledger_other_conflicts',body)
            status,again=self.post(n);self.assertEqual(status,200);self.assertEqual(again['state'],'ALREADY_RECORDED');self.assertEqual(again['ledger_publication'],'PUBLISHED');self.assertNotIn('ledger_other_conflicts',again)
            current=Path(self.bridge.root)/'events'/'tenant-ledger'/(n['event_id']+'.json')
            self.assertEqual(current.read_bytes(),canonical(n['ledger_event']));self.assertEqual(old.read_bytes(),b'{}')
        finally:self.stop_server()
    def test_current_published_file_conflict(self):
        self.setup_server()
        try:
            event=self.make('PROPOSE','p','NONE','alice');self.assertEqual(self.post(event)[1]['ledger_publication'],'PUBLISHED')
            path=Path(self.bridge.root)/'events'/'tenant-ledger'/(event['event_id']+'.json');path.write_bytes(b'{}')
            status,body=self.post(event)
            self.assertEqual(status,200);self.assertEqual(body['state'],'ALREADY_RECORDED');self.assertEqual(body['ledger_publication'],'CONFLICT')
            self.assertEqual(path.read_bytes(),b'{}')
        finally:self.stop_server()
