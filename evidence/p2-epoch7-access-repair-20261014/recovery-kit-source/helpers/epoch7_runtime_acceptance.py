"""Concrete bounded read-only runtime access and retained TLS/HTTPS acceptance.

Workers run only through the admitted ExactCommandRunner. No network is used by
compilation, construction or tests. Neither worker calls a model, notifier,
certbot, native admission RPC, or a database operation. Final business/Owner ACK
acceptance is intentionally not inferred from these infrastructure checks.
"""
import copy
import hashlib
import json
import re

from epoch7_command_runner import ExactCommandRunner
from epoch7_complete_approval import sequence_contract, sequence_contract_sha256
from epoch7_recovery_sequence import BoundedDiagnostics, observation
from epoch7_runtime_effects import (MANIFEST, RELEASE, TRANSACTION, ENV, need,
                                    packed, sha, strict_json)

DOMAIN = 'uk.wenwenwenyiyiyi.work'
TLS_ROOT = '/var/lib/xuanjun-development/tls-acme'
TLS_READY = 'READY_ISSUED_AND_RENEWAL_DRYRUN_VERIFIED'
ACTIVATION = '/var/lib/xuanjun-development/activation'
OWNER = '/etc/xuanjun-owner-callback'
CONFIG = '/etc/xuanjun-development'
ROLES = {
    'gateway':('xuanjun-uk-openclaw.service','xuanjun_dev',1002,1002),
    'relay':('xuanjun-p2-gateway-relay.service','xuanjun_dev',1002,1002),
    'dispatcher':('xuanjun-development-dispatcher.service','xuanjun-dispatcher',1003,1003),
    'ledger':('xuanjun-ledger.service','xuanjun-dispatcher',1003,1006),
    'callback':('xuanjun-uk-owner-callback.service','xuanjun-callback',1004,1006),
    'dashboard':('xuanjun-uk-owner-dashboard.service','xuanjun-callback',1004,1006)}

# No dynamic module import, RPC or execution of the inspected runtime files.
# This retains the original service-context preflight's actual UID and pinned
# runtime-file requirements without its git subprocess/native RPC side effects.
ACCESS_WORKER = r'''
import hashlib,json,os,pwd,stat,sys,time

def require(v):
 if not v:raise ValueError('ACCESS_HOLD')
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(b):return hashlib.sha256(b).hexdigest()
def stamp(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def check_deadline(end):require(time.monotonic()<end)
def inspect_rows(rows,end):
 total=0
 owner_private={
  '/etc/xuanjun-owner-callback/owner-callback-auth',
  '/etc/xuanjun-owner-callback/owner-callback-hmac',
  '/etc/xuanjun-owner-callback/owner-user-id',
  '/etc/xuanjun-owner-callback/owner-chat-id',
  '/etc/xuanjun-owner-callback/owner-dashboard-token'}
 for row in rows:
  check_deadline(end);path=row['path'];require(os.path.realpath(path)==path)
  if row['kind']=='directory':
   s=os.lstat(path);require(stat.S_ISDIR(s.st_mode) and os.access(path,os.X_OK,effective_ids=True))
   continue
  fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
  try:
   s=os.fstat(fd);require(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and not s.st_mode&0o022 and s.st_size<=1048576)
   if path in owner_private:require((s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))==(1004,1006,0o600))
   else:require(s.st_uid==0)
   h=hashlib.sha256();size=0
   while True:
    check_deadline(end);b=os.read(fd,min(65536,1048577-size))
    if not b:break
    size+=len(b);total+=len(b);require(size<=1048576 and total<=33554432);h.update(b)
   require(size==s.st_size and h.hexdigest()==row['sha256'] and stamp(s)==stamp(os.fstat(fd))==stamp(os.lstat(path)))
  finally:os.close(fd)
 return len(rows)
def execute(v):
 end=time.monotonic()+35
 require(os.geteuid()==0 and v['mode']=='access')
 i=v['identity'];account=pwd.getpwnam(i['user'])
 require(account.pw_uid==i['uid'])
 actual=sorted(set(os.getgrouplist(i['user'],i['gid'])))
 require(actual==i['nss_groups'])
 require(sorted(set(actual+i['unit_supplementary_groups']+[i['gid']]))==i['groups'])
 os.setgroups(i['groups']);os.setresgid(i['gid'],i['gid'],i['gid']);os.setresuid(i['uid'],i['uid'],i['uid'])
 require(os.getresuid()==(i['uid'],)*3 and os.getresgid()==(i['gid'],)*3 and sorted(os.getgroups())==i['groups'])
 with open('/proc/self/status','rb') as f:status=f.read(65537)
 require(len(status)<=65536);caps=dict(line.split(b':',1) for line in status.splitlines() if line.startswith((b'CapEff:',b'CapPrm:',b'CapAmb:')))
 require(caps.get(b'CapEff',b'1').strip()==b'0000000000000000' and caps.get(b'CapPrm',b'1').strip()==b'0000000000000000' and int(caps.get(b'CapAmb',b'0').strip(),16)==0)
 count=inspect_rows(v['paths'],end)
 return {'schema':1,'phase':'verify_runtime_access','state':'OBSERVED',
         'contract_sha256':digest(canonical(v)),'role':v['role'],'uid':i['uid'],'gid':i['gid'],
         'groups':i['groups'],'paths_verified':count,'file_contents_emitted':False,
         'service_namespace_reproduced':False,'model_calls':0,'database_operations':0}
def main():
 try:
  v=json.loads(sys.argv[1]);print(json.dumps(execute(v),sort_keys=True,separators=(',',':')));return 0
 except BaseException:
  sys.stderr.write('RUNTIME_ACCESS_HOLD\n');return 2
if __name__=='__main__':sys.exit(main())
'''

