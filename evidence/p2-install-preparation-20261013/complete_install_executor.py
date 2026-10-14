"""Root admission for ONE exact reviewed complete P2 candidate.

Approval is fetched from GitHub and checked again in Root, never inferred from
an argument, test success, or the candidate's pending authorization fields.
"""
import argparse,hashlib,http.client,json,os,pwd,grp,re,socket,ssl,stat,subprocess,sys,urllib.request
REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
TX='c529c379-9341-4510-8384-fc6be1e412e5'
MARKER='CHATGPT_NATIVE_TASK5_COMPLETE_INSTALL_ACCEPTANCE\n'
NOTIFIER_SHA='af0555ef8382213889c4d2b3390a202ab0d5218842d8b563456cad20720a8d56'
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('ADMISSION_API_REDIRECT')
def require(v,c):
 if not v:raise ValueError(c)
def digest(b):return hashlib.sha256(b).hexdigest()
def read(path,private=False,limit=1048576):
 require(os.path.realpath(path)==path,'ADMISSION_PATH_ALIAS')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());b=f.read(limit+1)
 require(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and len(b)<=limit,'ADMISSION_REGULAR_FILE_BOUND')
 if private:require(s.st_uid==0 and s.st_gid==0 and stat.S_IMODE(s.st_mode)==0o600,'ADMISSION_ROOT_PRIVATE')
 return b,s
def fetch_review(review_id,body_sha):
 require(type(review_id) is int and review_id>0 and re.fullmatch(r'[0-9a-f]{64}',body_sha) is not None,'ADMISSION_REVIEW_IDENTITY')
 request=urllib.request.Request('https://api.github.com/repos/'+REPO+'/issues/comments/'+str(review_id),headers={'Accept':'application/vnd.github+json'})
 with urllib.request.build_opener(NoRedirect()).open(request,timeout=20) as r:b=r.read(65537)
 require(len(b)<=65536,'ADMISSION_REVIEW_BOUND');comment=json.loads(b.decode())
 require(comment.get('id')==review_id and comment.get('user',{}).get('login')=='huhongchuan0422-creator' and comment.get('user',{}).get('id')==332398908,'ADMISSION_REVIEW_AUTHOR')
 body=comment.get('body','');require(digest(body.encode())==body_sha and body.startswith(MARKER),'ADMISSION_ACTUAL_REVIEW_BODY')
 value=json.loads(body[len(MARKER):])
 require(value.get('schema')==1 and value.get('reviewer')=='CHATGPT_NATIVE_TASK5' and value.get('decision')=='APPROVED_FOR_PROTECTED_INSTALL_AND_FENCED_ROLLBACK','ADMISSION_INDEPENDENT_DECISION')
 require(value.get('release_granted') is True and value.get('owner_install_scope_authorized') is True and value.get('accept_acme_terms') is True,'ADMISSION_INSTALL_SCOPE')
 return value
def bind_review(value,gate,plan_sha,gate_sha,executor_sha,auditor_sha):
 expected={'source':gate['source_commit'],'tree':gate['source_tree'],'artifact':gate['artifact_id'],
           'manifest_sha256':gate['manifest_sha256'],'plan_sha256':plan_sha,'outer_gate_sha256':gate_sha,
           'executor_sha256':executor_sha,'auditor_sha256':auditor_sha,'transaction_id':TX}
 require(all(value.get(k)==v for k,v in expected.items()),'ADMISSION_EXACT_BUNDLE_MISMATCH')
 return expected
