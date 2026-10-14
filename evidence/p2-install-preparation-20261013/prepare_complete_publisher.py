"""Prepare publisher seed and prove credential wiring in a disposable UID realm."""
import hashlib,json,os,re,shutil,socket,stat,subprocess,sys,tempfile,signal
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
REMOTE='https://github.com/'+REPO+'.git'
SOURCE='f30c40bc2a49d6ace9d30d17bd82cdf4a5fb7b7c'
TREE='7f40340da949764a2a8bc11b3ce5d40d9b48d37a'
GH_SHA='7469124f706944133d6a169691dd1c6c3511b12e85878d255e044e2948df4c9b'
ENV={'PATH':'/usr/bin:/bin','LANG':'C','GIT_TERMINAL_PROMPT':'0','GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_NOSYSTEM':'1','GIT_NO_REPLACE_OBJECTS':'1'}
def sha(data):return hashlib.sha256(data).hexdigest()
def read(path,mode=0o600,limit=1048576):
 assert os.path.realpath(path)==path
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());data=f.read(limit+1);end=os.fstat(f.fileno())
  assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==mode and s.st_nlink==1 and len(data)<=limit
  assert (s.st_size,s.st_mtime_ns,s.st_ctime_ns)==(end.st_size,end.st_mtime_ns,end.st_ctime_ns)
 return data
