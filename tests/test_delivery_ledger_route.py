import hashlib,json,os,sys,tempfile,unittest
from types import SimpleNamespace
ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
sys.path.insert(0,os.path.join(ROOT,'scripts'))
from task_center_app import build_handler
from task_delivery_observer import MetadataReader,observer_status
from task_delivery_ledger.core import Store,canonical,digest
from task_delivery_ledger.handoffs import SNAPSHOT_FIELDS
from task_supervisor import Supervisor
from reusable_task_gateway import GatewayKernel,TestTenantAuthority
from reusable_scheduler_cli import demo_graph

T='2026-11-16T10:00:00+08:00';KEY=b'0123456789abcdef0123456789abcdef'; ADMIN='synthetic-admin-1'
def event(eid,phase,data,validity='UNKNOWN',causation='NONE'):
    return {'schema_version':1,'sanitization':'MANUAL_REDACTED','namespace':'synthetic','event_id':eid,'task_id':'task1','attempt_id':'attempt1','idempotency_key':eid,'producer':'writer','type':phase,'validity':validity,'causation':causation,'occurred_at':T,'observed_at':T,'source':'source-ref','evidence':'evidence-ref','result':'observed','data':data}
def common(kind,id):return {'kind':kind,'id':id,'schema_version':1,'source':'source-ref','occurred_at':T,'observed_at':T,'validity':'HISTORICAL'}
class RouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=os.path.join(self.tmp.name,'tc.sqlite');sp=Supervisor(self.db);a=TestTenantAuthority(KEY);GatewayKernel(sp,a).register_graph(a.issue('tenant-ui','seed'),demo_graph('tenant-ui'));sp.close()
        self.root=os.path.join(self.tmp.name,'ledger');self.store=Store(self.root,'writer')
        obj=common('task','task1');obj.update(goal='历史任务',acceptance='UNKNOWN',instruction_ref='UNKNOWN',writer_role_id='UNKNOWN',state='UNKNOWN',blocker='UNKNOWN',next_action='等待核对',dependencies=[],code_refs=[],deploy_refs=[])
        role=common('role','role1');role.update(task_id='task1',verified_session_ref='UNKNOWN',entry_ref='entry-ref',query_capability='UNKNOWN',send_capability='UNAVAILABLE',receipt_ref='UNKNOWN')
        source=common('source_artifact','source1');source.update(task_id='task1',repo_ref='source-ref',branch='main',commit='a'*40,tree='b'*40,dirty_ref='UNKNOWN',manifest_ref='manifest-ref',size=1,artifact_sha256='c'*64,download_ref='UNKNOWN',test_ref='UNKNOWN',review_ref='UNKNOWN',deploy_refs=['deploy-ref'],rollback_ref='UNKNOWN',build_ref='build-ref')
        host=common('host_service','service1');host.update(task_id='task1',service_class='health',host_ref='host-ref',source_refs=['source-ref'],build_ref='build-ref',running_ref='UNKNOWN')
        perm=common('permission_ref','permission1');perm.update(task_id='task1',scope='read',expires_at='2020-01-01T00:00:00Z',denial='UNKNOWN',manager_ref='manager-ref')
        snap={k:'UNKNOWN' for k in SNAPSHOT_FIELDS};snap['deploy_refs']=['UNKNOWN'];snap['pending_operations']=['UNKNOWN']
        hd={'handoff_id':'h1','handoff_version':1,'snapshot_digest':digest(canonical(snap)),'actor_ref':'actor-ref','role_id':'role1','session_ref':'UNKNOWN','identity_evidence_ref':'UNKNOWN','permission_evidence_ref':'UNKNOWN','permission_expires_at':'UNKNOWN','snapshot_data':snap,'scope_included':list(SNAPSHOT_FIELDS),'scope_excluded':[],'scope_authorization_ref':'UNKNOWN'}
        data=[event('e01','register',obj,'HISTORICAL'),event('e02','register',role),event('e03','register',source),event('e04','register',host),event('e05','register',perm),event('e06','send_accepted',{},'HISTORICAL'),event('e07','actual_received',{},'STALE'),event('e08','handoff_propose',hd),event('e09','register',dict(obj,goal='其他任务目标'),'HISTORICAL')]
        for e in data:self.store.enqueue(e)
        self.store.flush('synthetic');self.reader=MetadataReader(self.root,'synthetic','writer','tenant-ui')
    def tearDown(self):self.tmp.cleanup()
    def call(self,path,admin=True,reader='bound',host='localhost:8765'):
        chosen=self.reader if reader=='bound' else None
        cls=build_handler(self.db,KEY,'tenant-ui','viewer',admin_token=ADMIN,delivery_ledger_reader=chosen)
        h=cls.__new__(cls);h.path=path;h.command='GET';h.headers={'Host':host};h.server=SimpleNamespace(server_port=8765)
        if admin:h.headers['X-Test-Admin-Token']=ADMIN
        received=[];h._send=lambda status,body,content_type,extra_headers=None:received.append((status,body,content_type))
        h.do_GET();return received[0]
    def test_main_handler_actual_routes_and_export(self):
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in __import__('pathlib').Path(self.root).rglob('*') if p.is_file()}
        status,body,_=self.call('/api/admin/delivery-ledger');self.assertEqual(status,200);data=json.loads(body.decode());row=data['tasks'][0]
        self.assertEqual(data['conflicts'],['e09']);self.assertEqual(data['writer_verification'],'UNKNOWN');self.assertEqual(data['source_trust'],'UNAVAILABLE')
        self.assertEqual(row['receipt']['sent']['validity'],'HISTORICAL');self.assertEqual(row['receipt']['received']['validity'],'STALE');self.assertEqual(row['receipt']['started'],'UNKNOWN')
        self.assertEqual(row['entry'],'UNKNOWN');self.assertEqual(row['permissions'][0]['validity'],'EXPIRED');self.assertEqual(row['sources'][0]['build'],'build-ref');self.assertEqual(row['services'][0]['running'],'UNKNOWN')
        self.assertNotEqual(row['handoffs'][0]['status'],'交接完成(范围)')
        status,body,_=self.call('/api/admin/delivery-handoff?task_id=task1');self.assertEqual(status,200);v=json.loads(body.decode());self.assertEqual(v['handoff']['task_id'],'task1');self.assertIn('task1:h1',v['handoff']['handoffs'])
        status,page,_=self.call('/delivery-ledger.html');self.assertEqual(status,404)
        status,js,_=self.call('/delivery-ledger.js');self.assertEqual(status,404)
        after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in __import__('pathlib').Path(self.root).rglob('*') if p.is_file()};self.assertEqual(before,after)
    def test_denied_unavailable_badquery_and_existing_routes(self):
        self.assertEqual(self.call('/api/admin/delivery-ledger',False)[0],403)
        self.assertEqual(self.call('/delivery-ledger.html',False)[0],404)
        self.assertEqual(self.call('/api/admin/delivery-ledger',reader=None)[0],503)
        self.assertEqual(self.call('/api/admin/delivery-handoff?task_id=task1&extra=1')[0],503)
        status,body,_=self.call('/api/admin/delivery-observer');self.assertEqual(status,200);self.assertEqual(json.loads(body.decode())['state'],'UNAVAILABLE')
        self.assertEqual(self.call('/api/projection')[0],200);self.assertEqual(self.call('/')[0],200)
        self.assertEqual(self.call('/api/admin/delivery-ledger',host='elsewhere')[0],421)
    def test_existing_session_role_and_tenant_boundary(self):
        import sqlite3
        from task_center_session_auth import SessionStore
        def conn():
            c=sqlite3.connect(self.db);c.row_factory=sqlite3.Row;return c
        clock=[1000.0];sessions=SessionStore(conn,'tenant-ui',ttl_seconds=10,clock=lambda:clock[0])
        token,_,_=sessions.create({'tenant_id':'tenant-ui','principal_id':'viewer','roles':['TASK_CENTER_ADMIN']})
        cls=build_handler(self.db,KEY,'tenant-ui','viewer',session_store=sessions,delivery_ledger_reader=self.reader)
        def get():
            h=cls.__new__(cls);h.path='/api/admin/delivery-ledger';h.command='GET';h.headers={'Host':'localhost:8765','Cookie':sessions.COOKIE+'='+token};h.server=SimpleNamespace(server_port=8765)
            out=[];h._send=lambda status,body,content_type,extra_headers=None:out.append(status);h.do_GET();return out[0]
        self.assertEqual(get(),200);clock[0]+=11;self.assertEqual(get(),403)
        wrong=MetadataReader(self.root,'synthetic','writer','other-tenant')
        with self.assertRaises(ValueError):build_handler(self.db,KEY,'tenant-ui','viewer',delivery_ledger_reader=wrong)
    def test_historical_354_example_is_not_current_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root,'ledger-writer')
            with open(os.path.join(ROOT,'examples','354-historical.json'),encoding='utf8') as f:value=json.load(f)
            store.enqueue(value);store.flush('pilot354');reader=MetadataReader(root,'pilot354','ledger-writer','tenant-ui')
            cls=build_handler(self.db,KEY,'tenant-ui','viewer',admin_token=ADMIN,delivery_ledger_reader=reader)
            h=cls.__new__(cls);h.path='/api/admin/delivery-ledger';h.command='GET';h.headers={'Host':'localhost:8765','X-Test-Admin-Token':ADMIN};h.server=SimpleNamespace(server_port=8765)
            out=[];h._send=lambda status,body,content_type,extra_headers=None:out.append((status,body));h.do_GET()
            self.assertEqual(out[0][0],200);data=json.loads(out[0][1].decode());row=data['tasks'][0]
            self.assertEqual(row['task_id'],'pilot-354');self.assertEqual(row['validity'],'HISTORICAL');self.assertEqual(row['writer'],'UNKNOWN');self.assertEqual(row['receipt']['received'],'UNKNOWN');self.assertEqual(data['source_trust'],'UNAVAILABLE')
    def test_corrupt_event_denied_preserved(self):
        path=__import__('pathlib').Path(self.root)/'events/synthetic/e01.json';original=path.read_text();value=json.loads(original);value['producer']='other';path.write_text(json.dumps(value));before=path.read_bytes()
        self.assertEqual(self.call('/api/admin/delivery-ledger')[0],503);self.assertEqual(self.call('/api/admin/delivery-handoff?task_id=task1')[0],503);self.assertEqual(path.read_bytes(),before)
if __name__=='__main__':unittest.main()
