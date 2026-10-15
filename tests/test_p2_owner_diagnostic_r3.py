"""Exact-checkout mocked r3 diagnostic gate; no network or host effects."""
import hashlib
import io
import json
import os
import pathlib
import re
import signal
import stat
import subprocess
import sys
import tempfile
import types
import unittest

PREFIX='evidence/p2-epoch7-access-repair-20261014/owner-diagnostic-r3/'
SOURCE='460a53e0f702fb416811e785a6ef8d6c39b2d003'
TREE='20f382a534da9f1c39fa2c2c97e7a484917f8aa5'
PUBLICATION='02822b674a7c8a0c9c395cbf5664b3d24bff2516'
ARCHIVE_SHA='c56a11e78914d567f91a94118d676d49f65775161b3c46b16583ece1403c1d85'
MANIFEST_SHA='e6618cf3012bc5edf8f3c9fb9982494dad7d916fbc7adcaeab39ebe0733cc3b8'

def need(value,label):
    if not value:raise ValueError(label)

def git(root,args):
    return subprocess.check_output(['/usr/bin/git','-C',str(root)]+args,timeout=15)

def verified_path(root,head,relative):
    path=root/relative
    need(path.resolve()==path,'SOURCE_PATH_ALIAS')
    fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        first=os.fstat(stream.fileno());need(stat.S_ISREG(first.st_mode) and first.st_nlink==1,'SOURCE_FILE_TYPE')
        raw=stream.read(1048577);after=os.fstat(stream.fileno())
    stamp=lambda x:tuple(getattr(x,'st_'+k) for k in ('dev','ino','mode','uid','gid','size','mtime_ns','ctime_ns'))
    need(len(raw)<=1048576 and stamp(first)==stamp(after)==stamp(os.lstat(str(path))),'SOURCE_CHANGED_OR_BOUND')
    blob=hashlib.sha1(('blob '+str(len(raw))+'\0').encode()+raw).hexdigest()
    expected=git(root,['rev-parse','--verify',head+':'+relative]).decode('ascii').strip()
    need(blob==expected,'EXACT_HEAD_BLOB_MISMATCH')
    return raw,hashlib.sha256(raw).hexdigest()

def verified_source(root,head,name):
    return verified_path(root,head,PREFIX+name)

def verify_uk_case_import(root,head,wrapper):
    """Actual frozen-kit loader, selecting only; never run the UID-specific case."""
    archive,archive_sha=verified_path(root,head,wrapper.ARCHIVE_PATH)
    need(archive_sha==ARCHIVE_SHA and len(archive)==1015797,'UK_IMPORT_ARCHIVE_PIN')
    extractor_path=PREFIX+'extract_epoch7_kit_r3.py'
    extractor_raw,extractor_sha=verified_path(root,head,extractor_path)
    need(extractor_sha==wrapper.EXTRACTOR_SHA and len(extractor_raw)==wrapper.EXTRACTOR_SIZE,'UK_IMPORT_EXTRACTOR_PIN')
    extractor=types.ModuleType('verified_ci_archive_inspector')
    extractor.__file__=str(root/extractor_path)
    exec(compile(extractor_raw,extractor.__file__,'exec',dont_inherit=True),extractor.__dict__)
    files,unused=extractor.inspect_archive(archive,ARCHIVE_SHA,wrapper.ENTRY_SHA,MANIFEST_SHA)
    need(len(files)==248,'UK_IMPORT_ARCHIVE_COUNT')
    entry=types.ModuleType('verified_ci_frozen_entry')
    entry.__file__=str(root/'__cache_only__/epoch7_recovery_entry.py')
    exec(compile(files['epoch7_recovery_entry.py'],entry.__file__,'exec',dont_inherit=True),entry.__dict__)
    manifest=entry.validate_manifest(entry.decode(files[entry.MANIFEST]))
    cache={name:data for name,data in files.items() if name!=entry.MANIFEST}
    entry.validate_runtime(manifest,cache)
    need(manifest['kit_source_commit']==SOURCE and manifest['kit_source_tree']==TREE,'UK_IMPORT_SOURCE_PIN')
    kit=entry.VerifiedKit(str(root/'__cache_only__'),manifest,cache,MANIFEST_SHA,raw_manifest=files[entry.MANIFEST])
    before=json.dumps(manifest,sort_keys=True)
    with kit.imports(wrapper.exact_uk_imports(kit)):
        suite=wrapper.load_exact_uid_suite()
        cases=list(suite)
        need(len(cases)==1 and cases[0].id()==wrapper.UK_CASE,'UK_IMPORT_EXACT_SELECTION')
    need(json.dumps(manifest,sort_keys=True)==before,'UK_IMPORT_MANIFEST_MUTATION')
    return {'case':wrapper.UK_CASE,'selection':'PASS','execution':'NOT_RUN','archive_sha256':archive_sha}

