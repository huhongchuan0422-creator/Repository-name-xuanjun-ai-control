"""Owner-operated PR99 manual portal migration using the existing SSH channel.

CURRENT deployment only; never issues or claims a legacy M99/Writer grant.
Root execution checkpoints record actual effects, not independent approvals.
WeCom is retired. Binance, model RPC, domestic CRM and unrelated routes remain.
"""
import array
import fcntl
import gzip
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import socket
import sqlite3
import ssl
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid

SOURCE = 'iZ6wee8q9z4t03hvqumwfhZ'
TARGET = 'iZvt5t8tlrm8oiZ'
R = Path('/opt/xuanjun-migration-s07/releases/portal-manual-6tm7b08f')
PREP = Path('/root/pr99-cutover-preparation-izmakdgr')
STATE = Path('/var/lib/pr99-migration-channel')
TARGET_JOB = STATE / 'portal-final-job-v1'
SOURCE_JOB = Path('/root/pr99-controller-o4ycynjz/portal-final-job-v1')
SOURCE_LOCK = Path('/root/pr99-controller.lock')
BASE = Path('/opt/trading-system')
SOURCE_UNIT = 'secure-secrets-portal.service'
TARGET_UNIT = 'xuanjun-pr99-domestic-portal.service'
RETIRED = ('xuanjun-wecom-customer-service.service',
           'xuanjun-wecom-customer-contact.service',
           'xuanjun-wecom-novel-ingress.service')
BRIDGE = 'provider-neutral-domestic-bridge.service'
UNIT_SHA = 'efff80c930d29b978c073df8837b8fd6f59ac5c5e24cbbceef98596fb351119f'
SOURCE_UNIT_SHA = '3023bd5152e1bc26f35cea3ee1cf8196a67c69a736faad7ecf53887882dad0a7'
ENTRY_SHA = '57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1'
LAUNCHER_SHA = '6c2548d7e5560046c00d795b3cb888411c4c22c852e1b5e749e5ed4d8ffa1242'
ROUTE_SHA = '23ec502aaf9c929582c3a92b078aeedbb0acab3cf6fd3f1ef9ed1b7b1c305f5c'
ROUTE = Path('/etc/nginx/pr122-minimal-cutover/tokyo-proxy-settings.conf')
PREFIXES = ('runtime/secure-secrets-portal',
            'runtime/v8-domestic-operations/operations-secretref-store',
            'runtime/v8-domestic-operations/telegram-customer-service-canary')
KEY_ROOT = Path('/root/pr99-key-preservation-etcq8gnf')
KEYS = ('project-config.env', 'portal-config.env', 'credential-bindings.json')
VERIFY_NAME = 'tiktokseZDn0fzmn8v7H8YWGlgzuT7PvLBQavc.txt'
VERIFY_BODY = b'tiktok-developers-site-verification=ZDn0fzmn8v7H8YWGlgzuT7PvLBQavc\n'
IMMUTABLE = 0x10
GETFLAGS = (2 << 30) | (struct.calcsize('l') << 16) | (ord('f') << 8) | 1
SETFLAGS = (1 << 30) | (struct.calcsize('l') << 16) | (ord('f') << 8) | 2
SSH = ['/usr/bin/sudo','-n','-u','admin','/usr/bin/ssh','-T',
       '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
       '-o','ConnectTimeout=10','-o','ConnectionAttempts=1',
       '-o','ClearAllForwardings=yes','-o','ForwardAgent=no',
       '-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2','binance-ops']

class Hold(RuntimeError): pass
class Unknown(Hold): pass

def need(value, reason):
    if not value: raise Hold(reason)

def encode(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()

def sha(raw): return hashlib.sha256(raw).hexdigest()

def host(expected):
    need(os.geteuid()==0 and os.uname().nodename.split('.')[0]==expected,'HOST_ROOT_MISMATCH')

def read(path, limit=200000000):
    path=Path(path)
    for item in [path,*path.parents]: need(not item.is_symlink(),'SYMLINK_INPUT')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=limit,'FILE_TYPE_SIZE')
        with os.fdopen(os.dup(fd),'rb') as stream: raw=stream.read(limit+1)
        after=os.fstat(fd); linked=path.stat()
        fp=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        need(fp(before)==fp(after)==fp(linked) and len(raw)==before.st_size,'FILE_DRIFT')
        return raw
    finally: os.close(fd)

def root_read(path, limit=200000000):
    for item in [Path(path),*Path(path).parents]:
        s=item.lstat()
        need(s.st_uid==0 and not s.st_mode&0o022,'ROOT_INPUT_OWNERSHIP')
    return read(path,limit)

def fsync_dir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)

def create(path, raw, mode=0o600):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    fsync_dir(Path(path).parent)

def command(argv, timeout=20):
    try:
        result=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              timeout=timeout,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'})
    except (subprocess.TimeoutExpired,OSError): raise Unknown('COMMAND_OUTCOME_UNKNOWN') from None
    need(len(result.stdout)+len(result.stderr)<=2000000,'COMMAND_OUTPUT_LIMIT')
    return result

def ctl(unit):
    p=command(['/usr/bin/systemctl','show',unit,'--all','--no-pager'])
    need(p.returncode==0,'SERVICE_QUERY_FAILED')
    return dict(line.split('=',1) for line in p.stdout.decode().splitlines() if '=' in line)

def stop_edges(values, permitted):
    need(all(key in values for key in ('RequiredBy','BoundBy','ConsistsOf')),'STOP_GRAPH_UNAVAILABLE')
    edges={v for key in ('RequiredBy','RequisiteOf','BoundBy','ConsistsOf','PropagatesStopTo')
           for v in values.get(key,'').split()}
    need(not edges-set(permitted),'STOP_PROPAGATES_OUTSIDE_SCOPE')

def static_target():
    need(sha(root_read(Path('/etc/systemd/system')/TARGET_UNIT))==UNIT_SHA,'TARGET_UNIT_CHANGED')
    need(sha(root_read(R/'migration_portal_launcher.py'))==LAUNCHER_SHA,'LAUNCHER_CHANGED')
    receipt=json.loads(root_read(R/'wired-portal-check-receipt.json'))
    need(receipt.get('status')=='PASS' and sha(root_read(R/'migration_credential_store.py'))==
         receipt.get('credential_component_sha256'),'CREDENTIAL_COMPONENT_CHANGED')
    need(sha(root_read(PREP/'candidate-domestic-proxy-settings.conf'))==ROUTE_SHA,'ROUTE_CANDIDATE_CHANGED')
    need(not ctl(TARGET_UNIT).get('DropInPaths'),'UNBOUND_TARGET_DROPINS')
    need(sha(root_read(R/'app/scripts/secure_secrets_portal_server.py'))==ENTRY_SHA,'TARGET_ENTRY_CHANGED')
    return receipt

def walk_files(directory):
    need(directory.is_dir() and not directory.is_symlink(),'DIRECTORY_MISSING')
    files={}
    for current,dirs,names in os.walk(directory,followlinks=False):
        for name in dirs:
            need(not (Path(current)/name).is_symlink(),'DIRECTORY_LINK')
        for name in names:
            path=Path(current)/name
            need(not path.is_symlink() and stat.S_ISREG(path.stat().st_mode),'TREE_SPECIAL_FILE')
            files[path.relative_to(directory).as_posix()]=path
    return files

def listener_owned(pid,port):
    sockets=set()
    for descriptor in (Path('/proc')/str(pid)/'fd').iterdir():
        try: value=os.readlink(descriptor)
        except (FileNotFoundError,ProcessLookupError): continue
        match=re.fullmatch(r'socket:\[([0-9]+)\]',value)
        if match: sockets.add(match.group(1))
    return any(fields[1]=='0100007F:'+format(port,'04X') and fields[3]=='0A' and fields[9] in sockets
               for fields in (line.split() for line in Path('/proc/net/tcp').read_text().splitlines()[1:]))


