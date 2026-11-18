"""TEST_ONLY: real handler and session store, synthetic tenant; no listener."""
import hashlib, json, os, re, sqlite3, sys, tempfile, unittest
from types import SimpleNamespace
from urllib.parse import urljoin
ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from task_center_app import (build_handler, WORKBENCH_ROOT, ModelControl,
    ensure_onboarding_schema, ConnectionManager, CodexExecutionControl)
from cryptography.fernet import Fernet
from task_center_session_auth import SessionStore
from task_supervisor import Supervisor
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
from reusable_scheduler_cli import demo_graph
KEY = b'0123456789abcdef0123456789abcdef'

class WorkbenchAssemblyDelta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.db = os.path.join(self.tmp.name, 'state.sqlite')
        s = Supervisor(self.db); a = TestTenantAuthority(KEY)
        g = GatewayKernel(s, a); g.register_graph(a.issue('tenant-synthetic', 'seed'), demo_graph('tenant-synthetic'))
        ctx = a.issue('tenant-synthetic', 'admin:viewer'); key = Fernet.generate_key()
        ModelControl(g, ctx, key); ensure_onboarding_schema(s.db); ConnectionManager(g, ctx, key); CodexExecutionControl(g, ctx); s.close()
        def connect():
            c = sqlite3.connect(self.db); c.row_factory = sqlite3.Row; return c
        self.sessions = SessionStore(connect, 'tenant-synthetic', ttl_seconds=600)
        self.tokens = {}
        for role in ('TASK_CENTER_ADMIN', 'TASK_CENTER_VIEWER'):
            self.tokens[role] = self.sessions.create({'tenant_id':'tenant-synthetic', 'principal_id':'fixture-'+role, 'roles':[role]})[0]
        self.handler = build_handler(self.db, KEY, 'tenant-synthetic', 'viewer', session_store=self.sessions)
    def tearDown(self): self.tmp.cleanup()
    def get(self, path, role=None):
        h = self.handler.__new__(self.handler); h.path = path; h.command = 'GET'
        h.headers = {'Host':'localhost:8765'}; h.server = SimpleNamespace(server_port=8765)
        if role: h.headers['Cookie'] = self.sessions.COOKIE + '=' + self.tokens[role]
        result = {'headers':{}}
        def send(status, body, content_type, extra_headers=None):
            result.update(status=status, body=body, content_type=content_type)
            result['headers'].update(dict(extra_headers or []))
        h._send = send
        h.send_response = lambda status: result.update(status=status)
        h.send_header = lambda k,v: result['headers'].update({k:v})
        h.end_headers = lambda: None
        h.do_GET(); return result
    def test_entries_assets_and_api_contract(self):
        admin = 'TASK_CENTER_ADMIN'; viewer = 'TASK_CENTER_VIEWER'
        for path in ('/workbench/', '/workbench/index.html', '/workbench/legacy.html'):
            r = self.get(path); self.assertEqual(r['status'], 302); self.assertEqual(r['headers']['Location'], '/login.html')
            for role in (admin, viewer): self.assertEqual(self.get(path,role)['status'],200)
        self.assertEqual(self.get('/api/session')['status'],401)
        self.assertEqual(self.get('/api/admin/workbench')['status'],403)
        self.assertEqual(self.get('/api/admin/workbench',viewer)['status'],403)
        session = json.loads(self.get('/api/session',admin)['body']); self.assertEqual(session['tenant_id'],'tenant-synthetic')
        projection = json.loads(self.get('/api/admin/workbench',admin)['body'])
        self.assertEqual(projection['tenant_id'],session['tenant_id']); self.assertEqual(projection['projection'],'UNIFIED_ADMIN_PROJECTION_V1')
        self.assertEqual(projection['mode'],'TEST_ONLY'); self.assertEqual(projection['capability']['mutation'],'NONE')
        module = projection['modules']['research-development']; self.assertEqual(module['status'],'CONNECTED_TEST_ONLY'); self.assertIsInstance(module['records'],list)
        for row in module['records']: self.assertIsInstance(row['task_id'],str); self.assertTrue(row['task_id'])
        new = self.get('/workbench/',admin)['body']; self.assertEqual(new,self.get('/workbench/index.html',admin)['body'])
        refs = re.findall(rb'(?:src|href)="([^"#]+)"',new)
        self.assertEqual(refs,[b'shell.css',b'catalog.js',b'task-read-adapter.js',b'shell.js'])
        legacy = self.get('/workbench/legacy.html',admin)['body']; self.assertIn(b'owner-workbench-v2',legacy)
        legacyrefs = re.findall(rb'(?:src|href)="([^"#]+)"',legacy)
        for ref in (b'styles.css',b'data.js',b'app.js'): self.assertIn(ref,legacyrefs)
        for ref in refs + [b'fonts/NotoSansCJKsc-Regular.otf',b'styles.css',b'data.js',b'app.js']:
            path = urljoin('/workbench/',ref.decode()); r = self.get(path)
            self.assertEqual(r['status'],200,path)
            file = os.path.join(WORKBENCH_ROOT, ('admin-owner/' if ref in refs or ref.startswith(b'fonts/') else '') + ref.decode())
            with open(file,'rb') as f: self.assertEqual(hashlib.sha256(r['body']).digest(),hashlib.sha256(f.read()).digest())
        css = self.get('/workbench/shell.css')['body']; self.assertIn(b'fonts/NotoSansCJKsc-Regular.otf',css)
        self.assertEqual(urljoin('/workbench/','../api/session'),'/api/session')
        self.assertEqual(urljoin('/workbench/','../api/admin/workbench'),'/api/admin/workbench')

