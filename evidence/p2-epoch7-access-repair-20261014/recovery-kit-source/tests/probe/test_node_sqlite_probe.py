"""Pure/synthetic Node predicate fixtures; never invokes Node or host resources."""
import copy
import errno
import hashlib
import json
import types
import unittest
from unittest import mock
import node_sqlite_probe as n


def fixture_node():
    return {'path':'/home/xuanjun_dev/.nvm/versions/node/v24.21.0/bin/node','sha256':'a'*64,
        'metadata':{'dev':1,'ino':2,'mode':0o755,'uid':1002,'gid':1002,'nlink':1,'size':123,
                    'mtime_ns':3,'ctime_ns':4}}


def fixture_observation():
    node=fixture_node();row=dict(node['metadata'],kind='FILE',sha256=node['sha256'])
    retained={'native_components':{'components':{node['path']:row}}}
    snapshot={'retained_resource_sha256':n.digest(n.canonical(retained))}
    evidence={'snapshot_sha256':n.digest(n.canonical(snapshot)),'retained':retained}
    metadata={'sections':{'native_gateway':{'state':'MEASURED_UNREVIEWED','evidence':{
        'gateway_identity':{'user':'xuanjun_dev','exe':node['path'],'sha256':node['sha256'],
                            'cgroup':'/system.slice/xuanjun-uk-openclaw.service'}}}}}
    value={'kind':'EPOCH7_OBSERVATION_ONLY_UNREVIEWED','install_admission':'NOT_GRANTED',
        'snapshot':snapshot,'evidence':evidence,'unit_metadata':metadata}
    for name in ('snapshot','evidence','unit_metadata'):value[name+'_sha256']=n.digest(n.canonical(value[name]))
    return value


def fixture_proof(node=None,nonce='a'*32,policy_sha256='b'*64,probe_input_sha256='c'*64):
    """Explicitly synthetic receipt using actual diagnostic source and predicates."""
    node=fixture_node() if node is None else node
    result={'schema':1,'node_version':'24.21.0','exec_path':node['path'],'exec_argv':[],
        'sqlite':{'available':True,'version':'3.51.3','text':True,'blob':True,'json':True,'error':None}}
    value={'schema':1,'status':'PASS_OBSERVED','node':copy.deepcopy(node),'nonce':nonce,
        'policy_sha256':policy_sha256,'probe_input_sha256':probe_input_sha256,
        'diagnostic_sha256':n.digest(n.SOURCE),'argv_sha256':n.digest(n.canonical(n.argv(node,nonce))),
        'environment_sha256':n.digest(n.canonical(n.ENV)),'execution_identity':copy.deepcopy(n.EXECUTION_IDENTITY),
        'result':result,'cleanup_state':'OBSERVED','error':None}
    n.validate_node_sqlite_proof(value,node,policy_sha256,probe_input_sha256)
    return value


def fixture_attempt(original_policy=None):
    if original_policy is None:
        from test_probe_driver import fixture
        policy=fixture()[0]
    else:policy=copy.deepcopy(original_policy)
    observation=fixture_observation()
    policy_sha=n.digest(n.canonical(policy)+b'\n');binding=n.binding_from_observation(observation)
    proof=fixture_proof(binding['node'],policy['nonce'],policy_sha,binding['probe_input_sha256'])
    raw=b'placeholder';metadata=dict(fixture_node()['metadata'],uid=0,gid=0,mode=0o600,size=len(raw))
    result={'failure':None,'resume_authority':False,'last_command_cleanup':[],
        'node_sqlite':proof,'cases':[{'case':i,'status':'FAIL_OBSERVED' if i in (6,8) else 'PASS_OBSERVED',
            'expected_rejection_observed':i in (6,8)} for i in range(1,9)],
        'cleanup':[{'status':'STOPPED_AND_EMPTY'},{'status':'REMOVED'}],
        'created_receipt':{'path':n.script_path(policy['nonce']).rsplit('/',1)[0]+'/created-receipt.json',
            'metadata':metadata,'sha256':n.digest(raw),'node_sqlite_event_sha256':n.digest(n.canonical(proof))}}
    attempt={'schema':1,'nonce':policy['nonce'],'stage':'RESULT_RECORDED','resume_authority':False,
        'operator_acknowledgement_is_external_approval_proof':False,'policy':policy,
        'policy_sha256':policy_sha,'result':result}
    raw=fixture_receipt(attempt);result['created_receipt'].update(sha256=n.digest(raw))
    result['created_receipt']['metadata']['size']=len(raw)
    return attempt,policy,observation,policy_sha