def protected_bridge():
    values=ctl(BRIDGE)
    need(values.get('ActiveState')=='active' and int(values.get('MainPID','0'))>0,'DOMESTIC_BRIDGE_NOT_ACTIVE')
    pid=values['MainPID']
    need(listener_owned(pid,18443),'DOMESTIC_BRIDGE_LISTENER_OWNERSHIP')
    env=dict(part.split(b'=',1) for part in (Path('/proc')/pid/'environ').read_bytes().split(b'\0') if b'=' in part)
    return {'pid':pid,'working_directory':values.get('WorkingDirectory'),
            'database_binding_sha256':sha(env.get(b'TRADING_DATABASE_URL',b''))}

class Checkpoint:
    def __init__(self,path): self.path=Path(path)
    def perform(self,name,action,binding=None):
        need(re.fullmatch('[a-z0-9_-]{1,60}',name),'OPERATION_NAME')
        intent=self.path/(name+'.intent.json'); result=self.path/(name+'.result.json')
        need(not intent.exists() and not result.exists(),'EXISTING_OPERATION_QUERY_ONLY')
        create(intent,encode({'operation':name,'binding':binding,'started_at':int(time.time())}))
        try: value=action()
        except BaseException as exc:
            error=self.path/(name+'.unknown.json')
            if not error.exists(): create(error,encode({'status':'HOLD_PRESERVED','error_type':type(exc).__name__}))
            raise
        create(result,encode({'operation':name,'status':'PASS','binding':binding,'evidence':value}))
        return value
    def summary(self):
        records={}
        for intent in sorted(self.path.glob('*.intent.json')):
            stem=intent.name[:-len('.intent.json')]
            result=self.path/(stem+'.result.json')
            records[stem]={'intent':json.loads(root_read(intent,2000000)),
                           'status':'PASS' if result.exists() else 'UNKNOWN_PRESERVED',
                           'result':json.loads(root_read(result,2000000)) if result.exists() else None}
        return records

def bridge_pin():
    context=ssl._create_unverified_context()
    with socket.create_connection(('127.0.0.1',18443),timeout=5) as raw:
        with context.wrap_socket(raw,server_hostname='localhost') as connection:
            return sha(connection.getpeercert(binary_form=True))

def nginx_tokens(text):
    tokens=[];index=0
    while index<len(text):
        if text[index].isspace(): index+=1;continue
        if text[index]=='#':
            end=text.find('\n',index);index=len(text) if end<0 else end+1;continue
        if text[index] in '{};': tokens.append(('punct',text[index]));index+=1;continue
        value=[]
        while index<len(text) and not text[index].isspace() and text[index] not in '{};#':
            char=text[index]
            if char in ('"',"'"):
                quote=char;index+=1
                while index<len(text) and text[index]!=quote:
                    if text[index]=='\\':
                        index+=1;need(index<len(text),'NGINX_ESCAPE')
                    value.append(text[index]);index+=1
                need(index<len(text),'NGINX_UNCLOSED_QUOTE');index+=1
            elif char=='\\':
                index+=1;need(index<len(text),'NGINX_ESCAPE');value.append(text[index]);index+=1
            elif text.startswith('${',index):
                end=text.find('}',index+2);need(end>=0,'NGINX_VARIABLE')
                value.append(text[index:end+1]);index=end+1
            else: value.append(char);index+=1
        need(value,'NGINX_TOKEN');tokens.append(('word',''.join(value)))
    return tokens

def route_probe_path(text):
    tokens=nginx_tokens(text)
    def parse(index,nested=False):
        rows=[];header=[]
        while index<len(tokens):
            kind,value=tokens[index];index+=1
            if kind=='word': header.append(value);continue
            if value==';':
                need(header,'NGINX_EMPTY_DIRECTIVE');rows.append((header,None));header=[]
            elif value=='{':
                need(header,'NGINX_EMPTY_BLOCK');children,index=parse(index,True)
                rows.append((header,children));header=[]
            else:
                need(nested and not header,'NGINX_BLOCK_BALANCE');return rows,index
        need(not nested and not header,'NGINX_BLOCK_BALANCE');return rows,index
    rows,_=parse(0);prefixes=[];exact=[]
    def walk(nodes):
        for header,children in nodes:
            if children is None: continue
            if header[0]=='location':
                args=header[1:];mode=args[0] if args and args[0] in ('=','^~','~','~*') else ''
                path=args[1] if mode and len(args)==2 else args[0] if not mode and len(args)==1 else None
                direct={tuple(h) for h,c in children if c is None}
                includes=[h[1] for h,c in children if c is None and len(h)==2 and h[0]=='include']
                bound=any(str(Path('/etc/nginx')/name)==str(ROUTE) if not name.startswith('/') else name==str(ROUTE) for name in includes)
                blocked=any(h[0] in ('return','rewrite','try_files','root','alias','auth_request','auth_basic') for h,c in children)
                if bound and not blocked and path and path.startswith('/') and '$' not in path:
                    if mode=='=' and path=='/'+VERIFY_NAME: exact.append(path)
                    elif mode in ('','^~') and path.endswith('/'):
                        prefixes.append((mode=='^~',len(path),path))
            walk(children)
    walk(rows)
    if exact: return exact[0]
    need(prefixes,'NO_VERIFIABLE_PORTAL_ROUTE_IN_EXISTING_CONFIG')
    prefix=sorted(prefixes,reverse=True)[0][2]
    return prefix+'__pr99_nonexistent_'+uuid.uuid4().hex


def target_capabilities():
    static_target()
    account=pwd.getpwnam('openclaw_ops')
    need(account.pw_uid==1001,'TARGET_SERVICE_IDENTITY_CHANGED')
    files={name:sha(root_read(path)) for name,path in walk_files(R/'app').items() if name.endswith('.py')}
    need(len(files)==168,'TARGET_SOURCE_SET_CHANGED')
    nginx=command(['/usr/sbin/nginx','-T'])
    need(nginx.returncode==0,'NGINX_CONFIG_INVALID')
    probe=route_probe_path(nginx.stdout.decode('utf-8'))
    return {'code_sha256':sha(root_read(Path(__file__))), 'host':TARGET,'route_probe':probe,
            'service':{k:ctl(TARGET_UNIT).get(k) for k in ('ActiveState','MainPID')},
            'source_files':files,
            'key_files':{name:sha(root_read(R/'database-preservation'/name)) for name in KEYS},
            'bridge':protected_bridge(),'scope':'MANUAL_PORTAL_ONLY_WECOM_RETIRED'}

def target_context(request):
    static_target()
    need(type(request)is dict and set(request)=={'operation','job','sha256'},'REQUEST_SCHEMA')
    need(re.fullmatch('portal-final-[0-9a-f]{32}',request['job'] or ''),'JOB_ID')
    if TARGET_JOB.exists():
        claim=json.loads(root_read(TARGET_JOB/'claim.json'))
        need(claim=={'job':request['job'],'code_sha256':sha(root_read(Path(__file__)))},'OTHER_OR_CHANGED_JOB_PRESERVED')
    else:
        need(request['operation']=='preflight','PREFLIGHT_REQUIRED')
        TARGET_JOB.mkdir(mode=0o700);fsync_dir(TARGET_JOB.parent)
        create(TARGET_JOB/'claim.json',encode({'job':request['job'],'code_sha256':sha(root_read(Path(__file__)))}))
    need(not list(TARGET_JOB.glob('*.unknown.json')), 'PRIOR_UNKNOWN_QUERY_ONLY')
    order=('preflight','prepare','check','start','cutover')
    for prior in order[:order.index(request['operation'])]:
        record=json.loads(root_read(TARGET_JOB/(prior+'.result.json')))
        need(record.get('status')=='PASS','PRIOR_STAGE_NOT_ACCEPTED')
        if prior!='preflight':
            need(record.get('binding')==request['sha256'],'FINAL_PACKAGE_CHANGED_BETWEEN_STAGES')
    return Checkpoint(TARGET_JOB)

def verify_protected():
    baseline=json.loads(root_read(TARGET_JOB/'preflight.result.json'))['evidence']
    need(protected_bridge()==baseline['bridge'],'PROTECTED_BRIDGE_CHANGED')
    current={name:sha(root_read(path)) for name,path in walk_files(R/'app').items() if name.endswith('.py')}
    need(current==baseline['source_files'],'ACCEPTED_APPLICATION_CHANGED')
    return baseline

