"""Owner-selected Tokyo -> Korea model/Gateway handoff.

Uses the existing precopy and SSH aliases. Private artifacts stay on the hosts.
One attempt, durable intents, no automatic replay of uncertain mutations.
The current offline-project handoff is separate from production model cutover.
"""
import ast, fcntl, hashlib, http.client, json, os, pwd, re, shlex, socket, ssl, stat
import subprocess, sys, tarfile, tempfile, time
from pathlib import Path, PurePosixPath
import korea_project_controller as transport
from portal_total_controller import Checkpoint

SOURCE=transport.SOURCE
TARGET=transport.TARGET
JOB=Path('/root/pr99-korea-model-handoff-v1')
ROOT=Path('/opt/xuanjun-migration-s07/releases/korea-model-handoff-v1')
BASELINE=Path('/opt/xuanjun-migration-s07/releases/korea-project-precopy-f4db2e4e5f20')
NODE=Path('/opt/node-v24.16.0-linux-x64')
STATE=Path('/home/admin/.openclaw')
WORKSPACE=Path('/mnt/btrfs-workspace/ws-398ab6')
PROJECT=Path('/opt/trading-system')
KEY=Path('/home/admin/.ssh/binance_ops_model_rpc_tunnel')
KNOWN=Path('/home/admin/.ssh/known_hosts')
RUNTIME=[Path('/opt/trading-system')/'runtime/v8-domestic-operations/model-rpc',Path('/opt/trading-system')/'runtime/v8-domestic-operations/internal-bridge/secrets']
SYSTEM_SOURCE=['restricted-rpc-openai-shim.service','tokyo-restricted-model-executor.service']
TUNNELS=['domestic-model-rpc-tunnel.service','korea-novel-model-rpc-tunnel.service','provider-neutral-tokyo-tunnel.service']
PROTECTED=['morelogin-socks5-permanent.service','xuanjun-novel-factory.service','tailscaled.service','postgresql.service','redis.service']
NAMES={'gateway':'pr99-korea-openclaw.service','rpc':'pr99-korea-model-rpc.service','shim':'pr99-korea-openai-shim.service','local':'pr99-korea-local-model-forward.service','tunnel':'pr99-korea-domestic-model-tunnel.service','gateway_tunnel':'pr99-korea-gateway-tunnel.service','bridge_tunnel':'pr99-korea-domestic-bridge-tunnel.service'}
HASHES={'ai_service/domestic_model_provider_canary.py':'381dcdcf96c2cfc6f10346be2d4c99d97ff00c235d18eb1b01d5d8f040f14f6c',
'ai_service/internal_provider_neutral_bridge.py':'9a7703b0ecac1dbd614668ffa1aa88e265989513a3babb05333b3fd2226daff1',
'ai_service/openclaw_gateway_model_worker.mjs':'5319443ca9f9c8e0c6c276c4c27895f27f1add790eb42380a8f10d3af1ca1eee'}

def require(ok,why):
    if not ok: raise RuntimeError(why)

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()

def save(path,obj):
    transport.save(Path(path),obj)

def run(args,timeout=30):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    if p.returncode:
        if JOB.is_dir():
            stamp=JOB/('command-failure-'+str(time.time_ns())+'.log')
            with stamp.open('xb') as f:f.write(p.stdout+b'\n'+p.stderr);f.flush();os.fsync(f.fileno())
        raise RuntimeError('COMMAND_FAILED_PRIVATE_LOG_ONLY')
    return p.stdout

def userctl(*args):
    return ['/usr/bin/sudo','-n','-u','admin','/usr/bin/env','XDG_RUNTIME_DIR=/run/user/1000','/usr/bin/systemctl','--user',*args]

def show(unit,user=False):
    args=userctl('show',unit,'--property=ActiveState,MainPID,User,FragmentPath') if user else ['/usr/bin/systemctl','show',unit,'--property=ActiveState,MainPID,User,FragmentPath']
    return dict(x.split('=',1) for x in run(args).decode().splitlines() if '=' in x)

def proc_contract(unit,user=False):
    state=show(unit,user);pid=int(state.get('MainPID',0));require(state['ActiveState']=='active' and pid>0,'SOURCE_NOT_ACTIVE')
    p=Path('/proc')/str(pid)
    env={k.decode():v.decode() for item in (p/'environ').read_bytes().split(b'\0') if b'=' in item for k,v in [item.split(b'=',1)]}
    env={k:v for k,v in env.items() if k not in ('INVOCATION_ID','JOURNAL_STREAM','SYSTEMD_EXEC_PID','NOTIFY_SOCKET','LISTEN_PID','LISTEN_FDS')}
    argv=[x.decode() for x in (p/'cmdline').read_bytes().split(b'\0') if x]
    require(p.stat().st_uid==1000,'SOURCE_IDENTITY_CHANGED')
    return {'unit':unit,'state':state,'pid':pid,'argv':argv,'env':env}

def gateway_argv(path,env):
    lines=Path(path).read_text().splitlines();values=[x.split('=',1)[1] for x in lines if x.startswith('ExecStart=') and x.split('=',1)[1]]
    require(len(values)==1 and not any(x.endswith('\\') for x in lines),'UNSUPPORTED_GATEWAY_UNIT_SYNTAX')
    argv=shlex.split(values[0]);require(argv[:2]==[str(NODE/'bin/node'),str(NODE/'lib/node_modules/openclaw/dist/index.js')],'GATEWAY_ENTRY_CHANGED')
    require(not any('$' in x or '%' in x for x in argv),'GATEWAY_SPECIFIERS_REQUIRE_BINDING')
    return argv

def link_allowed(path,target,roots):
    dest=Path(os.path.normpath(target if target.startswith('/') else str(path.parent/target)))
    return any(dest==r or r in dest.parents for r in roots)

