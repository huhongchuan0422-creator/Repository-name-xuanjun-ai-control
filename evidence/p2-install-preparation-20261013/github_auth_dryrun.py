import os,sys,socket,stat,subprocess,json,hashlib
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
run=sys.argv[1];assert run.isdigit()
base='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
tokenpath=base+'/github-intake-token.input';helper=base+'/git-preparation-askpass.py';mirror=base+'/control-mirror.git'
code=("#!/usr/bin/python3\nimport sys,os,stat\np="+repr(tokenpath)+"\nif 'Username' in sys.argv[1]: print('huhongchuan0422-creator')\nelse:\n fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)\n with os.fdopen(fd) as f:\n  s=os.fstat(f.fileno());assert s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o600\n  print(f.read().strip())\n").encode()
for path,mode in [(helper,0o500),(tokenpath,0o600)]:
 s=os.lstat(path);assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==mode and os.path.realpath(path)==path
with open(helper,'rb') as f:assert f.read()==code
s=os.lstat(mirror);assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700
env={'PATH':'/usr/bin:/bin','LANG':'C','GIT_TERMINAL_PROMPT':'0','GIT_ASKPASS':helper,'GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_NOSYSTEM':'1','GIT_NO_REPLACE_OBJECTS':'1'}
remote='https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control.git'
prefix=['/usr/bin/git','--git-dir='+mirror,'-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','-c','credential.helper=','-c','protocol.ext.allow=never','-c','protocol.file.allow=never']
source='0f7e150688632b250da375f23a4475c696b1a541';ref='refs/heads/xj-p2-auth-dryrun-'+run
def execute(args):return subprocess.run(prefix+args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
assert execute(['rev-parse',source+'^{commit}']).returncode==0
before=execute(['ls-remote','--refs',remote,ref]);assert before.returncode==0 and not before.stdout.strip()
p=execute(['push','--dry-run','--no-mirror','--porcelain','--no-verify',remote,source+':'+ref])
after=execute(['ls-remote','--refs',remote,ref]);assert after.returncode==0 and not after.stdout.strip()
result={'schema':1,'state':'GIT_RECEIVE_PACK_AUTH_DRY_RUN_PASS' if p.returncode==0 else 'HOLD_GIT_RECEIVE_PACK_AUTH_DRY_RUN_FAILED','exit_code':p.returncode,'remote_ref_absent_before_and_after':True,'github_refs_mutated':False,'pr_write_permission':'NOT_TESTED','credential_values_exported':False,'canonical_changed':False,'install':False,'model_calls':0}
raw=(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode()
fd=os.open(base+'/github-auth-dryrun-'+run+'.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
fd=os.open(base+'/github-auth-dryrun-'+run+'.private-log',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(p.stdout+p.stderr)
print(json.dumps(result,sort_keys=True));print('GIT_AUTH_DRYRUN_RECEIPT_SHA256='+hashlib.sha256(raw).hexdigest())
