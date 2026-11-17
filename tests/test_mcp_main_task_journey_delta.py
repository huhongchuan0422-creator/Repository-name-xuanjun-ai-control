"""TEST_ONLY real-main task_submit/get/result journey; no production data."""
import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

import test_task_center_mcp_service as fixture
from task_center_session_auth import password_hash

ROOT=Path(__file__).resolve().parents[1]
HOST='mcp.example.com'; ORIGIN='https://'+HOST; BASE='/task-center-test'

class LocalModel(fixture.Fixture):
    request_texts=[]
    def do_POST(self):
        n=int(self.headers.get('Content-Length','0'))
        body=json.loads(self.rfile.read(n).decode())
        messages=body['messages'];text=messages[-1]['content']
        type(self).request_texts.append(text)
        if text=='fixture-explicit-failure':
            self.send_response(401);self.send_header('Content-Length','0');self.end_headers();return
        data=json.dumps({'id':'local-only','choices':[{'message':{'content':'{"label":"safe","reason":"test-success"}'}}],
            'usage':{'prompt_tokens':8,'completion_tokens':4,'total_tokens':12}}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class MainTaskJourney(unittest.TestCase):
    def test_submit_get_result_failure_and_authorization(self):
        # Reuse existing service fixture to build a wholly new TEST_ONLY ledger;
        # only its loopback model responder is specialized for success/failure.
        LocalModel.request_texts=[]
        f=fixture.MCPTaskServiceTests()
        with patch.object(fixture,'Fixture',LocalModel):f.setUp()
        proc=None
        try:
            root=Path(f.root)
            def protected(name,raw):
                path=root/name;fd=os.open(str(path),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                with os.fdopen(fd,'wb') as stream:stream.write(raw)
                return str(path)
            auth=protected('authority.key',fixture.KEY)
            master=protected('master.key',f.master)
            hashed=password_hash('test-password-only')
            users={}
            for name,tenant,principal in [('owner','tenant-mcp','owner-1'),('other','tenant-mcp','other-1'),('alien','tenant-other','alien-1')]:
                users[name]={'enabled':True,'password_hash':hashed,'tenant_id':tenant,
                    'principal_id':principal,'roles':['TASK_CENTER_ADMIN']}
            identity=protected('identities.json',json.dumps({'users':users}).encode())
            sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
            cmd=[sys.executable,'-B',str(ROOT/'scripts'/'task_center_app.py'),'--db',f.db,
                '--test-authority-key-file',auth,'--tenant','tenant-mcp','--host','127.0.0.1','--port',str(port),
                '--model-master-key-file',master,'--test-identity-file',identity,'--external-origin',ORIGIN,
                '--base-path',BASE,'--enable-mcp','--allow-mcp-model-outbound']
            proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,
                env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
            line=proc.stdout.readline()
            if not line:
                _,err=proc.communicate(timeout=5);self.fail('main startup exit=%s: %s'%(proc.returncode,err[-2000:]))
            receipt=json.loads(line);self.assertEqual(receipt['state'],'STARTED');self.assertEqual(receipt['mcp_model_outbound'],'ENABLED_ZERO_SPEND_GATES')
            opener=build_opener(ProxyHandler({}),NoRedirect)
            def raw(path,method='GET',body=None,headers=None):
                h={'Host':HOST};h.update(headers or {})
                try:return opener.open(Request('http://127.0.0.1:%d%s%s'%(port,BASE,path),method=method,data=body,headers=h),timeout=15)
                except HTTPError as e:
                    if e.code in (301,302,303,307,308):return e
                    raise
            def jpost(path,obj,headers=None):
                h={'Content-Type':'application/json'};h.update(headers or {})
                return json.loads(raw(path,'POST',json.dumps(obj).encode(),h).read())
            def token_for(user,scope='task:read task:submit'):
                redirect='https://chatgpt.com/connector_platform_oauth_redirect'
                client=jpost('/oauth/register',{'redirect_uris':[redirect],'grant_types':['authorization_code'],
                    'response_types':['code'],'token_endpoint_auth_method':'none'})
                login=raw('/api/session/login','POST',json.dumps({'username':user,'password':'test-password-only'}).encode(),
                    {'Content-Type':'application/json','Origin':ORIGIN})
                cookie=login.headers.get_all('Set-Cookie')[0].split(';',1)[0]
                verifier='z'*64;challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
                resource=ORIGIN+BASE+'/mcp'
                params={'response_type':'code','client_id':client['client_id'],'redirect_uri':redirect,'code_challenge':challenge,
                    'code_challenge_method':'S256','state':'test-only','resource':resource,'scope':scope}
                loc=raw('/oauth/authorize?'+urlencode(params),headers={'Cookie':cookie}).headers['Location']
                exchange={'grant_type':'authorization_code','code':parse_qs(urlsplit(loc).query)['code'][0],
                    'client_id':client['client_id'],'redirect_uri':redirect,'code_verifier':verifier,'resource':resource}
                return json.loads(raw('/oauth/token','POST',urlencode(exchange).encode(),{'Content-Type':'application/x-www-form-urlencoded'}).read())['access_token']
            def call(token,name,args):
                reply=jpost('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}},
                    {'Authorization':'Bearer '+token})
                self.assertNotIn('error',reply,str(reply))
                return json.loads(reply['result']['content'][0]['text'])
            owner=token_for('owner'); other=token_for('other');readonly=token_for('owner','task:read')
            contract=call(owner,'task_dispatch_contract',{})
            self.assertEqual(contract['status'],'SOURCE_CANDIDATE_NOT_WIRED')
            self.assertFalse(contract['execution_connected'])
            def submission(idem,text):return {'project_id':'project-mcp','task_type':'TEXT_CLASSIFICATION','input_text':text,
                'idempotency_key':idem,'connection_id':'fixture-connection','max_output_tokens':32}
            def wait_result(task):
                deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    result=call(owner,'task_query_result',{'task_id':task})
                    if result['state'] in ('SUCCEEDED','FAILED','UNKNOWN','HOLD'):return result
                    time.sleep(.05)
                self.fail('task result not settled; last state='+result['state'])
            success=call(owner,'task_submit',submission('journey-success','fixture-success'))
            success_id=success['task_id']
            detail=call(owner,'task_get',{'task_id':success_id});self.assertEqual(detail['task_id'],success_id)
            self.assertEqual(detail['request']['request_id'],success['request_id'])
            good=wait_result(success_id)
            self.assertEqual(good['task_id'],success_id);self.assertEqual(good['request_id'],success['request_id'])
            self.assertEqual(good['state'],'SUCCEEDED');self.assertIn('test-success',good['result']['content'])
            self.assertEqual(good['usage']['cost_state'],'KNOWN_ZERO')
            self.assertEqual(call(owner,'task_get',{'task_id':success_id})['request']['state'],'SUCCEEDED')
            bad=call(owner,'task_submit',submission('journey-failure','fixture-explicit-failure'))
            failure_id=bad['task_id'];self.assertNotEqual(success_id,failure_id)
            bad_detail=call(owner,'task_get',{'task_id':failure_id});self.assertEqual(bad_detail['request']['request_id'],bad['request_id'])
            failed=wait_result(failure_id)
            self.assertEqual(failed['task_id'],failure_id);self.assertEqual(failed['request_id'],bad['request_id'])
            self.assertEqual((failed['state'],failed['error_kind'],failed['result']),('FAILED','AUTH',None))
            self.assertEqual(call(owner,'task_get',{'task_id':failure_id})['request']['error_kind'],'AUTH')
            self.assertEqual(call(owner,'task_query_result',{'task_id':success_id})['result'],good['result'])
            self.assertEqual(LocalModel.request_texts.count('fixture-success'),1);self.assertEqual(LocalModel.request_texts.count('fixture-explicit-failure'),1)
            with self.assertRaises(HTTPError) as no_scope:call(readonly,'task_submit',submission('scope-reject','fixture-success'))
            self.assertEqual(no_scope.exception.code,401)
            with self.assertRaises(HTTPError) as wrong_project:call(owner,'task_submit',dict(submission('wrong-project','fixture-success'),project_id='not-authorized'))
            self.assertEqual(wrong_project.exception.code,400)
            self.assertEqual(json.loads(wrong_project.exception.read())['error_description'],'MCP_PROJECT_SCOPE_REJECTED')
            with self.assertRaises(HTTPError) as invisible:call(other,'task_query_result',{'task_id':success_id})
            self.assertEqual(invisible.exception.code,400)
            self.assertEqual(json.loads(invisible.exception.read())['error_description'],'MCP_TASK_NOT_VISIBLE')
            for tool,tid,token in [('task_get',success_id,other),('task_query_result','mcp-nonexistent',owner),('task_get','mcp-nonexistent',owner)]:
                with self.assertRaises(HTTPError) as missing:call(token,tool,{'task_id':tid})
                self.assertEqual(missing.exception.code,400)
                self.assertEqual(json.loads(missing.exception.read())['error_description'],'MCP_TASK_NOT_VISIBLE')
            with self.assertRaises(HTTPError) as wrong_tenant:token_for('alien')
            self.assertEqual(wrong_tenant.exception.code,401)
            pid=proc.pid;proc.send_signal(signal.SIGTERM);out,err=proc.communicate(timeout=15)
            self.assertEqual(proc.returncode,0);self.assertIn('STOPPED',out);proc=None
            print('TASK_JOURNEY_PROOF '+json.dumps({'main_pid':pid,'main_exit':0,'argv':cmd,
                'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=str(ROOT)).decode().strip(),
                'success_task':success_id,'success_request':success['request_id'],'success_result_state':good['state'],
                'success_canonical_state':detail['canonical_task_state'],'failure_task':failure_id,
                'failure_request':bad['request_id'],'failure_result_state':failed['state'],'failure_error_kind':failed['error_kind'],
                'failure_result_is_null':failed['result'] is None,'success_model_calls':1,'failure_model_calls':1,
                'readonly_submit_http':no_scope.exception.code,'wrong_project_http':wrong_project.exception.code,
                'other_principal_http':invisible.exception.code,'other_tenant_login_http':wrong_tenant.exception.code,
                'source_contract_status':contract['status'],'source_contract_execution_connected':contract['execution_connected']},sort_keys=True))
        finally:
            if proc is not None:proc.kill();proc.communicate(timeout=10)
            f.tearDown()

class ErrorMappingTest(unittest.TestCase):
    def test_only_exact_visibility_key_is_mapped(self):
        from task_center_mcp import RemoteTaskCenterMCP
        class BrokenService:
            def status(self,unused):raise KeyError('UNRELATED_INTERNAL_KEY')
        with self.assertRaisesRegex(KeyError,'UNRELATED_INTERNAL_KEY'):
            RemoteTaskCenterMCP(BrokenService()).call('task_get',{'task_id':'x'})
