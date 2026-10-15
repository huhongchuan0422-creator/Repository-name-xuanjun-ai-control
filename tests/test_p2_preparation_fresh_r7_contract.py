"""Public CI boundary tests; synthetic metadata plus authenticated public R7 archive."""
import copy,ctypes,hashlib,json,os,pathlib,signal,subprocess,sys,tempfile,time,types,unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent
PUBLISHED=HERE.parent/'evidence/p2-epoch7-access-repair-20261014'
if (PUBLISHED/'artifacts/epoch7-kit-dc18f73e.tar.gz').is_file():
    EXTRACTOR=PUBLISHED/'recovery-kit-source/tools/extract_epoch7_kit.py'
    ARCHIVE=PUBLISHED/'artifacts/epoch7-kit-dc18f73e.tar.gz'
else:
    EXTRACTOR=HERE.parent/'r7-integration-candidate/tools/extract_epoch7_kit.py'
    ARCHIVE=HERE.parent/'r7-integration-candidate/selected-artifact-dc18f73e/epoch7-recovery-kit.tar.gz'


def gate_module():
    path=HERE/'test_p2_preparation_fresh_r7.py';m=types.ModuleType('preparation_gate_fixture');m.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__)
    return m


def fixture_inputs(m):
    archive=ARCHIVE.read_bytes();extractor=EXTRACTOR.read_bytes()
    if len(archive)!=m.ARCHIVE_SIZE or m.sha(archive)!=m.ARCHIVE_SHA:raise ValueError('TEST_ARCHIVE_PIN')
    if len(extractor)!=m.EXTRACTOR_SIZE or m.sha(extractor)!=m.EXTRACTOR_SHA:raise ValueError('TEST_EXTRACTOR_PIN')
    x=types.ModuleType('verified_fixture_extractor');exec(compile(extractor,str(EXTRACTOR),'exec'),x.__dict__)
    files,unused=x.inspect_archive(archive,m.ARCHIVE_SHA,m.ENTRY_SHA,m.MANIFEST_SHA)
    workflow=HERE/'p2-preparation-fresh-r7.yml'
    if not workflow.exists():workflow=HERE.parent/m.WORKFLOW_PATH
    raw=workflow.read_bytes()
    public={path:{'size':1,'sha256':'0'*64,'target':target} for path,target in m.source_targets().items()}
    public[m.DIAGNOSTIC_PATH].update(size=m.DIAGNOSTIC_SIZE,sha256=m.DIAGNOSTIC_SHA)
    for name,pin in m.FROZEN_TEST_FIXTURES.items():public[m.PREP_PREFIX+name]['sha256']=pin
    return {'schema':1,'feature_id':'P2_RETAINED_RECOVERY','public_files':public,
        'preparation_test_modules':list(m.PREP_MODULES),'delivery_test_modules':list(m.DELIVERY_MODULES),
        'required_r7_factory_test':m.FACTORY_TEST,'delivery_readiness':{'publication_bound':False,'source_commit':None},
        'preparation_expected_tests':187,'delivery_expected_tests':84,'requires_zero_errors_failures_skips':True,
        'outer_test_timeout_seconds':180,'host_operations':'NOT_RUN','private_plan_validation':'NOT_PERFORMED',
        'production_resume':'NOT_EXECUTED','install_admission':'NOT_GRANTED',
        'preparation_root_leaf':'epoch7-preparation-candidate-r7-fresh','kit_root_leaf':'epoch7-recovery-candidate-r7',
        'workflow':{'path':m.WORKFLOW_PATH,'size':len(raw),'sha256':m.sha(raw)},
        'r7_fixture':{'archive_bytes':m.ARCHIVE_SIZE,'archive_sha256':m.ARCHIVE_SHA,'manifest_sha256':m.MANIFEST_SHA,
        'files':{name:m.sha(raw) for name,raw in files.items()}}}


INPUT_FIXTURE=fixture_inputs(gate_module())
def inputs_raw():return json.dumps(INPUT_FIXTURE,sort_keys=True).encode('ascii')


