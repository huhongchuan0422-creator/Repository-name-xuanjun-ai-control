"""TEST_ONLY real main -> OAuth/MCP -> fixed runner -> restart readback.

Uses the existing producer fixture for an entirely new temporary ledger and
repository. Fixture identities and keys are synthetic, never real authority.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

import test_execution_intent_delta as existing
from task_center_session_auth import password_hash
from task_supervisor import canonical

ROOT=Path(__file__).resolve().parents[1]
HOST='mcp.example.com'
ORIGIN='https://'+HOST
BASE='/task-center-test'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

class MainProcessTest(unittest.TestCase):
    def test_original_main_mcp_real_runner_and_restart(self):
        f=existing.fixtures.ProducerExecutorTests();f.producer_http_test=True
        original=existing.fixtures.demo_graph
        def test_graph(tenant):
            graph=original(tenant);graph['project_id']='project-mcp';return graph
        # Only construction of the new TEST_ONLY fixture graph is customized;
        # the application, loader, HTTP server, OAuth and runner are not mocked.
        with patch.object(existing.fixtures,'demo_graph',side_effect=test_graph):f.setUp()
        proc=None
        try:
            f.profile['project_id']='project-mcp'
            request_id=f.proposal()
            root=f.root
            provider=root/'provider';provider.mkdir(mode=0o700)
            def protected(name,value,raw=False):
                path=root/name
                data=value if raw else json.dumps(value,sort_keys=True).encode()
                fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as stream:stream.write(data)
                return str(path)
            master=base64.urlsafe_b64encode(f.control.fernet._signing_key+f.control.fernet._encryption_key)
            master_file=protected('master',master,True)
            authority_file=protected('authority',existing.fixtures.KEY,True)
            identity_file=protected('identity.json',{'users':{'fixture-developer':{
                'enabled':True,'password_hash':password_hash('fixture-password-only'),
                'tenant_id':'tenant-a','principal_id':'developer-1','roles':['TASK_CENTER_ADMIN']}}})
            custody_file=protected('writer.json',{'demo-b':{'attempt_id':'attempt-b','ticket':f.ticket,'caller':f.caller,'lock_root':str(root/'locks')}})
            binding={'tenant_id':'tenant-a','principal_id':'developer-1','project_id':'project-mcp','task_id':'demo-b',
                'spec_sha256':'b'*64,'checkpoint_sha256':'a'*64,'contract_sha256':hashlib.sha256(canonical(f.contract).encode()).hexdigest(),
                'role_id':'developer','role_version':'v1','phase':'EXECUTOR','review_kind':None,
                'authority_identity':{'issuer':'fixture','subject':'developer'},'actions':['task_development_apply','task_development_status'],
                'candidate_root':None,'executor_profile':f.profile}
            host_file=protected('host.json',{'schema_version':1,'enabled':True,'bindings':[binding],
                'review_keyring_file':None,'writer_context_file':custody_file})
            # Reuse the exact original fence root; release only this fixture's local descriptor.
            f.fence.close()
            sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
            cmd=[sys.executable,'-B',str(ROOT/'scripts'/'task_center_app.py'),
                '--db',str(root/'ledger.sqlite'),'--test-authority-key-file',authority_file,
                '--tenant','tenant-a','--host','127.0.0.1','--port',str(port),
                '--model-master-key-file',master_file,'--test-identity-file',identity_file,
                '--external-origin',ORIGIN,'--base-path',BASE,'--enable-mcp',
                '--mcp-development-config-file',host_file,'--mcp-producer-provider-directory',str(provider)]
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
            opener=build_opener(ProxyHandler({}),NoRedirect)
            def start():
                p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,universal_newlines=True)
                line=p.stdout.readline()
                if not line:
                    _,err=p.communicate(timeout=5);self.fail('main startup failed exit=%s stderr=%s' %(p.returncode,err[-3000:]))
                receipt=json.loads(line);self.assertEqual(receipt['state'],'STARTED');self.assertEqual(receipt['mcp'],'ENABLED')
                return p
            def stop(p):
                p.send_signal(signal.SIGTERM);out,err=p.communicate(timeout=15)
                self.assertEqual(p.returncode,0,err[-2000:]);self.assertIn('STOPPED',out)
            def raw(path,method='GET',body=None,headers=None):
                h={'Host':HOST};h.update(headers or {})
                req=Request('http://127.0.0.1:%d%s%s'%(port,BASE,path),method=method,data=body,headers=h)
                try:return opener.open(req,timeout=60)
                except HTTPError as e:
                    if e.code in (301,302,303,307,308):return e
                    raise
            def jpost(path,obj,headers=None):
                h={'Content-Type':'application/json'};h.update(headers or {})
                return json.loads(raw(path,'POST',json.dumps(obj).encode(),h).read())
            def oauth():
                redirect='https://chatgpt.com/connector_platform_oauth_redirect'
                client=jpost('/oauth/register',{'redirect_uris':[redirect],'grant_types':['authorization_code'],
                    'response_types':['code'],'token_endpoint_auth_method':'none'})
                login=raw('/api/session/login','POST',json.dumps({'username':'fixture-developer','password':'fixture-password-only'}).encode(),
                    {'Content-Type':'application/json','Origin':ORIGIN})
                cookie=login.headers.get_all('Set-Cookie')[0].split(';',1)[0]
                verifier='z'*64;challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
                resource=ORIGIN+BASE+'/mcp'
                params={'response_type':'code','client_id':client['client_id'],'redirect_uri':redirect,'code_challenge':challenge,
                    'code_challenge_method':'S256','state':'fixture-only','resource':resource,'scope':'task:read task:submit'}
                response=raw('/oauth/authorize?'+urlencode(params),headers={'Cookie':cookie})
                code=parse_qs(urlsplit(response.headers['Location']).query)['code'][0]
                exchange={'grant_type':'authorization_code','code':code,'client_id':client['client_id'],
                    'redirect_uri':redirect,'code_verifier':verifier,'resource':resource}
                return json.loads(raw('/oauth/token','POST',urlencode(exchange).encode(),{'Content-Type':'application/x-www-form-urlencoded'}).read())['access_token']
            def apply(token):
                result=jpost('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'task_development_apply',
                    'arguments':{'task_id':'demo-b','attempt_id':'attempt-b','request_id':request_id}}},
                    {'Authorization':'Bearer '+token})
                self.assertNotIn('error',result,str(result));self.assertFalse(result['result']['isError'],str(result))
                return json.loads(result['result']['content'][0]['text'])
            def readback():
                with sqlite3.connect(str(root/'ledger.sqlite')) as db:
                    rows=db.execute("SELECT event_id,kind,payload_json FROM events WHERE kind IN ('DEVELOPMENT_EXECUTION_INTENT','DEVELOPMENT_EXECUTION') ORDER BY kind").fetchall()
                    task=db.execute("SELECT state,authority_state FROM tasks WHERE task_id='demo-b'").fetchone()
                self.assertEqual(len(rows),2)
                intent=json.loads(next(x[2] for x in rows if x[1]=='DEVELOPMENT_EXECUTION_INTENT'))
                with sqlite3.connect(str(provider/'producer-http.sqlite')) as db:
                    stored=db.execute('SELECT intent,observation,artifact FROM observations').fetchall()
                self.assertEqual(len(stored),1);self.assertEqual(stored[0][0],canonical(intent))
                return rows,task,intent,json.loads(stored[0][1]),stored[0][2]
            proc=start();first_pid=proc.pid;token=oauth();first=apply(token)
            self.assertEqual(first['execution_state'],'ISOLATED_TEST_ELIGIBLE');self.assertEqual(first['next_action'],'WAIT_INDEPENDENT_REVIEW')
            before=readback();self.assertEqual(hashlib.sha256(before[4]).hexdigest(),first['execution_artifact_sha256'])
            stop(proc);proc=None
            proc=start();second_pid=proc.pid;self.assertNotEqual(first_pid,second_pid)
            second=apply(token);after=readback()
            self.assertEqual(second['execution_event_id'],first['execution_event_id']);self.assertTrue(second['duplicate'])
            self.assertEqual(after,before);self.assertEqual(second['next_action'],'WAIT_INDEPENDENT_REVIEW')
            stop(proc);proc=None
            print('PROCESS_PROOF '+json.dumps({'main_pids':[first_pid,second_pid],'main_exit_codes':[0,0],
                'task':'demo-b','attempt':'attempt-b','intent_sha256':hashlib.sha256(canonical(before[2]).encode()).hexdigest(),
                'artifact_bytes':len(before[4]),'artifact_sha256':first['execution_artifact_sha256'],
                'execution_event_sha256':hashlib.sha256(first['execution_event_id'].encode()).hexdigest(),
                'canonical_state':list(before[1]),'next_action':first['next_action'],'second_apply_duplicate':second['duplicate'],
                'source_sha256':before[2]['source_sha256'],'source_bytes':len(f.raw),
                'candidate_commit':first['code_commit'],'test_reference_sha256':before[2]['test_reference_sha256'],
                'provider_store_rows':1,'execution_event_rows':1,'intent_event_rows':1,
                'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=str(ROOT)).decode().strip(),
                'runner_sha256':hashlib.sha256((ROOT/'scripts'/'producer_http_runner.py').read_bytes()).hexdigest(),
                'argv':cmd},sort_keys=True))
        finally:
            if proc is not None:
                proc.kill();proc.communicate(timeout=10)
            f.tearDown()
