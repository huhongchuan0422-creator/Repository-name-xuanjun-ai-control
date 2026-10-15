"""Bound r6 continuation CI checkpoint. Exact checkout; no host or network effects."""
import hashlib,io,json,os,pathlib,re,signal,stat,subprocess,sys,tempfile,types,unittest
PREFIX='evidence/p2-epoch7-access-repair-20261014/owner-diagnostic-r6/'
PINS_BOUND=True
SOURCE='0c8a0f2a97da0c3f00f53659cd6ef7fc7d4ec3ba'
TREE='7d0f402b495b1398637c86463d9c10b4d4559d1f'
PUBLICATION='1b7d382acc9e78d907b42f20d39b74b913e098f4'
ARCHIVE_SHA='600dc31aaf639aee875be1a075c7b544b9c8c5210fee24013ce614bc69ad5a83'
MANIFEST_SHA='70c76e30ae8390963f345813f87267bf1d2f024bc01031c8023733c84aa571cc'
ARCHIVE_SIZE=1032979
KIT_SOURCE_FILES=249
ENTRY_SHA='c56ba6d8281eeb1ecc062875a7f13defc223f6d5dd073a4490d1602b8cf1d3a5'
EXTRACTOR_SHA='e7977f5b849489befff4f782f35023f9267dd49a20b9b3e5f052eeb83758875d'
EXTRACTOR_SIZE=9582
ARCHIVE_PATH='evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-0c8a0f2a.tar.gz'
EXPECTED_TEST_COUNT=61
EXTRACTOR_PATH='evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tools/extract_epoch7_kit.py'
PIN_NAMES=('SOURCE','TREE','PUBLICATION','ARCHIVE_SHA','MANIFEST_SHA','ARCHIVE_SIZE','KIT_SOURCE_FILES','ENTRY_SHA','EXTRACTOR_SHA','EXTRACTOR_SIZE','ARCHIVE_PATH')

def need(value,label):
    if not value:raise ValueError(label)


def git(root,args):
    return subprocess.check_output(['/usr/bin/git','-C',str(root)]+args,timeout=15)


def verified_path(root,head,relative,maximum=1048576):
    need(type(maximum) is int and 0<maximum<=33554432,'SOURCE_SIZE_BOUND')
    path=root/relative
    need(path.resolve()==path,'SOURCE_PATH_ALIAS')
    fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        first=os.fstat(stream.fileno());need(stat.S_ISREG(first.st_mode) and first.st_nlink==1,'SOURCE_FILE_TYPE')
        raw=stream.read(maximum+1);after=os.fstat(stream.fileno())
    stamp=lambda x:tuple(getattr(x,'st_'+k) for k in ('dev','ino','mode','uid','gid','size','mtime_ns','ctime_ns'))
    need(len(raw)<=maximum and stamp(first)==stamp(after)==stamp(os.lstat(str(path))),'SOURCE_CHANGED_OR_BOUND')
    blob=hashlib.sha1(('blob '+str(len(raw))+'\0').encode()+raw).hexdigest()
    expected=git(root,['rev-parse','--verify',head+':'+relative]).decode('ascii').strip()
    need(blob==expected,'EXACT_HEAD_BLOB_MISMATCH')
    return raw,hashlib.sha256(raw).hexdigest()


def verified_source(root,head,name):
    return verified_path(root,head,PREFIX+name)


def publication_pins():
    need(PINS_BOUND is True,'R6_CI_PUBLICATION_NOT_BOUND')
    for name in ('SOURCE','TREE','PUBLICATION'):
        need(type(globals()[name]) is str and re.fullmatch('[0-9a-f]{40}',globals()[name]),'R6_CI_GIT_PIN')
    for name in ('ARCHIVE_SHA','MANIFEST_SHA','ENTRY_SHA','EXTRACTOR_SHA'):
        need(type(globals()[name]) is str and re.fullmatch('[0-9a-f]{64}',globals()[name]),'R6_CI_SHA_PIN')
    need(type(ARCHIVE_SIZE) is int and 0<ARCHIVE_SIZE<=33554432 and type(EXTRACTOR_SIZE) is int and 0<EXTRACTOR_SIZE<=1048576 and
         type(KIT_SOURCE_FILES) is int and 0<KIT_SOURCE_FILES<=1024,'R6_CI_SIZE_PINS')
    need(type(ARCHIVE_PATH) is str and re.fullmatch(r'evidence/p2-epoch7-access-repair-20261014/artifacts/[A-Za-z0-9_.-]+\.tar\.gz',ARCHIVE_PATH),'R6_CI_ARCHIVE_PATH')