def target_data_work(): return R/'portal-final-data-v1'

def target_preflight():
    capabilities=target_capabilities()
    need(capabilities['service']=={'ActiveState':'inactive','MainPID':'0'},'TARGET_NOT_STOPPED')
    need(not (R/'cutover-ready.json').exists(),'EXISTING_CUTOVER_MARKER')
    need(root_read(ROUTE)==root_read(PREP/'original-tokyo-proxy-settings.conf'),'LIVE_ROUTE_CHANGED')
    passed=json.loads(root_read(R/'pr99-latest-wired-check-2q0qxdrq/receipt-r2.json'))
    need(passed.get('status')=='PASS','EXISTING_WIRED_CHECK_NOT_ACCEPTED')
    latest=json.loads(root_read(Path('/root/pr99-latest-database-5t6qkvho/receipt.json')))
    need(sha(read(R/'live-data/trading.db'))==latest['snapshot_sha256'],'TARGET_PRECOPY_CHANGED')
    nginx=command(['/usr/sbin/nginx','-T'])
    need(nginx.returncode==0,'NGINX_BASELINE_INVALID')
    create(TARGET_JOB/'nginx-baseline.conf',nginx.stdout)
    need(not os.path.lexists(target_data_work()),'EXISTING_TARGET_DATA_WORK_PRESERVED')
    need(not os.path.ismount(R/'runtime') and not os.path.ismount(R/'live-data'),'TARGET_DATA_IS_MOUNTPOINT')
    target_data_work().mkdir(mode=0o700);fsync_dir(R)
    return capabilities

def incoming(package_sha):
    need(type(package_sha)is str and re.fullmatch('[0-9a-f]{64}',package_sha),'PACKAGE_SHA')
    directory=STATE/'packages'/package_sha
    receipt=json.loads(root_read(directory/'receipt.json'))
    need(receipt.get('status')=='PASS_STAGED' and receipt.get('sha256')==package_sha,'ROOT_STAGE_NOT_ACCEPTED')
    manifest=json.loads(root_read(directory/'manifest.json'))
    need(manifest.get('schema')==1 and manifest.get('source_host')==SOURCE and
         manifest.get('target_host')==TARGET and manifest.get('snapshot_kind')=='FINAL_SOURCE_FENCED',
         'NOT_FINAL_SOURCE_PACKAGE')
    proof=manifest.get('fence',{})
    need(proof.get('source_host')==SOURCE and proof.get('portal_stopped')is True and
         proof.get('portal_persistently_masked')is True and proof.get('admission_sealed')is True and
         proof.get('request_threads_drained')is True and proof.get('kernel_data_fence')is True,
         'SOURCE_FENCE_ATTESTATION_MISSING')
    need(manifest.get('job')==json.loads(root_read(TARGET_JOB/'claim.json'))['job'],'PACKAGE_JOB_MISMATCH')
    for name,expected in manifest['files'].items():
        need(name in {'database.sqlite',*KEYS} or any(name.startswith(p+'/') for p in PREFIXES),'DATA_SCOPE')
        need(not name.startswith('/') and all(p not in ('','.','..') for p in name.split('/')),'DATA_PATH')
        need(sha(root_read(directory/name))==expected,'ROOT_STAGE_DATA_CHANGED')
    baseline=verify_protected()
    for name in KEYS:
        need(manifest['files'].get(name)==baseline['key_files'][name],'KEY_BINDING_CHANGED')
    return directory,manifest

def own_tree(directory,account):
    for current,dirs,files in os.walk(directory,topdown=False):
        for name in files:
            path=Path(current)/name;os.chown(path,account.pw_uid,account.pw_gid);path.chmod(0o600)
        os.chown(current,account.pw_uid,account.pw_gid);os.chmod(current,0o700)

def target_prepare(package_sha):
    directory,manifest=incoming(package_sha)
    need(ctl(TARGET_UNIT).get('MainPID')=='0' and not (R/'cutover-ready.json').exists(),'TARGET_ALREADY_ACTIVE')
    database=directory/'database.sqlite'
    con=sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        need(con.execute('PRAGMA integrity_check').fetchone()[0]=='ok','FINAL_DATABASE_INTEGRITY')
        ids={row[0] for row in con.execute('SELECT credential_id FROM credential_records')}
        bindings=json.loads(root_read(directory/'credential-bindings.json'))['bindings']
        need(ids==set(bindings) and len(ids)==3,'UNBOUND_FINAL_CREDENTIAL_RECORDS')
    finally: con.close()
    prepared=target_data_work()/'prepared';prepared.mkdir(mode=0o700)
    runtime=prepared/'runtime';runtime.mkdir(mode=0o700)
    live=prepared/'live-data';live.mkdir(mode=0o700)
    create(live/'trading.db',root_read(database))
    for name in manifest['files']:
        if any(name.startswith(p+'/') for p in PREFIXES):
            destination=prepared/name
            destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            create(destination,root_read(directory/name))
    pin=runtime/'v8-domestic-operations/internal-bridge/domestic_bridge_cert.sha256'
    pin.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    create(pin,(bridge_pin()+'\n').encode())
    account=pwd.getpwnam('openclaw_ops');own_tree(runtime,account);own_tree(live,account)
    # Same fixed release parent; inactive service and absent marker prevent use
    # during these two durable swaps. Originals are renamed, never deleted.
    backup=target_data_work()/'backup';backup.mkdir(mode=0o700)
    os.rename(R/'live-data',backup/'live-data');os.rename(live,R/'live-data');fsync_dir(R)
    os.rename(R/'runtime',backup/'runtime');os.rename(runtime,R/'runtime');fsync_dir(R)
    need(sha(read(R/'live-data/trading.db'))==manifest['files']['database.sqlite'],'FINAL_DATABASE_READBACK')
    create(TARGET_JOB/'final-package.json',encode({'sha256':package_sha,'database_sha256':manifest['files']['database.sqlite']}))
    return {'database_integrity':'PASS','credential_count':len(ids),'package_sha256':package_sha,
            'source_proof':'ATTESTED_OVER_OWNER_AUTHORIZED_EXISTING_SSH','production_cutover':False}

def target_check(package_sha):
    incoming(package_sha);verify_protected()
    before=sha(read(R/'live-data/trading.db'))
    work=target_data_work()/'validation';work.mkdir(mode=0o700)
    runtime=work/'runtime';shutil.copytree(R/'runtime',runtime,symlinks=False)
    own_tree(runtime,pwd.getpwnam('openclaw_ops'))
    sites=list((R/'venv/lib').glob('python*/site-packages'));need(len(sites)==1,'DEPENDENCY_LAYOUT')
    bridge=Path('/home/openclaw_ops/v8-domestic-operations/runtime/internal-bridge/secrets')
    properties=[
        'User=openclaw_ops','PrivateNetwork=yes','PrivateTmp=yes','ProtectSystem=strict',
        'ProtectHome=yes','NoNewPrivileges=yes','CapabilityBoundingSet=','RuntimeMaxSec=60',
        'WorkingDirectory=/opt/trading-system',
        'BindReadOnlyPaths='+str(R/'app')+':/opt/trading-system',
        'BindReadOnlyPaths='+str(sites[0])+':/srv/pr99-packages',
        'BindReadOnlyPaths='+str(R/'migration_portal_launcher.py')+':/srv/pr99-launcher.py',
        'BindReadOnlyPaths='+str(R/'migration_credential_store.py')+':/srv/migration_credential_store.py',
        'BindPaths='+str(runtime)+':/opt/trading-system/runtime',
        'BindReadOnlyPaths='+str(R/'live-data')+':/srv/pr99-database',
        'BindReadOnlyPaths='+str(bridge)+':/srv/pr99-bridge-secrets',
        'Environment=TRADING_DATABASE_URL=sqlite:///file:/srv/pr99-database/trading.db?mode=ro&uri=true',
    ]
    properties+=['LoadCredential='+label+':'+str(R/'database-preservation'/name)
                 for label,name in zip(('project','portal','bindings'),KEYS)]
    job=json.loads(root_read(TARGET_JOB/'claim.json'))['job']
    argv=['/usr/bin/systemd-run','--quiet','--wait','--pipe','--collect','--unit=pr99-final-check-'+job[-12:]]
    for prop in properties: argv+=['--property='+prop]
    argv+=['/usr/bin/python3','-I','-B','/srv/pr99-launcher.py','--check']
    log=TARGET_JOB/'final-check.log'
    with log.open('xb') as output:
        try: result=subprocess.run(argv,stdout=output,stderr=subprocess.STDOUT,timeout=75)
        except subprocess.TimeoutExpired: raise Unknown('VALIDATION_UNIT_QUERY_ONLY') from None
        output.flush();os.fsync(output.fileno())
    text=root_read(log,2000000).decode(errors='replace')
    markers=('LIVE_SERVICE_STORE_DECRYPTION=3_PASS','WIRED_PORTAL_HTTP=PASS',
             'DOMESTIC_BRIDGE_PORT=18443','TEST_PROCESS_COMPLETED=YES')
    need(result.returncode==0 and all(item in text.splitlines() for item in markers),'FINAL_WIRED_VALIDATION_FAILED')
    need(sha(read(R/'live-data/trading.db'))==before,'VALIDATION_CHANGED_DATABASE')
    return {'application_credential_reads':'3_PASS','isolated_http':'PASS',
            'new_write_component':'REUSED_UNCHANGED_ACCEPTED_COMPONENT',
            'log_sha256':sha(root_read(log)),'external_network':'ISOLATED'}

