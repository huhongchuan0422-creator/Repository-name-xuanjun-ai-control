"""Bound r7 continuation CI checkpoint. Exact checkout; no host or network effects."""
import hashlib,io,json,os,pathlib,re,signal,stat,subprocess,sys,tempfile,types,unittest
PREFIX='evidence/p2-epoch7-access-repair-20261014/owner-diagnostic-r7/'
PINS_BOUND=True
SOURCE='dc18f73e67818dc59f5acea247dbf05443bde10d'
TREE='860d1a126b3a447c60079e315ebb549fcf5333aa'
PUBLICATION='ec3f0c3ceb1842fc5c0cb5e2f2a5c37792494eac'
ARCHIVE_SHA='e9841797571b3f039af8782b0aa1051c11c4b7938a2287abfd433e394b3d1645'
MANIFEST_SHA='7b926fda92065d9ff981bfeaad490d5568dd5901d2b1089d1f1dfac94eae8bb4'
ARCHIVE_SIZE=1041263
KIT_SOURCE_FILES=252
ENTRY_SHA='1be06802e012b5747f837af02ff8746fec9864ef94715b561f67c39be95e0948'
EXTRACTOR_SHA='eba0e2de223f0e0853968cd2a47f827a0dfe670c437a2071ea82cfd13b36dbf0'
EXTRACTOR_SIZE=9582
ARCHIVE_PATH='evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-dc18f73e.tar.gz'
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
    need(PINS_BOUND is True,'R7_CI_PUBLICATION_NOT_BOUND')
    for name in ('SOURCE','TREE','PUBLICATION'):
        need(type(globals()[name]) is str and re.fullmatch('[0-9a-f]{40}',globals()[name]),'R7_CI_GIT_PIN')
    for name in ('ARCHIVE_SHA','MANIFEST_SHA','ENTRY_SHA','EXTRACTOR_SHA'):
        need(type(globals()[name]) is str and re.fullmatch('[0-9a-f]{64}',globals()[name]),'R7_CI_SHA_PIN')
    need(type(ARCHIVE_SIZE) is int and 0<ARCHIVE_SIZE<=33554432 and type(EXTRACTOR_SIZE) is int and 0<EXTRACTOR_SIZE<=1048576 and
         type(KIT_SOURCE_FILES) is int and 0<KIT_SOURCE_FILES<=1024,'R7_CI_SIZE_PINS')
    need(type(ARCHIVE_PATH) is str and re.fullmatch(r'evidence/p2-epoch7-access-repair-20261014/artifacts/[A-Za-z0-9_.-]+\.tar\.gz',ARCHIVE_PATH),'R7_CI_ARCHIVE_PATH')


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
    raw,source_sha=verified_source(root,head,'owner_diagnostic_r7.py')
    test,test_sha=verified_source(root,head,'test_owner_diagnostic_r7.py')
    need('owner_diagnostic_r7' not in sys.modules,'PRELOADED_WRAPPER')
    module=types.ModuleType('owner_diagnostic_r7');module.__file__=str(root/PREFIX/'owner_diagnostic_r7.py')
    sys.modules[module.__name__]=module
    try:
        exec(compile(raw,module.__file__,'exec',dont_inherit=True),module.__dict__)
        need(module.READY is True,'OUTER_NOT_READY');module.publication_gate()
        for key in PIN_NAMES:need(getattr(module,key)==globals()[key],'OUTER_IMMUTABLE_PIN_'+key)
        need(module.PREFIX=='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/','OUTER_REPOSITORY_PIN')
        core=verify_core_cache(root,head,module)
        tests=types.ModuleType('verified_owner_r7_tests');tests.__file__=str(root/PREFIX/'test_owner_diagnostic_r7.py')
        exec(compile(test,tests.__file__,'exec',dont_inherit=True),tests.__dict__)
        suite=unittest.defaultTestLoader.loadTestsFromModule(tests)
        need(suite.countTestCases()==EXPECTED_TEST_COUNT,'EXACT_OUTER_TEST_COUNT')
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        need(result.wasSuccessful() and result.testsRun==EXPECTED_TEST_COUNT and not result.skipped,'OUTER_TEST_FAILURE_OR_SKIP')
        need(git(root,['rev-parse','--verify','HEAD']).decode('ascii').strip()==head,'HEAD_CHANGED')
        need(verified_source(root,head,'owner_diagnostic_r7.py')[0]==raw and verified_source(root,head,'test_owner_diagnostic_r7.py')[0]==test,'SOURCE_CHANGED_AFTER_TEST')
        print(json.dumps({'kind':'EXACT_OWNER_R7_CONTINUATION_MOCKED_CI','head':head,'wrapper_sha256':source_sha,'test_sha256':test_sha,
            'tests':EXPECTED_TEST_COUNT,'core_cache':core,'skipped':0,'success':True,'kit_source':SOURCE,'archive_publication':PUBLICATION,
            'host_operations':'NOT_RUN','production_admission':'NOT_GRANTED'},sort_keys=True))
    finally:sys.modules.pop(module.__name__,None)

class OwnerR7Checkpoint(unittest.TestCase):
    def test_exact_owner_r7_mocked_boundaries(self):
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
            self.assertEqual(code,0,'EXACT_OWNER_R7_MOCKED_CI_FAILED')


if __name__=='__main__':
    if sys.argv[1:]==['--worker']:worker()
    else:unittest.main()
