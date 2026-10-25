from __future__ import print_function

import json
import os
import shutil
import socketserver
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.parse import parse_qs

from cryptography.fernet import Fernet

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
import sys;sys.path.insert(0,os.path.join(ROOT,'scripts'))
from connection_management import ConnectionManager
from reusable_task_gateway import GatewayKernel,TestTenantAuthority
from task_supervisor import Supervisor

KEY=b'0123456789abcdef0123456789abcdef'


class ThreadServer(socketserver.ThreadingMixIn,HTTPServer):daemon_threads=True
class OAuthHandler(BaseHTTPRequestHandler):
    calls=[]
    def log_message(self,*args):pass
    def do_POST(self):
        n=int(self.headers.get('Content-Length','0'));form=parse_qs(
          self.rfile.read(n).decode());self.calls.append(form)
        if form.get('grant_type')==['authorization_code']:
            value={'access_token':'access-token-one','refresh_token':'refresh-one',
              'token_type':'Bearer','expires_in':60,'scope':'models.run tools.read'}
        else:value={'access_token':'access-token-two','refresh_token':'refresh-two',
          'token_type':'Bearer','expires_in':120,'scope':'models.run tools.read'}
        raw=json.dumps(value).encode();self.send_response(200)
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)


class ConnectionManagementTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.mkdtemp();self.db=os.path.join(self.root,'state.sqlite3')
        self.supervisor=Supervisor(self.db);self.authority=TestTenantAuthority(KEY)
        self.gateway=GatewayKernel(self.supervisor,self.authority)
        self.context=self.authority.issue('tenant-a','admin:owner')
        self.master=Fernet.generate_key();self.manager=ConnectionManager(
          self.gateway,self.context,self.master,clock=lambda:1000)
        self.server=ThreadServer(('127.0.0.1',0),OAuthHandler)
        self.thread=threading.Thread(target=self.server.serve_forever)
        self.thread.daemon=True;self.thread.start();OAuthHandler.calls=[]
        self.base='http://127.0.0.1:%d'%self.server.server_port

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
        self.supervisor.close();shutil.rmtree(self.root)

    def oauth_config(self,cid='oauth'):
        return {'connection_id':cid,'provider_id':'fixture','purpose':'MODEL_INFERENCE',
          'auth_type':'OAUTH2_AUTH_CODE_PKCE','destination_origin':self.base,
          'issuer':self.base,'authorization_endpoint':self.base+'/authorize',
          'token_endpoint':self.base+'/token','revocation_endpoint':self.base+'/revoke',
          'redirect_uri':self.base+'/callback','client_id':'test-client',
          'scopes':['models.run','tools.read'],'supports_refresh':True}

    def api_config(self,cid='key',origin=None):
        return {'connection_id':cid,'provider_id':'fixture','purpose':'MODEL_INFERENCE',
          'auth_type':'API_KEY','destination_origin':origin or self.base,'issuer':None,
          'authorization_endpoint':None,'token_endpoint':None,
          'revocation_endpoint':None,'redirect_uri':None,'client_id':None,
          'scopes':[],'supports_refresh':False}

    def test_api_key_is_encrypted_masked_and_destination_bound(self):
        self.manager.upsert(self.api_config(),credential='api-key-123456')
        with open(self.db,'rb') as stream:raw=stream.read()
        self.assertNotIn(b'api-key-123456',raw)
        projected=json.dumps(self.manager.projection(),ensure_ascii=False)
        self.assertNotIn('api-key-123456',projected);self.assertIn('••••3456',projected)
        secret,version=self.manager.credential('key',self.base,'MODEL_INFERENCE')
        self.assertEqual((secret,version),('api-key-123456',1))
        other='http://127.0.0.1:%d'%(self.server.server_port+1)
        changed=self.manager.upsert(self.api_config(origin=other),credential=None)
        self.assertEqual(changed['status'],'REAUTH_REQUIRED')
        with self.assertRaisesRegex(ValueError,'ACTIVE_CONNECTION'):
            self.manager.credential('key',other,'MODEL_INFERENCE')
        config=self.api_config('other-purpose');config['purpose']='MCP_TOOL'
        self.manager.upsert(config,
          credential='api-key-purpose')
        with self.assertRaisesRegex(ValueError,'PURPOSE_MISMATCH'):
            self.manager.credential('other-purpose',self.base,'MODEL_INFERENCE')

    def test_unrecognized_connection_purpose_is_rejected(self):
        config=self.api_config('bad-purpose');config['purpose']='ARBITRARY_CHANNEL'
        with self.assertRaisesRegex(ValueError,'CONNECTION_PURPOSE_REQUIRED'):
            self.manager.upsert(config,credential='api-key-purpose')

    def test_oauth_pkce_success_replay_refresh_and_revoke(self):
        self.manager.upsert(self.oauth_config())
        flow=self.manager.begin_oauth('oauth')
        self.assertIn('code_challenge_method=S256',flow['authorization_url'])
        receipt=self.manager.complete_oauth('oauth',flow['flow_id'],flow['state'],
          'one-time-code',self.base,self.base+'/callback',now=1001)
        self.assertEqual(receipt['status'],'ACTIVE')
        with self.assertRaisesRegex(ValueError,'REPLAY'):
            self.manager.complete_oauth('oauth',flow['flow_id'],flow['state'],
              'again',self.base,self.base+'/callback',now=1002)
        refreshed=self.manager.refresh('oauth',now=1002)
        self.assertEqual(refreshed['status'],'ACTIVE')
        self.assertEqual(len(OAuthHandler.calls),2)
        self.assertEqual(self.manager.revoke('oauth')['status'],'REVOKED')
        with self.assertRaisesRegex(ValueError,'ACTIVE_CONNECTION'):
            self.manager.credential('oauth',self.base,'MODEL_INFERENCE',now=1003)

    def test_oauth_state_issuer_redirect_expiry_and_refresh_conflict(self):
        self.manager.upsert(self.oauth_config());flow=self.manager.begin_oauth('oauth')
        for state,issuer,redirect,error in (
          ('wrong',self.base,self.base+'/callback','STATE_MISMATCH'),
          (flow['state'],self.base+'/wrong',self.base+'/callback','ISSUER_MISMATCH'),
          (flow['state'],self.base,self.base+'/wrong','REDIRECT_MISMATCH')):
            with self.assertRaisesRegex(ValueError,error):
                self.manager.complete_oauth('oauth',flow['flow_id'],state,'code',
                  issuer,redirect,now=1001)
        with self.assertRaisesRegex(ValueError,'FLOW_EXPIRED'):
            self.manager.complete_oauth('oauth',flow['flow_id'],flow['state'],
              'code',self.base,self.base+'/callback',now=1600)
        flow=self.manager.begin_oauth('oauth',now=2000)
        self.manager.complete_oauth('oauth',flow['flow_id'],flow['state'],'code',
          self.base,self.base+'/callback',now=2001)
        self.supervisor.db.execute('''UPDATE service_connections SET
          status='REFRESHING',refresh_lease='other',refresh_lease_until=2100''')
        self.supervisor.db.commit()
        with self.assertRaisesRegex(ValueError,'REFRESH_IN_PROGRESS'):
            self.manager.refresh('oauth',now=2002)
        with self.assertRaisesRegex(ValueError,'REFRESH_IN_PROGRESS'):
            self.manager.upsert(self.oauth_config(),now=2002)
        self.supervisor.db.execute('''UPDATE service_connections SET
          refresh_lease_until=NULL WHERE connection_id='oauth' ''')
        self.supervisor.db.commit()
        with self.assertRaisesRegex(ValueError,'RECOVERY_REAUTH_REQUIRED'):
            self.manager.refresh('oauth',now=2200)
        row=self.supervisor.db.execute('''SELECT status,refresh_lease,
          refresh_lease_until FROM service_connections WHERE
          connection_id='oauth' ''').fetchone()
        self.assertEqual(tuple(row),('REAUTH_REQUIRED',None,None))

    def test_tenant_isolation_and_scope_expansion_require_new_authorization(self):
        self.manager.upsert(self.oauth_config())
        expanded=self.oauth_config();expanded['scopes'].append('admin.write')
        with self.assertRaisesRegex(ValueError,'SCOPE_EXPANSION'):
            self.manager.upsert(expanded)
        other=ConnectionManager(self.gateway,
          self.authority.issue('tenant-b','admin:other'),self.master)
        self.assertEqual(other.projection(),[])

    def test_revoke_invalidates_pending_and_inflight_exchange(self):
        self.manager.upsert(self.oauth_config());flow=self.manager.begin_oauth('oauth')
        self.manager.revoke('oauth',now=1001)
        with self.assertRaisesRegex(ValueError,'REPLAY'):
            self.manager.complete_oauth('oauth',flow['flow_id'],flow['state'],'code',
              self.base,self.base+'/callback',now=1002)
        self.manager.upsert(self.oauth_config(),now=1010)
        flow=self.manager.begin_oauth('oauth',now=1011)
        manager=self.manager
        class RevokeDuringExchange(object):
            def exchange(self,*_args):
                manager.revoke('oauth',now=1012)
                return {'access_token':'late-access','refresh_token':'late-refresh',
                  'token_type':'Bearer','expires_in':60,
                  'scope':'models.run tools.read'}
        with self.assertRaisesRegex(ValueError,'REVOKED_OR_CONFIG_CHANGED'):
            self.manager.complete_oauth('oauth',flow['flow_id'],flow['state'],'code',
              self.base,self.base+'/callback',adapter=RevokeDuringExchange(),now=1012)
        row=self.supervisor.db.execute('''SELECT status,secret_cipher,
          refresh_cipher FROM service_connections WHERE connection_id='oauth' ''').fetchone()
        self.assertEqual(tuple(row),('REVOKED',None,None))

    def test_refresh_unknown_failure_requires_new_authorization(self):
        self.manager.upsert(self.oauth_config());flow=self.manager.begin_oauth('oauth')
        self.manager.complete_oauth('oauth',flow['flow_id'],flow['state'],'code',
          self.base,self.base+'/callback',now=1001)
        class Broken(object):
            def __init__(self):self.calls=0
            def exchange(self,*_args):self.calls+=1;raise RuntimeError('lost')
        broken=Broken()
        with self.assertRaises(RuntimeError):self.manager.refresh('oauth',broken,now=1002)
        with self.assertRaisesRegex(ValueError,'REAUTH_REQUIRED'):
            self.manager.refresh('oauth',broken,now=1003)
        self.assertEqual(broken.calls,1)


if __name__=='__main__':unittest.main()