def package_check(plan,gate):
 root=plan['artifact']['root'];require(root==os.path.dirname(gate['plan_path'])+'/xuanjun-p2-package','ADMISSION_PACKAGE_PATH')
 for parent,dirs,files in os.walk(root,followlinks=False):
  i=os.lstat(parent);require(stat.S_ISDIR(i.st_mode) and i.st_uid==0 and not i.st_mode&0o022 and os.path.realpath(parent)==parent,'ADMISSION_PACKAGE_DIRECTORY')
  require(not any(os.path.islink(parent+'/'+name) for name in dirs),'ADMISSION_PACKAGE_DIRECTORY_ALIAS')
  require(not any(name.endswith('.pyc') for name in files),'ADMISSION_UNREVIEWED_BYTECODE')
 b,s=read(plan['artifact']['manifest']);require(s.st_uid==0 and not s.st_mode&0o022 and digest(b)==gate['manifest_sha256'],'ADMISSION_MANIFEST_BINDING')
 manifest=json.loads(b.decode());require(len(manifest['files'])==100,'ADMISSION_COMPLETE_RUNTIME_COUNT')
 for name,wanted in manifest['files'].items():
  require(not name.startswith('/') and '..' not in name.split('/'),'ADMISSION_PAYLOAD_PATH')
  raw,info=read(root+'/'+name,limit=16777216)
  require(info.st_uid==0 and not info.st_mode&0o022 and digest(raw)==wanted,'ADMISSION_PAYLOAD_BYTES')
 proof=json.loads(read(root+'/P2_PACKAGE_PROVENANCE.json')[0].decode())
 require(proof['source_commit']==gate['source_commit'] and proof['source_tree']==gate['source_tree'] and proof['runtime_manifest_sha256']==gate['manifest_sha256'],'ADMISSION_PROVENANCE')
 return root
