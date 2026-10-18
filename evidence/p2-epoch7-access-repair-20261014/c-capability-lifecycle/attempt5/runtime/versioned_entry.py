"""Strict, cached import scope for the separate Attempt5 Kit, Python 3.6.

Caller must independently pin this loader and the outer manifest SHA. This API
only verifies/imports source; it does not discover credentials, issue permits,
assemble a production Driver from guessed inputs, Prepare or install anything.
"""
import contextlib
import hashlib
import json
import os
import re
import sys
import types

LEGACY_ENTRY_SHA='21a982161bc4cb8ffd7e67e4b9a8e24bf23916df6d78c3dd43376af3cfb34890'
MODULES={'attempt_ledger':'attempt5/original/attempt_ledger.py',
         'production_boundary':'attempt5/original/production_boundary.py',
         'receipt_provider':'attempt5/runtime/receipt_provider.py',
         'authority_store':'attempt5/runtime/authority_store.py',
         'issuer_service':'attempt5/runtime/issuer_service.py',
         'authorization':'attempt5/runtime/authorization.py',
         'native_state':'attempt5/runtime/native_state.py',
         'permit_cycle':'attempt5/runtime/permit_cycle.py',
         'approved_config':'attempt5/runtime/approved_config.py',
         'native_recovery':'attempt5/runtime/native_recovery.py'}
def need(ok, code):
    if not ok:raise ValueError('P2_ATTEMPT5_KIT_'+code)
def sha(raw):return hashlib.sha256(raw).hexdigest()

@contextlib.contextmanager
def imports(root, manifest_sha256):
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'ISOLATED_INTERPRETER_REQUIRED')
    need(type(root) is str and os.path.isabs(root) and os.path.normpath(root)==root, 'ROOT')
    need(type(manifest_sha256) is str and re.fullmatch('[0-9a-f]{64}',manifest_sha256), 'MANIFEST_PIN')
    path=root+'/legacy/epoch7_recovery_entry.py'
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:raw=os.read(fd,65537)
    finally:os.close(fd)
    need(sha(raw)==LEGACY_ENTRY_SHA,'BOOTSTRAP_ENTRY')
    entry=types.ModuleType('_attempt5_legacy_bootstrap');entry.__file__=path
    exec(compile(raw,path,'exec'),entry.__dict__)
    cache={}
    with entry.DescriptorTree(root) as tree:
        raw=tree.read('attempt5-manifest.json')
        need(sha(raw)==manifest_sha256,'MANIFEST_SHA')
        manifest=entry.decode(raw)
        need(set(manifest)=={'schema','kind','source_commit','source_tree','legacy_kit_sha256',
             'inherited_files','files','max_attempts','production_ready','install_permit','trusted_provider','release'} and
             manifest['schema']==1 and manifest['kind']=='P2_ATTEMPT5_CANDIDATE_V1' and
             manifest['max_attempts']==5 and manifest['production_ready'] is False and
             manifest['install_permit']=='NOT_ISSUED' and manifest['release']=='HOLD', 'VERSION')
        for key in ('source_commit','source_tree'):
            need(type(manifest[key]) is str and re.fullmatch('[0-9a-f]{40}',manifest[key]),'SOURCE_IDENTITY')
        files=manifest['files'];need(type(files) is dict and len(files)<1024,'FILES')
        actual_files, actual_dirs=tree.inventory()
        need(actual_files==set(files)|{'attempt5-manifest.json'} and
             actual_dirs==entry.directories(actual_files),'STRICT_INVENTORY')
        for name,pin in files.items():
            entry.relative(name);need(type(pin) is str and re.fullmatch('[0-9a-f]{64}',pin),'FILE_PIN')
            body=tree.read(name);need(sha(body)==pin,'FILE_SHA');cache[name]=body
        need(len(manifest['inherited_files'])==257 and all(
             name.startswith('legacy/') and files.get(name)==pin
             for name,pin in manifest['inherited_files'].items()),'INHERITED_CLOSURE')
        old_manifest=entry.validate_manifest(entry.decode(cache['legacy/recovery-kit-manifest.json']))
        need(set(manifest['inherited_files'])=={'legacy/'+name for name in old_manifest['files']}|
             {'legacy/recovery-kit-manifest.json'},'LEGACY_CLOSURE')
        need(all(sha(cache['legacy/'+name])==pin for name,pin in old_manifest['files'].items()),'LEGACY_SHA')
        tree.recheck()
    modules={name:'legacy/'+path for name,path in old_manifest['modules'].items()}
    need(not set(modules)&set(MODULES),'MODULE_COLLISION');modules.update(MODULES)
    need(not set(modules)&set(sys.modules),'PRELOADED_CANDIDATE')
    finder=entry.CachedSources(root,cache,modules,tuple(sys.path))
    sys.meta_path.insert(0,finder)
    try:
        yield {'source_commit':manifest['source_commit'],'source_tree':manifest['source_tree'],
               'manifest_sha256':manifest_sha256,'production_authorized':False}
    finally:
        sys.meta_path.remove(finder)
        for name in modules:sys.modules.pop(name,None)