def archive_tree(tar,root,manifest,roots):
    """Stable private capture; symlink traversal is never followed implicitly."""
    paths=[root]
    if root.is_dir() and not root.is_symlink():
        for current,dirs,files in os.walk(root,followlinks=False):
            paths.extend(Path(current)/x for x in dirs+files)
    for p in paths:
        rel=p.as_posix().lstrip('/');s=p.lstat()
        if stat.S_ISLNK(s.st_mode):
            target=os.readlink(p);require(link_allowed(p,target,roots),'EXTERNAL_LINK_REQUIRES_CAPTURE')
            info=tarfile.TarInfo('rootfs/'+rel);info.type=tarfile.SYMTYPE;info.linkname=target;info.mode=stat.S_IMODE(s.st_mode)
            tar.addfile(info);manifest[rel]={'kind':'link','target':target};continue
        info=tarfile.TarInfo('rootfs/'+rel);info.uid=1000;info.gid=1000;info.mode=stat.S_IMODE(s.st_mode)&0o777
        if stat.S_ISDIR(s.st_mode):
            info.type=tarfile.DIRTYPE;tar.addfile(info);manifest[rel]={'kind':'directory','mode':info.mode};continue
        if stat.S_ISSOCK(s.st_mode):
            manifest[rel]={'kind':'ephemeral_socket_not_copied'};continue
        require(stat.S_ISREG(s.st_mode),'SPECIAL_FILE_REQUIRES_DECISION')
        fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as f:
            before=os.fstat(f.fileno());h=hashlib.sha256()
            class HashReader:
                def read(self,n=-1):
                    b=f.read(n);h.update(b);return b
            info.size=before.st_size;tar.addfile(info,HashReader());after=os.fstat(f.fileno())
        require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'CAPTURE_CHANGED_KEEP_CHECKPOINT')
        manifest[rel]={'kind':'file','bytes':info.size,'sha256':h.hexdigest(),'mode':info.mode}

def remote(action,payload=None,package=None,timeout=180):
    program=Path(__file__).read_text()
    # Target mode has no imports from the source helper modules.
    stub=program.split('\n# TARGET_PROGRAM_BEGIN\n',1)[1].split('\n# TARGET_PROGRAM_END\n',1)[0]
    request=json.dumps({'action':action,'payload':payload or {}})
    trampoline='import os,sys;os.execv("/bin/python3.11",["/bin/python3.11","-I","-B","-S","-c",sys.argv[1],sys.argv[2]])'
    cmd=shlex.join(['/usr/bin/sudo','-n','/usr/bin/python3','-I','-B','-S','-c',trampoline,stub,request])
    log=JOB/('remote-'+action+'-'+str(time.time_ns()))
    with (log.with_suffix('.out')).open('xb') as out,(log.with_suffix('.err')).open('xb') as err:
        inp=package.open('rb') if package else subprocess.DEVNULL
        try:
            p=subprocess.Popen(transport.SSH+[cmd],stdin=inp,stdout=out,stderr=err)
            deadline=time.monotonic()+timeout
            while True:
                try: code=p.wait(timeout=15);break
                except subprocess.TimeoutExpired:
                    print('WAITING_KOREA_'+action.upper(),flush=True)
                    if time.monotonic()>deadline:
                        p.kill();p.wait();raise RuntimeError('REMOTE_UNKNOWN_QUERY_ONLY')
        finally:
            if package: inp.close()
    require(code==0,'REMOTE_NONZERO_OR_UNKNOWN_QUERY_ONLY')
    result=json.loads(log.with_suffix('.out').read_text());require(result.get('host')==TARGET and result.get('status')=='PASS','REMOTE_RECEIPT')
    return result

