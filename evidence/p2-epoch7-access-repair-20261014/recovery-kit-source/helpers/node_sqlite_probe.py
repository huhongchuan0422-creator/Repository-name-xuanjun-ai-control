"""One reviewed builtin-only Node SQLite predicate; no OpenClaw imports.

The source predicate is OpenClaw npm 2026.9.9 node-sqlite.mjs, SHA256
 ef9e2430552069dfa8a8eb0900fd053ef6dc4218c5841693f3a0f9c8dae59aba.
The launcher calls runtime recovery on failure. This probes only :memory: NUL
round trips; WAL safety is a version predicate, never a disk/WAL workload.
"""
import copy
import errno
import hashlib
import json
import os
import re
import stat
import threading

MAX_NODE_BYTES=268435456
SECONDS=5
OUTPUT_BYTES=4096
PREFIX='xj-p2-proof-'
META=('dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns')
ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C','LC_ALL':'C',
     'NODE_NO_WARNINGS':'1','NODE_DISABLE_COMPILE_CACHE':'1'}
EXECUTION_IDENTITY={'uid':1002,'gid':1002,'supplementary_groups':[]}
# No package resolution, filesystem, subprocess, network or OpenClaw imports.
# Use a worker, as the official current-runtime probe does; successful worker
# exit and database.close are prerequisites to a positive result.
SOURCE=b'''"use strict";
function probeSqlite(DatabaseSync) {
  const r = {available:false,version:null,text:false,blob:false,json:false,error:null};
  let db;
  try {
    if (typeof DatabaseSync !== "function") { r.error="SQLITE_UNAVAILABLE"; return r; }
    db = new DatabaseSync(":memory:"); r.available=true;
    const version=db.prepare("SELECT sqlite_version() AS version").get()?.version;
    r.version=typeof version === "string" ? version : null;
    const text="a\\u0000b\\u0000", bytes=Buffer.from(text,"utf8"), value=JSON.stringify({value:text});
    db.exec("CREATE TABLE probe (text_value TEXT, blob_value BLOB, json_value TEXT)");
    db.prepare("INSERT INTO probe VALUES (?, ?, ?)").run(text,bytes,value);
    const row=db.prepare("SELECT text_value, blob_value, json_value FROM probe").get();
    r.text=typeof row?.text_value === "string" && row.text_value.length === text.length && Buffer.from(row.text_value,"utf8").equals(bytes);
    r.blob=row?.blob_value instanceof Uint8Array && Buffer.from(row.blob_value).equals(bytes);
    r.json=row?.json_value === value && JSON.parse(row.json_value).value === text;
  } catch (_) { r.error="SQLITE_CHECK_FAILED"; }
  finally { try { db?.close(); } catch (_) { r.error="SQLITE_CLOSE_FAILED"; } }
  return r;
}
const failed=(label)=>({available:false,version:null,text:false,blob:false,json:false,error:label});
let emitted=false;
function finish(sqlite) {
  if (emitted) return; emitted=true;
  process.stdout.write(JSON.stringify({schema:1,node_version:process.versions.node,
    exec_path:process.execPath,exec_argv:process.execArgv,sqlite})+"\\n");
}
try {
  const sqlite=process.getBuiltinModule?.("node:sqlite");
  if (process.getuid?.() !== 1002 || process.geteuid?.() !== 1002 ||
      process.getgid?.() !== 1002 || process.getegid?.() !== 1002) finish(failed("EXECUTION_IDENTITY_MISMATCH"));
  else if (typeof sqlite?.DatabaseSync !== "function") finish(failed("SQLITE_UNAVAILABLE"));
  else {
    const {Worker}=process.getBuiltinModule("node:worker_threads");
    const execArgv=process.allowedNodeEnvironmentFlags?.has("--experimental-sqlite") ? ["--experimental-sqlite"] : [];
    const worker=new Worker(`const {parentPort}=require("node:worker_threads");
      parentPort.postMessage((${probeSqlite.toString()})(require("node:sqlite").DatabaseSync));
      parentPort.close();`,{eval:true,env:{NODE_NO_WARNINGS:"1"},execArgv});
    let result, failure;
    worker.on("message",value=>{
      if (result !== undefined || value === null || typeof value !== "object") {
        failure="WORKER_RESULT_INVALID"; worker.terminate().catch(()=>{});
      } else result=value;
    });
    worker.on("error",()=>{failure="WORKER_FAILED";});
    worker.on("messageerror",()=>{failure="WORKER_RESULT_INVALID";worker.terminate().catch(()=>{});});
    worker.once("exit",code=>finish(failure ? failed(failure) :
      code === 0 && result !== undefined ? result : failed("WORKER_EXIT_FAILED")));
  }
} catch (_) { finish(failed("WORKER_UNAVAILABLE")); }
'''