# Same retained fingerprint encoding and original local unauthenticated route
# checks, with one overall deadline and bounded headers/output. No certbot,
# credential submission, redirect following, DNS lookup or response-body read.
HTTPS_WORKER = r'''
import hashlib,json,os,re,socket,ssl,stat,sys,time

def require(v):
 if not v:raise ValueError('HTTPS_HOLD')
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(b):return hashlib.sha256(b).hexdigest()
def stamp(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def remaining(end):
 value=end-time.monotonic();require(value>0);return value
def read_regular(path,limit,end,private=False):
 require(os.path.realpath(path)==path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  s=os.fstat(fd);require(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_uid==0 and not s.st_mode&0o022 and s.st_size<=limit)
  if private:require(s.st_gid==0 and stat.S_IMODE(s.st_mode)==0o600)
  out=bytearray()
  while True:
   remaining(end);b=os.read(fd,min(65536,limit+1-len(out)))
   if not b:break
   out.extend(b);require(len(out)<=limit)
  require(len(out)==s.st_size and stamp(s)==stamp(os.fstat(fd))==stamp(os.lstat(path)));return bytes(out)
 finally:os.close(fd)
def fingerprint(root,end):
 require(os.path.realpath(root)==root);s=os.lstat(root)
 require(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700)
 rows=[];total=0;pending=[(root,0)]
 while pending:
  parent,depth=pending.pop();remaining(end);require(depth<=32)
  with os.scandir(parent) as listing:
   for item in listing:
    remaining(end);p=parent+'/'+item.name;s=os.lstat(p);rel=os.path.relpath(p,root)
    require(s.st_uid==0 and (stat.S_ISLNK(s.st_mode) or not s.st_mode&0o022))
    if stat.S_ISLNK(s.st_mode):
     target=os.path.realpath(p);require(target.startswith(root+'/') and os.path.isfile(target));rows.append([rel,'LINK',os.readlink(p)])
    elif stat.S_ISDIR(s.st_mode):
     rows.append([rel,'DIR',stat.S_IMODE(s.st_mode)]);pending.append((p,depth+1))
    else:
     raw=read_regular(p,16777216,end);total+=len(raw);require(total<=67108864)
     rows.append([rel,'FILE',stat.S_IMODE(s.st_mode),digest(raw)])
    require(len(rows)<=4096)
 return digest(json.dumps(sorted(rows),separators=(',',':')).encode())
def route(path,v,end):
 raw=socket.socket(socket.AF_INET,socket.SOCK_STREAM);secure=None
 try:
  raw.settimeout(remaining(end));raw.connect(('127.0.0.1',443))
  context=ssl.create_default_context();require(context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED)
  raw.settimeout(remaining(end));secure=context.wrap_socket(raw,server_hostname=v['domain'])
  require(digest(secure.getpeercert(binary_form=True))==v['certificate_sha256'])
  cert=secure.getpeercert();require(ssl.cert_time_to_seconds(cert['notAfter'])>=time.time()+86400)
  request=('GET '+path+' HTTP/1.1\r\nHost: '+v['domain']+'\r\nConnection: close\r\n\r\n').encode('ascii')
  secure.settimeout(remaining(end));secure.sendall(request)
  headers=bytearray()
  while b'\r\n\r\n' not in headers:
   secure.settimeout(remaining(end));chunk=secure.recv(1);require(bool(chunk));headers.extend(chunk);require(len(headers)<=32768)
  lines=bytes(headers).split(b'\r\n');require(len(lines)<=202)
  match=re.fullmatch(br'HTTP/1\.[01] ([0-9]{3}) [^\r\n]*',lines[0]);require(match is not None)
  code=int(match.group(1));require(code in {'/owner/':(200,),'/owner/api/state':(401,403),'/owner-callback':(403,405)}[path]);return code
 finally:
  if secure is not None:secure.close()
  raw.close()
def execute(v):
 end=time.monotonic()+45;require(os.geteuid()==0 and v['mode']=='https')
 raw=read_regular(v['journal'],1048576,end,private=True);require(digest(raw)==v['journal_sha256']);record=json.loads(raw.decode())
 require(record['state']=='READY_ISSUED_AND_RENEWAL_DRYRUN_VERIFIED' and record['certificate_sha256']==v['certificate_sha256'] and record['fingerprint']==v['tree_sha256'])
 require(digest(canonical(record['config']))==v['config_sha256'] and record['config']['release_sha256']==v['manifest_sha256'])
 require(fingerprint(v['root'],end)==v['tree_sha256'])
 statuses={path:route(path,v,end) for path in ('/owner/','/owner/api/state','/owner-callback')}
 require(read_regular(v['journal'],1048576,end,private=True)==raw and fingerprint(v['root'],end)==v['tree_sha256'])
 return {'schema':1,'phase':'post_install_checks','state':'OBSERVED','contract_sha256':digest(canonical(v)),
         'retained_certificate_ready':True,'served_certificate_sha256':v['certificate_sha256'],'https_statuses':statuses,
         'new_issue_calls':0,'renew_calls':0,'dry_run_calls':0,'model_calls':0,'notification_calls':0,
         'owner_ack':'PENDING','business_e2e':'PENDING','production_acceptance':'PENDING'}
def main():
 try:
  v=json.loads(sys.argv[1]);print(json.dumps(execute(v),sort_keys=True,separators=(',',':')));return 0
 except BaseException:
  sys.stderr.write('RUNTIME_HTTPS_HOLD\n');return 2
if __name__=='__main__':sys.exit(main())
'''


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


