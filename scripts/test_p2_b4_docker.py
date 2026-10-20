"""Hosted-only real finite original-consumer sandbox test; never UK execution."""
import json,os,subprocess,tempfile
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
base=Path(tempfile.mkdtemp(prefix='p2-b3-test-b4-',dir='/tmp'));os.chown(str(base),1002,1002);base.chmod(0o700)
image='python:3.11.2-slim'
common=['/bin/docker','run','--rm','--user=1002:1002','--network=none','--cap-drop=ALL',
 '--security-opt=no-new-privileges','--read-only','--pids-limit=96','--memory=512m',
 '--tmpfs=/tmp:rw,nosuid,nodev,size=64m,mode=1777','--workdir=/source',
 '--mount=type=bind,src='+str(repo)+',dst=/source,readonly']
def run(label,mounts,args):
 command=common+sum((['--mount=type=bind,src='+str(src)+',dst='+str(dst)+(',readonly' if ro else '')] for src,dst,ro in mounts),[])
 command+=[image,'/usr/local/bin/python3.11','-B','-S']+args
 result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=50)
 (base/(label+'.stdout')).write_bytes(result.stdout);(base/(label+'.stderr')).write_bytes(result.stderr)
 print(label+': '+result.stdout.decode(errors='replace')[-12000:]);print(result.stderr.decode(errors='replace')[-12000:])
 assert result.returncode==0,(label,result.returncode)
run('fixture',[(base,base,False)],['tests/p2_install/test_b4_sandbox.py','fixture',str(base)])
for role in ('developer','platform-engineer'):
 mounts=[(base,base,False),(base/'b3-initialize',base/'b3-initialize',True)]
 if role=='platform-engineer':mounts.append((base/'b4-sandbox/workspace',base/'b4-sandbox/workspace',True))
 run(role,mounts,['tests/p2_install/test_b4_sandbox.py','role',str(base/'request.json'),role])
print(json.dumps({'status':'PASS','retained_fixture':str(base),'UK_EXECUTED':False}))
