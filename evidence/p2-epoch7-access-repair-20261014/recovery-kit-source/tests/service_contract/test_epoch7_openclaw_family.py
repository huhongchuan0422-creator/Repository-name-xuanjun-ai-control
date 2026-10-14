"""Complete synthetic cgroup/ancestry evidence for the source-derived families."""
import copy
import hashlib
import os
import pathlib
import unittest
HERE=pathlib.Path(__file__).resolve().parent
import epoch7_service_roles as sr
from test_epoch7_openclaw_recipe import complete_fixture
import epoch7_service_contract as sc
from test_epoch7_service_roles import fixture2
import epoch7_live_controls as live
GW='xuanjun-uk-openclaw.service';RELAY='xuanjun-p2-gateway-relay.service'


class SourceFamilyTests(unittest.TestCase):
    def setUp(self):
        args,delta=complete_fixture();compiled=sc.compile_service_contract(*args,candidate_delta=delta)
        self.context,self.contract,self.view=fixture2()
        self.blocks={u:compiled['service_role_contract']['units'][u] for u in (GW,RELAY)}
        self.contract['service_role_contract']['units'].update(copy.deepcopy(self.blocks))
        self.contract['process_roles']=[r for r in self.contract['process_roles'] if r['unit']!=RELAY]
        for unit,block in self.blocks.items():
            for point in self.contract['checkpoints']:
                if point['units'][unit]['main_required']:point['units'][unit]['main_role_sha256']=live.digest(block['roles'][0])
            main=self.view['units'][unit]['before']['MainPID']
            self.assign(main,unit,'main',1,create=False)
            evidence=copy.deepcopy(self.view['service_role_evidence']['units'][GW])
            evidence['sources']=copy.deepcopy(block['sources'])
            evidence['quiet_startup']=copy.deepcopy(block['quiet_startup'])
            evidence['start']['argv_sha256']=sr.argv_hash(['/usr/bin/systemctl','start',unit])
            self.view['service_role_evidence']['units'][unit]=evidence
        self.gw=self.view['units'][GW]['before']['MainPID'];self.relay=self.view['units'][RELAY]['before']['MainPID']

    def assign(self,pid,unit,name,parent,create=True,title=None):
        role=next(r for r in self.blocks[unit]['roles'] if r['name']==name)
        if create:
            base=copy.deepcopy(self.view['processes'][str(self.view['units'][unit]['before']['MainPID'])])
            for when in ('before','after'):base[when].update(pid=pid,starttime=100000+pid)
            self.view['processes'][str(pid)]=base
            self.view['units'][unit]['cgroups']['/sys/fs/cgroup/systemd/system.slice/'+unit+'/cgroup.procs'].append(pid)
        raw=title.encode()+b'\0'*7 if title else None
        for when in ('before','after'):
            row=self.view['processes'][str(pid)][when];row.update(copy.deepcopy(role['identity']))
            row['argv_sha256']=hashlib.sha256(raw).hexdigest() if raw else role['command']['sha256']
        observed={'ppid':parent,'parent_starttime':self.view['processes'][str(parent)]['before']['starttime'],
            'executable_dev':role['executable_dev'],'executable_ino':role['executable_ino'],
            'cmdline_title':title,'cmdline_size':len(raw) if raw else 256}
        self.view['service_role_evidence']['processes'][str(pid)]={'before':observed,'after':copy.deepcopy(observed)}
        self.view['pids_before']=self.view['pids_after']=sorted(int(x) for x in self.view['processes'])
        return pid

    def check(self):
        live.validate_contract(self.contract,self.context)
        return live.validate_process_view(self.view,self.contract,self.contract['checkpoints'][16],os.getpid(),
            context_sha256=self.context['context_sha256'],checkpoint_index=16)

    def test_serving_main_native_bridge_and_relay_respawn(self):
        self.assign(self.gw,GW,'main',1,create=False,title='openclaw-gateway')
        self.assign(self.gw+30000,GW,'bridge_main',self.gw)
        cli=self.assign(self.relay+20000,RELAY,'cli',self.relay)
        self.assign(cli+1,RELAY,'cli_respawn',cli,title='openclaw');self.check()

    def test_cache_child_serves_and_is_the_only_native_bridge_parent(self):
        cache=self.assign(self.gw+20000,GW,'compile_cache_child',self.gw,title='openclaw-gateway')
        self.assign(cache+10000,GW,'bridge_child',cache);self.check()

    def test_cache_waiting_parent_cannot_also_have_serving_title(self):
        self.assign(self.gw,GW,'main',1,create=False,title='openclaw-gateway')
        self.assign(self.gw+20000,GW,'compile_cache_child',self.gw,title='openclaw-gateway')
        with self.assertRaisesRegex(ValueError,'CACHE_PARENT'):self.check()

    def test_bridge_cannot_use_initial_or_intermediate_title_parent(self):
        self.assign(self.gw,GW,'main',1,create=False,title='openclaw')
        self.assign(self.gw+30000,GW,'bridge_main',self.gw)
        with self.assertRaisesRegex(ValueError,'SERVING_GATEWAY'):self.check()

    def test_excess_native_bridge_is_refused(self):
        self.assign(self.gw,GW,'main',1,create=False,title='openclaw-gateway')
        self.assign(self.gw+30000,GW,'bridge_main',self.gw);self.assign(self.gw+30001,GW,'bridge_main',self.gw)
        with self.assertRaisesRegex(ValueError,'COUNT_EXCEEDED|ONE_NATIVE_BRIDGE'):self.check()

    def test_both_native_bridge_parents_are_refused(self):
        cache=self.assign(self.gw+20000,GW,'compile_cache_child',self.gw,title='openclaw-gateway')
        self.assign(cache+10000,GW,'bridge_child',cache);self.assign(cache+10001,GW,'bridge_main',self.gw)
        with self.assertRaisesRegex(ValueError,'ONE_NATIVE_BRIDGE'):self.check()

    def test_relay_wrong_operation_argv_is_refused(self):
        cli=self.assign(self.relay+20000,RELAY,'cli',self.relay)
        for when in ('before','after'):self.view['processes'][str(cli)][when]['argv_sha256']=sr.argv_hash(['node','agent','--danger'])
        with self.assertRaisesRegex(ValueError,'PROCESS_ROLE'):self.check()

    def test_relay_respawn_wrong_flag_or_title_is_refused(self):
        cli=self.assign(self.relay+20000,RELAY,'cli',self.relay)
        child=self.assign(cli+1,RELAY,'cli_respawn',cli,title='openclaw-gateway')
        with self.assertRaisesRegex(ValueError,'PROCESS_ROLE'):self.check()

    def test_relay_respawn_cannot_reparent_to_manager(self):
        cli=self.assign(self.relay+20000,RELAY,'cli',self.relay)
        self.assign(cli+1,RELAY,'cli_respawn',1,title='openclaw')
        with self.assertRaises(ValueError):self.check()

    def test_detachment_never_excuses_foreign_cgroup(self):
        cli=self.assign(self.relay+20000,RELAY,'cli',self.relay)
        child=self.assign(cli+1,RELAY,'cli_respawn',cli,title='openclaw')
        for when in ('before','after'):self.view['processes'][str(child)][when]['unit']=None
        with self.assertRaises(ValueError):self.check()

    def test_relay_extra_child_or_wrong_credentials_refused(self):
        cli=self.assign(self.relay+20000,RELAY,'cli',self.relay)
        child=self.assign(cli+1,RELAY,'cli_respawn',cli,title='openclaw')
        for when in ('before','after'):self.view['processes'][str(child)][when]['groups']=[0]
        with self.assertRaisesRegex(ValueError,'PROCESS_ROLE'):self.check()
    def test_changed_live_quiet_projection_cannot_reuse_start_receipt(self):
        self.view['service_role_evidence']['units'][GW]['quiet_startup']['selected_environment']['NODE_OPTIONS']='--require=evil'
        with self.assertRaisesRegex(ValueError,'CURRENT_QUIET'):self.check()


