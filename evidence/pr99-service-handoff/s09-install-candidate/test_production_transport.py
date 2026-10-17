import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.parse
import production_transport as t
import production_start as host


class RpcFixture:
 def __init__(self):
  self.calls=[];self.reply={'InvokeId':'t-fixture-1'};self.status='Success';self.exit=0;self.output=None
 def __call__(self,endpoint,version,action,credentials,**params):
  self.calls.append((endpoint,version,action,params))
  if action=='RunCommand':return self.reply
  return {'InvocationResult':{'InstanceId':t.INSTANCE,'InvokeId':'t-fixture-1',
          'InvocationStatus':self.status,'ExitCode':self.exit,'Output':self.output}}


class TransportTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.rpc=RpcFixture();self.source='a'*64;self.operation='b'*64
  self.adapter=t.DomesticStartTransport(self.root,self.rpc,('fixture-key','fixture-secret','fixture-token'),self.source,self.operation)
  receipt={'status':'THREE_APPS_STARTED_NO_TRAFFIC_CUTOVER','production_cutover':False,
           'services_installed':True,'health':{r:200 for r in host.UNITS}}
  self.rpc.output=json.dumps({'operation_id':self.operation,'source_sha256':self.source,'host':host.HOST,'uid':0,'receipt':receipt})
 def test_pinned_rpc_load_no_private_environment_or_network(self):
  with patch.dict(os.environ,{},clear=True),patch('urllib.request.build_opener',side_effect=AssertionError('network')):
   rpc=t.load_original_rpc()
   self.assertTrue(callable(rpc));self.assertNotIn('CN_CREDENTIALS',rpc.__globals__)
 def test_original_rpc_actual_signer_with_injected_http(self):
  rpc=t.load_original_rpc();captured=[]
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):return False
   def read(self,limit):return b'{"InvokeId":"t-fixture"}'
  class Opener:
   def open(self,request,timeout):captured.append(request);return Response()
  with patch('urllib.request.build_opener',return_value=Opener()):
   result=rpc(t.ENDPOINT,'2020-06-01','RunCommand',('fake-key','fake-secret','fake-token'),InstanceId=t.INSTANCE)
  fields=urllib.parse.parse_qs(captured[0].data.decode())
  self.assertEqual(result,{'InvokeId':'t-fixture'});self.assertEqual(fields['Action'],['RunCommand'])
  self.assertIn('Signature',fields);self.assertEqual(fields['SecurityToken'],['fake-token'])
 def test_original_rpc_source_drift_blocks(self):
  with patch.object(t,'LEGACY_SHA','f'*64),self.assertRaisesRegex(t.Hold,'LEGACY_RPC_SOURCE_DRIFT'):t.load_original_rpc()
 def test_fixed_command_has_no_untrusted_input_and_no_large_payload(self):
  shell=self.adapter.shell
  self.assertLess(len(shell.encode()),6000);self.assertIn(str(host.RELEASE/'production_start.py'),shell)
  self.assertIn("r=n['start']()",shell);self.assertIn('hashlib.sha256(b).hexdigest()==SOURCE_SHA',shell)
  self.assertNotIn('ALIYUN_ACCESS_KEY',shell)
  for bad in ('../path','; echo unsafe','A'*64):
   with self.assertRaises(t.Hold):t.command(bad,self.operation)
 def test_dispatch_intent_precedes_real_rpc_call(self):
  real=self.rpc
  def rpc(*args,**kwargs):
   self.assertEqual(t.private_read(self.root/'cloud-start.intent.json'),self.adapter.intent)
   return real(*args,**kwargs)
  self.adapter.rpc=rpc;result=self.adapter.dispatch_once()
  self.assertEqual(result['status'],'DISPATCHED_QUERY_ONLY')
  self.assertEqual(self.rpc.calls[0][0],t.ENDPOINT)
  self.assertEqual(self.rpc.calls[0][3]['InstanceId'],t.INSTANCE)
 def test_dispatch_replay_and_second_operation_blocked(self):
  self.adapter.dispatch_once()
  with self.assertRaises(FileExistsError):self.adapter.dispatch_once()
  second=t.DomesticStartTransport(self.root,self.rpc,('x','y','z'),self.source,'c'*64)
  with self.assertRaises(FileExistsError):second.dispatch_once()
  self.assertEqual(len(self.rpc.calls),1)
 def test_timeout_before_invoke_never_redispatches(self):
  with patch.object(self.adapter,'rpc',side_effect=TimeoutError('secret')):
   with self.assertRaisesRegex(t.Hold,'DISPATCH_UNKNOWN'):self.adapter.dispatch_once()
  self.assertEqual(self.adapter.query_only()['status'],'UNKNOWN_NO_INVOKE_NO_REPLAY')
  self.assertEqual(self.rpc.calls,[])
  self.assertNotIn('secret',(self.root/'cloud-start.intent.json').read_text())
 def test_missing_invoke_is_unknown(self):
  self.rpc.reply={}
  with self.assertRaisesRegex(t.Hold,'DISPATCH_UNKNOWN'):self.adapter.dispatch_once()
  self.assertEqual(self.adapter.query_only()['status'],'UNKNOWN_NO_INVOKE_NO_REPLAY')
 def test_invoke_persistence_failure_consumes_dispatch(self):
  real=t.persist
  def persist(path,value):
   if path.name.endswith('invocation.json'):raise OSError('disk')
   real(path,value)
  with patch.object(t,'persist',persist),self.assertRaisesRegex(t.Hold,'DISPATCH_UNKNOWN'):self.adapter.dispatch_once()
  self.assertEqual(len(self.rpc.calls),1)
  self.assertEqual(self.adapter.query_only()['status'],'UNKNOWN_NO_INVOKE_NO_REPLAY')
 def test_pending_query_only(self):
  self.adapter.dispatch_once();self.rpc.status='Running'
  self.assertEqual(self.adapter.query_only()['status'],'PENDING_QUERY_ONLY')
  self.assertEqual([x[2] for x in self.rpc.calls],['RunCommand','DescribeInvocationResult'])
 def test_success_plain_and_base64_receipt(self):
  self.adapter.dispatch_once();self.rpc.output=base64.b64encode(self.rpc.output.encode()).decode()
  result=self.adapter.query_only();self.assertEqual(result['status'],'THREE_APPS_STARTED_NO_TRAFFIC_CUTOVER')
  before=len(self.rpc.calls);self.assertEqual(self.adapter.query_only(),result);self.assertEqual(len(self.rpc.calls),before)
 def test_failure_is_not_assumed_no_effect(self):
  self.adapter.dispatch_once();self.rpc.status='Failed';self.rpc.exit=2
  self.assertEqual(self.adapter.query_only()['status'],'REMOTE_FAILED_QUERY_HOST_STATE_NO_REPLAY')
 def test_foreign_identity_even_pending_is_unknown(self):
  self.adapter.dispatch_once()
  with patch.object(self.adapter,'rpc',return_value={'InvocationResult':{'InstanceId':'other','InvokeId':'t-fixture-1','InvocationStatus':'Running'}}):
   self.assertEqual(self.adapter.query_only()['status'],'UNKNOWN_QUERY_ONLY_NO_REPLAY')
 def test_wrong_output_nonce_is_unknown(self):
  self.adapter.dispatch_once();r=json.loads(self.rpc.output);r['operation_id']='c'*64;self.rpc.output=json.dumps(r)
  self.assertEqual(self.adapter.query_only()['status'],'UNKNOWN_QUERY_ONLY_NO_REPLAY')
 def test_wrong_source_or_cutover_claim_is_unknown(self):
  self.adapter.dispatch_once();r=json.loads(self.rpc.output);r['receipt']['production_cutover']=True;self.rpc.output=json.dumps(r)
  self.assertEqual(self.adapter.query_only()['status'],'UNKNOWN_QUERY_ONLY_NO_REPLAY')
 def test_cached_result_all_fields_validated_without_rpc(self):
  self.adapter.dispatch_once();self.adapter.query_only()
  path=self.root/'cloud-start.result.json';original=t.private_read(path);before=len(self.rpc.calls)
  mutations=[lambda x:x.update(status='PRODUCTION_MIGRATION_COMPLETE'),
             lambda x:x.update(source_sha256='f'*64),lambda x:x.update(production_cutover=True),
             lambda x:x.update(production_cutover=0),lambda x:x.update(retry_allowed=True),
             lambda x:x.update(upstream_auth_acceptance='PASS'),lambda x:x.update(private_details='must-not-return'),
             lambda x:x.pop('source_sha256')]
  for change in mutations:
   bad=dict(original);change(bad);path.write_bytes(t.encode(bad))
   with self.subTest(bad=bad),self.assertRaises(t.Hold):self.adapter.query_only()
  self.assertEqual(len(self.rpc.calls),before)
 def test_cached_failure_bound_to_source_and_safe_flags(self):
  self.adapter.dispatch_once();self.rpc.status='Failed';self.rpc.exit=2
  result=self.adapter.query_only();self.assertEqual(result['source_sha256'],self.source)
  self.assertFalse(result['production_cutover']);self.assertFalse(result['retry_allowed'])
  before=len(self.rpc.calls);self.assertEqual(self.adapter.query_only(),result);self.assertEqual(len(self.rpc.calls),before)
 def test_private_credential_values_never_persisted(self):
  self.adapter.dispatch_once();self.adapter.query_only()
  text=''.join(p.read_text() for p in self.root.iterdir())
  self.assertNotIn('fixture-secret',text);self.assertNotIn('fixture-token',text);self.assertNotIn('fixture-key',text)
 def test_query_timeout_only_describes(self):
  self.adapter.dispatch_once()
  with patch.object(self.adapter,'rpc',side_effect=TimeoutError):self.assertEqual(self.adapter.query_only()['status'],'UNKNOWN_QUERY_ONLY_NO_REPLAY')
  self.assertEqual(sum(c[2]=='RunCommand' for c in self.rpc.calls),1)
 def test_explicit_credentials_required(self):
  for credentials in (None,(),('a','b',''),['a','b','c']):
   with self.assertRaisesRegex(t.Hold,'EXPLICIT_STS_REQUIRED'):t.DomesticStartTransport(self.root,self.rpc,credentials,self.source,self.operation)
 def test_actual_start_result_integrates_with_transport(self):
  import test_production_durable as durable
  fixture=durable.DurableTests('test_actual_start_files_and_durable_effects');fixture.setUp();self.addCleanup(fixture.doCleanups)
  real=self.rpc
  def rpc(endpoint,version,action,credentials,**params):
   if action=='RunCommand':
    receipt=host.start()
    self.rpc.output=json.dumps({'operation_id':self.operation,'source_sha256':self.source,'host':host.HOST,'uid':0,'receipt':receipt})
   return real(endpoint,version,action,credentials,**params)
  self.adapter.rpc=rpc;self.adapter.dispatch_once();result=self.adapter.query_only()
  self.assertEqual(result['status'],'THREE_APPS_STARTED_NO_TRAFFIC_CUTOVER')
  self.assertTrue((fixture.state/'receipt.json').is_file());self.assertEqual(len(fixture.effects()),7)

if __name__=='__main__':unittest.main()
