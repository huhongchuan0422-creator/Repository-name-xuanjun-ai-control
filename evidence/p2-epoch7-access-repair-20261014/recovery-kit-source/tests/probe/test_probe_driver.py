"""No HostOps effects, sockets, systemd, syscall or SDK import in this suite."""
import copy
import hashlib
import json
import pathlib
import re
import unittest
from unittest import mock
import probe_driver as p
import activation_control
from test_node_sqlite_probe import fixture_observation, fixture_proof

BASE=pathlib.Path(activation_control.__file__).resolve().parent.parent

def fixture(source_root=None):
    source=BASE if source_root is None else pathlib.Path(source_root)
    helper=b'synthetic helper bytes'
    files={rel:(source/rel).read_bytes() for rel in p.CANDIDATE_SOURCES}
    manifest=(source/'deploy/integration-manifest.json').read_bytes()
    value={'schema':2,'purpose':'ISOLATED_ROOT_MANAGER_ACCESS_PROBE','nonce':'a'*32,
        'hostname':p.EXPECTED_HOST,'machine_id_sha256':'1'*64,'runtime_manifest_sha256':p.RUNTIME_MANIFEST,
        'driver_sha256':'2'*64,'helper_sha256':p.digest(helper),
        'python':{'path':'/usr/libexec/platform-python3.6','sha256':'3'*64},
        'systemctl':{'path':'/usr/bin/systemctl','sha256':'4'*64},'profiles':{},
        'sdk_bindings':[{'path':'/home/xuanjun_dev/.openclaw/tools/sdk/index.mjs','sha256':'5'*64,'uid':1002,'gid':1002,'size':10}],
        'public_files':[{'path':'/usr/bin/systemctl','sha256':'4'*64,'maximum':33554432},
                        {'path':'/usr/lib/systemd/systemd','sha256':'6'*64,'maximum':33554432}],
        'candidate_sources':{k:p.digest(v) for k,v in files.items()},
        'ledger_capability_reviewed':True,'cleanup_reviewed':True,'limits':dict(p.LIMITS),
        'node_sqlite_reviewed':True,'node_sqlite':p.node_sqlite_probe.binding_from_observation(fixture_observation())}
    for role in p.ROLES:value['profiles'][role]={'user':p.USERS[role],
        'uid':p.UIDS[role],'group':p.GROUPS[role],'gid':0 if role=='broker' else (1002 if role=='native' else 1006),
        'supplementary_groups':{name:(1003 if name=='xuanjun-dispatcher' else 1007 if name=='xuanjun-ledger-client' else 990)
                                for name in p.SUPPLEMENTARY[role]},
        'protect_home':'read-only' if role=='native' else 'yes'}
    return value,helper,manifest,files


class FakeOps(object):
    def __init__(self):self.receipt=None;self.events=[];self.fail=None;self.operator_acknowledged=False;self.used=False
    def check_host(self):self.events.append(('host',));return {'fixture':True}
    def preflight_sources(self,raw=None):return {'fixture':True}
    def run_node_sqlite(self):
        self.events.append(('node_sqlite',))
        value=fixture_proof(self.policy['node_sqlite']['node'],self.policy['nonce'],self.policy_sha,
                            self.policy['node_sqlite']['probe_input_sha256'])
        if self.fail=='node_sqlite':value['cleanup_state']='UNKNOWN'
        return value
    def receipt_binding(self):return {'fixture_only':True}
    def begin(self):
        if self.used:raise ValueError('NONCE_ALREADY_USED')
        self.used=True;self.receipt={'connections_reserved':0};self.events.append(('begin',))
        if self.fail=='begin':raise OSError('UNCERTAIN_CREATE')
    def install(self,raw):
        self.events.append(('install',))
        if self.fail=='install':raise OSError('INSTALL_FAILURE')
    def event(self,event,detail=None):self.events.append((event,detail))
    def run_case(self,case,role,kind):
        self.events.append(('case',case))
        if self.fail==case:raise OSError('CASE_FAILURE')
        return {'case':case,'status':'PASS_OBSERVED','fixture_only':True,
                'expected_rejection_observed':kind in ('restart_during','recreate_during')}
    def cleanup(self):self.events.append(('cleanup',));return [{'fixture':'cleanup'}]


