"""Exact public same-attempt R7 68-test checkpoint; no host or network effects."""
import hashlib,importlib.util,json,os,pathlib,re,resource,signal,stat,subprocess,sys,tempfile,time,types,unittest
FEATURE_ID='P2_RETAINED_RECOVERY'
MAX_LOG=1048576
MAX_FILE=16*1024*1024
MAX_TOTAL=288*1024*1024
TEST_COUNT=68
PREFIX='evidence/p2-epoch7-access-repair-20261014/'
GATE_PATH='tests/test_p2_same_attempt_r7.py'
WORKFLOW_PATH='.github/workflows/p2-same-attempt-r7.yml'
TEST_TARGET='kit-candidate/same-attempt-r7-candidate/test_observe_with_writer_capture.py'
R7_ARTIFACT='r7-integration-candidate/selected-artifact-dc18f73e/epoch7-recovery-kit.tar.gz'
LOCAL_RECORD='r7-integration-candidate/artifact-verification-dc18f73e-python312.json'
PINS={'evidence/p2-epoch7-access-repair-20261014/same-attempt-r7/observe_with_writer_capture.py': (38675, 'c82f4a75ec051003e3beab82d4b5b338d628fb81b4ad0bb05d7b9b57e7cef57e', 'kit-candidate/same-attempt-r7-candidate/observe_with_writer_capture.py'), 'evidence/p2-epoch7-access-repair-20261014/same-attempt-r7/test_observe_with_writer_capture.py': (37417, '15bfdc8f64e257137334af50bbc71652eaf2087c04c797707daaed9fb0d7ead3', 'kit-candidate/same-attempt-r7-candidate/test_observe_with_writer_capture.py'), 'evidence/p2-epoch7-access-repair-20261014/writer-diagnostic-r5/diagnose_writer_pair.py': (28922, '7179cceabd458d403fadf6b3d54e681c7e97f345ebe32b18251ae42b200da042', 'kit-candidate/writer-observation-readback-r5-candidate/diagnose_writer_pair.py'), 'evidence/p2-epoch7-access-repair-20261014/writer-diagnostic-r5/test_diagnose_writer_pair.py': (40852, 'efe85665ab04435be3b4ad0dba0554aee557efbf93d6b06631b69d3152a345d6', 'kit-candidate/writer-observation-readback-r5-candidate/test_diagnose_writer_pair.py'), 'evidence/p2-epoch7-access-repair-20261014/same-attempt-r6/observe_with_writer_capture.py': (37118, 'aa3d4f3f4b8882a203d964ac66479228f82f364be1352ed4c75af00d9ad9e5aa', 'kit-candidate/owner-hold-readback-candidate/r6-stored/read_existing_r6_hold.py'), 'evidence/p2-epoch7-access-repair-20261014/owner-diagnostic-r7/owner_diagnostic_r7.py': (27133, 'aca59a35b9b17351b71e8ba18ed1f4133c5dfab008c48dd52cf8422e6f39107a', 'r7-owner-continuation-candidate/owner_diagnostic_r7.py'), 'evidence/p2-epoch7-access-repair-20261014/owner-diagnostic-r6/extract_epoch7_kit_r6.py': (9582, 'e7977f5b849489befff4f782f35023f9267dd49a20b9b3e5f052eeb83758875d', None), 'evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tools/extract_epoch7_kit.py': (9582, 'eba0e2de223f0e0853968cd2a47f827a0dfe670c437a2071ea82cfd13b36dbf0', None), 'evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-0c8a0f2a.tar.gz': (1032979, '600dc31aaf639aee875be1a075c7b544b9c8c5210fee24013ce614bc69ad5a83', None), 'evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-dc18f73e.tar.gz': (1041263, 'e9841797571b3f039af8782b0aa1051c11c4b7938a2287abfd433e394b3d1645', None), '.github/workflows/p2-same-attempt-r7.yml': (3618, '8a00a44221d495c727ba2b14942b3b2f1ed256b1311760337e36e0e00cdfd563', None)}
ARCHIVES=[{'archive': 'evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-0c8a0f2a.tar.gz', 'extractor': 'evidence/p2-epoch7-access-repair-20261014/owner-diagnostic-r6/extract_epoch7_kit_r6.py', 'root': 'epoch7-recovery-candidate-r6', 'files': 250, 'entry_sha': 'c56ba6d8281eeb1ecc062875a7f13defc223f6d5dd073a4490d1602b8cf1d3a5', 'manifest_sha': '70c76e30ae8390963f345813f87267bf1d2f024bc01031c8023733c84aa571cc', 'target': 'r6-integration-candidate/build-0c8a0f2a-python312-v2-a/epoch7-recovery-candidate-r6'}, {'archive': 'evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-dc18f73e.tar.gz', 'extractor': 'evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tools/extract_epoch7_kit.py', 'root': 'epoch7-recovery-candidate-r7', 'files': 253, 'entry_sha': '1be06802e012b5747f837af02ff8746fec9864ef94715b561f67c39be95e0948', 'manifest_sha': '7b926fda92065d9ff981bfeaad490d5568dd5901d2b1089d1f1dfac94eae8bb4', 'target': 'r7-integration-candidate/selected-artifact-dc18f73e/epoch7-recovery-candidate-r7'}]