def fixture_receipt(attempt):
    proof=attempt['result']['node_sqlite'];nonce=attempt['nonce']
    info=dict(fixture_node()['metadata'],uid=0,gid=0,mode=0o644,size=len(n.SOURCE))
    return n.canonical({'schema':1,'purpose':'ISOLATED_PROBE_CREATION_RECEIPT','nonce':nonce,
        'policy_sha256':attempt['policy_sha256'],'operator_acknowledged':True,
        'external_approval_authenticated':False,'attempt_consumed':True,'connections_reserved':8,
        'accepted_connections':8,'stage':'CLEANUP_OBSERVED','cleanup':attempt['result']['cleanup'],
        'events':[{'event':'NODE_SQLITE_OBSERVED','detail':proof}],
        'resources':[{'path':n.script_path(nonce),'kind':'FILE','identity':info,'sha256':n.digest(n.SOURCE)}]})+b'\n'


class AttemptBindingTests(unittest.TestCase):
    def test_explicit_policy_fixture_does_not_read_cached_runtime(self):
        from test_probe_driver import fixture
        policy=fixture()[0]
        with mock.patch('test_probe_driver.fixture',side_effect=AssertionError('UNEXPECTED_RUNTIME_READ')):
            args=fixture_attempt(policy)
        self.assertEqual(n.validated_proof_from_attempt(*args)['policy_sha256'],args[3])
        self.assertIsNot(args[1],policy)
    def test_protected_receipt_bytes_anchor_policy_and_exact_event(self):
        attempt,unused,observation,unused2=fixture_attempt();observation['finite_probe']=attempt
        value=n.authenticate_receipt_binding(fixture_receipt(attempt),attempt['result']['created_receipt']['metadata'],observation)
        self.assertEqual(value['proof'],attempt['result']['node_sqlite'])
    def test_caller_consistent_leaf_cannot_change_protected_policy(self):
        attempt,unused,observation,unused2=fixture_attempt();raw=fixture_receipt(attempt)
        observation['finite_probe']=attempt;attempt['policy_sha256']='0'*64
        attempt['result']['node_sqlite']['policy_sha256']='0'*64
        with self.assertRaises(ValueError):n.authenticate_receipt_binding(raw,attempt['result']['created_receipt']['metadata'],observation)
    def test_repeated_node_event_or_changed_receipt_hash_holds(self):
        for mutation in ('duplicate','hash','metadata'):
            attempt,unused,observation,unused2=fixture_attempt();observation['finite_probe']=attempt
            value=n.parse(fixture_receipt(attempt));reported=attempt['result']['created_receipt']
            if mutation=='duplicate':value['events']*=2
            raw=n.canonical(value)+b'\n';reported['metadata']['size']=len(raw);reported['sha256']=n.digest(raw)
            metadata=copy.deepcopy(reported['metadata'])
            if mutation=='hash':raw+=b' '
            if mutation=='metadata':metadata['ino']+=1
            with self.assertRaises(ValueError):n.authenticate_receipt_binding(raw,metadata,observation)
    def test_protected_receipt_pending_case_refused_despite_complete_result(self):
        for incomplete in ({'completion':False}, {}, False, []):
            attempt,unused,observation,unused2=fixture_attempt();observation['finite_probe']=attempt
            attempt['result']['incomplete_case']=None
            value=n.parse(fixture_receipt(attempt));value['incomplete_case']=incomplete
            raw=n.canonical(value)+b'\n';reported=attempt['result']['created_receipt']
            reported['metadata']['size']=len(raw);reported['sha256']=n.digest(raw)
            with self.assertRaisesRegex(ValueError,'PROTECTED_RECEIPT_SCOPE'):
                n.authenticate_receipt_binding(raw,reported['metadata'],observation)
    def test_protected_receipt_explicit_none_remains_compatible(self):
        attempt,unused,observation,expected=fixture_attempt();observation['finite_probe']=attempt
        value=n.parse(fixture_receipt(attempt));value['incomplete_case']=None
        raw=n.canonical(value)+b'\n';reported=attempt['result']['created_receipt']
        reported['metadata']['size']=len(raw);reported['sha256']=n.digest(raw)
        self.assertEqual(n.authenticate_receipt_binding(raw,reported['metadata'],observation)['policy_sha256'],expected)
    def test_original_policy_and_observation_path(self):
        args=fixture_attempt();value=n.validated_proof_from_attempt(*args)
        self.assertEqual(value['proof'],args[0]['result']['node_sqlite'])
        self.assertEqual(value['policy_sha256'],args[3])
    def test_self_consistent_leaf_cannot_replace_original_policy(self):
        attempt,policy,observation,expected=fixture_attempt()
        other=copy.deepcopy(policy);other['nonce']='b'*32
        attempt.update(policy=other,policy_sha256=n.digest(n.canonical(other)+b'\n'),nonce=other['nonce'])
        with self.assertRaises(ValueError):n.validated_proof_from_attempt(attempt,policy,observation,expected)
    def test_original_observation_cannot_be_replaced_by_leaf_claim(self):
        attempt,policy,observation,expected=fixture_attempt()
        observation['unit_metadata']['sections']['native_gateway']['evidence']['gateway_identity']['sha256']='0'*64
        observation['unit_metadata_sha256']=n.digest(n.canonical(observation['unit_metadata']))
        with self.assertRaises(ValueError):n.validated_proof_from_attempt(attempt,policy,observation,expected)
    def test_self_consistent_leaf_cannot_change_attempt_nonce(self):
        attempt,policy,observation,expected=fixture_attempt()
        proof=attempt['result']['node_sqlite'];proof['nonce']='b'*32
        proof['argv_sha256']=n.digest(n.canonical(n.argv(proof['node'],proof['nonce'])))
        attempt['result']['created_receipt']['path']=n.script_path(proof['nonce']).rsplit('/',1)[0]+'/created-receipt.json'
        attempt['result']['created_receipt']['node_sqlite_event_sha256']=n.digest(n.canonical(proof))
        with self.assertRaisesRegex(ValueError,'PROOF_NONCE_BINDING'):
            n.validated_proof_from_attempt(attempt,policy,observation,expected)
    def test_failed_other_case_or_cleanup_invalidates_whole_proof(self):
        for mutation in ('case','cleanup','receipt','command'):
            attempt,policy,observation,expected=fixture_attempt();result=attempt['result']
            if mutation=='case':result['cases'][2]['status']='NOT_VERIFIED'
            if mutation=='cleanup':result['cleanup'][0]['status']='UNKNOWN'
            if mutation=='receipt':result['created_receipt']['node_sqlite_event_sha256']='0'*64
            if mutation=='command':result['last_command_cleanup']=['CHILD_REAP_UNCONFIRMED']
            with self.assertRaises(ValueError):n.validated_proof_from_attempt(attempt,policy,observation,expected)
    def test_incomplete_case_invalidates_otherwise_complete_whole_proof(self):
        for incomplete in ({'completion':False}, {}, False, []):
            args=fixture_attempt();result=args[0]['result']
            self.assertIsNone(result['failure']);self.assertEqual(len(result['cases']),8)
            result['incomplete_case']=incomplete
            with self.assertRaisesRegex(ValueError,'WHOLE_PROBE_NOT_VERIFIED'):
                n.validated_proof_from_attempt(*args)
    def test_missing_or_none_incomplete_case_remains_compatible(self):
        for explicit in (False,True):
            args=fixture_attempt()
            if explicit:args[0]['result']['incomplete_case']=None
            self.assertEqual(n.validated_proof_from_attempt(*args)['policy_sha256'],args[3])
    def test_receipt_authority_and_path_are_exact(self):
        for key,bad in (('uid',False),('gid',1002),('mode',0o644),('size',0)):
            args=fixture_attempt();args[0]['result']['created_receipt']['metadata'][key]=bad
            with self.assertRaises(ValueError):n.validated_proof_from_attempt(*args)
    def test_no_missing_or_unknown_proof_fallback(self):
        args=fixture_attempt();args[0]['result']['node_sqlite']['cleanup_state']='UNKNOWN'
        with self.assertRaises(ValueError):n.validated_proof_from_attempt(*args)