class PolicyTests(unittest.TestCase):
    def setUp(self):self.policy,self.helper,self.manifest,self.files=fixture()
    def test_explicit_fixture_source_ignores_cached_default_module_path(self):
        import sys
        with mock.patch.object(sys.modules[__name__],'BASE',None):
            value,helper,manifest,files=fixture(pathlib.Path(activation_control.__file__).resolve().parent.parent)
        self.assertEqual((value,helper,manifest,files),(self.policy,self.helper,self.manifest,self.files))
    def test_exact_policy(self):p.validate_policy(self.policy)
    def test_wrong_host_policy_identity_type(self):
        self.policy['hostname']='';self.assertRaises(ValueError,p.validate_policy,self.policy)
    def test_bool_uid_denied(self):
        self.policy['profiles']['broker']['uid']=False;self.assertRaises(ValueError,p.validate_policy,self.policy)
    def test_unreviewed_capability_denied(self):
        self.policy['ledger_capability_reviewed']=False;self.assertRaises(ValueError,p.validate_policy,self.policy)
    def test_unknown_scope_key_denied(self):
        self.policy['production']=True;self.assertRaises(ValueError,p.validate_policy,self.policy)
    def test_ninth_connection_not_allowable(self):
        self.policy['limits']['connections']=9;self.assertRaises(ValueError,p.validate_policy,self.policy)
    def test_different_runtime_source_denied(self):
        self.policy['runtime_manifest_sha256']='0'*64;self.assertRaises(ValueError,p.validate_policy,self.policy)
    def test_public_private_config_denied(self):
        self.policy['public_files'][0]['path']='/etc/xuanjun-development/dispatcher.json'
        self.assertRaises(ValueError,p.validate_policy,self.policy)
    def test_preinstall_does_not_require_opt_candidate(self):
        self.assertFalse(any('/opt/' in row['path'] for row in self.policy['public_files']))
        p.validate_policy(self.policy)
    def test_sdk_outside_fixed_tools_denied(self):
        self.policy['sdk_bindings'][0]['path']='/home/xuanjun_dev/.openclaw/profile.json'
        self.assertRaises(ValueError,p.validate_policy,self.policy)
    def test_sdk_bound_exact(self):
        self.policy['sdk_bindings'][0]['size']=8*1024*1024;p.validate_policy(self.policy)
        self.policy['sdk_bindings'][0]['size']+=1;self.assertRaises(ValueError,p.validate_policy,self.policy)
    def test_nonce_shell_chars_denied(self):
        self.policy['nonce']='a'*31+';';self.assertRaises(ValueError,p.validate_policy,self.policy)
    def test_duplicate_json_denied(self):self.assertRaises(ValueError,p.parse,b'{"a":1,"a":2}')
    def test_capability_only_ledger_unit(self):
        for role in p.ROLES:
            unused,raw=p.render_unit(self.policy,role)
            self.assertEqual(b'CAP_SYS_PTRACE' in raw,role=='ledger')
            self.assertNotIn(b'CAP_SYS_ADMIN',raw)
    def test_socket_remove_on_stop_explicit_and_no_install_section(self):
        raw=p.render_socket(self.policy)
        self.assertIn(b'RemoveOnStop=yes',raw);self.assertNotIn(b'[Install]',raw)
        self.assertIn(p.scope(self.policy)['socket'].encode(),raw)


