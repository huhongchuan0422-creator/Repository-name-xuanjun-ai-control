import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from html.parser import HTMLParser
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import urlopen

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
sys.path.insert(0,os.path.join(ROOT,'scripts'))
import task_center_app as app
from reusable_scheduler_cli import demo_graph
from reusable_task_gateway import GatewayKernel,TestTenantAuthority
from task_supervisor import Supervisor

KEY=bytes(range(32))
PREFIX='/task-center-test/'
CSP="default-src 'self'; object-src 'none'; frame-ancestors 'none'"
ASSETS={
    'index.html':('3a358955f7b257c1b14a439dee0568ae3c36d46c6b5fdbb1a6c6773e996d38e7','text/html; charset=utf-8'),
    'styles.css':('7518dbf2cf1346df7c13449c51bb1cfd568cc5821db262acb00f5769eac25dab','text/css; charset=utf-8'),
    'workbench.js':('de7a1513f1a0a3c2b34276bf9beff0baa55819f4cbd30d4671b6c76ede4ceee3','application/javascript; charset=utf-8'),
    'public-projection.js':('60625fed226b5daced47a5ce9c79ce3cf5a24546d4d9cfdbc2bd7f9c51caf543','application/javascript; charset=utf-8'),
    'preview.js':('77dbd0213f12de8a5ba75dbbf7bcee16ac75e032e56fd0990cc381a706a8d6f6','application/javascript; charset=utf-8'),
}

class ScriptTags(HTMLParser):
    def __init__(self):super().__init__();self.scripts=[];self.inline=False
    def handle_starttag(self,tag,attrs):
        if tag=='script':
            value=dict(attrs).get('src');self.scripts.append(value)
            if value is None:self.inline=True

class ResearchWorkbenchAssetsDelta(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.mkdtemp();self.db=os.path.join(self.tmp,'fixture.sqlite')
        supervisor=Supervisor(self.db);authority=TestTenantAuthority(KEY)
        GatewayKernel(supervisor,authority).register_graph(authority.issue('tenant-fixture','seed'),demo_graph('tenant-fixture'))
        supervisor.db.execute('UPDATE tasks SET last_event_at=100');supervisor.db.commit();supervisor.close()
        self.server=app.make_server(self.db,KEY,'tenant-fixture','viewer',port=0,base_path=PREFIX)
        self.thread=threading.Thread(target=self.server.serve_forever);self.thread.daemon=True;self.thread.start()
        self.base='http://127.0.0.1:%d'%self.server.server_port
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2);shutil.rmtree(self.tmp)
    def get(self,path):
        with urlopen(self.base+path,timeout=3) as response:
            return response.status,response.headers,response.read()
    def test_six_assets_bytes_headers_and_script_order(self):
        for name,(expected,mime) in ASSETS.items():
            status,headers,body=self.get(PREFIX+'research-workbench/'+name)
            self.assertEqual(status,200);self.assertEqual(hashlib.sha256(body).hexdigest(),expected)
            self.assertEqual(headers['Content-Type'],mime);self.assertEqual(headers['Content-Security-Policy'],CSP)
            self.assertEqual(headers['X-Content-Type-Options'],'nosniff');self.assertEqual(headers['Cache-Control'],'no-store')
            if name=='index.html':html=body.decode('utf-8')
            if name=='public-projection.js':adapter=body.decode('utf-8')
            if name=='preview.js':preview=body.decode('utf-8')
        status,headers,body=self.get(PREFIX+'research-workbench/')
        self.assertEqual(status,200);self.assertEqual(hashlib.sha256(body).hexdigest(),ASSETS['index.html'][0])
        parser=ScriptTags();parser.feed(html)
        self.assertFalse(parser.inline);self.assertEqual(parser.scripts,['workbench.js','public-projection.js','preview.js'])
        self.assertIn("credentials:'omit'",adapter)
        self.assertIn("new URL('../api/public-projection',document.baseURI)",preview)
        self.assertEqual(urljoin(self.base+PREFIX+'research-workbench/index.html','../api/public-projection'),self.base+PREFIX+'api/public-projection')
    def test_anonymous_public_api_and_legacy_roots_preserved(self):
        _,headers,body=self.get(PREFIX+'api/public-projection');data=json.loads(body.decode('utf-8'))
        self.assertEqual(headers['Content-Security-Policy'],CSP)
        self.assertEqual(data['source'],'task-center-public-projection');self.assertEqual(data['schema_version'],1)
        self.assertEqual(data['observed_at'],100);self.assertEqual(data['freshness'],'UNKNOWN');self.assertIsNone(data['valid_until'])
        self.assertNotIn('tenant_id',data);self.assertNotIn('tasks',data)
        _,_,body=self.get(PREFIX)
        with open(os.path.join(app.ASSET_ROOT,'index.html'),'rb') as f:self.assertEqual(body,f.read())
        _,_,body=self.get(PREFIX+'workbench/')
        with open(os.path.join(app.WORKBENCH_ROOT,'index.html'),'rb') as f:self.assertEqual(body,f.read())
        for name in ('integration-manifest.json','resource-metadata.test.cjs','dev-preview.cjs'):
            with self.assertRaises(HTTPError) as caught:self.get(PREFIX+'research-workbench/'+name)
            self.assertEqual(caught.exception.code,404)
    def test_preview_uses_real_http_projection_and_admin_denial(self):
        subprocess.check_call(['node', 'tests/research_workbench_http_delta.test.cjs', self.base+PREFIX], cwd=ROOT, timeout=15)

    def test_rendered_return_link_resolves_to_existing_main_entry(self):
        # Use the actually served JS from the selected app root (including
        # installed-base overlays), not a separately copied JS fixture.
        workbench=os.path.join(app.ASSET_ROOT,'research-workbench','workbench.js')
        payload=subprocess.check_output(['node','tests/research_return_link_delta.test.cjs',workbench],cwd=ROOT,timeout=15)
        links=json.loads(payload.decode('utf-8'))
        for page in ('research-workbench/','research-workbench/index.html'):
            for link in links:
                target=urljoin(self.base+PREFIX+page,link)
                self.assertEqual(target,self.base+PREFIX+'task-center.html')
                status,_,body=self.get(PREFIX+'task-center.html')
                self.assertEqual(status,200)
                self.assertIn(b'id=\"researchEntry\"',body)
                self.assertIn(b'task-center.js',body)
        with self.assertRaises(HTTPError) as denied:self.get(PREFIX+'api/admin/delivery-ledger')
        self.assertEqual(denied.exception.code,403)

    def test_public_api_error_is_503_without_internal_details(self):
        with patch.object(app,'read_only_projection',side_effect=ValueError('INTERNAL_PRIVATE_DETAIL')):
            with self.assertRaises(HTTPError) as caught:self.get(PREFIX+'api/public-projection')
        self.assertEqual(caught.exception.code,503)
        body=caught.exception.read().decode('utf-8')
        self.assertEqual(json.loads(body),{'error':'PUBLIC_PROJECTION_UNAVAILABLE'})
        self.assertNotIn('INTERNAL_PRIVATE_DETAIL',body)

if __name__=='__main__':unittest.main()