def need(value,label):
    if not value:raise ValueError('NODE_SQLITE_'+label)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def digest(value):return hashlib.sha256(value).hexdigest()
def sha(value):need(type(value) is str and re.fullmatch(r'[0-9a-f]{64}',value),'HASH')
def keys(value,expected,label):need(type(value) is dict and set(value)==set(expected),label)
def same(a,b):return canonical(a)==canonical(b)
def parse(raw):
    def pairs(items):
        value={}
        for key,item in items:
            need(key not in value,'DUPLICATE_RESULT_KEY');value[key]=item
        return value
    return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,
        parse_constant=lambda value:need(False,'NONFINITE_RESULT'))
def metadata(info):return {key:getattr(info,'st_'+key) if key!='mode' else stat.S_IMODE(info.st_mode) for key in META}
def script_path(nonce):
    need(type(nonce) is str and re.fullmatch(r'[0-9a-f]{32}',nonce),'NONCE')
    return '/run/'+PREFIX+nonce+'/node-sqlite-probe.cjs'
def argv(node,nonce):return [node['path'],script_path(nonce)]


def validate_node(node):
    keys(node,('path','sha256','metadata'),'NODE_KEYS');sha(node['sha256'])
    path=node['path'];need(type(path) is str and len(path)<=512 and re.fullmatch(r'/home/xuanjun_dev/[A-Za-z0-9_./+-]+/node',path)
        and os.path.normpath(path)==path and '..' not in path.split('/'),'EXACT_USER_NODE_PATH')
    row=node['metadata'];keys(row,META,'NODE_METADATA')
    need(all(type(x) is int and x>=0 for x in row.values()) and row['ino']>0 and row['nlink']==1
        and row['uid']==row['gid']==1002 and 0<row['size']<=MAX_NODE_BYTES and row['mode']&0o100
        and not row['mode']&0o7022,'NODE_AUTHORITY')
    return copy.deepcopy(node)


def binding_from_observation(value):
    need(type(value) is dict and value.get('kind')=='EPOCH7_OBSERVATION_ONLY_UNREVIEWED'
        and value.get('install_admission')=='NOT_GRANTED','COMPLETE_OBSERVATION')
    for name in ('snapshot','evidence','unit_metadata'):
        need(digest(canonical(value[name]))==value[name+'_sha256'],'OBSERVATION_DIGEST')
    retained=value['evidence']['retained'];snapshot=value['snapshot']
    need(digest(canonical(retained))==snapshot['retained_resource_sha256'] and
        value['evidence']['snapshot_sha256']==value['snapshot_sha256'],'RETAINED_DIGEST')
    section=value['unit_metadata']['sections']['native_gateway']
    need(section['state']=='MEASURED_UNREVIEWED','MEASURED_NODE_REQUIRED')
    identity=section['evidence']['gateway_identity']
    keys(identity,('user','exe','sha256','cgroup'),'GATEWAY_IDENTITY')
    need(identity['user']=='xuanjun_dev' and identity['cgroup']=='/system.slice/xuanjun-uk-openclaw.service','GATEWAY_SCOPE')
    row=retained['native_components']['components'][identity['exe']]
    keys(row,tuple(META)+('kind','sha256'),'NODE_OBSERVATION_METADATA')
    need(row['kind']=='FILE' and row['sha256']==identity['sha256'],'NODE_BINDING')
    node=validate_node({'path':identity['exe'],'sha256':identity['sha256'],
                        'metadata':{key:row[key] for key in META}})
    proof_input={'snapshot_sha256':value['snapshot_sha256'],
        'retained_resource_sha256':snapshot['retained_resource_sha256'],
        'unit_metadata_sha256':value['unit_metadata_sha256']}
    return {'node':node,'probe_input_sha256':digest(canonical(proof_input)),
            'diagnostic_sha256':digest(SOURCE)}