class PredicateTests(unittest.TestCase):
    def test_synthetic_positive_exact_source(self):
        proof=fixture_proof();self.assertEqual(n.validate_node_sqlite_proof(proof,fixture_node(),'b'*64,'c'*64),proof['result'])
    def test_wal_release_line_boundaries(self):
        for version in ('3.51.3','3.50.7','3.44.6','3.52.0','4.0.0'):
            value=fixture_proof()['result'];value['sqlite']['version']=version;n.validate_result(value,fixture_node())
        for version in ('3.51.2','3.50.6','3.44.5','3.49.999','3.45.999','2.99.99','3.51.3-extra','9007199254740992.0.0'):
            value=fixture_proof()['result'];value['sqlite']['version']=version
            with self.assertRaises(ValueError):n.validate_result(value,fixture_node())
    def test_supported_node_boundaries(self):
        for version in ('24.16.0','24.21.0','26.1.0','27.0.0'):
            value=fixture_proof()['result'];value['node_version']=version;n.validate_result(value,fixture_node())
        for version in ('22.16.0','24.15.99','25.99.99','26.0.99','v24.16.0','24.16.0-extra'):
            value=fixture_proof()['result'];value['node_version']=version
            with self.assertRaises(ValueError):n.validate_result(value,fixture_node())
    def test_every_nul_capability_requires_literal_true(self):
        for name in ('available','text','blob','json'):
            for bad in (False,1,None):
                value=fixture_proof()['result'];value['sqlite'][name]=bad
                with self.assertRaises(ValueError):n.validate_result(value,fixture_node())
    def test_error_preloads_and_wrong_executable_reject(self):
        for key,bad in (('exec_path','/other/node'),('exec_argv',['--require=evil'])):
            value=fixture_proof()['result'];value[key]=bad
            with self.assertRaises(ValueError):n.validate_result(value,fixture_node())
        value=fixture_proof()['result'];value['sqlite']['error']='SQLITE_CLOSE_FAILED'
        with self.assertRaises(ValueError):n.validate_result(value,fixture_node())
    def test_every_proof_binding_rejects_drift_or_unknown(self):
        for key,bad in (('diagnostic_sha256','0'*64),('policy_sha256','0'*64),('probe_input_sha256','0'*64),
            ('argv_sha256','0'*64),('environment_sha256','0'*64),('status','NOT_VERIFIED'),
            ('cleanup_state','UNKNOWN'),('error','CHILD_REAP_UNCONFIRMED')):
            value=fixture_proof();value[key]=bad
            with self.assertRaises(ValueError):n.validate_node_sqlite_proof(value,fixture_node(),'b'*64,'c'*64)
    def test_no_root_execution_or_supplementary_membership(self):
        for row in ({'uid':0,'gid':0,'supplementary_groups':[]},
                    {'uid':1002,'gid':1002,'supplementary_groups':[990]}):
            value=fixture_proof();value['execution_identity']=row
            with self.assertRaises(ValueError):n.validate_node_sqlite_proof(value,fixture_node(),'b'*64,'c'*64)
    def test_derived_node_binding_no_boolean_admission(self):
        value=fixture_observation();result=n.binding_from_observation(value)
        self.assertEqual(result['node'],fixture_node());self.assertEqual(result['diagnostic_sha256'],n.digest(n.SOURCE))
        value['unit_metadata']['sections']['native_gateway']['state']='UNKNOWN'
        value['unit_metadata_sha256']=n.digest(n.canonical(value['unit_metadata']))
        with self.assertRaises(ValueError):n.binding_from_observation(value)
    def test_observation_digest_drift_rejects(self):
        value=fixture_observation();value['snapshot_sha256']='0'*64
        with self.assertRaises(ValueError):n.binding_from_observation(value)
    def test_source_has_only_builtin_requires_and_memory_database(self):
        import re
        self.assertEqual(set(re.findall(br'require\("([^\"]+)"\)',n.SOURCE)),{b'node:sqlite',b'node:worker_threads'})
        self.assertIn(b'new DatabaseSync(":memory:")',n.SOURCE)
        self.assertNotIn(b'node:fs',n.SOURCE);self.assertNotIn(b'node:net',n.SOURCE)
        self.assertNotIn('NODE_OPTIONS',n.ENV);self.assertNotIn('NODE_PATH',n.ENV)


