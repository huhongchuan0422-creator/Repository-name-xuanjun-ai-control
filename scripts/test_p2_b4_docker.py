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
# Exercise the real host main in a disposable namespace. Only fixed deployment
# constants/B3 fixture pin are replaced in memory; no production CLI override.
import importlib.util,sys
spec=importlib.util.spec_from_file_location('b4_host',repo/'scripts/p2_b4_owner_sandbox_20261020.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
spec=importlib.util.spec_from_file_location('b4_bundle',repo/'scripts/build_p2_b4_bundle.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
original_base=base
base=Path(tempfile.mkdtemp(prefix='p2-b3-test-b4-',dir='/tmp'));os.chown(str(base),1002,1002);base.chmod(0o700)
run('host-fixture',[(base,base,False)],['tests/p2_install/test_b4_sandbox.py','fixture',str(base)])
req=json.loads((base/'request.json').read_bytes());req['application']='/application/stage1'
# Empty fixture output is removed before exercising only-new-directory ownership.
for name in ('workspace','developer','platform-engineer'):(base/'b4-sandbox'/name).rmdir()
(base/'b4-sandbox').rmdir()
os.chown(str(base),0,0)
(base/'state').mkdir(mode=0o700);(base/'state/.formal-cli.lock').write_bytes(b'');(base/'state/.formal-cli.lock').chmod(0o600)
(base/'b3-ledger-final-20261020').mkdir(mode=0o700)
proof=base/'b3-ledger-final-20261020/proof.json';proof.write_bytes(b'CONSTRUCTED_B3_INPUT_FIXTURE_NOT_UK_PROOF');proof.chmod(0o444)
h.HOST=os.uname().nodename.split('.')[0];h.BASE=base;h.WORK=base/'host-work';h.ROOT=base/'b4-sandbox';h.PRIOR=base/'b3-initialize'
h.IMAGE=subprocess.check_output(['/bin/docker','image','inspect',image,'--format','{{.Id}}']).decode().strip()
h.B3_RECEIPT=req['b3_receipt_sha256'];h.B3_PROOF=__import__('hashlib').sha256(proof.read_bytes()).hexdigest()
raw=b.build(repo,request_override=req);bundle=base/'bundle.json';bundle.write_bytes(raw)
sys.argv=['host','--bundle',str(bundle),'--bundle-sha256',__import__('hashlib').sha256(raw).hexdigest()]
assert h.main()==0
before=(h.WORK/'summary.json').read_bytes();assert h.main()==0;assert (h.WORK/'summary.json').read_bytes()==before
for role in ('developer','platform-engineer'):
 c=json.loads(subprocess.check_output(['/bin/docker','inspect','p2-b4-finite-'+role]))[0]
 assert c['State']['Running'] is False and c['State']['ExitCode']==0
 subprocess.check_call(['/bin/docker','rm',c['Id']],stdout=subprocess.DEVNULL)
print(json.dumps({'status':'HOST_MAIN_ROUNDTRIP_PASS','retained_fixture':str(base),'UK_EXECUTED':False}))
