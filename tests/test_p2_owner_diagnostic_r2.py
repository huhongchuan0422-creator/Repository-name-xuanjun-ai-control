"""Exact-checkout mocked r2 diagnostic gate; no network or host effects."""
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

PREFIX='evidence/p2-epoch7-access-repair-20261014/owner-diagnostic-r2/'
SOURCE='4798cda235b24b31a18b57d3957fbc0d396d634b'
TREE='f050e9e6810decb7a4f62a14f3a5679908451c1f'
PUBLICATION='965c0f8bd7e5145dc353a9145388c733e0660ab5'
ARCHIVE_SHA='7c67ef5e1e2d756898b982bcce625fd9168e4c3d93c3ed2153d4ed8fd8e37d71'
MANIFEST_SHA='560d8bf9bae026ffd64b4b0fc43e87216a177070f2a0c948489c884a1296c8b3'

def need(value,label):
    if not value:raise ValueError(label)

def git(root,args):
    return subprocess.check_output(['/usr/bin/git','-C',str(root)]+args,timeout=15)

def verified_source(root,head,name):
    relative=PREFIX+name;path=root/relative
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

def worker():
    root=pathlib.Path(__file__).resolve().parents[1]
    head=git(root,['rev-parse','--verify','HEAD']).decode('ascii').strip()
    need(re.fullmatch('[0-9a-f]{40}',head) is not None,'HEAD_FORMAT')
    raw,source_sha=verified_source(root,head,'owner_diagnostic_r2.py')
    test,test_sha=verified_source(root,head,'test_owner_diagnostic_r2.py')
    need('owner_diagnostic_r2' not in sys.modules,'PRELOADED_WRAPPER')
    module=types.ModuleType('owner_diagnostic_r2');module.__file__=str(root/PREFIX/'owner_diagnostic_r2.py')
    sys.modules[module.__name__]=module
    try:
        exec(compile(raw,module.__file__,'exec',dont_inherit=True),module.__dict__)
        need(module.READY is True,'OUTER_NOT_READY')
        module.publication_gate()
        for key,expected in [('SOURCE',SOURCE),('TREE',TREE),('PUBLICATION',PUBLICATION),('ARCHIVE_SHA',ARCHIVE_SHA),('MANIFEST_SHA',MANIFEST_SHA),('ARCHIVE_SIZE',1009595),('KIT_SOURCE_FILES',245),('ENTRY_SHA','999803b505bbebdef8a2f3303954f8e773cdf6bb10f9c2855563d36b1f759dd2'),('EXTRACTOR_SHA','d8f1942bc82bb001d8282192e87b9b71e3b89c2f374c6c69d49589b025293b87'),('EXTRACTOR_SIZE',9582),('ARCHIVE_PATH','evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-4798cda2.tar.gz'),('PREFIX','https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/')]:
            need(getattr(module,key)==expected,'OUTER_IMMUTABLE_PIN_'+key)
        tests=types.ModuleType('verified_owner_r2_tests');tests.__file__=str(root/PREFIX/'test_owner_diagnostic_r2.py')
        exec(compile(test,tests.__file__,'exec',dont_inherit=True),tests.__dict__)
        suite=unittest.defaultTestLoader.loadTestsFromModule(tests)
        need(suite.countTestCases()==25,'EXACT_OUTER_TEST_COUNT')
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        need(result.wasSuccessful() and result.testsRun==25 and not result.skipped,'OUTER_TEST_FAILURE_OR_SKIP')
        need(git(root,['rev-parse','--verify','HEAD']).decode('ascii').strip()==head,'HEAD_CHANGED')
        need(verified_source(root,head,'owner_diagnostic_r2.py')[0]==raw and verified_source(root,head,'test_owner_diagnostic_r2.py')[0]==test,'SOURCE_CHANGED_AFTER_TEST')
        print(json.dumps({'kind':'EXACT_OWNER_R2_MOCKED_CI','head':head,'wrapper_sha256':source_sha,'test_sha256':test_sha,'tests':25,'skipped':0,'success':True,'kit_source':SOURCE,'archive_publication':PUBLICATION,'host_operations':'NOT_RUN','production_admission':'NOT_GRANTED'},sort_keys=True))
    finally:sys.modules.pop(module.__name__,None)

class OwnerR2Checkpoint(unittest.TestCase):
    def test_exact_owner_r2_mocked_boundaries(self):
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
            self.assertEqual(code,0,'EXACT_OWNER_R2_MOCKED_CI_FAILED')

if __name__=='__main__':
    if sys.argv[1:]==['--worker']:worker()
    else:unittest.main()