class DropIdentityTests(unittest.TestCase):
    def test_all_ids_and_groups_drop_before_exec(self):
        with mock.patch.object(n.os,'setgroups') as groups,mock.patch.object(n.os,'setresgid') as gid,\
             mock.patch.object(n.os,'setresuid') as uid,mock.patch.object(n.os,'umask'),\
             mock.patch.object(n.os,'getresuid',return_value=(1002,)*3),\
             mock.patch.object(n.os,'getresgid',return_value=(1002,)*3),mock.patch.object(n.os,'getgroups',return_value=[]):
            n.child_identity();groups.assert_called_once_with([]);gid.assert_called_once_with(1002,1002,1002)
            uid.assert_called_once_with(1002,1002,1002)
    def test_uid_drop_failure_never_finishes_preexec(self):
        with mock.patch.object(n.os,'setgroups'),mock.patch.object(n.os,'setresgid'),\
             mock.patch.object(n.os,'setresuid',side_effect=PermissionError()),mock.patch.object(n.os,'umask') as later:
            with self.assertRaises(PermissionError):n.child_identity()
            later.assert_not_called()
    def test_actual_popen_identity_failure_prevents_harmless_exec(self):
        import os,pathlib,subprocess,sys,tempfile,time
        with tempfile.TemporaryDirectory(prefix='epoch7-node-drop-failure-') as root:
            target=root+'/would-have-executed';start=time.monotonic()
            with mock.patch.object(n.os,'setresuid',side_effect=PermissionError('FIXTURE_DENIAL')):
                with self.assertRaises(subprocess.SubprocessError):
                    subprocess.Popen([sys.executable,'-B','-c',
                        'open('+repr(target)+',"w").write("unexpected")'],
                        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                        close_fds=True,start_new_session=True,preexec_fn=n.child_identity)
            self.assertFalse(pathlib.Path(target).exists());self.assertLess(time.monotonic()-start,2)


