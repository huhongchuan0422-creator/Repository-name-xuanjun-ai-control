"""Exact public R7 fresh-preparation checkpoint. Synthetic fixture inputs only.
FEATURE_ID=P2_RETAINED_RECOVERY. No host operation, private-plan check or admission.
"""
import ast,hashlib,json,os,pathlib,re,resource,shutil,signal,stat,subprocess,sys,tempfile,time,types,unittest

PINS_BOUND=True
PUBLIC_INPUTS_SHA='7b30430d9ff77c1b72a4abb074c02144c552d985ca65c583b5f2e1db9fbb2d5b'
EXPECTED_PREPARATION_COUNT=189
EXPECTED_DELIVERY_COUNT=84
DELIVERY_PUBLICATION_BOUND=True
DELIVERY_SOURCE_COMMIT='c9fe40be1e44d4e41ca741e80ea257356a6b2ebb'
PREP_PREFIX='evidence/p2-epoch7-access-repair-20261014/preparation-source-r7-fresh/'
DELIVERY_PREFIX='evidence/p2-epoch7-access-repair-20261014/preparation-delivery-r7-fresh/'
CI_PREFIX='evidence/p2-epoch7-access-repair-20261014/preparation-fresh-r7-ci/'
INPUTS_PATH=CI_PREFIX+'PUBLIC_INPUTS.json'
WORKFLOW_PATH='.github/workflows/p2-preparation-fresh-r7.yml'
GATE_PATH='tests/test_p2_preparation_fresh_r7.py'
CONTRACT_PATH='tests/test_p2_preparation_fresh_r7_contract.py'
PREP_TARGET='r7-fresh-preparation-candidate'
DELIVERY_TARGET='r7-fresh-preparation-delivery-candidate'
KIT_TARGET='epoch7-recovery-candidate-r7'
PREP_FILES=('README.md','LOCAL_RESULTS.json','epoch7_prepare.py','epoch7_prepare_data.py','epoch7_topology_projection.py',
 'run_local_tests.py','test_epoch7_prepare.py','test_epoch7_topology_projection.py',
 'test_epoch7_prepare_data_r7.py','test_r7_preparation_orchestration.py','test_r7_fresh_inventory.py',
 'test_collect_native_integration.py','test_fixtures/epoch7_prepare_frozen_r6.py','test_fixtures/epoch7_prepare_native_only.py')
DELIVERY_FILES=('epoch7_prepare_delivery.py','test_epoch7_prepare_delivery.py',
 'test_epoch7_prepare_delivery_projection.py','test_epoch7_prepare_bootstrap_binding.py',
 'test_r7_delivery_scope.py','OWNER_PREPARATION_UNBOUND.txt','run_local_tests.py','README.md')
PREP_MODULES=('test_epoch7_prepare','test_epoch7_topology_projection','test_epoch7_prepare_data_r7','test_r7_preparation_orchestration','test_r7_fresh_inventory','test_collect_native_integration')
DELIVERY_MODULES=('test_epoch7_prepare_delivery','test_epoch7_prepare_delivery_projection','test_epoch7_prepare_bootstrap_binding','test_r7_delivery_scope')
DIAGNOSTIC_PATH='evidence/p2-epoch7-access-repair-20261014/preparation-delivery-r6-contracts/fixtures/diagnose_preparation.py'
DIAGNOSTIC_SHA='9cd065c6fb7d7f756314420d0867d4f639fcef090d82b449fdc3a20570eeed25'
DIAGNOSTIC_SIZE=15641
FROZEN_TEST_FIXTURES={'test_fixtures/epoch7_prepare_frozen_r6.py':'83c218fc10d19094446494e10767be58593f09dbc92866cbc8779d9a0e776ebc',
 'test_fixtures/epoch7_prepare_native_only.py':'e4b377b9b4913f72e79a940ce39890d5512db6792b68c6da81f4e8756e375510'}