class SequenceTests(unittest.TestCase):
    def setUp(self):
        self.policy,self.helper,unused,unused2=fixture();self.ops=FakeOps()
        self.ops.policy=self.policy;self.ops.policy_sha=p.digest(p.canonical(self.policy)+b'\n')
        self.probe=p.Probe(self.policy,self.ops.policy_sha,self.ops)
    def test_inspect_has_no_effects(self):
        result=self.probe.inspect();self.assertEqual(result['effect_count'],0)
        self.assertEqual(self.ops.events,[('host',)])
    def test_apply_requires_explicit_acknowledgement(self):
        self.assertRaises(ValueError,self.probe.apply,self.helper,False);self.assertEqual(self.ops.events,[])
    def test_truthy_ack_not_accepted(self):self.assertRaises(ValueError,self.probe.apply,self.helper,1)
    def test_exact_eight_once_and_cleanup(self):
        result=self.probe.apply(self.helper,True)
        self.assertEqual([x[1] for x in self.ops.events if x[0]=='case'],list(range(1,9)))
        self.assertEqual(self.ops.receipt['connections_reserved'],8)
        self.assertFalse(result['resume_authority']);self.assertEqual(self.ops.events[-1],('cleanup',))
    def test_failure_no_retry_no_remaining_cases(self):
        self.ops.fail=3;result=self.probe.apply(self.helper,True)
        self.assertEqual([x[1] for x in self.ops.events if x[0]=='case'],[1,2,3])
        self.assertIsNotNone(result['failure']);self.assertEqual(self.ops.events[-1],('cleanup',))
    def test_node_unknown_stops_before_all_socket_connections(self):
        self.ops.fail='node_sqlite';result=self.probe.apply(self.helper,True)
        self.assertEqual(result['cases'],[]);self.assertEqual(self.ops.receipt['connections_reserved'],0)
        self.assertIsNotNone(result['failure']);self.assertEqual(self.ops.events[-1],('cleanup',))
    def test_partial_begin_always_cleanup(self):
        self.ops.fail='begin';result=self.probe.apply(self.helper,True)
        self.assertEqual(self.ops.events[-1],('cleanup',));self.assertIsNotNone(result['failure'])
    def test_install_failure_always_cleanup(self):
        self.ops.fail='install';self.probe.apply(self.helper,True);self.assertEqual(self.ops.events[-1],('cleanup',))
    def test_same_nonce_no_second_attempt(self):
        self.probe.apply(self.helper,True);result=self.probe.apply(self.helper,True)
        self.assertIn('NONCE_ALREADY_USED',result['failure'])
    def test_cleanup_failure_does_not_erase_primary(self):
        self.ops.fail=2
        def bad():raise OSError('CLEANUP_FAILURE')
        self.ops.cleanup=bad;result=self.probe.apply(self.helper,True)
        self.assertIn('CASE_FAILURE',result['failure']);self.assertEqual(result['cleanup'][0]['status'],'UNKNOWN')