def backend_probe(path):
    connection=http.client.HTTPConnection('127.0.0.1',18080,timeout=5)
    try:
        connection.request('GET',path,headers={'Host':'wenwenwenyiyiyi.work'})
        response=connection.getresponse();body=response.read(8193)
        return {'status':response.status,'body_sha256':sha(body)}
    except (OSError,http.client.HTTPException): return {'status':None,'body_sha256':None}
    finally: connection.close()

def portal_http():
    return backend_probe('/'+VERIFY_NAME)=={'status':200,'body_sha256':sha(VERIFY_BODY)}

def target_start(package_sha):
    verify_protected();incoming(package_sha)
    need((TARGET_JOB/'check.result.json').is_file(),'FINAL_VALIDATION_REQUIRED')
    expected=json.loads(root_read(TARGET_JOB/'final-package.json'))
    need(sha(read(R/'live-data/trading.db'))==expected['database_sha256'],'FINAL_DATABASE_CHANGED_BEFORE_START')
    need(ctl(TARGET_UNIT).get('MainPID')=='0','TARGET_ALREADY_RUNNING')
    marker={'scope':'MANUAL_PORTAL_ONLY','package_sha256':package_sha,
            'database_sha256':expected['database_sha256'],'source_resumed':False}
    create(R/'cutover-ready.json',encode(marker))
    result=command(['/usr/bin/systemctl','start',TARGET_UNIT])
    if result.returncode: raise Unknown('START_OUTCOME_REQUIRES_QUERY')
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        state=ctl(TARGET_UNIT)
        if (state.get('ActiveState')=='active' and int(state.get('MainPID','0'))>0
                and listener_owned(state['MainPID'],18080) and portal_http()):
            return {'active':True,'http_verification':'PASS','production_cutover':False}
        time.sleep(.5)
    raise Hold('START_HEALTH_NOT_CONFIRMED_SOURCE_REMAINS_FENCED')

def replace_route(expected,replacement):
    need(root_read(ROUTE)==expected,'ROUTE_COMPARE_FAILED')
    path=ROUTE.parent/('.pr99-'+uuid.uuid4().hex)
    create(path,replacement,0o644)
    need(root_read(ROUTE)==expected,'ROUTE_COMPARE_FAILED')
    os.replace(path,ROUTE);fsync_dir(ROUTE.parent)

def https_probe(path):
    context=ssl.create_default_context()
    try:
        with socket.create_connection(('127.0.0.1',443),timeout=35) as plain:
            with context.wrap_socket(plain,server_hostname='wenwenwenyiyiyi.work') as secure:
                secure.sendall(('GET '+path+'?pr99='+uuid.uuid4().hex+
                    ' HTTP/1.1\r\nHost: wenwenwenyiyiyi.work\r\nConnection: close\r\n\r\n').encode())
                response=http.client.HTTPResponse(secure);response.begin()
                return {'status':response.status,'body_sha256':sha(response.read(8193))}
    except (OSError,http.client.HTTPException): return {'status':None,'body_sha256':None}

def target_cutover(package_sha,journal):
    verify_protected();incoming(package_sha)
    need((TARGET_JOB/'start.result.json').is_file() and portal_http(),'OWNED_PORTAL_NOT_READY')
    original=root_read(PREP/'original-tokyo-proxy-settings.conf')
    candidate=root_read(PREP/'candidate-domestic-proxy-settings.conf')
    need(root_read(ROUTE)==original,'ROUTE_CHANGED_BEFORE_CUTOVER')
    current=command(['/usr/sbin/nginx','-T'])
    need(current.returncode==0 and current.stdout==root_read(TARGET_JOB/'nginx-baseline.conf'),'OTHER_NGINX_CONFIG_CHANGED')
    baseline=verify_protected()
    probe_path=baseline['route_probe']
    expected=backend_probe(probe_path)
    need(expected['status'] in (200,404) and backend_probe(probe_path)==expected,'NONDETERMINISTIC_ROUTE_PROBE')
    cold=https_probe(probe_path)
    need(cold['status'] in (502,503,504),'PROBE_NOT_BOUND_TO_FENCED_SOURCE_ROUTE')
    journal.perform('route_write',lambda:(replace_route(original,candidate) or {'sha256':sha(candidate)}))
    tested=command(['/usr/sbin/nginx','-t'])
    if tested.returncode:
        journal.perform('restore_invalid_candidate',lambda:(replace_route(candidate,original) or {'restored':True}))
        raise Hold('INVALID_NGINX_CANDIDATE_ORIGINAL_RESTORED')
    def reload():
        result=command(['/usr/bin/systemctl','reload','nginx.service'])
        if result.returncode: raise Unknown('NGINX_RELOAD_UNKNOWN')
        return {'reload_exit':0}
    before_reload=command(['/usr/sbin/nginx','-T'])
    if not (before_reload.returncode==0 and before_reload.stdout.count(candidate)==1 and
            before_reload.stdout.replace(candidate,original,1)==root_read(TARGET_JOB/'nginx-baseline.conf')):
        journal.perform('restore_before_reload',lambda:(replace_route(candidate,original) or {'restored':True}))
        raise Hold('OTHER_NGINX_CHANGE_DETECTED_OWN_FILE_RESTORED_NO_RELOAD')
    journal.perform('nginx_reload',reload)
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        probe=https_probe(probe_path)
        if probe==expected:
            post=command(['/usr/sbin/nginx','-T'])
            need(post.returncode==0 and post.stdout.count(candidate)==1 and
                 post.stdout.replace(candidate,original,1)==root_read(TARGET_JOB/'nginx-baseline.conf'),
                 'UNRELATED_NGINX_CONFIG_DRIFT')
            verify_protected()
            return {'scope':'PORTAL_ONLY','https':'PASS','cold_status':cold['status'],
                    'backend_http':'PASS','route_sha256':sha(candidate),
                    'source_resumed':False,'tokyo_model_rpc':'RETAINED',
                    'production_cutover':True}
        time.sleep(.5)
    # Known failed read-only acceptance after a completed reload: contain only
    # our route and service. Never restore a database or reopen source writes.
    static_target()
    journal.perform('restore_route',lambda:(replace_route(candidate,original) or {'route_restored':True}))
    need(command(['/usr/sbin/nginx','-t']).returncode==0,'RESTORED_ROUTE_CONFIG_NOT_CONFIRMED')
    journal.perform('restore_reload',reload)
    def stop_owned():
        static_target()
        result=command(['/usr/bin/systemctl','stop',TARGET_UNIT],30)
        if result.returncode: raise Unknown('CONTAINMENT_STOP_UNKNOWN')
        need(ctl(TARGET_UNIT).get('MainPID')=='0','CONTAINMENT_STOP_NOT_CONFIRMED')
        return {'owned_service_stopped':True,'database_restored':False,'source_resumed':False}
    journal.perform('stop_owned',stop_owned)
    raise Hold('HTTPS_FAILED_ROUTE_RESTORED_SOURCE_FENCED_DATA_PRESERVED')