class DetachedRelayContainmentTests(unittest.TestCase):
    def test_unknown_activation_still_runs_all_independent_unit_cleanup_groups(self):
        import test_epoch7_recovery_sequence as outer
        import epoch7_recovery_sequence as sequence
        rig=outer.Rig();phase='activate_new_services'
        # A detached Node child can escape the inner process group. UNKNOWN is
        # therefore propagated to the outer coordinator, never labeled reaped.
        rig.faults.overrides[phase]=sequence.observation(rig.driver.context,phase,None,'UNKNOWN')
        state=rig.hold()
        self.assertEqual(state['failed_phase'],phase)
        self.assertEqual(rig.cleanups(),[operation if unit is None else operation+':'+unit
            for operation,unit in sequence.CLEANUP])
        self.assertIn('stop_unit:'+RELAY,rig.cleanups())
        self.assertIn('observe_stopped_before:'+RELAY,rig.cleanups())
        self.assertIn('observe_stopped_after:'+RELAY,rig.cleanups())
        self.assertNotIn('post_install_checks',rig.effects())

    def test_failed_relay_stop_does_not_suppress_gateway_or_final_cgroup_observation(self):
        import test_epoch7_recovery_sequence as outer
        import epoch7_recovery_sequence as sequence
        rig=outer.Rig();rig.faults.failures['effect:activate_new_services']=OSError
        rig.faults.failures['cleanup:stop_unit:'+RELAY]=OSError
        state=rig.hold()
        self.assertEqual(state['containment_status'],'UNKNOWN')
        self.assertEqual(len(rig.cleanups()),len(sequence.CLEANUP))
        self.assertIn('stop_unit:'+GW,rig.cleanups())
        self.assertIn('observe_stopped_after:'+RELAY,rig.cleanups())


if __name__=='__main__':unittest.main()
