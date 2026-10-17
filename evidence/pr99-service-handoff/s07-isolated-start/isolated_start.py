"""Temporary S07 startup against copies inside new mount/network/PID namespaces.
Applications run as uid/gid65534 inside a copied chroot; no host runtime mounts.
No production service/unit/proxy change. All generated logs/materials stay private.
"""
import base64
import ctypes
import hashlib
import http.client
import json
import os
from pathlib import Path,PurePosixPath
import re
import resource
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time

KOREA='iZmj7a5kwr75qc1tul4kf9Z'
DOMESTIC='iZvt5t8tlrm8oiZ'
LOCAL=Path('/root/pr99-s07-isolated-start-launch-v2')
ATTEMPT=Path('/var/lib/xuanjun-pr99-s07-isolated-start-v2')
MATERIAL=Path('/var/lib/xuanjun-pr99-s07-private-materials-v1')
TRANSFER_PATH=Path('/root/pr99-s07-domestic-data-launch.FbAIVIap/transfer.py')
TRANSFER_SHA='90b49446307de25820b8190988582a53f05cc093ea97655d567cdf96a275df79'
ORIGINAL_SHA='745c67d34cf4b0d546aee28c74c11b1586a315a03d970cbebc37508ebc61f8fd'
SOURCE_SHA='137a2acea1924b4c62e43abfe6f8689c64450db868c7a216d759a16779c939b4'
TAR_SHA='dee6e24933f6a9b14c12ea0b838099093c40e53dda447360080d382793bc8c8c'
WIRE_SHA='7b0c1dbde63482c10d02ff51081fd1cdee0d3f1c17b1fbd75ffe3b111e40ab4f'
ROLES={
 'portal':('secure-secrets-portal.service','scripts/secure_secrets_portal_server.py',18080),
 'contact':('xuanjun-wecom-customer-contact.service','ai_service/wecom_customer_contact_service.py',18781),
 'customer_service':('xuanjun-wecom-customer-service.service','ai_service/wecom_customer_service.py',18780)}

def need(v,code):
    if not v:raise RuntimeError(code)

def sha(b):return hashlib.sha256(b).hexdigest()

def load(raw,digest):
    need(sha(raw)==digest,'HELPER_HASH_CHANGED')
    ns={'__name__':'frozen_functions','__file__':'frozen_helper.py'}
    exec(compile(raw,'frozen_helper.py','exec'),ns)
    return ns

def launch_command(raw,entry,port):
    # Accept only the observed Python entry and host/port options, never a shell.
    a=shlex.split(raw)
    need(a and re.fullmatch(r'/(?:usr/bin/python3(?:\.11)?|opt/trading-system/venv/bin/python(?:3(?:\.11)?)?)',a[0]),'UNIT_PYTHON_EXECUTABLE')
    tail=a[1:]
    while tail and tail[0] in ('-u','-B'):tail=tail[1:]
    module=entry[:-3].replace('/','.')
    if tail[:2]==['-m',module]:
        invocation=['-m',module];tail=tail[2:]
    else:
        need(tail and tail[0] in (entry,'/opt/trading-system/'+entry),'UNIT_ENTRY_CHANGED')
        invocation=['/opt/trading-system/'+entry];tail=tail[1:]
    # Owner metadata + pinned portal AST confirm the literal serve subcommand.
    if entry=='scripts/secure_secrets_portal_server.py' and tail[:1]==['serve']:
        invocation.append('serve');tail=tail[1:]
    normalized=[]
    while tail:
        token=tail.pop(0)
        if '=' in token:key,value=token.split('=',1)
        else:
            key=token;need(bool(tail),'UNIT_OPTION_VALUE');value=tail.pop(0)
        need(key in ('--host','--port'),'UNSUPPORTED_START_OPTION')
        if key=='--host':
            need(value in ('127.0.0.1','0.0.0.0','localhost'),'UNSUPPORTED_LISTEN_HOST')
            value='127.0.0.1'
        else:need(value==str(port),'UNIT_PORT_CHANGED')
        need(key not in normalized,'DUPLICATE_START_OPTION')
        normalized.extend([key,value])
    return ['/venv/bin/python','-B','-u']+invocation+normalized

