"""Real loopback serving thread; all host identity/backup are fixtures."""
import http.client, json, threading
from pathlib import Path
from test_handoff_ledger_host_bridge import MainChain
from task_center_app import make_server
from task_delivery_observer import MetadataReader

class ThreadFix(MainChain):
    def test_threaded_http_and_committed_recovery(self):
        for action,label,cause,actor in [('PROPOSE','p','NONE','alice'),('NOMINATE','n','p','alice'),('RECEIVE','r','p','bob'),('ALIGNED','a','r','bob'),('SUPERVISION_START','s','n','carol'),('VERIFIED','v','s','carol')]:
            value=self.make(action,label,cause,actor)
            self.assertEqual(self.host.record(actor,value)['state'],'RECORDED')
            # Model interruption after the commit: publication is explicitly recovered.
            self.assertEqual(self.bridge.flush('task-1','attempt-1',value['event_id'])['enqueue'],'APPENDED')
        eid=value['event_id'];self.assertEqual(self.bridge.flush('task-1','attempt-1',eid)['enqueue'],'DUPLICATE')
        flushed=[]
        t=threading.Thread(target=lambda:flushed.append(self.bridge.flush('task-1','attempt-1',eid)))
        t.start();t.join(3);self.assertEqual(flushed[0]['enqueue'],'DUPLICATE')
        reader=MetadataReader(self.bridge.root,'tenant-ledger','writer','tenant-1',ledger_authority=self.bridge)
        server=make_server(self.path,b'0123456789abcdef0123456789abcdef','tenant-1','viewer',port=0,admin_token='synthetic-admin-1',outbound_enabled=False,delivery_ledger_reader=reader)
        thread=threading.Thread(target=server.serve_forever);thread.start()
        def get(admin=True):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
            try:
                headers={'Host':'localhost:%s'%server.server_port}
                if admin:headers['X-Test-Admin-Token']='synthetic-admin-1'
                c.request('GET','/api/admin/delivery-handoff?task_id=task-1',headers=headers)
                response=c.getresponse();return response.status,json.loads(response.read().decode())
            finally:c.close()
        try:
            self.assertEqual(get(False)[0],403)
            status,body=get();self.assertEqual(status,200)
            key='task-1:'+self.refs['p']['handoff_id']
            self.assertEqual(body['handoff']['handoffs'][key]['handoff_status'],'交接完成(范围)')
            self.auth.verify_ledger_event_current=lambda event,record:False
            status,body=get();self.assertEqual(status,200)
            self.assertNotEqual(body['handoff']['handoffs'][key]['handoff_status'],'交接完成(范围)')
            path=Path(self.bridge.root)/'events'/'tenant-ledger'/(eid+'.json')
            path.write_bytes(b'{}')
            self.assertEqual(self.bridge.flush('task-1','attempt-1',eid)['flush']['conflict'],1)
            self.assertEqual(get()[0],503)
        finally:
            server.shutdown();thread.join(3);server.server_close()

    def test_make_server_original_post_publishes_and_recovers(self):
        import sqlite3
        from task_center_session_auth import SessionStore
        from task_center_handoff_host import FormalHandoffIdentityProvider
        class FixtureIdentity(FormalHandoffIdentityProvider):
            def is_formal_session(self,session):return session.get('principal_id')=='alice'
        def connect():
            db=sqlite3.connect(self.path);db.row_factory=sqlite3.Row;return db
        sessions=SessionStore(connect,'tenant-1',ttl_seconds=7200)
        token,csrf,_=sessions.create({'tenant_id':'tenant-1','principal_id':'alice','roles':['TASK_CENTER_ADMIN']})
        original_auth=self.auth.authenticate_and_authorize
        self.auth.authenticate_and_authorize=lambda session,action,binding:original_auth(session['principal_id'] if isinstance(session,dict) else session,action,binding)
        value=self.make('PROPOSE','p','NONE','alice')
        server=make_server(self.path,b'0123456789abcdef0123456789abcdef','tenant-1','viewer',port=0,identity_provider=FixtureIdentity(),session_store=sessions,outbound_enabled=False,handoff_host=self.host,ledger_bridge=self.bridge)
        thread=threading.Thread(target=server.serve_forever);thread.start()
        def call(method,path,body=None):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
            try:
                headers={'Host':'localhost:%s'%server.server_port,'Cookie':sessions.COOKIE+'='+token,'X-CSRF-Token':csrf,'Content-Type':'application/json'}
                c.request(method,path,body=json.dumps(body) if body is not None else None,headers=headers)
                response=c.getresponse();return response.status,json.loads(response.read().decode())
            finally:c.close()
        flush=self.bridge.flush
        try:
            import copy
            wrong=copy.deepcopy(value);wrong['ledger_event']['producer']='other-writer'
            self.assertEqual(call('POST','/api/admin/handoff-event',wrong)[0],409)
            self.bridge.flush=lambda *args:(_ for _ in ()).throw(OSError('fixture interrupted'))
            status,body=call('POST','/api/admin/handoff-event',value)
            self.assertEqual(status,200);self.assertEqual(body['state'],'RECORDED');self.assertEqual(body['ledger_publication'],'PENDING_RECOVERY')
            self.bridge.flush=flush
            status,body=call('POST','/api/admin/handoff-event',value)
            self.assertEqual(status,200);self.assertEqual(body['state'],'ALREADY_RECORDED');self.assertEqual(body['ledger_publication'],'PUBLISHED')
            self.assertEqual(call('GET','/api/admin/delivery-handoff?task_id=task-1')[0],200)
            sessions.revoke(token)
            self.assertEqual(call('GET','/api/admin/delivery-handoff?task_id=task-1')[0],403)
        finally:
            self.bridge.flush=flush
            server.shutdown();thread.join(3);server.server_close()
