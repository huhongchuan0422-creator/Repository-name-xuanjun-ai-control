#!/usr/bin/env python3
"""Data-only review aid. Never extracts files or executes packaged Python.
Reviewer must inspect this aid and run it independently. Its output alone is
not a release approval or verification of the private plan/production effects.
"""
import argparse,base64,gzip,hashlib,io,json,pathlib,re,tarfile
ARCHIVE='8b69ec24d3f55b7010cfd98c2982b7b55a4d1b5ce27f3bb2d3c012313ab8d075'
KIT='12ec5e711b4a7de865e44323b887fefbac6cc7954d13609e58b7137bd34374e1'
ENTRY='c88330b7d7a685a049e43e29cd0413336255a34df8db4ae46f6fb4cc1acc24e6'
RUNTIME='153653ebc48d6b20680e513402dad077d50dce953ab3d4b7cc1748bcff0f64e7'
OLD='9bb1d7ae186e43b4ea9fa720f7368475af3979d225bee830db4ac90b5083b1e3'
FREEZER='f1fe5dc3e199fe891a89969c07612304803ee453ee79e165815eab776eb6bb8e'
TREE='c3ac139fb3c69e6826c41a10abc847d999b09f07'
PREFIX='epoch5-recovery-candidate-v4'
REPO_PREFIX='evidence/p2-epoch5-recovery-20261014/'
HELPERS=set(('build_epoch5_runtime.py', 'complete_install_executor.py', 'epoch3_install_lock.py', 'epoch3_preserve.py', 'epoch3_service_containment.py', 'epoch5_activation_rebind.py', 'epoch5_approval.py', 'epoch5_attempt_journal.py', 'epoch5_host_driver.py', 'epoch5_host_preflight.py', 'epoch5_native_binding.py', 'epoch5_plan.py', 'epoch5_recovery_sequence.py', 'epoch5_retained_runtime.py', 'epoch5_retained_state.py', 'epoch5_retained_tls.py', 'inspect_epoch3.py', 'inspect_epoch5.py', 'observe_epoch5.py', 'prepare_epoch5_bindings.py', 'recover_exact_hold.py', 'verify_retained_publisher.py'))
REPAIRS={'stage1/p2_fixed_host_runtime.py':'83ca91a597c3220c40a4de37c8af211463dba13eb36eac55a8802c12d5a36ac2',
'stage1/p2_tls_lifecycle.py':'948ea9920d5a6785aad2ebd0cbc7384c11d93b42cf97b4014a79f15f58d554f1'}
def need(value,label):
 if not value:raise ValueError(label)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pairs(items):
 d={}
 for k,v in items:need(k not in d,'DUPLICATE_JSON');d[k]=v
 return d