def verify_core_cache(root,head,wrapper):
    """Actual archive and core cache boundary only; no test alias or case load."""
    archive,archive_sha=verified_path(root,head,wrapper.ARCHIVE_PATH,ARCHIVE_SIZE)
    need(archive_sha==ARCHIVE_SHA and len(archive)==ARCHIVE_SIZE,'CORE_ARCHIVE_PIN')
    extractor_raw,extractor_sha=verified_path(root,head,EXTRACTOR_PATH)
    need(extractor_sha==wrapper.EXTRACTOR_SHA and len(extractor_raw)==wrapper.EXTRACTOR_SIZE,'CORE_EXTRACTOR_PIN')
    extractor=types.ModuleType('verified_ci_archive_inspector');extractor.__file__=str(root/EXTRACTOR_PATH)
    exec(compile(extractor_raw,extractor.__file__,'exec',dont_inherit=True),extractor.__dict__)
    files,unused=extractor.inspect_archive(archive,ARCHIVE_SHA,wrapper.ENTRY_SHA,MANIFEST_SHA)
    need(len(files)==KIT_SOURCE_FILES+1,'CORE_ARCHIVE_COUNT')
    entry=types.ModuleType('verified_ci_frozen_entry');entry.__file__=str(root/'__cache_only__/epoch7_recovery_entry.py')
    exec(compile(files['epoch7_recovery_entry.py'],entry.__file__,'exec',dont_inherit=True),entry.__dict__)
    manifest=entry.validate_manifest(entry.decode(files[entry.MANIFEST]))
    cache={name:data for name,data in files.items() if name!=entry.MANIFEST}
    need(len(cache)==KIT_SOURCE_FILES,'CORE_CACHE_COUNT')
    entry.validate_runtime(manifest,cache)
    need(manifest['kit_source_commit']==SOURCE and manifest['kit_source_tree']==TREE,'CORE_SOURCE_PIN')
    kit=entry.VerifiedKit(str(root/'__cache_only__'),manifest,cache,MANIFEST_SHA,raw_manifest=files[entry.MANIFEST])
    before=json.dumps(manifest,sort_keys=True)
    with kit.imports():pass
    need(json.dumps(manifest,sort_keys=True)==before,'CORE_MANIFEST_MUTATION')
    return {'state':'PASS','archive_members':len(files),'cached_files':len(cache),'archive_sha256':archive_sha,
            'test_aliases':'NOT_REQUESTED','uid_fixture':'NOT_IMPORTED_OR_EXECUTED','host_operations':'NOT_RUN'}


def worker():
    publication_pins()
    root=pathlib.Path(__file__).resolve().parents[1]
    head=git(root,['rev-parse','--verify','HEAD']).decode('ascii').strip()
    need(re.fullmatch('[0-9a-f]{40}',head) is not None,'HEAD_FORMAT')
    raw,source_sha=verified_source(root,head,'owner_diagnostic_r6.py')
    test,test_sha=verified_source(root,head,'test_owner_diagnostic_r6.py')
    need('owner_diagnostic_r6' not in sys.modules,'PRELOADED_WRAPPER')
    module=types.ModuleType('owner_diagnostic_r6');module.__file__=str(root/PREFIX/'owner_diagnostic_r6.py')
    sys.modules[module.__name__]=module
    try:
        exec(compile(raw,module.__file__,'exec',dont_inherit=True),module.__dict__)
        need(module.READY is True,'OUTER_NOT_READY');module.publication_gate()
        for key in PIN_NAMES:need(getattr(module,key)==globals()[key],'OUTER_IMMUTABLE_PIN_'+key)
        need(module.PREFIX=='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/','OUTER_REPOSITORY_PIN')
        core=verify_core_cache(root,head,module)
        tests=types.ModuleType('verified_owner_r6_tests');tests.__file__=str(root/PREFIX/'test_owner_diagnostic_r6.py')
        exec(compile(test,tests.__file__,'exec',dont_inherit=True),tests.__dict__)
        suite=unittest.defaultTestLoader.loadTestsFromModule(tests)
        need(suite.countTestCases()==EXPECTED_TEST_COUNT,'EXACT_OUTER_TEST_COUNT')
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        need(result.wasSuccessful() and result.testsRun==EXPECTED_TEST_COUNT and not result.skipped,'OUTER_TEST_FAILURE_OR_SKIP')
        need(git(root,['rev-parse','--verify','HEAD']).decode('ascii').strip()==head,'HEAD_CHANGED')
        need(verified_source(root,head,'owner_diagnostic_r6.py')[0]==raw and verified_source(root,head,'test_owner_diagnostic_r6.py')[0]==test,'SOURCE_CHANGED_AFTER_TEST')
        print(json.dumps({'kind':'EXACT_OWNER_R6_CONTINUATION_MOCKED_CI','head':head,'wrapper_sha256':source_sha,'test_sha256':test_sha,
            'tests':EXPECTED_TEST_COUNT,'core_cache':core,'skipped':0,'success':True,'kit_source':SOURCE,'archive_publication':PUBLICATION,
            'host_operations':'NOT_RUN','production_admission':'NOT_GRANTED'},sort_keys=True))
    finally:sys.modules.pop(module.__name__,None)

class OwnerR6Checkpoint(unittest.TestCase):
    def test_exact_owner_r6_mocked_boundaries(self):
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
            self.assertEqual(code,0,'EXACT_OWNER_R6_MOCKED_CI_FAILED')


if __name__=='__main__':
    if sys.argv[1:]==['--worker']:worker()
    else:unittest.main()
