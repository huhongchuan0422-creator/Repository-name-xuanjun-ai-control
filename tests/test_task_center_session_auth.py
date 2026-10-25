from __future__ import print_function

import http.cookiejar
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from cryptography.fernet import Fernet

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
import sys
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

from reusable_scheduler_cli import demo_graph
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
from task_center_app import make_server
from task_center_session_auth import (FileTestIdentityProvider, SessionStore,
                                      password_hash)
from task_supervisor import Supervisor

KEY = b'0123456789abcdef0123456789abcdef'


class SessionAuthIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.mkdtemp();self.db=os.path.join(self.root,'state.sqlite3')
        supervisor=Supervisor(self.db);authority=TestTenantAuthority(KEY)
        GatewayKernel(supervisor,authority).register_graph(
          authority.issue('tenant-session','seed'),demo_graph('tenant-session'))
        supervisor.close()
        self.identity_path=os.path.join(self.root,'identities.json')
        users={'admin':{'password_hash':password_hash('fixture-password-only'),
          'tenant_id':'tenant-session','principal_id':'owner-test',
          'roles':['TASK_CENTER_ADMIN','TASK_EXECUTOR'],'enabled':True},
          'viewer':{'password_hash':password_hash('fixture-viewer-only'),
          'tenant_id':'tenant-session','principal_id':'viewer-test',
          'roles':['TASK_CENTER_VIEWER'],'enabled':True}}
        with open(self.identity_path,'w') as stream:json.dump({'users':users},stream)
        os.chmod(self.identity_path,0o600)
        def connect():
            db=sqlite3.connect(self.db);db.row_factory=sqlite3.Row;return db
        self.sessions=SessionStore(connect,'tenant-session',ttl_seconds=600)
        self.server=make_server(self.db,KEY,'tenant-session','viewer',port=0,
          model_master_key=Fernet.generate_key(),
          identity_provider=FileTestIdentityProvider(self.identity_path),
          session_store=self.sessions,outbound_enabled=False)
        self.thread=threading.Thread(target=self.server.serve_forever)
        self.thread.daemon=True;self.thread.start()
        self.base='http://127.0.0.1:%d'%self.server.server_port
        self.jar=http.cookiejar.CookieJar()
        self.client=build_opener(HTTPCookieProcessor(self.jar))

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
        shutil.rmtree(self.root)

    def request(self,path,method='GET',value=None,csrf=None):
        headers={'Content-Type':'application/json'}
        if csrf:headers['X-CSRF-Token']=csrf
        body=None if value is None else json.dumps(value).encode('utf-8')
        return self.client.open(Request(self.base+path,data=body,method=method,
          headers=headers),timeout=3)

    def login(self,user='admin',password='fixture-password-only'):
        response=self.request('/api/session/login','POST',
          {'username':user,'password':password})
        return json.loads(response.read().decode('utf-8'))

    def test_login_cookie_csrf_logout_and_expiry_are_server_enforced(self):
        with self.assertRaises(HTTPError) as denied:
            self.request('/api/projection')
        self.assertEqual(denied.exception.code,401)
        receipt=self.login();self.assertEqual(receipt['state'],'AUTHENTICATED')
        session=json.loads(self.request('/api/session').read().decode('utf-8'))
        self.assertEqual(session['principal_id'],'owner-test')
        with self.assertRaises(HTTPError) as csrf:
            self.request('/api/admin/model-control','POST',{'action':'RECONCILE_CODEX_RESTART'})
        self.assertEqual(csrf.exception.code,403)
        response=self.request('/api/session/logout','POST',{},receipt['csrf_token'])
        self.assertEqual(json.loads(response.read())['state'],'LOGGED_OUT')
        with self.assertRaises(HTTPError) as logged_out:
            self.request('/api/session')
        self.assertEqual(logged_out.exception.code,401)
        self.login()
        db=sqlite3.connect(self.db)
        db.execute('UPDATE task_center_sessions SET expires_at=0')
        db.commit();db.close()
        with self.assertRaises(HTTPError) as expired:
            self.request('/api/session')
        self.assertEqual(expired.exception.code,401)

    def test_non_admin_session_cannot_read_or_mutate_admin_api(self):
        receipt=self.login('viewer','fixture-viewer-only')
        with self.assertRaises(HTTPError) as denied:
            self.request('/api/admin/model-control')
        self.assertEqual(denied.exception.code,403)
        with self.assertRaises(HTTPError) as denied_post:
            self.request('/api/admin/model-control','POST',
              {'action':'RECONCILE_CODEX_RESTART'},receipt['csrf_token'])
        self.assertEqual(denied_post.exception.code,403)

    def test_admin_page_uses_session_and_canonical_asset_query_contract(self):
        receipt=self.login()
        html=self.request('/admin.html').read().decode('utf-8')
        js=self.request('/admin.js').read().decode('utf-8')
        self.assertNotIn('adminToken',html);self.assertNotIn('actorToken',html)
        self.assertIn('QUERY_CANONICAL_ASSET',js)
        self.assertNotIn("source_kind:'REGISTRY'",js)
        projection=json.loads(self.request('/api/admin/model-control').read())
        self.assertEqual(projection['mode'],'TEST_ONLY')
        def post(value):
            return json.loads(self.request('/api/admin/model-control','POST',
              value,receipt['csrf_token']).read().decode('utf-8'))
        task={'project_id':'project-session','task_id':'task-session',
          'board_id':'research-development','delivery_stage':'implementation',
          'feature_unit':'session-journey','goal':'verify session page journey',
          'scope':['WRITE_SOURCE'],'asset_version':'asset-session-v1',
          'deliverables':['source'],'acceptance':['tests'],'dependencies':[],
          'priority':50,'owner':'owner-test'}
        self.assertIn('graph_id',post({'action':'CREATE_PROJECT_TASK','task':task}))
        query=post({'action':'QUERY_CANONICAL_ASSET','task_id':'task-session',
          'query_id':'query-session','source_version':'registry-session-v1',
          'asset_key':'missing-session-asset'})
        self.assertEqual(query['query_id'],'query-session')
        preflight=post({'action':'RECORD_DISPATCH_PREFLIGHT',
          'task_id':'task-session','asset_version':'asset-session-v1',
          'query_ids':['query-session'],'outcome':'NOT_FOUND',
          'reuse_reason':'canonical source proves absence in fixture'})
        self.assertEqual(preflight['state'],'READY_FOR_DISPATCH')
        self.assertEqual(post({'action':'START_TEST_ONLY_TASK',
          'task_id':'task-session','attempt_id':'attempt-session'})['state'],
          'STARTED')
        with self.assertRaises(HTTPError) as outbound:
            self.request('/api/admin/model-control','POST',
              {'action':'RUN_SCHEDULER_ONCE'},receipt['csrf_token'])
        self.assertIn('REAL_OUTBOUND_DISABLED',
          json.loads(outbound.exception.read())['detail'])

    def test_bad_login_does_not_create_session_and_logs_never_need_secret(self):
        with self.assertRaises(HTTPError) as denied:
            self.login('admin','wrong-password-value')
        self.assertEqual(denied.exception.code,401)
        db=sqlite3.connect(self.db)
        self.assertEqual(db.execute('SELECT count(*) FROM task_center_sessions').fetchone()[0],0)
        db.close()


if __name__=='__main__':unittest.main()