FACTORY_TEST='test_epoch7_prepare.PureTests.test_real107_full_factory_compiles_new_identity_policies_and_final_body'
PRODUCTION_FILES=('epoch7_prepare.py','epoch7_prepare_data.py','epoch7_topology_projection.py')
ARCHIVE_PATH='evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-dc18f73e.tar.gz'
ARCHIVE_SHA='e9841797571b3f039af8782b0aa1051c11c4b7938a2287abfd433e394b3d1645'
ARCHIVE_SIZE=1041263
MANIFEST_SHA='7b926fda92065d9ff981bfeaad490d5568dd5901d2b1089d1f1dfac94eae8bb4'
ENTRY_SHA='1be06802e012b5747f837af02ff8746fec9864ef94715b561f67c39be95e0948'
EXTRACTOR_PATH='evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tools/extract_epoch7_kit.py'
EXTRACTOR_SHA='eba0e2de223f0e0853968cd2a47f827a0dfe670c437a2071ea82cfd13b36dbf0'
EXTRACTOR_SIZE=9582
SOURCE='dc18f73e67818dc59f5acea247dbf05443bde10d'
TREE='860d1a126b3a447c60079e315ebb549fcf5333aa'
RUNTIME_SOURCE='4ed2f5114e2f065266af26eedd8d62aebdbf0957'
RUNTIME_TREE='0c2cbcb0f898331865bbdfdf39f2c85ef675a88a'
RUNTIME_MANIFEST_SHA='0ac28c96636ee63364015b375202779e2ef1dd0bd9f1b81e77d4387b6754316c'
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


def source_targets():
    targets={PREP_PREFIX+name:PREP_TARGET+'/'+name for name in PREP_FILES}
    targets.update({DELIVERY_PREFIX+name:DELIVERY_TARGET+'/'+name for name in DELIVERY_FILES})
    targets[DIAGNOSTIC_PATH]=DELIVERY_TARGET+'/fixtures/diagnose_preparation.py'
    return targets


def public_inventory(root):
    found=set()
    for prefix in (PREP_PREFIX,DELIVERY_PREFIX,CI_PREFIX):
        folder=root/prefix
        need(folder.is_dir() and folder.resolve()==folder,'PUBLIC_SOURCE_DIRECTORY')
        for path in folder.rglob('*'):
            row=path.lstat();need(not stat.S_ISLNK(row.st_mode),'PUBLIC_SOURCE_ALIAS')
            if stat.S_ISDIR(row.st_mode):continue
            need(stat.S_ISREG(row.st_mode),'PUBLIC_SOURCE_TYPE');found.add(path.relative_to(root).as_posix())
    need(found==(set(source_targets())-{DIAGNOSTIC_PATH})|{INPUTS_PATH},'PUBLIC_SOURCE_ALLOWLIST')


def publication_gate():
    need(PINS_BOUND is True,'PREPARATION_PUBLICATION_NOT_BOUND')
    need(type(PUBLIC_INPUTS_SHA) is str and re.fullmatch('[0-9a-f]{64}',PUBLIC_INPUTS_SHA),'PUBLIC_INPUTS_PIN')
    for count in (EXPECTED_PREPARATION_COUNT,EXPECTED_DELIVERY_COUNT):
        need(type(count) is int and 0<count<1024,'EXPECTED_TEST_COUNT_PIN')


