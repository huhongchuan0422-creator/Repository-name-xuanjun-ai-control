"""Synthetic files through real HTTP and original encrypted Center storage."""
import base64
import concurrent.futures
import hashlib
import hmac
import http.client
import json
import unittest
from pathlib import Path
from unittest.mock import Mock

import test_community_mini_center_identity as fixtures
from scripts.community_center_operations import CenterOperations
from scripts.community_commerce import Commerce
from scripts.community_mini_http import serve
from scripts.community_project_materials import MAX_DOCUMENT_BYTES, MAX_UPLOAD_BODY
from scripts.pr122_customer_core import canonical, Unavailable


class ProjectMaterialJourney(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.ExistingCenterComposition(); self.fx.setUp()
        self.c = self.fx.center
        self.token = self.fx.token()
        self.import_requirements()
        self.owner = self.c.login('one@example.org', 'FixturePassword123!')
        self.reviewer = self.c.login('two@example.org', 'FixturePassword123!')
        self.compose()
        self.server = serve(self.fx.gateway, commerce=self.commerce)

    def compose(self):
        ops = CenterOperations(self.c, self.fx.stage.api, {'merchant': dict(
            user_id=self.fx.uid1, project='project1', project_roles=['OWNER'],
            principal=self.fx.stage.merchant)})
        self.commerce = Commerce(ops, self.fx.identity)
        self.fx.gateway.commerce = self.commerce

    def import_requirements(self):
        _, _, details = self.c.project(self.fx.uid1, 'project1')
        material = dict(id='document1', title='Synthetic document', purpose='fixture',
                        required=True, identity_requirements=[], official_url='https://example.org',
                        instructions='Synthetic files only', minimum_permissions=[], fees=[],
                        verified_at=self.c.now(), formats=['application/pdf', 'image/png', 'image/jpeg'],
                        valid_until=self.c.now()+3600, submission_type='PRIVATE_DOCUMENT', category='MATERIAL')
        reference = dict(material, id='reference1', required=False, formats=[], submission_type='SECRETREF')
        project = dict(details, requirements=[material, reference], reviewer_emails=['two@example.org'])
        payload = dict(revision=2, expires=self.c.now()+3600, projects=[project])
        key = b'a'*32
        self.c.import_authority(dict(payload=payload, signature=hmac.new(key, canonical(payload), hashlib.sha256).hexdigest()), key)

    def tearDown(self):
        self.server.server_close(); self.fx.tearDown()

    def body(self, raw=b'%PDF-1.4\nSynthetic fixture\n', **changes):
        return dict(dict(item='document1', revision=0, filename='fixture.pdf',
                         content_base64=base64.b64encode(raw).decode()), **changes)

    def upload(self, body=None):
        return self.commerce.project_document_upload(self.token, 'shop1', self.body() if body is None else body)

    def review(self, operation='checklist', params=None, web=None, workspace='project1'):
        web = self.reviewer if web is None else web
        return self.commerce.project_material_review(web['token'], web['csrf'],
            dict(workspace=workspace, operation=operation, params=params or {}))

    def http(self, path, body, headers=None):
        raw = json.dumps(body).encode()
        def request():
            conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
            try:
                conn.request('POST', path, raw, {'Content-Type': 'application/json', **(headers or {})})
                response = conn.getresponse(); return response.status, json.loads(response.read())
            finally: conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(request); self.server.handle_request(); return future.result()

    def mini_headers(self):
        return {'X-Community-Session': self.token, 'X-Community-Scene': 'shop1'}

    def web_headers(self, web=None):
        web = self.reviewer if web is None else web
        return {'Cookie': '__Host-xj_customer='+web['token'], 'X-CSRF-Token': web['csrf']}

    def transition_http(self, action, revision):
        return self.http('/community/commerce', dict(workspace='project1', operation='project_review',
            params=dict(item='document1', revision=revision, action=action, reason='Synthetic review')),
            self.web_headers())

    def test_http_upload_correction_resubmit_independent_acceptance_and_download(self):
        self.c.scanner = Mock(return_value=True)
        tables = self.c.db.execute('SELECT name FROM sqlite_master ORDER BY name').fetchall()
        code, saved = self.http('/mini/project-materials', self.body(), self.mini_headers())
        self.assertEqual(code, 200); self.assertFalse(saved['payment_enabled'])
        self.assertEqual(saved['result']['state'], 'PARTIAL')
        self.c.scanner.assert_called_once_with(b'%PDF-1.4\nSynthetic fixture\n')
        def submit(revision):
            return self.http('/mini/api', dict(scene='shop1', operation='commerce.project_submit',
                params=dict(item='document1', revision=revision)), {'X-Community-Session': self.token})
        self.assertEqual(submit(1)[1]['result']['state'], 'SUBMITTED')
        self.assertEqual(self.transition_http('begin_review', 2)[1]['result']['state'], 'IN_REVIEW')
        self.assertEqual(self.transition_http('request_changes', 3)[1]['result']['state'], 'NEEDS_CORRECTION')
        self.assertEqual(self.http('/mini/project-materials', self.body(revision=4), self.mini_headers())[0], 200)
        self.assertEqual(submit(5)[0], 200)
        self.assertEqual(self.transition_http('begin_review', 6)[0], 200)
        self.assertEqual(self.transition_http('approve', 7)[1]['result']['state'], 'ACCEPTED')
        code, response = self.http('/community/project-materials', dict(workspace='project1', operation='checklist', params={}), self.web_headers())
        self.assertEqual(code, 200); self.assertEqual(response['result']['overall'], 'ACCEPTED')
        oid = response['result']['items'][0]['versions'][0]['details']['object_id']
        code, downloaded = self.http('/community/project-materials', dict(workspace='project1', operation='download', params={'object_id': oid}), self.web_headers())
        self.assertEqual(code, 200)
        self.assertEqual(base64.b64decode(downloaded['result']['content_base64']), b'%PDF-1.4\nSynthetic fixture\n')
        self.assertEqual(downloaded['result']['filename'], oid+'.pdf')
        self.assertEqual(tables, self.c.db.execute('SELECT name FROM sqlite_master ORDER BY name').fetchall())
        self.assertEqual(self.transition_http('approve', 7)[0], 400)
        self.assertNotIn(b'Synthetic fixture', (self.c.objects/oid).read_bytes())

    def test_scanner_absent_unknown_and_rejected_never_save(self):
        with self.assertRaisesRegex(Unavailable, 'SCANNER_PENDING'): self.upload()
        self.assertEqual(self.http('/mini/project-materials', self.body(), self.mini_headers())[0], 503)
        for outcome in (False, None, 'CLEAN', 1):
            self.c.scanner = lambda raw: outcome
            with self.assertRaisesRegex(PermissionError, 'QUARANTINED_SCAN_NOT_CLEAN'): self.upload()
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM objects').fetchone()[0], 0)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM versions').fetchone()[0], 0)

    def test_strict_fields_filename_mime_base64_revision_and_type(self):
        self.c.scanner = Mock(return_value=True)
        changes = [dict(revision=True), dict(revision=-1), dict(filename='../secret.pdf'),
                   dict(filename='x\\secret.pdf'), dict(filename='x:secret.pdf'), dict(filename=' x.pdf'),
                   dict(filename='x\u202e.pdf'), dict(filename='x.png'), dict(filename='x.pdf.exe'),
                   dict(content_base64='JVBERi0=\n'), dict(content_base64='!!!!'), dict(content_base64=''),
                   dict(content_base64='JVBERi1='), dict(mime='application/pdf'), dict(scan='CLEAN'),
                   dict(project='other'), dict(object_id='o_fake'), dict(item='reference1')]
        for change in changes:
            with self.subTest(change=change), self.assertRaises((ValueError, PermissionError)):
                self.upload(self.body(**change))
        self.c.scanner.assert_not_called()
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM objects').fetchone()[0], 0)

    def test_exact_size_limit_and_all_supported_document_formats(self):
        self.c.scanner = lambda raw: True
        raw = b'%PDF-'+b'x'*(MAX_DOCUMENT_BYTES-5)
        self.assertEqual(self.upload(self.body(raw))['revision'], 1)
        with self.assertRaises(ValueError): self.upload(self.body(raw+b'x', revision=1))
        for raw, name, revision in [(b'\x89PNG\r\n\x1a\nfixture', 'image.PNG', 1), (b'\xff\xd8\xfffixture', 'image.jpeg', 2)]:
            self.assertEqual(self.upload(self.body(raw, filename=name, revision=revision))['revision'], revision+1)

    def test_document_state_and_permissions_are_original_center_enforced(self):
        self.c.scanner = lambda raw: True
        self.upload()
        with self.assertRaises(ValueError): self.upload()
        self.commerce.consumer(self.token, 'shop1', 'project_submit', dict(item='document1', revision=1))
        with self.assertRaises(ValueError): self.upload(self.body(revision=2))
        with self.assertRaises(PermissionError): self.review(web=self.owner)
        with self.assertRaises(PermissionError): self.review(workspace='otherproject')
        with self.assertRaises(ValueError): self.review(web=dict(self.reviewer, csrf=''))
        with self.assertRaises(PermissionError): self.review(web=dict(self.reviewer, csrf='wrong'))
        with self.assertRaises(PermissionError): self.review('download', {'object_id':'o_'+'f'*32})
        self.c.db.execute('UPDATE members SET active=0 WHERE project=? AND user_id=?', ('project1',self.fx.uid2))
        with self.assertRaises(PermissionError): self.review()
        self.c.db.execute('UPDATE members SET active=0 WHERE project=? AND user_id=?', ('project1',self.fx.uid1))
        with self.assertRaises(PermissionError): self.upload(self.body(revision=2))

    def test_http_large_body_authenticated_before_read_and_other_api_stays_small(self):
        # Send headers only. A timely rejection proves no private body was awaited.
        def request():
            conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
            try:
                conn.putrequest('POST', '/mini/project-materials')
                conn.putheader('Content-Type', 'application/json')
                conn.putheader('Content-Length', str(MAX_UPLOAD_BODY))
                conn.endheaders()
                response = conn.getresponse(); response.read(); return response.status
            finally: conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(request); self.server.handle_request(); self.assertIn(future.result(), (400,403))
        self.assertEqual(self.http('/mini/api', {'padding':'x'*20000}, self.mini_headers())[0], 400)
        self.assertEqual(self.http('/mini/project-materials', self.body(), dict(self.mini_headers(),Cookie='x=y'))[0],403)
        self.assertEqual(self.http('/community/project-materials', dict(workspace='project1',operation='checklist',params={}), self.mini_headers())[0],403)

    def test_original_objects_survive_database_reopen_and_no_scanner_is_created(self):
        self.c.scanner = lambda raw: True; self.upload()
        oid = self.review()['items'][0]['versions'][0]['details']['object_id']
        self.server.server_close(); self.fx.reopen(); self.c = self.fx.center; self.compose()
        self.server = serve(self.fx.gateway, commerce=self.commerce)
        self.assertEqual(base64.b64decode(self.review('download', {'object_id':oid})['content_base64']), b'%PDF-1.4\nSynthetic fixture\n')
        with self.assertRaisesRegex(Unavailable,'SCANNER_PENDING'): self.upload(self.body(revision=1))

    def test_cross_project_download_tenant_rebinding_and_author_review_denied(self):
        self.c.scanner = lambda raw: True
        self.upload()
        _, _, original = self.c.project(self.fx.uid1, 'project1')
        other = dict(original, id='project2', title='Other synthetic project')
        payload = dict(revision=3, expires=self.c.now()+3600, projects=[original, other])
        key = b'a'*32
        self.c.import_authority(dict(payload=payload, signature=hmac.new(key,canonical(payload),hashlib.sha256).hexdigest()),key)
        self.c.save(self.fx.uid1, 'project2', 'document1', 0, 'DOCUMENT', b'%PDF-other')
        oid = self.c.checklist(self.fx.uid2,'project2')['items'][0]['versions'][0]['details']['object_id']
        with self.assertRaises(PermissionError): self.review('download', {'object_id':oid})
        identity = self.commerce.runtime.bindings[self.fx.stage.customer]
        original_tenant = identity['tenant_id']; identity['tenant_id']='foreign'
        try:
            with self.assertRaises(PermissionError): self.upload(self.body(revision=1))
        finally: identity['tenant_id']=original_tenant
        self.commerce.consumer(self.token,'shop1','project_submit',dict(item='document1',revision=1))
        # Even an independently changed role cannot make the material author
        # its own reviewer: the unchanged Core checks original SAVE actor.
        self.c.db.execute("UPDATE members SET role='REVIEWER' WHERE project='project1' AND user_id=?",(self.fx.uid1,))
        with self.assertRaisesRegex(PermissionError,'INDEPENDENT_REVIEW_REQUIRED'):
            self.commerce.dispatch(self.owner['token'],self.owner['csrf'],dict(
                workspace='project1',operation='project_review',
                params=dict(item='document1',revision=2,action='begin_review',reason='')))

    def test_http_full_document_size_and_revocation_during_body_parsing(self):
        self.c.scanner = lambda raw: True
        code, reply = self.http('/mini/project-materials',
            self.body(b'%PDF-'+b'x'*(MAX_DOCUMENT_BYTES-5)), self.mini_headers())
        self.assertEqual(code,200); self.assertEqual(reply['result']['revision'],1)
        # The pre-body authorization is not a cache of permission for the save.
        original = self.commerce.project_document_authorize
        def authorize_then_revoke(token, scene):
            result=original(token,scene)
            self.c.db.execute("UPDATE members SET active=0 WHERE project='project1' AND user_id=?",(self.fx.uid1,))
            return result
        self.commerce.project_document_authorize=authorize_then_revoke
        self.assertEqual(self.http('/mini/project-materials', self.body(revision=1), self.mini_headers())[0],403)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM objects').fetchone()[0],1)

    def test_quarantined_and_tampered_objects_cannot_be_downloaded(self):
        self.c.scanner=lambda raw:True; self.upload()
        oid=self.review()['items'][0]['versions'][0]['details']['object_id']
        self.c.db.execute("UPDATE objects SET scan='UNKNOWN' WHERE id=?",(oid,))
        with self.assertRaisesRegex(PermissionError,'QUARANTINED'):self.review('download',{'object_id':oid})
        self.c.db.execute("UPDATE objects SET scan='CLEAN',sha=? WHERE id=?",('0'*64,oid))
        with self.assertRaisesRegex(PermissionError,'OBJECT_INTEGRITY'):self.review('download',{'object_id':oid})

    def test_original_core_source_pin_is_unchanged(self):
        root=Path(__file__).resolve().parents[1]/'scripts'
        expected={'pr122_customer_core.py':'f9a736fa954bcc3fbdf2eea317bb0b71559864126c940ac6738a4bc9e4a87bd4',
                  'pr122_customer_source.py':'3e8d531ede69577b72b6ee9089fdc8f481b2f91578f19e0e44d1841c168f3471',
                  'pr122_customer_runtime.py':'3a483ed81eb595309665c3d2b5746e56a50016fb246617000eb326dc5ff2b959'}
        for name, sha in expected.items(): self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),sha)


if __name__=='__main__': unittest.main()