def write(path,data):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
def cmd(args,env=ENV,timeout=30):
 p=subprocess.Popen(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
 try:out,err=p.communicate(timeout=timeout)
 except subprocess.TimeoutExpired:
  os.killpg(p.pid,signal.SIGKILL);p.communicate();raise ValueError('PUBLISHER_COMMAND_TIMEOUT_GROUP_KILLED')
 if p.returncode:raise ValueError('PUBLISHER_EXTERNAL_COMMAND_FAILED')
 return out
def git(directory,*args):
 return ['/usr/bin/git','--git-dir='+directory,'-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','-c','credential.helper=']+list(args)
def main(run):
 assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ' and run.isdigit()
 s=os.lstat(BASE);assert s.st_uid==0 and stat.S_ISDIR(s.st_mode) and stat.S_IMODE(s.st_mode)==0o700
 output=BASE+'/publisher-realm-'+run;os.mkdir(output,0o700)
 token=read(BASE+'/github-intake-token.input').strip();assert re.fullmatch(br'github_pat_[A-Za-z0-9_]+',token)
 config=b'github.com:\n    user: huhongchuan0422-creator\n    git_protocol: https\n    oauth_token: '+token+b'\n'
 write(output+'/gh-hosts.yml',config)
 mirror=BASE+'/control-mirror.git';assert os.path.realpath(mirror)==mirror
 s=os.lstat(mirror);assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700
 assert cmd(git(mirror,'config','--get','remote.origin.url')).decode().strip()==REMOTE
 ref='refs/xuanjun-preparation/'+SOURCE
 helper=BASE+'/git-preparation-askpass.py';read(helper,0o500)
 fetch_env=dict(ENV,GIT_ASKPASS=helper)
 # Standalone preparation must not depend on a separate queued verifier fetching first.
 cmd(git(mirror,'fetch','--quiet','--no-tags',REMOTE,SOURCE+':'+ref),fetch_env,timeout=60)
 assert cmd(git(mirror,'rev-parse',ref+'^{tree}')).decode().strip()==TREE
 bundle=output+'/control.bundle';cmd(git(mirror,'bundle','create',bundle,ref),timeout=60);os.chmod(bundle,0o600)
 size=os.stat(bundle).st_size;assert size<134217728
 seed_plan=read(BASE+'/adopted-core-plan-38439161110/protected-core-install-plan.json')
 assert sha(seed_plan)=='4d16f2f68016afa5c869373e59e01ffeae581eb54db3c69cdc6b686cfc4f05e8'
 sources=[x['source'] for x in json.loads(seed_plan)['runtime']['prerequisites']['binaries'] if x['sha256']==GH_SHA]
 assert len(sources)==1
 gh=[(sources[0],read(sources[0],0o555,67108864))];assert sha(gh[0][1])==GH_SHA
 fixture=tempfile.mkdtemp(prefix='xj-p2-publisher-realm-');os.chmod(fixture,0o711)
 result={'schema':1,'source_commit':SOURCE,'source_tree':TREE,'canonical_mirror_applied':False,'github_config_applied':False,
  'pr_write_permission':'NOT_TESTED','model_calls':0,'install':False,'writer_admission':False}
 try:
  binary=fixture+'/gh';write(binary,gh[0][1]);os.chmod(binary,0o555)
  seed=fixture+'/control.git';cmd(['/usr/bin/git','init','--bare','--quiet',seed])
  cmd(git(seed,'-c','protocol.file.allow=always','fetch','--quiet','--no-tags',bundle,ref+':refs/heads/bootstrap-source'))
  cmd(git(seed,'symbolic-ref','HEAD','refs/heads/bootstrap-source'))
  cmd(git(seed,'config','remote.origin.url',REMOTE));cmd(git(seed,'config','remote.origin.fetch','+refs/heads/*:refs/remotes/origin/*'))
  for parent,dirs,files in os.walk(seed):
   for name in list(files):
    if '/hooks' in parent:os.unlink(parent+'/'+name);continue
    p=parent+'/'+name;s=os.lstat(p);assert stat.S_ISREG(s.st_mode) and s.st_nlink==1
    os.chown(p,1003,1003);os.chmod(p,0o600)
   os.chown(parent,1003,1003);os.chmod(parent,0o700)
  home=fixture+'/home';os.mkdir(home,0o700);os.chown(home,1003,1003)
  for part in (home+'/.config',home+'/.config/gh'):
   os.mkdir(part,0o700);os.chown(part,1003,1003)
  hosts=home+'/.config/gh/hosts.yml';write(hosts,config);os.chown(hosts,1003,1003)
  env=dict(ENV,HOME=home,GH_PROMPT_DISABLED='1',NO_COLOR='1')
  prefix=['/usr/bin/setpriv','--reuid=1003','--regid=1003','--clear-groups']
  actual=cmd(prefix+[binary,'api','user','--jq','.login'],env).decode().strip();assert actual=='huhongchuan0422-creator'
  assert cmd(prefix+[binary,'api','repos/'+REPO,'--jq','.full_name'],env).decode().strip()==REPO
  assert cmd(prefix+git(seed,'rev-parse','HEAD^{tree}'),env).decode().strip()==TREE
  target='refs/heads/xj-p2-publisher-dryrun-'+run
  publish=git(seed,'-c','credential.helper='+binary+' auth git-credential')
  before=cmd(prefix+publish+['ls-remote','--refs',REMOTE,target],env);assert not before.strip()
  cmd(prefix+publish+['push','--dry-run','--no-mirror','--porcelain','--no-verify',REMOTE,SOURCE+':'+target],env)
  after=cmd(prefix+publish+['ls-remote','--refs',REMOTE,target],env);assert not after.strip()
  # Actual PR comment write/readback under the isolated publisher identity.
  # This is the existing PR17 checkpoint channel, not a new PR/task/review.
  body='WORK_NATIVE publisher authentication checkpoint: preparation Run'+run+' Source '+SOURCE+'. Exact-source isolated credential PR17 write/readback verification; P2 INSTALL=NO, RELEASE=HOLD; no host installation or remote ref publication.'
  posted=json.loads(cmd(prefix+[binary,'api','repos/'+REPO+'/issues/17/comments','--method','POST','-f','body='+body],env).decode())
  comment_id=posted['id'];readback=json.loads(cmd(prefix+[binary,'api','repos/'+REPO+'/issues/comments/'+str(comment_id)],env).decode())
  assert readback['id']==comment_id and readback['body']==body and readback['user']['login']=='huhongchuan0422-creator'
  result.update(pr_write_permission='PASS_ACTUAL_PR17_COMMENT_READBACK',pr_write_checkpoint_comment_id=comment_id,github_comment_effects=1)
  probe="import os,sys;u=int(sys.argv[1]);os.setgroups([]);os.setgid(u);os.setuid(u);\ntry:\n f=open(sys.argv[2],'rb');f.close();print('ALLOWED')\nexcept PermissionError:print('DENIED')"
  access=[]
  for uid,expected in [(1003,'ALLOWED'),(1002,'DENIED'),(1005,'DENIED')]:
   row=cmd(['/usr/bin/python3','-I','-B','-c',probe,str(uid),hosts]).decode().strip();assert row==expected
   access.append({'uid':uid,'gh_configuration_read':row})
  result.update(state='ISOLATED_DISPATCHER_GH_CONFIG_MIRROR_AND_DRYRUN_PASS',numeric_uid=1003,
    gh_configuration_access=access,gh_identity_verified=True,repository_verified=True,seed_tree_verified=True,
    git_receive_pack_authenticated=True,remote_ref_absent_before_after=True)
 finally:
  shutil.rmtree(fixture);result['fixture_removed']=not os.path.lexists(fixture)
 with open(bundle,'rb') as f:bundle_sha=sha(f.read())
 manifest={'schema':1,'source_commit':SOURCE,'source_tree':TREE,'repository':REPO,
  'bundle':{'path':bundle,'sha256':bundle_sha,'size':size},
  'github_hosts':{'path':output+'/gh-hosts.yml','sha256':sha(config),'owner_uid':1003,'group_gid':1003,'mode':0o600},
  'target_mirror':'/var/lib/xuanjun-development/control.git',
  'target_gh_hosts':'/var/lib/xuanjun-development/service-home/.config/gh/hosts.yml',
  'canonical_targets_applied':False,'requires_separate_install_integration':True}
 raw=(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n').encode();write(output+'/protected-publisher-inputs.json',raw)
 result['publisher_inputs_sha256']=sha(raw);result['publisher_inputs_path']=output+'/protected-publisher-inputs.json';result['bundle_bytes']=size
 receipt=(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode();write(output+'/protected-publisher-receipt.json',receipt)
 print(json.dumps(result,sort_keys=True));print('PUBLISHER_REALM_RECEIPT_SHA256='+sha(receipt))
if __name__=='__main__':main(sys.argv[1])