def public_inputs(raw):
    need(sha(raw)==PUBLIC_INPUTS_SHA,'PUBLIC_INPUTS_PIN');value=strict_json(raw)
    need(type(value) is dict and type(value.get('schema')) is int and value.get('schema')==1 and value.get('feature_id')=='P2_RETAINED_RECOVERY','PUBLIC_INPUTS_SCHEMA')
    need(type(value.get('public_files')) is dict and set(value['public_files'])==set(source_targets()),'EXACT_PUBLIC_FILES')
    for path,pin in value['public_files'].items():
        safe_name(path);need(type(pin) is dict and set(pin)=={'size','sha256','target'} and
            type(pin['size']) is int and 0<pin['size']<=1048576 and type(pin['sha256']) is str and
            re.fullmatch('[0-9a-f]{64}',pin['sha256']) and pin['target']==source_targets()[path],'PUBLIC_FILE_PIN')
    need(value.get('preparation_test_modules')==list(PREP_MODULES) and
         value.get('delivery_test_modules')==list(DELIVERY_MODULES),'EXACT_PUBLIC_MODULES')
    need(type(value.get('preparation_expected_tests')) is int and value['preparation_expected_tests']==EXPECTED_PREPARATION_COUNT and
         type(value.get('delivery_expected_tests')) is int and value['delivery_expected_tests']==EXPECTED_DELIVERY_COUNT and
         value.get('requires_zero_errors_failures_skips') is True and value.get('outer_test_timeout_seconds')==180,'PUBLIC_TEST_CONTRACT')
    need(value.get('host_operations')=='NOT_RUN' and value.get('private_plan_validation')=='NOT_PERFORMED' and
         value.get('production_resume')=='NOT_EXECUTED' and value.get('install_admission')=='NOT_GRANTED','PUBLIC_SCOPE_DECLARATION')
    need(value.get('preparation_root_leaf')=='epoch7-preparation-candidate-r7-fresh' and
         value.get('kit_root_leaf')==KIT_TARGET,'CANDIDATE_ROOT_BINDING')
    need(value.get('required_r7_factory_test')==FACTORY_TEST,'GENUINE_R7_FACTORY_TEST_REQUIRED')
    readiness=value.get('delivery_readiness')
    need(type(readiness) is dict and type(readiness.get('publication_bound')) is bool and
        readiness=={'publication_bound':DELIVERY_PUBLICATION_BOUND,'source_commit':DELIVERY_SOURCE_COMMIT},'DELIVERY_READINESS_DECLARATION')
    for name,pin in FROZEN_TEST_FIXTURES.items():need(value['public_files'][PREP_PREFIX+name]['sha256']==pin,'FROZEN_TEST_FIXTURE_PIN')
    pin=value['public_files'][DIAGNOSTIC_PATH]
    need(pin['sha256']==DIAGNOSTIC_SHA and pin['size']==DIAGNOSTIC_SIZE,'HISTORICAL_DIAGNOSTIC_PIN')
    workflow=value.get('workflow');need(type(workflow) is dict and set(workflow)=={'path','size','sha256'} and
        workflow['path']==WORKFLOW_PATH and type(workflow['size']) is int and 0<workflow['size']<=65536 and
        type(workflow['sha256']) is str and re.fullmatch('[0-9a-f]{64}',workflow['sha256']),'WORKFLOW_PIN')
    fixture=value.get('r7_fixture');need(type(fixture) is dict and set(fixture)=={'archive_sha256','archive_bytes','manifest_sha256','files'} and
        fixture['archive_sha256']==ARCHIVE_SHA and type(fixture['archive_bytes']) is int and fixture['archive_bytes']==ARCHIVE_SIZE and
        fixture['manifest_sha256']==MANIFEST_SHA and type(fixture['files']) is dict and len(fixture['files'])==253,'EXACT_R7_FIXTURE')
    for name,pin in fixture['files'].items():
        safe_name(name);need(type(pin) is str and re.fullmatch('[0-9a-f]{64}',pin),'R7_FIXTURE_FILE_PIN')
    return value


def inspect_fixture(archive,extractor_raw,inputs):
    need(len(archive)==ARCHIVE_SIZE and sha(archive)==ARCHIVE_SHA,'ARCHIVE_PIN')
    need(len(extractor_raw)==EXTRACTOR_SIZE and sha(extractor_raw)==EXTRACTOR_SHA,'EXTRACTOR_PIN')
    module=types.ModuleType('verified_preparation_fixture_extractor');module.__file__='<verified-r7-extractor>'
    exec(compile(extractor_raw,module.__file__,'exec',dont_inherit=True),module.__dict__)
    files,unused=module.inspect_archive(archive,ARCHIVE_SHA,ENTRY_SHA,MANIFEST_SHA)
    need(len(files)==253 and {name:sha(raw) for name,raw in files.items()}==inputs['r7_fixture']['files'],'R7_FIXTURE_FILE_MAP')
    entry=types.ModuleType('verified_preparation_fixture_entry');entry.__file__='<verified-r7-entry>'
    exec(compile(files['epoch7_recovery_entry.py'],entry.__file__,'exec',dont_inherit=True),entry.__dict__)
    manifest=entry.validate_manifest(entry.decode(files[entry.MANIFEST]));cache={name:raw for name,raw in files.items() if name!=entry.MANIFEST}
    entry.validate_runtime(manifest,cache)
    need(len(cache)==252 and len(manifest['files'])==252,'R7_CACHE_COUNT')
    need(manifest['kit_source_commit']==SOURCE and manifest['kit_source_tree']==TREE and
        manifest['runtime_source_commit']==RUNTIME_SOURCE and manifest['runtime_source_tree']==RUNTIME_TREE and
        manifest['runtime_manifest_sha256']==RUNTIME_MANIFEST_SHA,'R7_SOURCE_PROVENANCE')
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