# Source admission is a real loopback SYN gate followed by an empty listener
# backlog, no accepted TCP requests and exactly the single HTTP main thread.
# Empty fds alone are never treated as a drain or writer proof.
def flag(path,value=None):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        flags=array.array('l',[0]);fcntl.ioctl(fd,GETFLAGS,flags,True)
        if value is not None:
            desired=array.array('l',[value]);fcntl.ioctl(fd,SETFLAGS,desired,False);os.fsync(fd)
            flags=array.array('l',[0]);fcntl.ioctl(fd,GETFLAGS,flags,True)
            need(flags[0]==value,'KERNEL_FENCE_NOT_CONFIRMED')
        return flags[0]
    finally: os.close(fd)

def firewall_args(job):
    program=shutil.which('iptables');need(program,'IPTABLES_UNAVAILABLE')
    return [program,'--wait','5'],['INPUT','-i','lo','-p','tcp','--dport','18080','--syn',
           '-m','comment','--comment','pr99-'+job,'-j','REJECT','--reject-with','tcp-reset']

def tcp_drained(pid):
    found=False
    for line in Path('/proc/net/tcp').read_text().splitlines()[1:]:
        fields=line.split();address,port=fields[1].split(':')
        if int(port,16)!=18080: continue
        need(address=='0100007F','SOURCE_LISTENER_ADDRESS_CHANGED')
        if fields[3]=='0A':
            found=True
            if int(fields[4].split(':')[1],16): return False
        elif fields[3] not in ('06','07'): return False
    tids=[p.name for p in (Path('/proc')/str(pid)/'task').iterdir()]
    return found and tids==[str(pid)]

def source_inventory():
    known={SOURCE_UNIT,*RETIRED,'restricted-rpc-openai-shim.service','tokyo-restricted-model-executor.service'}
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name)==os.getpid(): continue
        try:
            cwd=os.readlink(process/'cwd');args=(process/'cmdline').read_bytes()
            if not (cwd==str(BASE) or cwd.startswith(str(BASE)+'/') or str(BASE).encode() in args): continue
            groups=(process/'cgroup').read_text()
            units=set(re.findall(r'([A-Za-z0-9_.@-]+\.service)(?:/|$)',groups,re.M))
            need(len(units)==1 and units<=known,'UNCLASSIFIED_PROJECT_PROCESS')
            if 'tokyo-restricted-model-executor.service' in units and b'python' in (process/'exe').readlink().name.encode():
                need(b'--enable-model-rpc\0' in args,'RETAINED_EXECUTOR_MODE_CHANGED')
        except (FileNotFoundError,ProcessLookupError): continue
    timers=command(['/usr/bin/systemctl','list-timers','--all','--no-legend','--no-pager'])
    need(timers.returncode==0,'TIMER_QUERY_FAILED')
    need(not any(word in timers.stdout.lower() for word in (b'trading',b'binance',b'xuanjun',b'portal')),
         'UNCLASSIFIED_PROJECT_TIMER')
    cron_roots=[Path('/etc/cron.d'),Path('/var/spool/cron'),Path('/etc/cron.hourly'),
                Path('/etc/cron.daily'),Path('/etc/cron.weekly'),Path('/etc/cron.monthly')]
    cron_files=[p for p in (Path('/etc/crontab'),Path('/etc/anacrontab')) if p.is_file()]
    for directory in cron_roots:
        if directory.is_dir():
            for current,dirs,names in os.walk(directory,followlinks=False):
                need(all(not (Path(current)/name).is_symlink() for name in dirs),'CRON_DIRECTORY_LINK')
                cron_files.extend(Path(current)/name for name in names)
    for p in cron_files:
        content=read(p,1000000)
        active=b'\n'.join(line for line in content.splitlines() if line.strip() and not line.lstrip().startswith(b'#'))
        need(not any(word in active.lower() for word in (b'/opt/trading-system',b'binance',b'xuanjun',b'portal')),
             'PROJECT_CRON_REQUIRES_CLASSIFICATION')

def source_preflight(capabilities):
    need(capabilities.get('code_sha256')==sha(root_read(Path(__file__))),'REMOTE_CONTROLLER_VERSION_MISMATCH')
    need(capabilities.get('service')=={'ActiveState':'inactive','MainPID':'0'},'TARGET_NOT_STOPPED')
    need(sha(read(BASE/'scripts/secure_secrets_portal_server.py'))==ENTRY_SHA,'SOURCE_PORTAL_CHANGED')
    need(not ctl(SOURCE_UNIT).get('DropInPaths'),'UNBOUND_SOURCE_DROPINS')
    need(sha(root_read(Path('/etc/systemd/system')/SOURCE_UNIT))==SOURCE_UNIT_SHA,'SOURCE_UNIT_CHANGED')
    for name,expected in capabilities['source_files'].items():
        if not Path(name).name.startswith('wecom_'):
            need(sha(read(BASE/name))==expected,'SOURCE_APPLICATION_DIFFERS_FROM_ACCEPTED_TARGET')
    for name,expected in capabilities['key_files'].items(): need(sha(root_read(KEY_ROOT/name))==expected,'KEY_PRESERVATION_CHANGED')
    for unit in (SOURCE_UNIT,*RETIRED):
        state=ctl(unit)
        if state.get('LoadState')!='not-found': stop_edges(state,(SOURCE_UNIT,*RETIRED))
    source_inventory()
    need(Path('/etc/systemd/system').stat().st_dev==SOURCE_JOB.parent.stat().st_dev,
         'SOURCE_UNIT_BACKUP_FILESYSTEM_DIFFERS')
    state=ctl(SOURCE_UNIT)
    need(state.get('ActiveState')=='active' and int(state.get('MainPID','0'))>0,'SOURCE_PORTAL_NOT_ACTIVE')
    need(listener_owned(state['MainPID'],18080),'SOURCE_LISTENER_OWNERSHIP')
    argv=(Path('/proc')/state['MainPID']/'cmdline').read_bytes().split(b'\0')
    need(any(arg in (b'scripts/secure_secrets_portal_server.py',str(BASE/'scripts/secure_secrets_portal_server.py').encode()) for arg in argv),
         'SOURCE_PROCESS_ENTRY_CHANGED')
    status=Path('/proc/self/status').read_text()
    capabilities_value=int(next(line.split()[1] for line in status.splitlines() if line.startswith('CapEff:')),16)
    need(capabilities_value & (1<<9) and capabilities_value & (1<<12),'KERNEL_FENCE_CAPABILITIES_MISSING')
    firewall_args('preflight')
    roots=[BASE/'database/data',*[BASE/p for p in PREFIXES]]
    allowed={'trading.db','trading.db-wal','trading.db-shm','trading.db-journal','.gitkeep'}
    need(set(p.name for p in roots[0].iterdir())<=allowed,'SHARED_DATABASE_DIRECTORY_REQUIRES_CLASSIFICATION')
    for root in roots:
        files=walk_files(root)
        for path in [root,*files.values()]: need(not flag(path)&IMMUTABLE,'EXISTING_EXTERNAL_SOURCE_FENCE')
    return {'pid':int(state['MainPID']),'retired_scope':list(RETIRED)}