def worker():
    root=pathlib.Path(__file__).resolve().parents[1]
    head=git(root,['rev-parse','--verify','HEAD']).decode('ascii').strip()
    need(re.fullmatch('[0-9a-f]{40}',head) is not None,'HEAD_FORMAT')
    raw,source_sha=verified_source(root,head,'owner_diagnostic_r3.py')
    test,test_sha=verified_source(root,head,'test_owner_diagnostic_r3.py')
    need('owner_diagnostic_r3' not in sys.modules,'PRELOADED_WRAPPER')
    module=types.ModuleType('owner_diagnostic_r3');module.__file__=str(root/PREFIX/'owner_diagnostic_r3.py')
    sys.modules[module.__name__]=module
    try:
        exec(compile(raw,module.__file__,'exec',dont_inherit=True),module.__dict__)
        need(module.READY is True,'OUTER_NOT_READY')
        module.publication_gate()
        for key,expected in [('SOURCE',SOURCE),('TREE',TREE),('PUBLICATION',PUBLICATION),('ARCHIVE_SHA',ARCHIVE_SHA),('MANIFEST_SHA',MANIFEST_SHA),('ARCHIVE_SIZE',1015797),('KIT_SOURCE_FILES',247),('ENTRY_SHA','24ad01d9b216e2a2771180c169c0d8d858173f6dee2a6b0cf9e35f9ad97108d4'),('EXTRACTOR_SHA','87122167bf6c63f5f96452369d6e3d7d59c5254fade9a2ed52d3e959d8538261'),('EXTRACTOR_SIZE',9582),('ARCHIVE_PATH','evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-460a53e0.tar.gz'),('PREFIX','https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/')]:
            need(getattr(module,key)==expected,'OUTER_IMMUTABLE_PIN_'+key)
        selected=verify_uk_case_import(root,head,module)
        tests=types.ModuleType('verified_owner_r3_tests');tests.__file__=str(root/PREFIX/'test_owner_diagnostic_r3.py')
        exec(compile(test,tests.__file__,'exec',dont_inherit=True),tests.__dict__)
        suite=unittest.defaultTestLoader.loadTestsFromModule(tests)
        need(suite.countTestCases()==36,'EXACT_OUTER_TEST_COUNT')
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        need(result.wasSuccessful() and result.testsRun==36 and not result.skipped,'OUTER_TEST_FAILURE_OR_SKIP')
        need(git(root,['rev-parse','--verify','HEAD']).decode('ascii').strip()==head,'HEAD_CHANGED')
        need(verified_source(root,head,'owner_diagnostic_r3.py')[0]==raw and verified_source(root,head,'test_owner_diagnostic_r3.py')[0]==test,'SOURCE_CHANGED_AFTER_TEST')
        print(json.dumps({'kind':'EXACT_OWNER_R3_MOCKED_CI','head':head,'wrapper_sha256':source_sha,'test_sha256':test_sha,'tests':36,'uk_case_import':selected,'skipped':0,'success':True,'kit_source':SOURCE,'archive_publication':PUBLICATION,'host_operations':'NOT_RUN','production_admission':'NOT_GRANTED'},sort_keys=True))
    finally:sys.modules.pop(module.__name__,None)

class OwnerR3Checkpoint(unittest.TestCase):
    def test_exact_owner_r3_mocked_boundaries(self):
        with tempfile.TemporaryFile() as log:
            child=subprocess.Popen([sys.executable,'-I','-B','-S',str(pathlib.Path(__file__).resolve()),'--worker'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                code=child.wait(timeout=90)
            except BaseException:
                if child.returncode is None:
                    try:os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    finally:child.wait(timeout=5)
                raise
            finally:
                log.seek(0,os.SEEK_END);size=log.tell();log.seek(max(0,size-65536));print(log.read(65536).decode('utf-8','replace'))
            self.assertEqual(code,0,'EXACT_OWNER_R3_MOCKED_CI_FAILED')

if __name__=='__main__':
    if sys.argv[1:]==['--worker']:worker()
    else:unittest.main()