def terminal(raw,expected=None,network=False):
    expected=EXPECTED_PREPARATION_COUNT if expected is None else expected
    need(type(raw) is bytes and 0<len(raw)<=MAX_LOG,'TERMINAL_LOG_BOUND')
    lines=raw.splitlines();need(lines and len(lines[-1])<=4096,'TERMINAL_ABSENT_OR_BOUND')
    value=strict_json(lines[-1])
    fields={'schema','state','tests','errors','failures','skips','python','host_NOT_RUN','privateplan_NOT_RUN'}
    if network:fields.add('network_NOT_RUN')
    need(type(value) is dict and set(value)==fields,'TERMINAL_SCHEMA')
    if network:need(value['network_NOT_RUN'] is True,'PORTABLE_NETWORK_SCOPE')
    need(type(value['schema']) is int and value['schema']==1 and value['state']=='PASS','TERMINAL_STATE')
    need(type(value['tests']) is int and value['tests']==expected,'EXACT_PORTABLE_TEST_COUNT')
    for key in ('errors','failures','skips'):need(type(value[key]) is int and value[key]==0,'PORTABLE_FAILURE_OR_SKIP')
    need(value['host_NOT_RUN'] is True and value['privateplan_NOT_RUN'] is True,'PORTABLE_PRIVATE_OR_HOST_SCOPE')
    need(type(value['python']) is str and value['python']==sys.version.split()[0],'TERMINAL_INTERPRETER')
    return value


def delivery_readiness(raw):
    rows={name:[] for name in ('PINS_BOUND','PUBLICATION_COMMIT')}
    for node in ast.parse(raw.decode('utf-8')).body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in rows:rows[target.id].append(ast.literal_eval(node.value))
    need(rows=={'PINS_BOUND':[DELIVERY_PUBLICATION_BOUND],'PUBLICATION_COMMIT':[DELIVERY_SOURCE_COMMIT]} and
        len(rows['PINS_BOUND'])==1 and type(rows['PINS_BOUND'][0]) is bool,'DELIVERY_RUNTIME_READINESS_MISMATCH')
    need(type(DELIVERY_PUBLICATION_BOUND) is bool,'DELIVERY_PUBLICATION_STATE')
    if DELIVERY_PUBLICATION_BOUND:
        need(type(DELIVERY_SOURCE_COMMIT) is str and re.fullmatch('[0-9a-f]{40}',DELIVERY_SOURCE_COMMIT),'DELIVERY_SOURCE_COMMIT_REQUIRED')
    else:need(DELIVERY_SOURCE_COMMIT is None,'UNBOUND_DELIVERY_COMMIT_FORBIDDEN')
    return {'publication_bound':DELIVERY_PUBLICATION_BOUND,'source_commit':DELIVERY_SOURCE_COMMIT,
        'state':'BOUND_SOURCE_CANDIDATE_ONLY' if DELIVERY_PUBLICATION_BOUND else 'NOT_READY'}


def checkout_records(root,head):
    paths=set(source_targets())|{INPUTS_PATH,GATE_PATH,CONTRACT_PATH,WORKFLOW_PATH,ARCHIVE_PATH,EXTRACTOR_PATH}
    records={path:verified_path(root,head,path,ARCHIVE_SIZE if path==ARCHIVE_PATH else 1048576) for path in sorted(paths)}
    need(pathlib.Path(__file__).read_bytes()==records[GATE_PATH],'CHECKPOINT_NOT_EXACT_HEAD')
    inputs=public_inputs(records[INPUTS_PATH])
    for path,pin in inputs['public_files'].items():
        need(len(records[path])==pin['size'] and sha(records[path])==pin['sha256'],'PUBLIC_SOURCE_HASH')
    pin=inputs['workflow'];need(len(records[WORKFLOW_PATH])==pin['size'] and sha(records[WORKFLOW_PATH])==pin['sha256'],'WORKFLOW_PIN')
    delivery_readiness(records[DELIVERY_PREFIX+'epoch7_prepare_delivery.py'])
    return records,inputs


