"""Bounded copied-release restart and cleanup acceptance; never production activation."""
import base64,ctypes,hashlib,http.client,json,os,re,resource,signal,socket,stat,subprocess,time
from pathlib import Path
HOST='iZvt5t8tlrm8oiZ'
R=Path('/opt/xuanjun-migration-s07/releases/domestic-r2');ROOT=R/'rootfs';A=R/'callback-restart-acceptance-v1'
ROLES={'portal':(18080,['/venv/bin/python','scripts/secure_secrets_portal_server.py','serve','--host','127.0.0.1','--port','18080']),'contact':(18781,['/venv/bin/python','-m','ai_service.wecom_customer_contact_service']),'customer_service':(18780,['/venv/bin/python','-m','ai_service.wecom_customer_service'])}
UNITS=('secure-secrets-portal.service','xuanjun-wecom-customer-contact.service','xuanjun-wecom-customer-service.service','provider-neutral-domestic-bridge.service','winctl.service','nginx.service')
def need(ok,code):
 if not ok:raise RuntimeError(code)
def snapshot():
 out={}
 for u in UNITS:
  r=subprocess.run(['/usr/bin/systemctl','show',u,'--property=LoadState,ActiveState,SubState,MainPID,FragmentPath','--no-pager'],capture_output=True,timeout=10);need(r.returncode==0,'UNIT_QUERY');out[u]=r.stdout.decode()
 for name in ('/var/www/wenwenwenyiyiyi.work/current','/opt/trading-system'):
  p=Path(name)
  if p.is_symlink():out[name]={'link':os.readlink(p)}
  elif p.exists():
   s=p.stat();out[name]={'dev':s.st_dev,'ino':s.st_ino,'mode':s.st_mode,'uid':s.st_uid,'gid':s.st_gid}
  else:out[name]=None
 return out
def status(port,path):
 c=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
 try:c.request('GET',path);r=c.getresponse();r.read(65536);return r.status
 except (OSError,http.client.HTTPException):return None
 finally:c.close()
def listening(port):
 s=socket.socket();s.settimeout(.2)
 try:return s.connect_ex(('127.0.0.1',port))==0
 finally:s.close()
def child():
 subprocess.run(['/usr/bin/mount','--make-rprivate','/'],check=True,timeout=10)
 ip=next((x for x in ('/usr/sbin/ip','/sbin/ip','/usr/bin/ip') if Path(x).is_file()),None);need(ip,'IP_MISSING')
 links=json.loads(subprocess.check_output([ip,'-j','link','show'],timeout=10));need([x['ifname'] for x in links]==['lo'],'EXTERNAL_INTERFACE');subprocess.run([ip,'link','set','lo','up'],check=True,timeout=10)
 for name in ('usr','lib','lib64'):
  if not Path('/'+name).exists():continue
  target=ROOT/name;target.mkdir(exist_ok=True,mode=0o755);target.chmod(0o755)
  subprocess.run(['/usr/bin/mount','--bind','/'+name,str(target)],check=True,timeout=10);subprocess.run(['/usr/bin/mount','-o','remount,bind,ro,nosuid,nodev',str(target)],check=True,timeout=10)
 (ROOT/'dev').mkdir(exist_ok=True,mode=0o755)
 for name in ('null','urandom'):
  p=ROOT/'dev'/name;p.touch(mode=0o600,exist_ok=True);subprocess.run(['/usr/bin/mount','--bind','/dev/'+name,str(p)],check=True,timeout=10)
 libc=ctypes.CDLL(None,use_errno=True)
 def confine():
  os.chroot(ROOT);os.chdir('/opt/trading-system');need(libc.prctl(38,1,0,0,0)==0,'NO_NEW_PRIVS');os.setgroups([]);os.setgid(65534);os.setuid(65534);resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(536870912,536870912));resource.setrlimit(resource.RLIMIT_CPU,(60,60));resource.setrlimit(resource.RLIMIT_NOFILE,(256,256));resource.setrlimit(resource.RLIMIT_FSIZE,(134217728,134217728))
 env={'PATH':'/venv/bin:/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8','PYTHONPATH':'/opt/trading-system','PYTHONDONTWRITEBYTECODE':'1','WECOM_CONTACT_HOST':'127.0.0.1','WECOM_CONTACT_PORT':'18781','WECOM_KF_HOST':'127.0.0.1','WECOM_KF_PORT':'18780'}
 rounds=[]
 for turn in (1,2):
  procs={};logs=[];rows={}
  try:
   for role,(port,cmd) in ROLES.items():
    f=(A/(role+'.'+str(turn)+'.private.log')).open('xb');logs.append(f);procs[role]=subprocess.Popen(cmd,preexec_fn=confine,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True)
   deadline=time.monotonic()+25
   while time.monotonic()<deadline:
    if all(listening(port) for port,_ in ROLES.values()) or all(p.poll() is not None for p in procs.values()):break
    time.sleep(.3)
   for role,(port,_) in ROLES.items():
    p=procs[role];rows[role]={'alive':p.poll() is None,'health':status(port,'/healthz') if p.poll() is None else None,'invalid_auth_status':None}
    if p.poll() is None and role!='portal':rows[role]['invalid_auth_status']=status(port,('/wecom/customer-contact/callback' if role=='contact' else '/wecom/customer-service/callback')+'?msg_signature=INVALID&timestamp=0&nonce=PR99&echostr=INVALID')
  finally:
   for p in procs.values():
    if p.poll() is None:
     try:os.killpg(p.pid,signal.SIGTERM)
     except ProcessLookupError:pass
   for p in procs.values():
    try:p.wait(timeout=8)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)
   for f in logs:f.close()
  gone=all(not listening(port) for port,_ in ROLES.values());need(gone,'LISTENER_REMAINS');rounds.append({'round':turn,'roles':rows,'all_processes_stopped':all(p.poll() is not None for p in procs.values()),'listeners_removed':gone})
  need(all(r['alive'] and r['health']==200 for r in rows.values()),'APPLICATION_START_FAILED')
  need(all(rows[role]['invalid_auth_status'] in (400,401,403) for role in ('contact','customer_service')),'CALLBACK_REJECTION_NOT_PROVEN')
 print(json.dumps({'rounds':rounds,'restart_health_pass':True,'application_processes_stopped':True,'callback_rejections_do_not_prove_signed_success_or_upstream_auth':True}),flush=True)
