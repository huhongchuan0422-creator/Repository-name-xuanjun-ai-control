"""Explicitly invoked domestic-only SWAS start/query adapter; no automatic entry.

Reuses the pinned original RPC signer without importing its consumed S07 batch or
reading environment credentials. No code here provisions credentials/permissions.
Use requires a persistent PRIVATE controller directory and a reviewed, pre-staged
helper at the exact final-release path. That staging/authorization is not inferred.
No workflow invokes this adapter. CLI always holds. All tests inject a fake RPC.
"""
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat

import production_start as start

LEGACY_PATH=Path(__file__).parent.parent/'aliyun-execution'/'s07_private_coordinator.py'
LEGACY_SHA='8bc8d13d9be01e2c695608ee975d30914eab9c7eda5144c8d7cba0051a3fa37a'
REGION='cn-shanghai'
INSTANCE='3a22c458934142eea89ec6e3bf481a57'
ENDPOINT='swas.cn-shanghai.aliyuncs.com'
HELPER=start.RELEASE/'production_start.py'
SHA=re.compile(r'[0-9a-f]{64}')
INVOKE=re.compile(r'[A-Za-z0-9_-]{1,180}')


class Hold(RuntimeError):pass

def require(value,code):
 if not value:raise Hold(code)

def encode(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()


def load_original_rpc():
 """Reuse only original audited definitions. No historical top-level initializer."""
 raw=LEGACY_PATH.read_bytes();require(sha(raw)==LEGACY_SHA,'LEGACY_RPC_SOURCE_DRIFT')
 source=ast.parse(raw)
 functions={'Hold','safe','quote','NoRedirect','rpc'}
 constants={'UK','KR','CN','HOSTS'}
 selected=[]
 for node in source.body:
  if isinstance(node,(ast.Import,ast.ImportFrom)):
   selected.append(node)
  elif isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in functions:
   selected.append(node)
  elif isinstance(node,ast.Assign) and all(isinstance(t,ast.Name) and t.id in constants for t in node.targets):
   selected.append(node)
 scope={'__name__':'pr99_pinned_rpc_only'}
 exec(compile(ast.Module(body=selected,type_ignores=[]),str(LEGACY_PATH),'exec'),scope)
 require('CN_CREDENTIALS' not in scope and 'main' not in scope and 'remote' not in scope,'LEGACY_BATCH_NOT_IMPORTED')
 return scope['rpc']


def private_read(path):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  st=os.fstat(fd)
  require(stat.S_ISREG(st.st_mode) and st.st_uid==os.geteuid() and
          stat.S_IMODE(st.st_mode)==0o600 and st.st_nlink==1 and st.st_size<=100000,'TRANSPORT_RECORD_IDENTITY')
  with os.fdopen(os.dup(fd),'rb') as f:raw=f.read(100001)
  require(len(raw)==st.st_size,'TRANSPORT_RECORD_SIZE')
  try:value=json.loads(raw)
  except (ValueError,UnicodeError):raise Hold('TRANSPORT_RECORD_CORRUPT_UNKNOWN') from None
  require(raw==encode(value),'TRANSPORT_RECORD_ENCODING')
  return value
 finally:os.close(fd)


def persist(path,value):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  with os.fdopen(fd,'wb',closefd=False) as f:f.write(encode(value));f.flush();os.fsync(f.fileno())
 finally:os.close(fd)
 fd=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(fd)
 finally:os.close(fd)


def command(source_sha,operation_id):
 require(type(source_sha) is str and SHA.fullmatch(source_sha),'SOURCE_SHA')
 require(type(operation_id) is str and SHA.fullmatch(operation_id),'OPERATION_ID')
 # No arbitrary path, action, host, module, code or command can be supplied.
 program="""import os,stat,hashlib,json
from pathlib import Path
assert os.geteuid()==0 and os.uname().nodename==HOST
p=Path(HELPER)
for a in (p,*p.parents):
 s=a.lstat();assert not stat.S_ISLNK(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022
fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
with os.fdopen(fd,'rb') as f:
 s=os.fstat(f.fileno());assert stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=100000
 b=f.read(100001)
assert hashlib.sha256(b).hexdigest()==SOURCE_SHA
n={'__name__':'reviewed_start','__file__':str(p)}
exec(compile(b,str(p),'exec'),n)
r=n['start']()
print(json.dumps({'operation_id':OPERATION_ID,'source_sha256':SOURCE_SHA,'host':HOST,'uid':0,'receipt':r},sort_keys=True))
"""
 bindings='HOST='+repr(start.HOST)+'\nHELPER='+repr(str(HELPER))+'\nSOURCE_SHA='+repr(source_sha)+'\nOPERATION_ID='+repr(operation_id)+'\n'
 shell="#!/bin/sh\nset -eu\n/usr/bin/python3.11 -I -B - <<'PR99PY'\n"+bindings+program+'PR99PY\n'
 require(len(shell.encode())<=6000,'COMMAND_SIZE')
 return shell


class DomesticStartTransport:
 """Persistent at-most-once dispatch using the existing RPC protocol.

    The supplied RPC and STS credentials are explicit dependencies. Authorization
    must be supplied via the existing independent private host admission; the host
    helper checks its new exact source hash. This adapter is not an admission issuer.
    A runner-local ephemeral directory is NOT durable cross-run storage.
 """
 def __init__(self,state,rpc,credentials,source_sha,operation_id):
  require(callable(rpc),'EXPLICIT_RPC_REQUIRED')
  require(type(credentials) is tuple and len(credentials)==3 and
          all(type(v) is str and v and '\n' not in v and '\r' not in v for v in credentials),'EXPLICIT_STS_REQUIRED')
  self.state=Path(state)
  for p in (self.state,*self.state.parents):require(not p.is_symlink(),'TRANSPORT_PARENT_SYMLINK')
  st=self.state.stat();require(stat.S_ISDIR(st.st_mode) and st.st_uid==os.geteuid() and stat.S_IMODE(st.st_mode)==0o700,'TRANSPORT_DIRECTORY')
  self.rpc,self.credentials=rpc,credentials
  self.source_sha,self.operation_id=source_sha,operation_id
  self.shell=command(source_sha,operation_id)
  self.intent={'operation_id':operation_id,'source_sha256':source_sha,'command_sha256':sha(self.shell.encode()),
               'region':REGION,'instance':INSTANCE,'host':start.HOST,'action':'PR99_FINAL_DOMESTIC_START_V1'}

 def dispatch_once(self):
  # Global claim in this supplied transaction directory. An existing or partial
  # claim prohibits all future dispatch, including different operation IDs.
  persist(self.state/'cloud-start.intent.json',self.intent)
  try:
   out=self.rpc(ENDPOINT,'2020-06-01','RunCommand',self.credentials,
       RegionId=REGION,InstanceId=INSTANCE,Type='RunShellScript',WorkingUser='root',WorkingDir='/root',
       Timeout=240,Name='pr99-final-start-'+self.operation_id[:24],CommandContent=self.shell)
   invoke=out.get('InvokeId')
   require(type(invoke) is str and INVOKE.fullmatch(invoke),'DISPATCH_UNKNOWN_NO_INVOKE')
   persist(self.state/'cloud-start.invocation.json',dict(self.intent,invoke_id=invoke))
  except BaseException:raise Hold('DISPATCH_UNKNOWN_QUERY_ONLY_NO_REPLAY') from None
  return {'status':'DISPATCHED_QUERY_ONLY','invoke_id':invoke,'operation_id':self.operation_id}

 def terminal_result(self,status,invoke):
  require(status in ('THREE_APPS_STARTED_NO_TRAFFIC_CUTOVER','REMOTE_FAILED_QUERY_HOST_STATE_NO_REPLAY'),'SAVED_RESULT_STATUS')
  return {'status':status,'invoke_id':invoke,'operation_id':self.operation_id,
          'source_sha256':self.source_sha,'production_cutover':False,
          'upstream_auth_acceptance':'PENDING','retry_allowed':False}

 def validate_saved_result(self,result,invoke):
  require(type(result) is dict,'SAVED_RESULT_SCHEMA')
  status=result.get('status')
  expected=self.terminal_result(status,invoke)
  require(set(result)==set(expected),'SAVED_RESULT_SCHEMA')
  require(result.get('source_sha256')==self.source_sha and result.get('invoke_id')==invoke and
          result.get('operation_id')==self.operation_id,'SAVED_RESULT_BINDING')
  require(result.get('production_cutover') is False and result.get('retry_allowed') is False and
          result.get('upstream_auth_acceptance')=='PENDING','SAVED_RESULT_FLAGS')
  require(result==expected,'SAVED_RESULT_BINDING')
  return expected

 def query_only(self):
  require(private_read(self.state/'cloud-start.intent.json')==self.intent,'TRANSPORT_INTENT_BINDING')
  if not os.path.lexists(self.state/'cloud-start.invocation.json'):
   return {'status':'UNKNOWN_NO_INVOKE_NO_REPLAY','operation_id':self.operation_id}
  record=private_read(self.state/'cloud-start.invocation.json');invoke=record.get('invoke_id')
  require(type(invoke) is str and INVOKE.fullmatch(invoke) and record==dict(self.intent,invoke_id=invoke),'INVOCATION_BINDING')
  if os.path.lexists(self.state/'cloud-start.result.json'):
   result=private_read(self.state/'cloud-start.result.json')
   return self.validate_saved_result(result,invoke)
  try:
   out=self.rpc(ENDPOINT,'2020-06-01','DescribeInvocationResult',self.credentials,
                RegionId=REGION,InstanceId=INSTANCE,InvokeId=invoke)
   detail=out.get('InvocationResult',{})
   require(detail.get('InstanceId')==INSTANCE and detail.get('InvokeId')==invoke,'REMOTE_RESULT_IDENTITY')
   status=detail.get('InvocationStatus')
   if status in ('Pending','Running','Stopping'):
    return {'status':'PENDING_QUERY_ONLY','invoke_id':invoke,'operation_id':self.operation_id}
   if status!='Success' or type(detail.get('ExitCode')) is not int or detail['ExitCode']!=0:
    require(status in ('Failed','Error','Timeout','Cancelled','Stopped','Success'),'REMOTE_STATUS_UNKNOWN')
    result=self.terminal_result('REMOTE_FAILED_QUERY_HOST_STATE_NO_REPLAY',invoke)
   else:
    output=detail.get('Output');require(type(output) is str and len(output)<=40000,'OUTPUT_SIZE')
    try:r=json.loads(output)
    except (ValueError,UnicodeError):r=json.loads(base64.b64decode(output,validate=True))
    require(type(r) is dict and r.get('host')==start.HOST and type(r.get('uid')) is int and r.get('uid')==0 and
            r.get('source_sha256')==self.source_sha and r.get('operation_id')==self.operation_id,'OUTPUT_BINDING')
    receipt=r.get('receipt',{})
    require(receipt.get('status')=='THREE_APPS_STARTED_NO_TRAFFIC_CUTOVER' and
            receipt.get('production_cutover') is False and receipt.get('services_installed') is True and
            receipt.get('health')=={role:200 for role in start.UNITS},'START_RECEIPT_BINDING')
    result=self.terminal_result('THREE_APPS_STARTED_NO_TRAFFIC_CUTOVER',invoke)
  except BaseException:return {'status':'UNKNOWN_QUERY_ONLY_NO_REPLAY','invoke_id':invoke,'operation_id':self.operation_id}
  result=self.validate_saved_result(result,invoke)
  persist(self.state/'cloud-start.result.json',result)
  return result


if __name__=='__main__':
 raise SystemExit('REVIEW_ONLY_NO_AUTOMATIC_DISPATCH')
