import hashlib,io,json,sqlite3,unittest
from types import SimpleNamespace
from unittest import mock
import test_delivery_ledger_route as fixture
KEY=fixture.KEY; ADMIN=fixture.ADMIN
from task_center_app import build_handler
from task_center_session_auth import SessionStore
from task_delivery_observer import MetadataReader

class Integration144a(unittest.TestCase):
    def setUp(self):self.f=fixture.RouteTests();self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def sessions(self,tenant):
        def connect():
            c=sqlite3.connect(self.f.db);c.row_factory=sqlite3.Row;return c
        return SessionStore(connect,tenant,ttl_seconds=60)
    def session_request(self,sessions,token,path='/api/admin/delivery-ledger'):
        cls=build_handler(self.f.db,KEY,'tenant-ui','viewer',session_store=sessions,delivery_ledger_reader=self.f.reader)
        h=cls.__new__(cls);h.path=path;h.command='GET';h.headers={'Host':'localhost:8765','Cookie':sessions.COOKIE+'='+token};h.server=SimpleNamespace(server_port=8765)
        out=[];h._send=lambda status,body,content_type,extra_headers=None:out.append(status);h.do_GET();return out[0]
    def test_cross_tenant_store_and_session_fact_fail_closed(self):
        other=self.sessions('tenant-other');other.create({'tenant_id':'tenant-other','principal_id':'fixture-viewer','roles':['TASK_CENTER_ADMIN']})
        with self.assertRaisesRegex(ValueError,'TEST_METADATA_SESSION_TENANT_MISMATCH'):
            build_handler(self.f.db,KEY,'tenant-ui','viewer',session_store=other,delivery_ledger_reader=self.f.reader)
        same=self.sessions('tenant-ui');token,_,_=same.create({'tenant_id':'tenant-ui','principal_id':'fixture-viewer','roles':['TASK_CENTER_ADMIN']})
        self.assertEqual(self.session_request(same,token),200)
        self.assertEqual(self.session_request(same,''),403)
        viewer,_,_=same.create({'tenant_id':'tenant-ui','principal_id':'fixture-readonly','roles':['TASK_VIEWER']})
        self.assertEqual(self.session_request(same,viewer),403)
        with mock.patch.object(same,'get',return_value={'tenant_id':'tenant-other','roles':['TASK_CENTER_ADMIN']}):
            for path in ('/api/admin/delivery-ledger','/api/admin/delivery-handoff?task_id=task1','/api/admin/delivery-observer'):
                self.assertEqual(self.session_request(same,token,path),403)
        wrong=MetadataReader(self.f.root,'synthetic','writer','tenant-other')
        with self.assertRaisesRegex(ValueError,'TEST_METADATA_TENANT_MISMATCH'):
            build_handler(self.f.db,KEY,'tenant-ui','viewer',delivery_ledger_reader=wrong)
    def test_attachment_headers_use_existing_send(self):
        cls=build_handler(self.f.db,KEY,'tenant-ui','viewer',admin_token=ADMIN,delivery_ledger_reader=self.f.reader)
        h=cls.__new__(cls);h.path='/api/admin/delivery-handoff?task_id=task1';h.command='GET';h.headers={'Host':'localhost:8765','X-Test-Admin-Token':ADMIN};h.server=SimpleNamespace(server_port=8765)
        h.wfile=io.BytesIO();received=[];h.send_response=lambda status:received.append(('status',status));h.send_header=lambda name,value:received.append((name,value));h.end_headers=lambda:None
        h.do_GET();headers=dict(received);self.assertEqual(headers['status'],200)
        self.assertEqual(headers['Content-Disposition'],'attachment; filename="xuanjun-task-handoff.json"')
        self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        data=h.wfile.getvalue();self.assertEqual(json.loads(data.decode())['handoff']['task_id'],'task1');self.assertNotIn(ADMIN.encode(),data)
    def test_144a_public_projection_and_workbench_assets(self):
        status,body,_=self.f.call('/api/public-projection',admin=False);self.assertEqual(status,200)
        public=json.loads(body.decode());self.assertEqual(public['source'],'task-center-public-projection');self.assertNotIn('tasks',public);self.assertNotIn('tenant_id',public);self.assertEqual(public['freshness'],'UNKNOWN')
        expected={'index.html':'d13ce92e34403a26eb12aff76ac827e8be38a39c92ae6ba2e2651cd4dbe5eecf','styles.css':'7518dbf2cf1346df7c13449c51bb1cfd568cc5821db262acb00f5769eac25dab','workbench.js':'444a1bf2ea76c9b795c0e3e9190b3ddabf316b964dcf6277684395687599b31d','public-projection.js':'60625fed226b5daced47a5ce9c79ce3cf5a24546d4d9cfdbc2bd7f9c51caf543','preview.js':'be4ed31f1d9244c837acdf47b5c249e46d6f97008dd948309cb2c98a9019735b'}
        for name,sha in expected.items():
            status,body,_=self.f.call('/research-workbench/'+name,admin=False);self.assertEqual(status,200);self.assertEqual(hashlib.sha256(body).hexdigest(),sha)
        self.assertEqual(self.f.call('/api/projection')[0],200);self.assertEqual(self.f.call('/',host='elsewhere')[0],421)
if __name__=='__main__':unittest.main()