def main():
 need(os.geteuid()==0 and os.uname().nodename==HOST,'HOST_ROOT')
 manifest=json.loads((R/'runtime-candidate.private.json').read_bytes());need(manifest['status']=='R2_RUNTIME_CANDIDATE_COPIED_NOT_ACTIVE','RUNTIME_STAGE')
 for name,h in manifest['file_hashes'].items():
  p=ROOT/name;need(not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==h,'RUNTIME_HASH')
 before=snapshot()
 for u in UNITS[:3]:need('LoadState=not-found' in before[u],'PRODUCTION_UNIT_EXISTS')
 A.mkdir(mode=0o700)
 try:
  for base in (ROOT/'opt',ROOT/'home'):
   for current,dirs,files in os.walk(base,followlinks=False):
    os.chown(current,65534,65534);os.chmod(current,0o700)
    for n in files:
     p=Path(current)/n;need(not p.is_symlink(),'PROJECT_LINK');os.chown(p,65534,65534);p.chmod(0o444 if p.suffix=='.py' else 0o600)
  for current,dirs,files in os.walk(ROOT/'venv',followlinks=False):
   os.chmod(current,0o755)
   for n in files:
    p=Path(current)/n
    if not p.is_symlink():p.chmod(0o555 if p.stat().st_mode&0o111 else 0o444)
  ROOT.chmod(0o755)
  for n in ('opt','home','tmp','etc'):(ROOT/n).mkdir(exist_ok=True,mode=0o755);(ROOT/n).chmod(0o755)
  (ROOT/'tmp').chmod(0o1777)
  for n,b in {'passwd':b'root:x:0:0:root:/root:/bin/false\nnobody:x:65534:65534:nobody:/nonexistent:/bin/false\n','group':b'root:x:0:\nnobody:x:65534:\n','hosts':b'127.0.0.1 localhost\n::1 localhost\n'}.items():
   p=ROOT/'etc'/n
   with p.open('xb') as f:f.write(b)
   p.chmod(0o444)
  bootstrap='import base64;n={"__name__":"child_functions"};exec(base64.b64decode('+repr(SELF_BASE64)+'),n);n["child"]()'
  with (A/'namespace.private.log').open('xb') as err,(A/'result.private.log').open('xb') as out:
   p=subprocess.Popen(['/usr/bin/unshare','--mount','--net','--pid','--fork','/usr/bin/python3.11','-I','-B','-u','-c',bootstrap],stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
   try:p.wait(timeout=100)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=10);raise RuntimeError('TIMEOUT_PRESERVE_NO_RETRY')
  need(p.returncode==0,'NAMESPACE_FAILED_PRESERVE_PRIVATE_LOG');result=json.loads((A/'result.private.log').read_bytes());need(snapshot()==before,'PROTECTED_CHANGED')
  result.update(status='R2_CALLBACK_REJECTION_RESTART_CLEANUP_PASS_NOT_PRODUCTION',hostname=HOST,uid=0,attempt_nonce=ATTEMPT_NONCE,protected_state_unchanged=True,service_actions=0,services_installed=False,production_cutover=False,business_api_requests=0,final_cutover_snapshot=False)
  with (A/'receipt.json').open('x') as f:json.dump(result,f,sort_keys=True)
  print(json.dumps(result),flush=True)
 except Exception:
  with (A/'failure.json').open('x') as f:json.dump({'status':'HOLD_PRESERVE_NO_RETRY'},f)
  raise
if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'status':'HOLD_PRESERVE_NO_RETRY','exception':type(e).__name__,'code':str(e) if re.fullmatch(r'[A-Z0-9_]{1,100}',str(e)) else 'PRIVATE_DETAIL_WITHHELD'}),flush=True);raise SystemExit(2)