def seal_source(job,pid):
    base,args=firewall_args(job)
    need(command(base+['-C',*args]).returncode!=0,'EXISTING_ADMISSION_RULE')
    result=command(base+['-I','INPUT','1',*args[1:]])
    if result.returncode: raise Unknown('ADMISSION_RULE_OUTCOME_UNKNOWN')
    need(command(base+['-C',*args]).returncode==0,'ADMISSION_GATE_NOT_VERIFIED')
    deadline=time.monotonic()+60; stable=0
    while time.monotonic()<deadline:
        need(ctl(SOURCE_UNIT).get('MainPID')==str(pid),'SOURCE_PROCESS_CHANGED_DURING_DRAIN')
        stable=stable+1 if tcp_drained(pid) else 0
        if stable>=3: return {'admission_sealed':True,'request_threads_drained':True,'pid':pid}
        print('SOURCE_DRAIN_WAITING',flush=True);time.sleep(1)
    # Target has not started and the source was never stopped: a known drain
    # timeout can safely remove this exact owned rule, preserving availability.
    need(ctl(SOURCE_UNIT).get('MainPID')==str(pid),'SOURCE_CHANGED_KEEP_GATE')
    target=remote_action('query',job)
    need(target['service']=={'ActiveState':'inactive','MainPID':'0'},'TARGET_CHANGED_KEEP_GATE')
    result=command(base+['-D',*args])
    if result.returncode: raise Unknown('ADMISSION_CLEANUP_UNKNOWN')
    need(command(base+['-C',*args]).returncode!=0,'ADMISSION_CLEANUP_NOT_CONFIRMED')
    raise Hold('SOURCE_DRAIN_NOT_PROVEN_OWN_GATE_REMOVED_TARGET_NOT_STARTED')

def assert_units_empty(units):
    for process in Path('/proc').iterdir():
        if not process.name.isdigit(): continue
        try: groups=(process/'cgroup').read_text().splitlines()
        except (FileNotFoundError,ProcessLookupError): continue
        for line in groups:
            parts=line.split(':',2)
            need(len(parts)==3,'CGROUP_FORMAT')
            need(not set(parts[2].split('/')).intersection(units),'STOPPED_UNIT_HAS_REMAINING_PROCESSES')


def source_stop_and_fence(job,journal,drain):
    for unit in RETIRED:
        state=ctl(unit)
        if state.get('LoadState')=='not-found': continue
        stop_edges(state,(SOURCE_UNIT,*RETIRED))
        result=command(['/usr/bin/systemctl','stop',unit],30)
        if result.returncode: raise Unknown('RETIRED_STOP_UNKNOWN')
        state=ctl(unit)
        need(state.get('MainPID')=='0' and state.get('ActiveState') in ('inactive','failed'),'RETIRED_STOP_NOT_CONFIRMED')
    source_inventory();stop_edges(ctl(SOURCE_UNIT),(SOURCE_UNIT,*RETIRED))
    result=command(['/usr/bin/systemctl','stop',SOURCE_UNIT],30)
    if result.returncode: raise Unknown('SOURCE_STOP_UNKNOWN')
    need(ctl(SOURCE_UNIT).get('MainPID')=='0','SOURCE_PORTAL_STILL_RUNNING')
    assert_units_empty((SOURCE_UNIT,*RETIRED))
    unit=Path('/etc/systemd/system')/SOURCE_UNIT
    need(sha(root_read(unit))==SOURCE_UNIT_SHA,'SOURCE_UNIT_DRIFT')
    os.rename(unit,SOURCE_JOB/'source-portal.service');fsync_dir(unit.parent)
    os.symlink('/dev/null',unit);fsync_dir(unit.parent)
    need(command(['/usr/bin/systemctl','daemon-reload']).returncode==0,'SOURCE_MASK_RELOAD_UNKNOWN')
    masked=ctl(SOURCE_UNIT)
    need(masked.get('MainPID')=='0' and masked.get('LoadState')=='masked','SOURCE_PERSISTENT_MASK_NOT_CONFIRMED')
    database=BASE/'database/data/trading.db'
    con=sqlite3.connect(database,timeout=5)
    try:
        need(con.execute('PRAGMA integrity_check').fetchone()[0]=='ok','SOURCE_DATABASE_INTEGRITY')
        result=con.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        need(result[0]==0 and result[1] in (0,-1) and result[2] in (0,-1),'DATABASE_CHECKPOINT_BUSY')
    finally: con.close()
    wal=Path(str(database)+'-wal')
    need(not wal.exists() or wal.stat().st_size==0,'UNMERGED_SOURCE_WAL')
    rollback=Path(str(database)+'-journal')
    if rollback.exists() and rollback.stat().st_size:
        need(not any(read(rollback)[:28]),'UNRESOLVED_ROLLBACK_JOURNAL')
    objects=[];membership={}
    for root in [BASE/'database/data',*[BASE/p for p in PREFIXES]]:
        files=walk_files(root)
        directories={root,*[p.parent for p in files.values()]}
        for current,dirs,_ in os.walk(root): directories.update(Path(current)/name for name in dirs)
        ordered=[*files.values(),*sorted(directories,key=lambda p:len(p.parts),reverse=True)]
        for path in ordered:
            info=path.stat();old=flag(path)
            need(not old&IMMUTABLE,'SOURCE_OBJECT_ALREADY_FENCED')
            if stat.S_ISDIR(info.st_mode): membership[str(path)]=sorted(os.listdir(path))
            else: need(stat.S_ISREG(info.st_mode) and info.st_nlink==1,'SOURCE_FILE_ALIAS')
            objects.append({'path':str(path),'device':info.st_dev,'inode':info.st_ino,'original_flags':old})
    # Original inode identities and flags are durable BEFORE the first flag write.
    create(SOURCE_JOB/'fence-plan.json',encode({'objects':objects,'membership':membership}))
    assert_no_other_writers(objects)
    for obj in objects:
        path=Path(obj['path']);info=path.lstat()
        need(not stat.S_ISLNK(info.st_mode) and (info.st_dev,info.st_ino)==(obj['device'],obj['inode']),
             'SOURCE_OBJECT_REPLACED')
        need(flag(path)==obj['original_flags'],'SOURCE_FLAGS_CHANGED')
        flag(path,obj['original_flags']|IMMUTABLE)
    for path,names in membership.items(): need(sorted(os.listdir(path))==names,'SOURCE_MEMBERSHIP_DRIFT')
    proof={**drain,'source_host':SOURCE,'portal_stopped':True,'portal_persistently_masked':True,
           'kernel_data_fence':True,'observed_at':int(time.time()),'objects':objects}
    create(SOURCE_JOB/'source-fence.json',encode(proof));check_source_fence(job,proof)
    return {'fence_sha256':sha(encode(proof)),'object_count':len(objects)}

def assert_no_other_writers(objects):
    identities={(obj['device'],obj['inode']) for obj in objects}
    database_ids={(obj['device'],obj['inode']) for obj in objects
                  if Path(obj['path']).parent==BASE/'database/data' and Path(obj['path']).name!='.gitkeep'}
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name)==os.getpid(): continue
        try:
            for descriptor in (process/'fd').iterdir():
                try:
                    info=descriptor.stat()
                    if (info.st_dev,info.st_ino) not in identities: continue
                    need((info.st_dev,info.st_ino) not in database_ids,'OTHER_CONSUMER_USING_SOURCE_DATABASE')
                    text=(process/'fdinfo'/descriptor.name).read_text()
                    flags=int(next(line.split()[1] for line in text.splitlines() if line.startswith('flags:')),8)
                    need(not flags&os.O_ACCMODE,'OTHER_PROCESS_HAS_WRITABLE_SOURCE_FD')
                except (FileNotFoundError,ProcessLookupError): continue
            for line in (process/'maps').read_text().splitlines():
                parts=line.split(None,5)
                if len(parts)<5 or len(parts[1])<4: continue
                major,minor=parts[3].split(':')
                identity=(os.makedev(int(major,16),int(minor,16)),int(parts[4]))
                need(identity not in database_ids,'OTHER_CONSUMER_MAPPING_SOURCE_DATABASE')
                if parts[1][1]!='w' or parts[1][3]!='s': continue
                need(identity not in identities,
                     'OTHER_PROCESS_HAS_WRITABLE_SHARED_SOURCE_MAPPING')
        except (FileNotFoundError,ProcessLookupError): continue