def need(value,label):
    if not value:raise ValueError(label)

def digest(raw):return hashlib.sha256(raw).hexdigest()

def relative(value):
    need(type(value) is str and 0<len(value)<=512 and re.fullmatch(r'[A-Za-z0-9_.\-/]+',value) and
         all(part not in ('','.','..','__pycache__') and not part.endswith(('.pyc','.pyo')) for part in value.split('/')),'PUBLIC_RELATIVE_PATH')
    return value

def git(root,args):
    return subprocess.check_output(['/usr/bin/git','-C',str(root)]+args,timeout=15)

def head_value(root):
    head=git(root,['rev-parse','--verify','HEAD']).decode('ascii').strip()
    need(re.fullmatch('[0-9a-f]{40}',head) is not None,'HEAD_FORMAT');return head

def read_public(root,name,maximum):
    relative(name);need(type(maximum) is int and 0<maximum<=32*1024*1024,'PUBLIC_FILE_BOUND')
    path=root/name;need(path.resolve()==path,'PUBLIC_PATH_ALIAS')
    fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno());need(stat.S_ISREG(before.st_mode) and before.st_nlink==1,'PUBLIC_FILE_TYPE')
        raw=stream.read(maximum+1);after=os.fstat(stream.fileno())
    stamp=lambda s:tuple(getattr(s,'st_'+k) for k in ('dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns'))
    need(stamp(before)==stamp(after)==stamp(os.lstat(str(path))) and len(raw)<=maximum,'PUBLIC_FILE_CHANGED_OR_BOUND')
    return raw

def read_head(root,head,name,maximum):
    raw=read_public(root,name,maximum)
    blob=hashlib.sha1(('blob '+str(len(raw))+'\0').encode()+raw).hexdigest()
    need(git(root,['rev-parse','--verify',head+':'+name]).decode('ascii').strip()==blob,'EXACT_HEAD_BLOB_MISMATCH')
    return raw

def read_inputs(root,head):
    result={GATE_PATH:read_head(root,head,GATE_PATH,MAX_FILE)}
    for name,(size,pin,target) in PINS.items():
        raw=read_head(root,head,name,size)
        need(len(raw)==size and digest(raw)==pin,'PUBLIC_FILE_PIN');result[name]=raw
    return result

def archive_files(inputs,row):
    # Both executable inspector and archive are fixed public SHA/size inputs.
    for name in (row['extractor'],row['archive']):
        size,pin,target=PINS[name];raw=inputs[name]
        need(type(raw) is bytes and len(raw)==size and digest(raw)==pin,'ARCHIVE_OR_INSPECTOR_PIN')
    module=types.ModuleType('pinned_public_archive_inspector');module.__file__='<pinned-public-inspector>'
    exec(compile(inputs[row['extractor']],module.__file__,'exec',dont_inherit=True),module.__dict__)
    need(module.ROOT_NAME==row['root'],'ARCHIVE_GENERATION')
    files,unused=module.inspect_archive(inputs[row['archive']],PINS[row['archive']][1],row['entry_sha'],row['manifest_sha'])
    need(len(files)==row['files'] and all(type(raw) is bytes and len(raw)<=MAX_FILE for raw in files.values()) and
         sum(map(len,files.values()))<=144*1024*1024,'PUBLIC_CACHE_BOUND')
    for name in files:relative(name)
    return files

