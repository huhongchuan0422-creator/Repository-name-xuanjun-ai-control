"""Bind protected prerequisite proposal to exact reviewed runtime and real RPM evidence; no apply."""
import os,sys,stat,socket,json,hashlib,pwd,grp,subprocess
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
REFS={
 'core_plan':(BASE+'/plan-p2pkg-38420216343-1/protected-core-install-plan.json','6a7789a023d0cbb265663275ee7442fdd026eaaee0fc4ee4a0f237ec5a62e970'),
 'owner_readback':(BASE+'/owner-canary-pagination-38409965442/protected-owner-binding-inputs.json','a6223af5bf3d53d886e7d337dde29068883802f3a0ee14ef20e308a31cde3bf8'),
 'rpm_baseline':(BASE+'/rpm-tls-baseline-38410346819/protected-rpm-tls-baseline.json','f784c4809b77df7f75ded97209efc32ff8c69944be33028e59e9422dcae100ec'),
 'rpm_effects':(BASE+'/rpm-effects-38411108032/protected-rpm-effects.json','aef9dc5502d2da938959bfa71a29f9848d233d129cc3d6e49436ac2cbfd10736'),
 'rpm_rehearsal':(BASE+'/rpm-rehearsal-38411861476/protected-rpm-rehearsal.json','09de6870ee258c1719607fff7a5d3a599e19761dd087168628743511fcdb319d')}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path,mode=0o600,limit=16777216):
 assert os.path.realpath(path)==path
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());raw=f.read(limit+1)
  assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==mode and s.st_nlink==1 and len(raw)<=limit
 return raw
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ' and len(sys.argv)==2 and sys.argv[1].isdigit()
values={}
for name,(path,digest) in REFS.items():
 raw=read(path);assert sha(raw)==digest;values[name]=json.loads(raw)
assert values['owner_readback']['public_receipt']['prior_canary_readback_match'] is True
assert values['rpm_rehearsal']['public_receipt']['isolated_packages_removed'] is True
assert values['core_plan']['artifact']['source_commit']=='62d2e64d34feea1f02bffa7e8b597484bb98307f'
identity_free=True
for fn,key in ((pwd.getpwnam,'nginx'),(grp.getgrnam,'nginx'),(pwd.getpwuid,1008),(grp.getgrgid,1008)):
 try:fn(key);identity_free=False
 except KeyError:pass
# Inspect actual RPM modes rather than treating all listed directories as conflicts.
conflicts=[];checked=0;packages=values['rpm_baseline']['packages']
for row in packages:
 assert row['before'] is None and sha(read(row['path'],0o400,67108864))==row['sha256']
 absent=subprocess.run(['/bin/rpm','-q',row['name']],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
 assert absent.returncode==1, 'HOLD_HOST_PACKAGE_BASELINE_CHANGED'
 p=subprocess.run(['/bin/rpm','-qp','--qf','[%{FILENAMES}\t%{FILEMODES:octal}\n]',row['path']],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
 assert p.returncode==0 and len(p.stdout)<=16777216
 for line in p.stdout.decode().splitlines():
  path,mode=line.rsplit('\t',1);mode=int(mode,8);checked+=1;assert checked<=50000 and path.startswith('/')
  if not stat.S_ISDIR(mode) and os.path.lexists(path):conflicts.append(path)
units={}
for unit in ('xuanjun-uk-stage1-minimal.service','xuanjun-uk-openclaw.service'):
 p=subprocess.run(['/usr/bin/systemctl','show',unit,'--property=Id,ActiveState,SubState,MainPID,ControlGroup,UnitFileState'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
 assert p.returncode==0
 units[unit]=dict(line.split('=',1) for line in p.stdout.decode().splitlines() if '=' in line)
 cg=units[unit].get('ControlGroup','');units[unit]['cgroup_empty']=False
 if cg.startswith('/system.slice/') and '..' not in cg:
  try:
   with open('/sys/fs/cgroup/systemd'+cg+'/cgroup.procs','r') as f:units[unit]['cgroup_empty']=not f.read(65537).strip()
  except FileNotFoundError:pass
paths=[row['path'] for row in packages];names=[row['name'] for row in packages]
proposal={'schema':1,'state':'PROTECTED_PREREQUISITE_PLAN_NOT_APPROVED','reviewed_runtime':{'source':'62d2e64d34feea1f02bffa7e8b597484bb98307f','artifact':11825547804,'manifest_sha256':'2b49066f37742dedd41657fb445c91f4204fd4a2a257f921dd9fd514e5b25f0e','source_review':'https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/58#issuecomment-6149473773'},'references':{name:{'path':path,'sha256':digest} for name,(path,digest) in REFS.items()},'proposed_nginx_identity':{'name':'nginx','uid':1008,'gid':1008,'home':'/var/lib/xuanjun-development/nginx-home','shell':'/sbin/nologin','currently_free':identity_free,'reserved':False},'rpm_install_command':['/bin/rpm','-U','--noscripts','--notriggers']+paths,'rpm_rollback_command':['/bin/rpm','-e','--noscripts','--notriggers']+names,'excluded_host_flag':'--nodeps','unit_autopreset_allowed':False,'old_units_observed':units,'existing_payload_conflicts':sorted(set(conflicts)),'payload_paths_checked':checked,'required_before_apply':['INDEPENDENT_PROTECTED_PLAN_APPROVAL','OLD_EXECUTORS_QUIESCED_AND_FENCED','DURABLE_EFFECT_JOURNAL','NSS_FIXED_IDENTITY_APPLY_AND_EXACT_ROLLBACK','ALL_PACKAGE_TARGETS_AND_ROLLBACK_STATE_REVALIDATED','SAME_VERSION_PRODUCTION_RELEASE_GATE'],'install_admission':False,'apply_entrypoint_integrated':True,'production_rollback_verified':False,'model_calls':0}
out=BASE+'/prerequisite-plan-'+sys.argv[1];os.mkdir(out,0o700);path=out+'/protected-prerequisite-install-proposal.json';raw=(json.dumps(proposal,sort_keys=True,separators=(',',':'))+'\n').encode()
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
print(json.dumps({'state':proposal['state'],'nginx_identity_free_unreserved':identity_free,'payload_paths_checked':checked,'existing_payload_conflict_count':len(set(conflicts)),'old_units':units,'owner_canary_readback':True,'rpm_isolated_install_and_erase':True,'install':False,'services_changed':False,'canonical_ledger_changed':False,'model_calls':0},sort_keys=True))
print('PREREQUISITE_PROPOSAL_PATH='+path);print('PREREQUISITE_PROPOSAL_SHA256='+sha(raw))