class DescriptorTests(unittest.TestCase):
    def test_real_descriptor_and_path_replacement_refused(self):
        import os,pathlib,tempfile
        with tempfile.TemporaryDirectory(prefix='epoch7-node-descriptor-') as root:
            path=root+'/fixture-node';raw=b'\x7fELF-not-executable-fixture';pathlib.Path(path).write_bytes(raw)
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            try:
                node={'path':path,'sha256':n.digest(raw),'metadata':n.metadata(os.fstat(fd))}
                with self.assertRaises(ValueError):n.validate_node(node)
                n.check_node(fd,node,mock.Mock())
                os.rename(path,path+'.old');pathlib.Path(path).write_bytes(raw)
                with self.assertRaisesRegex(ValueError,'NODE_(?:PATH_REPLACED|DESCRIPTOR_CHANGED)'):
                    n.check_node(fd,node,mock.Mock())
            finally:os.close(fd)
    def test_real_descriptor_mutation_refused(self):
        import os,pathlib,tempfile
        with tempfile.TemporaryDirectory(prefix='epoch7-node-descriptor-') as root:
            path=root+'/fixture-node';raw=b'\x7fELF-not-executable-fixture';pathlib.Path(path).write_bytes(raw)
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            try:
                node={'path':path,'sha256':n.digest(raw),'metadata':n.metadata(os.fstat(fd))}
                pathlib.Path(path).write_bytes(raw+b'changed')
                with self.assertRaisesRegex(ValueError,'NODE_DESCRIPTOR_CHANGED'):
                    n.check_node(fd,node,mock.Mock())
            finally:os.close(fd)
    def test_file_capability_presence_or_unreadability_rejects(self):
        for value in (b'',b'fixture-capability-not-applied'):
            with mock.patch.object(n.os,'getxattr',return_value=value):
                with self.assertRaisesRegex(ValueError,'FILE_CAPABILITIES_PRESENT'):n.no_file_capabilities(99)
        for error in (errno.EACCES,errno.EIO,errno.EPERM):
            with mock.patch.object(n.os,'getxattr',side_effect=OSError(error,'fixture')):
                with self.assertRaisesRegex(ValueError,'CAPABILITY_XATTR_READ'):n.no_file_capabilities(99)
        for error in (errno.ENODATA,errno.ENOTSUP):
            with mock.patch.object(n.os,'getxattr',side_effect=OSError(error,'fixture')):n.no_file_capabilities(99)


