"""Exact public preparation checkpoint; synthetic fixtures only. FEATURE_ID=P2_RETAINED_RECOVERY."""
import hashlib,json,os,pathlib,re,resource,shutil,signal,stat,subprocess,sys,tempfile,time,types,unittest

PREFIX='evidence/p2-epoch7-access-repair-20261014/preparation-source-r6-contracts/'
PINS_BOUND=True
PUBLIC_INPUTS_SHA='7d75dd17c9002db09ded5df95641580795d875f4eb76442469a10600c375dd2f'
EXPECTED_TEST_COUNT=88
EXPECTED_INTEGRATION_COUNT=31
FROZEN_PREFIX='evidence/p2-epoch7-access-repair-20261014/preparation-source-r6/'
FROZEN_FILES={'epoch7_prepare.py': '83c218fc10d19094446494e10767be58593f09dbc92866cbc8779d9a0e776ebc', 'epoch7_prepare_data.py': '71be3f9cb6a58c82083c029fad8f6ba2ba524451bc110443ed3423ef7c9364a1', 'epoch7_topology_projection.py': 'f8b731a8668a5b5374e18dab9a59657f80fc8d11ea2d9c4588a62942dbf74854', 'test_epoch7_prepare.py': '5489374357c6b0f0d0d7c1dfa37cc6cb23d328db06da78bd59cb59a1790103d3', 'test_epoch7_topology_projection.py': '86fbf00462cc854092cdd2592855fffd881e63e1d84f9b5b1191b7c2ac514e26'}
PUBLIC_FILES=('README.md','epoch7_prepare.py','epoch7_prepare_data.py','epoch7_topology_projection.py',
              'run_local_tests.py','test_epoch7_prepare.py','test_epoch7_topology_projection.py',
              'test_collect_native_integration.py','test_fixtures/epoch7_prepare_native_only.py')
ARCHIVE_PATH='evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-0c8a0f2a.tar.gz'
ARCHIVE_SHA='600dc31aaf639aee875be1a075c7b544b9c8c5210fee24013ce614bc69ad5a83'
ARCHIVE_SIZE=1032979
MANIFEST_SHA='70c76e30ae8390963f345813f87267bf1d2f024bc01031c8023733c84aa571cc'
ENTRY_SHA='c56ba6d8281eeb1ecc062875a7f13defc223f6d5dd073a4490d1602b8cf1d3a5'
EXTRACTOR_PATH='evidence/p2-epoch7-access-repair-20261014/preparation-source-r6/fixtures/extract_epoch7_kit_r6.py'
EXTRACTOR_SHA='e7977f5b849489befff4f782f35023f9267dd49a20b9b3e5f052eeb83758875d'
EXTRACTOR_SIZE=9582
SOURCE='0c8a0f2a97da0c3f00f53659cd6ef7fc7d4ec3ba'
TREE='7d0f402b495b1398637c86463d9c10b4d4559d1f'
MAX_LOG=4*1024*1024


def need(value,label):
    if not value:raise ValueError(label)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(rows):
        result={}
        for key,value in rows:
            need(key not in result,'DUPLICATE_JSON');result[key]=value
        return result
    return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,
        parse_constant=lambda unused:need(False,'NONFINITE_JSON'))


def safe_name(name):
    need(type(name) is str and 0<len(name)<=512 and re.fullmatch(r'[A-Za-z0-9_.\-/]+',name) and
         all(x not in ('','.','..','__pycache__') and not x.endswith(('.pyc','.pyo')) for x in name.split('/')),'SOURCE_PATH_SCOPE')
    return name


def git(root,args):
    # These fixed rev-parse requests return only one object identifier.
    raw=subprocess.check_output(['/usr/bin/git','-C',str(root)]+args,timeout=15)
    need(len(raw)<=128,'GIT_OUTPUT_BOUND');value=raw.decode('ascii').strip()
    need(re.fullmatch('[0-9a-f]{40}',value),'GIT_OBJECT_FORMAT');return value


def verified_path(root,head,relative,maximum=1048576):
    safe_name(relative);path=root/relative
    need(path.resolve()==path,'SOURCE_PATH_ALIAS')
    fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        first=os.fstat(stream.fileno());need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_size<=maximum,'SOURCE_FILE_TYPE_OR_BOUND')
        raw=stream.read(maximum+1);after=os.fstat(stream.fileno())
    stamp=lambda row:tuple(getattr(row,'st_'+name) for name in ('dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns'))
    need(len(raw)<=maximum and stamp(first)==stamp(after)==stamp(os.lstat(str(path))),'SOURCE_CHANGED_OR_BOUND')
    blob=hashlib.sha1(('blob '+str(len(raw))+'\0').encode()+raw).hexdigest()
    need(blob==git(root,['rev-parse','--verify',head+':'+relative]),'EXACT_HEAD_BLOB_MISMATCH')
    return raw


