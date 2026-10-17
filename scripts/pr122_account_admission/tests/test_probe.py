import ast, base64, contextlib, copy, hashlib, importlib.util, json, pathlib, shlex, stat, types, unittest
from unittest.mock import patch, Mock
HERE=pathlib.Path(__file__).resolve().parents[1]
OLD=HERE.parent/'pr122_account_preparation'
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
probe=load('probe',HERE/'readonly_probe.py')
t=load('transport',HERE/'readonly_transport.py')
raw=(HERE/'approved_account_prepare.py').read_bytes()
ns=probe.load_approved(raw)
class Fake:
    host=ns['HOST'];uid=euid=0
    calls=[]
    def getpwnam(self,name):raise KeyError(name)
    def getgrnam(self,name):raise KeyError(name)
    def lstat(self,path):
        if path in ns['ABSENT_PATHS']:raise FileNotFoundError(path)
        mode=stat.S_IFREG|0o755 if path in ns['EXECUTABLES'] else stat.S_IFDIR|0o755
        return types.SimpleNamespace(st_uid=0,st_gid=0,st_mode=mode,st_nlink=1)
    @contextlib.contextmanager
    def lock_existing(self,path):
        assert path==ns['ORIGINAL_LOCK'];self.calls.append('lock');yield;self.calls.append('unlock')
    def platform_preconditions(self):
        self.calls.append('platform');return dict.fromkeys(probe.BOOLS,True)|dict(uid_min=101,uid_max=999,gid_min=101,gid_max=999)
    def command(self,args):raise FileNotFoundError('mock rpm absent')

def sample(fake=None):
    fake=fake or Fake();fake.calls=[];n=ns.copy();n['OS']=lambda:fake
    for key in ('main','create_once'):n[key]=Mock(side_effect=AssertionError('MUTATION'))
    for key in ('reserve_original_evidence','record_original_evidence','run_fixed_useradd','private_postcheck'):
        setattr(fake,key,Mock(side_effect=AssertionError('MUTATION')))
    with patch.object(probe,'meta',return_value={'state':'UNKNOWN'}),patch.object(probe,'identity',return_value={'state':'UNKNOWN'}):
        result=probe.run(n)
    return result,n,fake
