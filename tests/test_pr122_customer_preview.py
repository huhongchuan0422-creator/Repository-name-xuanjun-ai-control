"""Isolated real HTTP and signed test-source checks; no production claims."""
import base64
import copy
import hashlib
import hmac
import json
import time
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from tests.test_pr122_customer_http import HttpTests
from tests.test_pr122_customer_center import CustomerTests
from tests.pr122_customer_change_fixture import snapshot,seed,PAGE_SHA
from scripts.pr122_customer_core import canonical,digest,Denied
from scripts.pr122_customer_changes import Changes
from scripts.pr122_customer_change_authority import import_snapshot,load
from scripts.pr122_customer_preview import route,render,served,listing
from scripts.pr122_customer_delivery_source import issue,REQUIRED

class PreviewTests(unittest.TestCase):
    imported=CustomerTests.imported
    def setUp(self):
        CustomerTests.setUp(self);self.path='/preview/consumer/'
        self.body=b'<!doctype html><html><meta name="viewport" content="width=device-width"><title>Customer preview</title><body><h1>Private project</h1><style>h1{color:#123}</style><script>document.documentElement.dataset.preview="ready";</script></body></html>'
        self.sha=digest(self.body);self.revision=1;self.install()
    def install(self,body=None,scope=True):
        body=self.body if body is None else body;self.sha=digest(body)
        e=snapshot(self,revision=self.revision);m=e['payload']['previews'][0]['manifest'];m['pages']=[{'path':self.path,'sha256':self.sha}]
        if scope:m['execution_scope']='TRUSTED_CUSTOMER_FRONTEND'
        entry=e['payload']['previews'][0];entry['manifest_sha256']=digest(canonical(m));entry['blobs']={self.sha:base64.b64encode(body).decode()};e['signature']=hmac.new(self.auth,canonical(e['payload']),hashlib.sha256).hexdigest();import_snapshot(self.c,e,self.auth)
    def test_real_bytes_render_footer_and_exact_csp_hashes(self):
        raw,mime,csp=render(self.c,self.owner,'project-a',digest(self.path.encode()),self.sha)
        self.assertIn(b'data-project-feedback="project-a"',raw);self.assertIn(b'Private project',raw)
        expected=base64.b64encode(hashlib.sha256(b'document.documentElement.dataset.preview="ready";').digest()).decode()
        self.assertIn("'sha256-"+expected+"'",csp);self.assertIn("base-uri 'none'",csp);self.assertNotIn("unsafe-inline",csp);self.assertNotIn("script-src 'self'",csp);self.assertTrue(mime.startswith('text/html'))
    def test_content_approval_cannot_authorize_executable_application(self):
        self.revision=2;self.install(scope=False)
        self.assertEqual(listing(self.c,self.owner,'project-a')['pages'],[])
        with self.assertRaises(Denied):render(self.c,self.owner,'project-a',digest(self.path.encode()),self.sha)
    def test_cross_customer_stale_version_and_revocation(self):
        for uid,sha in ((self.other,self.sha),(self.owner,'f'*64)):
            with self.assertRaises(Denied):render(self.c,uid,'project-a',digest(self.path.encode()),sha)
        self.imported(2,[])
        with self.assertRaises(Denied):listing(self.c,self.owner,'project-a')
    def test_external_resource_and_unregistered_asset_fail_closed(self):
        for src in ('https://external.example/a.js','/assets/not-reviewed.js'):
            self.revision+=1;self.install(('<html><script src="'+src+'"></script></html>').encode())
            with self.assertRaises(Denied):render(self.c,self.owner,'project-a',digest(self.path.encode()),self.sha)
    def test_served_evidence_encrypted_append_only_and_not_browser_or_tls_pass(self):
        raw,_,_=render(self.c,self.owner,'project-a',digest(self.path.encode()),self.sha)
        result=served(self.c,self.owner,'project-a',digest(self.path.encode()),self.sha,raw)
        row=self.c.db.execute('SELECT * FROM preview_serves WHERE id=?',(result['id'],)).fetchone()
        self.assertNotIn(b'Private project',row['payload']);proof=json.loads(self.c.decrypt(row['payload'],row['id']))
        self.assertEqual(proof['render_sha256'],digest(raw));self.assertEqual(proof['browser_acceptance'],'NOT_ESTABLISHED')
        with self.assertRaises(Exception):self.c.db.execute('DELETE FROM preview_serves')
    def publication(self):
        before=self.sha;service=Changes(self.c);r=service.submit(self.owner,'project-a',self.path,before,'调整标题颜色');service.assess(self.reviewer,'project-a',r['id'],1,'IN_SCOPE_SMALL',10,[],[],'仅改变颜色')
        self.revision=2;self.install(self.body.replace(b'#123',b'#456'))
        raw,_,policy=render(self.c,self.owner,'project-a',digest(self.path.encode()),self.sha);receipt=served(self.c,self.owner,'project-a',digest(self.path.encode()),self.sha,raw)
        record=load(self.c)['previews'][0];private=Ed25519PrivateKey.generate();public=private.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
        trust={'source_writer_principal':'writer','keys':{'test-key':{'principal':'isolated-test-runner','public_key_b64':base64.b64encode(public).decode(),'state':'ACTIVE','custody_evidence_sha256':'a'*64,'scope':'PRODUCTION_PRIVATE_PREVIEW','origin':'https://wenwenwenyiyiyi.work'}},'allowed_harness_sha256':['b'*64]}
        payload={'purpose':'PR122_PRIVATE_PREVIEW_TEST_V1','project':'project-a','case':r['id'],'request_sha256':service._request_sha(service._events(self.owner,'project-a',r['id'])),'page':self.path,'before_sha256':before,'after_sha256':self.sha,'manifest_sha256':record['manifest_sha256'],'source_commit':record['source_commit'],'artifact_sha256':record['artifact_sha256'],'render_sha256':digest(raw),'csp_sha256':digest(policy.encode()),'harness_sha256':'b'*64,'checks':{k:'PASS' for k in REQUIRED},'issued_at':self.now,'expires':self.now+300,'summary':'已调整标题颜色','origin':'https://wenwenwenyiyiyi.work','environment':'PRODUCTION_PRIVATE_PREVIEW','tls_verified':True}
        report={'payload':payload,'key_id':'test-key','signature':base64.b64encode(private.sign(canonical(payload))).decode()}
        return r,receipt,report,trust,private
    def test_signed_test_and_real_server_receipt_generate_delivery_without_network(self):
        r,receipt,report,trust,_=self.publication()
        with patch('socket.socket',side_effect=AssertionError('no API')):result=issue(self.c,'project-a',r['id'],receipt['id'],report,trust,self.auth)
        updates=Changes(self.c).page_updates(self.owner,'project-a',self.path,self.sha)['updates'];self.assertEqual(len(updates),1);self.assertEqual(updates[0]['state'],'AWAIT_RETEST');self.assertEqual(result['revision'],3)
        row=self.c.db.execute('SELECT * FROM preview_delivery_proofs').fetchone();self.assertNotIn(b'checks',row['payload'])
        with self.assertRaises(Exception):self.c.db.execute('DELETE FROM preview_delivery_proofs')
    def test_forged_report_author_self_signature_unknown_harness_and_missing_serve(self):
        r,receipt,report,trust,private=self.publication()
        with self.assertRaises(Denied):issue(self.c,'project-a',r['id'],'pv_missing',report,trust,self.auth)
        bad=copy.deepcopy(report);bad['payload']['summary']='篡改'
        with self.assertRaises(Denied):issue(self.c,'project-a',r['id'],receipt['id'],bad,trust,self.auth)
        badtrust=copy.deepcopy(trust);badtrust['keys']['test-key']['principal']='writer'
        with self.assertRaises(Denied):issue(self.c,'project-a',r['id'],receipt['id'],report,badtrust,self.auth)
        badtrust=copy.deepcopy(trust);badtrust['allowed_harness_sha256']=[]
        with self.assertRaises(Denied):issue(self.c,'project-a',r['id'],receipt['id'],report,badtrust,self.auth)
    def test_wrong_deployed_hash_fail_check_and_old_report_rejected(self):
        r,receipt,report,trust,private=self.publication()
        for key,value in (('render_sha256','f'*64),('csp_sha256','f'*64),('request_sha256','f'*64),('expires',self.now-1)):
            bad=copy.deepcopy(report);bad['payload'][key]=value;bad['signature']=base64.b64encode(private.sign(canonical(bad['payload']))).decode()
            with self.assertRaises(Denied):issue(self.c,'project-a',r['id'],receipt['id'],bad,trust,self.auth)
        report['payload']['checks']['mobile']='FAIL';report['signature']=base64.b64encode(private.sign(canonical(report['payload']))).decode()
        with self.assertRaises(Denied):issue(self.c,'project-a',r['id'],receipt['id'],report,trust,self.auth)

    def test_fixture_scope_wrong_origin_and_unverified_tls_cannot_publish(self):
        r,receipt,report,trust,private=self.publication()
        for field,value in (('environment','ISOLATED_FIXTURE'),('origin','http://127.0.0.1'),('tls_verified',False)):
            bad=copy.deepcopy(report);bad['payload'][field]=value;bad['signature']=base64.b64encode(private.sign(canonical(bad['payload']))).decode()
            with self.assertRaises(Denied):issue(self.c,'project-a',r['id'],receipt['id'],bad,trust,self.auth)
        trust['keys']['test-key']['scope']='ISOLATED_FIXTURE'
        with self.assertRaises(Denied):issue(self.c,'project-a',r['id'],receipt['id'],report,trust,self.auth)

    def test_contract_reassignment_cannot_reuse_old_request_for_publication(self):
        r,receipt,report,trust,_=self.publication()
        self.imported(2,[{**self.p,'contract_ref':'contract-b'}])
        with self.assertRaisesRegex(Denied,'REQUEST_CONTRACT_BINDING'):issue(self.c,'project-a',r['id'],receipt['id'],report,trust,self.auth)