class RunTests(unittest.TestCase):
    def setUp(self):
        self.node=fixture_node();self.proof=fixture_proof()
        self.ops=types.SimpleNamespace(policy={'nonce':'a'*32,'node_sqlite_reviewed':True,
            'node_sqlite':{'node':self.node,'probe_input_sha256':'c'*64,'diagnostic_sha256':n.digest(n.SOURCE)}},
            policy_sha='b'*64,paths={'root':'/run/'+n.PREFIX+'a'*32},operator_acknowledged=True,receipt={},
            deadline=mock.Mock(),event=mock.Mock(),publish=mock.Mock(),last_capture_cleanup=None)
        self.ops.capture=mock.Mock(side_effect=self.capture)
    def capture(self,*args,**kwargs):
        self.ops.last_capture_cleanup=[]
        return {'stdout':n.canonical(self.proof['result'])+b'\n','stderr':b'','returncode':0}
    def run_fake(self,check_error=None):
        with mock.patch.object(n,'open_node',return_value=99),mock.patch.object(n,'check_node',side_effect=check_error),\
             mock.patch.object(n.os,'close'),mock.patch.object(n.threading,'active_count',return_value=1),\
             mock.patch.object(n.os,'listdir',return_value=[str(n.os.getpid())]):
            return n.run(self.ops)
    def test_fixed_argv_env_descriptor_identity_budget(self):
        value=self.run_fake();self.assertEqual(value['status'],'PASS_OBSERVED')
        args,kwargs=self.ops.capture.call_args
        self.assertEqual(args,(n.argv(self.node,'a'*32),n.ENV,5,4096))
        self.assertEqual(kwargs['executable'],'/proc/self/fd/99');self.assertEqual(kwargs['pass_fds'],(99,))
        self.assertIs(kwargs['preexec_fn'],n.child_identity)
    def test_path_or_descriptor_replacement_holds(self):
        value=self.run_fake(ValueError('NODE_SQLITE_NODE_PATH_REPLACED'))
        self.assertEqual(value['status'],'NOT_VERIFIED')
    def test_cleanup_unknown_never_passes(self):
        def capture(*args,**kwargs):
            value=self.capture();self.ops.last_capture_cleanup=['CHILD_REAP_UNCONFIRMED'];return value
        self.ops.capture.side_effect=capture
        value=self.run_fake();self.assertEqual(value['status'],'NOT_VERIFIED');self.assertEqual(value['cleanup_state'],'UNKNOWN')
    def test_preexec_failure_or_timeout_holds_without_retry(self):
        for error in (PermissionError(),TimeoutError()):
            self.ops.capture.reset_mock();self.ops.capture.side_effect=error
            value=self.run_fake();self.assertEqual(value['status'],'NOT_VERIFIED');self.ops.capture.assert_called_once()
    def test_multithreaded_parent_refuses_before_open_or_spawn(self):
        with mock.patch.object(n.threading,'active_count',return_value=2),mock.patch.object(n,'open_node') as opened:
            value=n.run(self.ops)
        self.assertEqual(value['status'],'NOT_VERIFIED');opened.assert_not_called();self.ops.capture.assert_not_called()
    def test_descriptor_close_failure_never_passes(self):
        with mock.patch.object(n,'open_node',return_value=99),mock.patch.object(n,'check_node'),\
             mock.patch.object(n.os,'close',side_effect=OSError()),mock.patch.object(n.threading,'active_count',return_value=1),\
             mock.patch.object(n.os,'listdir',return_value=[str(n.os.getpid())]):
            value=n.run(self.ops)
        self.assertEqual(value['status'],'NOT_VERIFIED');self.assertEqual(value['cleanup_state'],'UNKNOWN')
    def test_missing_ack_never_executes(self):
        self.ops.operator_acknowledged=False;value=self.run_fake()
        self.assertEqual(value['status'],'NOT_VERIFIED');self.ops.capture.assert_not_called()


if __name__=='__main__':unittest.main()