class InstallContractTests(unittest.TestCase):
    def setUp(self):self.policy,self.helper,self.manifest,self.files=fixture()
    def fake_install(self):
        ops=p.HostOps(self.policy,p.digest(p.canonical(self.policy)),'/synthetic-reviewed-source')
        ops.operator_acknowledged=True;ops.receipt={'resources':[]};published={}
        ops.publish=lambda path,raw:published.update({path:raw})
        ops.command=lambda *args,**kwargs:None;ops.event=lambda *args:None
        def read(path,maximum,protected=True):
            if path.endswith('/deploy/integration-manifest.json'):return self.manifest,{}
            return self.files[path[len('/synthetic-reviewed-source/'):]],{}
        ops.read_file=read;ops.install(self.helper)
        return ops,published
    def test_every_rendered_path_exists_for_all_eight_cases(self):
        ops,published=self.fake_install()
        for case,role,kind in p.CASES:
            unit,raw=p.render_unit(self.policy,role,case);lines=raw.decode().splitlines()
            config=next(x for x in lines if x.startswith('ExecStart=')).split('--config ',1)[1].split(' --mode')[0]
            output=next(x for x in lines if x.startswith('StandardOutput=file:')).split('file:',1)[1]
            error=next(x for x in lines if x.startswith('StandardError=file:')).split('file:',1)[1]
            self.assertIn(config,published);self.assertIn(output,published);self.assertIn(error,published)
        self.assertEqual(len([x for x in published if x.startswith('/run/systemd/system/')]),6)
    def test_source_copies_are_under_nonce_not_opt(self):
        ops,published=self.fake_install()
        self.assertEqual(len([x for x in published if '/candidate-' in x]),3)
        self.assertFalse(any(x.startswith('/opt/') for x in published))
    def test_bad_helper_hash_before_publish(self):
        self.helper=b'changed';self.assertRaises(ValueError,self.fake_install)
    def test_full_write_handles_short_writes(self):
        chunks=[]
        def write(fd,raw):chunks.append(raw[:2]);return min(2,len(raw))
        with mock.patch.object(p.os,'write',side_effect=write):p.HostOps.write_all(99,b'abcdefg')
        self.assertEqual(b''.join(chunks),b'abcdefg')
    def test_nonce_search_mode_is_explicit_under_private_umask(self):
        import os,stat,tempfile
        with tempfile.TemporaryDirectory(prefix='epoch7-probe-umask-') as parent:
            ops=p.HostOps(self.policy,'a'*64);ops.operator_acknowledged=True
            ops.paths['root']=parent+'/nonce';ops.assert_absent=mock.Mock();ops.save_receipt=mock.Mock()
            previous=os.umask(0o077)
            try:ops.begin()
            finally:os.umask(previous)
            self.assertEqual(stat.S_IMODE(os.stat(ops.paths['root']).st_mode),0o755)
            target=ops.paths['root']+'/node-sqlite-probe.cjs'
            with mock.patch.object(ops,'protected_parent'):
                ops._write(target,p.node_sqlite_probe.SOURCE,0o644)
            self.assertEqual(stat.S_IMODE(os.stat(target).st_mode),0o644)
            self.assertEqual(pathlib.Path(target).read_bytes(),p.node_sqlite_probe.SOURCE)
    def test_zero_write_rejected(self):
        with mock.patch.object(p.os,'write',return_value=0):self.assertRaises(ValueError,p.HostOps.write_all,99,b'x')
    def test_production_unit_commands_denied_before_popen(self):
        ops=p.HostOps(self.policy,'1'*64)
        with mock.patch.object(p.subprocess,'Popen',side_effect=AssertionError('NO_HOST_CALL')):
            self.assertRaises(ValueError,ops.command,['start','xuanjun-ledger.service'])
            self.assertRaises(ValueError,ops.command,['show','xuanjun-ledger.service','--no-pager','--property=MainPID'])
    def test_no_manager_mutation_without_ack_attempt(self):
        ops=p.HostOps(self.policy,'1'*64)
        with mock.patch.object(p.subprocess,'Popen',side_effect=AssertionError('NO_HOST_CALL')):
            self.assertRaises(ValueError,ops.command,['daemon-reload'])




class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.policy,self.helper,self.manifest,self.files=fixture()
        self.ops=p.HostOps(self.policy,'1'*64);self.ops.operator_acknowledged=True
        self.ops.receipt={'events':[]};self.calls=[];self.unlinked=[]
        self.ops.created=[]
        for unit in [self.ops.paths['socket_unit'],self.ops.paths['service_unit']]+list(self.ops.paths['client_units'].values()):
            self.ops.created.append({'path':'/run/systemd/system/'+unit,'kind':'FILE','sha256':p.digest(b'unit'),
                'identity':{'dev':1,'ino':len(self.ops.created)+1,'mode':0o644,'uid':0,'gid':0,'nlink':1,'size':4,'mtime_ns':1,'ctime_ns':1}})
        self.ops.read_file=lambda target,*args,**kwargs:(b'unit',copy.deepcopy(next(x['identity'] for x in self.ops.created if x['path']==target)))
        self.ops.command=lambda args,**kwargs:self.calls.append(args)
        self.ops.stopped_exact=lambda unit:True;self.ops.save_receipt=lambda:None
    def cleanup(self):
        with mock.patch.object(p.os,'unlink',side_effect=self.unlinked.append),mock.patch.object(p.os.path,'lexists',return_value=False):
            return self.ops.cleanup()
    def test_every_exact_created_unit_stopped_and_files_removed(self):
        self.cleanup();self.assertEqual(sum(x[0]=='stop' for x in self.calls),6)
        self.assertEqual(len(self.unlinked),6)
    def test_failed_first_stop_does_not_skip_other_units_or_delete_files(self):
        original=self.ops.command
        def command(args,**kwargs):
            original(args,**kwargs)
            if args[0]=='stop' and args[1].endswith('-broker.service'):raise OSError('STOP_FAIL')
        self.ops.command=command;result=self.cleanup()
        self.assertEqual(sum(x[0]=='stop' for x in self.calls),6);self.assertEqual(self.unlinked,[])
        self.assertTrue(any(row.get('files')=='RETAINED_BECAUSE_UNIT_STOP_UNCONFIRMED' for row in result))
    def test_changed_unit_not_stopped_and_not_unlinked(self):
        original=self.ops.read_file
        def read(target,*args,**kwargs):
            raw,info=original(target,*args,**kwargs)
            if target.endswith('-broker.service'):info['ino']+=1
            return raw,info
        self.ops.read_file=read;self.cleanup()
        self.assertEqual(sum(x[0]=='stop' for x in self.calls),5);self.assertEqual(self.unlinked,[])
    def test_untrusted_cleanup_receipt_cannot_name_production_file(self):
        self.ops.created[0]['path']='/etc/passwd'
        self.assertRaises(ValueError,self.cleanup);self.assertEqual(self.calls,[])
    def test_duplicate_cleanup_target_rejected(self):
        self.ops.created.append(copy.deepcopy(self.ops.created[0]))
        self.assertRaises(ValueError,self.cleanup);self.assertEqual(self.calls,[])
    def test_nonroot_recorded_owner_rejected(self):
        self.ops.created[0]['identity']['uid']=1002
        self.assertRaises(ValueError,self.cleanup);self.assertEqual(self.calls,[])
    def test_cgroup_not_empty_keeps_all_artifacts(self):
        def not_empty(unit):raise ValueError('CGROUP_NOT_EMPTY')
        self.ops.stopped_exact=not_empty;self.cleanup();self.assertEqual(self.unlinked,[])
        self.assertEqual(sum(x[0]=='stop' for x in self.calls),6)