def put(path,b,mode=0o600):
    path.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
    with path.open('xb') as f:f.write(b)
    path.chmod(mode)

def public_directory(path):
    # mkdir's requested mode is masked by the coordinator's private umask.
    path.mkdir(mode=0o755,exist_ok=True)
    need(not path.is_symlink() and path.is_dir(),'ISOLATION_DIRECTORY_TYPE')
    path.chmod(0o755)

def require_preserved_failure(old):
    previous=Path('/var/lib/xuanjun-pr99-s07-isolated-start-v1')
    need(previous.is_dir() and not previous.is_symlink(),'PREVIOUS_ATTEMPT_MISSING')
    failure=json.loads(old['stable'](previous/'failure.json',10000))
    need(failure=={'status':'HOLD_PRESERVE_NO_RETRY'},'PREVIOUS_FAILURE_CHANGED')
    need(not os.path.lexists(previous/'receipt.json'),'PREVIOUS_RECEIPT_REQUIRES_REVIEW')
    before=json.loads(old['stable'](previous/'protected.before.json',4*1024*1024))
    need(before==old['protected_snapshot'](),'PREVIOUS_PROTECTED_STATE_CHANGED')
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name)==os.getpid():continue
        try:
            cmd=(p/'cmdline').read_bytes()
            process_root=os.readlink(p/'root')
        except FileNotFoundError:continue
        need(str(previous) not in process_root and str(previous).encode() not in cmd,
             'PREVIOUS_ISOLATED_PROCESS_PRESENT')

def copy_project(root,sources,data):
    project=root/'opt/trading-system'
    project.mkdir(parents=True,mode=0o700)
    for n,b in sources.items():
        p=PurePosixPath(n)
        need(not p.is_absolute() and '..' not in p.parts and str(p)==n and '\\' not in n,'SOURCE_PATH')
        put(project/n,b,0o400)
    for name,b in data.items():
        if name.startswith('project/'):target=project/name[len('project/'):]
        elif name=='referral/0.json':
            target=root/'home/admin/.openclaw/workspace/xuanjun-agent-coordination/CUSTOMER_REFERRAL_CONFIG.json'
        elif name=='referral/1.json':
            target=root/'home/openclaw_ops/v8-domestic-operations/config/customer-referral/CUSTOMER_REFERRAL_CONFIG.json'
        else:raise RuntimeError('MATERIAL_PATH')
        if target.exists():need(target.read_bytes()==b,'SOURCE_DATA_COLLISION')
        else:put(target,b)
    for base in (root/'opt',root/'home'):
        if not base.exists():continue
        for current,dirs,files in os.walk(base,followlinks=False):
            os.chown(current,65534,65534);os.chmod(current,0o700)
            for name in files:os.chown(Path(current)/name,65534,65534)
    # The fixed /opt and /home mount-root paths need traversing after dropping uid.
    for p in (root/'opt',root/'home'):
        if p.exists():p.chmod(0o755)
    for n,b in sources.items():need(sha((project/n).read_bytes())==sha(b),'COPIED_SOURCE_CHANGED')
    return project

