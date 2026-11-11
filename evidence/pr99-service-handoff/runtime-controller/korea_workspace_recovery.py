"""Recover the observed legacy workspace start failure; never replay migration."""
import os,sys,json,hashlib,subprocess,shlex,time,fcntl,runpy,re
from pathlib import Path
BASE=Path('/root/pr99-korea-total-19d605cfd153')
JOB=Path('/root/pr99-korea-model-handoff-v1')
RECOVERY=JOB/'workspace-recovery-v1'
EXPECTED='9079fece47bfc5fb397b1d8f183a5392296f60dfb7e1d0e999dd11a1f841af68'

TARGET=r'''
import os,sys,json,hashlib,subprocess,time,fcntl,socket,ssl,http.client,tarfile,shutil,stat
from pathlib import Path
ROOT=Path('/opt/xuanjun-migration-s07/releases/korea-model-handoff-v1')
WORK=ROOT/'workspace-recovery-v1'
GATEWAY='pr99-korea-openclaw.service'
DOCTOR='pr99-korea-workspace-doctor-v1.service'
def need(ok,why):
 if not ok:raise RuntimeError(why)
def save(p,obj):
 with p.open('x') as f:json.dump(obj,f,sort_keys=True);f.flush();os.fsync(f.fileno())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def command(args,timeout=30):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 if p.returncode:
  log=WORK/('command-error-'+str(time.time_ns())+'.log')
  with log.open('xb') as f:f.write(p.stdout+b'\n'+p.stderr);f.flush();os.fsync(f.fileno())
  raise RuntimeError('TARGET_COMMAND_FAILED_PRIVATE_LOG')
 return p.stdout
def state(unit):
 return dict(x.split('=',1) for x in command(['/usr/bin/systemctl','show',unit,'--property=LoadState,ActiveState,MainPID,Result,ExecMainStatus']).decode().splitlines() if '=' in x)
def phase(name,fn):
 need(not (WORK/(name+'.intent.json')).exists(),'EXISTING_PHASE_QUERY_ONLY')
 save(WORK/(name+'.intent.json'),{'operation':name,'time':int(time.time())})
 result=fn();save(WORK/(name+'.result.json'),{'status':'PASS','evidence':result});print('RECOVERY_PHASE='+name+'_PASS',file=sys.stderr,flush=True);return result
def no_children(unit):
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:need('/'+unit not in (p/'cgroup').read_text(),'SERVICE_CHILD_STILL_RUNNING')
  except (FileNotFoundError,ProcessLookupError):pass
need(os.geteuid()==0 and os.uname().nodename.split('.')[0]=='iZmj7a5kwr75qc1tul4kf9Z','TARGET_IDENTITY')
os.umask(0o077)
lock=os.open('/root/pr99-korea-project-install.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
need(not any(p.is_symlink() for p in [ROOT]+list(ROOT.parents)),'ROOT_SYMLINK')
if WORK.exists():
 if (WORK/'receipt.json').is_file():print((WORK/'receipt.json').read_text(),flush=True);sys.exit(0)
 raise RuntimeError('TARGET_RECOVERY_EXISTS_QUERY_ONLY')
for unit in ('pr99-korea-model-rpc.service','pr99-korea-openai-shim.service','pr99-korea-local-model-forward.service','pr99-korea-domestic-model-tunnel.service'):
 s=state(unit);need(s['ActiveState']=='inactive' and s['MainPID']=='0','UNEXPECTED_PARTIAL_START')
for unit in ('pr99-korea-gateway-tunnel.service','pr99-korea-domestic-bridge-tunnel.service'):
 s=state(unit);need(s['ActiveState']=='active' and int(s['MainPID'])>0,'DEPENDENCY_TUNNEL_NOT_ACTIVE')
WORK.mkdir(mode=0o700)
config=json.loads((ROOT/'contract.json').read_text())
def stop_gateway():
 command(['/usr/bin/systemctl','stop',GATEWAY],120);s=state(GATEWAY);need(s['ActiveState']=='inactive' and s['MainPID']=='0','GATEWAY_STOP_NOT_PROVEN');no_children(GATEWAY);return {'stopped':True}
phase('stop_gateway',stop_gateway)
state_root=ROOT/'rootfs/home/admin/.openclaw'
workspace=ROOT/'rootfs/mnt/btrfs-workspace/ws-398ab6'
def backup():
 total=0
 for root in (state_root,workspace):
  need(root.is_dir() and not root.is_symlink(),'BACKUP_ROOT_TYPE')
  for current,dirs,files in os.walk(root,followlinks=False):
   for name in files:
    p=Path(current)/name
    if not p.is_symlink() and p.is_file():total+=p.stat().st_size
 need(shutil.disk_usage(ROOT).free>total+268435456,'BACKUP_DISK_SPACE')
 archive=WORK/'before-doctor.tar.gz'
 with tarfile.open(archive,'w:gz',dereference=False) as t:
  for root in (state_root,workspace):t.add(root,arcname=str(root.relative_to(ROOT)),recursive=True)
 with archive.open('rb') as f:os.fsync(f.fileno())
 return {'archive':str(archive),'sha256':sha(archive),'bytes':archive.stat().st_size}
phase('backup_private_state',backup)
# Clone the existing namespace and identity. Only private copied state/workspace
# is writable; no host OpenClaw installation or user unit is repaired.
launcher=r"""import os,json
from pathlib import Path
c=json.loads(Path('/srv/pr99-model-contract.json').read_text())['gateway']
os.environ.update(c['env'])
f=os.open('/srv/pr99-doctor.log',os.O_WRONLY|os.O_APPEND)
os.dup2(f,1);os.dup2(f,2);os.close(f)
a=c['argv'];entry='/opt/node-v24.16.0-linux-x64/lib/node_modules/openclaw/dist/index.js'
i=a.index(entry)
argv=a[:i+1]+['doctor','--fix']
os.execve(argv[0],argv,os.environ)
"""
def doctor_unit_text(text,script,log):
 lines=[];count=0
 for line in text.splitlines():
  if line=='[Install]':break
  if line.startswith('ExecStart='):
   need(line=='ExecStart=/bin/python3.11 -I -B -S /srv/pr99-model-launcher.py gateway','GATEWAY_EXEC_CHANGED')
   line='ExecStart=/bin/python3.11 -I -B -S /srv/pr99-doctor-launcher.py';count+=1
  elif line=='Type=simple':line='Type=oneshot'
  elif line.startswith('Restart='):line='Restart=no'
  lines.append(line)
 need(count==1,'DOCTOR_UNIT_ENTRY')
 lines+=['BindReadOnlyPaths='+str(script)+':/srv/pr99-doctor-launcher.py','BindPaths='+str(log)+':/srv/pr99-doctor.log','StandardInput=null','TimeoutStartSec=300']
 return '\n'.join(lines)+'\n'
def doctor():
 script=ROOT/'workspace-doctor-launcher-v1.py';log=ROOT/'workspace-doctor-v1.log'
 for p,body,mode in ((script,launcher.encode(),0o644),(log,b'',0o600)):
  need(not p.exists() and not p.is_symlink(),'DOCTOR_ARTIFACT_EXISTS')
  with p.open('xb') as f:f.write(body);os.fchmod(f.fileno(),mode);f.flush();os.fsync(f.fileno())
 os.chown(log,1000,1000)
 old=Path('/etc/systemd/system')/GATEWAY
 need(not old.is_symlink() and old.stat().st_uid==0,'GATEWAY_UNIT_IDENTITY')
 text=doctor_unit_text(old.read_text(),script,log)
 unit=Path('/etc/systemd/system')/DOCTOR
 need(state(DOCTOR)['LoadState']=='not-found' and not unit.exists() and not unit.is_symlink(),'DOCTOR_UNIT_EXISTS')
 with unit.open('x') as f:f.write(text);os.fchmod(f.fileno(),0o644);f.flush();os.fsync(f.fileno())
 save(WORK/'doctor-input.json',{'gateway_unit_sha256':sha(old),'doctor_unit_sha256':sha(unit),'launcher_sha256':sha(script),'command':'doctor --fix'})
 command(['/usr/bin/systemctl','daemon-reload'])
 command(['/usr/bin/systemctl','start',DOCTOR],330)
 s=state(DOCTOR);need(s['Result']=='success' and s['ExecMainStatus']=='0' and s['MainPID']=='0','DOCTOR_NOT_SUCCESSFUL')
 no_children(DOCTOR)
 return {'exit_code':0,'private_log':str(log),'log_sha256':sha(log)}
phase('doctor_fix_private_workspace',doctor)
def start_gateway():
 command(['/usr/bin/systemctl','start',GATEWAY],120)
 deadline=time.monotonic()+180
 while True:
  s=state(GATEWAY)
  if s['ActiveState']=='active' and int(s['MainPID'])>0:
   try:
    with socket.create_connection(('127.0.0.1',11505),timeout=2):pass
    return {'gateway_port':11505,'pid':int(s['MainPID'])}
   except OSError:pass
  need(time.monotonic()<deadline,'GATEWAY_PORT_NOT_READY_AFTER_DOCTOR');time.sleep(2)
phase('start_repaired_gateway',start_gateway)
for role in ('model-rpc','openai-shim'):
 unit='pr99-korea-'+role+'.service'
 def start(unit=unit):
  need(state(unit)['ActiveState']=='inactive','SERVICE_START_STATE_CHANGED')
  command(['/usr/bin/systemctl','start',unit],120);s=state(unit)
  need(s['ActiveState']=='active' and int(s['MainPID'])>0,'SERVICE_NOT_ACTIVE')
  return {'unit':unit,'pid':int(s['MainPID'])}
 phase('start_'+role.replace('-','_'),start)
def verify():
 deadline=time.monotonic()+90
 while True:
  try:
   c=http.client.HTTPSConnection('127.0.0.1',20443,context=ssl._create_unverified_context(),timeout=10)
   try:
    c.request('GET','/healthz');pin=hashlib.sha256(c.sock.getpeercert(binary_form=True)).hexdigest();r=c.getresponse();body=json.loads(r.read(100000));need(pin==config['pin'] and r.status==200 and body.get('status')=='PASS','RPC_HEALTH')
   finally:c.close()
   c=http.client.HTTPConnection('127.0.0.1',19445,timeout=10)
   try:
    c.request('GET',config['shim_health_path']);r=c.getresponse();body=json.loads(r.read(100000));need(r.status==200 and all(body.get(k)==v for k,v in config['shim_health_fields'].items()),'SHIM_HEALTH')
   finally:c.close()
   break
  except Exception:
   need(time.monotonic()<deadline,'HEALTH_NOT_READY_AFTER_WORKSPACE_REPAIR');time.sleep(2)
 return {'gateway':'PASS','rpc_tls':'PASS','shim':'PASS'}
health=phase('reconcile_target_start',verify)
receipt={'host':'iZmj7a5kwr75qc1tul4kf9Z','status':'PASS_WORKSPACE_REPAIR_AND_START','health':health,'checkpoint':str(WORK)}
save(WORK/'receipt.json',receipt);print(json.dumps(receipt,sort_keys=True),flush=True)
'''


