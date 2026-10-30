from __future__ import print_function

import json
import hashlib
import os
import shutil
import socketserver
import tempfile
import threading
import time
import unittest
import sys
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError

from cryptography.fernet import Fernet

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
sys.path.insert(0,os.path.join(ROOT,'scripts'))
from reusable_task_gateway import GatewayKernel,TestTenantAuthority
from task_center_app import make_server
from task_center_mcp import TaskCenterMCP
from task_supervisor import Supervisor

KEY=b'0123456789abcdef0123456789abcdef'
TOKEN='test-admin-token-full-journey'
ACTORS={'developer-token-123456':'developer-1',
        'reviewer-token-123456':'qa-1',
        'security-token-123456':'security-1',
        'acceptor-token-123456':'acceptor-1'}


class ThreadServer(socketserver.ThreadingMixIn,HTTPServer):daemon_threads=True
class ModelFixture(BaseHTTPRequestHandler):
    def log_message(self,*_args):pass
    def do_POST(self):
        length=int(self.headers.get('Content-Length','0'))
        value=json.loads(self.rfile.read(length).decode('utf-8'))
        content='ok:'+value['model']
        body=json.dumps({'id':'journey-result','choices':[{'message':
          {'content':content}}],'usage':{'prompt_tokens':4,
          'completion_tokens':2,'total_tokens':6}}).encode()
        self.send_response(200);self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)


class FullJourneyTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.mkdtemp();self.db=os.path.join(self.root,'state.sqlite3')
        supervisor=Supervisor(self.db);GatewayKernel(supervisor,
          TestTenantAuthority(KEY));supervisor.close()
        self.model=ThreadServer(('127.0.0.1',0),ModelFixture)
        self.model_thread=threading.Thread(target=self.model.serve_forever)
        self.model_thread.daemon=True;self.model_thread.start()
        self.server=make_server(self.db,KEY,'tenant-journey','owner',port=0,
          model_master_key=Fernet.generate_key(),admin_token=TOKEN,
          actor_tokens=ACTORS)
        self.thread=threading.Thread(target=self.server.serve_forever)
        self.thread.daemon=True;self.thread.start()
        self.base='http://127.0.0.1:%d'%self.server.server_port
        self.mcp=TaskCenterMCP(self.base,TOKEN,'developer-token-123456',
          'developer-1')

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
        self.model.shutdown();self.model.server_close();self.model_thread.join(2)
        shutil.rmtree(self.root)

    def post(self,value,actor_token=None):
        headers={'Content-Type':'application/json','X-Test-Admin-Token':TOKEN}
        if actor_token:headers['X-Test-Actor-Token']=actor_token
        request=Request(self.base+'/api/admin/model-control',method='POST',
          data=json.dumps(value).encode('utf-8'),headers=headers)
        try:return json.loads(urlopen(request,timeout=3).read().decode('utf-8'))
        except HTTPError as exc:
            raise AssertionError(exc.read().decode('utf-8'))

    def test_project_to_model_to_independent_review_acceptance(self):
        task={'project_id':'project-journey','task_id':'task-journey',
          'board_id':'research-development','delivery_stage':'implementation',
          'feature_unit':'provider-routing','goal':'deliver tested candidate',
          'scope':['WRITE_SOURCE'],'asset_version':'asset-v1',
          'deliverables':['source','logs'],'acceptance':['tests','review'],
          'dependencies':[],'priority':80,'owner':'developer-1'}
        self.post({'action':'CREATE_PROJECT_TASK','task':task})
        observed={'matches':[]}
        # Query an absent key from the server-owned canonical registry; the
        # observed result is verified by the service, not trusted from caller.
        self.post({'action':'RECORD_ASSET_QUERY','task_id':'task-journey',
          'query_id':'query-journey-1','source_kind':'CANONICAL_DB',
          'source_version':'registry-v1','query':{'lookup':{'asset_key':'asset-v1'},
          'observed_result':observed,
          'evidence_ref':'canonical-db://asset-v1@registry-v1'},
          'result_digest':hashlib.sha256(json.dumps(observed,sort_keys=True,
          separators=(',',':')).encode()).hexdigest()})
        self.post({'action':'RECORD_DISPATCH_PREFLIGHT','task_id':'task-journey',
          'asset_version':'asset-v1','query_ids':['query-journey-1'],
          'outcome':'NOT_FOUND','reuse_reason':'verified new TEST_ONLY task'})
        self.assertEqual(self.mcp.call('task_claim',{'task_id':'task-journey',
          'attempt_id':'attempt-1'})['state'],'STARTED')
        listed=self.mcp.call('task_list',{})
        self.assertEqual([x['task_id'] for x in listed],['task-journey'])
        context=self.mcp.call('task_read_context',{'task_id':'task-journey'})
        self.assertEqual(context['task']['attempt_id'],'attempt-1')
        codex_provider={'provider_id':'codex-fixture','display_name':'Codex Fixture',
          'adapter_type':'openai-compatible','base_url':'http://127.0.0.1:9',
          'enabled':True,'price_state':'KNOWN_FREE','rate_limit_per_min':10,
          'concurrency_limit':1,'timeout_seconds':1,'retry_limit':0}
        self.post({'action':'UPSERT_PROVIDER','config':codex_provider,
          'secret':'fixture-codex-secret'})
        self.post({'action':'SET_QUOTA_STATUS','provider_id':'codex-fixture',
          'quota_state':'AVAILABLE','quota_source':'TEST_ONLY_INCLUDED_FIXTURE',
          'verified_at':time.time(),'unavailable_reason':None})
        self.post({'action':'UPSERT_CONNECTION','config':{
          'connection_id':'codex-connection','provider_id':'codex-fixture',
          'purpose':'CODEX_EXECUTION','auth_type':'API_KEY',
          'destination_origin':'http://127.0.0.1:9','issuer':None,
          'authorization_endpoint':None,'token_endpoint':None,
          'revocation_endpoint':None,'redirect_uri':None,'client_id':None,
          'scopes':[],'supports_refresh':False},'credential':'fixture-codex-key'})
        preference=self.post({'action':'SET_OPENAI_CHANNEL_PREFERENCE',
          'preference':'API_FIRST','api_connection_id':'codex-connection',
          'oauth_connection_id':None,'expected_version':0})
        self.assertEqual(preference['effective_channel'],'API')
        codex=self.post({'action':'CREATE_CODEX_INTENT',
          'task_id':'task-journey','transport_kind':'CODEX_SDK',
          'idempotency_key':'journey-codex-intent','context':{
          'goal':'deliver tested candidate','scope':['WRITE_SOURCE'],
          'acceptance':['tests','review'],'asset_version':'asset-v1',
          'reuse_evidence':['query-journey-1'],'connection_id':'codex-connection',
          'provider_id':'codex-fixture'}},'developer-token-123456')
        self.assertEqual(codex['state'],'PENDING')
        verify=Supervisor(self.db)
        try:
            bound=verify.db.execute('''SELECT connection_id,provider_id FROM
              codex_execution_intents WHERE intent_id=?''',(
              codex['intent_id'],)).fetchone()
            self.assertEqual(tuple(bound),
                             ('codex-connection','codex-fixture'))
        finally:verify.close()
        self.assertEqual(self.post({'action':'CANCEL_CODEX_INTENT',
          'intent_id':codex['intent_id']},'developer-token-123456')['state'],
          'CANCELLED')
        provider={'provider_id':'fixture','display_name':'Fixture',
          'adapter_type':'openai-compatible','base_url':
          'http://127.0.0.1:%d'%self.model.server_port,'enabled':True,
          'price_state':'KNOWN_FREE','rate_limit_per_min':10,
          'concurrency_limit':2,'timeout_seconds':1,'retry_limit':1}
        self.post({'action':'UPSERT_PROVIDER','config':provider,
                   'secret':'fixture-secret-value'})
        self.post({'action':'UPSERT_MODEL','config':{'provider_id':'fixture',
          'model_id':'capable','capabilities':['code'],'enabled':True,
          'price_state':'KNOWN_FREE','input_unit_cost':0,
          'output_unit_cost':0}})
        self.post({'action':'REGISTER_BENCHMARK','suite_version':'journey-v1',
          'cases':[{'case_id':'code-1','capability':'code','messages':
          [{'role':'user','content':'check'}],'expected_contains':'ok'}]})
        self.assertEqual(self.post({'action':'RUN_BENCHMARK',
          'provider_id':'fixture','model_id':'capable','suite_version':
          'journey-v1'})['state'],'QUALIFIED')
        roles=(('executor','EXECUTOR',True,'developer-1',None),
               ('reviewer','REVIEWER',False,'qa-1','QA'),
               ('security','REVIEWER',False,'security-1','SECURITY'),
               ('acceptor','ACCEPTOR',False,'acceptor-1',None))
        for role,phase,writer,principal,review_kind in roles:
            self.post({'action':'CREATE_ROLE','config':{'role_id':role,
              'version':'v1','phase':phase,'capabilities':['code'],
              'writer_allowed':writer,'enabled':True,
              'review_kind':review_kind}})
            self.post({'action':'ASSIGN_ROLE','task_id':'task-journey',
              'role_id':role,'role_version':'v1','principal_id':principal,
              'allow_paid':False})
        queued=self.post({'action':'QUEUE_REQUEST','task_id':'task-journey',
          'role_id':'executor','messages':[{'role':'user','content':'build'}],
          'idempotency_key':'journey-execute'})
        self.assertEqual(self.post({'action':'RUN_SCHEDULER_ONCE'})['state'],
          'SUCCEEDED')
        checklist=self.post({'action':'REGISTER_CHECKLIST','task_id':'task-journey',
          'items':[{'id':'tests','required':True,'result':'PASS',
          'evidence':'fixture-test-log'},{'id':'review','required':True,
          'result':'PASS','evidence':'fixture-review-plan'}]})['content_sha256']
        candidate=self.post({'action':'SUBMIT_CANDIDATE','task_id':'task-journey',
          'artifact_sha256':'a'*64,'checklist_sha256':checklist,
          'submitted_by':'developer-1'},'developer-token-123456')
        changed=self.post({'action':'REVIEW_CANDIDATE','candidate_id':
          candidate['candidate_id'],'reviewer':'qa-1','findings':
          [{'id':'DEFECT-1'}],'passed':False},'reviewer-token-123456')
        self.assertEqual(changed['state'],'CHANGES_REQUESTED')
        revised=self.post({'action':'SUBMIT_CANDIDATE','task_id':'task-journey',
          'artifact_sha256':'c'*64,'checklist_sha256':checklist,
          'submitted_by':'developer-1'},'developer-token-123456')
        self.assertEqual(self.post({'action':'REVIEW_CANDIDATE','candidate_id':
          revised['candidate_id'],'reviewer':'qa-1','findings':[],
          'review_kind':'QA','passed':True},'reviewer-token-123456')['state'],
          'QA_PASSED')
        self.assertEqual(self.post({'action':'REVIEW_CANDIDATE','candidate_id':
          revised['candidate_id'],'reviewer':'security-1','findings':[],
          'review_kind':'SECURITY','passed':True},'security-token-123456')['state'],
          'REVIEW_PASSED')
        self.assertEqual(self.post({'action':'ACCEPT_CANDIDATE','candidate_id':
          revised['candidate_id'],'acceptor':'acceptor-1'},
          'acceptor-token-123456')['canonical_task_state'],'SUCCESS')
        request=Request(self.base+'/api/admin/model-control',headers={
          'X-Test-Admin-Token':TOKEN})
        projection=json.loads(urlopen(request,timeout=3).read().decode())
        self.assertEqual(projection['requests'][0]['request_id'],
          queued['request_id'])
        self.assertIn('ACCEPTED',{x['state'] for x in projection['candidates']})
        live=json.loads(urlopen(self.base+'/api/projection',timeout=3).read().decode())
        self.assertEqual(live['tasks'][0]['project_id'],'project-journey')
        self.assertEqual(live['tasks'][0]['state'],'SUCCESS')
        self.assertEqual(live['tasks'][0]['authority_state'],'REVOKED')


if __name__=='__main__':unittest.main()