def version_parts(value):
    need(type(value) is str and len(value)<=64 and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',value),'VERSION_FORMAT')
    result=tuple(int(x) for x in value.split('.'))
    need(all(x<=9007199254740991 for x in result),'VERSION_SAFE_INTEGER')
    return result

def validate_result(value,node):
    keys(value,('schema','node_version','exec_path','exec_argv','sqlite'),'RESULT_KEYS')
    need(type(value['schema']) is int and value['schema']==1 and value['exec_path']==node['path']
        and type(value['exec_argv']) is list and value['exec_argv']==[],'EXECUTION_RESULT')
    major,minor,patch=version_parts(value['node_version'])
    need((major==24 and minor>=16) or major>26 or (major==26 and minor>=1),'SUPPORTED_NODE_VERSION')
    result=value['sqlite'];keys(result,('available','version','text','blob','json','error'),'SQLITE_KEYS')
    need(all(result[key] is True for key in ('available','text','blob','json')) and result['error'] is None,'NUL_ROUNDTRIP')
    major,minor,patch=version_parts(result['version'])
    need(major>3 or (major==3 and (minor>51 or (minor==51 and patch>=3) or
        (minor==50 and patch>=7) or (minor==44 and patch>=6))),'WAL_RESET_SAFE_VERSION')
    return copy.deepcopy(value)


def validate_node_sqlite_proof(proof,expected_node,expected_policy_sha256,expected_probe_input_sha256):
    validate_node(expected_node);sha(expected_policy_sha256);sha(expected_probe_input_sha256)
    keys(proof,('schema','status','node','diagnostic_sha256','policy_sha256','probe_input_sha256',
        'nonce','argv_sha256','environment_sha256','execution_identity','result','cleanup_state','error'),'PROOF_KEYS')
    need(type(proof['schema']) is int and proof['schema']==1 and proof['status']=='PASS_OBSERVED'
        and proof['cleanup_state']=='OBSERVED' and proof['error'] is None,'PROOF_NOT_VERIFIED')
    need(same(proof['node'],expected_node) and proof['diagnostic_sha256']==digest(SOURCE)
        and proof['policy_sha256']==expected_policy_sha256
        and proof['probe_input_sha256']==expected_probe_input_sha256,'PROOF_BINDING')
    need(proof['argv_sha256']==digest(canonical(argv(expected_node,proof['nonce'])))
        and proof['environment_sha256']==digest(canonical(ENV))
        and same(proof['execution_identity'],EXECUTION_IDENTITY),'EXECUTION_BINDING')
    return validate_result(proof['result'],expected_node)


def validated_proof_from_attempt(attempt,original_policy,original_observation,expected_policy_sha256):
    """Pure binding adapter; callers authenticate the original policy separately.

    The expected digest is a reviewed/pinned external input, never authority
    copied from the leaf proof. Digest consistency cannot authenticate a caller.
    The protected loader and complete approval bind the whole original evidence.
    """
    sha(expected_policy_sha256)
    need(type(original_policy) is dict and original_policy.get('schema')==2 and
        original_policy.get('node_sqlite_reviewed') is True and
        digest(canonical(original_policy)+b'\n')==expected_policy_sha256,'ORIGINAL_POLICY_BINDING')
    binding=binding_from_observation(original_observation)
    need(same(binding,original_policy.get('node_sqlite')),'ORIGINAL_OBSERVATION_BINDING')
    need(type(attempt) is dict and type(attempt.get('schema')) is int and attempt['schema']==1 and
        attempt.get('stage')=='RESULT_RECORDED' and attempt.get('resume_authority') is False and
        attempt.get('operator_acknowledgement_is_external_approval_proof') is False and
        attempt.get('nonce')==original_policy['nonce'] and
        attempt.get('policy_sha256')==expected_policy_sha256 and same(attempt.get('policy'),original_policy),
        'AUTHENTICATED_ATTEMPT_BINDING')
    result=attempt['result'];need(type(result) is dict and result.get('failure') is None and
        result.get('incomplete_case') is None and
        result.get('resume_authority') is False and result.get('last_command_cleanup')==[],
        'WHOLE_PROBE_NOT_VERIFIED')
    cases=result.get('cases');need(type(cases) is list and len(cases)==8,'EIGHT_CASES_REQUIRED')
    for index,row in enumerate(cases,1):
        need(type(row) is dict and type(row.get('case')) is int and row['case']==index and
            (row.get('expected_rejection_observed') is True and row.get('status')=='FAIL_OBSERVED' if index in (6,8)
             else row.get('status')=='PASS_OBSERVED'),'CASE_NOT_VERIFIED')
    cleanup=result.get('cleanup');need(type(cleanup) is list and cleanup and
        all(type(row) is dict and row and not any(type(v) is str and
            (v=='UNKNOWN' or v.startswith('RETAINED')) for v in row.values()) for row in cleanup),
        'WHOLE_PROBE_CLEANUP_UNKNOWN')
    proof=result['node_sqlite']
    need(type(proof) is dict and proof.get('nonce')==original_policy['nonce'],'PROOF_NONCE_BINDING')
    validate_node_sqlite_proof(proof,binding['node'],expected_policy_sha256,binding['probe_input_sha256'])
    receipt=result['created_receipt'];keys(receipt,('path','sha256','metadata','node_sqlite_event_sha256'),'RECEIPT_BINDING_KEYS')
    sha(receipt['sha256']);keys(receipt['metadata'],META,'RECEIPT_METADATA')
    need(all(type(v) is int and v>=0 for v in receipt['metadata'].values()) and
        receipt['metadata']['ino']>0 and 0<receipt['metadata']['size']<=131072 and
        receipt['path']==script_path(proof['nonce']).rsplit('/',1)[0]+'/created-receipt.json' and
        (receipt['metadata']['uid'],receipt['metadata']['gid'],receipt['metadata']['mode'],receipt['metadata']['nlink'])
            ==(0,0,0o600,1) and
        receipt['node_sqlite_event_sha256']==digest(canonical(proof)),'DURABLE_RECEIPT_BINDING')
    return {'proof':copy.deepcopy(proof),'policy_sha256':expected_policy_sha256,
            'input_sha256':binding['probe_input_sha256']}


def authenticate_receipt_binding(receipt_raw,observed_metadata,observation):
    """Validate bytes supplied by the protected loader's exact nonce-file read.

    This function performs no I/O. Only the loader can establish that these are
    bytes/metadata from the root-owned, no-follow, single-link0600 receipt. Do
    not call this a substitute for that read or for the complete approval gate.
    """
    need(type(receipt_raw) is bytes and 0<len(receipt_raw)<=131072,'RECEIPT_BYTES_BOUND')
    attempt=observation['finite_probe'];reported=attempt['result']['created_receipt']
    need(same(observed_metadata,reported['metadata']) and digest(receipt_raw)==reported['sha256']
        and observed_metadata['size']==len(receipt_raw),'PROTECTED_RECEIPT_READBACK')
    receipt=parse(receipt_raw)
    need(type(receipt) is dict and type(receipt.get('schema')) is int and receipt['schema']==1 and
        receipt.get('purpose')=='ISOLATED_PROBE_CREATION_RECEIPT' and
        receipt.get('nonce')==attempt['nonce'] and receipt.get('operator_acknowledged') is True and
        receipt.get('external_approval_authenticated') is False and receipt.get('attempt_consumed') is True and
        receipt.get('stage')=='CLEANUP_OBSERVED' and receipt.get('incomplete_case') is None and
        type(receipt.get('connections_reserved')) is int and receipt['connections_reserved']==8 and
        type(receipt.get('accepted_connections')) is int and receipt['accepted_connections']==8,
        'PROTECTED_RECEIPT_SCOPE')
    events=receipt.get('events');need(type(events) is list and len(events)<=512 and
        all(type(row) is dict for row in events),'RECEIPT_EVENTS')
    rows=[row.get('detail') for row in events if row.get('event')=='NODE_SQLITE_OBSERVED']
    need(len(rows)==1 and same(rows[0],attempt['result']['node_sqlite']) and
        digest(canonical(rows[0]))==reported['node_sqlite_event_sha256'],'ONE_EXACT_NODE_RECEIPT_EVENT')
    need(same(receipt.get('cleanup'),attempt['result']['cleanup']),'RECEIPT_CLEANUP_BINDING')
    resources=receipt.get('resources');need(type(resources) is list and len(resources)<=128 and
        all(type(row) is dict for row in resources),'RECEIPT_RESOURCES')
    scripts=[row for row in resources if row.get('path')==script_path(attempt['nonce'])]
    need(len(scripts)==1 and scripts[0].get('kind')=='FILE' and scripts[0].get('sha256')==digest(SOURCE),
        'RECEIPT_DIAGNOSTIC_SOURCE')
    info=scripts[0]['identity'];keys(info,META,'RECEIPT_SCRIPT_METADATA')
    need(all(type(v) is int and v>=0 for v in info.values()) and info['ino']>0 and
        (info['uid'],info['gid'],info['mode'],info['nlink'],info['size'])==(0,0,0o644,1,len(SOURCE)),
        'RECEIPT_SCRIPT_AUTHORITY')
    # This is the independently read original value, not a leaf-proof claim.
    expected_policy_sha256=receipt['policy_sha256'];sha(expected_policy_sha256)
    original=dict(observation);original.pop('finite_probe')
    return validated_proof_from_attempt(attempt,attempt['policy'],original,expected_policy_sha256)


def child_identity():
    # Popen caller first proves one Python thread and one kernel task. No NSS,
    # locks, allocation-heavy work, imports or callbacks occur in this child.
    os.setgroups([]);os.setresgid(1002,1002,1002);os.setresuid(1002,1002,1002);os.umask(0o077)
    if os.getresuid()!=(1002,1002,1002) or os.getresgid()!=(1002,1002,1002) or os.getgroups()!=[]:
        raise RuntimeError('NODE_IDENTITY_DROP_FAILED')


def no_acl(fd):
    for name in ('system.posix_acl_access','system.posix_acl_default'):
        try:os.getxattr(fd,name)
        except OSError as error:need(error.errno in (errno.ENODATA,errno.ENOTSUP),'ACL_READ')
        else:need(False,'UNREVIEWED_ACL')


def no_file_capabilities(fd):
    try:os.getxattr(fd,'security.capability')
    except OSError as error:need(error.errno in (errno.ENODATA,errno.ENOTSUP),'CAPABILITY_XATTR_READ')
    else:need(False,'FILE_CAPABILITIES_PRESENT')


def open_node(node,deadline):
    """Anchor every parent and keep the measured ELF fd open through exec."""
    validate_node(node);held=[]
    try:
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);held.append(fd)
        for part in node['path'].split('/')[1:-1]:
            info=os.fstat(fd);need(info.st_uid in (0,1002) and not info.st_mode&0o7022,'NODE_PARENT_AUTHORITY');no_acl(fd)
            fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);held.append(fd)
        info=os.fstat(fd);need(info.st_uid in (0,1002) and not info.st_mode&0o7022,'NODE_PARENT_AUTHORITY');no_acl(fd)
        leaf=node['path'].rsplit('/',1)[1]
        result=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd);held.append(result)
        check_node(result,node,deadline)
        need(metadata(os.stat(leaf,dir_fd=fd,follow_symlinks=False))==node['metadata'],'NODE_PATH_REPLACED')
        held.pop();return result
    finally:
        for fd in reversed(held):os.close(fd)