# Fixed local Python import closure of the six actual entrypoint/previously
# checked module roots. Includes literal function-local imports, never stdlib,
# arbitrary payloads or import execution. Regression recomputes this from the
# exact authenticated public runtime source; manifests independently pin bytes.
READ_MODULE_ROOTS = {'callback': ('owner_callback_server', 'owner_process_identity'), 'dashboard': ('owner_dashboard', 'native_peer_identity'), 'dispatcher': ('p2_service_context_preflight', 'development_service', 'native_pipeline_runtime', 'native_gateway_controller'), 'gateway': ('native_ledger_bridge', 'native_peer_identity'), 'ledger': ('ledger_service', 'native_peer_identity'), 'relay': ('p2_gateway_relay',)}
READ_MODULE_CLOSURE = {
    'callback': tuple('activation_control dependency_evidence_view ledger_read_client ledger_read_projection ledger_read_transport ledger_server_identity native_ledger_operations native_peer_identity owner_callback_server owner_dashboard owner_process_identity run_usage_projection task_cost_projection uk_owner_callback_core'.split()),
    'dashboard': tuple('activation_control dependency_evidence_view ledger_read_client ledger_read_projection ledger_read_transport ledger_server_identity native_peer_identity owner_dashboard run_usage_projection task_cost_projection'.split()),
    'dispatcher': tuple('activation_control codex_worker development_loop development_pipeline development_service execution_ledger execution_supervision ledger_read_projection ledger_read_transport ledger_server_identity native_child_adapter native_gateway_controller native_github_notifier native_pipeline_runtime native_snapshot_access p2_service_context_preflight task_supervisor_inventory_adapter'.split()),
    'gateway': tuple('activation_control ledger_read_projection ledger_read_transport ledger_server_identity native_ledger_bridge native_peer_identity owner_feishu_bridge_cycle owner_feishu_history owner_feishu_https owner_feishu_transport'.split()),
    'ledger': tuple('activation_control codex_worker dependency_evidence_view development_loop development_pipeline development_service execution_ledger execution_supervision ledger_read_client ledger_read_projection ledger_read_transport ledger_server_identity ledger_service native_child_adapter native_github_notifier native_ledger_operations native_peer_identity native_pipeline_runtime native_snapshot_access owner_dashboard owner_feishu_claim_guard owner_feishu_ledger_endpoint owner_process_identity run_usage_projection task_cost_projection task_supervisor_inventory_adapter uk_owner_callback_core'.split()),
    'relay': tuple('activation_control ledger_read_projection ledger_read_transport ledger_server_identity native_child_adapter native_gateway_controller p2_gateway_relay'.split()),
}