TARGET_PROGRAM=r'''
# TARGET_PROGRAM_BEGIN
import os,sys,json,stat,hashlib,tarfile,subprocess,socket,ssl,http.client,time,fcntl,pwd,shutil
from pathlib import Path
TARGET='iZmj7a5kwr75qc1tul4kf9Z'
ROOT=Path('/opt/xuanjun-migration-s07/releases/korea-model-handoff-v1')
BASELINE=Path('/opt/xuanjun-migration-s07/releases/korea-project-precopy-f4db2e4e5f20')
NAMES={'gateway':'pr99-korea-openclaw.service','rpc':'pr99-korea-model-rpc.service','shim':'pr99-korea-openai-shim.service','local':'pr99-korea-local-model-forward.service','tunnel':'pr99-korea-domestic-model-tunnel.service','gateway_tunnel':'pr99-korea-gateway-tunnel.service','bridge_tunnel':'pr99-korea-domestic-bridge-tunnel.service'}
PROTECTED=['morelogin-socks5-permanent.service','xuanjun-novel-factory.service','tailscaled.service','postgresql.service','redis.service']
def need(v,why):
 if not v: raise RuntimeError(why)
def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
def cmd(args,timeout=30):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 if p.returncode:
  if ROOT.is_dir():write(ROOT/('command-failure-'+str(time.time_ns())+'.log'),p.stdout+b'\n'+p.stderr)
  raise RuntimeError('COMMAND_FAILED_PRIVATE_LOG')
 return p.stdout

def states(units):
 result={}
 for unit in units:
  raw=cmd(['/usr/bin/systemctl','show',unit,'--property=ActiveState,MainPID,LoadState'])
  result[unit]=dict(x.split('=',1) for x in raw.decode().splitlines() if '=' in x)
 return result

def write(p,body,mode=0o600):
 with p.open('xb') as f: f.write(body);f.flush();os.fchmod(f.fileno(),mode);os.fsync(f.fileno())

def private(path):
 return not any(p.is_symlink() for p in [path]+list(path.parents))

def install_unit(role,contract):
 app=BASELINE/'opt/trading-system'
 # The source project is the verified precopy. Only the declared current model
 # source files are refreshed in a separate private app below.
 app=ROOT/'app'
 bindings=[(app,'/opt/trading-system'),(ROOT/'rootfs/opt/node-v24.16.0-linux-x64','/opt/node-v24.16.0-linux-x64'),
 (ROOT/'rootfs/home/admin/.openclaw','/home/admin/.openclaw'),
 (ROOT/'rootfs/mnt/btrfs-workspace/ws-398ab6','/mnt/btrfs-workspace/ws-398ab6')]
 header='[Unit]\nDescription=PR99 Korea '+role+'\nAfter=network-online.target\nWants=network-online.target\n[Service]\nType=simple\nUser=admin\nGroup=admin\nUMask=0077\nWorkingDirectory=/opt/trading-system\nRestart=on-failure\nRestartSec=5\nTimeoutStopSec=90\nKillMode=control-group\nNoNewPrivileges=yes\nPrivateTmp=yes\nProtectSystem=strict\nProtectHome=tmpfs\nMemoryAccounting=yes\nSlice=pr99koreamodel.slice\nOOMScoreAdjust=500\n'
 dependencies={'gateway':['gateway_tunnel','bridge_tunnel'],'rpc':['gateway'],'shim':['rpc'],'local':['rpc'],'tunnel':['rpc']}
 if role in dependencies:
  related=' '.join(NAMES[x] for x in dependencies[role])
  header=header.replace('[Service]','After='+related+'\nRequires='+related+'\n[Service]',1)
 for source,dest in bindings:
  kind='BindReadOnlyPaths=' if dest in ('/opt/trading-system','/opt/node-v24.16.0-linux-x64') else 'BindPaths='
  header+=kind+str(source)+':'+dest+'\n'
 header+='BindPaths='+str(app/'runtime')+':/opt/trading-system/runtime\n'
 header+='BindReadOnlyPaths='+str(ROOT/'contract.json')+':/srv/pr99-model-contract.json\n'
 header+='BindReadOnlyPaths='+str(ROOT/'launcher.py')+':/srv/pr99-model-launcher.py\n'
 if role in ('tunnel','gateway_tunnel','bridge_tunnel'):
  for name in contract['ssh_files']:
   header+='BindReadOnlyPaths='+str(ROOT/'rootfs/home/admin/.ssh'/name)+':/home/admin/.ssh/'+name+'\n'
 header+='ExecStart=/bin/python3.11 -I -B -S /srv/pr99-model-launcher.py '+role+'\n[Install]\nWantedBy=multi-user.target\n'
 path=Path('/etc/systemd/system')/NAMES[role]
 need(not path.exists() and not path.is_symlink(),'UNIT_CONFLICT')
 write(path,header.encode(),0o644)

LAUNCHER=r"""
import os,sys,json,runpy,socket,threading,select
from pathlib import Path
role=sys.argv[1]
c=json.loads(Path('/srv/pr99-model-contract.json').read_text())
if role=='local':
 def relay(client):
  try:
   with client,socket.create_connection(('127.0.0.1',20443),timeout=10) as upstream:
    client.setblocking(False);upstream.setblocking(False)
    sockets=[client,upstream]
    while True:
     readable,_,_=select.select(sockets,[],[],120)
     if not readable:return
     for current in readable:
      data=current.recv(65536)
      if not data:return
      other=upstream if current is client else client
      other.setblocking(True);other.settimeout(30);other.sendall(data);other.setblocking(False)
  except OSError:pass
 server=socket.socket();server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);server.bind(('127.0.0.1',19444));server.listen(64)
 while True:
  client,_=server.accept();threading.Thread(target=relay,args=(client,),daemon=True).start()
else:
 cfg=c[role];os.environ.update(cfg['env']);argv=cfg['argv']
 if role in ('gateway','tunnel','gateway_tunnel','bridge_tunnel'):os.execve(argv[0],argv,os.environ)
 sys.path[:0]=['/opt/trading-system','/opt/trading-system/venv/lib/python3.11/site-packages']
 sys.argv=argv[1:];runpy.run_path(argv[1],run_name='__main__')
"""

def tls_health(port,pin):
 conn=http.client.HTTPSConnection('127.0.0.1',port,context=ssl._create_unverified_context(),timeout=10)
 try:
  conn.request('GET','/healthz');actual=hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest();r=conn.getresponse();body=json.loads(r.read(100000))
  need(actual==pin and r.status==200 and body.get('status')=='PASS','TLS_HEALTH_FAILED')
 finally:conn.close()

need(os.geteuid()==0 and os.uname().nodename.split('.')[0]==TARGET,'HOST_OR_ROOT')
os.umask(0o077)
request=json.loads(sys.argv[1]);action=request['action'];payload=request['payload']
listed=cmd(['/usr/bin/systemctl','list-units','--type=service','--all','--no-legend','--no-pager']).decode()
PROTECTED=sorted(set(PROTECTED)|{line.split()[0] for line in listed.splitlines() if line.split() and any(x in line.lower() for x in ('postgres','redis','morelogin','novel-factory','tailscaled','actions.runner'))})
need(action in ('preflight','receive','install','start','canary','local','tunnel','stop','status','enable','nodecheck','sshcheck'),'ACTION')
lock=os.open('/root/pr99-korea-project-install.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
result={'host':TARGET,'status':'PASS','action':action}
if action=='preflight':
 need(not ROOT.exists() and private(ROOT),'EXISTING_ATTEMPT_RECONCILE')
 need(pwd.getpwnam('admin').pw_uid==1000,'ADMIN_IDENTITY')
 for port in (11505,19150,19443,20443,19445):
  s=socket.socket()
  try:s.bind(('0.0.0.0',port))
  finally:s.close()
 for v in states(list(NAMES.values())+['pr99koreamodel.slice']).values():need(v['LoadState']=='not-found','EXISTING_UNIT')
 mem=dict((x.split(':')[0],int(x.split()[1])) for x in Path('/proc/meminfo').read_text().splitlines() if len(x.split())>=2 and x.split()[1].isdigit())
 need(mem.get('MemAvailable',0)>=700000,'INSUFFICIENT_MEMORY_FOR_GATEWAY_PREFLIGHT')
 need(shutil.disk_usage('/opt').free>payload['required_bytes']*2+1073741824,'DISK_SPACE')
 need((BASELINE/'PR99_KOREA_EXTRACTION_RECEIPT.json').is_file(),'PRECOPY_MISSING')
 result['protected']=states(PROTECTED);result['available_memory_kib']=mem['MemAvailable'];result['memory_budget_bytes']=max(0,(mem['MemAvailable']-262144)*1024)
elif action=='receive':
 segment=payload['segment'];need(segment in ('static','state'),'SEGMENT')
 if segment=='static':
  need(not ROOT.exists() and private(ROOT),'RECEIVE_CONFLICT');ROOT.mkdir(mode=0o700)
 else:
  need(ROOT.exists() and private(ROOT) and (ROOT/'received-static.json').is_file() and not (ROOT/'received-state.json').exists(),'STATE_CONFLICT')
 package=ROOT/('input-'+segment+'.tar.gz');h=hashlib.sha256();left=payload['bytes'];need(0<left<12000000000,'SIZE')
 with package.open('xb') as out:
  while left:
   b=sys.stdin.buffer.read(min(left,1048576));need(bool(b),'SHORT_TRANSFER');out.write(b);h.update(b);left-=len(b)
  need(not sys.stdin.buffer.read(1),'EXTRA_BYTES');out.flush();os.fsync(out.fileno())
 need(h.hexdigest()==payload['sha256'] and digest(package)==payload['sha256'],'PACKAGE_HASH')
 with tarfile.open(package,'r:gz') as t:
  members=t.getmembers();seen=set();links=[]
  need(len(members)<250000 and sum(m.size for m in members)<12000000000,'UNPACK_LIMIT')
  for m in members:
   parts=m.name.split('/');need(not m.name.startswith('/') and all(p not in ('','.','..') for p in parts) and '\\' not in m.name and m.name not in seen,'UNSAFE_MEMBER');seen.add(m.name)
   need(m.isdir() or m.isfile() or m.issym(),'MEMBER_TYPE')
   need(m.name in ('contract.json','manifest.json') or m.name.startswith(('rootfs/opt/node-v24.16.0-linux-x64','rootfs/home/admin/.openclaw','rootfs/mnt/btrfs-workspace/ws-398ab6','rootfs/home/admin/.ssh/','rootfs/opt/trading-system/runtime/','source/')),'MEMBER_SCOPE')
   dest=ROOT/('manifest-'+segment+'.json') if m.name=='manifest.json' else ROOT/m.name;need(private(dest.parent),'PARENT_LINK')
   if segment=='static':need(m.name=='manifest.json' or m.name=='rootfs/opt/node-v24.16.0-linux-x64' or m.name.startswith(('rootfs/opt/node-v24.16.0-linux-x64/','rootfs/home/admin/.ssh/')),'STATIC_SCOPE')
   else:need(not m.name.startswith(('rootfs/opt/node-v24.16.0-linux-x64','rootfs/home/admin/.ssh/')),'STATE_SCOPE')
   if m.issym():links.append(m);continue
   dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
   if m.isdir():dest.mkdir(exist_ok=True,mode=0o700)
   else:
    with t.extractfile(m) as inp,dest.open('xb') as out:shutil.copyfileobj(inp,out,1048576);out.flush();os.fsync(out.fileno())
    os.chmod(dest,m.mode&0o777);os.chown(dest,1000,1000)
  manifest=json.loads((ROOT/('manifest-'+segment+'.json')).read_text())
  for name,meta in manifest.items():
   p=ROOT/'rootfs'/name
   if meta['kind']=='file':need(p.stat().st_size==meta['bytes'] and digest(p)==meta['sha256'],'FILE_READBACK')
  for m in links:
   dest=ROOT/m.name;target=os.path.normpath(m.linkname if m.linkname.startswith('/') else '/'+str(Path(m.name).parent).removeprefix('rootfs/')+'/'+m.linkname)
   allowed=('/opt/node-v24.16.0-linux-x64/','/home/admin/.openclaw/','/mnt/btrfs-workspace/ws-398ab6/','/opt/trading-system/runtime/')
   need(any(target==a.rstrip('/') or target.startswith(a) for a in allowed),'LINK_ESCAPE')
   dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700);dest.symlink_to(m.linkname)
  for name,meta in sorted(manifest.items(),key=lambda x:len(Path(x[0]).parts),reverse=True):
   p=ROOT/'rootfs'/name
   if meta['kind']=='directory':os.chown(p,1000,1000);os.chmod(p,meta['mode']&0o777)
 write(ROOT/('received-'+segment+'.json'),json.dumps(payload,sort_keys=True).encode())
 result['package_sha256']=payload['sha256'];result['files']=len(manifest)
elif action=='nodecheck':
 version=cmd([str(ROOT/'rootfs/opt/node-v24.16.0-linux-x64/bin/node'),'--version']).decode().strip();need(version=='v24.16.0','NODE_RUNTIME_INCOMPATIBLE');result['node_version']=version
elif action=='sshcheck':
 verdicts=[]
 for original in payload['commands']:
  need(original[0]=='/usr/bin/ssh' and original[-1] and len(original)<80,'SSH_CHECK_COMMAND')
  argv=[];i=0
  while i<len(original):
   arg=original[i]
   if arg in ('-L','-R','-D'):i+=2;continue
   argv.append(arg.replace('/home/admin/.ssh/',str(ROOT/'rootfs/home/admin/.ssh')+'/'));i+=1
  argv.insert(1,'-v');argv[1:1]=['-o','ConnectTimeout=10','-o','ConnectionAttempts=1']
  log=ROOT/('ssh-preflight-'+str(len(verdicts))+'.log')
  need(not log.exists(),'SSH_CHECK_ALREADY_ATTEMPTED')
  with log.open('xb') as err:
   process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=err)
   try:
    deadline=time.monotonic()+15;authenticated=False
    while time.monotonic()<deadline:
     if b'Authenticated to ' in log.read_bytes():authenticated=True;break
     if process.poll() is not None:break
     time.sleep(.25)
    need(authenticated,'SSH_AUTHENTICATION_FROM_KOREA_NOT_PROVEN')
   finally:
    if process.poll() is None:process.terminate()
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:process.kill();process.wait()
  verdicts.append('PASS_AUTHENTICATED_WITHOUT_FORWARD_CHANGE')
 result['ssh_authentication']=verdicts
elif action=='install':
 need((ROOT/'received-state.json').is_file(),'NOT_RECEIVED')
 contract=json.loads((ROOT/'contract.json').read_text())
 app=ROOT/'app';need(not app.exists(),'APP_CONFLICT');source_project=Path(contract['project_directory'])
 need(source_project.name=='project' and source_project.parent.name=='korea-current-recovery-'+contract['project_package_sha256'] and private(source_project),'CURRENT_PROJECT_BINDING')
 point=json.loads((source_project.parent/'receipt.json').read_text());need(point.get('status')=='PASS_CURRENT_OFFLINE_RECOVERY' and point.get('package_sha256')==contract['project_package_sha256'],'CURRENT_PROJECT_RECEIPT')
 shutil.copytree(source_project,app,symlinks=True)
 # Copy only current model program files; the portal and trading DB are not activated.
 for name,hash_value in contract['source_hashes'].items():
  src=ROOT/'source'/name;need(digest(src)==hash_value,'CURRENT_SOURCE_HASH');dest=app/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
 for current,dirs,files in os.walk(app,followlinks=False):
  os.chown(current,1000,1000);os.chmod(current,0o700)
  for name in files:
   p=Path(current)/name
   if not p.is_symlink():os.chown(p,1000,1000);os.chmod(p,0o600)
 for rel in ('runtime/v8-domestic-operations/model-rpc','runtime/v8-domestic-operations/internal-bridge/secrets'):
  dest=app/rel
  if dest.exists():shutil.rmtree(dest)
  shutil.copytree(ROOT/'rootfs/opt/trading-system'/rel,dest,symlinks=True)
  for current,dirs,files in os.walk(dest,followlinks=False):
   os.chown(current,1000,1000);os.chmod(current,0o700)
   for name in files:
    q=Path(current)/name
    if not q.is_symlink():os.chown(q,1000,1000);os.chmod(q,0o600)
 write(ROOT/'launcher.py',LAUNCHER.encode(),0o644);os.chown(ROOT/'contract.json',1000,1000)
 version=cmd([str(ROOT/'rootfs/opt/node-v24.16.0-linux-x64/bin/node'),'--version']).decode().strip();need(version=='v24.16.0','NODE_RUNTIME_INCOMPATIBLE')
 slice_path=Path('/etc/systemd/system/pr99koreamodel.slice');need(not slice_path.exists() and not slice_path.is_symlink(),'SLICE_CONFLICT')
 write(slice_path,('[Unit]\nDescription=PR99 isolated model resource budget\n[Slice]\nMemoryAccounting=yes\nMemoryLimit='+str(contract['memory_budget_bytes'])+'\n').encode(),0o644)
 for role in NAMES:install_unit(role,contract)
 cmd(['/usr/bin/systemctl','daemon-reload'])
 result['node_version']=version
elif action in ('start','local','tunnel'):
 roles=['gateway_tunnel','bridge_tunnel','gateway','rpc','shim'] if action=='start' else [action]
 for role in roles:
  cmd(['/usr/bin/systemctl','start',NAMES[role]],120)
  deadline=time.monotonic()+60
  while True:
   state=states([NAMES[role]])[NAMES[role]]
   if state['ActiveState']=='active' and int(state['MainPID'])>0:
    if role in ('gateway','gateway_tunnel','bridge_tunnel'):
     try:
      with socket.create_connection(('127.0.0.1',11505 if role=='gateway' else (19150 if role=='gateway_tunnel' else 19443)),timeout=1):pass
      if role=='bridge_tunnel':
       cfg=json.loads((ROOT/'contract.json').read_text());tls_health(19443,cfg['domestic_bridge_pin'])
      break
     except (OSError,RuntimeError,ValueError):pass
    else:break
   need(time.monotonic()<deadline,'START_DEADLINE');time.sleep(1)
 if action=='start':
  cfg=json.loads((ROOT/'contract.json').read_text());deadline=time.monotonic()+60
  while True:
   connection=http.client.HTTPConnection('127.0.0.1',19445,timeout=5)
   try:
    connection.request('GET',cfg['shim_health_path']);response=connection.getresponse();body=json.loads(response.read(100000));need(response.status==200 and all(body.get(k)==v for k,v in cfg['shim_health_fields'].items()),'SHIM_HEALTH_MISMATCH');break
   except Exception:need(time.monotonic()<deadline,'SHIM_HEALTH_DEADLINE');time.sleep(2)
   finally:connection.close()
 if action in ('start','local'):
  deadline=time.monotonic()+90
  while True:
   try:tls_health(20443 if action=='start' else 19444,payload['pin']);break
   except Exception:
    need(time.monotonic()<deadline,'HEALTH_DEADLINE');time.sleep(2)
elif action=='canary':
 # Enter precisely the service's existing mount namespace; no second worker stack.
 state=states([NAMES['rpc']])[NAMES['rpc']];pid=int(state['MainPID']);need(pid>0,'RPC_NOT_RUNNING')
 probe="""import sys,json
from pathlib import Path
sys.path[:0]=['/opt/trading-system','/opt/trading-system/venv/lib/python3.11/site-packages']
from ai_service.internal_provider_neutral_bridge import ProviderNeutralBridgeClient,BridgeSecretProvider,make_model_completion_payload,make_model_rpc_envelope
cfg=json.loads(Path('/srv/pr99-model-contract.json').read_text())
c=ProviderNeutralBridgeClient('127.0.0.1',20443,secret_provider=BridgeSecretProvider(secret_dir=Path('/opt/trading-system/runtime/v8-domestic-operations/internal-bridge/secrets')),cert_sha256=cfg['pin'],timeout=90)
request=make_model_completion_payload('Reply only MIGRATION_OK. Do not use tools.',provider='openai',model='gpt-5.6-sol')
r=c.model_complete(make_model_rpc_envelope(request))
assert r.status=='PASS'
def nodes(value):
 if isinstance(value,dict):
  yield value
  for item in value.values():yield from nodes(item)
 elif isinstance(value,list):
  for item in value:yield from nodes(item)
items=list(nodes(r.payload))
assert not any(n.get('fallback_attempts') for n in items)
assert any(n.get('provider')=='openai' and n.get('model')=='gpt-5.6-sol' and isinstance(n.get('reply') or n.get('text'),str) and (n.get('reply') or n.get('text')).strip() for n in items)
print('REAL_MODEL_CANARY=PASS')
"""
 ns=shutil.which('nsenter');need(ns is not None,'NSENTER_MISSING')
 out=cmd([ns,'--target',str(pid),'--mount','--setgid','1000','--setuid','1000','--','/usr/bin/env','HOME=/home/admin','/bin/python3.11','-I','-B','-S','-c',probe],120)
 need(out.strip()==b'REAL_MODEL_CANARY=PASS','MODEL_CANARY');result['real_model']='PASS'
elif action=='stop':
 for role in ('tunnel','local','shim','rpc','gateway','gateway_tunnel','bridge_tunnel'):
  if states([NAMES[role]])[NAMES[role]]['LoadState']!='not-found':cmd(['/usr/bin/systemctl','stop',NAMES[role]],120)
 for v in states(list(NAMES.values())).values():need(v['ActiveState']=='inactive' and v['MainPID']=='0','STOP_NOT_PROVEN')
elif action=='enable':
 cmd(['/usr/bin/systemctl','enable',*NAMES.values()])
else:result['services']=states(list(NAMES.values()))
result['protected']=states(PROTECTED)
print(json.dumps(result,sort_keys=True),flush=True)
# TARGET_PROGRAM_END
'''