def write(path,data):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
def post_install_checks(plan,root,result):
 sys.path.insert(0,root+'/stage1')
 from activation_control import ActivationStore
 from p2_tls_lifecycle import certificate_check,TIMER,TlsLifecycle
 active=ActivationStore('/var/lib/xuanjun-development/activation/active.json','/var/lib/xuanjun-development/activation/epochs.jsonl','/var/lib/xuanjun-development/activation/activation.lock').read(require_active=True)
 expected=dict(plan['activation']);expected.pop('expected_epoch');expected['epoch']=result['epoch'];expected['state']='ACTIVE'
 require(all(active.get(k)==v for k,v in expected.items()),'POSTINSTALL_ACTIVE_IDENTITY')
 for name,user in plan['runtime']['prerequisites']['users'].items():
  p=pwd.getpwnam(name);require((p.pw_uid,p.pw_gid,p.pw_dir,p.pw_shell)==(user['uid'],user['gid'],user['home'],'/sbin/nologin'),'POSTINSTALL_NSS_IDENTITY')
  expected_groups={user['gid']}|{plan['runtime']['prerequisites']['groups'][g] for g in user['groups']}
  require(set(os.getgrouplist(name,user['gid']))==expected_groups,'POSTINSTALL_NSS_MEMBERSHIP')
 for name,gid in plan['runtime']['prerequisites']['groups'].items():require(grp.getgrnam(name).gr_gid==gid,'POSTINSTALL_NSS_GROUP')
 units=plan['runtime']['services']+['xuanjun-uk-openclaw.service','nginx.service',TIMER]
 for unit in units:require(subprocess.run(['/usr/bin/systemctl','is-active','--quiet',unit],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20).returncode==0,'POSTINSTALL_UNIT_INACTIVE')
 tls=TlsLifecycle(BASE+'/legacy-isolation-'+TX).rollback_check();require(tls['state']=='READY_ISSUED_AND_RENEWAL_DRYRUN_VERIFIED','POSTINSTALL_TLS_RENEWAL_DRYRUN')
 leaf=certificate_check();statuses={}
 for path in ('/owner/','/owner/api/state','/owner-callback'):
  sock=socket.create_connection(('127.0.0.1',443),timeout=10)
  with ssl.create_default_context().wrap_socket(sock,server_hostname='uk.wenwenwenyiyiyi.work') as secure:
   require(digest(secure.getpeercert(binary_form=True))==leaf,'POSTINSTALL_SERVED_CERTIFICATE')
   secure.sendall(('GET '+path+' HTTP/1.1\r\nHost: uk.wenwenwenyiyiyi.work\r\nConnection: close\r\n\r\n').encode())
   response=http.client.HTTPResponse(secure);response.begin();statuses[path]=response.status
 require(statuses['/owner/']==200 and statuses['/owner/api/state'] in (401,403) and statuses['/owner-callback'] in (403,405),'POSTINSTALL_HTTPS_AUTH_BOUNDARY')
 return {'active_identity_verified':True,'nss_verified':True,'services_active':True,'https_statuses':statuses,'served_certificate_sha256':leaf,'real_acme_issuance_and_renewal_dryrun':True,'model_calls_by_these_checks':0,'historical_notification_replay':False,'production_rollback':'ONLY_IF_FAILURE_NOT_CLAIMED_TESTED'}
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--candidate',required=True);parser.add_argument('--review-id',type=int,required=True);parser.add_argument('--review-body-sha256',required=True);parser.add_argument('--run-id',required=True);parser.add_argument('--operation',choices=('install','rollback'),required=True)
 a=parser.parse_args();require(os.geteuid()==0 and a.run_id.isdigit() and len(a.run_id)<=20 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ','ADMISSION_ROOT_AND_RUN')
 require(a.candidate.startswith(BASE+'/complete-install-candidate-') and a.candidate.endswith('/protected-outer-admission-candidate.json'),'ADMISSION_CANDIDATE_SCOPE')
 gate_bytes,_=read(a.candidate,private=True);gate=json.loads(gate_bytes.decode());require(gate['transaction_id']==TX and gate['transaction_directory']==BASE+'/legacy-isolation-'+TX,'ADMISSION_ORIGINAL_TRANSACTION')
 require(gate['plan_path']==os.path.dirname(a.candidate)+'/protected-core-install-plan.json' and gate['install_receipt']==os.path.dirname(a.candidate)+'/install-receipt.json','ADMISSION_PLAN_RECEIPT_SCOPE')
 for directory in (os.path.dirname(a.candidate),gate['transaction_directory']):
  i=os.lstat(directory);require(os.path.realpath(directory)==directory and i.st_uid==0 and stat.S_ISDIR(i.st_mode) and stat.S_IMODE(i.st_mode)==0o700,'ADMISSION_PRIVATE_DIRECTORY')
 plan_bytes,_=read(gate['plan_path'],private=True);require(digest(plan_bytes)==gate['plan_sha256'],'ADMISSION_PLAN_BYTES');plan=json.loads(plan_bytes.decode())
 require(plan['artifact']['source_commit']==gate['source_commit'] and plan['artifact']['source_tree']==gate['source_tree'] and plan['artifact']['manifest_sha256']==gate['manifest_sha256'],'ADMISSION_PLAN_SOURCE')
 root=package_check(plan,gate)
 here=os.path.dirname(os.path.abspath(__file__));audit_bytes,_=read(here+'/consolidated_readiness.py');notifier_bytes,_=read(here+'/notifier_isolation_candidate.py')
 require(digest(notifier_bytes)==NOTIFIER_SHA,'ADMISSION_READONLY_ISOLATION_AUDITOR')
 executor_sha=globals().get('EXECUTOR_SHA256');require(re.fullmatch(r'[0-9a-f]{64}',executor_sha or '') is not None,'ADMISSION_HASHED_ROOT_LOADER_REQUIRED')
 value=fetch_review(a.review_id,a.review_body_sha256);expected=bind_review(value,gate,digest(plan_bytes),digest(gate_bytes),executor_sha,digest(audit_bytes))
 d=gate['transaction_directory']+'/complete-admission-'+a.run_id;os.mkdir(d,0o700)
 write(d+'/authorization.json',(json.dumps({'review_id':a.review_id,'review_body_sha256':a.review_body_sha256,'bundle':expected,'operation':a.operation},sort_keys=True)+'\n').encode())
 if a.operation=='install':
  require(not os.path.lexists(gate['install_receipt']),'ADMISSION_EXISTING_INSTALL_HOLD')
  write(d+'/consolidated_readiness.py',audit_bytes);write(d+'/notifier_isolation_candidate.py',notifier_bytes)
  r=subprocess.run(['/usr/bin/python3','-I','-B',d+'/consolidated_readiness.py',a.run_id,gate['plan_path'],gate['plan_sha256']],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
  require(r.returncode==0,'ADMISSION_FRESH_READINESS_FAILED')
  lines=r.stdout.decode().splitlines();measurement=json.loads(next(x.split('=',1)[1] for x in lines if x.startswith('CONSOLIDATED_READINESS_RESULT=')))
  require(not measurement['errors'] and measurement['sections']['fresh_canonical_db_fd_scope']['complete_no_holders'],'ADMISSION_FRESH_SCOPE_HOLD')
  authority=measurement['sections']['legacy_authority_and_expiry_fixture'];require(authority['fixture_claim_result']=='NONE' and authority['expired_request_denials']==authority['unconsumed_expired_requests'] and authority['native_execution_records']==0,'ADMISSION_OLD_EXECUTION_HOLD')
  entries=measurement['sections']['remaining_control_entry_inventory'];require(not entries['control_related_scheduler_files'] and all(x['exe']=='/usr/bin/ssh' for x in entries['uid1002_processes']),'ADMISSION_UNCLASSIFIED_OLD_ENTRY_HOLD')
  write(d+'/fresh-readiness-output.json',(json.dumps(measurement,sort_keys=True)+'\n').encode())
 require(gate['cli_path']==root+'/scripts/uk-p2-install.py' and gate['release_installer']==root+'/scripts/uk-integration-install.py','ADMISSION_EXACT_CLI')
 argv=['/usr/bin/python3','-I','-B',gate['cli_path'],'--operation',a.operation,'--plan',gate['plan_path'],'--plan-sha256',gate['plan_sha256'],'--receipt',gate['install_receipt'],'--transaction-directory',gate['transaction_directory'],'--release-installer',gate['release_installer']]
 try:r=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=900)
 except subprocess.TimeoutExpired:
  print('P2_ADMITTED_EXECUTION_HOLD='+json.dumps({'review_id':a.review_id,'operation':a.operation,'reason':'CLI_TIMEOUT_RECONCILIATION_REQUIRED','automatic_retry':False,'effects':'UNKNOWN_READ_JOURNALS'}));return 1
 if r.returncode:
  receipt=None
  if os.path.lexists(gate['install_receipt']):receipt=json.loads(read(gate['install_receipt'],private=True)[0].decode())
  print('P2_ADMITTED_EXECUTION_HOLD='+json.dumps({'review_id':a.review_id,'operation':a.operation,'receipt':receipt,'automatic_retry':False},sort_keys=True))
  return 1
 result=json.loads(r.stdout.decode());expected_stage='COMPLETE' if a.operation=='install' else 'ROLLED_BACK';require(result['stage']==expected_stage,'ADMISSION_UNEXPECTED_EXECUTION_STAGE')
 checks=None
 if a.operation=='install':
  try:checks=post_install_checks(plan,root,result)
  except Exception as error:
   # The approval explicitly covers fenced rollback. Reuse the exact CLI and
   # COMPLETE receipt; no legacy restart, new plan or blind execution retry.
   rollback_argv=list(argv);rollback_argv[rollback_argv.index('--operation')+1]='rollback'
   rollback=subprocess.run(rollback_argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300)
   state=json.loads(read(gate['install_receipt'],private=True)[0].decode())
   print('P2_POSTINSTALL_ACCEPTANCE_HOLD='+json.dumps({'error_type':type(error).__name__,'rollback_exit':rollback.returncode,'actual_receipt':state,'automatic_retry':False},sort_keys=True));return 1
 write(d+'/actual-cli-result.json',(json.dumps(result,sort_keys=True)+'\n').encode())
 print('P2_ADMITTED_EXECUTION_RESULT='+json.dumps({'review_id':a.review_id,'operation':a.operation,'bundle':expected,'result':result,'post_install_checks':checks,'authorization_directory':d},sort_keys=True))
 return 0
if __name__=='__main__':sys.exit(main())
