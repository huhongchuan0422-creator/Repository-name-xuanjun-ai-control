from __future__ import print_function

import json
import os
import shutil
import socketserver
import tempfile
import threading
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
from task_supervisor import Supervisor

KEY=b'0123456789abcdef0123456789abcdef'
TOKEN='test-admin-token-full-journey'
ACTORS={'developer-token-123456':'developer-1',
        'reviewer-token-123456':'qa-1',
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
          'dependencies':[],'priority':80,'owner':'developer'}
        self.post({'action':'CREATE_PROJECT_TASK','task':task})
        self.assertEqual(self.post({'action':'START_TEST_ONLY_TASK',
          'task_id':'task-journey','attempt_id':'attempt-1'})['state'],'STARTED')
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
        roles=(('executor','EXECUTOR',True,'developer-1'),
               ('reviewer','REVIEWER',False,'qa-1'),
               ('acceptor','ACCEPTOR',False,'acceptor-1'))
        for role,phase,writer,principal in roles:
            self.post({'action':'CREATE_ROLE','config':{'role_id':role,
              'version':'v1','phase':phase,'capabilities':['code'],
              'writer_allowed':writer,'enabled':True}})
            self.post({'action':'ASSIGN_ROLE','task_id':'task-journey',
              'role_id':role,'role_version':'v1','principal_id':principal,
              'allow_paid':False})
        queued=self.post({'action':'QUEUE_REQUEST','task_id':'task-journey',
          'role_id':'executor','messages':[{'role':'user','content':'build'}],
          'idempotency_key':'journey-execute'})
        self.assertEqual(self.post({'action':'RUN_SCHEDULER_ONCE'})['state'],
          'SUCCEEDED')
        checklist=self.post({'action':'REGISTER_CHECKLIST','task_id':'task-journey',
          'items':[{'id':'journey-core','required':True,'result':'PASS',
          'evidence':'fixture-log'}]})['content_sha256']
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
          'passed':True},'reviewer-token-123456')['state'],'REVIEW_PASSED')
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
