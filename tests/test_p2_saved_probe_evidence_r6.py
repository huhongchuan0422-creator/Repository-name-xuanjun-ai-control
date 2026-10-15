"""P2 saved finite-probe export fixture checkpoint: 33+14+23, no host/network."""
import hashlib,importlib.util,io,json,os,pathlib,resource,signal,stat,subprocess,sys,tarfile,tempfile,time,unittest
FEATURE_ID='P2_RETAINED_RECOVERY'
MAX_LOG=1048576
ARCHIVE_PATH='evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-0c8a0f2a.tar.gz'
ARCHIVE_SIZE=1032979
ARCHIVE_SHA='600dc31aaf639aee875be1a075c7b544b9c8c5210fee24013ce614bc69ad5a83'
MANIFEST_SHA='70c76e30ae8390963f345813f87267bf1d2f024bc01031c8023733c84aa571cc'
MANIFEST_MEMBER='epoch7-recovery-candidate-r6/recovery-kit-manifest.json'
MANIFEST_TARGET='r6-integration-candidate/build-0c8a0f2a-python312-v2-a/epoch7-recovery-candidate-r6/recovery-kit-manifest.json'
PINS={'evidence/p2-epoch7-access-repair-20261014/saved-probe-evidence-r6/export_saved_evidence.py': (29149, 'dd1f6c2a701dbf849ff5e3361e226b5be505cd72d65aa3d58f6b0a1e68ee30fc', 'saved-probe-evidence-export-candidate/export_saved_evidence.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-probe-evidence-r6/export_schema.py': (23175, '4b3560afaebfb62fc7dc18d7648f0131a4d6756a5c971ea5469b7741d32126e8', 'saved-probe-evidence-export-candidate/export_schema.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-probe-evidence-r6/verify_exported_evidence.py': (10222, '054658a06d039d577236cb8edf5d6ade4890161f5bdd8d55d7fc87c52770a20b', 'saved-probe-evidence-export-candidate/verify_exported_evidence.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-probe-evidence-r6/test_export_saved_evidence.py': (18624, '8ec1ed9fdeec34a426286a59ecadbb644d3415abb9772d9a61b8cef4dcb08bc5', 'saved-probe-evidence-export-candidate/test_export_saved_evidence.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-probe-evidence-r6/test_export_schema.py': (17938, '462717000f3098bddf102c8ba1116a25d309d521b75daeb7fe45b5c08b1fbc43', 'saved-probe-evidence-export-candidate/test_export_schema.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-probe-evidence-r6/run_local_tests.py': (1455, '5eaade74c7cfa46281c3e9f615455665d4bf830ba8b2bba1ec731e1963be2b31', 'saved-probe-evidence-export-candidate/run_local_tests.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-probe-evidence-r6/test_fixtures/reviewed_reader_mechanics.py': (3166, '0a46e801b096b888398be31b93db5f3750e835af1f3ded48cddc17d8b8736fe4', 'saved-probe-evidence-export-candidate/test_fixtures/reviewed_reader_mechanics.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-probe-evidence-r6/bootstrap/OWNER_COMMAND_NOT_READY.txt': (4721, 'ba0ad3c59a8d4fe2dd91cffeb52d2a21106dbf75cf7ec4ee670c526f7feba454', 'saved-probe-evidence-export-candidate/bootstrap/OWNER_COMMAND_NOT_READY.txt'), 'evidence/p2-epoch7-access-repair-20261014/saved-probe-evidence-r6/bootstrap/test_owner_bootstrap.py': (9790, '6b7156fed635a090b8bb55683f436b5a44568d8738bd064b2184f8a060c175e9', 'saved-probe-evidence-export-candidate/bootstrap/test_owner_bootstrap.py'), 'evidence/p2-epoch7-access-repair-20261014/preparation-source-r6-contracts/epoch7_prepare.py': (42190, '44b181cac0da6da287bd98455a0d49fc4285a83d8a58c875bf1af98ebf49295d', 'r6-preparation-contract-fix-candidate/epoch7_prepare.py'), 'evidence/p2-epoch7-access-repair-20261014/preparation-source-r6-contracts/epoch7_prepare_data.py': (13888, '71be3f9cb6a58c82083c029fad8f6ba2ba524451bc110443ed3423ef7c9364a1', 'r6-preparation-contract-fix-candidate/epoch7_prepare_data.py'), 'evidence/p2-epoch7-access-repair-20261014/preparation-source-r6-contracts/epoch7_topology_projection.py': (27151, 'f8b731a8668a5b5374e18dab9a59657f80fc8d11ea2d9c4588a62942dbf74854', 'r6-preparation-contract-fix-candidate/epoch7_topology_projection.py'), 'evidence/p2-epoch7-access-repair-20261014/preparation-source-r6-contracts/test_epoch7_topology_projection.py': (27086, '86fbf00462cc854092cdd2592855fffd881e63e1d84f9b5b1191b7c2ac514e26', 'r6-preparation-contract-fix-candidate/test_epoch7_topology_projection.py')}

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

def archive_files(raw):
    need(type(raw) is bytes and len(raw)==ARCHIVE_SIZE and digest(raw)==ARCHIVE_SHA,'ARCHIVE_PIN')
    files={};prefix='epoch7-recovery-candidate-r6/'
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        rows=archive.getmembers();need(len(rows)<=512,'ARCHIVE_MEMBER_BOUND')
        for row in rows:
            if row.isdir():continue
            need(row.isreg() and row.name.startswith(prefix) and 0<=row.size<=33554432,'ARCHIVE_MEMBER')
            name=row.name[len(prefix):]
            need(name and not name.startswith('/') and '..' not in name.split('/') and name not in files,'ARCHIVE_NAME')
            with archive.extractfile(row) as stream:body=stream.read(row.size+1)
            need(len(body)==row.size,'ARCHIVE_BYTES');files[name]=body
    need(len(files)==250 and digest(files['recovery-kit-manifest.json'])==MANIFEST_SHA,'MANIFEST_PIN')
    manifest=json.loads(files['recovery-kit-manifest.json'].decode('ascii'))
    need(set(files)==set(manifest['files'])|{'recovery-kit-manifest.json'},'EXACT_ARCHIVE_FILES')
    for name,pin in manifest['files'].items():need(digest(files[name])==pin,'ARCHIVE_SOURCE_PIN')
    return files

def fixtures(root):
    result={target:read_pin(root,path,size,pin) for path,(size,pin,target) in PINS.items()}
    result.update({MANIFEST_TARGET.rsplit('/',1)[0]+'/'+name:body for name,body in
        archive_files(read_pin(root,ARCHIVE_PATH,ARCHIVE_SIZE,ARCHIVE_SHA)).items()})
    return result

def materialize(root,files):
    need(not root.exists(),'FIXTURE_EXISTS');root.mkdir(mode=0o700)
    allowed={row[2] for row in PINS.values()}
    kitprefix=MANIFEST_TARGET.rsplit('/',1)[0]+'/'
    for name,raw in sorted(files.items()):
        need(name in allowed or (name.startswith(kitprefix) and '..' not in name.split('/') and not name.endswith('/')),'FIXTURE_PATH')
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
    with tempfile.TemporaryDirectory(prefix='p2-saved-evidence-public-') as folder:
        work=materialize(pathlib.Path(folder)/'fixture',files);counts=[]
        for name,wanted in (('orchestration',33),('schema',14),('bootstrap',23)):
            script=work/'saved-probe-evidence-export-candidate/run_local_tests.py'
            code,raw=run_child([sys.executable,'-I','-B','-S',str(script),name],work,180,new_session=False)
            print(raw.decode('utf-8','replace'));need(code==0,'PUBLIC_TEST_PROCESS_FAILED')
            result=json.loads(raw.splitlines()[-1].decode('ascii'))
            need(result=={'schema':1,'state':'PASS','suite':name,'tests':wanted,'errors':0,'failures':0,'skips':0,
                'python':sys.version.split()[0],'host_NOT_RUN':True,'network_NOT_RUN':True},'PUBLIC_TEST_FAILURE_OR_SKIP')
            counts.append(wanted)
        check_materialized(work,files)
        need(fixtures(root)==files,'PUBLIC_INPUT_DRIFT')
    print(json.dumps({'schema':1,'state':'PASS','tests':70,'suite_counts':counts,'errors':0,'failures':0,'skips':0,
        'host_NOT_RUN':True,'network_NOT_RUN':True,'privateplan_NOT_RUN':True,'manifest_sha256':MANIFEST_SHA},sort_keys=True))

class SavedProbeEvidenceR6Tests(unittest.TestCase):
    def test_exact_public_33_plus_14_plus_23_suites(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        code,raw=run_child([sys.executable,'-I','-B','-S',str(pathlib.Path(__file__).resolve()),'--worker'],root,240)
        print(raw.decode('utf-8','replace'));self.assertEqual(code,0)
        value=json.loads(raw.splitlines()[-1].decode('ascii'))
        self.assertEqual(value,{'schema':1,'state':'PASS','tests':70,'suite_counts':[33,14,23],'errors':0,'failures':0,'skips':0,
            'host_NOT_RUN':True,'network_NOT_RUN':True,'privateplan_NOT_RUN':True,'manifest_sha256':MANIFEST_SHA})
    def test_exact_readonly_workflow_contract(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        raw=read_pin(root,'.github/workflows/p2-saved-probe-evidence-r6.yml',3670,'0583a4549de01d000d4323c3f2a7000299f1bc51478032e01cfb0b7d05be585f')
        text=raw.decode('utf-8');self.assertIn('contents: read',text);self.assertIn('persist-credentials: false',text)
        self.assertIn('python -I -B -S tests/test_p2_saved_probe_evidence_r6.py -v',text)
        self.assertNotIn('secrets.',text);self.assertIn('timeout-minutes: 8',text)
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
            with self.assertRaisesRegex(ValueError,'ARCHIVE_PIN'):archive_files(b'wrong')
    def test_unlisted_materialization_path_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'FIXTURE_PATH'):materialize(pathlib.Path(folder)/'fixture',{'../escape':b'x'})

if __name__=='__main__':
    if sys.argv[1:]==['--worker']:worker()
    else:unittest.main(verbosity=2)