def child(root,commands):
    need(os.geteuid()==0 and os.uname().nodename==DOMESTIC,'NAMESPACE_HOST')
    subprocess.run(['/usr/bin/mount','--make-rprivate','/'],check=True,timeout=10)
    ip=next((p for p in ('/usr/sbin/ip','/sbin/ip','/usr/bin/ip') if Path(p).is_file()),None);need(bool(ip),'IP_TOOL_MISSING')
    links=json.loads(subprocess.check_output([ip,'-j','link','show'],timeout=10))
    need([x['ifname'] for x in links]==['lo'],'NETWORK_NAMESPACE_HAS_EXTERNAL_INTERFACE')
    subprocess.run([ip,'link','set','lo','up'],check=True,timeout=10)
    for name in ('usr','lib','lib64'):
        origin=Path('/'+name)
        if not origin.exists():continue
        target=root/name;target.mkdir(mode=0o755,exist_ok=True)
        subprocess.run(['/usr/bin/mount','--bind',str(origin),str(target)],check=True,timeout=10)
        subprocess.run(['/usr/bin/mount','-o','remount,bind,ro,nosuid,nodev',str(target)],check=True,timeout=10)
    public_directory(root/'dev')
    for name in ('null','urandom'):
        target=root/'dev'/name;target.touch(mode=0o600)
        subprocess.run(['/usr/bin/mount','--bind','/dev/'+name,str(target)],check=True,timeout=10)
    libc=ctypes.CDLL(None,use_errno=True)
    def confined():
        os.chroot(root);os.chdir('/opt/trading-system')
        need(libc.prctl(38,1,0,0,0)==0,'NO_NEW_PRIVILEGES_FAILED')
        os.setgroups([]);os.setgid(65534);os.setuid(65534)
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        resource.setrlimit(resource.RLIMIT_NOFILE,(256,256))
        resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024*1024,128*1024*1024))
        resource.setrlimit(resource.RLIMIT_CPU,(30,30))
        resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    procs={};logs=[];observed={}
    env={'PATH':'/venv/bin:/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8',
         'PYTHONPATH':'/opt/trading-system','PYTHONDONTWRITEBYTECODE':'1',
         'WECOM_CONTACT_HOST':'127.0.0.1','WECOM_CONTACT_PORT':'18781',
         'WECOM_KF_HOST':'127.0.0.1','WECOM_KF_PORT':'18780'}
    try:
        for role,command in commands.items():
            f=(ATTEMPT/(role+'.private.log')).open('xb');logs.append(f)
            procs[role]=subprocess.Popen(command,preexec_fn=confined,env=env,
                stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True)
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            for role,proc in procs.items():
                alive=proc.poll() is None
                s=socket.socket();s.settimeout(0.2)
                try:listening=alive and s.connect_ex(('127.0.0.1',ROLES[role][2]))==0
                finally:s.close()
                observed[role]={'process_alive':alive,'returncode':proc.poll(),'loopback_listener':listening,
                    'health_http_status':None}
            if all(x['loopback_listener'] for x in observed.values()) or all(p.poll() is not None for p in procs.values()):break
            time.sleep(0.5)
        for role,row in observed.items():
            if row['loopback_listener']:
                c=http.client.HTTPConnection('127.0.0.1',ROLES[role][2],timeout=3)
                try:
                    c.request('GET','/healthz');r=c.getresponse()
                    row['health_http_status']=r.status;r.read(65536)
                except (OSError,http.client.HTTPException):row['health_http_status']='UNKNOWN'
                finally:c.close()
    finally:
        for p in procs.values():
            if p.poll() is None:
                try:os.killpg(p.pid,signal.SIGTERM)
                except ProcessLookupError:pass
        for p in procs.values():
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                p.wait(timeout=5)
        for f in logs:f.close()
    result={'status':'ISOLATED_THREE_LISTENERS_PASS_RUNTIME_ACCEPTANCE_PENDING'
        if len(observed)==3 and all(x['loopback_listener'] for x in observed.values()) else 'ISOLATED_START_HOLD',
        'roles':observed,'network_namespace_external_interfaces':0,
        'app_uid_gid':'65534:65534','application_root':'COPIED_CHROOT','application_processes_stopped':True,
        'temporary_app_process_starts':len(procs),'production_service_actions':0,
        'production_cutover':False,'final_cutover_snapshot':False}
    print(json.dumps(result,sort_keys=True),flush=True)

