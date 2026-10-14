#!/usr/bin/env python3
"""Exact kit loader. No recovery effects without fresh independent PR58 approval."""
import argparse,hashlib,json,os,pathlib,re,socket,stat,sys
KIT=('/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/'
     'complete-install-candidate-38503014520/epoch5-recovery-candidate-v3')
MANIFEST='3332a6e63b11b75420f1bd0f1a264c89528a92a771f6bc1399f2a38009f324ef'
SHA=re.compile(r'^[0-9a-f]{64}$')
HELPERS=frozenset(('epoch5_approval.py','epoch5_plan.py','epoch5_host_driver.py',
 'epoch5_host_preflight.py','epoch3_service_containment.py','epoch3_install_lock.py',
 'epoch5_native_binding.py','epoch5_attempt_journal.py','epoch3_preserve.py',
 'epoch5_retained_runtime.py','epoch5_retained_state.py','epoch5_activation_rebind.py',
 'epoch5_recovery_sequence.py','inspect_epoch5.py','verify_retained_publisher.py',
 'prepare_epoch5_bindings.py','build_epoch5_runtime.py','recover_exact_hold.py',
 'complete_install_executor.py','inspect_epoch3.py','epoch5_retained_tls.py','observe_epoch5.py'))

def need(value,label):
 if not value:raise ValueError(label)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):
 need(os.path.realpath(path)==path,'KIT_ALIAS')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as stream:
  info=os.fstat(stream.fileno());raw=stream.read(2097153);after=os.fstat(stream.fileno())
 need(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_gid==0 and
      not info.st_mode&0o022 and info.st_nlink==1 and len(raw)<=2097152,'KIT_FILE_AUTHORITY')
 need((info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)==
      (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'KIT_READ_RACE')
 return raw

def verify_kit(expected_sha):
 need(isinstance(expected_sha,str) and SHA.fullmatch(expected_sha),'KIT_SHA_REQUIRED')
 need(os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ','KIT_EXACT_HOST_ROOT')
 for p in (KIT,KIT+'/helpers',KIT+'/tests'):
  info=os.lstat(p)
  need(os.path.realpath(p)==p and stat.S_ISDIR(info.st_mode) and
       (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,0o700),'KIT_DIRECTORY_AUTHORITY')
 raw=read(KIT+'/recovery-kit-manifest.json');need(sha(raw)==expected_sha,'KIT_MANIFEST_CHANGED')
 value=json.loads(raw.decode())
 need(set(value)=={'schema','runtime_manifest_sha256','helper_files','entry_sha256','test_files'} and
      value['schema']==1 and value['runtime_manifest_sha256']==MANIFEST and
      set(value['helper_files'])==HELPERS,'KIT_EXACT_SCOPE')
 need(set(os.listdir(KIT+'/helpers'))==HELPERS,'KIT_EXTRA_HELPER_CONTENT')
 for name,wanted in value['helper_files'].items():
  need(isinstance(wanted,str) and SHA.fullmatch(wanted) and sha(read(KIT+'/helpers/'+name))==wanted,'KIT_HELPER_CHANGED')
 tests=value['test_files']
 need(isinstance(tests,dict) and 1<=len(tests)<=32,'KIT_TEST_SCOPE')
 need(set(os.listdir(KIT+'/tests'))==set(tests),'KIT_EXTRA_TEST_CONTENT')
 for name,wanted in tests.items():
  need(re.fullmatch(r'test_[a-z0-9_]+\.py',name) and isinstance(wanted,str) and SHA.fullmatch(wanted),
       'KIT_TEST_PATH')
  need(sha(read(KIT+'/tests/'+name))==wanted,'KIT_TEST_CHANGED')
 need(sha(read(os.path.abspath(__file__)))==value['entry_sha256'],'KIT_ENTRY_CHANGED')
 need(set(os.listdir(KIT))=={'helpers','tests','xuanjun-p2-package','recovery-kit-manifest.json','epoch5_recovery_entry.py'},'KIT_TOP_LEVEL_SCOPE')
 root=KIT+'/xuanjun-p2-package'
 manifest_raw=read(root+'/deploy/integration-manifest.json')
 need(sha(manifest_raw)==MANIFEST,'KIT_RUNTIME_MANIFEST')
 runtime=json.loads(manifest_raw.decode())
 need(len(runtime['files'])==102,'KIT_RUNTIME_COUNT')
 for name,wanted in runtime['files'].items():
  need(not name.startswith('/') and '..' not in name.split('/'),'KIT_RUNTIME_PATH')
  need(sha(read(root+'/'+name))==wanted,'KIT_RUNTIME_FILE')
 # No unverified importable files or bytecode may sit beside the staged sources.
 allowed=set(runtime['files'])|{'deploy/integration-manifest.json','P2_PACKAGE_PROVENANCE.json','tools/p2-package-freeze.py'}
 seen=set()
 def error(e):raise e
 for parent,dirs,files in os.walk(root,followlinks=False,onerror=error):
  for name in dirs:
   p=os.path.join(parent,name);info=os.lstat(p)
   need(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and info.st_gid==0 and not info.st_mode&0o022,'KIT_RUNTIME_DIRECTORY')
  for name in files:seen.add(os.path.relpath(os.path.join(parent,name),root))
 need(seen==allowed,'KIT_RUNTIME_EXTRA_OR_MISSING')
 return root

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--kit-manifest-sha256',required=True)
 parser.add_argument('--operation',required=True,choices=('verify-only','test-only','resume'))
 parser.add_argument('--affected-only',action='store_true')
 parser.add_argument('--review-id',type=int);parser.add_argument('--review-body-sha256');parser.add_argument('--snapshot-sha256')
 args=parser.parse_args()
 need(sys.flags.isolated and sys.dont_write_bytecode,'KIT_REQUIRE_ISOLATED_NO_BYTECODE')
 need(not args.affected_only or args.operation=='test-only','AFFECTED_SCOPE_ONLY_FOR_TESTS')
 root=verify_kit(args.kit_manifest_sha256)
 sys.path.insert(0,root+'/stage1');sys.path.insert(0,KIT+'/helpers');sys.path.insert(0,KIT)
 if args.operation=='test-only':
  need(args.review_id is None and args.review_body_sha256 is None and args.snapshot_sha256 is None,'TEST_ONLY_NO_APPROVAL_ARGUMENTS')
  import unittest
  os.environ.update(P2_SOURCE_ROOT=root,P2_NEW_ROOT=root,P2_ORIGINAL_ROOT=os.path.dirname(KIT)+'/xuanjun-p2-package',
                    P2_FIXES_ROOT=root+'/stage1',P2_PLAN_PATH=os.path.dirname(KIT)+'/protected-core-install-plan.json',
                    P2_REVIEWED_HELPERS=KIT+'/helpers',P2_ENTRY_PATH=os.path.abspath(__file__))
  os.environ.pop('P2_OBSERVATION_PATH',None)
  if args.affected_only:
   suite=unittest.TestSuite()
   for pattern in ('test_epoch5_bootstrap_rebind.py','test_epoch5_retained_state.py','test_epoch5_host_preflight.py','test_epoch5_plan.py','test_epoch5_host_driver.py','test_epoch5_recovery_entry.py'):
    suite.addTests(unittest.defaultTestLoader.discover(KIT+'/tests',pattern=pattern))
  else:suite=unittest.defaultTestLoader.discover(KIT+'/tests',pattern='test_*.py')
  result=unittest.TextTestRunner(verbosity=2).run(suite)
  print(json.dumps({'operation':'test-only','affected_only':args.affected_only,'tests':result.testsRun,'success':result.wasSuccessful(),
                    'production_resume':'NOT_EXECUTED','kit_manifest_sha256':args.kit_manifest_sha256},sort_keys=True))
  return 0 if result.wasSuccessful() else 1
 from epoch5_plan import compile_plan,canonical
 from epoch5_host_preflight import load_reviewed_scanner
 from epoch5_host_driver import HostDriver
 from epoch5_recovery_sequence import resume_once,RecoveryHold
 scanner=load_reviewed_scanner(KIT+'/helpers/recover_exact_hold.py')
 original=read(os.path.dirname(KIT)+'/protected-core-install-plan.json')
 plan=compile_plan(original,os.path.dirname(KIT)+'/xuanjun-p2-package',root)
 driver=HostDriver(scanner,args.kit_manifest_sha256,args.snapshot_sha256,args.review_body_sha256,
                   KIT+'/helpers/complete_install_executor.py')
 if args.operation=='verify-only':
  need(args.review_id is None and args.review_body_sha256 is None and args.snapshot_sha256 is None,'VERIFY_ONLY_NO_APPROVAL_ARGUMENTS')
  with driver.install_lock():evidence=driver.preflight(plan)
  print(json.dumps({'operation':'verify-only','plan_sha256':sha(canonical(plan)),
                    'snapshot_sha256':sha(canonical(evidence)),'kit_manifest_sha256':args.kit_manifest_sha256,
                    'epoch':5,'production_resume':'NOT_EXECUTED','install_admission':'NOT_GRANTED'},sort_keys=True))
  return 0
 need(args.review_id is not None and all(isinstance(v,str) and SHA.fullmatch(v)
      for v in (args.snapshot_sha256,args.review_body_sha256)),'RESUME_EXACT_APPROVAL_REQUIRED')
 try:result=resume_once(driver,plan,args.review_id)
 except RecoveryHold as error:
  print(json.dumps({'stage':'HOLD','reason':str(error),'automatic_retry':False,
                    'receipt':driver.journal.path,'production_acceptance':'PENDING'},sort_keys=True));return 1
 print(json.dumps({'stage':result['stage'],'receipt':driver.journal.path,
                   'production_acceptance':'PENDING','automatic_retry':False},sort_keys=True));return 0
if __name__=='__main__':sys.exit(main())