def parse(raw):return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs)
def relative(name):return isinstance(name,str) and name and not name.startswith('/') and '\\' not in name and all(x not in ('','.','..') for x in name.split('/'))
def blob(raw):return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
def verify(raw,tree=None,old_manifest=None):
 need(len(raw)==267336 and sha(raw)==ARCHIVE,'ARCHIVE_BYTES')
 with gzip.GzipFile(fileobj=io.BytesIO(raw),mode='rb') as compressed:data=compressed.read(8388609)
 need(len(data)<=8388608,'TAR_BOUND')
 files={};dirs=set();seen=set();total=0
 with tarfile.open(fileobj=io.BytesIO(data),mode='r:') as archive:
  for member in archive:
   name=member.name;need(relative(name) and name.split('/')[0]==PREFIX,'MEMBER_PATH')
   need(name not in seen and len(seen)<256,'DUPLICATE_OR_EXCESS_MEMBERS');seen.add(name)
   need(member.uid==0 and member.gid==0 and (member.isfile() or member.isdir()),'MEMBER_OWNER_TYPE')
   expected_mode=0o700 if name in (PREFIX,PREFIX+'/helpers',PREFIX+'/tests') else 0o755
   if member.isdir():need(member.mode==expected_mode and member.size==0,'DIRECTORY_MODE');dirs.add(name);continue
   need(member.mode==0o444 and 0<=member.size<=2097152,'FILE_MODE_SIZE')
   total+=member.size;need(total<=8388608,'MEMBER_TOTAL')
   payload=archive.extractfile(member).read(2097153);need(len(payload)==member.size,'MEMBER_LENGTH')
   files[name[len(PREFIX)+1:]]=payload
 need(sha(files['recovery-kit-manifest.json'])==KIT,'KIT_MANIFEST_HASH')
 kit=parse(files['recovery-kit-manifest.json']);need(set(kit)=={'schema','runtime_manifest_sha256','helper_files','entry_sha256','test_files'} and type(kit['schema']) is int and kit['schema']==1,'KIT_SCHEMA')
 need(set(kit['helper_files'])==HELPERS and len(kit['test_files'])==19,'HELPER_TEST_SCOPE')
 need(kit['entry_sha256']==ENTRY and sha(files['epoch5_recovery_entry.py'])==ENTRY,'ENTRY_HASH')
 need(kit['runtime_manifest_sha256']==RUNTIME,'RUNTIME_BINDING')
 expected={'epoch5_recovery_entry.py','recovery-kit-manifest.json'}
 for folder,key in (('helpers','helper_files'),('tests','test_files')):
  for name,wanted in kit[key].items():
   need(relative(name) and '/' not in name,'IMPORT_NAME')
   path=folder+'/'+name;need(sha(files[path])==wanted,'HELPER_OR_TEST_HASH:'+path);expected.add(path)
 root='xuanjun-p2-package/'
 manifest_raw=files[root+'deploy/integration-manifest.json'];need(sha(manifest_raw)==RUNTIME,'RUNTIME_MANIFEST_HASH')
 manifest=parse(manifest_raw);need(len(manifest['files'])==102,'RUNTIME_COUNT')
 for name,wanted in manifest['files'].items():
  need(relative(name),'RUNTIME_PATH');path=root+name
  need(sha(files[path])==wanted,'RUNTIME_HASH:'+name);expected.add(path)
 extras={'deploy/integration-manifest.json','P2_PACKAGE_PROVENANCE.json','tools/p2-package-freeze.py'}
 expected.update(root+n for n in extras)
 need(set(files)==expected,'FULL_FILE_INVENTORY')
 expected_dirs={PREFIX}
 for path in expected:
  parts=(PREFIX+'/'+path).split('/')
  expected_dirs.update('/'.join(parts[:i]) for i in range(1,len(parts)))
 need(dirs==expected_dirs,'FULL_DIRECTORY_INVENTORY')
 need(sha(files[root+'tools/p2-package-freeze.py'])==FREEZER,'FREEZER_HASH')
 provenance=parse(files[root+'P2_PACKAGE_PROVENANCE.json'])
 need(provenance['schema']==2 and provenance['runtime_manifest_sha256']==RUNTIME and provenance['runtime_files']==manifest['files'],'PROVENANCE_RUNTIME')
 need(provenance['source_commit']=='e058a82cf20acde95dd591dd3c95eaf4d4e7aa82' and provenance['source_tree']=='a27d226d96878e8230f4d4d28d93141d0f4900de' and provenance['verifier_sha256']==FREEZER,'PROVENANCE_SOURCE')
 result={'archive_sha256':ARCHIVE,'archive_bytes':len(raw),'regular_files':len(files),'directories':len(dirs),'helpers_verified':22,'test_modules_verified':19,'runtime_files_verified':102,'manifest_entry_inventory':'PASS','package_bytes_against_pinned_hashes':'PASS','repository_blob_comparison':'NOT_PROVIDED','old100_runtime_comparison':'NOT_PROVIDED','private_plan_and_rendered24':'NOT_RUN','release_approval':'NOT_GRANTED','production_effects':'NOT_RUN'}
 if tree is not None:
  need(tree.get('truncated') is False and tree['sha']==TREE,'REPOSITORY_TREE_BINDING')
  refs={x['path']:x for x in tree['tree']}
  for path in [n for n in files if n.startswith(('helpers/','tests/'))]+['epoch5_recovery_entry.py']:
   reference=refs[REPO_PREFIX+path.split('/')[-1]]
   need(reference['type']=='blob' and reference['mode']=='100644' and reference['sha']==blob(files[path]),'COMMITTED_SOURCE_MISMATCH:'+path)
  result['repository_blob_comparison']='PASS_22_HELPERS_19_TESTS_ENTRY'
 if old_manifest is not None:
  need(sha(old_manifest)==OLD,'OLD_MANIFEST_HASH');old=parse(old_manifest)
  need(set(old['files'])==set(manifest['files']),'OLD_NEW_SCOPE')
  changed={n for n in old['files'] if old['files'][n]!=manifest['files'][n]}
  need(changed==set(REPAIRS) and all(manifest['files'][n]==v for n,v in REPAIRS.items()),'EXACT_TWO_RUNTIME_REPAIRS')
  old['files'].update(REPAIRS);need(old==manifest,'UNRELATED_MANIFEST_CHANGE')
  result['old100_runtime_comparison']='PASS_100_UNCHANGED_2_PINNED_REPAIRS'
 return result
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('archive');parser.add_argument('--base64',action='store_true');parser.add_argument('--repository-tree');parser.add_argument('--old-runtime-manifest');args=parser.parse_args()
 raw=pathlib.Path(args.archive).read_bytes()
 if args.base64:raw=base64.b64decode(b''.join(raw.split()),validate=True)
 tree=parse(pathlib.Path(args.repository_tree).read_bytes()) if args.repository_tree else None
 old=pathlib.Path(args.old_runtime_manifest).read_bytes() if args.old_runtime_manifest else None
 print(json.dumps(verify(raw,tree,old),sort_keys=True,indent=2))