def required_paths():
    """Exact reviewed set; hashes are caller-supplied installed-byte evidence."""
    common={RELEASE:'directory',RELEASE+'/stage1':'directory',
            '/opt/xuanjun-control-releases':'directory'}
    by_role={
      'gateway':['stage1/native_ledger_bridge.py','stage1/native_peer_identity.py',
                 CONFIG+'/p2-native-controller.binding.json',CONFIG+'/p2-native-ledger-client.json',
                 CONFIG+'/p2-ledger-server-identity.json'],
      'relay':['stage1/p2_gateway_relay.py',CONFIG+'/p2-gateway-relay.json'],
      'dispatcher':['stage1/p2_service_context_preflight.py','stage1/native_pipeline_runtime.py',
                    'stage1/native_gateway_controller.py','stage1/native_gateway_controller.py.json',
                    CONFIG+'/dispatcher.json',CONFIG+'/p2-native-ledger-client.json',ACTIVATION+'/active.json'],
      'ledger':['stage1/ledger_service.py','stage1/native_peer_identity.py',CONFIG+'/p2-native-ledger-client.json',
                CONFIG+'/p2-ledger-server-identity.json',ACTIVATION+'/active.json'],
      'callback':['stage1/owner_callback_server.py','stage1/owner_process_identity.py',CONFIG+'/p2-owner-process-identity.json',
                  OWNER+'/owner-callback-auth',OWNER+'/owner-callback-hmac',
                  OWNER+'/owner-user-id',OWNER+'/owner-chat-id',ACTIVATION+'/active.json'],
      'dashboard':['stage1/owner_dashboard.py','stage1/owner_dashboard.html','stage1/native_peer_identity.py',
                   CONFIG+'/p2-ledger-server-identity.json',OWNER+'/owner-dashboard-token',ACTIVATION+'/active.json']}
    result={}
    for role,paths in by_role.items():
        result[role]=dict(common)
        for path in paths:result[role][RELEASE+'/'+path if path.startswith('stage1/') else path]='file'
        for name in READ_MODULE_CLOSURE[role]:result[role][RELEASE+'/stage1/'+name+'.py']='file'
    return result