def main():
    require(os.geteuid()==0 and os.uname().nodename.split('.')[0]==SOURCE,'SOURCE_HOST_OR_ROOT');os.umask(0o077)
    if not JOB.exists():
        print('PHASE=REUSE_CURRENT_PROJECT_SYNC',flush=True)
        helper=Path(__file__).parent/'korea_current_sync.py'
        require(helper.is_file() and not helper.is_symlink(),'CURRENT_SYNC_HELPER_MISSING')
        execute="import sys,runpy;sys.path.insert(0,sys.argv[1]);runpy.run_path(sys.argv[2],run_name='__main__')"
        subprocess.run(['/usr/bin/python3','-I','-B','-S','-c',execute,str(helper.parent),str(helper)],check=True,timeout=2400)
    lock=os.open('/root/pr99-controller.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if JOB.exists():
        print('MODE=QUERY_ONLY_NO_REPLAY',flush=True);print('CHECKPOINT='+str(JOB),flush=True)
        print(json.dumps({k:v['status'] for k,v in Checkpoint(JOB).summary().items()},sort_keys=True),flush=True)
        print(json.dumps(remote('status'),sort_keys=True),flush=True);return
    JOB.mkdir(mode=0o700);print('CHECKPOINT='+str(JOB),flush=True);journal=Checkpoint(JOB)
    try:
        # Source-side exact references are known from Owner's live process probes.
        for name,value in HASHES.items():require(sha(PROJECT/name)==value,'SOURCE_CODE_CHANGED')
        require(sha(NODE/'lib/node_modules/openclaw/package.json')=='226a35245ba5ba8b36ac707e68439eef62a9abb07a3234a154008d959976be7e','OPENCLAW_VERSION_CHANGED')
        require(STATE.is_dir() and not STATE.is_symlink() and (STATE/'workspace').is_symlink() and (STATE/'workspace').resolve()==WORKSPACE,'WORKSPACE_BINDING_CHANGED')
        contracts={'gateway':proc_contract('openclaw-gateway.service',True),'rpc':proc_contract(SYSTEM_SOURCE[1]),'shim':proc_contract(SYSTEM_SOURCE[0])}
        point=json.loads(Path('/root/pr99-korea-current-sync-v1/receipt.json').read_text())
        require(point.get('status')=='PASS_CURRENT_OFFLINE_RECOVERY','CURRENT_PROJECT_NOT_ACCEPTED')
        contracts['project_directory']=point['directory']+'/project';contracts['project_package_sha256']=point['package_sha256']
        shim_tree=ast.parse((PROJECT/'ai_service/restricted_rpc_openai_shim.py').read_text())
        constants={t.id:n.value.value for n in shim_tree.body if isinstance(n,ast.Assign) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str) for t in n.targets if isinstance(t,ast.Name)}
        health_paths=set()
        for fn in ast.walk(shim_tree):
            if isinstance(fn,ast.FunctionDef) and fn.name=='do_GET':
                for n in ast.walk(fn):
                    value=n.value if isinstance(n,ast.Constant) else constants.get(n.id) if isinstance(n,ast.Name) else None
                    if isinstance(value,str) and value in ('/healthz','/health'):health_paths.add(value)
        require(bool(health_paths),'SHIM_HEALTH_ROUTE_NOT_BOUND')
        contracts['shim_health_path']='/healthz' if '/healthz' in health_paths else '/health'
        connection=http.client.HTTPConnection('127.0.0.1',19445,timeout=10)
        try:
            connection.request('GET',contracts['shim_health_path']);response=connection.getresponse();body=json.loads(response.read(100000));require(response.status==200 and isinstance(body,dict),'SOURCE_SHIM_HEALTH')
            contracts['shim_health_fields']={k:body[k] for k in ('status','model','allowed_model','remote_model','transport','service','api_contract_version') if k in body}
            require(bool(contracts['shim_health_fields']),'SHIM_HEALTH_FIELDS')
        finally:connection.close()
        bridge=http.client.HTTPSConnection('127.0.0.1',19443,context=ssl._create_unverified_context(),timeout=10)
        try:
            bridge.request('GET','/healthz');contracts['domestic_bridge_pin']=hashlib.sha256(bridge.sock.getpeercert(binary_form=True)).hexdigest();response=bridge.getresponse();require(response.status==200 and json.loads(response.read(100000)).get('status')=='PASS','SOURCE_DOMESTIC_BRIDGE_HEALTH')
        finally:bridge.close()
        contracts['gateway']['argv']=gateway_argv('/home/admin/.config/systemd/user/openclaw-gateway.service',contracts['gateway']['env'])
        for role in ('rpc','shim'):require(contracts[role]['argv'][1].startswith(str(PROJECT)+'/'),'SOURCE_ENTRY_CHANGED')
        tunnel=proc_contract(TUNNELS[0]);require('-R' in tunnel['argv'] and '127.0.0.1:19444:127.0.0.1:20443' in tunnel['argv'] and str(KEY) in tunnel['argv'] and '47.101.152.210' in tunnel['argv'],'DOMESTIC_TUNNEL_CHANGED')
        contracts['tunnel']=tunnel
        contracts['korea_source_tunnel']=proc_contract(TUNNELS[1])
        contracts['bridge_tunnel']=proc_contract(TUNNELS[2])
        require('127.0.0.1:19443:127.0.0.1:18443' in contracts['bridge_tunnel']['argv'],'DOMESTIC_BRIDGE_TUNNEL_CHANGED')
        require('127.0.0.1:19444:127.0.0.1:20443' in contracts['korea_source_tunnel']['argv'],'KOREA_SOURCE_TUNNEL_CHANGED')
        gateway_ssh=[]
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:
                if 'openclaw-gateway.service' in (proc/'cgroup').read_text() and Path(os.readlink(proc/'exe')).name=='ssh':
                    require(proc.stat().st_uid==1000,'GATEWAY_SSH_IDENTITY')
                    argv=[x.decode() for x in (proc/'cmdline').read_bytes().split(b'\0') if x]
                    env={k.decode():v.decode() for item in (proc/'environ').read_bytes().split(b'\0') if b'=' in item for k,v in [item.split(b'=',1)]}
                    gateway_ssh.append({'argv':argv,'env':env})
            except (FileNotFoundError,ProcessLookupError):continue
        gateway_group_other=[]
        known_gateway_pids={contracts['gateway']['pid']}
        # A concurrent unrelated Codex/development child must not be silently
        # killed by stopping the shared source Gateway control group.
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:
                if 'openclaw-gateway.service' not in (proc/'cgroup').read_text():continue
                exe=Path(os.readlink(proc/'exe')).name
                if int(proc.name) not in known_gateway_pids and exe!='ssh':gateway_group_other.append(int(proc.name))
            except (FileNotFoundError,ProcessLookupError):continue
        if gateway_group_other:
            save(JOB/'source-gateway-other-tasks.json',{'pids':gateway_group_other})
            raise RuntimeError('SOURCE_GATEWAY_OTHER_TASKS_REQUIRE_DRAIN')
        require(len(gateway_ssh)==1,'GATEWAY_FORWARDING_CONTRACT_CHANGED')
        require('127.0.0.1:19150:127.0.0.1:10150' in gateway_ssh[0]['argv'],'GATEWAY_FORWARDING_CHANGED')
        contracts['gateway_tunnel']=gateway_ssh[0]
        ssh_files={KEY,KNOWN}
        for role in ('tunnel','gateway_tunnel','bridge_tunnel'):
            cfg=contracts[role]
            effective=run(['/usr/bin/sudo','-n','-u','admin','/usr/bin/ssh','-G',*cfg['argv'][1:]],30).decode()
            settings={};identities=[]
            for line in effective.splitlines():
                k,_,v=line.partition(' ')
                if k=='identityfile':identities.append(v)
                else:settings[k]=v
            require(settings.get('proxycommand','none')=='none' and settings.get('proxyjump','none')=='none','SSH_PROXY_DEPENDENCY_UNBOUND')
            identity=next((Path(x.replace('~','/home/admin',1)) for x in identities if Path(x.replace('~','/home/admin',1)).is_file()),None)
            require(identity is not None and identity.parent==Path('/home/admin/.ssh') and not identity.is_symlink(),'SSH_IDENTITY_FILE_UNBOUND')
            known_paths=[Path(x.replace('~','/home/admin',1)) for x in shlex.split(settings.get('userknownhostsfile',''))]
            known=next((p for p in known_paths if p.is_file()),None)
            require(known is not None and known.parent==Path('/home/admin/.ssh') and not known.is_symlink(),'SSH_HOST_TRUST_UNBOUND')
            require(settings.get('certificatefile','none')=='none','SSH_CERTIFICATE_DEPENDENCY_UNBOUND')
            require(settings.get('hostname') and settings.get('user') and settings.get('port'),'SSH_DESTINATION')
            forwards=[]
            for i,arg in enumerate(cfg['argv']):
                if arg in ('-L','-R') and i+1<len(cfg['argv']):forwards.extend([arg,cfg['argv'][i+1]])
            require(bool(forwards),'SSH_FORWARDING_MISSING')
            argv=['/usr/bin/ssh','-N','-T','-F','/dev/null','-i',str(identity),'-o','UserKnownHostsFile='+str(known),'-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3']
            if settings.get('hostkeyalias','none')!='none':argv+=['-o','HostKeyAlias='+settings['hostkeyalias']]
            argv+=['-o','IdentitiesOnly=yes','-o','ForwardAgent=no','-o','ControlMaster=no','-o','ControlPath=none']
            cfg['argv']=argv+forwards+['-l',settings['user'],'-p',settings['port'],settings['hostname']]
            cfg['env']={k:v for k,v in cfg['env'].items() if k in ('HOME','PATH','LANG')}
            ssh_files.update((identity,known))
        contracts['ssh_files']=sorted(str(p.relative_to('/home/admin/.ssh')) for p in ssh_files)
        require(all(re.fullmatch('[A-Za-z0-9_.-]+',name) for name in contracts['ssh_files']),'SSH_FILENAME_REQUIRES_ESCAPING')
        # All actually imported project Python/JS is refreshed, without activating
        # any archived trading, website or retired WeCom service.
        current={}
        for p in PROJECT.rglob('*'):
            if p.is_file() and not p.is_symlink() and p.suffix in ('.py','.mjs','.js') and not any(x in p.parts for x in ('venv','node_modules','.git','__pycache__')):
                current[str(p.relative_to(PROJECT))]=sha(p)
        contracts['source_hashes']=current
        cert=PROJECT/'runtime/v8-domestic-operations/model-rpc/tls/model_rpc.crt'
        contracts['pin']=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
        roots=[NODE,STATE,WORKSPACE]+sorted(ssh_files)+RUNTIME
        total=sum(p.lstat().st_size for root in roots for p in ([root]+list(root.rglob('*')) if root.is_dir() and not root.is_symlink() else [root]) if p.is_file() and not p.is_symlink())
        pre=journal.perform('target_preflight',lambda:remote('preflight',{'required_bytes':total+700000000}));protected=pre['protected'];contracts['memory_budget_bytes']=pre['memory_budget_bytes']
        save(JOB/'contract-private.json',contracts)
        # Validate static links and capacity before quiescing source services.
        gaps=[]
        for root in roots:
            for p in ([root]+list(root.rglob('*')) if root.is_dir() and not root.is_symlink() else [root]):
                if p.is_symlink() and not link_allowed(p,os.readlink(p),roots):gaps.append({'path':str(p),'target':os.readlink(p),'reason':'UNCAPTURED_EXTERNAL_LINK'})
                elif not p.is_symlink() and not (p.is_dir() or p.is_file() or stat.S_ISSOCK(p.lstat().st_mode)):gaps.append({'path':str(p),'reason':'SPECIAL_FILE'})
        if gaps:
            save(JOB/'source-dependency-gaps.json',{'gaps':gaps})
            print('DEPENDENCY_GAP_COUNT='+str(len(gaps)),flush=True)
            raise RuntimeError('DEPENDENCY_CLOSURE_GAPS_BEFORE_SOURCE_PAUSE')
        static=JOB/'node-runtime.tar.gz';static_manifest={}
        print('PHASE=REUSE_NODE_OPENCLAW_PROGRAM_BEFORE_SOURCE_PAUSE',flush=True)
        import io
        with tarfile.open(static,'w:gz') as t:
            archive_tree(t,NODE,static_manifest,[NODE])
            for p in sorted(ssh_files):archive_tree(t,p,static_manifest,roots)
            body=json.dumps(static_manifest).encode();info=tarfile.TarInfo('manifest.json');info.size=len(body);info.mode=0o600;t.addfile(info,io.BytesIO(body))
        with static.open('rb') as f:os.fsync(f.fileno())
        static_binding={'segment':'static','sha256':sha(static),'bytes':static.stat().st_size}
        journal.perform('static_receive',lambda:remote('receive',static_binding,static,1800),static_binding)
        journal.perform('node_abi_check',lambda:remote('nodecheck'),static_binding)
        journal.perform('korea_ssh_authentication',lambda:remote('sshcheck',{'commands':[contracts[x]['argv'] for x in ('tunnel','gateway_tunnel','bridge_tunnel')]},timeout=60),static_binding)
        for p in ssh_files:require(sha(p)==static_manifest[str(p).lstrip('/')]['sha256'],'SSH_IDENTITY_CHANGED_DURING_CAPTURE')
        require(sha(NODE/'lib/node_modules/openclaw/package.json')=='226a35245ba5ba8b36ac707e68439eef62a9abb07a3234a154008d959976be7e','OPENCLAW_CHANGED_DURING_CAPTURE')
        def fence():
            for role in ('gateway','rpc','shim','tunnel','korea_source_tunnel','bridge_tunnel'):
                cfg=contracts[role];require(show(cfg['unit'],role=='gateway')['MainPID']==str(cfg['pid']),'SOURCE_PROCESS_CHANGED_BEFORE_PAUSE')
            for unit in TUNNELS+SYSTEM_SOURCE:run(['/usr/bin/systemctl','stop',unit],120)
            run(userctl('stop','openclaw-gateway.service'),120)
            for unit in TUNNELS+SYSTEM_SOURCE:require(show(unit)['MainPID']=='0','SOURCE_STOP_NOT_PROVEN')
            require(show('openclaw-gateway.service',True)['MainPID']=='0','GATEWAY_STOP_NOT_PROVEN')
            stopped_units=TUNNELS+SYSTEM_SOURCE+['openclaw-gateway.service']
            for proc in Path('/proc').iterdir():
                if not proc.name.isdigit():continue
                try:group=(proc/'cgroup').read_text()
                except (FileNotFoundError,ProcessLookupError):continue
                require(not any('/'+u in group for u in stopped_units),'SOURCE_CHILD_PROCESS_REMAINS')
            for unit in TUNNELS+SYSTEM_SOURCE:run(['/usr/bin/systemctl','mask','--runtime',unit])
            run(userctl('mask','--runtime','openclaw-gateway.service'))
            return {'source_stopped':True,'automatic_replay':False}
        print('PHASE=SOURCE_SERVICE_HANDOFF_PAUSE',flush=True);journal.perform('source_fence',fence)
        package=JOB/'runtime.tar.gz';manifest={}
        print('PHASE=CAPTURE_EXACT_RUNTIME_AND_PRIVATE_IDENTITY',flush=True)
        with tarfile.open(package,'w:gz') as t:
            for root in roots:
                if root!=NODE and root not in ssh_files:archive_tree(t,root,manifest,roots)
            import io
            for name,body in [('contract.json',json.dumps(contracts).encode()),('manifest.json',json.dumps(manifest).encode())]:
                info=tarfile.TarInfo(name);info.size=len(body);info.mode=0o600;t.addfile(info,io.BytesIO(body))
            for name,h in current.items():
                p=PROJECT/name;require(sha(p)==h,'CODE_DRIFT_AFTER_FENCE');t.add(p,arcname='source/'+name,recursive=False)
        with package.open('rb') as f:os.fsync(f.fileno())
        binding={'segment':'state','sha256':sha(package),'bytes':package.stat().st_size};save(JOB/'package.json',binding)
        journal.perform('target_receive',lambda:remote('receive',binding,package,1800),binding)
        journal.perform('target_install',lambda:remote('install',timeout=300),binding)
        journal.perform('target_start',lambda:remote('start',{'pin':contracts['pin']},timeout=300),binding)
        journal.perform('real_model_canary',lambda:remote('canary',timeout=150),binding)
        # Source reverse forwarding has been stopped and proven; preserve port19444.
        journal.perform('korea_local_route',lambda:remote('local',{'pin':contracts['pin']}),binding)
        journal.perform('domestic_reverse_route',lambda:remote('tunnel'),binding)
        probe=r'''import os,sys,ssl,socket,http.client,json,hashlib
if os.uname().nodename.split('.')[0]!='iZvt5t8tlrm8oiZ':raise SystemExit('HOST')
c=http.client.HTTPSConnection('127.0.0.1',19444,context=ssl._create_unverified_context(),timeout=15)
c.request('GET','/healthz');pin=hashlib.sha256(c.sock.getpeercert(binary_form=True)).hexdigest();r=c.getresponse();body=json.loads(r.read(100000));assert pin==sys.argv[1] and r.status==200 and body.get('status')=='PASS';print('DOMESTIC_TO_KOREA_TLS_HEALTH=PASS')
'''
        def domestic_verify():
            ssh=transport.SSH[:-1]+['binance-ops',shlex.join(['/usr/bin/python3','-I','-B','-S','-c',probe,contracts['pin']])]
            deadline=time.monotonic()+60
            while True:
                p=subprocess.run(ssh,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25)
                if p.returncode==0 and p.stdout.strip()==b'DOMESTIC_TO_KOREA_TLS_HEALTH=PASS':return {'status':'PASS'}
                require(time.monotonic()<deadline,'DOMESTIC_VERIFICATION');time.sleep(2)
        journal.perform('domestic_verify',domestic_verify,binding)
        final=remote('status');require(final['protected']==protected,'PROTECTED_SERVICE_STATE_CHANGED')
        journal.perform('persist_target',lambda:remote('enable'),binding)
        def disable_source():
            for unit in TUNNELS+SYSTEM_SOURCE:run(['/usr/bin/systemctl','disable',unit])
            run(userctl('disable','openclaw-gateway.service'));return {'disabled':True,'runtime_masks_retained':True}
        journal.perform('persist_source_fence',disable_source,binding)
        save(JOB/'receipt.json',{'status':'PASS_MODEL_SERVICE_HANDOFF','target':TARGET,'source_services_stopped':True,'domestic_tls_health':'PASS','real_model':'PASS','protected_services_unchanged':True,'tokyo_shutdown_authorized':False})
        print('STATUS=PASS_MODEL_SERVICE_HANDOFF\nTOKYO_MACHINE_RETIREMENT=SEPARATE_REMAINING_DUTY_CHECK\nRECEIPT='+str(JOB/'receipt.json'),flush=True)
    except BaseException:
        # Known pre-start failure can restore untouched source identities, only
        # after the target has positively proved every owned service stopped.
        # Once a Gateway start was attempted its OAuth/session state can change;
        # automatic source restoration would discard that state and is forbidden.
        if (JOB/'source_fence.intent.json').exists() and not (JOB/'target_start.intent.json').exists():
            try:
                journal.perform('rollback_target_stop',lambda:remote('stop'))
                def restore_before_start():
                    for unit in TUNNELS+SYSTEM_SOURCE:run(['/usr/bin/systemctl','unmask','--runtime',unit])
                    run(userctl('unmask','--runtime','openclaw-gateway.service'))
                    run(userctl('start','openclaw-gateway.service'),120)
                    for unit in list(reversed(SYSTEM_SOURCE))+TUNNELS:run(['/usr/bin/systemctl','start',unit],120)
                    for unit in TUNNELS+SYSTEM_SOURCE:require(show(unit)['ActiveState']=='active' and int(show(unit)['MainPID'])>0,'SOURCE_RESTORE_NOT_PROVEN')
                    require(show('openclaw-gateway.service',True)['ActiveState']=='active','SOURCE_GATEWAY_RESTORE_NOT_PROVEN')
                    return {'source_restored':True,'target_stopped':True,'reason':'NO_TARGET_START_WAS_ATTEMPTED'}
                journal.perform('rollback_source_before_start',restore_before_start)
                print('KNOWN_PRESTART_FAILURE_SOURCE_RESTORED=YES',flush=True)
            except BaseException:
                print('ROLLBACK_OUTCOME=HOLD_QUERY_ONLY',flush=True)
        # Preserve both journals. Never resurrect Tokyo while Korea may still run.
        print('STATUS=HOLD\nRECONCILIATION_REQUIRED=YES\nCHECKPOINT='+str(JOB),flush=True)
        raise

if __name__=='__main__':
    try:main()
    except BaseException as exc:
        reason=str(exc)
        print('ERROR_TYPE='+type(exc).__name__,flush=True)
        if re.fullmatch('[A-Z][A-Z0-9_]{1,100}',reason):print('REASON='+reason,flush=True)
        sys.exit(2)