class CompilerTests(unittest.TestCase):
    def setUp(self):
        self.policy,unused,unused2,unused3=fixture()
        self.ingredients={k:copy.deepcopy(self.policy[k]) for k in ('hostname','machine_id_sha256','python','systemctl','sdk_bindings')}
        self.ingredients['profiles']={role:{k:v for k,v in row.items() if k!='protect_home'} for role,row in self.policy['profiles'].items()}
        self.ingredients['manager']={'path':'/usr/lib/systemd/systemd','sha256':'6'*64}
        self.offline={k:copy.deepcopy(self.policy[k]) for k in ('nonce','driver_sha256','helper_sha256','candidate_sources','ledger_capability_reviewed','cleanup_reviewed','node_sqlite_reviewed')}
        self.observation=fixture_observation()
    def test_one_collection_compiles_complete_policy_without_invented_pins(self):
        result=p.compile_policy(self.ingredients,self.offline,self.observation)
        self.assertEqual(result['hostname'],self.ingredients['hostname'])
        self.assertEqual(result['profiles']['native']['protect_home'],'read-only')
        self.assertEqual(result['runtime_manifest_sha256'],p.RUNTIME_MANIFEST)
    def test_missing_measured_hash_does_not_fallback(self):
        self.ingredients['manager']['sha256']=None
        self.assertRaises(ValueError,p.compile_policy,self.ingredients,self.offline,self.observation)
    def test_collector_cannot_insert_review_booleans(self):
        self.ingredients['cleanup_reviewed']=True
        self.assertRaises(ValueError,p.compile_policy,self.ingredients,self.offline,self.observation)
    def test_unsupported_host_or_role_never_compiles(self):
        self.ingredients['hostname']='different-host'
        self.assertRaises(ValueError,p.compile_policy,self.ingredients,self.offline,self.observation)
    def test_ledger_group_cannot_be_broadened(self):
        self.ingredients['profiles']['ledger']['supplementary_groups']['docker']=990
        self.assertRaises(ValueError,p.compile_policy,self.ingredients,self.offline,self.observation)
    def test_wrong_policy_hash_rejected_before_backend_use(self):
        self.assertRaises(ValueError,p.Probe,self.policy,'0'*64,FakeOps())
    def test_ledger_counter_inherited_fds_are_exact_nonce_file(self):
        unused,raw=p.render_unit(self.policy,'ledger');root=p.scope(self.policy)['root']
        self.assertIn(('StandardInput=file:'+root+'/connection-budget.json').encode(),raw)
        self.assertIn(('StandardOutput=file:'+root+'/connection-budget.json').encode(),raw)
        self.assertNotIn(b'ReadWritePaths=',raw)


