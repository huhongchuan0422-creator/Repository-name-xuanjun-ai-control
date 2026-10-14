import base64,hashlib,copy,unittest
from unittest.mock import Mock,patch
import epoch7_command_runner as m

class CommandRunnerTests(unittest.TestCase):
    def setUp(self):
        self.spec={'observe':{'phase':'install_verified_plugin','operation':'plugin_inventory',
            'argv':['/fixture/not-executed','plugins','list','--json'],'env':{'LANG':'C'},'timeout':3,'accepted_returncodes':[0]}}
        self.e={'schema':1,'failed_stage':'provision_from_retained_resources_INTENT','operation':'plugin_inventory',
            'epoch':8,'sequence':1,'reason':'SUCCESS','returncode':0,'interruption_requires_propagation':False}
        for name in ('stdout','stderr'):
            raw=b'{}' if name=='stdout' else b''
            self.e[name]={'prefix_b64':base64.b64encode(raw).decode(),'retained_bytes':len(raw),'observed_bytes':len(raw),
                'prefix_sha256':hashlib.sha256(raw).hexdigest(),'eof_observed':True,'truncated':False}
        self.launch=Mock(return_value=Mock());self.capture=Mock(return_value=self.e);self.publish=Mock()
        self.diag=m.BoundedDiagnostics(self.publish,self.capture);self.guard=Mock(return_value=True)
    def runner(self):return m.ExactCommandRunner(self.spec,self.guard,self.diag,self.launch)
    def test_exact_argv_and_protected_popen_contract(self):
        out=self.runner().run('observe');self.assertEqual(out.stdout,b'{}');self.assertIsNone(out.args)
        args,kw=self.launch.call_args;self.assertEqual(args[0],self.spec['observe']['argv'])
        self.assertTrue(kw['start_new_session']);self.assertTrue(kw['close_fds']);self.assertFalse(kw['shell'])
        self.assertEqual(kw['bufsize'],0);self.assertEqual(kw['stdin'],m.subprocess.DEVNULL)
    def test_contract_copy(self):
        r=self.runner();self.spec['observe']['argv'][0]='/other';r.run('observe')
        self.assertEqual(self.launch.call_args[0][0][0],'/fixture/not-executed')
    def test_unknown_key(self):
        with self.assertRaises(ValueError):self.runner().run('other')
        self.launch.assert_not_called()
    def test_literal_admission(self):
        self.guard.return_value=1
        with self.assertRaises(ValueError):self.runner().run('observe')
        self.launch.assert_not_called()
    def test_nonzero_latched_deferred_publication_no_retry(self):
        self.e.update(reason='EXIT_NONZERO',returncode=2);r=self.runner()
        with self.assertRaises(m.CommandFailure) as ctx:r.run('observe')
        self.assertIs(self.diag.scope_failure,ctx.exception);self.publish.assert_not_called()
        with self.assertRaisesRegex(ValueError,'NO_RETRY'):r.run('observe')
        self.assertEqual(self.launch.call_count,1)
    def test_explicit_nonzero_query_preserved(self):
        self.spec['observe']['operation']='service_is_active';self.spec['observe']['accepted_returncodes']=[3]
        self.e.update(operation='service_is_active',reason='EXIT_NONZERO',returncode=3)
        r=self.runner();self.assertEqual(r.run('observe').returncode,3);self.assertIsNone(self.diag.scope_failure)
    def test_shared_counter_not_runner_owned(self):
        r=self.runner();r.run('observe');self.e['sequence']=2;r.run('observe')
        self.assertEqual(self.diag.sequence,2);self.assertFalse(hasattr(r,'sequence'))
    def test_timeout_latched(self):
        self.e.update(reason='TIMEOUT',returncode=None)
        with self.assertRaises(m.CommandFailure):self.runner().run('observe')
    def test_spawn_failure_sanitized(self):
        self.launch.side_effect=OSError('private');r=self.runner()
        with self.assertRaises(m.CommandFailure) as ctx:r.run('observe')
        self.assertNotIn('private',str(ctx.exception.summary));self.assertTrue(r.poisoned)
        self.assertIs(self.diag.scope_failure,ctx.exception)
        self.assertEqual(self.diag.sequence,1)
    def test_capture_failure_cleanup_independent(self):
        self.capture.side_effect=OSError('private');r=self.runner();p=self.launch.return_value
        p.stdout.close.side_effect=OSError('close')
        with patch.object(m,'_signal_owned_group',side_effect=OSError('signal')):
            with self.assertRaises(m.CommandFailure):r.run('observe')
        p.stderr.close.assert_called_once();p.wait.assert_called_once_with(timeout=2)
    def test_cleanup_interrupt_retained_and_other_cleanup_attempted(self):
        self.capture.side_effect=OSError();p=self.launch.return_value;p.stdout.close.side_effect=SystemExit(7)
        with patch.object(m,'_signal_owned_group',return_value='SKIPPED_UNPROVEN'):
            with self.assertRaises(SystemExit):self.runner().run('observe')
        p.stderr.close.assert_called_once();p.wait.assert_called_once()
    def test_captured_systemexit_retains_class_for_outer(self):
        self.e.update(reason='INTERRUPTED',returncode=None,interruption_requires_propagation=True,failure_class='SystemExit')
        with self.assertRaises(m.CommandFailure) as ctx:self.runner().run('observe')
        self.assertEqual(ctx.exception.interruption_class,'SystemExit')
    def test_bound_working_directory(self):
        self.spec['observe']['cwd']='/fixture/source/stage1'
        self.runner().run('observe')
        self.assertEqual(self.launch.call_args[1]['cwd'],'/fixture/source/stage1')
    def test_relative_or_alias_cwd_rejected(self):
        for cwd in ('relative','/fixture/../other','/fixture/./other',42):
            self.spec['observe']['cwd']=cwd
            with self.assertRaises(ValueError):self.runner()
    def test_capture_failure_latched_before_cleanup(self):
        self.capture.side_effect=OSError('private')
        def observe_latch():
            self.assertIsNotNone(self.diag.scope_failure)
        self.launch.return_value.stdout.close.side_effect=observe_latch
        with patch.object(m,'_signal_owned_group',return_value='SKIPPED_UNPROVEN'):
            with self.assertRaises(m.CommandFailure):self.runner().run('observe')
        self.assertEqual(self.diag.sequence,1)
        self.publish.assert_not_called()
    def test_exhausted_counter_refuses_before_spawn(self):
        self.diag.sequence=m.MAX_COMMANDS
        with self.assertRaisesRegex(ValueError,'DIAGNOSTIC_CAPACITY'):self.runner().run('observe')
        self.launch.assert_not_called()
    def test_unrecorded_capture_refuses_before_spawn(self):
        self.diag.capture_allocation=('install_verified_plugin','plugin_inventory',1)
        with self.assertRaisesRegex(ValueError,'DIAGNOSTIC_CAPACITY'):self.runner().run('observe')
        self.launch.assert_not_called()
    def test_existing_failure_refuses_before_spawn(self):
        self.diag.record_adapter_failure('install_verified_plugin','plugin_inventory','OSError','SPAWN_UNCONFIRMED')
        with self.assertRaisesRegex(ValueError,'DIAGNOSTIC_CAPACITY'):self.runner().run('observe')
        self.launch.assert_not_called()
    def test_record_failure_cannot_skip_emergency_cleanup(self):
        self.capture.side_effect=OSError('capture')
        self.diag.record_adapter_failure=Mock(side_effect=ValueError('record'))
        p=self.launch.return_value
        with patch.object(m,'_signal_owned_group',return_value='SKIPPED_UNPROVEN') as kill:
            with self.assertRaisesRegex(RuntimeError,'RECORD_UNAVAILABLE'):self.runner().run('observe')
        kill.assert_called_once();p.stdout.close.assert_called_once();p.stderr.close.assert_called_once()
        p.wait.assert_called_once_with(timeout=2)
    def test_invalid_contracts(self):
        for key,value in [('accepted_returncodes',[True]),('timeout',True),('timeout',61),('argv',['relative']),('env',{'BAD\0':'x'}),('phase','provision_from_retained_resources')]:
            saved=copy.deepcopy(self.spec);self.spec['observe'][key]=value
            with self.assertRaises(ValueError):self.runner()
            self.spec=saved

if __name__=='__main__':unittest.main()