def gateway_is_stopped(state,has_children,masked):
    return state.get('ActiveState') in ('inactive','failed') and state.get('MainPID')=='0' and not has_children and masked

def main():
    if os.geteuid()!=0 or os.uname().nodename.split('.')[0]!='iZ6wee8q9z4t03hvqumwfhZ':raise RuntimeError('SOURCE_IDENTITY')
    os.umask(0o077)
    p=BASE/'korea_model_handoff_r7.py'
    if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError('BASE_CONTROLLER_SHA')
    m=runpy.run_path(str(p),run_name='pr99_recovery_base')
    locks=[]
    for name in ('/root/pr99-controller.lock','/root/pr99-workspace-recovery.lock'):
        fd=os.open(name,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(fd)
    state=m['show']('pr99-tokyo-korea-total-r7.service')
    m['require'](state['ActiveState']=='failed' and state['MainPID']=='0','ORIGINAL_CONTROLLER_NOT_STOPPED')
    if RECOVERY.exists():
        print('EXISTING_RECOVERY=QUERY_ONLY_NO_REPLAY',flush=True)
        if (RECOVERY/'receipt.json').is_file():print((RECOVERY/'receipt.json').read_text(),flush=True)
        else:print(json.dumps({k:v['status'] for k,v in m['Checkpoint'](RECOVERY).summary().items()},sort_keys=True),flush=True)
        return
    for name in ('target_preflight','static_receive','node_abi_check','korea_ssh_authentication','source_fence','target_receive','target_install'):
        evidence=json.loads((JOB/(name+'.result.json')).read_text());m['require'](evidence.get('status')=='PASS','REQUIRED_ORIGINAL_STAGE')
    m['require']((JOB/'target_start.unknown.json').is_file() and not (JOB/'target_start.result.json').exists(),'ORIGINAL_START_RECONCILIATION')
    m['require'](not any((JOB/(x+'.intent.json')).exists() for x in ('real_model_canary','korea_local_route','domestic_reverse_route','persist_target')),'LATER_STAGE_ALREADY_ATTEMPTED')
    for unit in m['TUNNELS']+m['SYSTEM_SOURCE']:
        s=m['show'](unit);m['require'](s['ActiveState']=='inactive' and s['MainPID']=='0','SOURCE_FENCE_LOST')
    s=m['show']('openclaw-gateway.service',True)
    has_children=False
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            if 'openclaw-gateway.service' in (proc/'cgroup').read_text():has_children=True
        except (FileNotFoundError,ProcessLookupError):pass
    mask=Path('/run/user/1000/systemd/user/openclaw-gateway.service')
    m['require'](gateway_is_stopped(s,has_children,mask.is_symlink() and os.readlink(mask)=='/dev/null'),'SOURCE_GATEWAY_FENCE_LOST')
    RECOVERY.mkdir(mode=0o700);journal=m['Checkpoint'](RECOVERY)
    print('CHECKPOINT='+str(RECOVERY),flush=True)
    def repair():
        command=shlex.join(['/usr/bin/sudo','-n','/usr/bin/python3','-I','-B','-S','-c','import os,sys;os.execv("/bin/python3.11",["/bin/python3.11","-I","-B","-S","-c",sys.argv[1]])',TARGET])
        with (RECOVERY/'target.out').open('xb') as out,(RECOVERY/'target.err').open('xb') as err:
            p=subprocess.Popen(m['transport'].SSH+[command],stdout=out,stderr=err)
            deadline=time.monotonic()+900
            while True:
                try:code=p.wait(timeout=15);break
                except subprocess.TimeoutExpired:
                    print('WORKSPACE_REPAIR_OR_START_RUNNING',flush=True)
                    if time.monotonic()>deadline:p.kill();p.wait();raise RuntimeError('REMOTE_REPAIR_UNKNOWN_NO_REPLAY')
        m['require'](code==0,'REMOTE_REPAIR_FAILED_PRIVATE_LOG')
        result=json.loads((RECOVERY/'target.out').read_text());m['require'](result.get('status')=='PASS_WORKSPACE_REPAIR_AND_START','TARGET_REPAIR_RECEIPT');return result
    journal.perform('repair_workspace_and_reconcile_start',repair)
    config=json.loads((JOB/'contract-private.json').read_text());pin=config['pin']
    journal.perform('real_model_canary',lambda:m['remote']('canary',timeout=150))
    journal.perform('korea_local_route',lambda:m['remote']('local',{'pin':pin}))
    journal.perform('domestic_reverse_route',lambda:m['remote']('tunnel'))
    probe="""import os,sys,ssl,http.client,json,hashlib
assert os.uname().nodename.split('.')[0]=='iZvt5t8tlrm8oiZ'
c=http.client.HTTPSConnection('127.0.0.1',19444,context=ssl._create_unverified_context(),timeout=15)
c.request('GET','/healthz');pin=hashlib.sha256(c.sock.getpeercert(binary_form=True)).hexdigest();r=c.getresponse();body=json.loads(r.read(100000));assert pin==sys.argv[1] and r.status==200 and body.get('status')=='PASS';print('PASS')
"""
    def verify_domestic():
        cmd=m['transport'].SSH[:-1]+['binance-ops',shlex.join(['/usr/bin/python3','-I','-B','-S','-c',probe,pin])]
        deadline=time.monotonic()+60
        while True:
            r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25)
            if r.returncode==0 and r.stdout.strip()==b'PASS':return {'tls_health':'PASS'}
            m['require'](time.monotonic()<deadline,'DOMESTIC_TLS_NOT_VERIFIED');time.sleep(2)
    journal.perform('domestic_verify',verify_domestic)
    protected=json.loads((JOB/'target_preflight.result.json').read_text())['evidence']['protected']
    current=m['remote']('status');m['require'](current['protected']==protected,'PROTECTED_SERVICE_STATE_CHANGED')
    journal.perform('persist_target',lambda:m['remote']('enable'))
    def disable_source():
        for unit in m['TUNNELS']+m['SYSTEM_SOURCE']:m['run'](['/usr/bin/systemctl','disable',unit])
        m['run'](m['userctl']('disable','openclaw-gateway.service'));return {'source_disabled':True}
    journal.perform('persist_source_fence',disable_source)
    receipt={'status':'PASS_MODEL_SERVICE_HANDOFF','target':'iZmj7a5kwr75qc1tul4kf9Z','real_model':'PASS','domestic_tls_health':'PASS','protected_services_unchanged':True,'source_services_stopped':True,'tokyo_shutdown_authorized':False,'recovered_target_start':str(RECOVERY),'original_start_unknown_preserved':True}
    m['save'](RECOVERY/'receipt.json',receipt);m['save'](JOB/'receipt.json',receipt)
    print('STATUS=PASS_MODEL_SERVICE_HANDOFF\nRECEIPT='+str(JOB/'receipt.json'),flush=True)

if __name__=='__main__':
    try:main()
    except BaseException as exc:
        print('STATUS=HOLD\nERROR_TYPE='+type(exc).__name__+'\nCHECKPOINT='+str(RECOVERY),flush=True)
        if re.fullmatch('[A-Z][A-Z0-9_]{1,120}',str(exc)):print('REASON='+str(exc),flush=True)
        if (RECOVERY/'target.err').is_file():
            for line in (RECOVERY/'target.err').read_text(errors='replace').splitlines():
                if re.fullmatch(r'(?:RuntimeError|AssertionError): [A-Z][A-Z0-9_]{1,120}',line.strip()):print(line.strip(),flush=True)
        sys.exit(2)