def validate_access(rows):
    need(type(rows) is list and len(rows)==len(ROLES) and
         {r.get('role') for r in rows}==set(ROLES), 'ACCEPTANCE_ACCESS_ROLES')
    expected=required_paths();result=[]
    for row in sorted(rows,key=lambda r:r['role']):
        need(type(row) is dict and set(row)=={'role','identity','paths'}, 'ACCEPTANCE_ACCESS_FIELDS')
        role=row['role'];identity=row['identity'];unit,user,uid,gid=ROLES[role]
        need(type(identity) is dict and set(identity)=={'unit','user','uid','gid','nss_groups','unit_supplementary_groups','groups'}
             and (identity['unit'],identity['user'],identity['uid'],identity['gid'])==(unit,user,uid,gid),
             'ACCEPTANCE_EXACT_SERVICE_IDENTITY')
        for name in ('nss_groups','unit_supplementary_groups','groups'):
            value=identity[name]
            need(type(value) is list and len(value)<=32 and
                 all(type(i) is int and 0<i<65536 for i in value) and value==sorted(set(value)),
                 'ACCEPTANCE_EXACT_GROUPS')
        need(identity['groups']==sorted(set(identity['nss_groups']+identity['unit_supplementary_groups']+[gid])),
             'ACCEPTANCE_GROUP_UNION')
        paths=row['paths']
        need(type(paths) is list and len(paths)==len(expected[role]) and
             {p.get('path') for p in paths}==set(expected[role]), 'ACCEPTANCE_EXACT_PATH_SET')
        for p in paths:
            need(type(p) is dict and set(p)=={'path','kind','sha256'} and p['kind']==expected[role][p['path']],
                 'ACCEPTANCE_PATH_SCHEMA')
            need(p['sha256'] is None if p['kind']=='directory' else
                 type(p['sha256']) is str and re.fullmatch(r'[0-9a-f]{64}',p['sha256']),
                 'ACCEPTANCE_INSTALLED_FILE_PIN')
        result.append(copy.deepcopy(dict(row,paths=sorted(paths,key=lambda p:p['path']))))
    return result


def validate_tls(value):
    need(type(value) is dict and set(value)=={'journal','journal_sha256','root','tree_sha256',
         'certificate_sha256','config_sha256','domain','manifest_sha256'}, 'ACCEPTANCE_TLS_FIELDS')
    need(value['journal']==TRANSACTION+'/tls-lifecycle.json' and value['root']==TLS_ROOT and
         value['domain']==DOMAIN and value['manifest_sha256']==MANIFEST, 'ACCEPTANCE_EXACT_TLS')
    for key in ('journal_sha256','tree_sha256','certificate_sha256','config_sha256'):
        need(type(value[key]) is str and re.fullmatch(r'[0-9a-f]{64}',value[key]), 'ACCEPTANCE_TLS_PIN')
    return copy.deepcopy(value)


def compile_acceptance_contract(context,access_rows,tls):
    """Pure finite reviewed input; no measurements or authority are fabricated."""
    # Plan material is frozen before GitHub assigns the genuine review ID.
    # Only this reviewed pin is ID-neutral; execution inputs/results below retain
    # the full actual context_sha256, authenticated by the complete verifier.
    return {'sequence_contract_sha256':sequence_contract_sha256(context),
            'access':validate_access(access_rows),
            'tls':validate_tls(tls),'access_worker_sha256':sha(ACCESS_WORKER.encode()),
            'https_worker_sha256':sha(HTTPS_WORKER.encode())}