class PreviewHTTPTests(HttpTests):
    imported=CustomerTests.imported
    finish=HttpTests.finish
    def setUp(self):
        HttpTests.setUp(self);self.path='/preview/consumer/';self.body=b'<!doctype html><title>Private HTTP preview</title>';self.sha=digest(self.body);self.revision=1;PreviewTests.install(self)
    request=HttpTests.request
    auth_headers=HttpTests.auth_headers
    def test_real_authenticated_http_page_and_no_anonymous_or_range_access(self):
        url=route('project-a',self.path,self.sha).removeprefix('/customer/center/')
        status,h,raw=self.request(url,headers=self.auth_headers());self.assertEqual(status,200);self.assertIn(b'data-project-feedback',raw);self.assertIn('no-store',h['Cache-Control']);self.assertIn("frame-ancestors 'none'",h['Content-Security-Policy'])
        self.assertEqual(self.request(url)[0],403);self.assertEqual(self.request(url,headers={**self.auth_headers(),'Range':'bytes=0-2'})[0],403)
        self.assertEqual(self.request('api/previews/project-a',headers=self.auth_headers())[0],200)
    def member_headers(self):
        user=self.users['member']
        return {'Cookie':__import__('scripts.pr122_customer_http',fromlist=['COOKIE']).COOKIE+'='+user['token'],
                'X-CSRF-Token':user['csrf']}

    def test_http_editor_download_revocation_keeps_session_and_other_project_access(self):
        project_b={**self.p,'id':'project-b','tenant':'tenant-b','customer':'customer-b',
                   'contract_ref':'contract-b','order_ref':'order-b','title':'Other legal project'}
        self.imported(2,[self.p,project_b])
        for pid in ('project-a','project-b'):
            token=self.c.invite(self.owner,pid,'member@example.com','EDITOR')['invitation']
            self.c.accept_invite(self.member,token)

        owner_headers=self.auth_headers()
        save_body={'project':'project-a','item':'license','revision':0,'kind':'DOCUMENT',
                   'content':base64.b64encode(b'%PDF-revocation-http').decode(),'expires':None}
        self.assertEqual(self.request('api/save',save_body,owner_headers)[0],200)
        oid=self.c.db.execute("SELECT id FROM objects WHERE project='project-a'").fetchone()[0]
        download='api/download/project-a/'+oid
        member_headers=self.member_headers()

        self.assertEqual(self.request(download,headers=member_headers)[0],200)
        self.assertEqual(self.request('api/checklist/project-b',headers=member_headers)[0],200)

        self.c.revoke(self.owner,'project-a',self.member)
        self.assertEqual(self.c.session(self.users['member']['token']),self.member)
        self.assertEqual(self.request('api/me',headers=member_headers)[0],200)
        self.assertEqual(self.request(download,headers=member_headers)[0],403)
        self.assertEqual(self.request('api/checklist/project-b',headers=member_headers)[0],200)

    def test_http_owner_preview_revocation_blocks_html_list_and_registered_asset(self):
        project_b={**self.p,'id':'project-b','tenant':'tenant-b','customer':'customer-b',
                   'contract_ref':'contract-b','order_ref':'order-b','title':'Other legal project'}
        self.imported(2,[self.p,project_b])

        # Bind a fresh preview snapshot to the current legal project revision.
        # Include a separately versioned CSS member so HTTP authorization is
        # exercised for a real resource route, not only inline content.
        page='/preview/consumer/'
        asset='/preview/app.css'
        page_body=b'<!doctype html><html><head><link rel="stylesheet" href="/preview/app.css"></head><body>Private preview</body></html>'
        asset_body=b'body{font-family:sans-serif}'
        page_sha=digest(page_body);asset_sha=digest(asset_body)
        e=snapshot(self,revision=2,paths=[page,asset])
        entry=e['payload']['previews'][0]
        manifest=entry['manifest']
        manifest['pages']=[{'path':page,'sha256':page_sha},{'path':asset,'sha256':asset_sha}]
        manifest['execution_scope']='TRUSTED_CUSTOMER_FRONTEND'
        entry['manifest_sha256']=digest(canonical(manifest))
        entry['blobs']={page_sha:base64.b64encode(page_body).decode(),
                        asset_sha:base64.b64encode(asset_body).decode()}
        e['signature']=hmac.new(self.auth,canonical(e['payload']),hashlib.sha256).hexdigest()
        import_snapshot(self.c,e,self.auth)

        headers=self.auth_headers()
        page_url=route('project-a',page,page_sha).removeprefix('/customer/center/')
        asset_url=route('project-a',asset,asset_sha).removeprefix('/customer/center/')
        listing_url='api/previews/project-a'

        self.assertEqual(self.request(page_url,headers=headers)[0],200)
        self.assertEqual(self.request(asset_url,headers=headers)[0],200)
        self.assertEqual(self.request(listing_url,headers=headers)[0],200)
        self.assertEqual(self.request('api/checklist/project-b',headers=headers)[0],200)

        # Full authority snapshot removes project-a but keeps project-b. Owner
        # account session remains valid; all project-a preview surfaces re-check
        # project authorization and fail without weakening preview revision rules.
        self.imported(3,[project_b])
        self.assertEqual(self.c.session(self.users['owner']['token']),self.owner)
        self.assertEqual(self.request('api/me',headers=headers)[0],200)
        self.assertEqual(self.request(page_url,headers=headers)[0],403)
        self.assertEqual(self.request(asset_url,headers=headers)[0],403)
        self.assertEqual(self.request(listing_url,headers=headers)[0],403)
        self.assertEqual(self.request('api/checklist/project-b',headers=headers)[0],200)

    def test_http_password_reset_replaces_cookie_without_changing_private_resource_authority(self):
        # Keep project authorization stable. Rebind preview only to the current
        # legal project revision and preserve the exact object/preview bytes
        # across the password-reset boundary.
        self.imported(2,[self.p])
        page='/preview/consumer/'
        asset='/preview/app.css'
        page_body=b'<!doctype html><html><head><link rel="stylesheet" href="/preview/app.css"></head><body>Reset fixture</body></html>'
        asset_body=b'body{font-family:sans-serif}'
        page_sha=digest(page_body);asset_sha=digest(asset_body)
        e=snapshot(self,revision=2,paths=[page,asset])
        entry=e['payload']['previews'][0]
        manifest=entry['manifest']
        manifest['pages']=[{'path':page,'sha256':page_sha},{'path':asset,'sha256':asset_sha}]
        manifest['execution_scope']='TRUSTED_CUSTOMER_FRONTEND'
        entry['manifest_sha256']=digest(canonical(manifest))
        entry['blobs']={page_sha:base64.b64encode(page_body).decode(),
                        asset_sha:base64.b64encode(asset_body).decode()}
        e['signature']=hmac.new(self.auth,canonical(e['payload']),hashlib.sha256).hexdigest()
        import_snapshot(self.c,e,self.auth)

        old_headers=self.auth_headers()
        save_body={'project':'project-a','item':'license','revision':0,'kind':'DOCUMENT',
                   'content':base64.b64encode(b'%PDF-reset-private-resource').decode(),'expires':None}
        self.assertEqual(self.request('api/save',save_body,old_headers)[0],200)
        oid=self.c.db.execute("SELECT id FROM objects WHERE project='project-a'").fetchone()[0]
        download='api/download/project-a/'+oid
        page_url=route('project-a',page,page_sha).removeprefix('/customer/center/')
        asset_url=route('project-a',asset,asset_sha).removeprefix('/customer/center/')
        listing_url='api/previews/project-a'
        protected=(download,page_url,asset_url,listing_url)

        for path in protected:
            self.assertEqual(self.request(path,headers=old_headers)[0],200)

        # Exercise the real HTTP reset routes. Reset must invalidate the old
        # session cookie but must not change project membership, object bytes,
        # preview authority revision, or registered resource hashes.
        self.assertEqual(self.request('api/request_reset',{'email':'owner@example.com'})[0],200)
        reset_row=self.c.db.execute("SELECT * FROM outbox WHERE kind='RESET' ORDER BY rowid DESC LIMIT 1").fetchone()
        reset_token=json.loads(self.c.decrypt(reset_row['payload'],'outbox:'+reset_row['id']))['token']
        self.assertEqual(self.request('api/reset',{'token':reset_token,'password':'replacement-password-123'})[0],200)
        for path in protected:
            self.assertEqual(self.request(path,headers=old_headers)[0],403)

        status,login_headers,raw=self.request('api/login',{'email':'owner@example.com','password':'replacement-password-123'})
        self.assertEqual(status,200)
        login_body=json.loads(raw)
        cookie=login_headers['Set-Cookie'].split(';',1)[0]
        new_headers={'Cookie':cookie,'X-CSRF-Token':login_body['csrf']}
        self.assertNotEqual(cookie,old_headers['Cookie'])

        # Same exact object and preview URLs become readable again with the new
        # authenticated session. Nothing is regenerated after reset.
        for path in protected:
            self.assertEqual(self.request(path,headers=new_headers)[0],200)
        self.assertEqual(self.c.db.execute("SELECT revision FROM projects WHERE id='project-a'").fetchone()[0],2)
        self.assertEqual(load(self.c)['revision'],2)

    def test_http_delivery_report_queue_requires_reviewer_not_customer(self):
        body={'project':'project-a','case':'change_fixture','serve_id':'pv_fixture','report':{'payload':{},'key_id':'not-enrolled','signature':'invalid'}}
        self.assertEqual(self.request('api/change_delivery_report',body,self.auth_headers())[0],403)
        user=self.users['reviewer'];headers={'Cookie':__import__('scripts.pr122_customer_http',fromlist=['COOKIE']).COOKIE+'='+user['token'],'X-CSRF-Token':user['csrf']}
        self.assertEqual(self.request('api/change_delivery_report',body,headers)[0],200)
        self.assertEqual(self.c.db.execute('SELECT state FROM preview_publication_jobs').fetchone()[0],'QUEUED')
    def test_no_http_publisher_or_report_writer(self):
        for name in ('issue-preview-delivery','import-preview','preview-served'):
            self.assertEqual(self.request('api/'+name,{},self.auth_headers())[0],404)

# Reuse the HTTP fixture without re-running already covered HTTP/core cases.
for _name in HttpTests.__dict__:
    if _name.startswith('test_'):setattr(PreviewHTTPTests,_name,None)