class Tests(unittest.TestCase):
    def test_01_exact_approved_bytes(self):
        self.assertEqual(hashlib.sha256(raw).hexdigest(),probe.APPROVED_SHA)
        self.assertEqual(raw,(OLD/'account_prepare.py').read_bytes())
    def test_02_hash_rejects_changed_bytes(self):
        with self.assertRaises(ValueError):probe.load_approved(raw+b'\n')
    def test_03_import_never_main(self):
        self.assertEqual(ns['__name__'],'approved_account_payload_readonly')
    def test_04_no_mutation_methods(self):
        result,n,fake=sample();n['main'].assert_not_called();n['create_once'].assert_not_called()
        for k in ('reserve_original_evidence','record_original_evidence','run_fixed_useradd','private_postcheck'):getattr(fake,k).assert_not_called()
        self.assertEqual(fake.calls,['lock','platform','unlock']);self.assertEqual(result['mutations'],0)
    def test_05_schema_accepts_sanitized_fixture(self):t.validate_result(sample()[0])
    def test_06_schema_rejects_extra_secret(self):
        r=sample()[0];r['password']='fake'
        with self.assertRaises(t.Hold):t.validate_result(r)
    def test_07_schema_rejects_nested_extra(self):
        r=sample()[0];r['receipt']['content']='fake'
        with self.assertRaises(t.Hold):t.validate_result(r)
    def test_08_nss_error_unknown_not_absent(self):
        fake=Fake();fake.getpwnam=Mock(side_effect=RuntimeError('secret-error'));r=sample(fake)[0]
        self.assertEqual(r['account_absence'],'UNKNOWN');self.assertNotIn('secret-error',json.dumps(r))
    def test_09_nss_row_never_exported(self):
        fake=Fake();fake.getpwnam=lambda _:types.SimpleNamespace(pw_passwd='SECRET');r=sample(fake)[0]
        self.assertEqual(r['account_absence'],'PRESENT');self.assertNotIn('SECRET',json.dumps(r))
    def test_10_platform_failure_sanitized(self):
        fake=Fake();fake.platform_preconditions=Mock(side_effect=ValueError('SECRET'));r=sample(fake)[0]
        self.assertEqual(r['platform']['uid_min'],'UNKNOWN');self.assertNotIn('SECRET',json.dumps(r))
        fake=Fake();fake.command=Mock(return_value=types.SimpleNamespace(returncode=0,stdout=b'--system --user-group --no-create-home --home-dir --shell --password'))
        config=lambda p: 'SYS_UID_MIN 101\nSYS_UID_MAX 999\nSYS_GID_MIN 101\nSYS_GID_MAX 999\n' if p=='/etc/login.defs' else 'GROUPS=\n'
        with patch.dict(ns,{'secure_postcheck_tool':Mock(),'read_public_config':config}),patch.object(ns['os'].path,'lexists',return_value=False):
            platform=ns['OS'].platform_preconditions(fake)
        self.assertEqual(platform['uid_min'],101);fake.command.assert_called_once_with(('/usr/sbin/useradd','--help'))
    def test_11_disabled_no_network(self):
        with patch.object(t,'rpc',side_effect=AssertionError),patch.object(t,'github',side_effect=AssertionError),patch.object(t,'persist'),patch('builtins.print'):
            self.assertEqual(t.main(),2)
    def test_12_exact_helpers_reused(self):
        workflow=(OLD/'transport-candidate.yml').read_text()
        self.assertEqual(hashlib.sha256(workflow.encode()).hexdigest(),'c0db7caa615abee1b5cc2db973ea889a507f1317a3edc411bfee873e7da27e2f')
        inline=workflow.split("          python3 - <<'PY'\n",1)[1].split('          PY\n',1)[0]
        source=''.join(line[10:]+'\n' for line in inline.splitlines());new=(HERE/'readonly_transport.py').read_text()
        def defs(src):return {n.name:ast.get_source_segment(src,n) for n in ast.parse(src).body if isinstance(n,ast.FunctionDef)}
        a,b=defs(source),defs(new)
        for k in ('need','persist','github','gate','quote','rpc'):self.assertEqual(a[k],b[k])
    def test_13_bundle_hash_and_command_size(self):
        payload=(HERE/'bundle.json').read_bytes();self.assertEqual(hashlib.sha256(payload).hexdigest(),t.PAYLOAD_SHA)
        script=t.command(payload,'0'*32);self.assertLessEqual(len(base64.b64encode(script.encode())),16384)
        self.assertNotIn("ns['main']",script);self.assertNotIn('--apply',script)
        compile(shlex.split(script.split('\n',2)[2])[-1],'fixed-wrapper-syntax','exec')
    def test_14_fixed_rpc_allowlist(self):
        with self.assertRaises(t.Hold):t.rpc('other','x','x',('','',''))
    def test_15_all_disarm_gates(self):
        self.assertFalse(t.ARMED);self.assertFalse(t.EXECUTION_ADMISSION);self.assertEqual(t.EXPIRES,'1970-01-01T00:00:00+00:00')
        y=(HERE/'readonly-transport-candidate.yml').read_text();self.assertIn('${{ false &&',y);self.assertNotIn('workflow_dispatch',y);self.assertNotIn('pull_request_target',y)
        self.assertEqual(t.PREFIX,'xj-ro-');self.assertEqual(len(t.PREFIX+'a'*40),46)
        self.assertEqual(t.EXPECTED_WORKFLOW_REF,t.REPO+'/'+t.WORKFLOW_PATH+'@refs/pull/122/merge')
        self.assertFalse(hasattr(t,'EXPECTED_WORKFLOW_SHA'))
    def test_16_response_binding(self):
        data=dict(hostname=t.HOST,nonce='0'*32,payload_sha256=t.PAYLOAD_SHA,result=sample()[0]);detail=dict(InstanceId=t.INSTANCE,InvokeId='test',InvocationStatus='Success',ExitCode=0,Output=json.dumps(data))
        self.assertEqual(t.validate(detail,'test','0'*32),data['result'])
        with self.assertRaises(t.Hold):t.validate(detail,'wrong','0'*32)
        pr=dict(state='open',mergeable=True,merge_commit_sha='b'*40,head={'sha':'a'*40,'ref':t.BRANCH,'repo':{'full_name':t.REPO}},base={'ref':t.BASE,'sha':'c'*40})
        event=json.dumps({'pull_request':copy.deepcopy(pr)})
        env={'GITHUB_WORKFLOW_REF':t.EXPECTED_WORKFLOW_REF,'GITHUB_WORKFLOW_SHA':'b'*40,'GITHUB_EVENT_PATH':'offline-event'}
        with patch.dict(t.os.environ,env),patch.object(t.Path,'read_text',return_value=event),patch.object(t,'github',return_value=pr),patch.dict(t.row,{'head_sha':'a'*40}):
            self.assertEqual(t.workflow_identity(),'b'*40)
            for section,key,value in ((None,'merge_commit_sha','d'*40),('head','sha','d'*40),('base','sha','d'*40)):
                target=pr[section] if section else pr;old=target[key];target[key]=value
                with self.assertRaises(t.Hold):t.workflow_identity()
                target[key]=old
            with patch.dict(t.os.environ,{'GITHUB_WORKFLOW_REF':t.REPO+'/'+t.WORKFLOW_PATH+'@refs/heads/main'}):
                with self.assertRaises(t.Hold):t.workflow_identity()
    def test_17_rpm_selects_only_useradd(self):
        fake=Fake();fake.command=Mock(side_effect=[types.SimpleNamespace(returncode=0,stdout=b'shadow-utils\n4.9\n1\nx86_64\n8\n'),types.SimpleNamespace(returncode=0,stdout=('/unrelated\tPRIVATE\n/usr/sbin/useradd\t'+'a'*64+'\n').encode())])
        r=probe.package_identity(fake,{'state':'OBSERVED','sha256':'a'*64});self.assertTrue(r['actual_digest_matches']);self.assertNotIn('PRIVATE',json.dumps(r));self.assertEqual(fake.command.call_count,2)
    def test_18_rpm_failure_unknown(self):self.assertEqual(probe.package_identity(Fake(),{}),{'state':'UNKNOWN'})
    def test_19_readonly_caller_no_mutator_calls(self):
        tree=ast.parse((HERE/'readonly_probe.py').read_text());forbidden={'main','create_once','reserve_original_evidence','record_original_evidence','run_fixed_useradd','private_postcheck','mkdir','unlink','chmod','write_text','write_bytes'}
        for n in ast.walk(tree):
            if isinstance(n,ast.Call):self.assertNotIn(n.func.attr if isinstance(n.func,ast.Attribute) else n.func.id if isinstance(n.func,ast.Name) else '',forbidden)
    def test_20_result_size(self):self.assertLess(len(json.dumps(sample()[0])),20000)
if __name__=='__main__':unittest.main(verbosity=2)