# Reuse the existing loopback-only TEST_ONLY HTTP runner and identity fixture.
from tests.test_task_center_session_auth import SessionAuthIntegrationTests
import http.client
class WorkbenchHTTP(SessionAuthIntegrationTests):
    def test_workbench_http_session_and_assets(self):
        def raw(path, cookie=None):
            conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
            conn.request('GET',path,headers={'Cookie':cookie} if cookie else {})
            response = conn.getresponse(); body = response.read(); result = (response.status, dict(response.getheaders()), body); conn.close(); return result
        for path in ('/workbench/','/workbench/index.html','/workbench/legacy.html'):
            status,headers,_ = raw(path); self.assertEqual(status,302); self.assertEqual(headers['Location'],'/login.html')
        self.assertEqual(raw('/api/session')[0],401); self.assertEqual(raw('/api/admin/workbench')[0],403)
        for role in ('TASK_CENTER_ADMIN','TASK_CENTER_VIEWER'):
            token,_,_ = self.sessions.create({'tenant_id':'tenant-session','principal_id':'http-fixture','roles':[role]})
            cookie = self.sessions.COOKIE+'='+token
            for path in ('/workbench/','/workbench/index.html','/workbench/legacy.html'): self.assertEqual(raw(path,cookie)[0],200)
            status,_,body=raw('/api/session',cookie); self.assertEqual(status,200); session=json.loads(body); self.assertEqual(session['tenant_id'],'tenant-session')
            status,_,body=raw('/api/admin/workbench',cookie)
            if role=='TASK_CENTER_VIEWER': self.assertEqual(status,403); continue
            self.assertEqual(status,200); projection=json.loads(body); self.assertEqual(projection['tenant_id'],session['tenant_id']); self.assertEqual(projection['projection'],'UNIFIED_ADMIN_PROJECTION_V1')
            module=projection['modules']['research-development']; self.assertEqual(module['status'],'CONNECTED_TEST_ONLY'); self.assertIsInstance(module['records'],list)
        status,_,page=raw('/workbench/',cookie); self.assertEqual(status,200)
        self.assertLess(page.index(b'src="catalog.js"'),page.index(b'src="task-read-adapter.js"')); self.assertLess(page.index(b'src="task-read-adapter.js"'),page.index(b'src="shell.js"'))
        for ref in ('shell.css','catalog.js','task-read-adapter.js','shell.js','fonts/NotoSansCJKsc-Regular.otf','styles.css','data.js','app.js'):
            status,_,body=raw(urljoin('/workbench/',ref)); self.assertEqual(status,200,ref)
            filename=os.path.join(WORKBENCH_ROOT, ('admin-owner/' if ref not in ('styles.css','data.js','app.js') else '')+ref)
            with open(filename,'rb') as f: self.assertEqual(hashlib.sha256(body).digest(),hashlib.sha256(f.read()).digest())
