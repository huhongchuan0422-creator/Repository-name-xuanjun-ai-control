"""R1/R2/R3 regression evidence; all credentials/keys are ephemeral fixtures."""
import base64
import copy
import io
import json
import logging
import os
import socket
import struct
import tempfile
import time
import traceback
import unittest
from contextlib import redirect_stdout,redirect_stderr
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from scripts.pr122_customer_core import Denied,Unavailable,canonical,digest
from scripts.pr122_customer_source import TrustedNginxSource,normalize
from scripts.pr122_customer_providers import telegram_send,Providers
from scripts.pr122_customer_review import trust_digest
from scripts import pr122_customer_release as release
from tests import test_pr122_customer_http as http_tests

class SourceTests(unittest.TestCase):
 def test_peer_uid_not_headers_controls_trust(self):
  class Sock:
   family=socket.AF_UNIX
   def getsockopt(self,*a):return struct.pack('3i',123,33,33)
  headers=Message();headers['X-Xuanjun-Client-IP']='198.51.100.1';headers['X-Forwarded-For']='203.0.113.99'
  self.assertEqual(TrustedNginxSource(33)(Sock(),headers),'198.51.100.1')
  with self.assertRaises(Denied):TrustedNginxSource(34)(Sock(),headers)
  Sock.family=socket.AF_INET
  with self.assertRaises(Denied):TrustedNginxSource(33)(Sock(),headers)
  Sock.family=socket.AF_UNIX;headers['X-Xuanjun-Client-IP']='192.0.2.1'
  with self.assertRaises(Denied):TrustedNginxSource(33)(Sock(),headers)
 def test_origin_normalization_and_spoofed_chain_rejection(self):
  self.assertEqual(normalize('::ffff:192.0.2.1'),'192.0.2.1');self.assertEqual(normalize('2001:db8::99'),normalize('2001:db8::2'))
  for value in ('unknown','1.2.3.4,5.6.7.8',' 192.0.2.1','fe80::1%lo'):
   with self.assertRaises(Denied):normalize(value)

class OriginHttpTests(http_tests.HttpTests):
 def setUp(self):
  super().setUp()
  # A separately injected fixture boundary, not enabled by any production flag.
  original=self.server.RequestHandlerClass
  from scripts.pr122_customer_http import App
  from scripts.pr122_customer_core import Center
  def factory():return Center(self.root,{'v1':self.key},'v1',clock=lambda:self.now,mail_ready=True,scanner=lambda b:True)
  self.server.RequestHandlerClass=App(factory,Providers({}),'https://wenwenwenyiyiyi.work','deploy/pr122-customer-center/ui',source_identity=lambda c,h:normalize(h['X-Fixture-Origin'])).handler()
 def test_40_anonymous_requests_cannot_consume_other_client_login(self):
  for i in range(40):self.assertEqual(self.request('api/request_reset',{'email':'unknown'+str(i)+'@example.com'},{'X-Fixture-Origin':'192.0.2.1'})[0],200)
  self.assertEqual(self.request('api/request_reset',{'email':'unknown40@example.com'},{'X-Fixture-Origin':'192.0.2.1'})[0],403)
  self.assertEqual(self.request('api/login',{'email':'owner@example.com','password':'correct-password-123'},{'X-Fixture-Origin':'198.51.100.2'})[0],200)
  self.assertEqual(self.request('api/request_reset',{'email':'member@example.com'},{'X-Fixture-Origin':'198.51.100.3'})[0],200)
for name in dir(http_tests.HttpTests):
 if name.startswith('test_'):setattr(OriginHttpTests,name,None)

class ReviewTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name);self.key=Ed25519PrivateKey.generate()
  self.plan={'manifest_sha256':'1'*64,'source_commit':'a'*40,'source_tree':'b'*40,'artifact_tar_sha256':'2'*64,'scope_sha256':'3'*64,'telegram_credential_evidence_sha256':'4'*64}
  self.approval={**{k:v for k,v in self.plan.items() if k!='telegram_credential_evidence_sha256'},'transaction':release.TXN,'decision':'INSTALL_APPROVED','plan_sha256':None,'max_executions':1,'rollback_approved':True,'issued_unix':int(time.time())-1,'expires_unix':int(time.time())+500,'review_comment_id':5,'ci_run_id':6,'artifact_id':7,'artifact_zip_sha256':'5'*64}
  self.payload={**{k:v for k,v in self.approval.items() if k in ('source_commit','source_tree','manifest_sha256','artifact_tar_sha256','artifact_zip_sha256','artifact_id','ci_run_id')},'decision':'AUDIT_PASS','reviewer_principal':'independent-task5','source_writer_principal':'work-writer','scope_sha256':'3'*64,'findings':{x:{'state':'CLOSED','evidence_sha256':['4'*64]} for x in ('R1','R2','R3')},'issued_unix':int(time.time())-1,'expires_unix':int(time.time())+1000}
  pub=base64.b64encode(self.key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
  self.trust={'schema':1,'source_writer_principal':'work-writer','reviewers':{'task5-key':{'public_key_b64':pub,'principal':'independent-task5','status':'ACTIVE','custody_evidence_sha256':'6'*64}},'revoked_review_ids':[],'install_anchors':{}}
 def prepare(self,*,sign=True):
  self.plan['review_trust_sha256']=trust_digest(self.trust);self.approval['plan_sha256']=digest(canonical(self.plan))
  sig=self.key.sign(canonical(self.payload)) if sign else b'0'*64
  envelope={'payload':self.payload,'signature':base64.b64encode(sig).decode(),'reviewer_key_id':'task5-key'}
  def comment(cid,body):return {'id':cid,'user':{'login':release.OWNER},'issue_url':'https://api.github.com/repos/x/y/issues/122','body':body}
  self.comments={4:comment(4,'XUANJUN_CUSTOMER_INSTALL\n'+json.dumps(self.approval)),5:comment(5,'XUANJUN_CUSTOMER_REVIEW_V2\n'+json.dumps(envelope))}
  self.trust['install_anchors']={release.TXN:{'install_comment_id':4,'install_body_sha256':digest(self.comments[4]['body'].encode()),'review_comment_id':5,'review_body_sha256':digest(self.comments[5]['body'].encode()),'custody_evidence_sha256':'6'*64}}
  p=self.root/'INDEPENDENT_REVIEW_TRUST.json';p.write_bytes(canonical(self.trust));p.chmod(0o600)
 def fetch(self,path):
  if path.startswith('issues/comments/'):return self.comments[int(path.rsplit('/',1)[1])]
  if path=='actions/runs/6':return {'conclusion':'success','head_sha':'a'*40,'path':'.github/workflows/pr122-customer-center.yml','event':'push'}
  if path.startswith('git/commits/'):return {'sha':'a'*40,'tree':{'sha':'b'*40}}
  if path=='actions/artifacts/7':return {'id':7,'expired':False,'digest':'sha256:'+'5'*64,'workflow_run':{'id':6,'head_sha':'a'*40}}
  raise ValueError(path)
 def gate(self):
  with patch.object(release,'CONFIG',self.root):return release.gate(4,self.plan,self.fetch)
 def test_separate_enrolled_signature_complete_scope_and_real_artifact_pass(self):
  self.prepare();self.assertEqual(self.gate()['artifact_id'],7)
 def test_fake_role_or_unenrolled_key_cannot_authorize(self):
  self.prepare(sign=False)
  with self.assertRaises(Denied):self.gate()
  self.trust['reviewers']['task5-key']['principal']='work-writer';self.prepare()
  with self.assertRaises(Denied):self.gate()
 def test_old_edited_revoked_or_open_findings_fail(self):
  for mutation in ('edited','revoked','open','expired','scope','artifact'):
   with self.subTest(kind=mutation):
    self.setUp();self.prepare()
    if mutation=='edited':self.comments[5]['body']+=' '
    elif mutation=='revoked':self.trust['revoked_review_ids']=[5];self.prepare()
    elif mutation=='open':self.payload['findings']['R2']['state']='OPEN';self.prepare()
    elif mutation=='expired':self.payload['expires_unix']=1;self.prepare()
    elif mutation=='scope':self.payload['scope_sha256']='f'*64;self.prepare()
    else:self.payload['artifact_tar_sha256']='f'*64;self.prepare()
    with self.assertRaises(Denied):self.gate()
 def test_missing_owner_trust_never_falls_back_to_github_role(self):
  self.prepare();(self.root/'INDEPENDENT_REVIEW_TRUST.json').unlink()
  with self.assertRaises((OSError,Denied)):self.gate()

class TelegramPathTests(unittest.TestCase):
 def test_direct_tls_no_proxy_debug_keylog_or_secret_exception(self):
  token='123456:FIXTURE_SECRET_TOKEN';events=[];output=io.StringIO()
  class Connection:
   def __init__(self,host,port,timeout,context):events.append((host,port,context.check_hostname,context.keylog_filename))
   def set_debuglevel(self,value):events.append(('debug',value))
   def request(self,method,path,body,headers):raise OSError('diagnostic includes '+token+' '+path)
   def close(self):pass
  with patch.dict(os.environ,{'HTTPS_PROXY':'http://untrusted.invalid:8080','SSLKEYLOGFILE':'/tmp/not-allowed-key-log'}),redirect_stdout(output),redirect_stderr(output):
   try:telegram_send(token,'123','hello',connect=Connection)
   except Unavailable as e:
    self.assertIsNone(e.__context__);self.assertNotIn(token,repr(e));self.assertNotIn(token,''.join(traceback.format_exception(e)))
   else:self.fail('expected sanitized failure')
  self.assertEqual(output.getvalue(),'');self.assertEqual(events[0],('api.telegram.org',443,True,None));self.assertIn(('debug',0),events)
 def test_redirect_or_token_in_response_never_escapes(self):
  token='123456:FIXTURE_SECRET_TOKEN'
  for status,data in [(302,{}),(200,{'ok':True,'result':{'message_id':token}}),(200,{'ok':False,'description':token})]:
   class Connection:
    def __init__(self,*a,**k):pass
    def set_debuglevel(self,v):pass
    def request(self,*a,**k):pass
    def getresponse(self):return type('Response',(),{'status':status,'read':lambda s,n:canonical(data)})()
    def close(self):pass
   with self.assertRaisesRegex(Unavailable,'^TELEGRAM_REQUEST_UNCONFIRMED$'):telegram_send(token,'123','hello',connect=Connection)