def public_inventory(root):
    folder=root/PREFIX;found=set()
    for path in folder.rglob('*'):
        row=path.lstat();need(not stat.S_ISLNK(row.st_mode),'PUBLIC_SOURCE_ALIAS')
        if stat.S_ISDIR(row.st_mode):continue
        need(stat.S_ISREG(row.st_mode),'PUBLIC_SOURCE_TYPE');found.add(path.relative_to(folder).as_posix())
    need(found==set(PUBLIC_FILES)|{'PUBLIC_INPUTS.json'},'PUBLIC_SOURCE_ALLOWLIST')


def publication_gate():
    need(PINS_BOUND is True,'PREPARATION_PUBLICATION_NOT_BOUND')
    need(type(PUBLIC_INPUTS_SHA) is str and re.fullmatch('[0-9a-f]{64}',PUBLIC_INPUTS_SHA),'PUBLIC_INPUTS_PIN')
    need(type(EXPECTED_TEST_COUNT) is int and 0<EXPECTED_TEST_COUNT<1024,'EXPECTED_TEST_COUNT_PIN')
    need(type(EXPECTED_INTEGRATION_COUNT) is int and 0<EXPECTED_INTEGRATION_COUNT<1024,'EXPECTED_INTEGRATION_COUNT_PIN')


def public_inputs(raw):
    need(sha(raw)==PUBLIC_INPUTS_SHA,'PUBLIC_INPUTS_PIN')
    value=strict_json(raw)
    need(type(value) is dict and value.get('schema')==1 and value.get('feature_id')=='P2_RETAINED_RECOVERY','PUBLIC_INPUTS_SCHEMA')
    need(type(value.get('public_files')) is dict and set(value['public_files'])==set(PUBLIC_FILES),'EXACT_PUBLIC_FILES')
    need(value.get('production_files')==['epoch7_prepare.py','epoch7_prepare_data.py','epoch7_topology_projection.py'] and
         value.get('test_modules')==['test_epoch7_prepare','test_epoch7_topology_projection'],'EXACT_PUBLIC_MODULES')
    need(value.get('hosted_private_plan_validation')=='NOT_PERFORMED' and value.get('production_resume')=='NOT_EXECUTED' and
         value.get('install_admission')=='NOT_GRANTED','PUBLIC_SCOPE_DECLARATION')
    need(type(value.get('portable_expected_tests')) is int and value['portable_expected_tests']==EXPECTED_TEST_COUNT and
         value.get('portable_requires_zero_errors_failures_skips') is True and value.get('outer_test_timeout_seconds')==180,'PUBLIC_TEST_CONTRACT')
    need(type(value.get('collection_integration_expected_tests')) is int and value['collection_integration_expected_tests']==EXPECTED_INTEGRATION_COUNT,'COLLECTION_INTEGRATION_COUNT')
    need(value.get('frozen_r6_preparation_fixture',{}).get('files')==FROZEN_FILES,'FROZEN_PUBLIC_FIXTURE_PINS')
    need(value.get('excluded_local_only')==['test_epoch7_prepare_private.py','all private original plans','all private observation/probe/seed buffers','LOCAL_STATUS.json','PUBLICATION_MAP.json','all local test logs'],'PRIVATE_SUITE_EXCLUSION')
    need(value.get('structured_terminal_fields')==['schema','state','tests','errors','failures','skips','python','host_NOT_RUN','privateplan_NOT_RUN'],'PUBLIC_TERMINAL_CONTRACT')
    fixture=value.get('r6_fixture');need(type(fixture) is dict and fixture.get('manifest_sha256')==MANIFEST_SHA and
         type(fixture.get('files')) is dict and len(fixture['files'])==250,'EXACT_R6_FIXTURE')
    for rows in (value['public_files'],fixture['files']):
        for name,pin in rows.items():
            safe_name(name);need(type(pin) is str and re.fullmatch('[0-9a-f]{64}',pin),'PUBLIC_FILE_PIN')
    return value