def check_node(fd,node,deadline):
    info=os.fstat(fd);need(stat.S_ISREG(info.st_mode) and metadata(info)==node['metadata'],'NODE_DESCRIPTOR_CHANGED')
    no_acl(fd);no_file_capabilities(fd)
    os.lseek(fd,0,os.SEEK_SET);value=hashlib.sha256();count=0;magic=b''
    while True:
        deadline.remaining();part=os.read(fd,65536)
        if not part:break
        if count==0:magic=part[:4]
        count+=len(part);need(count<=MAX_NODE_BYTES,'NODE_BOUND');value.update(part)
    need(magic==b'\x7fELF' and count==node['metadata']['size'] and value.hexdigest()==node['sha256']
        and metadata(os.fstat(fd))==node['metadata'],'NODE_ELF_HASH')
    no_file_capabilities(fd)
    need(metadata(os.lstat(node['path']))==node['metadata'] and os.path.realpath(node['path'])==node['path'],'NODE_PATH_REPLACED')


def run(ops):
    binding=ops.policy['node_sqlite'];node=binding['node'];nonce=ops.policy['nonce']
    proof={'schema':1,'status':'NOT_VERIFIED','node':copy.deepcopy(node),
        'diagnostic_sha256':digest(SOURCE),'policy_sha256':ops.policy_sha,
        'probe_input_sha256':binding['probe_input_sha256'],'nonce':nonce,
        'argv_sha256':digest(canonical(argv(node,nonce))),'environment_sha256':digest(canonical(ENV)),
        'execution_identity':copy.deepcopy(EXECUTION_IDENTITY),'result':None,'cleanup_state':'UNKNOWN','error':None}
    fd=None;capture_started=False
    try:
        need(ops.operator_acknowledged is True and ops.receipt is not None and
            ops.policy['node_sqlite_reviewed'] is True,'EXPLICIT_REVIEWED_EFFECT')
        need(threading.active_count()==1 and os.listdir('/proc/self/task')==[str(os.getpid())],'SINGLE_THREAD_REQUIRED')
        ops.event('NODE_SQLITE_INTENT',{'diagnostic_sha256':digest(SOURCE),'node_sha256':node['sha256'],
            'probe_input_sha256':binding['probe_input_sha256']})
        fd=open_node(node,ops.deadline)
        ops.publish(script_path(nonce),SOURCE)
        capture_started=True;ops.last_capture_cleanup=None
        output=ops.capture(argv(node,nonce),dict(ENV),SECONDS,OUTPUT_BYTES,
            executable='/proc/self/fd/'+str(fd),pass_fds=(fd,),preexec_fn=child_identity,cwd=ops.paths['root'])
        check_node(fd,node,ops.deadline)
        need(output['stderr']==b'' and len(output['stdout'])<=OUTPUT_BYTES,'UNEXPECTED_OUTPUT')
        proof['result']=parse(output['stdout'])
        validate_result(proof['result'],node)
        proof['status']='PASS_OBSERVED'
    except BaseException as error:
        proof['error']=str(error) if type(error) is ValueError and str(error).startswith('NODE_SQLITE_') else type(error).__name__
    finally:
        if fd is not None:
            try:os.close(fd)
            except BaseException:proof['error']='NODE_DESCRIPTOR_CLOSE_UNCONFIRMED'
        errors=getattr(ops,'last_capture_cleanup',None) if capture_started else []
        if errors is None:errors=['CHILD_CLEANUP_NOT_CONFIRMED']
        proof['cleanup_state']='OBSERVED' if not errors and proof['error']!='NODE_DESCRIPTOR_CLOSE_UNCONFIRMED' else 'UNKNOWN'
        if proof['error'] is not None or proof['cleanup_state']!='OBSERVED':proof['status']='NOT_VERIFIED'
    ops.event('NODE_SQLITE_OBSERVED',proof)
    return proof