def check_source_fence(job,proof):
    base,args=firewall_args(job)
    need(command(base+['-C',*args]).returncode==0,'SOURCE_ADMISSION_GATE_LOST')
    state=ctl(SOURCE_UNIT)
    need(state.get('MainPID')=='0' and state.get('LoadState')=='masked','SOURCE_WRITER_RESUMED')
    assert_units_empty((SOURCE_UNIT,))
    preflight=SOURCE_JOB/'target_preflight.result.json'
    if preflight.exists():
        expected=json.loads(root_read(preflight))['evidence']['source_files']
        for name,value in expected.items():
            if not Path(name).name.startswith('wecom_'):
                need(sha(read(BASE/name))==value,'SOURCE_APPLICATION_CHANGED_DURING_CUTOVER')
    for obj in proof['objects']:
        p=Path(obj['path']);info=p.lstat()
        need(not stat.S_ISLNK(info.st_mode) and (info.st_dev,info.st_ino)==(obj['device'],obj['inode']) and
             flag(p)==obj['original_flags']|IMMUTABLE,'SOURCE_FENCE_CHANGED')

def source_package(job):
    proof=json.loads(root_read(SOURCE_JOB/'source-fence.json'));check_source_fence(job,proof)
    snapshot=SOURCE_JOB/'database.sqlite'
    source=sqlite3.connect((BASE/'database/data/trading.db').as_uri()+'?mode=ro&immutable=1',uri=True)
    target=sqlite3.connect(snapshot)
    try:
        source.backup(target);target.execute('PRAGMA journal_mode=DELETE')
        need(target.execute('PRAGMA integrity_check').fetchone()[0]=='ok','SNAPSHOT_INTEGRITY')
        ids={row[0] for row in target.execute('SELECT credential_id FROM credential_records')}
        need(ids==set(json.loads(root_read(KEY_ROOT/'credential-bindings.json'))['bindings']),'NEW_UNBOUND_CREDENTIALS')
    finally: target.close();source.close()
    files={'database.sqlite':snapshot,**{name:KEY_ROOT/name for name in KEYS}}
    for prefix in PREFIXES:
        files.update({prefix+'/'+rel:path for rel,path in walk_files(BASE/prefix).items()})
    need(len(files)<=999,'FINAL_DATA_MEMBER_LIMIT')
    manifest={'schema':1,'source_host':SOURCE,'target_host':TARGET,'job':job,
              'snapshot_kind':'FINAL_SOURCE_FENCED','fence':{k:v for k,v in proof.items() if k!='objects'},
              'files':{name:sha(read(path)) for name,path in files.items()}}
    package=SOURCE_JOB/'migration-data.tar.gz'
    with tarfile.open(package,'x:gz') as archive:
        for name,path in files.items():
            raw=read(path);need(sha(raw)==manifest['files'][name],'CAPTURE_DATA_DRIFT')
            info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o600
            archive.addfile(info,io.BytesIO(raw))
        raw=encode(manifest);info=tarfile.TarInfo('manifest.json');info.size=len(raw);info.mode=0o600
        archive.addfile(info,io.BytesIO(raw))
    with package.open('rb') as stream: os.fsync(stream.fileno())
    check_source_fence(job,proof)
    return {'sha256':sha(read(package,100000000)),'bytes':package.stat().st_size,'files':len(files)}

