"""Offline RFC7662 resource tests. No real issuer, login or live grant."""
import io
import json
import unittest
from unittest.mock import patch

from production.cloud_connection.oauth_resource import Introspection, OAuthProjectResource, NoRedirect
from production.cloud_connection.queue import Hold
import test_cloud_connection_private_transfer as transfer

NOW = transfer.NOW
ISSUER = 'https://auth.example.test'
AUD = 'https://resource.example.test/mcp'
TOKEN = 'Bearer opaque-test-token-0001'


class Response(io.BytesIO):
    def getcode(self):
        return 200


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.claims = dict(active=True, iss=ISSUER, aud=AUD, sub='github:332398908',
                           scope='project.files.read connection.status', token_type='Bearer',
                           iat=NOW-10, exp=NOW+100)
        self.calls = []
        self.raw = None
        self.auth = Introspection(ISSUER, ISSUER+'/introspect', 'client', lambda:'private-secret',
            AUD, {'github:332398908': {'recipient':'work-window','projects':['p2']}}, self.network)

    def network(self, request, timeout):
        self.calls.append((request,timeout))
        return Response(self.raw if self.raw is not None else json.dumps(self.claims).encode())

    def check(self):
        return self.auth.authenticate(TOKEN,'project.files.read','p2',NOW)

    def test_verified_subject_maps_from_host_policy(self):
        self.assertEqual(self.check(),'work-window')
        request,timeout=self.calls[0]
        self.assertEqual(request.full_url,ISSUER+'/introspect')
        self.assertEqual(request.method,'POST')
        self.assertEqual(timeout,5)
        self.assertNotIn('opaque',request.full_url)

    def test_no_cache_revocation_immediate(self):
        self.check();self.claims['active']=False
        with self.assertRaises(Hold):self.check()
        self.assertEqual(len(self.calls),2)

    def test_missing_or_invalid_bearer(self):
        for token in ('','Basic xxx',TOKEN+'\n',TOKEN+',other','Bearer short'):
            with self.assertRaises(Hold):self.auth.authenticate(token,'project.files.read','p2',NOW)
        self.assertEqual(self.calls,[])

    def test_inactive_and_invalid_times(self):
        original=dict(self.claims)
        for changes in ({'active':1},{'exp':NOW},{'exp':True},{'iat':NOW+1},
                        {'iat':True},{'nbf':NOW+1},{'nbf':False},{'iss':'https://wrong.test'},
                        {'token_type':'refresh_token'},{'token_type':[]},{'token_type':None}):
            self.claims=dict(original,**changes)
            with self.assertRaises(Hold):self.check()

    def test_wrong_audience_even_if_list_contains_resource(self):
        for value in ('https://wrong.test',[AUD,'https://wrong.test'],None):
            self.claims['aud']=value
            with self.assertRaises(Hold):self.check()
        self.claims['aud']=[AUD];self.assertEqual(self.check(),'work-window')

    def test_scope_and_subject_and_project(self):
        for field,value in [('scope','connection.status'),('scope',['project.files.read']),
                            ('sub','github:95597695'),('sub',332398908)]:
            original=dict(self.claims);self.claims[field]=value
            with self.assertRaises(Hold):self.check()
            self.claims=original
        with self.assertRaises(Hold):self.auth.authenticate(TOKEN,'project.files.read','other',NOW)

    def test_network_failures_redacted(self):
        def fail(*a,**k):raise OSError('private-secret opaque-test-token-0001')
        self.auth.open_url=fail
        with self.assertRaisesRegex(Hold,'^OAUTH_INTROSPECTION_UNAVAILABLE$'):self.check()

    def test_secret_provider_error_redacted(self):
        def fail():raise OSError('private secret path')
        self.auth.secret_provider=fail
        with self.assertRaisesRegex(Hold,'^OAUTH_CLIENT_SECRET_UNAVAILABLE$'):self.check()
        self.assertEqual(self.calls,[])

    def test_malformed_duplicate_and_oversized_response(self):
        for raw in (b'null',b'[]',b'{"active":true,"active":false}',b'x'*16385,b'\xff'):
            self.raw=raw
            with self.assertRaises(Hold):self.check()

    def test_configuration_https_and_endpoint_binding(self):
        for endpoint in ('http://auth.example.test/introspect','https://wrong.test/introspect',
                         ISSUER+'/introspect?token=x', 'https://u:p@auth.example.test/introspect'):
            with self.assertRaises(Hold):
                Introspection(ISSUER,endpoint,'client',lambda:'secret',AUD,{},self.network)

    def test_redirect_refused(self):
        with self.assertRaises(Hold):NoRedirect().redirect_request(None,None,302,'',{},'https://other.test')


class ResourceTests(unittest.TestCase):
    setUp=transfer.PrivateTransferTests.setUp
    tearDown=transfer.PrivateTransferTests.tearDown
    make_catalog=transfer.PrivateTransferTests.make_catalog
    receipt=transfer.PrivateTransferTests.receipt

    def resource(self, recipient='work-window', enabled=True):
        class Auth:
            def authenticate(s,header,scope,project,now):
                if header != TOKEN:raise Hold('OAUTH_BEARER_REQUIRED')
                s.last=(scope,project,now)
                return recipient
        return OAuthProjectResource(self.q.db,{self.catalog.sha:(self.catalog,{'frozen-input':(str(self.src),0)})},Auth(),enabled)

    def args(self):
        return dict(manifest_sha256=self.catalog.sha,request_id='approved-transfer',object_ref='module-object',offset=0)

    def test_default_disabled_before_authentication(self):
        with self.assertRaisesRegex(Hold,'DISABLED'):self.resource(enabled=False).read(TOKEN,self.args(),NOW)

    def test_missing_auth_before_file_read(self):
        with patch('production.cloud_connection.private_transfer.read_object',side_effect=AssertionError('file access')):
            with self.assertRaisesRegex(Hold,'BEARER'):self.resource().read('',self.args(),NOW)

    def test_metadata_cannot_claim_identity(self):
        for key in ('_meta','recipient','authenticated_recipient'):
            args=self.args();args[key]='work-window'
            with self.assertRaisesRegex(Hold,'ARGUMENTS'):self.resource().read(TOKEN,args,NOW)

    def test_authenticated_recipient_still_requires_catalog_and_success_job(self):
        # Existing fixture creates a real SQLite SUCCESS record with synthetic
        # offline approval. This is not a production execution receipt.
        resource=self.resource()
        value=resource.read(TOKEN,self.args(),NOW)
        self.assertTrue(value)
        self.assertEqual(resource.authenticator.last,('project.files.read',self.catalog.value['project'],NOW))
        with self.assertRaises(Hold):self.resource('other-window').read(TOKEN,self.args(),NOW)
        args=self.args();args['request_id']='missing'
        with self.assertRaises(Hold):resource.read(TOKEN,args,NOW)

    def test_unknown_catalog_no_auth_or_file(self):
        args=self.args();args['manifest_sha256']='0'*64
        with self.assertRaisesRegex(Hold,'CATALOG'):self.resource().read(TOKEN,args,NOW)