def run_domestic(h):
    need(os.geteuid()==0 and os.uname().nodename==DOMESTIC,'DOMESTIC_ROOT_REQUIRED')
    os.umask(0o077)
    old=load(base64.b64decode(h['original'],validate=True),ORIGINAL_SHA)
    transfer=load(base64.b64decode(h['transfer'],validate=True),TRANSFER_SHA)
    source=load(base64.b64decode(h['source_helper'],validate=True),SOURCE_SHA)
    require_preserved_failure(old)
    need(not os.path.lexists(ATTEMPT),'ISOLATED_ATTEMPT_EXISTS_NO_RETRY')
    r=json.loads(old['stable'](MATERIAL/'receipt.json',100000))
    need(r['status']=='DOMESTIC_S07_PRIVATE_MATERIALS_STAGED_PASS' and r['tar_sha256']==TAR_SHA and r['wire_sha256']==WIRE_SHA,'DOMESTIC_MATERIAL_RECEIPT_CHANGED')
    wire=old['stable'](MATERIAL/'received.tar.gz',transfer['MAX_RAW'])
    need(sha(wire)==WIRE_SHA,'DOMESTIC_WIRE_CHANGED')
    raw=transfer['decompress_checked'](wire,{'wire_bytes':len(wire),'wire_sha256':WIRE_SHA,
        'tar_bytes':h['tar_bytes'],'tar_sha256':TAR_SHA})
    manifest,data=transfer['checked_members'](raw,source)
    for name,b in data.items():need(sha(old['stable'](MATERIAL/'received'/name,len(b)))==sha(b),'STAGED_MATERIAL_CHANGED')
    sources={}
    installed=json.loads(old['stable'](old['BASE']/'source-manifest.json',2*1024*1024))
    need(installed==h['sources'] and len(installed)==79,'INSTALLED_SOURCE_MANIFEST_CHANGED')
    for n,row in installed.items():
        p=PurePosixPath(n);need(not p.is_absolute() and '..' not in p.parts and str(p)==n,'SOURCE_PATH')
        b=old['stable'](old['BASE']/'app'/n,row['bytes'])
        need(sha(b)==row['sha256'],'INSTALLED_SOURCE_CHANGED');sources[n]=b
    need(set(h['commands'])==set(ROLES),'ROLE_SET')
    for role,command in h['commands'].items():
        # Revalidate the final fixed launcher; no arbitrary command/port can enter.
        fake='/usr/bin/python3 '+shlex.join(command[3:])
        need(launch_command(fake,ROLES[role][1],ROLES[role][2])==command,'LAUNCH_COMMAND_BINDING')
    before=old['protected_snapshot']()
    ATTEMPT.mkdir(mode=0o700)
    try:
        put(ATTEMPT/'protected.before.json',old['encoded'](before),0o400)
        unshare='/usr/bin/unshare';need(Path(unshare).is_file() and Path('/usr/bin/mount').is_file(),'NAMESPACE_TOOLS_MISSING')
        with (ATTEMPT/'namespace-preflight.private.log').open('xb') as f:
            subprocess.run([unshare,'--mount','--net','--pid','--fork','/usr/bin/true'],
                stdout=f,stderr=f,check=True,timeout=15)
        root=ATTEMPT/'rootfs';public_directory(root)
        copy_project(root,sources,data)
        shutil.copytree(old['BASE']/'venv',root/'venv',symlinks=True)
        for current,dirs,files in os.walk(root/'venv',followlinks=False):
            os.chmod(current,0o755)
            for name in files:
                p=Path(current)/name
                if not p.is_symlink():p.chmod(0o555 if p.stat().st_mode&0o111 else 0o444)
        for n in ('tmp','etc','usr','lib','lib64'):public_directory(root/n)
        (root/'tmp').chmod(0o1777)
        put(root/'etc/passwd',b'root:x:0:0:root:/root:/bin/false\nnobody:x:65534:65534:nobody:/nonexistent:/bin/false\n',0o444)
        put(root/'etc/group',b'root:x:0:\nnobody:x:65534:\n',0o444)
        put(root/'etc/hosts',b'127.0.0.1 localhost\n::1 localhost\n',0o444)
        bootstrap='import base64;n={"__name__":"namespace_functions"};exec(base64.b64decode('+repr(h['self'])+'),n);n["child"](n["Path"]('+repr(str(root))+'),'+repr(h['commands'])+')'
        with (ATTEMPT/'isolated-result.private.log').open('xb') as out,(ATTEMPT/'namespace.private.log').open('xb') as err:
            p=subprocess.Popen([unshare,'--mount','--net','--pid','--fork','/usr/bin/python3','-I','-B','-u','-c',bootstrap],
                stdout=out,stderr=err,stdin=subprocess.DEVNULL,start_new_session=True)
            try:p.wait(timeout=75)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=10)
                raise RuntimeError('ISOLATED_NAMESPACE_TIMEOUT_KILLED_PRESERVE')
            need(p.returncode==0,'NAMESPACE_EXECUTION_FAILED_PRESERVE_PRIVATE_LOG')
        raw=old['stable'](ATTEMPT/'isolated-result.private.log',100000).decode()
        rows=[json.loads(x) for x in raw.splitlines() if x.startswith('{')]
        need(rows,'ISOLATED_RESULT_MISSING')
        result=rows[-1]
        after=old['protected_snapshot']();put(ATTEMPT/'protected.after.json',old['encoded'](after),0o400)
        need(before==after,'DOMESTIC_PROTECTED_STATE_CHANGED')
        result['protected_state_unchanged']=True
        result['data_source']='PRELIMINARY_165_FILE_COPY_NOT_CANONICAL_WRITER'
        result['services_installed']=False;result['runtime_configuration_complete']=False
        put(ATTEMPT/'receipt.json',old['encoded'](result),0o400)
        print(json.dumps(result,sort_keys=True),flush=True)
    except BaseException:
        put(ATTEMPT/'failure.json',b'{"status":"HOLD_PRESERVE_NO_RETRY"}\n',0o400)
        raise