def inspect_fixture(archive,extractor_raw,inputs):
    need(len(archive)==ARCHIVE_SIZE and sha(archive)==ARCHIVE_SHA,'ARCHIVE_PIN')
    need(len(extractor_raw)==EXTRACTOR_SIZE and sha(extractor_raw)==EXTRACTOR_SHA,'EXTRACTOR_PIN')
    module=types.ModuleType('verified_preparation_fixture_extractor');module.__file__='<verified-historical-r6-extractor>'
    exec(compile(extractor_raw,module.__file__,'exec',dont_inherit=True),module.__dict__)
    files,unused=module.inspect_archive(archive,ARCHIVE_SHA,ENTRY_SHA,MANIFEST_SHA)
    need(len(files)==250 and {name:sha(raw) for name,raw in files.items()}==inputs['r6_fixture']['files'],'R6_FIXTURE_FILE_MAP')
    entry=types.ModuleType('verified_preparation_fixture_entry');entry.__file__='<verified-r6-entry>'
    exec(compile(files['epoch7_recovery_entry.py'],entry.__file__,'exec',dont_inherit=True),entry.__dict__)
    manifest=entry.validate_manifest(entry.decode(files[entry.MANIFEST]));cache={name:raw for name,raw in files.items() if name!=entry.MANIFEST}
    entry.validate_runtime(manifest,cache)
    need(manifest['kit_source_commit']==SOURCE and manifest['kit_source_tree']==TREE,'R6_SOURCE_PROVENANCE')
    return files


def materialize(folder,files):
    need(not folder.exists(),'FIXTURE_ALREADY_EXISTS');folder.mkdir(mode=0o700)
    for name,raw in sorted(files.items()):
        safe_name(name);path=folder/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        primary=None
        try:
            offset=0
            while offset<len(raw):
                count=os.write(fd,raw[offset:]);need(count>0,'FIXTURE_WRITE_NO_PROGRESS');offset+=count
            os.fchmod(fd,0o444)
        except BaseException as error:primary=error;raise
        finally:
            try:os.close(fd)
            except BaseException:
                if primary is not None:primary.preparation_ci_cleanup_unknown=True
                else:raise


def verify_materialized(folder,files):
    paths={}
    for path in folder.rglob('*'):
        row=path.lstat();need(not stat.S_ISLNK(row.st_mode),'FIXTURE_SYMLINK')
        if stat.S_ISDIR(row.st_mode):continue
        paths[path.relative_to(folder).as_posix()]=path
    need(set(paths)==set(files),'FIXTURE_INVENTORY_CHANGED')
    for name,path in paths.items():
        row=path.lstat();need(stat.S_ISREG(row.st_mode) and row.st_nlink==1,'FIXTURE_TYPE_CHANGED')
        with path.open('rb') as stream:raw=stream.read(len(files[name])+1)
        need(raw==files[name],'FIXTURE_BYTES_CHANGED')


def output_file_limit():
    # CI-only limit inherited by disposable fixture children, not production.
    resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_LOG,MAX_LOG))


