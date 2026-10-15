"""Type-aware systemd239 fields; recorded projection and synthetic live views.

The public19-unit fixture is a projection of the recorded diagnostic's selected
fields, not retained raw CLI output. No test runs systemctl or host effects.
"""
import copy
import os
import unittest
from unittest import mock

import epoch7_host_observer as observer
import epoch7_host_factory as factory
import epoch7_live_controls as live
import epoch7_service_contract as services
import epoch7_snapshot as snap
import epoch7_unit_transitions as transitions
from test_epoch7_live_controls import fixture,process_view
import test_epoch7_unit_transitions as transition_tests
from test_epoch7_full_factory_fixture import make_seed,native_pins,packed,meta
from test_node_sqlite_probe import fixture_proof
import node_sqlite_probe
from test_epoch7_openclaw_direct import direct_fixture
import test_epoch7_openclaw_direct as direct_tests
from test_unit_process_fields import actual_unit_rows,DIAGNOSTIC_SOURCE_SHA256


def omit_inapplicable(states):
    for unit,state in states.items():
        for key in (snap.UNIT_PROCESS_FIELDS if unit in snap.TIMER_UNITS else
                    {'MainPID'} if unit in snap.SOCKET_UNITS else set()):
            state.pop(key,None)
    return states


def typed_fixture():
    args,delta=direct_fixture()
    omit_inapplicable(args[4]['unit_states'])
    return args,delta


def omit_view(value):
    for when in ('before','after'):
        omit_inapplicable({u:row[when] for u,row in value['units'].items()})
    return value


