"""Stage exact95 and repair plan's package paths; no install or canonical writes."""
import copy,hashlib,io,json,os,socket,stat,subprocess,sys,tarfile,zipfile
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
TX='c529c379-9341-4510-8384-fc6be1e412e5'
OLD=BASE+'/legacy-isolation-'+TX
MANIFEST='44ede26d72bbb776dc813d6eb4d057581e11440d17082a6f1a207fc377689b0a'
SOURCE='2516b8adf88a126b956c6b5ccf1a1dd186a328a6'
TREE='e03b72b7b9578ef5087ca8c01c9276ab73825dcb'
def require(v,c):
 if not v:raise ValueError(c)
def h(v):return hashlib.sha256(v).hexdigest()
def read(p):
 require(os.path.realpath(p)==p,'PREPARATION_PATH_ALIAS')
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  i=os.fstat(f.fileno());b=f.read(2097153)
  require(stat.S_ISREG(i.st_mode) and i.st_nlink==1 and len(b)<=2097152,'PREPARATION_FILE_BOUND')
 return b
def write(p,b,mode=0o600):
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
 os.fchmod(fd,mode)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
def main():
 require(os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ','FIXED_ROOT_UK')
 run=sys.argv[1];require(run.isdigit(),'RUN_REQUIRED')
 archive_path=sys.argv[2]
 zraw=read(archive_path);require(h(zraw)=='b8b33cba5f9951466e3242dfaa264471d80fdab1cbf832843baacbac43202107','EXACT95_ZIP')
 z=zipfile.ZipFile(io.BytesIO(zraw));archive=z.read('p2-candidate.tar.gz')
 require(z.read('p2-source-tree.txt').decode().strip()==TREE,'EXACT95_SOURCE_TREE_RECEIPT')
 require(h(archive)=='53c0f0f898aca62edef45b1fcc9337c4eddabcf58eb364edbb164b8d0a97dd59','EXACT95_ARCHIVE')
 t=tarfile.open(fileobj=io.BytesIO(archive));members=t.getmembers();seen=set();total=0
 for m in members:
  require(m.isfile() and m.name.startswith('xuanjun-p2-package/') and '..' not in m.name.split('/') and m.name not in seen,'ARCHIVE_MEMBER_SCOPE')
  seen.add(m.name);total+=m.size;require(total<=16777216,'ARCHIVE_BOUND')
 oldplan=BASE+'/adopted-core-plan-38439161110/protected-core-install-plan.json'
 original=read(oldplan);require(h(original)=='4d16f2f68016afa5c869373e59e01ffeae581eb54db3c69cdc6b686cfc4f05e8','PRIOR_PLAN_DRIFT')
 plan=json.loads(original.decode());require(plan['transaction_id']==TX and plan['artifact']['source_commit']==SOURCE and plan['artifact']['source_tree']==TREE,'EXACT_ORIGINAL_BINDINGS')
 notifier=read(OLD+'/notifier/notifier-isolation-receipt.json')
 require(h(notifier)=='a43d2188c7f2528e6a061898ccf435958fe99d9d26cf3a4c8cddcd1670522a55','NOTIFIER_ACCEPTED_RECEIPT_DRIFT')
 require(json.loads(notifier.decode())['state']=='AUTHORIZED_NOTIFIER_ISOLATED','NOTIFIER_STATE')
 d=BASE+'/complete-install-candidate-'+run;os.mkdir(d,0o700)
 for m in members:
  target=d+'/'+m.name;parent=os.path.dirname(target)
  os.makedirs(parent,mode=0o755,exist_ok=True)
  require(os.path.realpath(parent)==parent,'STAGED_PARENT_ALIAS')
  write(target,t.extractfile(m).read(),0o644)
 root=d+'/xuanjun-p2-package';manifest=read(root+'/deploy/integration-manifest.json')
 require(h(manifest)==MANIFEST,'STAGED_MANIFEST_DRIFT')
 files=json.loads(manifest.decode())['files'];require(len(files)==95,'STAGED_FILE_COUNT')
 for rel,wanted in files.items():require(h(read(root+'/'+rel))==wanted,'STAGED_RUNTIME_HASH')
 previous={'root':plan['artifact']['root'],'manifest':plan['artifact']['manifest']}
 plan['artifact']['root']=root;plan['artifact']['manifest']=root+'/deploy/integration-manifest.json'
 # Every source/rendered provisioning binding must match the actual exact95 payload.
 for row in plan['runtime']['provisioning']:
  raw=read(root+'/'+row['source']);require(h(raw)==row['source_sha256'],'PROVISIONING_SOURCE_BINDING')
  rendered=raw
  for token,value in sorted(row['replacements'].items()):rendered=rendered.replace(token.encode(),value.encode())
  require(b'@@' not in rendered and h(rendered)==row['rendered_sha256'],'PROVISIONING_RENDERED_BINDING')
 sys.path.insert(0,root+'/stage1')
 from p2_install_entrypoint import validate_plan
 validate_plan(plan)
 packed=(json.dumps(plan,sort_keys=True,separators=(',',':'))+'\n').encode()
 path=d+'/protected-core-install-plan.json';write(path,packed)
 # Persist an OUTER admission candidate: notifier binding, original adapter
 # directory, and exact package/plan. It does not grant release on its own.
 gate={'schema':1,'transaction_id':TX,'source_commit':SOURCE,'source_tree':TREE,
       'artifact_id':11833404272,'manifest_sha256':MANIFEST,'plan_path':path,'plan_sha256':h(packed),
       'notifier_receipt_path':OLD+'/notifier/notifier-isolation-receipt.json',
       'notifier_receipt_sha256':h(notifier),'transaction_directory':OLD,
       'install_receipt':d+'/install-receipt.json','release_installer':root+'/scripts/uk-integration-install.py',
       'cli_path':root+'/scripts/uk-p2-install.py','independent_release_review':'PENDING',
       'install_authorized':False,'six_legacy_units_must_be_masked_before_install':True}
 gatepath=d+'/protected-outer-admission-candidate.json';gatebytes=(json.dumps(gate,sort_keys=True,separators=(',',':'))+'\n').encode();write(gatepath,gatebytes)
 # ORIGINAL transaction directory is required for a fresh CLI rollback adapter
 # to find legacy-units.json. Only new P2 journals would be added on installation.
 args=['/usr/bin/python3','-I','-B',gate['cli_path'],'--operation','verify-only',
       '--plan',path,'--plan-sha256',h(packed),'--receipt',gate['install_receipt'],
       '--transaction-directory',OLD,'--release-installer',gate['release_installer']]
 r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
 if r.returncode:
  import re
  codes=re.findall(r'(?:ValueError|RuntimeError|PermissionError): ([A-Z][A-Z0-9_]+)',r.stderr.decode('utf-8','replace'))
  print('COMPLETE_CLI_PREFLIGHT_ERROR_CODES='+json.dumps(codes))
 require(r.returncode==0,'COMPLETE_CLI_PREFLIGHT_HOLD')
 proof=json.loads(r.stdout.decode());require(proof['stage']=='VERIFIED_ONLY' and proof['effects']==0,'VERIFY_ONLY_PROOF')
 fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
 print('COMPLETE_INSTALL_CANDIDATE='+json.dumps({'schema':1,'source':SOURCE,'tree':TREE,'artifact_id':11833404272,
       'files_verified':95,'provisioning_bindings_verified':len(plan['runtime']['provisioning']),
       'prior_package_paths':previous,'new_package_root':root,'plan_path':path,'plan_sha256':h(packed),
       'plan_bytes':len(packed),'outer_gate_path':gatepath,'outer_gate_sha256':h(gatebytes),
       'verify_only':proof,'install':False,'canonical_database_mutation':False,'transaction_directory':OLD},sort_keys=True))
 print('COMPLETE_PLAN_BYTES_BASE64='+__import__('base64').b64encode(packed).decode())
 output=os.environ.get('GITHUB_OUTPUT')
 if output:
  with open(output,'a') as stream:stream.write('plan_path='+path+'\nplan_sha256='+h(packed)+'\n')
if __name__=='__main__':main()