def run_child(argv,cwd,timeout,new_session=True):
    """Outer owns one session; nested tests remain inside it until final group kill."""
    log=tempfile.TemporaryFile();child=None;primary=None;cleanup=[];raw=b'';code=None;owned=False
    try:
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        child=subprocess.Popen(argv,cwd=str(cwd),env=env,stdout=log,stderr=subprocess.STDOUT,
            start_new_session=new_session,preexec_fn=output_file_limit);owned=True
        if new_session:
            deadline=time.monotonic()+timeout
            while True:
                if time.monotonic()>=deadline:raise subprocess.TimeoutExpired(argv,timeout)
                # WNOWAIT retains the group leader's PID ownership through killpg.
                try:status=os.waitid(os.P_PID,child.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                except ChildProcessError:
                    owned=False;error=RuntimeError('CHILD_OWNERSHIP_UNKNOWN');error.preparation_ci_cleanup_unknown=True;raise error
                if time.monotonic()>=deadline:raise subprocess.TimeoutExpired(argv,timeout)
                if status is not None:break
                need(os.fstat(log.fileno()).st_size<MAX_LOG,'CHILD_LOG_BOUND')
                if time.monotonic()>=deadline:raise subprocess.TimeoutExpired(argv,timeout)
                time.sleep(.02)
        else:
            code=child.wait(timeout=timeout);owned=False
    except BaseException as error:primary=error
    finally:
        if child is not None and owned and not new_session and child.returncode is not None:
            # Popen.wait may reap while handling KeyboardInterrupt. Do not signal a reused PID.
            owned=False;code=child.returncode
        if child is not None and owned:
            try:
                if new_session:os.killpg(child.pid,signal.SIGKILL)
                else:os.kill(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            except BaseException as error:cleanup.append(error)
            try:code=child.wait(timeout=5);owned=False
            except BaseException as error:cleanup.append(error)
        elif child is not None and child.returncode is None:
            # Ownership was lost; never signal a potentially reused PGID.
            try:code=child.wait(timeout=5)
            except BaseException as error:cleanup.append(error)
        if primary is None and not cleanup:
            try:
                size=os.fstat(log.fileno()).st_size;need(size<MAX_LOG,'CHILD_LOG_BOUND')
                log.seek(0);raw=log.read(MAX_LOG);need(len(raw)<MAX_LOG,'CHILD_LOG_BOUND')
            except BaseException as error:primary=error
        try:log.close()
        except BaseException as error:cleanup.append(error)
    if primary is not None:
        if cleanup:primary.preparation_ci_cleanup_unknown=True
        raise primary
    if cleanup:
        error=RuntimeError('CHILD_CLEANUP_UNKNOWN');error.preparation_ci_cleanup_unknown=True;raise error
    return code,raw


def terminal(raw,expected=None):
    expected=EXPECTED_TEST_COUNT if expected is None else expected
    need(type(raw) is bytes and 0<len(raw)<=MAX_LOG,'TERMINAL_LOG_BOUND')
    lines=raw.splitlines();need(lines and len(lines[-1])<=4096,'TERMINAL_ABSENT_OR_BOUND')
    value=strict_json(lines[-1])
    need(type(value) is dict and set(value)=={'schema','state','tests','errors','failures','skips','python','host_NOT_RUN','privateplan_NOT_RUN'},'TERMINAL_SCHEMA')
    need(type(value['schema']) is int and value['schema']==1 and value['state']=='PASS','TERMINAL_STATE')
    need(type(value['tests']) is int and value['tests']==expected,'EXACT_PORTABLE_TEST_COUNT')
    for key in ('errors','failures','skips'):need(type(value[key]) is int and value[key]==0,'PORTABLE_FAILURE_OR_SKIP')
    need(value['host_NOT_RUN'] is True and value['privateplan_NOT_RUN'] is True,'PORTABLE_PRIVATE_OR_HOST_SCOPE')
    need(type(value['python']) is str and value['python']==sys.version.split()[0],'TERMINAL_INTERPRETER')
    return value


INTEGRATION_RUNNER = """import hashlib,json,pathlib,sys,types,unittest
path=pathlib.Path(sys.argv[1]);raw=path.read_bytes()
if hashlib.sha256(raw).hexdigest()!=sys.argv[2]:raise ValueError('INTEGRATION_SOURCE_PIN')
module=types.ModuleType('public_collect_integration');module.__file__=str(path)
exec(compile(raw,str(path),'exec'),module.__dict__)
suite=unittest.defaultTestLoader.loadTestsFromModule(module)
if suite.countTestCases()!=int(sys.argv[3]):raise ValueError('INTEGRATION_TEST_COUNT')
result=unittest.TextTestRunner(verbosity=2).run(suite)
passed=result.wasSuccessful() and not result.skipped and result.testsRun==int(sys.argv[3])
print(json.dumps({'schema':1,'state':'PASS' if passed else 'FAIL','tests':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'skips':len(result.skipped),'python':sys.version.split()[0],'host_NOT_RUN':True,'privateplan_NOT_RUN':True},sort_keys=True))
sys.exit(not passed)
"""

def worker(root=None):
    publication_gate();need(os.getsid(0)==os.getpid(),'WORKER_OWNED_SESSION_REQUIRED')
    root=pathlib.Path(root).resolve() if root else pathlib.Path(__file__).resolve().parents[1]
    head=git(root,['rev-parse','--verify','HEAD'])
    gate_raw=verified_path(root,head,'tests/test_p2_preparation_contracts_r6.py')
    need(pathlib.Path(__file__).read_bytes()==gate_raw,'CHECKPOINT_NOT_EXACT_HEAD')
    public_inventory(root)
    records={'tests/test_p2_preparation_contracts_r6.py':gate_raw,
        'tests/test_p2_preparation_contracts_r6_contract.py':verified_path(root,head,'tests/test_p2_preparation_contracts_r6_contract.py')};records[PREFIX+'PUBLIC_INPUTS.json']=verified_path(root,head,PREFIX+'PUBLIC_INPUTS.json')
    inputs=public_inputs(records[PREFIX+'PUBLIC_INPUTS.json']);sources={}
    for name in PUBLIC_FILES:
        raw=verified_path(root,head,PREFIX+name);need(sha(raw)==inputs['public_files'][name],'PUBLIC_SOURCE_HASH');sources[name]=raw;records[PREFIX+name]=raw
    records[ARCHIVE_PATH]=verified_path(root,head,ARCHIVE_PATH,ARCHIVE_SIZE)
    records[EXTRACTOR_PATH]=verified_path(root,head,EXTRACTOR_PATH)
    files=inspect_fixture(records[ARCHIVE_PATH],records[EXTRACTOR_PATH],inputs)
    frozen={}
    for name,pin in FROZEN_FILES.items():
        raw=verified_path(root,head,FROZEN_PREFIX+name);need(sha(raw)==pin,'FROZEN_PUBLIC_SOURCE_HASH')
        frozen[name]=raw;records[FROZEN_PREFIX+name]=raw
    temporary=pathlib.Path(tempfile.mkdtemp(prefix='.preparation-ci-',dir=str(root)));primary=None
    try:
        prep=temporary/'r6-preparation-contract-fix-candidate'
        kit=temporary/'r6-integration-candidate/build-0c8a0f2a-python312-v2-a/epoch7-recovery-candidate-r6'
        kit.parent.mkdir(parents=True,mode=0o700)
        frozen_root=temporary/'r6-preparation-candidate'
        materialize(prep,sources);materialize(kit,files);materialize(frozen_root,frozen)
        code,log=run_child([sys.executable,'-I','-B','-S',str(prep/'run_local_tests.py'),'--portable','--kit-root',str(kit)],temporary,180,new_session=False)
        print(log[-65536:].decode('utf-8','replace'))
        need(code==0,'PORTABLE_CHILD_EXIT');result=terminal(log)
        code,log=run_child([sys.executable,'-I','-B','-S','-c',INTEGRATION_RUNNER,str(prep/'test_collect_native_integration.py'),inputs['public_files']['test_collect_native_integration.py'],str(EXPECTED_INTEGRATION_COUNT)],temporary,180,new_session=False)
        print(log[-65536:].decode('utf-8','replace'))
        need(code==0,'COLLECTION_INTEGRATION_EXIT');integration=terminal(log,EXPECTED_INTEGRATION_COUNT)
        verify_materialized(prep,sources);verify_materialized(kit,files);verify_materialized(frozen_root,frozen)
        public_inventory(root)
        need(git(root,['rev-parse','--verify','HEAD'])==head,'HEAD_CHANGED')
        for path,raw in records.items():need(verified_path(root,head,path,ARCHIVE_SIZE if path==ARCHIVE_PATH else 1048576)==raw,'INPUT_CHANGED_AFTER_TEST')
        report={'kind':'EXACT_PUBLIC_PREPARATION_CHECKPOINT','schema':1,'head':head,'public_inputs_sha256':PUBLIC_INPUTS_SHA,
            'public_file_count':len(PUBLIC_FILES),'archive_files':250,'archive_sha256':ARCHIVE_SHA,'manifest_sha256':MANIFEST_SHA,
            'portable':result,'collection_integration':integration,'success':True,'host_operations':'NOT_RUN','private_plan_validation':'NOT_PERFORMED','production_admission':'NOT_GRANTED'}

    except BaseException as error:primary=error;raise
    finally:
        try:shutil.rmtree(str(temporary))
        except BaseException:
            if primary is not None:primary.preparation_ci_cleanup_unknown=True
            else:raise
    print(json.dumps(report,sort_keys=True));return report


class PreparationCheckpoint(unittest.TestCase):
    def test_exact_public_preparation(self):
        code,raw=run_child([sys.executable,'-I','-B','-S',str(pathlib.Path(__file__).resolve()),'--worker'],pathlib.Path(__file__).resolve().parents[1],240)
        print(raw[-65536:].decode('utf-8','replace'));self.assertEqual(code,0,'PREPARATION_CHECKPOINT_FAILED')
        report=strict_json(raw.splitlines()[-1]);self.assertEqual(report['kind'],'EXACT_PUBLIC_PREPARATION_CHECKPOINT');self.assertIs(report['success'],True)
        self.assertEqual(report['public_inputs_sha256'],PUBLIC_INPUTS_SHA);self.assertEqual(report['portable']['tests'],EXPECTED_TEST_COUNT)
        self.assertEqual(report['collection_integration']['tests'],EXPECTED_INTEGRATION_COUNT)


if __name__=='__main__':
    if sys.argv[1:]==['--worker']:worker()
    else:unittest.main()
