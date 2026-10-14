#!/usr/bin/env python3
"""Data-only review aid. Never extracts files or executes packaged Python.
Reviewer must inspect this aid and run it independently. Its output alone is
not a release approval or verification of the private plan/production effects.
"""
import argparse,base64,gzip,hashlib,io,json,pathlib,re,tarfile
ARCHIVE='7e3228b293d0737d27a3f3fca57385f5b6c5628cfddf6488ce1c17c1017d619f'
KIT='1e13f9e1b6c2fddc135c314fbfb4c6f2b687466ef01208321116a9de10a3c71c'
ENTRY='5c494fe7b5c8737a972d6e012e76a74d17b005a978462a6b3ab9b3cb8daa2848'
RUNTIME='338e488c4203e23d6375726ec8067af815c2d0ec9ee74adc6925f8ef49de9c09'
OLD='9bb1d7ae186e43b4ea9fa720f7368475af3979d225bee830db4ac90b5083b1e3'
FREEZER='f1fe5dc3e199fe891a89969c07612304803ee453ee79e165815eab776eb6bb8e'
TREE='552839cc0f55660ffe3d982c571e2c37b83763cd'
PREFIX='epoch3-recovery-candidate'
REPO_PREFIX='evidence/p2-install-preparation-20261013/'
HELPERS=set(('epoch3_approval.py','epoch3_plan.py','epoch3_host_driver.py',
'epoch3_host_preflight.py','epoch3_service_containment.py','epoch3_install_lock.py',
'epoch3_native_binding.py','epoch3_attempt_journal.py','epoch3_preserve.py',
'epoch3_retained_runtime.py','epoch3_retained_state.py','epoch3_activation_rebind.py',
'epoch3_recovery_sequence.py','inspect_epoch3.py','verify_retained_publisher.py',
'prepare_epoch3_bindings.py','build_epoch3_runtime.py','recover_exact_hold.py','complete_install_executor.py'))
REPAIRS={'stage1/p2_fixed_host_runtime.py':'83ca91a597c3220c40a4de37c8af211463dba13eb36eac55a8802c12d5a36ac2',
'stage1/p2_tls_lifecycle.py':'3ce2c341f4cf9dfc96014446f39dc63a005a1e97122fa310a1d6d3e6c3c264b7'}
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
 need(len(raw)==254327 and sha(raw)==ARCHIVE,'ARCHIVE_BYTES')
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
 need(set(kit['helper_files'])==HELPERS and len(kit['test_files'])==17,'HELPER_TEST_SCOPE')
 need(kit['entry_sha256']==ENTRY and sha(files['epoch3_recovery_entry.py'])==ENTRY,'ENTRY_HASH')
 need(kit['runtime_manifest_sha256']==RUNTIME,'RUNTIME_BINDING')
 expected={'epoch3_recovery_entry.py','recovery-kit-manifest.json'}
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
 need(provenance['source_commit']=='1a35f744224a64d73128196f6212195d15a9d0a7' and provenance['source_tree']=='fa23b50843e4fc579348f403322dc3224c8ff78e' and provenance['verifier_sha256']==FREEZER,'PROVENANCE_SOURCE')
 result={'archive_sha256':ARCHIVE,'archive_bytes':len(raw),'regular_files':len(files),'directories':len(dirs),'helpers_verified':19,'test_modules_verified':17,'runtime_files_verified':102,'manifest_entry_inventory':'PASS','package_bytes_against_pinned_hashes':'PASS','repository_blob_comparison':'NOT_PROVIDED','old100_runtime_comparison':'NOT_PROVIDED','private_plan_and_rendered24':'NOT_RUN','release_approval':'NOT_GRANTED','production_effects':'NOT_RUN'}
 if tree is not None:
  need(tree.get('truncated') is False and tree['sha']==TREE,'REPOSITORY_TREE_BINDING')
  refs={x['path']:x for x in tree['tree']}
  for path in [n for n in files if n.startswith(('helpers/','tests/'))]+['epoch3_recovery_entry.py']:
   reference=refs[REPO_PREFIX+path.split('/')[-1]]
   need(reference['type']=='blob' and reference['mode']=='100644' and reference['sha']==blob(files[path]),'COMMITTED_SOURCE_MISMATCH:'+path)
  result['repository_blob_comparison']='PASS_19_HELPERS_17_TESTS_ENTRY'
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