class LoaderWrapperTests(unittest.TestCase):
    def setUp(self):self.policy,self.helper,unused,unused2=fixture();self.sha=p.digest(p.canonical(self.policy)+b'\n')
    def test_loader_wrapper_keeps_watchdog_and_restores_handlers(self):
        ops=FakeOps()
        with mock.patch.object(p,'HostOps',return_value=ops),mock.patch.object(p.signal,'getitimer',return_value=(0.,0.)),\
             mock.patch.object(p.signal,'getsignal',return_value='previous'),mock.patch.object(p.signal,'signal') as handlers,\
             mock.patch.object(p.signal,'setitimer') as timers:
            result=p.execute_reviewed_probe(self.policy,self.sha,'/reviewed/stage',self.helper,True)
        self.assertTrue(ops.watchdog_armed);self.assertEqual(handlers.call_count,6)
        self.assertEqual(timers.call_args_list[0][0],(p.signal.ITIMER_REAL,60))
        self.assertEqual(timers.call_args_list[-1][0],(p.signal.ITIMER_REAL,0))
        self.assertFalse(result['resume_authority'])
    def test_loader_wrapper_cannot_run_without_manual_ack(self):
        with mock.patch.object(p,'HostOps',side_effect=AssertionError('NO_HOST_CONSTRUCT')):
            self.assertRaises(ValueError,p.execute_reviewed_probe,self.policy,self.sha,'/reviewed',self.helper,False)
    def test_existing_loader_alarm_is_not_silently_overridden(self):
        with mock.patch.object(p,'HostOps',return_value=FakeOps()),mock.patch.object(p.signal,'getitimer',return_value=(5.,0.)):
            self.assertRaises(ValueError,p.execute_reviewed_probe,self.policy,self.sha,'/reviewed',self.helper,True)


class RaceAdmissionTests(unittest.TestCase):
    def setUp(self):
        policy,unused,unused2,unused3=fixture();self.ops=p.HostOps(policy,'1'*64)
    def test_race_waits_for_old_service_acceptance(self):
        self.ops.capture_budget=mock.Mock(side_effect=[5,6])
        with mock.patch.object(p.time,'sleep'):
            self.ops.wait_accepted(6)
        self.assertEqual(self.ops.capture_budget.call_count,2)
    def test_unexpected_extra_connection_rejected(self):
        self.ops.capture_budget=lambda:7
        self.assertRaises(ValueError,self.ops.wait_accepted,6)
    def test_queue_only_connection_does_not_become_race_proof(self):
        self.ops.capture_budget=lambda:5
        self.ops.deadline.remaining=lambda:1
        with mock.patch.object(p.time,'monotonic',side_effect=[0,.1,1.1]),mock.patch.object(p.time,'sleep'):
            self.assertRaises(TimeoutError,self.ops.wait_accepted,6)
    def test_deadline_calls_clock_and_reports_remaining(self):
        clock=mock.Mock(side_effect=[10.,10.5]);deadline=p.Deadline(2,clock=clock)
        self.assertEqual(deadline.remaining(),1.5);self.assertEqual(clock.call_count,2)
    def test_deadline_expiration_never_returns_nonpositive_budget(self):
        clock=mock.Mock(side_effect=[10.,12.]);deadline=p.Deadline(2,clock=clock)
        self.assertRaises(TimeoutError,deadline.remaining)


class IncompleteCaseEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.policy,self.helper,unused,unused2=fixture()
        self.ops=p.HostOps(self.policy,'1'*64);self.ops.receipt={'events':[],'connections_reserved':1}
        self.ops.command=mock.Mock();self.ops.capture_output=mock.Mock();self.ops.replace_created=mock.Mock()
        self.ops.socket_identity=mock.Mock(return_value={});self.ops.namespace_proof=mock.Mock(return_value={'status':'NOT_VERIFIED'})
        self.ops.save_receipt=mock.Mock();self.ops.capture_budget=mock.Mock(return_value=0)
        self.observed={'case':1,'status':'FAIL_OBSERVED','reason':'TimeoutError:timed out','sdk':[]}
        self.ops.wait_output=mock.Mock(return_value={'result':self.observed})
    def test_missing_connection_keeps_partial_result_and_original_error(self):
        with self.assertRaisesRegex(ValueError,'UNEXPECTED_OR_MISSING_CONNECTION'):
            self.ops.run_case(1,'native','cold')
        row=self.ops.receipt['incomplete_case'];self.assertFalse(row['completion'])
        self.assertEqual(row['result'],self.observed);self.assertEqual(row['role'],'native')
        self.assertEqual(row['result']['namespace_proof'],{'status':'NOT_VERIFIED'})
        self.assertIsNot(row['result'],self.observed)
        self.assertEqual(self.ops.capture_budget.call_count,1)
    def test_extra_connection_keeps_original_budget_rejection(self):
        self.ops.capture_budget.return_value=2
        self.assertRaisesRegex(ValueError,'UNEXPECTED_OR_MISSING_CONNECTION',self.ops.run_case,1,'native','cold')
        self.assertFalse(self.ops.receipt['incomplete_case']['completion'])
    def test_stop_failure_retains_result_before_postcheck(self):
        count=[0]
        def command(argv,*args,**kwargs):
            if argv==['stop',self.ops.paths['client_units']['native']]:
                count[0]+=1
                if count[0]==2:raise OSError('STOP_FAILED')
        self.ops.command=command
        self.assertRaisesRegex(OSError,'STOP_FAILED',self.ops.run_case,1,'native','cold')
        self.ops.capture_budget.assert_not_called();self.assertFalse(self.ops.receipt['incomplete_case']['completion'])
    def test_budget_success_does_not_yet_clear_pending_until_observed_saved(self):
        self.ops.capture_budget.return_value=1
        result=self.ops.run_case(1,'native','cold');self.assertIn('incomplete_case',self.ops.receipt)
        self.ops.event('CASE_OBSERVED',result);self.assertNotIn('incomplete_case',self.ops.receipt)
    def test_receipt_save_failure_preserves_pending_and_original_exception(self):
        self.ops.capture_budget.return_value=1;result=self.ops.run_case(1,'native','cold')
        self.ops.save_receipt.side_effect=KeyboardInterrupt()
        self.assertRaises(KeyboardInterrupt,self.ops.event,'CASE_OBSERVED',result)
        self.assertFalse(self.ops.receipt['incomplete_case']['completion'])
    def test_wrong_result_cannot_clear_pending(self):
        self.ops.capture_budget.return_value=1;result=self.ops.run_case(1,'native','cold')
        other=dict(result,status='PASS_OBSERVED')
        self.assertRaisesRegex(ValueError,'CASE_CAPTURE_CHANGED',self.ops.event,'CASE_OBSERVED',other)
        self.assertIn('incomplete_case',self.ops.receipt)
    def test_oversized_result_refused_without_postcheck(self):
        self.observed['unexpected']='x'*16385
        self.assertRaisesRegex(ValueError,'CASE_RESULT_CAPTURE_BOUND',self.ops.run_case,1,'native','cold')
        self.ops.capture_budget.assert_not_called()
    def test_partial_case_not_counted_as_completed_by_coordinator(self):
        ops=FakeOps();ops.policy=self.policy;ops.policy_sha=p.digest(p.canonical(self.policy)+b'\n')
        def fail(*unused):
            ops.receipt['incomplete_case']={'case':1,'completion':False,'result':self.observed}
            raise ValueError('UNEXPECTED_OR_MISSING_CONNECTION')
        ops.run_case=fail
        result=p.Probe(self.policy,ops.policy_sha,ops).apply(self.helper,True)
        self.assertEqual(result['cases'],[]);self.assertFalse(result['incomplete_case']['completion'])
        self.assertEqual(result['failure'],'ValueError:UNEXPECTED_OR_MISSING_CONNECTION')
        self.assertFalse(result['resume_authority'])
    def test_pre_ready_traceback_retains_only_safe_category_and_hash(self):
        raw=b'Traceback (most recent call last):\n  File "PRIVATE", line 1\nValueError: EXACT_INHERITED_LISTENER\n'
        result=p.non_json_diagnostic(raw)
        self.assertEqual(result,{'kind':'TRACEBACK','bytes':len(raw),'sha256':p.digest(raw),
            'exception_class':'ValueError','failure_code':'EXACT_INHERITED_LISTENER'})
        self.assertNotIn('PRIVATE',p.canonical(result).decode())
    def test_unknown_traceback_message_is_opaque(self):
        raw=b'Traceback (most recent call last):\nOSError: PRIVATE_TOKEN=secret\n'
        result=p.non_json_diagnostic(raw)
        self.assertEqual(result['exception_class'],'OSError');self.assertEqual(result['failure_code'],'REDACTED_UNKNOWN')
        self.assertNotIn('secret',p.canonical(result).decode())
    def test_json_only_has_no_traceback_diagnostic(self):
        self.assertIsNone(p.non_json_diagnostic(b'{"event":"SERVER_READY"}\n'))
    def test_non_json_diagnostic_bound(self):
        self.assertRaisesRegex(ValueError,'OUTPUT_DIAGNOSTIC_BOUND',p.non_json_diagnostic,b'x'*65537)
    def test_capture_output_persists_server_failure_metadata_without_body(self):
        target=self.ops.paths['root']+'/output-ledger.jsonl';error=self.ops.paths['root']+'/error-ledger.txt'
        info={k:1 for k in ('dev','ino','uid','gid','mode','nlink')}
        self.ops.created=[{'path':path,'identity':dict(info)} for path in (target,error)]
        raw=b'Traceback (most recent call last):\nValueError: EXACT_INHERITED_LISTENER\n'
        self.ops.read_file=lambda path,maximum:(raw if path==target else b'',dict(info))
        p.HostOps.capture_output(self.ops,'ledger')
        event=self.ops.receipt['events'][0]['detail']
        self.assertEqual(event['observations'],[]);self.assertEqual(event['non_json_diagnostic']['failure_code'],'EXACT_INHERITED_LISTENER')
        self.assertEqual(event['sha256'],p.digest(raw));self.assertNotIn('Traceback',p.canonical(event).decode())
    def test_clean_ledger_capture_keeps_exact_historical_fields(self):
        target=self.ops.paths['root']+'/output-ledger.jsonl';error=self.ops.paths['root']+'/error-ledger.txt'
        info={k:1 for k in ('dev','ino','uid','gid','mode','nlink')}
        self.ops.created=[{'path':path,'identity':dict(info)} for path in (target,error)]
        self.ops.read_file=lambda path,maximum:(b'{"event":"SERVER_READY"}\n' if path==target else b'',dict(info))
        p.HostOps.capture_output(self.ops,'ledger')
        self.assertEqual(set(self.ops.receipt['events'][0]['detail']),{'path','sha256','bytes','observations'})


