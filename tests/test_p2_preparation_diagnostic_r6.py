"""P2 public diagnostic fixture adapter: 29+4 unchanged tests, no host/network."""
import hashlib,importlib.util,io,json,os,pathlib,resource,signal,stat,subprocess,sys,tarfile,tempfile,time,unittest
FEATURE_ID='P2_RETAINED_RECOVERY'
MAX_LOG=1048576
ARCHIVE_PATH='evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-0c8a0f2a.tar.gz'
ARCHIVE_SIZE=1032979
ARCHIVE_SHA='600dc31aaf639aee875be1a075c7b544b9c8c5210fee24013ce614bc69ad5a83'
MANIFEST_SHA='70c76e30ae8390963f345813f87267bf1d2f024bc01031c8023733c84aa571cc'
MANIFEST_MEMBER='epoch7-recovery-candidate-r6/recovery-kit-manifest.json'
MANIFEST_TARGET='r6-integration-candidate/build-0c8a0f2a-python312-v2-a/epoch7-recovery-candidate-r6/recovery-kit-manifest.json'
PINS={'evidence/p2-epoch7-access-repair-20261014/preparation-diagnostic-r6/diagnose_preparation.py': (15641, '9cd065c6fb7d7f756314420d0867d4f639fcef090d82b449fdc3a20570eeed25', 'r6-preparation-diagnostic-candidate/diagnose_preparation.py'), 'evidence/p2-epoch7-access-repair-20261014/preparation-diagnostic-r6/test_diagnose_preparation.py': (17209, 'cfe62756b59ce23b5e2cbd9eb79f75c7093bb46d3979066183430c16033b6b5c', 'r6-preparation-diagnostic-candidate/test_diagnose_preparation.py'), 'evidence/p2-epoch7-access-repair-20261014/preparation-diagnostic-r6/test_bootstrap_template.py': (3729, '708865424750253985d6e637eff7746517584dd4101283adf3fbd9fa2e848599', 'r6-preparation-diagnostic-candidate/test_bootstrap_template.py'), 'evidence/p2-epoch7-access-repair-20261014/preparation-diagnostic-r6/verify_bootstrap_binding.py': (1832, '07de7260d4a73856a6d637e16de2c3c714de605e093869abf72767aab69a8e25', 'r6-preparation-diagnostic-candidate/verify_bootstrap_binding.py'), 'evidence/p2-epoch7-access-repair-20261014/preparation-diagnostic-r6/OWNER_DIAGNOSTIC_UNBOUND.txt': (5054, '42c73239afa87a98809341d749464ac608a6636bc4483595d883913f5dcf7f8c', 'r6-preparation-diagnostic-candidate/OWNER_DIAGNOSTIC_UNBOUND.txt'), 'evidence/p2-epoch7-access-repair-20261014/preparation-delivery-r6/epoch7_prepare_delivery.py': (14950, '9a87f740ee8d81fb95fe41e1644584c85b723fe5823f309ea0bf07796140cf9f', 'r6-delivery-bound-candidate/epoch7_prepare_delivery.py'), 'evidence/p2-epoch7-access-repair-20261014/preparation-source-r6/epoch7_prepare.py': (41352, '83c218fc10d19094446494e10767be58593f09dbc92866cbc8779d9a0e776ebc', 'r6-preparation-candidate/epoch7_prepare.py'), 'evidence/p2-epoch7-access-repair-20261014/preparation-source-r6/epoch7_prepare_data.py': (13888, '71be3f9cb6a58c82083c029fad8f6ba2ba524451bc110443ed3423ef7c9364a1', 'r6-preparation-candidate/epoch7_prepare_data.py'), 'evidence/p2-epoch7-access-repair-20261014/preparation-source-r6/epoch7_topology_projection.py': (27151, 'f8b731a8668a5b5374e18dab9a59657f80fc8d11ea2d9c4588a62942dbf74854', 'r6-preparation-candidate/epoch7_topology_projection.py')}

def need(value,label):
    if not value:raise ValueError(label)

def digest(raw):return hashlib.sha256(raw).hexdigest()

def read_pin(root,relative,size,pin):
    path=root/relative;need(path.resolve()==path,'PUBLIC_PATH_ALIAS')
    fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno());need(stat.S_ISREG(before.st_mode) and before.st_nlink==1,'PUBLIC_FILE_TYPE')
        raw=stream.read(size+1);after=os.fstat(stream.fileno())
    stamp=lambda s:tuple(getattr(s,'st_'+k) for k in ('dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns'))
    need(stamp(before)==stamp(after)==stamp(os.lstat(str(path))),'PUBLIC_FILE_CHANGED')
    need(len(raw)==size and digest(raw)==pin,'PUBLIC_FILE_PIN');return raw

