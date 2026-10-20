#!/bin/sh
# CANDIDATE ONLY: UK source snapshot, NOT approved/executed, NOT plugin installation.
set -eu
sudo -n /usr/bin/python3 -I -B -S - <<'PY'
import os,sys,json,stat,pwd,hashlib,fcntl,subprocess,resource,signal
from urllib.request import build_opener,ProxyHandler
HOST='iZd7oeikknn1z21sq6ji6zZ'
BASE='/var/lib/xuanjun-p2-isolated-test'
NAME='b5-source-snapshot-20261020'
SOURCE_COMMIT='7c12b368b3586ba0b2d1f91498d8f9f4ed2d95b5'
SOURCE_SHA='505fbcaca2edb0ce3d9cfc697008242dd2e270d71dd394beede82679b003bf85'
def check(ok,reason):
    if not ok:raise RuntimeError(reason)
def put(directory,name,raw):
    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
check(os.geteuid()==os.getuid()==0 and os.uname().nodename.split('.')[0]==HOST,'HOLD_HOST_ROOT')
check(sys.version_info[:3]==(3,6,8),'HOLD_HOST_PYTHON368')
check(pwd.getpwuid(1002).pw_name=='xuanjun_dev' and pwd.getpwuid(1002).pw_gid==1002,'HOLD_UID_GID')
os.umask(0o077)
# One fixed HTTPS SOURCE fetch, no package/runtime/network discovery.
url='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/'+SOURCE_COMMIT+'/scripts/p2_b5_snapshot.py'
with build_opener(ProxyHandler({})).open(url,timeout=30) as response:source=response.read(1048577)
check(len(source)<=1048576 and hashlib.sha256(source).hexdigest()==SOURCE_SHA,'HOLD_SOURCE_SHA')
compile(source,'<fixed-b5-snapshot>','exec')
base=os.open(BASE,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
s=os.fstat(base);check(s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700 and os.path.realpath(BASE)==BASE,'HOLD_EXISTING_BASE')
space=os.fstatvfs(base);check(space.f_bavail*space.f_frsize>=1024*1024*1024 and space.f_favail>=64,'HOLD_SNAPSHOT_SPACE_BOUND')
lock=os.open('.b5-source-snapshot.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=base)
s=os.fstat(lock);check(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,'HOLD_LOCK')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
# Existing operation directory => STOP. Never remove or overwrite prior/partial evidence.
os.mkdir(NAME,0o700,dir_fd=base)
root=os.open(NAME,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=base)
put(root,'source.py',source)
os.mkdir('uid1002',0o700,dir_fd=root)
output=os.open('uid1002',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root)
os.fchown(output,1002,1002)  # ONLY this newly created child; parent and existing files unchanged.
os.fsync(root);os.fsync(base)
def child_limits():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_CPU,(100,100))
    resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024))
    resource.setrlimit(resource.RLIMIT_FSIZE,(640*1024*1024,640*1024*1024))
    resource.setrlimit(resource.RLIMIT_NOFILE,(128,128))
    os.setgroups([]);os.setgid(1002);os.setuid(1002)
result={'scope':'ISOLATED_TEST_ONLY_SOURCE_SNAPSHOT','state':'HOLD','source_commit':SOURCE_COMMIT,'source_sha256':SOURCE_SHA,'uk_b5_installation':'NOT_EXECUTED','dependency_closure':'UNKNOWN','compiled_export':'UNKNOWN'}
stdout=b'';stderr=b'';child=None
try:
    child=subprocess.Popen(['/usr/bin/python3','-I','-B','-S','-'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,pass_fds=(output,),start_new_session=True,preexec_fn=child_limits,env={'PATH':'/usr/bin:/bin','LANG':'C','P2_B5_OUTPUT_FD':str(output)})
    try:stdout,stderr=child.communicate(source,timeout=150)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid,signal.SIGKILL);stdout,stderr=child.communicate();result['error']='HOLD_CHILD_TIMEOUT_RETAINED'
    result['child_exit_code']=child.returncode
    # A captured snapshot intentionally exits2/HOLD: it is not a closed executable runtime.
    check(len(stdout)<=16*1024*1024 and len(stderr)<=16*1024*1024,'HOLD_LOG_BOUND')
    try:
        fd=os.open('result.json',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=output)
        with os.fdopen(fd,'rb') as f:
            raw=f.read(16*1024*1024+1);check(len(raw)<=16*1024*1024,'HOLD_RESULT_BOUND')
        result['collector_result_sha256']=hashlib.sha256(raw).hexdigest()
        value=json.loads(raw.decode('utf8'));result['capture']=value.get('capture','UNKNOWN')
        result['archive_sha256']=value.get('archive_sha256');result['manifest_sha256']=value.get('manifest_sha256')
    except Exception as exc:result['result_read_error']=type(exc).__name__
except Exception as exc:
    result['error']=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
finally:
    if child is not None and child.poll() is None:
        os.killpg(child.pid,signal.SIGKILL);child.wait()
    result['stdout_sha256']=hashlib.sha256(stdout).hexdigest();result['stderr_sha256']=hashlib.sha256(stderr).hexdigest()
    put(root,'stdout.log',stdout);put(root,'stderr.log',stderr)
    report=json.dumps(result,sort_keys=True).encode();put(root,'host-result.json',report)
    os.fsync(root);os.close(output);os.close(root);os.close(base)
print(json.dumps({'host_result':result,'host_result_sha256':hashlib.sha256(report).hexdigest()},sort_keys=True))
sys.exit(2)
PY
