"""Stage A saved-only public fixture gate. Publication and suite pins fail closed until frozen."""
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
REPORTER_TARGET='stage-a-saved-reporter-candidate'
COVERAGE_TARGET='stage-a-saved-coverage-candidate'
WORKFLOW_PATH='.github/workflows/p2-stage-a-saved-reporter.yml'
GATE_PATH='tests/test_p2_stage_a_saved_reporter.py'
CONTRACT_PATH='tests/test_p2_stage_a_saved_reporter_contract.py'
REGISTRY_PATH='governance/features.json'
SUITE_NAMES=('reporter','coverage')
SUITES=(('reporter', 43), ('coverage', 66))
PINS_BOUND=True
WORKFLOW_SIZE=4968
WORKFLOW_SHA='941bf2e72d7c82e20d881f1548d3569b8ea40cc12d1a2c6dbf8c54f64dc406b8'
PINS={'evidence/p2-epoch7-access-repair-20261014/stage-a-saved-reporter/report_saved_stage_a.py': (93912, '8ebd1ae2d572818677e5e404647f2d53ddae40f3aafa32320dcaf36d7384bde0', 'stage-a-saved-reporter-candidate/report_saved_stage_a.py'), 'evidence/p2-epoch7-access-repair-20261014/stage-a-saved-reporter/test_report_saved_stage_a.py': (23582, '2c69922bdd3e5aa3005f6190d6ad242dff03deaf4335a05101cca0f9e66bd88c', 'stage-a-saved-reporter-candidate/test_report_saved_stage_a.py'), 'evidence/p2-epoch7-access-repair-20261014/stage-a-saved-reporter/run_local_tests.py': (1371, '6f147d6abce5348af826cbbdbfb89197ad3c4074a89fadda950bc2b66e1e725a', 'stage-a-saved-reporter-candidate/run_local_tests.py'), 'evidence/p2-epoch7-access-repair-20261014/stage-a-saved-coverage/saved_authority_coverage.py': (21159, 'ac4be6793ec07c9294cf21c8f892e3a83ff4002fe9ba768416fee30d125afb9e', 'stage-a-saved-coverage-candidate/saved_authority_coverage.py'), 'evidence/p2-epoch7-access-repair-20261014/stage-a-saved-coverage/test_saved_authority_coverage.py': (21241, 'f598fbe0c71e374cf6d761b407bf6c39376f9a95c60d897ac2e5cf7f4186cda7', 'stage-a-saved-coverage-candidate/test_saved_authority_coverage.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/export_saved_evidence.py': (49401, 'a436d97072bf0062a94f9ccbd030aef1a08214f12f74645efd12d89d9f464815', 'saved-evidence-r7/export_saved_evidence.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/verify_exported_evidence.py': (11327, 'b5c7b39fa3403dda95e21cfdf5ab402d1f32656fe93951d356b1fe62464d71be', 'saved-evidence-r7/verify_exported_evidence.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/export_schema.py': (23175, 'df216347c7e969942be4e8eea42dfe580b3b155ff4a36d1383e9bca0cf253629', 'saved-evidence-r7/export_schema.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/test_export_schema.py': (19773, '9ea8d6a03157228f208758a1e3791f374ef8ab9f445a7f77c83faed258ea32a3', 'saved-evidence-r7/test_export_schema.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/test_export_saved_evidence.py': (18366, '4e0f3425a88004e367c7c546b7b1e39f425b8b40690019096f49896a86dc85e9', 'saved-evidence-r7/test_export_saved_evidence.py'), 'evidence/p2-epoch7-access-repair-20261014/preparation-source-r7-fresh/epoch7_prepare_data.py': (13888, '71be3f9cb6a58c82083c029fad8f6ba2ba524451bc110443ed3423ef7c9364a1', 'r7-saved-preparation-candidate/epoch7_prepare_data.py'), 'evidence/p2-epoch7-access-repair-20261014/preparation-source-r7-fresh/epoch7_topology_projection.py': (36482, '0e9817a1474dc4e54cf1779c0b4c243cf16e6204cab3a25210a12e41e03d00b6', 'r7-saved-preparation-candidate/epoch7_topology_projection.py'), 'evidence/p2-epoch7-access-repair-20261014/preparation-source-r7-fresh/test_epoch7_prepare_data_r7.py': (15985, 'e76d894610a9391ea02f2d29ce6cc89189cc4dc184dfc7cf8c0bc0e41d22eeed', 'r7-saved-preparation-candidate/test_epoch7_prepare_data_r7.py'), 'evidence/p2-epoch7-access-repair-20261014/preparation-source-r7-fresh/test_epoch7_topology_projection.py': (35404, '38e96133f4d3134e409cc7124f10426ea85cc59d01dd1e2392fb977c8e87dbcb', 'r7-saved-preparation-candidate/test_epoch7_topology_projection.py'), 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7-actual-20261015/packet.json': (294949, '45b832dce9577b49e6ee718f1637862eebd775c6c10f87d9150ed0a87476fdf7', 'saved-evidence-r7-actual-20261015/packet.json')}
SOURCE_TARGETS={'evidence/p2-epoch7-access-repair-20261014/stage-a-saved-reporter/report_saved_stage_a.py': 'stage-a-saved-reporter-candidate/report_saved_stage_a.py', 'evidence/p2-epoch7-access-repair-20261014/stage-a-saved-reporter/test_report_saved_stage_a.py': 'stage-a-saved-reporter-candidate/test_report_saved_stage_a.py', 'evidence/p2-epoch7-access-repair-20261014/stage-a-saved-reporter/run_local_tests.py': 'stage-a-saved-reporter-candidate/run_local_tests.py', 'evidence/p2-epoch7-access-repair-20261014/stage-a-saved-coverage/saved_authority_coverage.py': 'stage-a-saved-coverage-candidate/saved_authority_coverage.py', 'evidence/p2-epoch7-access-repair-20261014/stage-a-saved-coverage/test_saved_authority_coverage.py': 'stage-a-saved-coverage-candidate/test_saved_authority_coverage.py', 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/export_saved_evidence.py': 'saved-evidence-r7/export_saved_evidence.py', 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/verify_exported_evidence.py': 'saved-evidence-r7/verify_exported_evidence.py', 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/export_schema.py': 'saved-evidence-r7/export_schema.py', 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/test_export_schema.py': 'saved-evidence-r7/test_export_schema.py', 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/test_export_saved_evidence.py': 'saved-evidence-r7/test_export_saved_evidence.py', 'evidence/p2-epoch7-access-repair-20261014/preparation-source-r7-fresh/epoch7_prepare_data.py': 'r7-saved-preparation-candidate/epoch7_prepare_data.py', 'evidence/p2-epoch7-access-repair-20261014/preparation-source-r7-fresh/epoch7_topology_projection.py': 'r7-saved-preparation-candidate/epoch7_topology_projection.py', 'evidence/p2-epoch7-access-repair-20261014/preparation-source-r7-fresh/test_epoch7_prepare_data_r7.py': 'r7-saved-preparation-candidate/test_epoch7_prepare_data_r7.py', 'evidence/p2-epoch7-access-repair-20261014/preparation-source-r7-fresh/test_epoch7_topology_projection.py': 'r7-saved-preparation-candidate/test_epoch7_topology_projection.py', 'evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7-actual-20261015/packet.json': 'saved-evidence-r7-actual-20261015/packet.json'}
PUBLIC_DIRECTORIES=('evidence/p2-epoch7-access-repair-20261014/stage-a-saved-reporter',
                    'evidence/p2-epoch7-access-repair-20261014/stage-a-saved-coverage')


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
    need(PINS_BOUND is True,'STAGE_A_CI_PUBLICATION_NOT_BOUND')
    need(type(SUITES) is tuple and tuple(name for name,count in SUITES)==SUITE_NAMES
         and all(type(count) is int and count>0 for name,count in SUITES),'EXACT_SUITE_COUNTS_NOT_BOUND')
    need(len(set(SOURCE_TARGETS.values()))==len(SOURCE_TARGETS),'EXACT_PUBLIC_TARGETS')
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
    for prefix in PUBLIC_DIRECTORIES:
        for path in (root/prefix).rglob('*'):
            row=path.lstat();need(not stat.S_ISLNK(row.st_mode),'PUBLIC_SOURCE_ALIAS')
            if stat.S_ISDIR(row.st_mode):continue
            need(stat.S_ISREG(row.st_mode),'PUBLIC_SOURCE_TYPE');found.add(path.relative_to(root).as_posix())
    expected={path for path in SOURCE_TARGETS if any(path.startswith(prefix+'/') for prefix in PUBLIC_DIRECTORIES)}
    need(found==expected,'PUBLIC_SOURCE_ALLOWLIST')

def registry_contract(raw):
    # Registry additions are allowed; this gate authenticates its own registration
    # in the exact current HEAD rather than pinning an unrelated historical file.
    need(type(raw) is bytes and 0<len(raw)<=1048576,'REGISTRY_BOUND')
    value=strict_json(raw)
    need(type(value) is dict and type(value.get('schema_version')) is int and
         value['schema_version']==1 and type(value.get('features')) is list and
         0<len(value['features'])<=256,'REGISTRY_SCHEMA')
    need(all(type(row) is dict for row in value['features']),'REGISTRY_FEATURE_SHAPE')
    rows=[row for row in value['features'] if row.get('feature_id')==FEATURE_ID]
    need(len(rows)==1 and rows[0].get('status')=='IN_DEVELOPMENT','REGISTRY_FEATURE_SCOPE')
    acceptance=rows[0].get('acceptance')
    need(type(acceptance) is dict and type(acceptance.get('tests')) is list,'REGISTRY_TESTS')
    paths=acceptance['tests']
    need(0<len(paths)<=1024 and all(type(path) is str and
         re.fullmatch(r'tests/[A-Za-z0-9_./-]+\.py',path) and
         all(part not in ('','.','..') for part in path.split('/')) for path in paths),
         'REGISTRY_TEST_PATH')
    need(len(paths)==len(set(paths)) and
         all(paths.count(path)==1 for path in (GATE_PATH,CONTRACT_PATH)),
         'REGISTRY_REQUIRED_TESTS')

def checkout_records(root,head):
    paths=set(PINS)|{GATE_PATH,CONTRACT_PATH,WORKFLOW_PATH,REGISTRY_PATH,ARCHIVE_PATH}
    records={path:verified_path(root,head,path,ARCHIVE_SIZE if path==ARCHIVE_PATH else 1048576) for path in sorted(paths)}
    need(pathlib.Path(__file__).read_bytes()==records[GATE_PATH],'CHECKPOINT_NOT_EXACT_HEAD')
    need(len(records[WORKFLOW_PATH])==WORKFLOW_SIZE and digest(records[WORKFLOW_PATH])==WORKFLOW_SHA,'WORKFLOW_PIN')
    registry_contract(records[REGISTRY_PATH])
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

def aggregate():
    return {'schema':1,'state':'PASS','tests':sum(count for name,count in SUITES),
        'suite_counts':[count for name,count in SUITES],'errors':0,'failures':0,'skips':0,
        'host_NOT_RUN':True,'network_NOT_RUN':True,'privateplan_NOT_RUN':True,'fresh_authority_NOT_RUN':True,
        'production_resume':'NOT_EXECUTED',
        'manifest_sha256':MANIFEST_SHA,'archive_members':ARCHIVE_MEMBERS,'cached_files':KIT_CACHE_FILES}

def worker():
    publication_pins();need(os.getsid(0)==os.getpid(),'WORKER_OWNED_SESSION_REQUIRED')
    root=pathlib.Path(__file__).resolve().parents[1]
    head=git(root,['rev-parse','--verify','HEAD']);public_inventory(root)
    records=checkout_records(root,head);files=fixtures(root,records)
    with tempfile.TemporaryDirectory(prefix='p2-stage-a-public-') as folder:
        work=materialize(pathlib.Path(folder)/'fixture',files)
        os.environ['EPOCH7_STAGE_A_TEST_KIT_ROOT']=str(work/KIT_TARGET)
        os.environ['EPOCH7_STAGE_A_TEST_ARCHIVE']=str(work/ARCHIVE_TARGET)
        os.environ['EPOCH7_PREP_TEST_KIT_ROOT']=str(work/KIT_TARGET)
        os.environ['EPOCH7_EXPORT_TEST_ARCHIVE']=str(work/ARCHIVE_TARGET)
        os.environ['STAGE_A_ACTUAL_PACKET']=str(work/'saved-evidence-r7-actual-20261015/packet.json')
        os.environ['STAGE_A_TEST_PACKET']=str(work/'saved-evidence-r7-actual-20261015/packet.json')
        os.environ['STAGE_A_TEST_FIXTURE_ROOT']=str(work)
        for name,wanted in SUITES:
            argv=[sys.executable,'-I','-B','-S',str(work/REPORTER_TARGET/'run_local_tests.py'),name]
            code,raw=run_child(argv,work,180,new_session=False)
            print(raw.decode('utf-8','replace'));need(code==0,'PUBLIC_TEST_PROCESS_FAILED')
            terminal(raw,name,wanted)
        check_materialized(work,files)
        public_inventory(root)
        need(git(root,['rev-parse','--verify','HEAD'])==head,'HEAD_CHANGED')
        need(checkout_records(root,head)==records,'INPUT_CHANGED_AFTER_TEST')
    print(json.dumps(aggregate(),sort_keys=True))

class StageASavedReporterTests(unittest.TestCase):
    def test_exact_public_reporter_and_coverage_suites(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        code,raw=run_child([sys.executable,'-I','-B','-S',str(pathlib.Path(__file__).resolve()),'--worker'],root,300)
        print(raw.decode('utf-8','replace'));self.assertEqual(code,0)
        self.assertEqual(strict_json(raw.splitlines()[-1]),aggregate())
    def test_exact_readonly_workflow_contract(self):
        publication_pins();root=pathlib.Path(__file__).resolve().parents[1]
        raw=read_pin(root,WORKFLOW_PATH,WORKFLOW_SIZE,WORKFLOW_SHA)
        text=raw.decode('utf-8');self.assertIn('contents: read',text);self.assertIn('persist-credentials: false',text)
        for name in ('test_p2_stage_a_saved_reporter.py','test_p2_stage_a_saved_reporter_contract.py'):
            self.assertIn('python3 -I -B -S tests/'+name+' -v',text)
        self.assertNotIn('secrets.',text);self.assertIn('timeout-minutes: 8',text)

if __name__=='__main__':
    if sys.argv[1:]==['--worker']:worker()
    else:unittest.main(verbosity=2)