# SSH helpers below retain host-key verification and fixed existing endpoints.
# No root Python command is transmitted through the SSH account.
def ssh_json(remote,payload,timeout=120):
    process=subprocess.Popen(SSH+[remote],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    data=encode(payload);started=time.monotonic();first=True
    while True:
        try:
            stdout,stderr=process.communicate(data if first else None,timeout=10)
            break
        except subprocess.TimeoutExpired:
            first=False
            print('WAITING_REMOTE_RESULT',flush=True)
            if time.monotonic()-started>timeout:
                process.kill();process.communicate()
                raise Unknown('SSH_RESULT_UNKNOWN_NO_REPLAY')
    need(process.returncode==0 and len(stdout)<=200000 and len(stderr)<=100000,'REMOTE_RESULT_UNKNOWN_NO_REPLAY')
    result=json.loads(stdout)
    need(type(result)is dict,'REMOTE_JSON_SCHEMA')
    return result

def remote_action(operation,job,package_sha=None):
    result=ssh_json('/usr/bin/sudo -n /usr/local/sbin/pr99-portal-cutover',
                    {'operation':operation,'job':job,'sha256':package_sha})
    need(result.get('host')==TARGET and result.get('operation')==operation,'REMOTE_RESPONSE_BINDING')
    need(result.get('status')=='PASS','REMOTE_OPERATION_HOLD_QUERY_ONLY')
    return result['evidence']

RECEIVER=r'''
import os,sys,json,hashlib,fcntl,stat
from pathlib import Path
need=lambda value: value or sys.exit('HOLD_RECEIVER')
need(os.uname().nodename.split('.')[0]=='iZvt5t8tlrm8oiZ' and os.geteuid()==1001)
expected=sys.argv[1];size=int(sys.argv[2]);folder=Path('/home/openclaw_ops/pr99-controller-inbox')
need(len(expected)==64 and all(c in '0123456789abcdef' for c in expected) and 0<size<=100000000)
need(folder.is_dir() and not folder.is_symlink())
final=folder/(expected+'.tar.gz');partial=folder/(expected+'.tar.gz.partial')
need(not final.exists() and not final.is_symlink() and not partial.exists() and not partial.is_symlink())
fd=os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);h=hashlib.sha256();received=0
with os.fdopen(fd,'wb') as output:
 while received<size:
  body=sys.stdin.buffer.read(min(262144,size-received));need(body)
  output.write(body);h.update(body);received+=len(body)
 need(not sys.stdin.buffer.read(1));output.flush();os.fsync(output.fileno())
need(h.hexdigest()==expected)
with partial.open('rb') as stream:
 h=hashlib.sha256()
 while True:
  body=stream.read(1048576)
  if not body:break
  h.update(body)
need(h.hexdigest()==expected and partial.stat().st_size==size)
os.rename(partial,final)
fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
print(json.dumps({'status':'PASS','sha256':expected,'bytes':size}),flush=True)
'''

def transfer(package):
    path=SOURCE_JOB/'migration-data.tar.gz'
    remote=shlex.join(['/usr/bin/python3','-I','-B','-S','-c',RECEIVER,package['sha256'],str(package['bytes'])])
    process=subprocess.Popen(SSH+[remote],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        sent=0;last=-1
        with path.open('rb') as source:
            while True:
                body=source.read(262144)
                if not body:break
                process.stdin.write(body);process.stdin.flush();sent+=len(body)
                percent=sent*100//package['bytes']
                if percent//10!=last:
                    last=percent//10;print('TRANSFER_PROGRESS='+str(percent)+'%',flush=True)
        process.stdin.close();process.stdin=None
        stdout,stderr=process.communicate(timeout=90)
        need(process.returncode==0,'TRANSFER_UNKNOWN_PRESERVE_PARTIAL')
        result=json.loads(stdout)
        need(result=={'status':'PASS','sha256':package['sha256'],'bytes':package['bytes']},'TRANSFER_READBACK_NOT_VERIFIED')
    except BaseException:
        if process.poll()is None: process.kill();process.communicate()
        raise
    staged=ssh_json('/usr/bin/sudo -n /usr/local/sbin/pr99-migration-stage',{'sha256':package['sha256']})
    need(staged.get('status')=='PASS_STAGED' and staged.get('sha256')==package['sha256'],'ROOT_STAGE_NOT_VERIFIED')
    return {'sha256':package['sha256'],'disk_readback':'PASS','root_stage':'PASS'}

def target_main():
    host(TARGET)
    full_lock=os.open('/root/pr99-full-project-install.lock',os.O_RDWR|os.O_NOFOLLOW)
    fcntl.flock(full_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    fd=os.open(STATE/'lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    request=json.loads(sys.stdin.buffer.read(8193));operation=request.get('operation')
    need(operation in ('capabilities','preflight','prepare','check','start','cutover','query'),'UNSUPPORTED_OPERATION')
    if operation=='capabilities': evidence=target_capabilities()
    elif operation=='query':
        evidence={'checkpoint_exists':TARGET_JOB.exists(),
                  'service':{k:ctl(TARGET_UNIT).get(k) for k in ('ActiveState','MainPID')},
                  'records':Checkpoint(TARGET_JOB).summary() if TARGET_JOB.exists() else {}}
    else:
        journal=target_context(request)
        if operation=='preflight': action=target_preflight
        else:
            need(type(request['sha256'])is str and re.fullmatch('[0-9a-f]{64}',request['sha256']),'PACKAGE_SHA')
            if operation=='prepare': action=lambda:target_prepare(request['sha256'])
            elif operation=='check': action=lambda:target_check(request['sha256'])
            elif operation=='start': action=lambda:target_start(request['sha256'])
            else: action=lambda:target_cutover(request['sha256'],journal)
        evidence=journal.perform(operation,action,request['sha256'])
    print(json.dumps({'host':TARGET,'operation':operation,'status':'PASS','evidence':evidence}),flush=True)

def source_main(query=False):
    host(SOURCE)
    lock=os.open(SOURCE_LOCK,os.O_RDWR|os.O_NOFOLLOW)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return source_main_locked(query)
    finally: os.close(lock)

def source_main_locked(query=False):
    if SOURCE_JOB.exists():
        metadata=json.loads(root_read(SOURCE_JOB/'job.json'))
        physical={'portal':{k:ctl(SOURCE_UNIT).get(k) for k in ('LoadState','ActiveState','MainPID')}}
        base,args=firewall_args(metadata['job'])
        physical['admission_rule_present']=command(base+['-C',*args]).returncode==0
        plan_path=SOURCE_JOB/'fence-plan.json'
        if plan_path.exists():
            plan=json.loads(root_read(plan_path));count=0
            for obj in plan['objects']:
                path=Path(obj['path']);info=path.lstat()
                need((info.st_dev,info.st_ino)==(obj['device'],obj['inode']),'RECOVERY_SOURCE_INODE_CHANGED')
                count+=bool(flag(path)&IMMUTABLE)
            physical['kernel_objects']={'planned':len(plan['objects']),'immutable':count}
        result={'scope':'PORTAL_ONLY','checkpoint':str(SOURCE_JOB),'source_physical':physical,'records':Checkpoint(SOURCE_JOB).summary(),
                'target':remote_action('query',metadata['job'])}
        print(json.dumps(result,sort_keys=True,indent=2));return
    need(not query,'NO_SOURCE_CHECKPOINT')
    capabilities=remote_action('capabilities','portal-final-'+uuid.uuid4().hex)
    preflight=source_preflight(capabilities)
    SOURCE_JOB.mkdir(mode=0o700);fsync_dir(SOURCE_JOB.parent)
    job='portal-final-'+uuid.uuid4().hex
    create(SOURCE_JOB/'job.json',encode({'job':job,'code_sha256':sha(root_read(Path(__file__)))}))
    journal=Checkpoint(SOURCE_JOB)
    print('CHECKPOINT='+str(SOURCE_JOB),flush=True)
    journal.perform('target_preflight',lambda:remote_action('preflight',job))
    drain=journal.perform('source_seal',lambda:seal_source(job,preflight['pid']))
    journal.perform('source_fence',lambda:source_stop_and_fence(job,journal,drain))
    package=journal.perform('final_snapshot',lambda:source_package(job))
    journal.perform('transfer',lambda:transfer(package),package['sha256'])
    proof=json.loads(root_read(SOURCE_JOB/'source-fence.json'))
    for operation in ('prepare','check','start','cutover'):
        check_source_fence(job,proof)
        print('PHASE='+operation.upper(),flush=True)
        journal.perform('target_'+operation,lambda op=operation:remote_action(op,job,package['sha256']),package['sha256'])
    check_source_fence(job,proof)
    receipt={'status':'PASS_PORTAL_CUTOVER','scope':'PORTAL_ONLY','target_host':TARGET,
             'source_writer_resumed':False,'tokyo_model_rpc':'RETAINED',
             'wecom':'RETIRED_NOT_MIGRATED','whole_server_migration_complete':False}
    create(SOURCE_JOB/'receipt.json',encode(receipt))
    print(json.dumps(receipt,sort_keys=True),flush=True)
    print('RECEIPT='+str(SOURCE_JOB/'receipt.json'),flush=True)

def bootstrap():
    host(TARGET);static_target()
    lock=os.open('/root/pr99-full-project-install.lock',os.O_RDWR|os.O_NOFOLLOW)
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for parent in [STATE,*STATE.parents]:
        info=parent.lstat()
        need(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and
             info.st_uid==0 and not info.st_mode&0o022,'EXISTING_CHANNEL_DIRECTORY_UNSAFE')
    need(ctl(TARGET_UNIT).get('MainPID')=='0' and not (R/'cutover-ready.json').exists(),'BOOTSTRAP_TARGET_ALREADY_ACTIVE')
    visudo=shutil.which('visudo');need(visudo,'VISUDO_UNAVAILABLE')
    need(command([visudo,'-c']).returncode==0,'EXISTING_SUDOERS_INVALID')
    directory=Path('/usr/local/libexec/pr99-portal-cutover')
    directory.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
    if not directory.exists(): directory.mkdir(mode=0o755)
    for parent in [directory,*directory.parents]:
        info=parent.lstat()
        need(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and
             info.st_uid==0 and not info.st_mode&0o022,'CONTROLLER_DIRECTORY_UNSAFE')
    program=directory/'controller.py';raw=root_read(Path(__file__))
    if program.exists(): need(root_read(program)==raw,'EXISTING_DIFFERENT_CONTROLLER')
    else: create(program,raw,0o644)
    wrapper=Path('/usr/local/sbin/pr99-portal-cutover')
    wrapper_body=('#!/usr/bin/python3 -I\nimport os,sys,hashlib\n'
      'p='+repr(str(program))+'\n'
      'if len(sys.argv)!=1 or os.geteuid()!=0: raise SystemExit("HOLD_ARGUMENTS_OR_IDENTITY")\n'
      'with open(p,"rb") as f: b=f.read()\n'
      'if hashlib.sha256(b).hexdigest()!='+repr(sha(raw))+': raise SystemExit("HOLD_PROGRAM_CHANGED")\n'
      'os.execv("/usr/bin/python3",["/usr/bin/python3","-I","-B","-S",p,"--target"])\n').encode()
    if wrapper.exists(): need(root_read(wrapper)==wrapper_body,'EXISTING_DIFFERENT_WRAPPER')
    else: create(wrapper,wrapper_body,0o755)
    policy=('openclaw_ops ALL=(root) NOPASSWD: sha256:'+sha(wrapper_body)+' '+str(wrapper)+' ""\n').encode()
    policy_path=Path('/etc/sudoers.d/pr99-portal-cutover')
    temporary=Path(tempfile.mkdtemp(prefix='pr99-portal-channel-',dir='/root'))/'policy'
    create(temporary,policy,0o440)
    need(command([visudo,'-cf',str(temporary)]).returncode==0,'CANDIDATE_SUDOERS_INVALID')
    if policy_path.exists(): need(root_read(policy_path)==policy,'EXISTING_DIFFERENT_POLICY')
    else: create(policy_path,policy,0o440)
    need(command([visudo,'-c']).returncode==0,'FINAL_SUDOERS_INVALID')
    print('TARGET_CONTROLLER_ENTRY=INSTALLED',flush=True)
    print('PROGRAM_SHA256='+sha(raw),flush=True)
    print('SERVICE_STARTED=NO\nPRODUCTION_CUTOVER=NO',flush=True)

if __name__=='__main__':
    os.umask(0o077)
    try:
        if sys.argv[1:]==['--bootstrap']: bootstrap()
        elif sys.argv[1:]==['--target']: target_main()
        elif sys.argv[1:] in ([],['--query']): source_main(bool(sys.argv[1:]))
        else: raise Hold('UNSUPPORTED_ARGUMENTS')
    except BaseException as exc:
        reason=str(exc) if isinstance(exc,Hold) else type(exc).__name__
        if '--target' in sys.argv:
            print(json.dumps({'host':TARGET,'status':'HOLD','reason':reason}),flush=True)
        else:
            print('STATUS=HOLD\nREASON='+reason+'\nPRESERVE_CHECKPOINT_NO_BLIND_RETRY=YES',flush=True)
        sys.exit(2)