class RuntimeAcceptanceChecks(object):
    """Concrete callbacks for Epoch7RuntimeEffects; all expected input is finite.

    expected_contract_sha256 must be reviewed alongside the kit. Access file
    hashes must describe installed rendered bytes at QUIESCED, not manifest
    pre-render bytes. TLS journal hash describes the metadata-only rebound READY
    journal. These are measurements/bindings, never an authorization by themselves.
    """
    def __init__(self,context,access_rows,tls,live_check,diagnostics,
                 expected_contract_sha256,runner_factory=ExactCommandRunner):
        need(callable(live_check) and isinstance(diagnostics,BoundedDiagnostics), 'ACCEPTANCE_ADAPTERS')
        # Pure compilation also accepts a neutral preapproval contract; concrete
        # execution requires the full actual-ID context and a valid full hash.
        sequence_contract(context)
        need('review_id' in context and 'context_sha256' in context, 'ACCEPTANCE_ADMITTED_CONTEXT_REQUIRED')
        self.context=copy.deepcopy(context);self.access=validate_access(access_rows);self.tls=validate_tls(tls)
        need(context['runtime_manifest_sha256']==MANIFEST, 'ACCEPTANCE_CONTEXT')
        self.expected=compile_acceptance_contract(context,self.access,self.tls)
        need(sha(canonical(self.expected))==expected_contract_sha256, 'ACCEPTANCE_REVIEWED_CONTRACT')
        self.binding=expected_contract_sha256
        self.admission_context_sha256=context['context_sha256']
        need(len(ACCESS_WORKER)<=8192 and len(HTTPS_WORKER)<=8192, 'ACCEPTANCE_WORKER_BOUND')
        self.live,self.diagnostics=live_check,diagnostics
        self.phase=None;self.done=set();self.results={};self.contract={};self.inputs={}
        for row in self.access:
            key='access_'+row['role'];value=dict(row,mode='access',context_sha256=context['context_sha256'])
            self._add(key,'verify_runtime_access','runtime_access_probe',ACCESS_WORKER,value,40)
        self._add('local_https','post_install_checks','local_https_probe',HTTPS_WORKER,
                  dict(self.tls,mode='https',context_sha256=context['context_sha256']),50)
        self.runner=runner_factory(self.contract,self._live,diagnostics)

    def _add(self,key,phase,operation,code,value,timeout):
        raw=canonical(value).decode('utf-8');need(len(raw)<=8192, 'ACCEPTANCE_INPUT_BOUND')
        self.inputs[key]=value
        self.contract[key]={'phase':phase,'operation':operation,
            'argv':['/usr/bin/python3','-I','-B','-S','-c',code,raw],
            'env':dict(ENV),'cwd':'/','timeout':timeout,'accepted_returncodes':[0]}

    def _live(self):
        return self.live(copy.deepcopy(self.context),self.phase) is True

    def _enter(self,context,diagnostics,phase):
        need(context==self.context and self.context['context_sha256']==self.admission_context_sha256 and
             diagnostics is self.diagnostics and phase not in self.done,
             'ACCEPTANCE_ONE_EXACT_PHASE')
        need(sha(canonical(compile_acceptance_contract(self.context,self.access,self.tls)))==self.binding,
             'ACCEPTANCE_CONTRACT_MUTATED')
        self.done.add(phase);self.phase=phase;need(self._live(), 'ACCEPTANCE_LIVE_GUARD')

    def _run(self,key):
        value=strict_json(self.runner.run(key).stdout)
        need(type(value) is dict and type(value.get('schema')) is int and value['schema']==1 and value.get('phase')==self.phase and
             value.get('state')=='OBSERVED' and value.get('contract_sha256')==sha(canonical(self.inputs[key])),
             'ACCEPTANCE_WORKER_RESULT_BINDING')
        return value

    def verify_runtime_access(self,context,diagnostics):
        self._enter(context,diagnostics,'verify_runtime_access');evidence=[]
        for row in self.access:
            result=self._run('access_'+row['role']);i=row['identity']
            expected={'schema':1,'phase':self.phase,'state':'OBSERVED',
                'contract_sha256':sha(canonical(self.inputs['access_'+row['role']])),
                'role':row['role'],'uid':i['uid'],'gid':i['gid'],'groups':i['groups'],
                'paths_verified':len(row['paths']),'file_contents_emitted':False,
                'service_namespace_reproduced':False,'model_calls':0,'database_operations':0}
            need(result==expected and all(type(result[k]) is int for k in
                 ('uid','gid','paths_verified','model_calls','database_operations')) and
                 result['file_contents_emitted'] is False and result['service_namespace_reproduced'] is False,
                 'ACCEPTANCE_ACCESS_RESULT');evidence.append(result)
        self.results[self.phase]=evidence
        return observation(context,self.phase,sha(canonical(evidence)))

    def post_install_checks(self,context,diagnostics):
        self._enter(context,diagnostics,'post_install_checks');result=self._run('local_https')
        need(set(result)=={'schema','phase','state','contract_sha256','retained_certificate_ready',
             'served_certificate_sha256','https_statuses','new_issue_calls','renew_calls','dry_run_calls',
             'model_calls','notification_calls','owner_ack','business_e2e','production_acceptance'} and
             result['retained_certificate_ready'] is True and
             result['served_certificate_sha256']==self.tls['certificate_sha256'] and
             result['https_statuses'].get('/owner/')==200 and
             result['https_statuses'].get('/owner/api/state') in (401,403) and
             result['https_statuses'].get('/owner-callback') in (403,405) and
             set(result['https_statuses'])=={'/owner/','/owner/api/state','/owner-callback'} and
             all(type(result[k]) is int and result[k]==0 for k in
                 ('new_issue_calls','renew_calls','dry_run_calls','model_calls','notification_calls')) and
             all(result[k]=='PENDING' for k in ('owner_ack','business_e2e','production_acceptance')),
             'ACCEPTANCE_HTTPS_RESULT')
        self.results[self.phase]=result
        return observation(context,self.phase,sha(canonical(result)))
