"""P2 saved R7 public-only clean-checkout suites: 35+16+39+15+23."""
import hashlib,io,json,os,pathlib,re,resource,signal,stat,subprocess,sys,tarfile,tempfile,time,types,unittest
FEATURE_ID='P2_RETAINED_RECOVERY'
MAX_LOG=1048576
ARCHIVE_PATH='evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-dc18f73e.tar.gz'
ARCHIVE_SIZE=1041263
ARCHIVE_SHA='e9841797571b3f039af8782b0aa1051c11c4b7938a2287abfd433e394b3d1645'
MANIFEST_SHA='7b926fda92065d9ff981bfeaad490d5568dd5901d2b1089d1f1dfac94eae8bb4'
ARCHIVE_TARGET='r7-fixture/epoch7-recovery-kit.tar.gz'
KIT_TARGET='r7-fixture/epoch7-recovery-candidate-r7'
ARCHIVE_HEADERS=295
ARCHIVE_MEMBERS=253
KIT_CACHE_FILES=252
EXPORT_TARGET='saved-r7-evidence-export-candidate'
PREP_TARGET='r7-saved-preparation-candidate'
WORKFLOW_PATH='.github/workflows/p2-saved-evidence-r7.yml'
GATE_PATH='tests/test_p2_saved_evidence_r7.py'
CONTRACT_PATH='tests/test_p2_saved_evidence_r7_contract.py'
METADATA_PINS={'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/README.md': (5557, '4b12629bdd31f5780b59b50db81fc6d5d1ef42e36693ec6bb9eaec32b2367a9f'), 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/RESULTS.json': (3377, '5524d48ba8bdebc6b3798f1e3b79f582991e9645efef008c85a9af287dec5477')}
SUITES=(('orchestration',35),('schema',16),('topology',39),('data',15),('bootstrap',23))
PINS_BOUND=True
WORKFLOW_SIZE=3879
WORKFLOW_SHA='3d303676d48c5feee27e3b3aea46d8ae03cff466d668a1a977d53ccce0f837ce'
PINS={'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/export_saved_evidence.py': (49401, 'a436d97072bf0062a94f9ccbd030aef1a08214f12f74645efd12d89d9f464815', 'saved-r7-evidence-export-candidate/export_saved_evidence.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/export_schema.py': (23175, 'df216347c7e969942be4e8eea42dfe580b3b155ff4a36d1383e9bca0cf253629', 'saved-r7-evidence-export-candidate/export_schema.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/verify_exported_evidence.py': (11327, 'b5c7b39fa3403dda95e21cfdf5ab402d1f32656fe93951d356b1fe62464d71be', 'saved-r7-evidence-export-candidate/verify_exported_evidence.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/test_export_saved_evidence.py': (18366, '4e0f3425a88004e367c7c546b7b1e39f425b8b40690019096f49896a86dc85e9', 'saved-r7-evidence-export-candidate/test_export_saved_evidence.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/test_export_schema.py': (19773, '9ea8d6a03157228f208758a1e3791f374ef8ab9f445a7f77c83faed258ea32a3', 'saved-r7-evidence-export-candidate/test_export_schema.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/run_local_tests.py': (1471, 'c78e01de01972fa4038a220b95605a606321399ba8c1874a60afabf3b96bb229', 'saved-r7-evidence-export-candidate/run_local_tests.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/test_fixtures/reviewed_reader_mechanics.py': (3166, '0a46e801b096b888398be31b93db5f3750e835af1f3ded48cddc17d8b8736fe4', 'saved-r7-evidence-export-candidate/test_fixtures/reviewed_reader_mechanics.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/bootstrap/OWNER_COMMAND_NOT_READY.txt': (4715, 'ceab44dcf4999838f4a590eeeae15d7e0608ebf55872efc9dd990d4d80a06de6', 'saved-r7-evidence-export-candidate/bootstrap/OWNER_COMMAND_NOT_READY.txt'), 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/bootstrap/test_owner_bootstrap.py': (9784, 'a6a010e0673eb88a112efd9edfe2b5c3fdddc4fd631ac280b2a0329a20155a9f', 'saved-r7-evidence-export-candidate/bootstrap/test_owner_bootstrap.py'), 'evidence/p2-epoch7-access-repair-20261014/r7-saved-preparation/epoch7_prepare_data.py': (13888, '71be3f9cb6a58c82083c029fad8f6ba2ba524451bc110443ed3423ef7c9364a1', 'r7-saved-preparation-candidate/epoch7_prepare_data.py'), 'evidence/p2-epoch7-access-repair-20261014/r7-saved-preparation/epoch7_topology_projection.py': (36482, '0e9817a1474dc4e54cf1779c0b4c243cf16e6204cab3a25210a12e41e03d00b6', 'r7-saved-preparation-candidate/epoch7_topology_projection.py'), 'evidence/p2-epoch7-access-repair-20261014/r7-saved-preparation/test_epoch7_topology_projection.py': (35404, '38e96133f4d3134e409cc7124f10426ea85cc59d01dd1e2392fb977c8e87dbcb', 'r7-saved-preparation-candidate/test_epoch7_topology_projection.py'), 'evidence/p2-epoch7-access-repair-20261014/r7-saved-preparation/test_epoch7_prepare_data_r7.py': (15985, 'e76d894610a9391ea02f2d29ce6cc89189cc4dc184dfc7cf8c0bc0e41d22eeed', 'r7-saved-preparation-candidate/test_epoch7_prepare_data_r7.py')}
SOURCE_TARGETS={'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/export_saved_evidence.py': 'saved-r7-evidence-export-candidate/export_saved_evidence.py', 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/export_schema.py': 'saved-r7-evidence-export-candidate/export_schema.py', 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/verify_exported_evidence.py': 'saved-r7-evidence-export-candidate/verify_exported_evidence.py', 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/test_export_saved_evidence.py': 'saved-r7-evidence-export-candidate/test_export_saved_evidence.py', 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/test_export_schema.py': 'saved-r7-evidence-export-candidate/test_export_schema.py', 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/run_local_tests.py': 'saved-r7-evidence-export-candidate/run_local_tests.py', 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/test_fixtures/reviewed_reader_mechanics.py': 'saved-r7-evidence-export-candidate/test_fixtures/reviewed_reader_mechanics.py', 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/bootstrap/OWNER_COMMAND_NOT_READY.txt': 'saved-r7-evidence-export-candidate/bootstrap/OWNER_COMMAND_NOT_READY.txt', 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/bootstrap/test_owner_bootstrap.py': 'saved-r7-evidence-export-candidate/bootstrap/test_owner_bootstrap.py', 'evidence/p2-epoch7-access-repair-20261014/r7-saved-preparation/epoch7_prepare_data.py': 'r7-saved-preparation-candidate/epoch7_prepare_data.py', 'evidence/p2-epoch7-access-repair-20261014/r7-saved-preparation/epoch7_topology_projection.py': 'r7-saved-preparation-candidate/epoch7_topology_projection.py', 'evidence/p2-epoch7-access-repair-20261014/r7-saved-preparation/test_epoch7_topology_projection.py': 'r7-saved-preparation-candidate/test_epoch7_topology_projection.py', 'evidence/p2-epoch7-access-repair-20261014/r7-saved-preparation/test_epoch7_prepare_data_r7.py': 'r7-saved-preparation-candidate/test_epoch7_prepare_data_r7.py'}


def need(value,label):
    if not value:raise ValueError(label)

def digest(raw):return hashlib.sha256(raw).hexdigest()

def strict_json(raw):
    def unique(rows):
        result={}
        for key,value in rows:
            need(key not in result,'DUPLICATE_JSON_KEY');result[key]=value
        return result
    return json.loads(raw.decode('ascii'),object_pairs_hook=unique)

def safe_name(name):
    need(type(name) is str and name and not name.startswith('/') and '\\' not in name and '\0' not in name
         and all(part not in ('','.','..') for part in name.split('/')),'FINITE_RELATIVE_PATH')
    return name

def publication_pins():
    need(PINS_BOUND is True,'R7_CI_PUBLICATION_NOT_BOUND')
    need(set(PINS)==set(SOURCE_TARGETS),'EXACT_PUBLIC_INPUTS')
    for path,row in PINS.items():
        need(type(row) in (tuple,list) and len(row)==3,'PUBLIC_PIN_SHAPE')
        size,pin,target=row
        need(type(size) is int and 0<size<=33554432 and type(pin) is str and len(pin)==64
             and all(c in '0123456789abcdef' for c in pin) and target==SOURCE_TARGETS[path],'PUBLIC_PIN_SHAPE')
        safe_name(path);safe_name(target)
    need(type(WORKFLOW_SIZE) is int and 0<WORKFLOW_SIZE<=65536 and type(WORKFLOW_SHA) is str
         and len(WORKFLOW_SHA)==64 and all(c in '0123456789abcdef' for c in WORKFLOW_SHA),'WORKFLOW_NOT_BOUND')

def read_pin(root,relative,size,pin):
    path=root/relative;need(path.resolve()==path,'PUBLIC_PATH_ALIAS')
    fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno());need(stat.S_ISREG(before.st_mode) and before.st_nlink==1,'PUBLIC_FILE_TYPE')
        raw=stream.read(size+1);after=os.fstat(stream.fileno())
    stamp=lambda s:tuple(getattr(s,'st_'+k) for k in ('dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns'))
    need(stamp(before)==stamp(after)==stamp(os.lstat(str(path))),'PUBLIC_FILE_CHANGED')
    need(len(raw)==size and digest(raw)==pin,'PUBLIC_FILE_PIN');return raw

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


def archive_files(raw):
    need(type(raw) is bytes and len(raw)==ARCHIVE_SIZE and digest(raw)==ARCHIVE_SHA,'ARCHIVE_PIN')
    files={};prefix='epoch7-recovery-candidate-r7/'
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        rows=archive.getmembers();need(len(rows)==ARCHIVE_HEADERS,'ARCHIVE_HEADER_COUNT')
        for row in rows:
            if row.isdir():continue
            need(row.isreg() and row.name.startswith(prefix) and 0<=row.size<=33554432,'ARCHIVE_MEMBER')
            name=safe_name(row.name[len(prefix):]);need(name not in files,'ARCHIVE_NAME')
            with archive.extractfile(row) as stream:body=stream.read(row.size+1)
            need(len(body)==row.size,'ARCHIVE_BYTES');files[name]=body
    need(len(files)==ARCHIVE_MEMBERS,'ARCHIVE_MEMBER_COUNT')
    need(digest(files['recovery-kit-manifest.json'])==MANIFEST_SHA,'MANIFEST_PIN')
    manifest=strict_json(files['recovery-kit-manifest.json'])
    need(len(manifest['files'])==KIT_CACHE_FILES,'KIT_CACHE_COUNT')
    need(set(files)==set(manifest['files'])|{'recovery-kit-manifest.json'},'EXACT_ARCHIVE_FILES')
    for name,pin in manifest['files'].items():need(digest(files[name])==pin,'ARCHIVE_SOURCE_PIN')
    return files

def fixtures(root,records=None):
    publication_pins()
    def exact(path,size,pin):
        raw=read_pin(root,path,size,pin) if records is None else records[path]
        need(len(raw)==size and digest(raw)==pin,'PUBLIC_FILE_PIN');return raw
    result={target:exact(path,size,pin) for path,(size,pin,target) in PINS.items()}
    raw=exact(ARCHIVE_PATH,ARCHIVE_SIZE,ARCHIVE_SHA)
    result.update({KIT_TARGET+'/'+name:body for name,body in archive_files(raw).items()})
    result[ARCHIVE_TARGET]=raw
    return result

def public_inventory(root):
    found=set()
    for prefix in ('evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7',
                   'evidence/p2-epoch7-access-repair-20261014/r7-saved-preparation'):
        for path in (root/prefix).rglob('*'):
            row=path.lstat();need(not stat.S_ISLNK(row.st_mode),'PUBLIC_SOURCE_ALIAS')
            if stat.S_ISDIR(row.st_mode):continue
            need(stat.S_ISREG(row.st_mode),'PUBLIC_SOURCE_TYPE');found.add(path.relative_to(root).as_posix())
    need(found==set(PINS)|set(METADATA_PINS),'PUBLIC_SOURCE_ALLOWLIST')

def checkout_records(root,head):
    paths=set(PINS)|set(METADATA_PINS)|{GATE_PATH,CONTRACT_PATH,WORKFLOW_PATH,ARCHIVE_PATH}
    records={path:verified_path(root,head,path,ARCHIVE_SIZE if path==ARCHIVE_PATH else 1048576) for path in sorted(paths)}
    need(pathlib.Path(__file__).read_bytes()==records[GATE_PATH],'CHECKPOINT_NOT_EXACT_HEAD')
    need(len(records[WORKFLOW_PATH])==WORKFLOW_SIZE and digest(records[WORKFLOW_PATH])==WORKFLOW_SHA,'WORKFLOW_PIN')
    for path,(size,pin) in METADATA_PINS.items():
        need(len(records[path])==size and digest(records[path])==pin,'PUBLIC_METADATA_PIN')
    return records

def materialize(root,files):
    need(not root.exists(),'FIXTURE_EXISTS');root.mkdir(mode=0o700)
    allowed=set(SOURCE_TARGETS.values())|{ARCHIVE_TARGET}
    for name,raw in sorted(files.items()):
        safe_name(name)
        need(name in allowed or name.startswith(KIT_TARGET+'/'),'FIXTURE_PATH')
        path=root/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(raw)
    return root

def check_materialized(root,files):
    found={p.relative_to(root).as_posix():p for p in root.rglob('*') if not p.is_dir()}
    need(set(found)==set(files),'FIXTURE_INVENTORY')
    for path in root.rglob('*'):need(not path.is_symlink(),'FIXTURE_ALIAS')
    for name,path in found.items():
        need(path.is_file() and path.read_bytes()==files[name],'FIXTURE_DRIFT')

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


def summary(name,count):
    return {'schema':1,'state':'PASS','suite':name,'tests':count,'errors':0,'failures':0,'skips':0,
        'python':sys.version.split()[0],'host_NOT_RUN':True,'network_NOT_RUN':True}

def terminal(raw,name,count):
    need(type(raw) is bytes and raw.splitlines(),'PUBLIC_TEST_EMPTY')
    value=strict_json(raw.splitlines()[-1])
    # JSON representation preserves bool/int distinction that Python equality loses.
    need(json.dumps(value,sort_keys=True)==json.dumps(summary(name,count),sort_keys=True),'PUBLIC_TEST_FAILURE_OR_SKIP')
    return value

def preparation_suite(name,root):
    wanted=dict(SUITES).get(name);need(name in ('topology','data'),'EXACT_PREPARATION_SUITE')
    module_name={'topology':'test_epoch7_topology_projection','data':'test_epoch7_prepare_data_r7'}[name]
    path=root/PREP_TARGET/(module_name+'.py');module=types.ModuleType(module_name)
    module.__file__=str(path);sys.modules[module_name]=module
    exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
    suite=unittest.defaultTestLoader.loadTestsFromModule(module)
    need(suite.countTestCases()==wanted,'EXACT_PREPARATION_TEST_COUNT')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    ok=result.wasSuccessful() and not result.skipped and result.testsRun==wanted
    value=summary(name,result.testsRun);value.update(state='PASS' if ok else 'FAIL',
        errors=len(result.errors),failures=len(result.failures),skips=len(result.skipped))
    print(json.dumps(value,sort_keys=True));sys.exit(not ok)

def aggregate():
    return {'schema':1,'state':'PASS','tests':sum(count for name,count in SUITES),
        'suite_counts':[count for name,count in SUITES],'errors':0,'failures':0,'skips':0,
        'host_NOT_RUN':True,'network_NOT_RUN':True,'privateplan_NOT_RUN':True,
        'manifest_sha256':MANIFEST_SHA,'archive_members':ARCHIVE_MEMBERS,'cached_files':KIT_CACHE_FILES}

def worker():
    publication_pins();need(os.getsid(0)==os.getpid(),'WORKER_OWNED_SESSION_REQUIRED')
    root=pathlib.Path(__file__).resolve().parents[1]
    head=git(root,['rev-parse','--verify','HEAD']);public_inventory(root)
    records=checkout_records(root,head);files=fixtures(root,records)
    with tempfile.TemporaryDirectory(prefix='p2-saved-r7-public-') as folder:
        work=materialize(pathlib.Path(folder)/'fixture',files)
        os.environ['EPOCH7_PREP_TEST_KIT_ROOT']=str(work/KIT_TARGET)
        os.environ['EPOCH7_EXPORT_TEST_ARCHIVE']=str(work/ARCHIVE_TARGET)
        for name,wanted in SUITES:
            if name in ('topology','data'):
                argv=[sys.executable,'-I','-B','-S',str(pathlib.Path(__file__).resolve()),'--preparation',name,str(work)]
            else:
                argv=[sys.executable,'-I','-B','-S',str(work/EXPORT_TARGET/'run_local_tests.py'),name]
            code,raw=run_child(argv,work,180,new_session=False)
            print(raw.decode('utf-8','replace'));need(code==0,'PUBLIC_TEST_PROCESS_FAILED')
            terminal(raw,name,wanted)
        check_materialized(work,files)
        public_inventory(root)
        need(git(root,['rev-parse','--verify','HEAD'])==head,'HEAD_CHANGED')
        need(checkout_records(root,head)==records,'INPUT_CHANGED_AFTER_TEST')
    print(json.dumps(aggregate(),sort_keys=True))

class SavedEvidenceR7Tests(unittest.TestCase):
    def test_exact_public_35_plus_16_plus_39_plus_15_plus_23_suites(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        code,raw=run_child([sys.executable,'-I','-B','-S',str(pathlib.Path(__file__).resolve()),'--worker'],root,300)
        print(raw.decode('utf-8','replace'));self.assertEqual(code,0)
        self.assertEqual(strict_json(raw.splitlines()[-1]),aggregate())
    def test_exact_readonly_workflow_contract(self):
        publication_pins();root=pathlib.Path(__file__).resolve().parents[1]
        raw=read_pin(root,WORKFLOW_PATH,WORKFLOW_SIZE,WORKFLOW_SHA)
        text=raw.decode('utf-8');self.assertIn('contents: read',text);self.assertIn('persist-credentials: false',text)
        for name in ('test_p2_saved_evidence_r7.py','test_p2_saved_evidence_r7_contract.py'):
            self.assertIn('python3 -I -B -S tests/'+name+' -v',text)
        self.assertNotIn('secrets.',text);self.assertIn('timeout-minutes: 8',text)

if __name__=='__main__':
    if sys.argv[1:]==['--worker']:worker()
    elif len(sys.argv)==4 and sys.argv[1]=='--preparation':preparation_suite(sys.argv[2],pathlib.Path(sys.argv[3]))
    else:unittest.main(verbosity=2)