def fixtures(inputs,work):
    files={target:inputs[name] for name,(size,pin,target) in PINS.items() if target is not None}
    for row in ARCHIVES:
        for name,raw in archive_files(inputs,row).items():
            target=row['target']+'/'+name;need(target not in files,'FIXTURE_ALIAS');files[target]=raw
    files[R7_ARTIFACT]=inputs[ARCHIVES[1]['archive']]
    files[LOCAL_RECORD]=(json.dumps({'archive_path':str(work/R7_ARTIFACT)},sort_keys=True)+'\n').encode('ascii')
    need(len(files)==511 and sum(map(len,files.values()))<=MAX_TOTAL,'FIXTURE_TOTAL_BOUND')
    return files

def allowed_target(name):
    relative(name)
    return name in {row[2] for row in PINS.values() if row[2] is not None}|{R7_ARTIFACT,LOCAL_RECORD} or any(
        name.startswith(row['target']+'/') for row in ARCHIVES)

def materialize(root,files):
    need(not root.exists(),'FIXTURE_EXISTS')
    need(type(files) is dict and len(files)<=511 and sum(map(len,files.values()))<=MAX_TOTAL,'FIXTURE_TOTAL_BOUND')
    for name,raw in files.items():need(allowed_target(name) and type(raw) is bytes and len(raw)<=MAX_FILE,'FIXTURE_PATH')
    root.mkdir(mode=0o700)
    for name,raw in sorted(files.items()):
        path=root/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(raw)
    return root

def check_materialized(root,files):
    paths=list(root.rglob('*'));need(not any(p.is_symlink() for p in paths),'FIXTURE_ALIAS')
    found={p.relative_to(root).as_posix() for p in paths if not p.is_dir()}
    need(found==set(files),'FIXTURE_INVENTORY')
    for name,raw in files.items():need(read_public(root,name,max(1,len(raw)))==raw,'FIXTURE_DRIFT')

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


def terminal(head):
    return {'schema':1,'state':'PASS','head':head,'tests':TEST_COUNT,'errors':0,'failures':0,'skips':0,
        'prior_archive_files':250,'target_archive_files':253,'host_NOT_RUN':True,'network_NOT_RUN':True,
        'privateplan_NOT_RUN':True,'production_admission':'NOT_GRANTED'}

def worker():
    root=pathlib.Path(__file__).resolve().parents[1];head=head_value(root);inputs=read_inputs(root,head)
    with tempfile.TemporaryDirectory(prefix='p2-same-attempt-r7-public-') as folder:
        work=pathlib.Path(folder)/'fixture';files=fixtures(inputs,work);materialize(work,files)
        path=work/TEST_TARGET;spec=importlib.util.spec_from_file_location('verified_same_attempt_r7_tests',str(path))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        suite=unittest.defaultTestLoader.loadTestsFromModule(module);need(suite.countTestCases()==TEST_COUNT,'EXACT_PUBLIC_TEST_COUNT')
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        need(result.testsRun==TEST_COUNT and result.wasSuccessful() and not result.skipped,'PUBLIC_TEST_FAILURE_OR_SKIP')
        check_materialized(work,files)
        need(head_value(root)==head and read_inputs(root,head)==inputs,'PUBLIC_HEAD_OR_INPUT_DRIFT')
    print(json.dumps(terminal(head),sort_keys=True))

class SameAttemptR7Tests(unittest.TestCase):
    def test_exact_public_68_suite(self):
        root=pathlib.Path(__file__).resolve().parents[1];head=head_value(root)
        code,raw=run_child([sys.executable,'-I','-B','-S',str(pathlib.Path(__file__).resolve()),'--worker'],root,180)
        print(raw.decode('utf-8','replace'));self.assertEqual(code,0)
        self.assertEqual(json.loads(raw.splitlines()[-1].decode('ascii')),terminal(head))
        self.assertEqual(head_value(root),head)

if __name__=='__main__':
    if sys.argv[1:]==['--worker']:worker()
    else:unittest.main(verbosity=2)