def worker(root=None):
    publication_gate();need(os.getsid(0)==os.getpid(),'WORKER_OWNED_SESSION_REQUIRED')
    root=pathlib.Path(root).resolve() if root else pathlib.Path(__file__).resolve().parents[1]
    head=git(root,['rev-parse','--verify','HEAD']);public_inventory(root)
    records,inputs=checkout_records(root,head)
    files=inspect_fixture(records[ARCHIVE_PATH],records[EXTRACTOR_PATH],inputs)
    preparation={name:records[PREP_PREFIX+name] for name in PREP_FILES}
    delivery={name:records[DELIVERY_PREFIX+name] for name in DELIVERY_FILES}
    for name in PRODUCTION_FILES:delivery['fixtures/preparation-source/'+name]=preparation[name]
    delivery['fixtures/diagnose_preparation.py']=records[DIAGNOSTIC_PATH]
    delivery['fixtures/recovery-kit-manifest.json']=files['recovery-kit-manifest.json']
    temporary=pathlib.Path(tempfile.mkdtemp(prefix='.preparation-r7-ci-',dir=str(root)));primary=None
    try:
        prep=temporary/PREP_TARGET;kit=temporary/KIT_TARGET;deliver=temporary/DELIVERY_TARGET
        materialize(prep,preparation);materialize(kit,files);materialize(deliver,delivery)
        code,log=run_child([sys.executable,'-I','-B','-S',str(prep/'run_local_tests.py'),'--portable','--kit-root',str(kit)],temporary,180,new_session=False)
        print(log[-65536:].decode('utf-8','replace'));need(code==0,'PREPARATION_CHILD_EXIT');prepared=terminal(log,EXPECTED_PREPARATION_COUNT)
        code,log=run_child([sys.executable,'-I','-B','-S',str(deliver/'run_local_tests.py')],temporary,180,new_session=False)
        print(log[-65536:].decode('utf-8','replace'));need(code==0,'DELIVERY_CHILD_EXIT');delivered=terminal(log,EXPECTED_DELIVERY_COUNT,network=True)
        verify_materialized(prep,preparation);verify_materialized(kit,files);verify_materialized(deliver,delivery)
        public_inventory(root);need(git(root,['rev-parse','--verify','HEAD'])==head,'HEAD_CHANGED')
        for path,raw in records.items():need(verified_path(root,head,path,ARCHIVE_SIZE if path==ARCHIVE_PATH else 1048576)==raw,'INPUT_CHANGED_AFTER_TEST')
        report={'kind':'EXACT_PUBLIC_R7_FRESH_PREPARATION_CHECKPOINT','schema':1,'head':head,'public_inputs_sha256':PUBLIC_INPUTS_SHA,
            'public_file_count':len(source_targets()),'archive_files':253,'cache_files':252,'archive_sha256':ARCHIVE_SHA,'manifest_sha256':MANIFEST_SHA,
            'preparation':prepared,'delivery':delivered,'delivery_readiness':delivery_readiness(delivery['epoch7_prepare_delivery.py']),'required_r7_factory_test':FACTORY_TEST,'success':True,'host_operations':'NOT_RUN','private_plan_validation':'NOT_PERFORMED',
            'production_resume':'NOT_EXECUTED','production_admission':'NOT_GRANTED'}
    except BaseException as error:primary=error;raise
    finally:
        try:shutil.rmtree(str(temporary))
        except BaseException:
            if primary is not None:primary.preparation_ci_cleanup_unknown=True
            else:raise
    print(json.dumps(report,sort_keys=True));return report


class PreparationCheckpoint(unittest.TestCase):
    def test_exact_public_r7_fresh_preparation(self):
        code,raw=run_child([sys.executable,'-I','-B','-S',str(pathlib.Path(__file__).resolve()),'--worker'],pathlib.Path(__file__).resolve().parents[1],420)
        print(raw[-65536:].decode('utf-8','replace'));self.assertEqual(code,0,'PREPARATION_CHECKPOINT_FAILED')
        report=strict_json(raw.splitlines()[-1]);self.assertEqual(report['kind'],'EXACT_PUBLIC_R7_FRESH_PREPARATION_CHECKPOINT');self.assertIs(report['success'],True)
        self.assertEqual(report['public_inputs_sha256'],PUBLIC_INPUTS_SHA);self.assertEqual(report['preparation']['tests'],EXPECTED_PREPARATION_COUNT)
        self.assertEqual(report['delivery']['tests'],EXPECTED_DELIVERY_COUNT)


if __name__=='__main__':
    if sys.argv[1:]==['--worker']:worker()
    else:unittest.main()
