"""Original UK Gateway transport only; NOT a Writer, publisher, or task acceptor.

Host-only object. Default disabled; no CLI, credentials, URL, user, session or
shell selection from MCP parameters. Caller must use original task/Writer checks
and original durable dispatch state BEFORE invoke. This does not provide that
ledger or grant/renew authority. Not wired into production loader.
"""
import json,os,pwd,subprocess
CLI='/home/xuanjun_dev/.openclaw/tmp/agent-cli/openclaw'
WORKSPACE='/home/xuanjun_dev/.openclaw/workspace/deliveries/mcp-current-successor-closure-20261031/source-candidate'
SESSION='03fc80d9-56f3-4b1e-b670-cbe7f224f134'
REPOSITORY='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
BRANCH='feature/mcp-pr17-gateway-successor-20261031'
class OriginalGatewayTransport:
 def __init__(self, *, enabled=False):
  self.enabled=enabled;self._invoked=False
 def invoke(self, message, *, admit_original_dispatch):
  if self._invoked:raise ValueError('RECONCILE_EXISTING_DISPATCH_NO_REPLAY')
  if self.enabled is not True:raise ValueError('ORIGINAL_GATEWAY_TRANSPORT_DISABLED')
  if not isinstance(message,str) or not message.strip():raise ValueError('TASK_MESSAGE_REQUIRED')
  if not callable(admit_original_dispatch):raise ValueError('ORIGINAL_HOST_ADMISSION_REQUIRED')
  # Identity must already be correct. Never sudo/su/discover another credential.
  if pwd.getpwuid(os.geteuid()).pw_name!='xuanjun_dev':raise ValueError('ORIGINAL_OS_IDENTITY_REQUIRED')
  # Trusted host callback must validate task/attempt/Writer and persist original
  # dispatch state. If it raises, absolutely no subprocess is started.
  if admit_original_dispatch() is not True:raise ValueError('ORIGINAL_HOST_ADMISSION_NOT_GRANTED')
  self._invoked=True
  argv=[CLI,'agent','--agent','main','--session-key','agent:main:main','--message',message,'--json']
  try:
   result=subprocess.run(argv,cwd=WORKSPACE,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,shell=False)
  except (OSError,subprocess.SubprocessError):
   return {'state':'UNKNOWN','reason':'TRANSPORT_INTERRUPTED_RECONCILE_ORIGINAL_RUN','retry':False,'development_complete':False}
  if result.returncode!=0:
   return {'state':'UNKNOWN','reason':'NONZERO_EXIT_RECONCILE_ORIGINAL_RUN','exit_code':result.returncode,'retry':False,'development_complete':False}
  try:
   value=json.loads(result.stdout)
   meta=value['result']['meta'];agent=meta['agentMeta'];receipt=agent['terminalReceipt']
   run=value['runId']
   if not isinstance(run,str) or not run or receipt['runId']!=run or agent['sessionId']!=SESSION or receipt['sessionId']!=SESSION:raise ValueError()
   if value['status']!='ok' or value['summary']!='completed' or meta['aborted'] is not False or receipt['rerouted'] is not False:raise ValueError()
  except (ValueError,TypeError,KeyError,UnicodeError):
   return {'state':'UNKNOWN','reason':'UNBOUND_RESPONSE_RECONCILE_ORIGINAL_RUN','retry':False,'development_complete':False}
  return {'state':'GATEWAY_TURN_RETURNED','run_id':run,'session_id':SESSION,'response':value,'retry':False,'development_complete':False,'installation_complete':False,'publication':'NOT_PROVEN'}

 def invoke_registered(self, message, *, fence, ticket, caller, operation, admission_check=None):
  """Original writer_operations CAS/CommitLease admission; no new persistent table.

  Used by trusted original Host ONLY after its task/role/material checks.
  Completed Gateway turn remains an unresolved SOURCE operation until original
  source/commit/test readback reconciles effects. It is never a FAKE_TXN receipt.
  """
  import hashlib
  if self.enabled is not True:raise ValueError('ORIGINAL_GATEWAY_TRANSPORT_DISABLED')
  if not isinstance(operation,dict) or operation.get('operation_kind')!='OPENCLAW_DEVELOPMENT_TURN':raise ValueError('ORIGINAL_DEVELOPMENT_OPERATION_REQUIRED')
  if operation.get('request_sha256')!=hashlib.sha256(message.encode()).hexdigest():raise ValueError('EXACT_TASK_MESSAGE_BINDING_REQUIRED')
  if operation.get('expected_before',{}).get('repo')!=REPOSITORY or operation.get('expected_before',{}).get('branch')!=BRANCH:raise ValueError('ORIGINAL_REPOSITORY_BRANCH_REQUIRED')
  if operation.get('resource_key')!='git:'+REPOSITORY+'/'+BRANCH:raise ValueError('EXACT_ORIGINAL_SOURCE_RESOURCE_REQUIRED')
  # Original prepare verifies current ticket/caller/lease/spec/checkpoint/resource
  # and, with the companion Supervisor delta, rejects unresolved same-resource
  # effects even under a new key. PREPARED on crash is not resent here.
  prior=fence.prepare(ticket,caller,operation)
  if prior.get('duplicate'):
   return {'state':prior['state'],'operation_id':operation['operation_id'],'retry':False,'action':'RECONCILE_ORIGINAL_OPERATION','development_complete':False}
  with fence.commit_lease(ticket,caller,operation['operation_id']) as lease:
   def admitted():
    # CommitLease already validated original ticket/caller and persisted dispatch.
    # Recheck Host role/material binding while that original lease is held.
    if admission_check is not None and admission_check() is not True:return False
    row=fence.supervisor.db.execute('SELECT state FROM writer_operations WHERE operation_id=?',(operation['operation_id'],)).fetchone()
    return row is not None and row['state']=='DISPATCHING'
   result=self.invoke(message,admit_original_dispatch=admitted)
   evidence={'kind':'OPENCLAW_TURN_SOURCE_EFFECTS_REQUIRE_READBACK','transport_state':result['state']}
   if result.get('run_id'):evidence['run_id']=result['run_id'];evidence['session_id']=result['session_id']
   lease.unknown(evidence)
  result['operation_id']=operation['operation_id'];result['source_effect_state']='UNKNOWN_RECONCILIATION_REQUIRED'
  return result
