from __future__ import print_function

import http.cookiejar
import http.client
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest import mock
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
from task_center_test_identity_cli import main as identity_cli_main
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
          'roles':['TASK_CENTER_VIEWER'],'enabled':True},
          'developer':{'password_hash':password_hash('fixture-developer-only'),
          'tenant_id':'tenant-session','principal_id':'developer-test',
          'roles':['TASK_EXECUTOR'],'enabled':True},
          'qa':{'password_hash':password_hash('fixture-qa-reviewer'),
          'tenant_id':'tenant-session','principal_id':'qa-test',
          'roles':['TASK_REVIEWER'],'enabled':True},
          'security':{'password_hash':password_hash('fixture-security-review'),
          'tenant_id':'tenant-session','principal_id':'security-test',
          'roles':['TASK_REVIEWER'],'enabled':True},
          'acceptor':{'password_hash':password_hash('fixture-acceptor-only'),
          'tenant_id':'tenant-session','principal_id':'acceptor-test',
          'roles':['TASK_ACCEPTOR'],'enabled':True}}
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

    def actor(self,user,password):
        jar=http.cookiejar.CookieJar();client=build_opener(HTTPCookieProcessor(jar))
        request=Request(self.base+'/api/session/login',method='POST',
          data=json.dumps({'username':user,'password':password}).encode(),
          headers={'Content-Type':'application/json'})
        receipt=json.loads(client.open(request).read().decode())
        return client,receipt['csrf_token']

    def actor_post(self,client,csrf,value,expected_status=None):
        request=Request(self.base+'/api/admin/model-control',method='POST',
          data=json.dumps(value).encode(),headers={'Content-Type':'application/json',
          'X-CSRF-Token':csrf})
        if expected_status:
            with self.assertRaises(HTTPError) as caught:client.open(request)
            self.assertEqual(caught.exception.code,expected_status)
            return json.loads(caught.exception.read().decode())
        try:return json.loads(client.open(request).read().decode())
        except HTTPError as error:
            self.fail('unexpected HTTP %s: %s'%(error.code,
              error.read().decode('utf-8')))


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
        with self.assertRaises(HTTPError) as twin_denied:
            self.request('/api/admin/digital-twin')
        self.assertEqual(twin_denied.exception.code,403)
        with self.assertRaises(HTTPError) as denied_post:
            self.request('/api/admin/model-control','POST',
              {'action':'RECONCILE_CODEX_RESTART'},receipt['csrf_token'])
        self.assertEqual(denied_post.exception.code,403)

    def test_admin_session_can_read_digital_twin_without_action_surface(self):
        self.login()
        value=json.loads(self.request('/api/admin/digital-twin').read().decode())
        self.assertEqual(value['tenant_id'],'tenant-session')
        self.assertEqual(value['permissions']['read_role'],'TASK_CENTER_ADMIN')
        self.assertEqual(value['permissions']['mutation'],'NONE')
        self.assertFalse(value['event_contract']['ai_may_confirm'])

    def test_admin_page_uses_session_and_canonical_asset_query_contract(self):
        receipt=self.login()
        html=self.request('/admin.html').read().decode('utf-8')
        js=self.request('/admin.js').read().decode('utf-8')
        self.assertNotIn('adminToken',html);self.assertNotIn('actorToken',html)
        self.assertIn('QUERY_CANONICAL_ASSET',js)
        self.assertNotIn("source_kind:'REGISTRY'",js)
        self.assertIn("split(/\\r?\\n/)",js)
        self.assertNotIn("items:[{id:el('checklistItem')",js)
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

    def test_non_admin_roles_complete_submit_rework_dual_review_and_accept(self):
        admin=self.login();admin_client=self.client
        def admin_post(value):return self.actor_post(admin_client,
          admin['csrf_token'],value)
        task={'project_id':'project-roles','task_id':'task-roles',
          'board_id':'research-development','delivery_stage':'implementation',
          'feature_unit':'role-http-journey','goal':'role separated delivery',
          'scope':['WRITE_SOURCE'],'asset_version':'asset-role-v1',
          'deliverables':['source','logs'],'acceptance':['tests','security'],
          'dependencies':[],'priority':70,'owner':'developer-test'}
        admin_post({'action':'CREATE_PROJECT_TASK','task':task})
        admin_post({'action':'QUERY_CANONICAL_ASSET','task_id':'task-roles',
          'query_id':'query-roles','source_version':'registry-role-v1',
          'asset_key':'missing-role-asset'})
        admin_post({'action':'RECORD_DISPATCH_PREFLIGHT','task_id':'task-roles',
          'asset_version':'asset-role-v1','query_ids':['query-roles'],
          'outcome':'NOT_FOUND','reuse_reason':'verified fixture absence'})
        admin_post({'action':'UPSERT_PROVIDER','config':{'provider_id':'fixture-role',
          'display_name':'Role Fixture','adapter_type':'openai-compatible',
          'base_url':'http://127.0.0.1:9','enabled':True,
          'price_state':'KNOWN_FREE','rate_limit_per_min':10,
          'concurrency_limit':1,'timeout_seconds':1,'retry_limit':0}})
        admin_post({'action':'UPSERT_MODEL','config':{'provider_id':'fixture-role',
          'model_id':'fixture-role-model','capabilities':['code'],'enabled':True,
          'price_state':'KNOWN_FREE','input_unit_cost':0,
          'output_unit_cost':0}})
        admin_post({'action':'SET_QUOTA_STATUS','provider_id':'fixture-role',
          'quota_state':'AVAILABLE','quota_source':'TEST_ONLY_INCLUDED_FIXTURE',
          'verified_at':time.time(),'unavailable_reason':None})
        db=sqlite3.connect(self.db)
        db.execute('''INSERT INTO model_evaluations VALUES
          (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',('tenant-session','eval-role',
          'fixture-role','fixture-role-model','fixture-suite',1.0,1,1,1,0,0,
          'QUALIFIED','{}',time.time(),'KNOWN','KNOWN'))
        db.commit();db.close()
        roles=(('executor','EXECUTOR',True,'developer-test',None),
          ('qa','REVIEWER',False,'qa-test','QA'),
          ('security','REVIEWER',False,'security-test','SECURITY'),
          ('acceptor','ACCEPTOR',False,'acceptor-test',None))
        for role,phase,writer,principal,kind in roles:
            admin_post({'action':'CREATE_ROLE','config':{'role_id':role,
              'version':'v1','phase':phase,'capabilities':['code'],
              'writer_allowed':writer,'enabled':True,'review_kind':kind}})
        developer,dev_csrf=self.actor('developer','fixture-developer-only')
        self.assertEqual(self.actor_post(developer,dev_csrf,{
          'action':'START_TEST_ONLY_TASK','task_id':'task-roles',
          'attempt_id':'attempt-roles'})['state'],'STARTED')
        for role,_phase,_writer,principal,_kind in roles:
            admin_post({'action':'ASSIGN_ROLE','task_id':'task-roles',
              'role_id':role,'role_version':'v1','principal_id':principal,
              'allow_paid':False})
        qa,qa_csrf=self.actor('qa','fixture-qa-reviewer')
        security,security_csrf=self.actor('security','fixture-security-review')
        acceptor,accept_csrf=self.actor('acceptor','fixture-acceptor-only')
        self.assertEqual(self.actor_post(developer,dev_csrf,{
          'action':'REVIEW_CANDIDATE','candidate_id':'none','reviewer':
          'developer-test','findings':[],'passed':True},403)['error'],'ROLE_REQUIRED')
        self.assertEqual(self.actor_post(qa,qa_csrf,{'action':'UPSERT_PROVIDER',
          'config':{}},403)['error'],'ADMIN_REQUIRED')
        missing=self.actor_post(self.client,admin['csrf_token'],{
          'action':'REGISTER_CHECKLIST',
          'task_id':'task-roles','items':[{'id':'tests','required':True,
          'result':'PASS','evidence':'tests.log'}]},400)
        self.assertIn('ACCEPTANCE_COVERAGE_MISMATCH',missing['detail'])
        failed=self.actor_post(self.client,admin['csrf_token'],{
          'action':'REGISTER_CHECKLIST',
          'task_id':'task-roles','items':[{'id':'tests','required':True,
          'result':'PASS','evidence':'tests.log'},{'id':'security','required':True,
          'result':'FAIL','evidence':'security.log'}]},400)
        self.assertIn('REQUIRED_CHECK_EVIDENCE_REQUIRED',failed['detail'])
        checklist=self.actor_post(self.client,admin['csrf_token'],{
          'action':'REGISTER_CHECKLIST','task_id':'task-roles','items':[
          {'id':'tests','required':True,'result':'PASS','evidence':'tests.log'},
          {'id':'security','required':True,'result':'PASS',
           'evidence':'security.log'}]})['content_sha256']
        first=self.actor_post(developer,dev_csrf,{'action':'SUBMIT_CANDIDATE',
          'task_id':'task-roles','artifact_sha256':'1'*64,
          'checklist_sha256':checklist,'submitted_by':'developer-test'})
        self.assertEqual(self.actor_post(qa,qa_csrf,{'action':'REVIEW_CANDIDATE',
          'candidate_id':first['candidate_id'],'reviewer':'qa-test',
          'review_kind':'QA','findings':[{'id':'DEFECT-ROLE'}],
          'passed':False})['state'],'CHANGES_REQUESTED')
        revised=self.actor_post(developer,dev_csrf,{'action':'SUBMIT_CANDIDATE',
          'task_id':'task-roles','artifact_sha256':'2'*64,
          'checklist_sha256':checklist,'submitted_by':'developer-test'})
        self.assertEqual(self.actor_post(qa,qa_csrf,{'action':'REVIEW_CANDIDATE',
          'candidate_id':revised['candidate_id'],'reviewer':'qa-test',
          'review_kind':'QA','findings':[],'passed':True})['state'],'QA_PASSED')
        self.assertEqual(self.actor_post(security,security_csrf,{
          'action':'REVIEW_CANDIDATE','candidate_id':revised['candidate_id'],
          'reviewer':'security-test','review_kind':'SECURITY','findings':[],
          'passed':True})['state'],'REVIEW_PASSED')
        accepted=self.actor_post(acceptor,accept_csrf,{
          'action':'ACCEPT_CANDIDATE','candidate_id':revised['candidate_id'],
          'acceptor':'acceptor-test'})
        self.assertEqual(accepted['canonical_task_state'],'SUCCESS')

    def test_bad_login_does_not_create_session_and_logs_never_need_secret(self):
        with self.assertRaises(HTTPError) as denied:
            self.login('admin','wrong-password-value')
        self.assertEqual(denied.exception.code,401)
        db=sqlite3.connect(self.db)
        self.assertEqual(db.execute('SELECT count(*) FROM task_center_sessions').fetchone()[0],0)
        db.close()

    def test_identity_cli_appends_distinct_role_subjects_without_overwrite(self):
        target=os.path.join(self.root,'prepared-identities.json')
        base=['--output',target,'--tenant','tenant-session']
        with mock.patch('getpass.getpass',side_effect=['fixture-one-password',
                                                       'fixture-one-password']):
            self.assertEqual(identity_cli_main(base+['--username','executor-cli',
              '--principal','executor-cli','--roles','TASK_EXECUTOR']),0)
        with mock.patch('getpass.getpass',side_effect=['fixture-two-password',
                                                       'fixture-two-password']):
            self.assertEqual(identity_cli_main(base+['--append','--username','qa-cli',
              '--principal','qa-cli','--roles','TASK_REVIEWER']),0)
        with open(target) as stream:prepared=json.load(stream)
        self.assertEqual(set(prepared['users']),{'executor-cli','qa-cli'})
        self.assertEqual(os.stat(target).st_mode & 0o777,0o600)


class ExternalHttpsContractTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.mkdtemp();self.db=os.path.join(self.root,'state.sqlite3')
        supervisor=Supervisor(self.db);authority=TestTenantAuthority(KEY)
        GatewayKernel(supervisor,authority).register_graph(
          authority.issue('tenant-session','seed'),demo_graph('tenant-session'))
        supervisor.close();self.identity_path=os.path.join(self.root,'identities.json')
        with open(self.identity_path,'w') as stream:
            json.dump({'users':{'admin':{'password_hash':password_hash('fixture-password-only'),
              'tenant_id':'tenant-session','principal_id':'owner-test',
              'roles':['TASK_CENTER_ADMIN'],'enabled':True}}},stream)
        os.chmod(self.identity_path,0o600)
        def connect():
            db=sqlite3.connect(self.db);db.row_factory=sqlite3.Row;return db
        self.sessions=SessionStore(connect,'tenant-session',ttl_seconds=600)
        self.server=make_server(self.db,KEY,'tenant-session','viewer',port=0,
          model_master_key=Fernet.generate_key(),
          identity_provider=FileTestIdentityProvider(self.identity_path),
          session_store=self.sessions,outbound_enabled=False,
          external_origin='https://uk.wenwenwenyiyiyi.work',
          base_path='/task-center-test/')
        self.thread=threading.Thread(target=self.server.serve_forever)
        self.thread.daemon=True;self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
        shutil.rmtree(self.root)

    def raw(self,method,path,body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        supplied={'Host':'uk.wenwenwenyiyiyi.work'};supplied.update(headers or {})
        connection.request(method,path,body=body,headers=supplied)
        response=connection.getresponse();data=response.read()
        result=(response.status,response.getheaders(),data);connection.close();return result

    def test_external_base_path_host_origin_cookie_and_redirect_contract(self):
        status,headers,_=self.raw('GET','/task-center-test/admin.html')
        self.assertEqual(status,302);self.assertEqual(dict(headers)['Location'],'/task-center-test/login.html')
        self.assertEqual(self.raw('GET','/admin.html')[0],404)
        self.assertEqual(self.raw('GET','/task-center-test/login.html',headers={
          'Host':'evil.example','X-Forwarded-Host':'uk.wenwenwenyiyiyi.work',
          'X-Forwarded-Proto':'https'})[0],421)
        payload=json.dumps({'username':'admin','password':'fixture-password-only'})
        self.assertEqual(self.raw('POST','/task-center-test/api/session/login',payload,
          {'Content-Type':'application/json'})[0],403)
        self.assertEqual(self.raw('POST','/task-center-test/api/session/login',payload,
          {'Content-Type':'application/json','Origin':'https://evil.example'})[0],403)
        status,headers,body=self.raw('POST','/task-center-test/api/session/login',payload,
          {'Content-Type':'application/json','Origin':'https://uk.wenwenwenyiyiyi.work'})
        self.assertEqual(status,200);receipt=json.loads(body.decode())
        cookies=[value for name,value in headers if name.lower()=='set-cookie']
        self.assertEqual(len(cookies),2)
        self.assertTrue(all('Path=/task-center-test/' in value and 'Secure' in value
                            and 'SameSite=Strict' in value for value in cookies))
        self.assertIn('HttpOnly',next(x for x in cookies if x.startswith('xuanjun_task_center_session=')))
        cookie='; '.join(x.split(';',1)[0] for x in cookies)
        self.assertEqual(self.raw('GET','/task-center-test/api/session',headers={'Cookie':cookie})[0],200)
        status,headers,_=self.raw('POST','/task-center-test/api/session/logout','{}',{
          'Content-Type':'application/json','Origin':'https://uk.wenwenwenyiyiyi.work',
          'Cookie':cookie,'X-CSRF-Token':receipt['csrf_token']})
        self.assertEqual(status,200)
        cleared=[value for name,value in headers if name.lower()=='set-cookie']
        self.assertTrue(all('Path=/task-center-test/' in value and 'Secure' in value
                            and 'Max-Age=0' in value for value in cleared))

    def test_external_assets_are_base_relative_and_configuration_is_strict(self):
        for path in ('/task-center-test/app.js','/task-center-test/admin.js',
                     '/task-center-test/login.js','/task-center-test/login.html',
                     '/task-center-test/oauth-callback.html'):
            status,_,body=self.raw('GET',path);self.assertEqual(status,200)
            self.assertNotIn(b"fetch('/api/",body);self.assertNotIn(b'href="/admin.html"',body)
        with self.assertRaisesRegex(ValueError,'HTTPS_EXTERNAL_ORIGIN_REQUIRED'):
            make_server(self.db,KEY,'tenant-session','viewer',port=0,
              external_origin='http://uk.wenwenwenyiyiyi.work',base_path='/task-center-test/')
        with self.assertRaisesRegex(ValueError,'VALID_BASE_PATH_REQUIRED'):
            make_server(self.db,KEY,'tenant-session','viewer',port=0,
              external_origin='https://uk.wenwenwenyiyiyi.work',base_path='/../bad/')


if __name__=='__main__':unittest.main()