class UnitTypeTests(unittest.TestCase):
    def test_recorded19_shape_replay_preserves_all_absences(self):
        rows=actual_unit_rows(int)
        self.assertEqual(DIAGNOSTIC_SOURCE_SHA256,'699b2a75228e6af2040a481b96a20c07e2b62ab3ba1eefc6726fe8bb20eceab2')
        self.assertEqual(set(rows),snap.WRITER_UNITS)
        # Serialize the selected projection for the parser boundary only. This
        # is not asserted to reproduce the original command bytes or raw hash.
        raw='\n\n'.join('\n'.join(k+'='+str(v) for k,v in sorted(row.items()))
                        for unit,row in sorted(rows.items())).encode()+b'\n'
        actual=observer.LinuxProcessCensus._parse_unit_blocks(raw,sorted(snap.WRITER_UNITS))
        self.assertEqual(actual,rows)
        for unit,state in actual.items():
            row={'before':state,'after':copy.deepcopy(state),'cgroup_present':False,'cgroups':{}}
            self.assertEqual(live.validate_unit_row(unit,row,stopped=True),set())
        self.assertEqual(sum('ControlGroup' not in row for row in actual.values()),3)
        self.assertEqual(sum('MainPID' not in row for row in actual.values()),6)
        self.assertEqual(sum('ControlPID' not in row for row in actual.values()),3)

    def test_parser_requires_every_applicable_property(self):
        for unit,row in actual_unit_rows(str).items():
            for key in set(row):
                changed=dict(row);changed.pop(key)
                raw=''.join(k+'='+v+'\n' for k,v in sorted(changed.items())).encode()
                with self.subTest(unit=unit,key=key),self.assertRaises(ValueError):
                    observer.LinuxProcessCensus._parse_unit_blocks(raw,[unit])

    def view(self,index=0):
        unused,context,contract,unused_views=fixture()
        return context,contract,omit_view(process_view(contract,index))

    def test_complete_stopped_and_final_live_census(self):
        for index in (0,14,15,16):
            context,contract,value=self.view(index);before=copy.deepcopy(value)
            live.validate_process_view(value,contract,contract['checkpoints'][index],os.getpid())
            self.assertEqual(value,before)

    def test_independent_cleanup_preserves_raw_missing_properties(self):
        context,contract,value=self.view();before=copy.deepcopy(value)
        live.validate_cleanup_process_view(value,contract,os.getpid())
        self.assertEqual(value,before)

    def test_services_and_sockets_keep_required_fields(self):
        for unit,keys in (('xuanjun-ledger.service',snap.UNIT_PROCESS_FIELDS),
                          ('xuanjun-ledger.socket',{'ControlPID','ControlGroup'})):
            for key in keys:
                context,contract,value=self.view()
                for when in ('before','after'):value['units'][unit][when].pop(key)
                with self.subTest(unit=unit,key=key),self.assertRaises(ValueError):
                    live.validate_process_view(value,contract,contract['checkpoints'][0],os.getpid())

    def test_timer_contradictory_fields_and_socket_optional_pid_reject(self):
        cases=[(unit,key,value) for unit in snap.TIMER_UNITS
               for key,value in (('MainPID',7),('ControlPID',7),('ControlGroup','/system.slice/'+unit))]
        cases += [(u,'MainPID',7) for u in snap.SOCKET_UNITS]
        for unit,key,change in cases:
            context,contract,value=self.view()
            for when in ('before','after'):value['units'][unit][when][key]=change
            with self.subTest(unit=unit,key=key),self.assertRaises(ValueError):
                live.validate_process_view(value,contract,contract['checkpoints'][0],os.getpid())

    def test_timer_omission_drift_between_reads_rejects(self):
        context,contract,value=self.view()
        value['units']['xuanjun-p2-tls-renew.timer']['after']['ControlGroup']=''
        with self.assertRaisesRegex(ValueError,'STATE_RACE'):
            live.validate_process_view(value,contract,contract['checkpoints'][0],os.getpid())

    def test_active_approved_timer_still_requires_empty_complete_cgroup(self):
        context,contract,value=self.view(16);unit='xuanjun-p2-tls-renew.timer'
        self.assertEqual(value['units'][unit]['before']['ActiveState'],'active')
        row=value['units'][unit];row['cgroup_present']=True
        row['cgroups']['/sys/fs/cgroup/systemd/system.slice/'+unit+'/cgroup.procs']=[8123]
        with self.assertRaisesRegex(ValueError,'CGROUP_NOT_EMPTY'):
            live.validate_unit_row(unit,row,contract['checkpoints'][16]['units'][unit])

    def test_timer_cgroup_scan_cannot_be_skipped_by_missing_property(self):
        context,contract,value=self.view();census=object.__new__(observer.LinuxProcessCensus)
        states={u:row['before'] for u,row in value['units'].items()}
        census._show_units=mock.Mock(return_value=states)
        census._cgroups=mock.Mock(return_value=(False,{}))
        self.assertEqual(census._all_units(),value['units'])
        self.assertEqual(census._cgroups.call_count,38)
        for unit in snap.TIMER_UNITS:self.assertEqual(census._cgroups.call_args_list.count(mock.call(unit)),2)

    def test_cached_timer_target_transition_uses_semantics_not_inserted_pids(self):
        case=transition_tests.UnitTransitionTests();case.setUp()
        old_unit,old_path=case.unit,case.path;unit='xuanjun-p2-tls-renew.timer';path=transitions.ROOT+unit
        policy=case.c['unit_transition_contract']['units'].pop(old_unit)
        for props in policy.values():props['Id']=unit
        case.c['unit_transition_contract']['units'][unit]=policy
        case.c['unit_transition_contract']['targets'][path]=case.c['unit_transition_contract']['targets'].pop(old_path)
        targets=case.v['unit_transition_evidence']['target_receipt']['targets'];targets[path]=targets.pop(old_path)
        for point in case.c['checkpoints'][:15]:point['units'][unit]['properties']=copy.deepcopy(policy['before'])
        for when in ('before','after'):case.v['units'][unit][when]=copy.deepcopy(policy['before'])
        case.unit,case.path=unit,path;case.props(NeedDaemonReload='yes')
        before=copy.deepcopy(case.v);case.check();self.assertEqual(case.v,before)

    def test_compiler_does_not_accept_missing_service_or_socket_properties(self):
        for unit,key in (('xuanjun-ledger.service','MainPID'),('xuanjun-ledger.service','ControlGroup'),
                         ('xuanjun-ledger.socket','ControlPID'),('xuanjun-ledger.socket','ControlGroup')):
            args,delta=typed_fixture();args[4]['unit_states'][unit].pop(key)
            with self.subTest(unit=unit,key=key),self.assertRaises(ValueError):
                services.compile_service_contract(*args,candidate_delta=delta)

    def test_direct_final_roles_with_timer_absence_keep_start_receipts(self):
        case=direct_tests.DirectFamilyTests();case.setUp();omit_view(case.view)
        case.check()
        case.view['service_role_evidence']['units']['xuanjun-uk-openclaw.service']['start']['returncode']=1
        with self.assertRaises(ValueError):case.check()

    def test_real107_factory_accepts_measured_root_config_and_absent_openclaw(self):
        # Selected Owner topology only: the rest is synthetic host metadata,
        # including an internally consistent fixture probe, never admission.
        seed=make_seed(service_fixture=typed_fixture)
        observation=seed['observation'];path='/home/xuanjun_dev/.config'
        observation['policy']['directories'][path]={'uid':0,'gid':0,'mode':0o755}
        self.assertNotIn(path+'/openclaw',observation['policy']['directories'])
        retained=observation['evidence']['retained']
        retained['policy_sha256']=factory.d.digest(observation['policy'])
        observation['snapshot']['retained_resource_sha256']=factory.d.digest(retained)
        observation['evidence']['snapshot_sha256']=factory.d.digest(observation['snapshot'])
        for key in ('snapshot','evidence','policy'):
            observation[key+'_sha256']=factory.d.digest(observation[key])
        # The synthetic prior probe must bind the changed observation. All real
        # validators still run; no compiler or acceptance result is mocked.
        attempt=observation['finite_probe'];policy=attempt['policy']
        policy['node_sqlite']=node_sqlite_probe.binding_from_observation(observation)
        pin=factory.sha(packed(policy));binding=policy['node_sqlite']
        proof=fixture_proof(binding['node'],policy['nonce'],pin,binding['probe_input_sha256'])
        receipt=packed({'schema':1,'nonce':policy['nonce'],'policy_sha256':pin,
            'events':[{'event':'NODE_SQLITE_OBSERVED','detail':proof}]})
        attempt['policy_sha256']=pin;attempt['result']['node_sqlite']=proof
        attempt['result']['created_receipt'].update(sha256=factory.sha(receipt),
            metadata={k:v for k,v in meta(receipt,mode=0o600).items() if k not in ('kind','sha256')},
            node_sqlite_event_sha256=factory.d.digest(proof))
        with native_pins(seed):
            result=factory.prepare_host_inputs(seed)
            self.assertEqual(result['state'],'COMPILED_NOT_ADMITTED',result.get('unresolved'))
            contract=factory.compile_host_contract(result['inputs'])
        inputs=result['inputs'];self.assertEqual(len(inputs['source_payloads']),107)
        self.assertEqual(len(inputs['resource_views']),17)
        self.assertEqual({k:inputs['resource_directories'][path][0][k] for k in ('uid','gid','mode')},
                         {'uid':0,'gid':0,'mode':0o755})
        self.assertNotIn(path+'/openclaw',inputs['resource_directories'])
        # Missing dotenv ancestry is proved by the quiet reader's shared
        # DescriptorReader, not represented as an existing resource parent.
        for view in inputs['resource_views']:
            self.assertFalse(any(row['path']==path+'/openclaw/gateway.env'
                                 for rows in view.values() for row in rows))
        self.assertEqual(contract['host_contract']['production_acceptance'],'PENDING')
        self.assertFalse(result['install_admission'])

    def test_real107_whole_factory_with_three_missing_timer_fields_then_live(self):
        seed=make_seed(service_fixture=typed_fixture)
        with native_pins(seed):
            result=factory.prepare_host_inputs(seed)
            self.assertEqual(result['state'],'COMPILED_NOT_ADMITTED',result.get('unresolved'))
            contract=factory.compile_host_contract(result['inputs'])['live_controls']
        self.assertEqual(len(result['inputs']['source_payloads']),107)
        self.assertEqual(len(result['inputs']['resource_views']),17)
        states=result['inputs']['service_facts']['unit_states']
        for unit in snap.TIMER_UNITS:self.assertFalse(set(states[unit]) & snap.UNIT_PROCESS_FIELDS)
        value=omit_view(process_view(contract,0))
        value['processes']['1']['before']['starttime']=contract['manager']['starttime']
        value['processes']['1']['after']['starttime']=contract['manager']['starttime']
        value['service_role_evidence']={'context_sha256':None,'units':{},'processes':{}}
        value['unit_transition_evidence']=None
        live.validate_process_view(value,contract,contract['checkpoints'][0],os.getpid(),checkpoint_index=0)
        live.validate_cleanup_process_view(value,contract,os.getpid())


if __name__=='__main__':unittest.main()