def manifest_bytes(raw):
    need(type(raw) is bytes and len(raw)==ARCHIVE_SIZE and digest(raw)==ARCHIVE_SHA,'ARCHIVE_PIN')
    # No extract/extractall and no executable archive member is loaded.
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        rows=archive.getmembers();need(len(rows)<=512,'ARCHIVE_MEMBER_BOUND')
        matches=[row for row in rows if row.name==MANIFEST_MEMBER]
        need(len(matches)==1 and matches[0].isreg() and 0<matches[0].size<=1048576,'MANIFEST_MEMBER')
        with archive.extractfile(matches[0]) as stream:body=stream.read(1048577)
        need(len(body)==matches[0].size and digest(body)==MANIFEST_SHA,'MANIFEST_PIN');return body

def fixtures(root):
    result={target:read_pin(root,path,size,pin) for path,(size,pin,target) in PINS.items()}
    result[MANIFEST_TARGET]=manifest_bytes(read_pin(root,ARCHIVE_PATH,ARCHIVE_SIZE,ARCHIVE_SHA))
    return result

def materialize(root,files):
    need(not root.exists(),'FIXTURE_EXISTS');root.mkdir(mode=0o700)
    for name,raw in sorted(files.items()):
        need(name in {row[2] for row in PINS.values()}|{MANIFEST_TARGET},'FIXTURE_PATH')
        path=root/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(raw)
    return root

def check_materialized(root,files):
    found={p.relative_to(root).as_posix():p for p in root.rglob('*') if not p.is_dir()}
    need(set(found)==set(files),'FIXTURE_INVENTORY')
    for name,path in found.items():
        need(not path.is_symlink() and path.is_file() and path.read_bytes()==files[name],'FIXTURE_DRIFT')

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


def worker():
    root=pathlib.Path(__file__).resolve().parents[1];files=fixtures(root)
    with tempfile.TemporaryDirectory(prefix='p2-diagnostic-public-') as folder:
        work=materialize(pathlib.Path(folder)/'fixture',files);suites=[];counts=[]
        for name,wanted in (('test_diagnose_preparation',29),('test_bootstrap_template',4)):
            path=work/'r6-preparation-diagnostic-candidate'/(name+'.py')
            spec=importlib.util.spec_from_file_location('public_'+name,str(path));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            suite=unittest.defaultTestLoader.loadTestsFromModule(module);need(suite.countTestCases()==wanted,'EXACT_PUBLIC_TEST_COUNT')
            suites.append(suite);counts.append(wanted)
        result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(suites))
        need(result.testsRun==33 and result.wasSuccessful() and not result.skipped,'PUBLIC_TEST_FAILURE_OR_SKIP')
        check_materialized(work,files)
        # Every repository byte is reread after tests; fixture inputs stay exact.
        need(fixtures(root)==files,'PUBLIC_INPUT_DRIFT')
    print(json.dumps({'schema':1,'state':'PASS','tests':33,'suite_counts':counts,'errors':0,'failures':0,'skips':0,
        'host_NOT_RUN':True,'network_NOT_RUN':True,'privateplan_NOT_RUN':True,'manifest_sha256':MANIFEST_SHA},sort_keys=True))

class PreparationDiagnosticR6Tests(unittest.TestCase):
    def test_exact_public_29_plus_4_suites(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        code,raw=run_child([sys.executable,'-I','-B','-S',str(pathlib.Path(__file__).resolve()),'--worker'],root,90)
        print(raw.decode('utf-8','replace'));self.assertEqual(code,0)
        value=json.loads(raw.splitlines()[-1].decode('ascii'))
        self.assertEqual(value,{'schema':1,'state':'PASS','tests':33,'suite_counts':[29,4],'errors':0,'failures':0,'skips':0,
            'host_NOT_RUN':True,'network_NOT_RUN':True,'privateplan_NOT_RUN':True,'manifest_sha256':MANIFEST_SHA})
    def test_missing_or_changed_source_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            with self.assertRaises(FileNotFoundError):read_pin(root,'fixed.py',3,digest(b'abc'))
            (root/'fixed.py').write_bytes(b'abd')
            with self.assertRaisesRegex(ValueError,'PUBLIC_FILE_PIN'):read_pin(root,'fixed.py',3,digest(b'abc'))
    def test_source_alias_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);(root/'real.py').write_bytes(b'abc');(root/'alias.py').symlink_to(root/'real.py')
            with self.assertRaisesRegex(ValueError,'PUBLIC_PATH_ALIAS'):read_pin(root,'alias.py',3,digest(b'abc'))
    def test_wrong_archive_never_opens_tar(self):
        from unittest import mock
        with mock.patch.object(tarfile,'open',side_effect=AssertionError('unverified archive')):
            with self.assertRaisesRegex(ValueError,'ARCHIVE_PIN'):manifest_bytes(b'wrong')
    def test_unlisted_materialization_path_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'FIXTURE_PATH'):materialize(pathlib.Path(folder)/'fixture',{'../escape':b'x'})

if __name__=='__main__':
    if sys.argv[1:]==['--worker']:worker()
    else:unittest.main(verbosity=2)
