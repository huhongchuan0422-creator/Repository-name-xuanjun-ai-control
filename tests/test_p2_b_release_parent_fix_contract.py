"""Exact-source, count, isolation, child-ownership and hosted-workflow contracts.

Real Git fixtures are exclusively disposable directories with no remote.
"""
import ast,contextlib,ctypes,hashlib,io,json,os,pathlib,signal,subprocess,sys,tempfile,time,types,unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent
GATE=HERE/'test_p2_b_release_parent_fix.py'
REVIEWED_CHILD_SHA='5414c5b83756c529cf073811282c1c70dbaf796e29e10a21a57dade5849f4a56'


def module():
    value=types.ModuleType('parentfix_adapter_fixture');value.__file__=str(GATE)
    exec(compile(GATE.read_bytes(),str(GATE),'exec'),value.__dict__)
    return value


def workflow():
    return (HERE.parent/'.github/workflows/p2-b-release-parent-fix.yml').read_text()


class AdapterContractTests(unittest.TestCase):
    def setUp(self):self.m=module()
    def test_missing_changed_oversized_source_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            with self.assertRaises(FileNotFoundError):self.m.read_pin(root,'fixed.py',3,self.m.digest(b'abc'))
            for raw in (b'abd',b'abcd',b'ab'):
                (root/'fixed.py').write_bytes(raw)
                with self.subTest(raw=raw),self.assertRaisesRegex(ValueError,'PUBLIC_FILE_PIN'):
                    self.m.read_pin(root,'fixed.py',3,self.m.digest(b'abc'))

    def test_source_symlink_hardlink_and_fifo_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);(root/'real.py').write_bytes(b'abc')
            (root/'alias.py').symlink_to(root/'real.py')
            with self.assertRaisesRegex(ValueError,'PUBLIC_PATH_ALIAS'):self.m.read_pin(root,'alias.py',3,self.m.digest(b'abc'))
            (root/'alias.py').unlink();os.link(str(root/'real.py'),str(root/'alias.py'))
            with self.assertRaisesRegex(ValueError,'PUBLIC_FILE_TYPE'):self.m.read_pin(root,'alias.py',3,self.m.digest(b'abc'))
            (root/'alias.py').unlink();os.mkfifo(str(root/'alias.py'))
            with self.assertRaisesRegex(ValueError,'PUBLIC_FILE_TYPE'):self.m.read_pin(root,'alias.py',3,self.m.digest(b'abc'))

    def test_wrong_archive_never_opens_tar(self):
        with mock.patch.object(self.m.tarfile,'open',side_effect=AssertionError('UNVERIFIED_TAR')):
            with self.assertRaisesRegex(ValueError,'ARCHIVE_PIN'):self.m.archive_files(b'wrong')

    def test_archive_header_and_file_counts_reject(self):
        raw=b'synthetic';self.m.ARCHIVE_SIZE=len(raw);self.m.ARCHIVE_SHA=self.m.digest(raw)
        archive=mock.MagicMock();archive.__enter__.return_value=archive;archive.getmembers.return_value=[]
        with mock.patch.object(self.m.tarfile,'open',return_value=archive):
            with self.assertRaisesRegex(ValueError,'ARCHIVE_HEADER_COUNT'):self.m.archive_files(raw)
            self.m.ARCHIVE_HEADERS=0
            with self.assertRaisesRegex(ValueError,'ARCHIVE_MEMBER_COUNT'):self.m.archive_files(raw)

    def test_materialization_exclusive_and_exact_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)/'fixture';name=next(iter(self.m.SOURCE_TARGETS.values()));files={name:b'synthetic'}
            self.m.materialize(root,files);self.m.check_materialized(root,files)
            with self.assertRaisesRegex(ValueError,'FIXTURE_EXISTS'):self.m.materialize(root,files)
            (root/name).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'FIXTURE_DRIFT'):self.m.check_materialized(root,files)
            (root/'extra').write_bytes(b'extra')
            with self.assertRaisesRegex(ValueError,'FIXTURE_INVENTORY'):self.m.check_materialized(root,files)

    def test_materialization_paths_and_directory_alias_refused(self):
        for name in ('../outside','/absolute','a//b','a/../b','a\\b','a\0b','unlisted.py'):
            with tempfile.TemporaryDirectory() as folder, self.subTest(name=name),self.assertRaises(ValueError):
                self.m.materialize(pathlib.Path(folder)/'fixture',{name:b'x'})
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)/'fixture';self.m.materialize(root,{})
            (root/'alias').symlink_to(root,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'FIXTURE_ALIAS'):self.m.check_materialized(root,{})

    def test_terminal_exact_success_for_all_four_suites(self):
        for name,count in self.m.SUITES:
            value=self.m.summary(name,count)
            self.assertEqual(self.m.terminal(json.dumps(value).encode(),name,count),value)

    def test_terminal_count_skip_error_scope_types_reject(self):
        for key,value in [('tests',34),('tests',True),('errors',1),('failures',1),('skips',1),('skips',False),('host_NOT_RUN',False),('network_NOT_RUN',False),('python','0.0.0'),('suite','other'),('state','FAIL')]:
            row=self.m.summary('reporter',2);row[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.m.terminal(json.dumps(row).encode(),'reporter',2)
        for raw in (b'',b'not json',b'{}',json.dumps(self.m.summary('reporter',2)).encode()+b'\nextra',b'{"state":"FAIL","state":"PASS"}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):self.m.terminal(raw,'reporter',2)

    def test_reviewed_child_mechanics_exact(self):
        raw=GATE.read_text();chunk=raw[raw.index('def output_file_limit():'):raw.index('\ndef summary(')]
        self.assertEqual(hashlib.sha256(chunk.encode()).hexdigest(),REVIEWED_CHILD_SHA)

    def test_real_local_child_bounded_output(self):
        code,raw=self.m.run_child([sys.executable,'-I','-B','-S','-c','print("synthetic")'],HERE,5)
        self.assertEqual((code,raw),(0,b'synthetic\n'))

    def test_real_child_timeout_kills_and_reaps(self):
        with mock.patch.object(self.m.subprocess,'Popen',wraps=subprocess.Popen) as popen:
            with self.assertRaises(subprocess.TimeoutExpired):self.m.run_child([sys.executable,'-I','-B','-S','-c','import time;time.sleep(10)'],HERE,.05)
        self.assertIsNotNone(popen.return_value)

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
            with tempfile.TemporaryDirectory() as tmp:
                record=str(pathlib.Path(tmp)/'nested.pid')
                child_script="import os,time\nwith open(%r,'w') as f:f.write(str(os.getpid()))\ntime.sleep(30)\n"%record
                script="import pathlib,sys,types\nm=types.ModuleType('nested_gate_fixture');m.__file__=%r\nexec(compile(pathlib.Path(m.__file__).read_bytes(),m.__file__,'exec'),m.__dict__)\nm.run_child([sys.executable,'-I','-B','-S','-c',%r],pathlib.Path(%r),30,new_session=False)\n"%(str(GATE),child_script,str(HERE))
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

    def test_worker_requires_owned_session_before_git(self):
        with mock.patch.object(self.m,'publication_pins'),mock.patch.object(self.m.os,'getsid',return_value=1),mock.patch.object(self.m.os,'getpid',return_value=2),mock.patch.object(self.m,'git') as git:
            with self.assertRaisesRegex(ValueError,'WORKER_OWNED_SESSION_REQUIRED'):self.m.worker()
        git.assert_not_called()

    def test_source_target_alias_refuses(self):
        self.m.PINS_BOUND=True;key=next(iter(self.m.SOURCE_TARGETS));self.m.SOURCE_TARGETS=dict(self.m.SOURCE_TARGETS)
        other=next(path for path in self.m.SOURCE_TARGETS if path!=key)
        self.m.SOURCE_TARGETS[other]=self.m.SOURCE_TARGETS[key]
        with self.assertRaisesRegex(ValueError,'EXACT_PUBLIC_TARGETS'):self.m.publication_pins()

    def test_terminal_nonterminal_success_and_duplicate_json_refuse(self):
        raw=json.dumps(self.m.summary('reporter',2)).encode()+b'\nnonterminal'
        with self.assertRaises(ValueError):self.m.terminal(raw,'reporter',2)
        with self.assertRaisesRegex(ValueError,'DUPLICATE_JSON_KEY'):
            self.m.strict_json(b'{"schema":1,"schema":1}')

    def test_publication_unbound_rejects_before_reads(self):
        self.m.PINS_BOUND=False
        with mock.patch.object(self.m,'read_pin') as read:
            with self.assertRaisesRegex(ValueError,'PUBLICATION_NOT_BOUND'):self.m.fixtures(HERE)
        read.assert_not_called()
    def test_exact_constants_and_four_counts(self):
        self.assertEqual(self.m.SUITES,(('consumer',23),('wrapper',39),('pipeline',7),('affected',97)))
        self.assertEqual(self.m.aggregate()['tests'],166)
        self.assertEqual(self.m.aggregate()['preparation_compiler_binding'],'UNBOUND')
        self.assertTrue(self.m.aggregate()['host_NOT_RUN'])
        self.assertEqual((self.m.ARCHIVE_HEADERS,self.m.ARCHIVE_MEMBERS,self.m.KIT_CACHE_FILES),(295,253,252))
        self.assertEqual(self.m.ARCHIVE_SHA,'e9841797571b3f039af8782b0aa1051c11c4b7938a2287abfd433e394b3d1645')
        self.assertEqual(self.m.MANIFEST_SHA,'7b926fda92065d9ff981bfeaad490d5568dd5901d2b1089d1f1dfac94eae8bb4')
    def test_missing_extra_remapped_boolean_source_pins_refuse(self):
        pins=dict(self.m.PINS)
        for mode in ('missing','extra','remapped','boolean_size'):
            self.m.PINS=dict(pins);key=next(iter(pins));size,pin,target=pins[key]
            if mode=='missing':del self.m.PINS[key]
            elif mode=='extra':self.m.PINS['extra.py']=(1,'1'*64,'extra.py')
            elif mode=='remapped':self.m.PINS[key]=(size,pin,'elsewhere.py')
            else:self.m.PINS[key]=(True,pin,target)
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.m.publication_pins()
    def test_missing_duplicate_boolean_suite_counts_refuse(self):
        for suites in ((),(('consumer',23),),tuple(reversed(self.m.SUITES)),(('consumer',True),)+self.m.SUITES[1:]):
            self.m.SUITES=suites
            with self.subTest(suites=suites),self.assertRaisesRegex(ValueError,'EXACT_SUITE_COUNTS_NOT_BOUND'):self.m.publication_pins()
    def test_exact_candidate_and_saved_fixture_layout(self):
        prefix='evidence/p2-epoch7-access-repair-20261014/'
        candidate=prefix+'b-release-parent-fix/'
        self.assertEqual(self.m.KIT_TARGET,'kit/epoch7-recovery-candidate-r7')
        self.assertEqual(len(self.m.PINS),35)
        self.assertEqual(self.m.PINS[candidate+'tests/test_fresh_release_parent.py'][:2],(17229,'1df4eb37f1a7e9dacd3c157d6b69b626db0bb99dc8e9e2fc2c4467be992e67dc'))
        for path,target in self.m.SOURCE_TARGETS.items():
            self.assertNotIn('private',path.lower())
            if path.startswith(candidate):self.assertEqual(target,self.m.CANDIDATE_TARGET+'/'+path[len(candidate):])
        for name in ('epoch7_prepare_data.py','epoch7_topology_projection.py','test_epoch7_prepare_data_r7.py','test_epoch7_topology_projection.py'):
            self.assertEqual(self.m.SOURCE_TARGETS[prefix+'preparation-source-r7-fresh/'+name],'fixtures/r7-saved-preparation-candidate/'+name)
        self.assertEqual(set(self.m.DERIVED_TARGETS),{self.m.CANDIDATE_TARGET+'/baseline-preparation/'+x for x in ('epoch7_prepare_data.py','epoch7_topology_projection.py')})
    def test_public_inventory_rejects_extra_and_alias(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            for name in self.m.SOURCE_TARGETS:
                if not any(name.startswith(prefix+'/') for prefix in self.m.PUBLIC_DIRECTORIES):continue
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture')
            self.m.public_inventory(root)
            path=root/self.m.PUBLIC_DIRECTORIES[0]/'extra.py';path.write_bytes(b'extra')
            with self.assertRaisesRegex(ValueError,'PUBLIC_SOURCE_ALLOWLIST'):self.m.public_inventory(root)
            path.unlink();path.symlink_to(path.parent,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'PUBLIC_SOURCE_ALIAS'):self.m.public_inventory(root)
    def test_workflow_readonly_exact_trigger_and_commands(self):
        text=workflow();trigger=text.split('on:\n',1)[1].split('permissions:\n',1)[0]
        expected={prefix+'/**' for prefix in self.m.PUBLIC_DIRECTORIES}
        expected.update(path for path in self.m.SOURCE_TARGETS if not any(path.startswith(prefix+'/') for prefix in self.m.PUBLIC_DIRECTORIES))
        expected.update((self.m.ARCHIVE_PATH,self.m.GATE_PATH,self.m.CONTRACT_PATH,self.m.WORKFLOW_PATH,self.m.REGISTRY_PATH))
        actual=[line.strip()[3:-1] for line in trigger.splitlines() if line.strip().startswith("- '")]
        self.assertEqual(set(actual),expected);self.assertEqual(len(actual),len(expected))
        self.assertTrue(trigger.startswith('  push:\n    branches: [repair/p2-chatgpt-clean-review-20261013]\n    paths:\n'))
        self.assertIn('permissions:\n  contents: read\n',text);self.assertIn('persist-credentials: false',text)
        commands=[line.strip() for line in text.splitlines() if ' -S tests/' in line]
        self.assertEqual(commands,['python3 -I -B -S tests/test_p2_b_release_parent_fix_contract.py -v','python3 -I -B -S tests/test_p2_b_release_parent_fix.py -v'])
        for bad in ('secrets.','self-hosted','upload-artifact','curl ','wget ','pip ','pull_request_target','workflow_dispatch','chmod 777'):
            self.assertNotIn(bad,text)
    def test_separate_builder_count_and_ephemeral_build_contract(self):
        self.assertEqual(self.m.ADDITIONAL_SUITES,(('builder',24),('binding',10),('delivery',36)))
        self.assertEqual(self.m.aggregate()['tests'],166)
        self.assertEqual(self.m.aggregate()['builder_tests'],24)
        self.assertTrue(self.m.aggregate()['source_bound_build_verified'])
    def test_fixture_umask_is_local_to_disposable_suite_child(self):
        source=GATE.read_text();suite=source.split('def run_suite(root,name):',1)[1].split('def worker():',1)[0]
        self.assertIn('os.umask(0o022)',suite)
        self.assertEqual(source.count('os.umask('),1)
        self.assertIn('umask 0077',workflow())
    def test_hosted_official_python36_clean_native_import_is_mandatory(self):
        text=workflow()
        for expected in ('python:3.6.15-bullseye','python:3.12-bookworm','fail-fast: false','runs-on: ubuntu-22.04','container:',"import ctypes, os, sys, uuid",'ctypes.CDLL(None).getpid()','CLEAN_NATIVE_IMPORT_PASS='):
            self.assertIn(expected,text)
        self.assertNotIn('continue-on-error',text);self.assertNotIn('sys.modules[',text)
        self.assertLess(text.index('Require clean native Python import'),text.index('Verify exact public focused fixture'))
    def test_workflow_preserves_acl_safe_root_owned_ancestry(self):
        text=workflow()
        for expected in ("for path in ('/',):",'info.st_uid==0 and info.st_gid==0',"('system.posix_acl_access','system.posix_acl_default')",'CI_STAGING_ANCESTRY_ACL','"$MKTEMP" -d /xuanjun-p2-parentfix-ci.XXXXXXXX','--no-hardlinks --no-checkout','EXPECTED_TREE=',"rev-parse 'HEAD^{tree}'",'export RUNNER_TEMP="$CI_ROOT/temp" TMPDIR="$CI_ROOT/temp"'):
            self.assertIn(expected,text)
        for tool in ('git','mktemp','chown','id','stat','mkdir'):
            self.assertIn('$(command -v '+tool+')',text)
        self.assertIn('"$GIT" -c safe.directory="$GITHUB_WORKSPACE" -C "$GITHUB_WORKSPACE" rev-parse HEAD',text)
        self.assertIn('"$GIT" -c safe.directory="$GITHUB_WORKSPACE" -C "$GITHUB_WORKSPACE" rev-parse "$GITHUB_SHA^{tree}"',text)
        self.assertIn('"$GIT" -c safe.directory="$GITHUB_WORKSPACE" -c safe.directory="$GITHUB_WORKSPACE/.git" -c core.hooksPath=/dev/null clone',text)
        self.assertEqual(text.count('-c safe.directory='),4)
        for forbidden in ('/usr/bin/mktemp','/usr/bin/chown','config --global','safe.directory=*','safe.directory="*"'):
            self.assertNotIn(forbidden,text)
    def test_selected_compiler_and_delivery_fixture_closure(self):
        prefix='evidence/p2-epoch7-access-repair-20261014/'
        candidate=self.m.CANDIDATE_TARGET
        for folder,public,names in (
            ('preparation-bound','b-release-parent-bound',('epoch7_prepare.py','epoch7_prepare_data.py','epoch7_topology_projection.py','test_compiler_binding.py')),
            ('delivery-candidate','b-release-parent-delivery',('epoch7_prepare_delivery.py','extract_epoch7_compiler_kit.py','test_parentfix_delivery.py','README.md'))):
            for name in names:self.assertEqual(self.m.SOURCE_TARGETS[prefix+public+'/'+name],candidate+'/'+folder+'/'+name)
        self.assertEqual(self.m.PINS[self.m.SELECTED_COMPILER_ARCHIVE_PATH],
            (1045651,'6553938a56b882e17d13029fa9a06787131bb55a5c55bc1138e2b825277b7307',self.m.SELECTED_COMPILER_ARCHIVE_TARGET))
        self.assertEqual(self.m.SELECTED_COMPILER_MANIFEST_SHA,'b33b365ef1fd18458d85bcbbec44d883f3cc33bf859064cbdca6bfc3fad7d571')
        self.assertEqual(self.m.aggregate()['tests'],166)
        self.assertEqual(self.m.aggregate()['builder_tests'],24)
        self.assertEqual(self.m.aggregate()['binding_tests'],10)
        self.assertEqual(self.m.aggregate()['delivery_tests'],36)
    def test_new_suite_routing_isolated_and_preserves_old_test_sources(self):
        source=GATE.read_text()
        self.assertIn("'binding':[candidate/'preparation-bound/test_compiler_binding.py']",source)
        self.assertIn("'delivery':[candidate/'delivery-candidate/test_parentfix_delivery.py']",source)
        self.assertIn("os.environ['EPOCH7_COMPILER_TEST_ARCHIVE']=str(root/SELECTED_COMPILER_ARCHIVE_TARGET)",source)
        self.assertIn("[sys.executable,'-I','-B','-S'",source)
    def test_registry_accepts_other_additions_but_requires_own_exact_registration(self):
        value={'schema_version':1,'features':[{'feature_id':self.m.FEATURE_ID,'status':'IN_DEVELOPMENT',
            'acceptance':{'tests':[self.m.GATE_PATH,self.m.CONTRACT_PATH]}}]}
        packed=lambda v:json.dumps(v).encode('ascii')
        self.m.registry_contract(packed(value))
        future=json.loads(json.dumps(value));future['features'][0]['acceptance']['tests'].insert(0,'tests/test_future.py')
        future['features'][0]['acceptance']['tests'].reverse();self.m.registry_contract(packed(future))
        for mode in ('missing','duplicate','wrong_status','duplicate_feature','bad_path','boolean_schema'):
            candidate=json.loads(json.dumps(value));feature=candidate['features'][0];tests=feature['acceptance']['tests']
            if mode=='missing':tests.remove(self.m.GATE_PATH)
            elif mode=='duplicate':tests.append(self.m.CONTRACT_PATH)
            elif mode=='wrong_status':feature['status']='COMPLETE'
            elif mode=='duplicate_feature':candidate['features'].append(feature)
            elif mode=='bad_path':tests.append('tests/../private.py')
            else:candidate['schema_version']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.m.registry_contract(packed(candidate))
    def test_ci_successor_preserves_published_compiler_source_identity(self):
        self.assertEqual(self.m.COMPILER_SOURCE_COMMIT,'dacd45a2f6888cae7b751cae5becacd3099c1ed2')
        self.assertEqual(self.m.COMPILER_SOURCE_TREE,'f31ae40b6f7c48f09846f6d70f5bb599f4980fe1')
        source=GATE.read_text()
        self.assertIn("'current_checkout':{'commit':head,'tree':tree}",source)
        self.assertIn("'compiler_source':{'commit':COMPILER_SOURCE_COMMIT,'tree':COMPILER_SOURCE_TREE}",source)
        self.assertIn("build_exact_source(work,pathlib.Path(folder)/'artifact',COMPILER_SOURCE_COMMIT,COMPILER_SOURCE_TREE)",source)
        self.assertNotIn("build_exact_source(work,pathlib.Path(folder)/'artifact',head,tree)",source)
    def test_worker_rechecks_head_records_and_fixture_after_each_suite(self):
        for kind,label in (('head','HEAD_CHANGED'),('records','INPUT_CHANGED_AFTER_TEST')):
            reports=[(0,json.dumps(self.m.summary(name,count)).encode()) for name,count in self.m.SUITES+self.m.ADDITIONAL_SUITES]
            heads=['a'*40,'c'*40,('b' if kind=='head' else 'a')*40]
            records=[{},({'changed':b'x'} if kind=='records' else {})]
            with self.subTest(kind=kind),contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(self.m,'publication_pins'))
                stack.enter_context(mock.patch.object(self.m.os,'getsid',return_value=os.getpid()))
                stack.enter_context(mock.patch.object(self.m,'git',side_effect=heads))
                stack.enter_context(mock.patch.object(self.m,'checkout_records',side_effect=records))
                stack.enter_context(mock.patch.object(self.m,'public_inventory'))
                stack.enter_context(mock.patch.object(self.m,'fixtures',return_value={}))
                stack.enter_context(mock.patch.object(self.m,'materialize',return_value=HERE/'synthetic-fixture'))
                check=stack.enter_context(mock.patch.object(self.m,'check_materialized'))
                run=stack.enter_context(mock.patch.object(self.m,'run_child',side_effect=reports))
                stack.enter_context(mock.patch.object(self.m,'clean_import'))
                build=stack.enter_context(mock.patch.object(self.m,'build_exact_source'))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                with self.assertRaisesRegex(ValueError,label):self.m.worker()
                self.assertEqual(run.call_count,7);self.assertEqual(check.call_count,9)
                self.assertEqual(build.call_args[0][2:],(self.m.COMPILER_SOURCE_COMMIT,self.m.COMPILER_SOURCE_TREE))
                self.assertTrue(all(call[2]['new_session'] is False for call in run.mock_calls))
                for call,(name,unused) in zip(run.call_args_list,self.m.SUITES+self.m.ADDITIONAL_SUITES):
                    self.assertEqual(call[0],([sys.executable,'-I','-B','-S',str(GATE),'--suite',str(HERE/'synthetic-fixture'),name],HERE/'synthetic-fixture',180))

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


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    if suite.countTestCases()!=41:raise ValueError('EXACT_ADAPTER_CONTRACT_COUNT')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    ok=result.wasSuccessful() and not result.skipped and result.testsRun==41
    print(json.dumps({'schema':1,'state':'PASS' if ok else 'FAIL','tests':result.testsRun,'errors':len(result.errors),
        'failures':len(result.failures),'skips':len(result.skipped),'python':sys.version.split()[0],
        'host_NOT_RUN':True,'network_NOT_RUN':True},sort_keys=True))
    sys.exit(not ok)
