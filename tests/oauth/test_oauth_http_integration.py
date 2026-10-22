"""Actual loopback TLS/HTTP + Authlib + SQLite; GitHub upstream is a simulator.

Not actual GitHub login, installed tunnel, production approval or LIVE acceptance.
No authentication method in the production app is replaced by a fixture.
"""
import base64
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import ssl
import tempfile
import threading
import time
import unittest
from urllib.parse import urlencode, urlsplit, parse_qs
from unittest.mock import patch

import requests
from flask import Flask, request, jsonify, redirect
from werkzeug.serving import make_server, WSGIRequestHandler
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from authlib.oauth2.rfc7636 import create_s256_code_challenge

from production.cloud_connection.oauth_authority import create_app, initialize_new_database, digest
from production.cloud_connection.oauth_http import create_resource_app
from production.cloud_connection.oauth_resource import Introspection, bounded_http
from production.cloud_connection.github_network import GithubNetwork
from production.cloud_connection.queue import Hold
from production.cloud_connection.private_mcp import PrivateMcp
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_cloud_connection_private_transfer as transfer


class Quiet(WSGIRequestHandler):
    def log_request(self, *args, **kwargs): pass
    def log_error(self, *args, **kwargs): pass


class Server:
    def __init__(self, app, cert=None):
        self.server=make_server('127.0.0.1',0,app,threaded=True,ssl_context=cert,request_handler=Quiet)
        self.base=('https' if cert else 'http')+'://localhost:'+str(self.server.server_port)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.closed=False
    def start(self):self.thread.start();return self
    def close(self):
        if not self.closed:
            self.server.shutdown();self.thread.join(3);self.server.server_close();self.closed=True


def restarted_authority(config, path, session_secret, cert, ready):
    def connect():return sqlite3.connect(path,isolation_level=None,timeout=0)
    app=create_app(config,connect,session_secret,'simulated-github-secret',True)
    server=make_server('127.0.0.1',urlsplit(config['issuer']).port,app,
                       threaded=True,ssl_context=cert,request_handler=Quiet)
    ready.set();server.serve_forever()


def certificate(root):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
    now=datetime.datetime.now(datetime.timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1))
          .not_valid_after(now+datetime.timedelta(days=1))
          .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]),critical=False)
          .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(key,hashes.SHA256()))
    certpath,keypath=root/'test-ca.pem',root/'test-key.pem'
    certpath.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keypath.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    os.chmod(str(keypath),0o600)
    return str(certpath),str(keypath)


class OAuthHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/root')
        self.root=Path(self.tmp.name);self.cert=certificate(self.root)
        self.path=self.root/'auth.sqlite';self.offset=0
        connection=sqlite3.connect(str(self.path),isolation_level=None)
        initialize_new_database(connection);connection.close();os.chmod(str(self.path),0o600)
        self.subject_id=332398908;self.provider_codes={}
        self.provider_fault=None;self.provider_stage=None;self.redirect_hits=0
        self.fault_entered=threading.Event()
        self.fault_count=0;self.fault_lock=threading.Lock();self.provider_delays={}
        provider=Flask('simulated-github')
        def fault(stage):
            if stage in self.provider_delays:time.sleep(self.provider_delays[stage])
            if self.provider_stage!=stage or self.provider_fault is None:return None
            from flask import Response
            self.fault_entered.set()
            with self.fault_lock:self.fault_count+=1
            mode=self.provider_fault
            if mode in ('silent','slow_headers'):
                time.sleep(8 if mode=='silent' else 6)
                return jsonify(id=332398908)
            if mode=='drip':
                def stream():
                    for _ in range(100):yield b' ';time.sleep(0.15)
                return Response(stream(),content_type='application/json')
            if mode=='oversize':
                return Response(b'x'* (16385 if stage=='token' else 65537),content_type='application/json')
            if mode=='oversize_stream':
                return Response(iter([b'x'*10000]*8),content_type='application/json')
            if mode=='oversize_headers':
                return Response(b'{}',headers={'X-Fill':'x'*9000},content_type='application/json')
            if mode=='redirect':return redirect(self.provider.base+'/leak',302)
            raise AssertionError(mode)
        @provider.route('/leak',methods=['GET','POST'])
        def leak():
            self.redirect_hits+=1
            return jsonify(id=332398908)
        @provider.get('/login/oauth/authorize')
        def upstream_login():
            code=secrets.token_urlsafe(24)
            self.provider_codes[code]=(request.args['code_challenge'],request.args['redirect_uri'],self.subject_id)
            return redirect(request.args['redirect_uri']+'?'+urlencode({'code':code,'state':request.args['state']}))
        @provider.post('/login/oauth/access_token')
        def upstream_token():
            failure=fault('token')
            if failure is not None:return failure
            code=self.provider_codes.pop(request.form.get('code'),None)
            if (not code or request.form.get('redirect_uri')!=code[1]
                    or create_s256_code_challenge(request.form.get('code_verifier',''))!=code[0]):
                return jsonify(error='invalid_grant'),400
            return jsonify(access_token='github-simulator-'+str(code[2]),token_type='Bearer')
        @provider.get('/user')
        def upstream_user():
            failure=fault('user')
            if failure is not None:return failure
            value=request.headers.get('Authorization','').split('-')[-1]
            return jsonify(id=int(value))
        self.provider=Server(provider,self.cert).start()
        self.authority=Server(lambda e,s:[],self.cert)
        self.issuer=self.authority.base
        self.audience='https://resource.example.test/mcp'
        self.config=dict(issuer=self.issuer,audience=self.audience,github_client_id='github-app',
            clients={
                'chatgpt':{'redirect_uris':['https://client.example.test/callback'],
                           'auth_method':'none','secret_hash':digest('unused'),'resource_client':False},
                'resource':{'redirect_uris':[], 'auth_method':'client_secret_basic',
                            'secret_hash':digest('resource-secret'),'resource_client':True}},
            subjects=['github:332398908','github:95597695'])
        self.session_secret=b'fixed-offline-session-secret-000000000'
        self.authority.server.app=self.make_app()
        original_send=requests.sessions.Session.send
        def send(client,prepared,**kwargs):
            u=urlsplit(prepared.url)
            if u.hostname in ('github.com','api.github.com'):
                prepared.url=self.provider.base+u.path+('?' + u.query if u.query else '')
                kwargs['proxies']={}
            return original_send(client,prepared,**kwargs)
        self.patcher=patch.object(requests.sessions.Session,'send',send);self.patcher.start()
        self.authority.start()
        self.browser=self.client()

    def connect(self):return sqlite3.connect(str(self.path),isolation_level=None,timeout=0)
    def clock(self):return time.time()+self.offset
    def make_app(self):
        return create_app(self.config,self.connect,self.session_secret,'github-fixture-secret',True,self.clock,
                          github_network=GithubNetwork(self.provider.base,self.cert[0]))
    def client(self):
        c=requests.Session();c.trust_env=False;c.verify=self.cert[0];return c
    def tearDown(self):
        self.browser.close();self.authority.close();self.provider.close();self.patcher.stop();self.tmp.cleanup()

    def authorize(self, browser=None, approve=True, pause_callback=False, **changes):
        browser=browser or self.browser
        verifier='v'*64
        params=dict(client_id='chatgpt',redirect_uri='https://client.example.test/callback',
            response_type='code',scope='project.files.read connection.status',state=secrets.token_urlsafe(24),
            code_challenge=create_s256_code_challenge(verifier),code_challenge_method='S256',resource=self.audience)
        params.update(changes)
        response=browser.get(self.issuer+'/authorize',params=params,allow_redirects=False,timeout=5)
        if response.status_code!=302:return response,verifier
        # Real HTTP redirects through the simulated upstream and real Authlib
        # client callback, stop before following the external client callback.
        for _ in range(5):
            location=response.headers.get('Location','')
            if location=='/consent':break
            if location.startswith('/'):location=self.issuer+location
            if pause_callback and location.startswith(self.issuer+'/github/callback?'):
                return response,verifier
            response=browser.get(location,allow_redirects=False,
                                 timeout=8 if location.startswith(self.issuer+'/github/callback?') else 5)
            if response.status_code!=302:return response,verifier
        consent=browser.get(self.issuer+'/consent',timeout=5)
        if consent.status_code!=200:return consent,verifier
        if not approve:return consent,verifier
        csrf=re.search(r'name="csrf" value="([^"]+)"',consent.text).group(1)
        return browser.post(self.issuer+'/consent',data={'csrf':csrf,'approve':'yes'},allow_redirects=False,timeout=5),verifier

    def issue(self):
        response,verifier=self.authorize()
        self.assertEqual(response.status_code,302,response.text)
        code=parse_qs(urlsplit(response.headers['Location']).query)['code'][0]
        payload=dict(client_id='chatgpt',grant_type='authorization_code',code=code,
                     redirect_uri='https://client.example.test/callback',code_verifier=verifier,resource=self.audience)
        response=self.browser.post(self.issuer+'/token',data=payload,timeout=5)
        self.assertEqual(response.status_code,200,response.text)
        return response.json(),payload

    def inspect(self, raw):
        response=self.browser.post(self.issuer+'/introspect',data={'token':raw},
                                   auth=('resource','resource-secret'),timeout=5)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_real_http_code_pkce_introspection_and_no_plaintext_database_tokens(self):
        tokens,payload=self.issue()
        info=self.inspect(tokens['access_token'])
        self.assertEqual(info['sub'],'github:332398908');self.assertEqual(info['aud'],self.audience)
        self.assertTrue(info['active']);self.assertEqual(info['token_type'],'Bearer')
        raw=self.path.read_bytes()
        for secret in (tokens['access_token'],tokens['refresh_token'],payload['code']):
            self.assertNotIn(secret.encode(),raw)

    def test_code_single_use_and_wrong_verifier(self):
        tokens,payload=self.issue()
        replay=self.browser.post(self.issuer+'/token',data=payload,timeout=5)
        self.assertEqual(replay.status_code,400)
        response,verifier=self.authorize();code=parse_qs(urlsplit(response.headers['Location']).query)['code'][0]
        payload.update(code=code,code_verifier='x'*64)
        self.assertEqual(self.browser.post(self.issuer+'/token',data=payload,timeout=5).status_code,400)
        payload['code_verifier']=verifier
        self.assertEqual(self.browser.post(self.issuer+'/token',data=payload,timeout=5).status_code,200)

    def test_refresh_rotation_replay_revokes_successor(self):
        old,_=self.issue()
        form=dict(client_id='chatgpt',grant_type='refresh_token',refresh_token=old['refresh_token'])
        response=self.browser.post(self.issuer+'/token',data=form,timeout=5)
        self.assertEqual(response.status_code,200,response.text)
        new=response.json();self.assertNotEqual(new['refresh_token'],old['refresh_token'])
        self.assertFalse(self.inspect(old['access_token'])['active'])
        self.assertTrue(self.inspect(new['access_token'])['active'])
        self.assertEqual(self.browser.post(self.issuer+'/token',data=form,timeout=5).status_code,400)
        self.assertFalse(self.inspect(new['access_token'])['active'])

    def test_revocation_and_restart_persist(self):
        tokens,_=self.issue()
        self.authority.server.app=self.make_app()
        self.assertTrue(self.inspect(tokens['access_token'])['active'])
        response=self.browser.post(self.issuer+'/revoke',data={'token':tokens['refresh_token'],'client_id':'chatgpt'},timeout=5)
        self.assertEqual(response.status_code,200,response.text)
        self.authority.server.app=self.make_app()
        self.assertFalse(self.inspect(tokens['access_token'])['active'])

    def test_exact_callback_and_s256_only(self):
        for change in ({'redirect_uri':'https://client.example.test/callback/extra'},
                       {'code_challenge_method':'plain'},{'resource':'https://other.test/mcp'}):
            response,_=self.authorize(**change);self.assertEqual(response.status_code,400)

    def test_unenrolled_github_subject(self):
        self.subject_id=1234
        response,_=self.authorize();self.assertEqual(response.status_code,401)
        self.assertEqual(self.connect().execute('SELECT count(*) FROM oauth_tokens').fetchone()[0],0)

    def test_expired_code_and_token(self):
        response,verifier=self.authorize()
        code=parse_qs(urlsplit(response.headers['Location']).query)['code'][0]
        self.offset=121
        form=dict(client_id='chatgpt',grant_type='authorization_code',code=code,
                  redirect_uri='https://client.example.test/callback',code_verifier=verifier)
        self.assertEqual(self.browser.post(self.issuer+'/token',data=form,timeout=5).status_code,400)
        self.offset=0;tokens,_=self.issue();self.offset=901
        self.assertFalse(self.inspect(tokens['access_token'])['active'])

    def test_concurrent_code_exchange_has_single_winner(self):
        response,verifier=self.authorize();code=parse_qs(urlsplit(response.headers['Location']).query)['code'][0]
        payload=dict(client_id='chatgpt',grant_type='authorization_code',code=code,
                     redirect_uri='https://client.example.test/callback',code_verifier=verifier)
        barrier=threading.Barrier(2);results=[]
        def exchange():
            with self.client() as client:
                barrier.wait();results.append(client.post(self.issuer+'/token',data=payload,timeout=5).status_code)
        threads=[threading.Thread(target=exchange) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join(6)
        self.assertEqual(results.count(200),1,results)
        self.assertTrue(all(s in (200,400,503) for s in results))
        with self.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM oauth_tokens').fetchone()[0],1)

    def test_http_resource_full_transfer_scope_project_sha_and_revocation(self):
        tokens,_=self.issue()
        fixture=transfer.PrivateTransferTests()
        with patch.object(transfer,'NOW',int(time.time())):fixture.setUp()
        resource_server=None
        try:
            (fixture.root/'private-results').mkdir(mode=0o700)
            os.chmod(str(fixture.root/'queue.sqlite'),0o600)
            auth=Introspection(self.issuer,self.issuer+'/introspect','resource',lambda:'resource-secret',
                self.audience,{'github:332398908':{'recipient':'work-window','projects':['project-fixture']},
                               'github:95597695':{'recipient':'audit-window','projects':['different-project']}})
            catalogs={fixture.catalog.sha:(fixture.catalog,{'frozen-input':(str(fixture.src),0)})}
            app=create_resource_app(auth,lambda:PrivateMcp(str(fixture.root)),catalogs,self.audience,True)
            resource_server=Server(app).start()
            endpoint=resource_server.base+'/mcp'
            payload={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{
                'name':'read_project_chunk','arguments':dict(manifest_sha256=fixture.catalog.sha,
                request_id='approved-transfer',object_ref='module-object',offset=0)}}
            challenge=self.browser.post(endpoint,json=payload,timeout=8)
            self.assertEqual(challenge.status_code,401)
            self.assertIn('resource_metadata=',challenge.headers['WWW-Authenticate'])
            discovery=self.browser.get(resource_server.base+'/.well-known/oauth-protected-resource',timeout=5).json()
            self.assertEqual(discovery['resource'],self.audience)
            headers={'Authorization':'Bearer '+tokens['access_token']}
            with patch.dict(os.environ,{'SSL_CERT_FILE':self.cert[0]}):
                response=self.browser.post(endpoint,json=payload,headers=headers,timeout=12)
                self.assertEqual(response.status_code,200,response.text)
                value=response.json()['result']['structuredContent']
                self.assertEqual(value['sha256'],hashlib.sha256(fixture.data).hexdigest())
                result=fixture.receiver.accept(value,int(time.time()))
                for offset in range(transfer.CHUNK,len(fixture.data),transfer.CHUNK):
                    payload['params']['arguments']['offset']=offset
                    part=self.browser.post(endpoint,json=payload,headers=headers,timeout=12)
                    self.assertEqual(part.status_code,200,part.text)
                    result=fixture.receiver.accept(part.json()['result']['structuredContent'],int(time.time()))
                self.assertEqual(result['state'],'SUCCESS')
                self.assertEqual(hashlib.sha256((fixture.dst/result['private_ref']).read_bytes()).hexdigest(),
                                 hashlib.sha256(fixture.data).hexdigest())
                payload['params']['arguments']['offset']=0
                initialize={'jsonrpc':'2.0','id':2,'method':'initialize','params':{'protocolVersion':'2025-06-18'}}
                self.assertEqual(self.browser.post(endpoint,json=initialize,headers=headers,timeout=8).status_code,200)
                # Real second OAuth browser/subject, same HTTP resource, no
                # mutable shared recipient state from the first request.
                self.subject_id=95597695
                second,_=self.issue()
                other={'Authorization':'Bearer '+second['access_token']}
                self.assertEqual(self.browser.post(endpoint,json=payload,headers=other,timeout=8).status_code,401)
                self.assertEqual(self.browser.post(endpoint,json=payload,headers=headers,timeout=12).status_code,200)
                self.browser.post(self.issuer+'/revoke',data={'client_id':'chatgpt','token':tokens['access_token']},timeout=5)
                self.assertEqual(self.browser.post(endpoint,json=payload,headers=headers,timeout=8).status_code,401)
        finally:
            if resource_server:resource_server.close()
            fixture.tearDown()

    def test_network_total_deadline_cancels_slow_http_drip(self):
        from flask import Response
        drip_app=Flask('drip')
        @drip_app.post('/drip')
        def drip():
            def stream():
                for _ in range(100):
                    yield b' ';time.sleep(0.15)
            return Response(stream(),content_type='application/json')
        server=Server(drip_app,self.cert).start()
        try:
            import urllib.request
            req=urllib.request.Request(server.base+'/drip',data=b'token=fixture')
            before=time.monotonic()
            with patch.dict(os.environ,{'SSL_CERT_FILE':self.cert[0]}):
                with self.assertRaises(Hold):bounded_http(req,5)
            elapsed=time.monotonic()-before
            self.assertGreater(elapsed,4.5);self.assertLess(elapsed,5.8)
            import multiprocessing
            self.assertEqual(multiprocessing.active_children(),[])
        finally:server.close()

    def test_missing_state_and_csrf_do_not_issue_code(self):
        response,verifier=self.authorize(approve=False)
        self.assertEqual(response.status_code,200)
        csrf=re.search(r'name="csrf" value="([^"]+)"',response.text).group(1)
        with self.connect() as db:before=db.execute('SELECT count(*) FROM oauth_codes').fetchone()[0]
        self.assertEqual(self.browser.post(self.issuer+'/consent',data={'csrf':'fake','approve':'yes'},timeout=5).status_code,403)
        other=self.client()
        try:
            response=other.get(self.issuer+'/github/callback?code=fake&state=fake',timeout=5)
            self.assertEqual(response.status_code,401)
        finally:other.close()
        with self.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM oauth_codes').fetchone()[0],before)
        self.assertEqual(self.browser.post(self.issuer+'/consent',data={'csrf':csrf,'approve':'yes'},timeout=5,allow_redirects=False).status_code,302)

    def test_metadata_and_introspection_require_secret(self):
        metadata=self.browser.get(self.issuer+'/.well-known/oauth-authorization-server',timeout=5).json()
        self.assertEqual(metadata['code_challenge_methods_supported'],['S256'])
        token,_=self.issue()
        for auth in (None,('resource','wrong')):
            response=self.browser.post(self.issuer+'/introspect',data={'token':token['access_token']},auth=auth,timeout=5)
            self.assertEqual(response.status_code,401)

    def test_resource_and_authority_strict_enable(self):
        for value in (False,1,'false'):
            with self.assertRaises(Hold):
                create_app(self.config,self.connect,self.session_secret,'secret',value)
            with self.assertRaises(Hold):
                create_resource_app(None,None,{},self.audience,value)

    def test_commit_busy_rolls_back_without_consuming_code(self):
        response,verifier=self.authorize();code=parse_qs(urlsplit(response.headers['Location']).query)['code'][0]
        payload=dict(client_id='chatgpt',grant_type='authorization_code',code=code,
                     redirect_uri='https://client.example.test/callback',code_verifier=verifier)
        reader=self.connect();reader.execute('BEGIN');reader.execute('SELECT * FROM oauth_tokens').fetchall()
        try:
            self.assertEqual(self.browser.post(self.issuer+'/token',data=payload,timeout=5).status_code,503)
            self.assertEqual(reader.execute('SELECT count(*) FROM oauth_tokens').fetchone()[0],0)
        finally:reader.rollback();reader.close()
        self.assertEqual(self.browser.post(self.issuer+'/token',data=payload,timeout=5).status_code,200)

    def test_scope_escalation_and_refresh_absolute_expiry(self):
        tokens,_=self.issue()
        form=dict(client_id='chatgpt',grant_type='refresh_token',refresh_token=tokens['refresh_token'],scope='admin')
        self.assertEqual(self.browser.post(self.issuer+'/token',data=form,timeout=5).status_code,400)
        self.offset=7*86400+1;form.pop('scope')
        self.assertEqual(self.browser.post(self.issuer+'/token',data=form,timeout=5).status_code,400)

    def test_concurrent_refresh_never_issues_two_successors(self):
        tokens,_=self.issue();barrier=threading.Barrier(2);results=[]
        def refresh():
            with self.client() as c:
                barrier.wait()
                results.append(c.post(self.issuer+'/token',data=dict(client_id='chatgpt',grant_type='refresh_token',
                    refresh_token=tokens['refresh_token']),timeout=5).status_code)
        threads=[threading.Thread(target=refresh) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join(6)
        self.assertEqual(results.count(200),1,results)
        self.assertTrue(all(v in (200,400,503) for v in results))
        with self.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM oauth_tokens').fetchone()[0],2)

    def test_independent_process_restart_refresh_and_revocation(self):
        import multiprocessing
        tokens,_=self.issue()
        self.authority.close()
        ctx=multiprocessing.get_context('spawn')
        def start():
            ready=ctx.Event()
            process=ctx.Process(target=restarted_authority,args=(self.config,str(self.path),self.session_secret,self.cert,ready))
            process.start()
            if not ready.wait(5):
                process.terminate();process.join();self.fail('authority restart timeout')
            return process
        process=start()
        try:
            response=self.browser.post(self.issuer+'/token',data=dict(client_id='chatgpt',grant_type='refresh_token',
                    refresh_token=tokens['refresh_token']),timeout=5)
            self.assertEqual(response.status_code,200,response.text);new=response.json()
            self.assertTrue(self.inspect(new['access_token'])['active'])
        finally:process.terminate();process.join(3)

        process=start()
        try:
            self.assertTrue(self.inspect(new['access_token'])['active'])
            self.assertFalse(self.inspect(tokens['access_token'])['active'])
            response=self.browser.post(self.issuer+'/revoke',data={'client_id':'chatgpt','token':new['refresh_token']},timeout=5)
            self.assertEqual(response.status_code,200)
            self.assertFalse(self.inspect(new['access_token'])['active'])
        finally:process.terminate();process.join(3)

    def test_http_protocol_rejects_origin_duplicate_json_unknown_tool_and_expiry(self):
        tokens,_=self.issue()
        auth=Introspection(self.issuer,self.issuer+'/introspect','resource',lambda:'resource-secret',
            self.audience,{'github:332398908':{'recipient':'work-window','projects':['project-fixture']}})
        def no_backend():raise AssertionError('no file/DB access for rejected protocol request')
        app=create_resource_app(auth,no_backend,{},self.audience,True)
        server=Server(app).start()
        try:
            headers={'Authorization':'Bearer '+tokens['access_token']}
            endpoint=server.base+'/mcp'
            message={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}}
            with patch.dict(os.environ,{'SSL_CERT_FILE':self.cert[0]}):
                self.assertEqual(self.browser.get(endpoint,timeout=8).status_code,401)
                self.assertEqual(self.browser.get(endpoint,headers=headers,timeout=8).status_code,405)
                self.assertEqual(self.browser.post(endpoint,json=message,headers=dict(headers,Origin='https://evil.test'),timeout=8).status_code,400)
                bad=dict(headers,**{'Content-Type':'application/json'})
                self.assertEqual(self.browser.post(endpoint,data='{"jsonrpc":"2.0","id":1,"id":2}',headers=bad,timeout=8).status_code,400)
                self.assertEqual(self.browser.post(endpoint,data='x'*16385,headers=bad,timeout=8).status_code,413)
                unknown=dict(message,method='tools/call',params={'name':'run_shell','arguments':{}})
                self.assertEqual(self.browser.post(endpoint,json=unknown,headers=headers,timeout=8).status_code,401)
                self.offset=901
                self.assertEqual(self.browser.post(endpoint,json=message,headers=headers,timeout=8).status_code,401)
        finally:server.close()

    def assert_no_github_binding(self):
        with self.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM oauth_flows WHERE sub IS NOT NULL').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM oauth_codes').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM oauth_tokens').fetchone()[0],0)

    def test_github_slow_headers_drip_and_silent_fail_without_identity_or_code(self):
        for stage in ('token','user'):
            for mode in ('slow_headers','drip','silent'):
                with self.subTest(stage=stage,mode=mode):
                    self.provider_stage=stage;self.provider_fault=mode
                    before=time.monotonic()
                    response,_=self.authorize()
                    elapsed=time.monotonic()-before
                    self.assertEqual(response.status_code,401)
                    self.assertGreater(elapsed,4.5);self.assertLess(elapsed,6.5)
                    self.assert_no_github_binding()
                    import multiprocessing
                    self.assertEqual(multiprocessing.active_children(),[])

    def test_github_declared_and_streamed_oversize_response_bounds(self):
        for stage in ('token','user'):
            for mode in ('oversize','oversize_stream','oversize_headers'):
                with self.subTest(stage=stage,mode=mode):
                    self.provider_stage=stage;self.provider_fault=mode
                    response,_=self.authorize()
                    self.assertEqual(response.status_code,401)
                    self.assert_no_github_binding()

    def test_github_redirect_is_not_followed_on_either_endpoint(self):
        for stage in ('token','user'):
            self.provider_stage=stage;self.provider_fault='redirect'
            response,_=self.authorize()
            self.assertEqual(response.status_code,401)
            self.assertEqual(self.redirect_hits,0)
            self.assert_no_github_binding()

    def test_github_token_and_user_share_one_total_deadline(self):
        self.provider_delays={'token':3,'user':3}
        before=time.monotonic();response,_=self.authorize();elapsed=time.monotonic()-before
        self.assertEqual(response.status_code,401)
        self.assertGreater(elapsed,4.5);self.assertLess(elapsed,6.5)
        self.assert_no_github_binding()

    def test_github_transport_does_not_inherit_environment_proxies(self):
        with patch.dict(os.environ,{'HTTPS_PROXY':'http://127.0.0.1:1','HTTP_PROXY':'http://127.0.0.1:1',
                                    'ALL_PROXY':'http://127.0.0.1:1','NO_PROXY':''}):
            tokens,_=self.issue()
        self.assertTrue(self.inspect(tokens['access_token'])['active'])

    def test_blocked_github_callbacks_leave_introspection_and_revocation_capacity(self):
        # Four-slot actual TLS/HTTP WSGI host, matching entrypoint threads=4.
        # Two blocked callbacks plus immediate refusal cannot consume all slots.
        app=self.authority.server.app;slots=threading.BoundedSemaphore(4)
        def four_slot_host(environ,start_response):
            with slots:
                response=app(environ,start_response)
                try:yield from response
                finally:
                    if hasattr(response,'close'):response.close()
        self.authority.server.app=four_slot_host
        tokens,_=self.issue()
        before_codes=self.connect().execute('SELECT count(*) FROM oauth_codes').fetchone()[0]
        clients=[self.client() for _ in range(4)];urls=[]
        for client in clients:
            response,_=self.authorize(browser=client,pause_callback=True)
            urls.append(response.headers['Location'])
        self.provider_stage='token';self.provider_fault='silent'
        results=[]
        def call(index):results.append(clients[index].get(urls[index],timeout=8).status_code)
        blocked=[threading.Thread(target=call,args=(i,)) for i in range(2)]
        for t in blocked:t.start()
        end=time.monotonic()+3
        while self.fault_count<2 and time.monotonic()<end:time.sleep(0.01)
        self.assertEqual(self.fault_count,2)
        start=time.monotonic()
        self.assertEqual(clients[2].get(urls[2],timeout=2).status_code,503)
        self.assertTrue(self.inspect(tokens['access_token'])['active'])
        revoked=self.browser.post(self.issuer+'/revoke',data={'client_id':'chatgpt','token':tokens['refresh_token']},timeout=2)
        self.assertEqual(revoked.status_code,200)
        self.assertLess(time.monotonic()-start,2)
        for t in blocked:t.join(8)
        self.assertEqual(results.count(401),2,results)
        with self.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM oauth_codes').fetchone()[0],before_codes)
            self.assertEqual(db.execute('SELECT count(*) FROM oauth_flows WHERE used=0 AND sub IS NOT NULL').fetchone()[0],0)
        # Slot permits are released after both failures: a new valid request works.
        self.provider_fault=None
        response,_=self.authorize(browser=clients[3]);self.assertEqual(response.status_code,302)
        for c in clients:c.close()

    def test_real_http_initialize_negotiates_unknown_version_without_shared_identity(self):
        tokens,_=self.issue()
        auth=Introspection(self.issuer,self.issuer+'/introspect','resource',lambda:'resource-secret',self.audience,
            {'github:332398908':{'recipient':'work-window','projects':['project-fixture']}})
        def no_backend():raise AssertionError('initialize must not open private files')
        server=Server(create_resource_app(auth,no_backend,{},self.audience,True)).start()
        headers={'Authorization':'Bearer '+tokens['access_token']}
        try:
            with patch.dict(os.environ,{'SSL_CERT_FILE':self.cert[0]}):
                for proposed,expected in (('2025-06-18','2025-06-18'),('2025-11-25','2025-06-18')):
                    message={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':proposed}}
                    response=self.browser.post(server.base+'/mcp',json=message,
                        headers=dict(headers,**{'MCP-Protocol-Version':proposed}),timeout=8)
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['result']['protocolVersion'],expected)
                ping={'jsonrpc':'2.0','id':2,'method':'ping'}
                self.assertEqual(self.browser.post(server.base+'/mcp',json=ping,headers=dict(headers,**{'MCP-Protocol-Version':'2025-06-18'}),timeout=8).status_code,200)
                self.assertEqual(self.browser.post(server.base+'/mcp',json=ping,headers=dict(headers,**{'MCP-Protocol-Version':'2025-11-25'}),timeout=8).status_code,400)
                for value in ('invalid','2025/11/25',True,None):
                    message={'jsonrpc':'2.0','id':3,'method':'initialize','params':{'protocolVersion':value}}
                    self.assertEqual(self.browser.post(server.base+'/mcp',json=message,headers=headers,timeout=8).status_code,400)
                # Previous successful initialization grants no next-request identity.
                self.assertEqual(self.browser.post(server.base+'/mcp',json=ping,timeout=8).status_code,401)
        finally:server.close()



if __name__=='__main__':unittest.main()