def module():
    m=gate_module();m.PINS_BOUND=True;m.PUBLIC_INPUTS_SHA=m.sha(inputs_raw());m.DELIVERY_PUBLICATION_BOUND=False;m.DELIVERY_SOURCE_COMMIT=None
    m.EXPECTED_PREPARATION_COUNT=INPUT_FIXTURE['preparation_expected_tests'];m.EXPECTED_DELIVERY_COUNT=INPUT_FIXTURE['delivery_expected_tests']
    return m

class ContractTests(unittest.TestCase):
    def setUp(self):self.m=module()
    def test_pending_gate_rejects(self):
        self.m.PINS_BOUND=False
        with self.assertRaisesRegex(ValueError,'NOT_BOUND'):self.m.publication_gate()
    def test_public_inputs_exact(self):self.m.public_inputs(inputs_raw())
    def test_public_source_allowlist_rejects_missing_extra_private(self):
        for kind in ('missing','extra','private'):
            value=json.loads(inputs_raw().decode('ascii'))
            if kind=='missing':value['public_files'].pop(self.m.PREP_PREFIX+'epoch7_prepare.py')
            elif kind=='extra':value['public_files'][self.m.PREP_PREFIX+'new.py']={'size':1,'sha256':'1'*64,'target':'new.py'}
            else:value['public_files'][self.m.PREP_PREFIX+'test_epoch7_prepare_private.py']=value['public_files'].pop(self.m.PREP_PREFIX+'test_epoch7_prepare.py')
            raw=json.dumps(value).encode();self.m.PUBLIC_INPUTS_SHA=self.m.sha(raw)
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'EXACT_PUBLIC'):self.m.public_inputs(raw)
    def test_public_inventory_refuses_unlisted_private_file(self):
        with tempfile.TemporaryDirectory(dir=str(HERE)) as tmp:
            root=pathlib.Path(tmp)
            for name in (set(self.m.source_targets())-{self.m.DIAGNOSTIC_PATH})|{self.m.INPUTS_PATH}:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'public fixture')
            self.m.public_inventory(root)
            (root/self.m.PREP_PREFIX/'test_epoch7_prepare_private.py').write_bytes(b'do not run')
            with self.assertRaisesRegex(ValueError,'PUBLIC_SOURCE_ALLOWLIST'):self.m.public_inventory(root)
    def test_input_pin_and_duplicate_reject(self):
        with self.assertRaisesRegex(ValueError,'PUBLIC_INPUTS_PIN'):self.m.public_inputs(b'{}')
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):self.m.strict_json(b'{"a":1,"a":2}')
    def test_public_test_contract_rejects(self):
        for key,value in [('preparation_expected_tests',True),('preparation_expected_tests',1),('requires_zero_errors_failures_skips',False),('outer_test_timeout_seconds',360),('private_plan_validation','PERFORMED')]:
            row=json.loads(inputs_raw().decode('ascii'));row[key]=value;raw=json.dumps(row).encode();self.m.PUBLIC_INPUTS_SHA=self.m.sha(raw)
            with self.subTest(key=key),self.assertRaises(ValueError):self.m.public_inputs(raw)
    def terminal(self):
        return {'schema':1,'state':'PASS','tests':self.m.EXPECTED_PREPARATION_COUNT,'errors':0,'failures':0,'skips':0,'python':sys.version.split()[0],'host_NOT_RUN':True,'privateplan_NOT_RUN':True}
    def test_terminal_exact_success(self):self.assertEqual(self.m.terminal(json.dumps(self.terminal()).encode())['state'],'PASS')
    def test_terminal_missing_count_skip_error_scope_types_reject(self):
        for key,value in [('tests',1),('tests',True),('errors',1),('failures',1),('skips',1),('skips',False),('privateplan_NOT_RUN',False),('host_NOT_RUN',False),('python','0.0.0'),('state','FAIL')]:
            row=self.terminal();row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.m.terminal(json.dumps(row).encode())
        with self.assertRaises(ValueError):self.m.terminal(b'not json')
        with self.assertRaises(ValueError):self.m.terminal(b'')
    def test_terminal_trailing_nonterminal_rejects(self):
        with self.assertRaises(ValueError):self.m.terminal(json.dumps(self.terminal()).encode()+b'\nextra')
    def test_actual_archive_exact_map(self):
        value=self.m.public_inputs(inputs_raw())
        files=self.m.inspect_fixture(ARCHIVE.read_bytes(),EXTRACTOR.read_bytes(),value)
        self.assertEqual(len(files),253);self.assertNotIn('test_epoch7_prepare_private.py',files)
    def test_archive_extractor_map_tamper_rejects(self):
        value=self.m.public_inputs(inputs_raw());archive=ARCHIVE.read_bytes();extractor=EXTRACTOR.read_bytes()
        with self.assertRaisesRegex(ValueError,'ARCHIVE_PIN'):self.m.inspect_fixture(archive+b'X',extractor,value)
        with self.assertRaisesRegex(ValueError,'EXTRACTOR_PIN'):self.m.inspect_fixture(archive,extractor+b'X',value)
        value['r7_fixture']['files']['epoch7_recovery_entry.py']='0'*64
        with self.assertRaisesRegex(ValueError,'R7_FIXTURE_FILE_MAP'):self.m.inspect_fixture(archive,extractor,value)
    def test_materialization_safe_exclusive_and_inventory(self):
        with tempfile.TemporaryDirectory(dir=str(HERE)) as tmp:
            root=pathlib.Path(tmp)/'fixture';files={'safe/file.py':b'print(1)\n'}
            self.m.materialize(root,files);self.m.verify_materialized(root,files)
            self.assertEqual((root/'safe/file.py').stat().st_mode&0o777,0o444)
            with self.assertRaisesRegex(ValueError,'ALREADY_EXISTS'):self.m.materialize(root,files)
            (root/'extra').write_bytes(b'extra')
            with self.assertRaisesRegex(ValueError,'INVENTORY'):self.m.verify_materialized(root,files)
    def test_materialization_traversal_refuses(self):
        for name in ('../outside','/absolute','a//b','a/../b','x.pyc'):
            with self.subTest(name=name),self.assertRaises(ValueError):self.m.safe_name(name)
    def test_materialization_symlink_and_zero_write_refuse(self):
        with tempfile.TemporaryDirectory(dir=str(HERE)) as tmp:
            root=pathlib.Path(tmp)/'fixture';self.m.materialize(root,{'a':b'x'});os.symlink('/tmp',str(root/'alias'))
            with self.assertRaisesRegex(ValueError,'SYMLINK'):self.m.verify_materialized(root,{'a':b'x'})
            with mock.patch.object(self.m.os,'write',return_value=0):
                with self.assertRaisesRegex(ValueError,'NO_PROGRESS'):self.m.materialize(pathlib.Path(tmp)/'second',{'x':b'x'})
    def test_materialize_close_does_not_replace_write_primary(self):
        with tempfile.TemporaryDirectory(dir=str(HERE)) as tmp:
            primary=KeyboardInterrupt();real=self.m.os.close
            def close(fd):real(fd);raise OSError('synthetic close failure')
            with mock.patch.object(self.m.os,'write',side_effect=primary),mock.patch.object(self.m.os,'close',side_effect=close):
                with self.assertRaises(KeyboardInterrupt) as caught:self.m.materialize(pathlib.Path(tmp)/'fixture',{'x':b'x'})
            self.assertIs(caught.exception,primary);self.assertTrue(primary.preparation_ci_cleanup_unknown)
    def test_real_local_child_bounded_output(self):
        code,raw=self.m.run_child([sys.executable,'-I','-B','-S','-c','print("synthetic")'],HERE,5)
        self.assertEqual((code,raw),(0,b'synthetic\n'))
    def test_real_child_timeout_kills_and_reaps(self):
        with mock.patch.object(self.m.subprocess,'Popen',wraps=subprocess.Popen) as popen:
            with self.assertRaises(subprocess.TimeoutExpired):self.m.run_child([sys.executable,'-I','-B','-S','-c','import time;time.sleep(10)'],HERE,.05)
        # Actual process lifetime handled by the original Popen; no host command.
    def test_child_cleanup_preserves_primary(self):
        child=mock.Mock(returncode=None,pid=123);primary=KeyboardInterrupt();child.wait.side_effect=OSError('reap')
        with mock.patch.object(self.m.subprocess,'Popen',return_value=child),mock.patch.object(self.m.os,'waitid',side_effect=primary),mock.patch.object(self.m.os,'killpg',side_effect=OSError('signal')):
            with self.assertRaises(KeyboardInterrupt) as caught:self.m.run_child(['synthetic'],HERE,1)
        self.assertIs(caught.exception,primary);self.assertTrue(primary.preparation_ci_cleanup_unknown);self.assertEqual(child.wait.call_count,1)
    def test_inner_interrupted_already_reaped_child_is_not_signaled(self):
        child=mock.Mock(returncode=None,pid=123);primary=KeyboardInterrupt()
        def wait(**unused):child.returncode=0;raise primary
        child.wait.side_effect=wait
        with mock.patch.object(self.m.subprocess,'Popen',return_value=child),mock.patch.object(self.m.os,'kill') as kill:
            with self.assertRaises(KeyboardInterrupt) as caught:self.m.run_child(['synthetic'],HERE,1,new_session=False)
        self.assertIs(caught.exception,primary);kill.assert_not_called();child.wait.assert_called_once_with(timeout=1)
    def test_outer_late_terminal_status_remains_timeout(self):
        child=mock.Mock(returncode=None,pid=123);child.wait.return_value=0
        with mock.patch.object(self.m.subprocess,'Popen',return_value=child),mock.patch.object(self.m.os,'waitid',return_value=types.SimpleNamespace(si_pid=123)),mock.patch.object(self.m.time,'monotonic',side_effect=[0,0,2]),mock.patch.object(self.m.os,'killpg') as kill:
            with self.assertRaises(subprocess.TimeoutExpired):self.m.run_child(['synthetic'],HERE,1)
        kill.assert_called_once_with(123,signal.SIGKILL);child.wait.assert_called_once_with(timeout=5)
    def test_unknown_leader_never_signals_reused_group(self):
        child=mock.Mock(returncode=None,pid=123);child.wait.return_value=0
        with mock.patch.object(self.m.subprocess,'Popen',return_value=child),mock.patch.object(self.m.os,'waitid',side_effect=ChildProcessError()),mock.patch.object(self.m.os,'killpg') as kill:
            with self.assertRaisesRegex(RuntimeError,'OWNERSHIP_UNKNOWN') as caught:self.m.run_child(['synthetic'],HERE,1)
        kill.assert_not_called();child.wait.assert_called_once_with(timeout=5)
        self.assertTrue(caught.exception.preparation_ci_cleanup_unknown)
    def test_real_outer_timeout_contains_nested_child_group(self):
        libc=ctypes.CDLL(None,use_errno=True);old=ctypes.c_int()
        self.assertEqual(libc.prctl(37,ctypes.byref(old),0,0,0),0)
        self.assertEqual(libc.prctl(36,1,0,0,0),0)
        pid=None
        try:
            with tempfile.TemporaryDirectory(dir=str(HERE)) as tmp:
                record=str(pathlib.Path(tmp)/'nested.pid')
                child_script="import os,time\nwith open(%r,'w') as f:f.write(str(os.getpid()))\ntime.sleep(30)\n"%record
                gate=str(HERE/'test_p2_preparation_fresh_r7.py')
                script="import pathlib,sys,types\nm=types.ModuleType('nested_gate_fixture');m.__file__=%r\nexec(compile(pathlib.Path(m.__file__).read_bytes(),m.__file__,'exec'),m.__dict__)\nm.run_child([sys.executable,'-I','-B','-S','-c',%r],pathlib.Path(%r),30,new_session=False)\n"%(gate,child_script,str(HERE))
                with self.assertRaises(subprocess.TimeoutExpired):self.m.run_child([sys.executable,'-I','-B','-S','-c',script],HERE,3)
                pid=int(pathlib.Path(record).read_text());deadline=time.monotonic()+5
                while True:
                    try:got,status=os.waitpid(pid,os.WNOHANG)
                    except ChildProcessError:pid=None;raise
                    if got==pid:pid=None;break
                    if time.monotonic()>deadline:self.fail('NESTED_CHILD_NOT_REAPED')
                    time.sleep(.01)
                self.assertTrue(os.WIFSIGNALED(status));self.assertEqual(os.WTERMSIG(status),signal.SIGKILL)
        finally:
            if pid is not None:
                try:os.kill(pid,signal.SIGKILL)
                except ProcessLookupError:pass
                deadline=time.monotonic()+5
                while True:
                    try:got,unused=os.waitpid(pid,os.WNOHANG)
                    except ChildProcessError:break
                    if got==pid:break
                    if time.monotonic()>=deadline:raise RuntimeError('TEST_NESTED_REAP_UNKNOWN')
                    time.sleep(.01)
            self.assertEqual(libc.prctl(36,old.value,0,0,0),0)
    def test_output_cap_rejects(self):
        self.m.MAX_LOG=32
        with self.assertRaisesRegex(ValueError,'LOG_BOUND'):self.m.run_child([sys.executable,'-I','-B','-S','-c','print("x"*64)'],HERE,5)

    def test_delivery_count_and_r7_fixture_pins_are_required(self):
        for key,value in [('delivery_expected_tests',True),('delivery_expected_tests',1),('r7_fixture',{})]:
            row=json.loads(inputs_raw().decode('ascii'));row[key]=value;raw=json.dumps(row).encode();self.m.PUBLIC_INPUTS_SHA=self.m.sha(raw)
            with self.subTest(key=key),self.assertRaises(ValueError):self.m.public_inputs(raw)
    def test_integration_terminal_requires_its_exact_count_and_zero_skips(self):
        row=self.terminal();row['tests']=self.m.EXPECTED_DELIVERY_COUNT
        self.m.terminal(json.dumps(row).encode(),self.m.EXPECTED_DELIVERY_COUNT)
        row['skips']=1
        with self.assertRaises(ValueError):self.m.terminal(json.dumps(row).encode(),self.m.EXPECTED_DELIVERY_COUNT)

    def test_workflow_preserves_reviewed_acl_and_readonly_mechanics(self):
        name='p2-preparation-fresh-r7.yml'
        path=HERE/name if (HERE/name).exists() else HERE.parent/'.github/workflows'/name
        raw=path.read_text()
        for line in ("      - 'evidence/p2-epoch7-access-repair-20261014/preparation-delivery-r7-fresh/**'\n",
                     "      - 'evidence/p2-epoch7-access-repair-20261014/preparation-fresh-r7-ci/**'\n",
                     "      - 'evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-dc18f73e.tar.gz'\n",
                     "      - 'evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tools/extract_epoch7_kit.py'\n"):
            self.assertIn(line,raw);raw=raw.replace(line,'')
        for new,old in [('P2 Public Fresh Preparation R7','P2 Public Preparation R6 Contracts'),
                        ('preparation-source-r7-fresh/**','preparation-source-r6-contracts/**'),
                        ('test_p2_preparation_fresh_r7','test_p2_preparation_contracts_r6'),
                        ('p2-preparation-fresh-r7','p2-preparation-contracts-r6'),
                        ('timeout-minutes: 10','timeout-minutes: 8'),
                        ('frozen R7 fixture and preparation/delivery tests','historical fixture and portable preparation tests')]:
            self.assertIn(new,raw);raw=raw.replace(new,old)
        self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(),'59aa98fd157fc50c6fd4ca156140bfe8e700f996c6b07e104bf770c7943a0976')

    def test_delivery_terminal_requires_network_not_run(self):
        row=self.terminal();row['tests']=self.m.EXPECTED_DELIVERY_COUNT;row['network_NOT_RUN']=True
        self.m.terminal(json.dumps(row).encode(),self.m.EXPECTED_DELIVERY_COUNT,network=True)
        for value in (False,1,None):
            row['network_NOT_RUN']=value
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'NETWORK_SCOPE'):
                self.m.terminal(json.dumps(row).encode(),self.m.EXPECTED_DELIVERY_COUNT,network=True)
        row.pop('network_NOT_RUN')
        with self.assertRaisesRegex(ValueError,'TERMINAL_SCHEMA'):
            self.m.terminal(json.dumps(row).encode(),self.m.EXPECTED_DELIVERY_COUNT,network=True)

    def test_r6_archive_cannot_be_relabelled_r7(self):
        value=json.loads(inputs_raw().decode('ascii'))
        for key,wrong in [('manifest_sha256','70c76e30ae8390963f345813f87267bf1d2f024bc01031c8023733c84aa571cc'),
                          ('archive_sha256','600dc31aaf639aee875be1a075c7b544b9c8c5210fee24013ce614bc69ad5a83'),
                          ('archive_bytes',1032979)]:
            changed=copy.deepcopy(value);changed['r7_fixture'][key]=wrong
            raw=json.dumps(changed).encode();self.m.PUBLIC_INPUTS_SHA=self.m.sha(raw)
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'EXACT_R7_FIXTURE'):self.m.public_inputs(raw)

    def test_historical_diagnostic_is_exact_and_cannot_be_rebound(self):
        value=json.loads(inputs_raw().decode('ascii'));value['public_files'][self.m.DIAGNOSTIC_PATH]['sha256']='1'*64
        raw=json.dumps(value).encode();self.m.PUBLIC_INPUTS_SHA=self.m.sha(raw)
        with self.assertRaisesRegex(ValueError,'HISTORICAL_DIAGNOSTIC_PIN'):self.m.public_inputs(raw)

    def test_wrong_candidate_root_and_module_scope_refuse(self):
        for key,wrong in [('preparation_root_leaf','epoch7-preparation-candidate-r6-contracts'),
                          ('kit_root_leaf','epoch7-recovery-candidate-r6'),('preparation_test_modules',[]),
                          ('delivery_test_modules',['test_epoch7_prepare_private'])]:
            value=json.loads(inputs_raw().decode('ascii'));value[key]=wrong
            raw=json.dumps(value).encode();self.m.PUBLIC_INPUTS_SHA=self.m.sha(raw)
            with self.subTest(key=key),self.assertRaises(ValueError):self.m.public_inputs(raw)

    def test_source_target_escape_and_size_type_refuse(self):
        for field,wrong in [('target','../../private'),('size',True),('sha256','abc')]:
            value=json.loads(inputs_raw().decode('ascii'));value['public_files'][self.m.PREP_PREFIX+'epoch7_prepare.py'][field]=wrong
            raw=json.dumps(value).encode();self.m.PUBLIC_INPUTS_SHA=self.m.sha(raw)
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'PUBLIC_FILE_PIN'):self.m.public_inputs(raw)

    def test_unbound_runtime_is_explicitly_not_ready(self):
        self.m.DELIVERY_PUBLICATION_BOUND=False;self.m.DELIVERY_SOURCE_COMMIT=None
        row=self.m.delivery_readiness(b'PINS_BOUND=False\nPUBLICATION_COMMIT=None\n')
        self.assertEqual(row,{'publication_bound':False,'source_commit':None,'state':'NOT_READY'})

    def test_bound_runtime_requires_exact_actual_commit_binding(self):
        self.m.DELIVERY_PUBLICATION_BOUND=True;self.m.DELIVERY_SOURCE_COMMIT='a'*40
        row=self.m.delivery_readiness(('PINS_BOUND=True\nPUBLICATION_COMMIT=%r\n'%('a'*40)).encode())
        self.assertEqual(row['state'],'BOUND_SOURCE_CANDIDATE_ONLY')
        for raw in (b'PINS_BOUND=False\nPUBLICATION_COMMIT=None\n',
                    ('PINS_BOUND=True\nPUBLICATION_COMMIT=%r\n'%('b'*40)).encode(),
                    ('PINS_BOUND=True\nPUBLICATION_COMMIT=%r\nPINS_BOUND=False\n'%('a'*40)).encode()):
            with self.assertRaisesRegex(ValueError,'READINESS_MISMATCH'):self.m.delivery_readiness(raw)
        self.m.DELIVERY_SOURCE_COMMIT=None
        with self.assertRaisesRegex(ValueError,'SOURCE_COMMIT_REQUIRED'):
            self.m.delivery_readiness(b'PINS_BOUND=True\nPUBLICATION_COMMIT=None\n')

    def test_factory_identity_and_frozen_baseline_cannot_drift(self):
        for mode in ('factory','baseline'):
            value=json.loads(inputs_raw().decode('ascii'))
            if mode=='factory':value['required_r7_factory_test']='synthetic.stub'
            else:value['public_files'][self.m.PREP_PREFIX+'test_fixtures/epoch7_prepare_frozen_r6.py']['sha256']='0'*64
            raw=json.dumps(value).encode();self.m.PUBLIC_INPUTS_SHA=self.m.sha(raw)
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.m.public_inputs(raw)

    def test_delivery_readiness_rejects_boolean_coercion(self):
        for value in (0,1,None):
            row=json.loads(inputs_raw().decode('ascii'));row['delivery_readiness']['publication_bound']=value
            raw=json.dumps(row).encode();self.m.PUBLIC_INPUTS_SHA=self.m.sha(raw)
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'READINESS_DECLARATION'):self.m.public_inputs(raw)
        with self.assertRaisesRegex(ValueError,'READINESS_MISMATCH'):
            self.m.delivery_readiness(b'PINS_BOUND=0\nPUBLICATION_COMMIT=None\n')

class GitBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.m=module();self.temp=tempfile.TemporaryDirectory(prefix='git-contract-',dir=str(HERE));self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name);(self.root/'fixed.py').write_bytes(b'public synthetic fixture\n')
        self.env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null')
        for args in (['init','-q'],['add','.'],['-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','core.hooksPath=/dev/null','-c','commit.gpgsign=false','commit','-qm','Local synthetic fixture']):
            subprocess.check_call(['/usr/bin/git','-C',str(self.root)]+args,env=self.env,timeout=15)
        self.head=self.m.git(self.root,['rev-parse','--verify','HEAD'])
    def test_exact_checkout_bytes_pass(self):
        self.assertEqual(self.m.verified_path(self.root,self.head,'fixed.py'),b'public synthetic fixture\n')
    def test_uncommitted_change_refuses(self):
        (self.root/'fixed.py').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'EXACT_HEAD_BLOB'):self.m.verified_path(self.root,self.head,'fixed.py')
    def test_missing_file_refuses(self):
        (self.root/'fixed.py').unlink()
        with self.assertRaises(OSError):self.m.verified_path(self.root,self.head,'fixed.py')
    def test_symlink_and_hardlink_refuse(self):
        (self.root/'fixed.py').rename(self.root/'original');os.symlink('original',str(self.root/'fixed.py'))
        with self.assertRaisesRegex(ValueError,'SOURCE_PATH_ALIAS'):self.m.verified_path(self.root,self.head,'fixed.py')
        (self.root/'fixed.py').unlink();os.link(str(self.root/'original'),str(self.root/'fixed.py'))
        with self.assertRaisesRegex(ValueError,'SOURCE_FILE_TYPE'):self.m.verified_path(self.root,self.head,'fixed.py')
    def test_read_size_bound(self):
        with self.assertRaisesRegex(ValueError,'BOUND'):self.m.verified_path(self.root,self.head,'fixed.py',2)

if __name__=='__main__':unittest.main(verbosity=2)