class CasePublicationFailureTests(unittest.TestCase):
    def test_failed_case_publication_never_enters_completed_cases_or_events(self):
        policy,helper,unused,unused2=fixture();sha=p.digest(p.canonical(policy)+b'\n')
        class SavingOps(FakeOps):
            def begin(self):
                super(SavingOps,self).begin();self.receipt['events']=[]
            def event(self,name,detail=None):p.HostOps.event(self,name,detail)
            def save_receipt(self):
                if self.receipt['events'] and self.receipt['events'][-1]['event']=='CASE_OBSERVED':
                    raise OSError('CASE_SAVE_FAILED')
            def run_case(self,case,role,kind):
                result={'case':case,'status':'PASS_OBSERVED'}
                self.receipt['incomplete_case']={'case':case,'completion':False,'result':copy.deepcopy(result)}
                return result
            def cleanup(self):
                self.save_receipt();return super(SavingOps,self).cleanup()
        ops=SavingOps();ops.policy=policy;ops.policy_sha=sha
        result=p.Probe(policy,sha,ops).apply(helper,True)
        self.assertEqual(result['failure'],'OSError:CASE_SAVE_FAILED')
        self.assertEqual(result['cases'],[]);self.assertFalse(result['incomplete_case']['completion'])
        self.assertFalse(any(row['event']=='CASE_OBSERVED' for row in ops.receipt['events']))
        self.assertIn(('cleanup',),ops.events)


if __name__=='__main__':unittest.main()