def main():
    need(os.geteuid()==0 and os.uname().nodename==KOREA,'KOREA_ROOT_REQUIRED')
    os.umask(0o077);need(not os.path.lexists(LOCAL),'LOCAL_ATTEMPT_EXISTS_NO_RETRY')
    tr=TRANSFER_PATH.read_bytes();transfer=load(tr,TRANSFER_SHA)
    material_path=Path('/root/pr99-s07-material-v2-launch.mgOIzkS1/stage.py')
    sr=material_path.read_bytes();source=load(sr,SOURCE_SHA)
    original=source['read_plain_file'](Path('/root/pr99-s07-install-launch.a5NZU99H/install.py'),100000)
    old=load(original,ORIGINAL_SHA)
    p=Path('/root/pr99-s07-runtime-inventory.8no57zD5/inspect.py')
    inventory=load(source['read_plain_file'](p,100000),'295b3e4df882793978042edcb3222c1068c493a9a33e47370ae8558d37095134')
    resolver=inventory['load_pinned'](inventory['RESOLVER'],inventory['RESOLVER_SHA'])
    projection,collector=resolver['bootstrap']()
    receipt=json.loads(collector['stable_file'](projection['ROOT']/'receipt.json',20000,private=True))
    need(receipt['archive_sha256']==projection['ARCHIVE_SHA'],'S06_ARCHIVE_BINDING')
    archive=collector['stable_file'](projection['ROOT']/'payload.tar.gz',4*1024*1024+65536,private=True)
    need(sha(archive)==projection['ARCHIVE_SHA'],'S06_ARCHIVE_CHANGED')
    units=collector['verify_archive'](archive,receipt)
    commands={}
    for role,(unit,entry,port) in ROLES.items():
        fields=resolver['unit_service'](units['units/'+unit])
        need(len(fields.get('ExecStart',[]))==1,'UNIT_START_COUNT')
        commands[role]=launch_command(fields['ExecStart'][0],entry,port)
    package=old['stable'](old['LOCAL_ATTEMPT']/'package.json',64*1024*1024)
    plan,files=old['unpack'](package,sha(package))
    selfraw=source['read_plain_file'](Path(__file__).absolute(),100000)
    h={'original':base64.b64encode(original).decode(),'transfer':base64.b64encode(tr).decode(),
       'source_helper':base64.b64encode(sr).decode(),'self':base64.b64encode(selfraw).decode(),
       'commands':commands,'sources':{n:{'bytes':len(b),'sha256':sha(b)} for n,b in files.items()},
       'tar_bytes':(Path('/root/pr99-s07-private-materials-v2/materials.tar')).stat().st_size}
    auth=Path(tempfile.mkdtemp(prefix='pr99-s07-isolated-auth-',dir='/root'))
    (auth/'known_hosts').write_text(transfer['HOST_KEY'])
    ssh=['/usr/bin/ssh','-T','-S',str(auth/'socket'),'-o','ControlMaster=auto','-o','ControlPersist=600',
       '-o','UserKnownHostsFile='+str(auth/'known_hosts'),'-o','GlobalKnownHostsFile=/dev/null',
       '-o','StrictHostKeyChecking=yes','-o','HostKeyAlgorithms=ecdsa-sha2-nistp256',
       '-o','UpdateHostKeys=no','-o','ForwardAgent=no','-o','ForwardX11=no','-o','ClearAllForwardings=yes',
       '-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2']
    remote='root@47.101.152.210'
    try:
        print('请输入国内root密码；仅复制品隔离启动，禁外网，结束即停止，不切入口。',flush=True)
        subprocess.run(ssh+['-n',remote,'test "$(hostname -s)" = '+DOMESTIC+' && test "$(id -u)" = 0'],check=True,timeout=180)
        LOCAL.mkdir(mode=0o700);wire=(json.dumps(h)+'\n').encode();need(len(wire)<250000,'BOOTSTRAP_LENGTH')
        put(LOCAL/'private-input.json',wire,0o400)
        bootstrap='import sys,json,base64;h=json.loads(sys.stdin.buffer.readline(250000));n={"__name__":"isolated_start_functions"};exec(base64.b64decode(h["self"]),n);n["run_domestic"](h)'
        command='/usr/bin/python3 -I -B -u -c '+shlex.quote(bootstrap)
        with (LOCAL/'private-input.json').open('rb') as inp,(LOCAL/'result.log').open('xb') as out,(LOCAL/'ssh-private.log').open('xb') as err:
            p=subprocess.Popen(ssh+['-o','BatchMode=yes',remote,command],stdin=inp,stdout=out,stderr=err)
            deadline=time.monotonic()+240
            while True:
                try:p.wait(timeout=15);break
                except subprocess.TimeoutExpired:
                    print('S07_ISOLATED_START_PROGRESS',flush=True)
                    if time.monotonic()>deadline:
                        p.terminate();p.wait(timeout=15);raise RuntimeError('REMOTE_RESULT_UNKNOWN_PRESERVE')
            need(p.returncode==0,'REMOTE_ISOLATED_START_FAILED_PRESERVE_PRIVATE_LOG')
        text=old['stable'](LOCAL/'result.log',100000).decode()
        rows=[json.loads(x) for x in text.splitlines() if x.startswith('{')]
        need(rows,'RESULT_RECEIPT_MISSING')
        put(LOCAL/'receipt.json',old['encoded'](rows[-1]),0o400)
        print(json.dumps(rows[-1],sort_keys=True),flush=True)
    finally:
        try:subprocess.run(ssh+['-O','exit',remote],capture_output=True,timeout=10)
        except (OSError,subprocess.TimeoutExpired):pass

if __name__=='__main__':
    try:main()
    except BaseException as e:
        reason=str(e) if isinstance(e,RuntimeError) and str(e).replace('_','').isalnum() and len(str(e))<120 else type(e).__name__
        print('S07_ISOLATED_START_HOLD='+reason+' PRESERVE_NO_RETRY',flush=True)
        raise SystemExit(2)
