import base64
import copy
import json
import importlib.util
import sys
import os
import shutil
import stat
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import epoch7_runtime_effects as m


def fixture():
    return {'manifest_sha256':m.MANIFEST,
        'activation_proposal':{'epoch':8,'state':'PREPARED','db_path':m.delta.DB,
                               'release_sha256':m.MANIFEST,'generation':1},
        'runtime':{'release_directory':'integration-'+m.MANIFEST[:16],
          'services':list(m.ALLOWED_SERVICES),'sandbox_policy':{'fixture':True},
          'prerequisites':{},'plugin':{
            'id':m.P2_PLUGIN_ID,'gateway_service':m.GATEWAY_SERVICE,
            'openclaw_bin':'/home/xuanjun_dev/.openclaw/bin/openclaw',
            'service_user':'xuanjun_dev','source':'plugins/p2-native-controller',
            'binding_file':'/etc/xuanjun-development/p2-native-controller.binding.json',
            'binding_sha256':'a'*64}}}


def context():
    return {'runtime_manifest_sha256':m.MANIFEST,'transaction_id':m.delta.TX,
            'expected_epoch':7,'proposed_prepared_epoch':8,'context_sha256':'b'*64}


def db_before():
    return {'device':1,'inode':2,'uid':0,'gid':0,'mode':0o600,'size':4096,
            'mtime_ns':123,'ctime_ns':123,'nlink':1}


def info(row):
    return types.SimpleNamespace(st_mode=stat.S_IFREG|row['mode'],
        **dict(('st_'+k,v) for k,v in row.items() if k not in ('mode','device','inode')),
        st_dev=row['device'],st_ino=row['inode'])


class Runner(object):
    def __init__(self, owner, contract, guard, diagnostics):
        self.owner,self.contract,self.guard,self.diagnostics = owner,contract,guard,diagnostics
        self.poisoned = False
    def run(self,key):
        if self.poisoned: raise ValueError('FAKE_POISONED')
        assert self.guard() is True
        self.owner.calls.append(key)
        if key in self.owner.fail:
            self.poisoned = True
            raise RuntimeError('FIXED_FAILURE')
        if key in self.owner.outputs: return self.owner.outputs[key]
        spec = self.contract[key]
        code,out = 0,b''
        if key == 'inventory': out = b'{"plugins":[]}'
        elif key in ('inventory_installed','cleanup_inventory'):
            out = m.packed({'plugins':[] if key=='cleanup_inventory' and 'uninstall' in self.owner.calls else [{'id':m.P2_PLUGIN_ID}]})
        elif key.startswith('inspect_'):
            out = m.packed({'id':m.P2_PLUGIN_ID,'tools':['xuanjun.execution.start','xuanjun.execution.inspect']})
        elif spec['operation'] == 'boot_is_enabled':
            state = self.owner.boot[spec['argv'][-1]]
            code,out = (0,b'enabled\n') if state == 'enabled' else (1,b'disabled\n')
        elif spec['operation'] == 'boot_enable': self.owner.boot[spec['argv'][-1]] = 'enabled'
        elif spec['operation'] == 'boot_disable': self.owner.boot[spec['argv'][-1]] = 'disabled'
        elif key.startswith(('stopped_','gateway_stopped')): code = 3
        return subprocess.CompletedProcess(None,code,out,b'')


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.plan,self.ctx = fixture(),context()
        self.calls,self.fail,self.outputs,self.runners = [],set(),{},[]
        self.boot = dict((u,'disabled') for u in m.BOOT_UNITS)
        self.diag = m.BoundedDiagnostics(Mock())
        self.descriptor = Mock(return_value=dict(self.plan['activation_proposal'],state='QUIESCED'))
        self.guard,self.cleanup_guard = Mock(return_value=True),Mock(return_value=True)
        self.sandbox = Mock(journal='/fixture/epoch8-sandbox-profile.json',
                            backup='/fixture/epoch8-sandbox-profile-original.json',
                            candidate='/fixture/epoch8-sandbox-profile-candidate.json')
        self.access = Mock(side_effect=lambda c,d:m.observation(c,'verify_runtime_access','c'*64))
        self.post = Mock(side_effect=lambda c,d:m.observation(c,'post_install_checks','d'*64))
        self.rows = {}
    def factory(self,contract,guard,diagnostics):
        runner = Runner(self,contract,guard,diagnostics); self.runners.append(runner); return runner
    def make(self,**kwargs):
        args = dict(directory=m.TRANSACTION,compiled=self.plan,context=self.ctx,
            descriptor_reader=self.descriptor,phase_guard=self.guard,cleanup_guard=self.cleanup_guard,
            diagnostics=self.diag,database_before=db_before(),runtime_access_check=self.access,
            postcheck=self.post,boot_before=copy.deepcopy(self.boot),
            runner_factory=self.factory,sandbox_factory=lambda *unused:self.sandbox)
        args.update(kwargs); result=m.Epoch7RuntimeEffects(**args)
        result._authority = Mock()
        def create(name,row):
            if name in self.rows: raise ValueError('EXISTING_JOURNAL')
            row = dict(row,schema=1,context_sha256=self.ctx['context_sha256']);self.rows[name]=row
            return row
        def save(name,before,after):
            self.assertEqual(self.rows[name],before);self.rows[name]=after
        result._create,result._save = Mock(side_effect=create),Mock(side_effect=save)
        result._read = Mock(side_effect=lambda name:copy.deepcopy(self.rows[name]))
        return result
    def test_finite_exact_contract_no_tls_or_unbounded_shell(self):
        forward,cleanup=m.command_contract(self.plan,False)
        self.assertEqual((len(forward),len(cleanup)),(91,76))
        for contract in (forward,cleanup):
            m.ExactCommandRunner(contract,lambda:True,self.diag,Mock())
            for spec in contract.values():
                self.assertLessEqual(spec['timeout'],60)
                self.assertEqual(spec['cwd'],'/')
                self.assertNotIn('certbot',str(spec['argv']))
                self.assertFalse(any(a in ('renew','--dry-run','certonly') for a in spec['argv']))
                self.assertNotIn('/bin/sh',spec['argv'])
        self.assertIn(m.TLS_TIMER,forward['start_12']['argv'])
    def test_manifest_service_and_plugin_identity_cannot_drift(self):
        for change in ('manifest','services','plugin'):
            p=fixture()
            if change=='manifest':p['manifest_sha256']='e'*64
            elif change=='services':p['runtime']['services'].reverse()
            else:p['runtime']['plugin']['source']='plugins/other'
            with self.assertRaises(ValueError):m.command_contract(p,False)
    def test_explicit_callbacks_exact_db_and_boot_required(self):
        for kwargs in ({'runtime_access_check':None},{'database_before':dict(db_before(),uid=1003)},
                       {'boot_before':{}},{'directory':'/tmp/other'},
                       {'activate_retained_renewal_timer':1}):
            with self.assertRaises(ValueError):self.make(**kwargs)
    def test_context_and_diagnostics_cannot_be_replaced(self):
        r=self.make()
        with self.assertRaises(ValueError):r.apply_fresh_sandbox(dict(self.ctx,expected_epoch=6),self.diag)
        self.assertEqual(self.calls,[])
    def test_nonliteral_guard_fails_before_commands(self):
        self.guard.return_value=1;r=self.make()
        with self.assertRaises(ValueError):r.apply_fresh_sandbox(self.ctx,self.diag)
        self.assertEqual(self.calls,[])
    def test_sandbox_gateway_quiesced_before_fresh_apply_and_no_retry(self):
        r=self.make();result=r.apply_fresh_sandbox(self.ctx,self.diag)
        self.assertEqual(self.calls,['gateway_stop','gateway_stopped'])
        self.sandbox.apply.assert_called_once_with(self.plan['runtime']['sandbox_policy'])
        self.assertEqual(result['operation'],'apply_fresh_sandbox')
        with self.assertRaises(ValueError):r.apply_fresh_sandbox(self.ctx,self.diag)
    def test_wrong_descriptor_before_any_sandbox_effect(self):
        self.descriptor.return_value['state']='PREPARED';r=self.make()
        with self.assertRaises(ValueError):r.apply_fresh_sandbox(self.ctx,self.diag)
        self.assertEqual(self.calls,[]);self.sandbox.apply.assert_not_called()
    def install(self,r):
        with patch.object(m.os.path,'isdir',return_value=True):
            return r.install_verified_plugin(self.ctx,self.diag)
    def test_plugin_refresh_order_and_owned_journal(self):
        r=self.make();self.install(r)
        self.assertEqual(self.calls,['inventory','install','config_set','plugin_enable','config_validate','inventory_installed'])
        self.assertEqual(self.rows[m.JOURNALS[3]]['state'],'INSTALLED')
        self.assertEqual(self.rows[m.JOURNALS[3]]['previous'],'ABSENT')
        self.assertEqual(self.sandbox.capture.call_count,6)
    def test_present_plugin_holds_without_install_or_uninstall(self):
        self.outputs['inventory']=subprocess.CompletedProcess(None,0,m.packed({'id':m.P2_PLUGIN_ID}),b'')
        r=self.make()
        with self.assertRaises(ValueError):self.install(r)
        self.assertEqual(self.calls,['inventory'])
        self.assertEqual(self.rows[m.JOURNALS[3]]['previous'],'UNKNOWN')
    def test_invalid_duplicate_inventory_and_missing_after_inventory_hold(self):
        for key,output in [('inventory',b'{"plugins":[],"plugins":[]}'),('inventory_installed',b'[]')]:
            self.setUp();self.outputs[key]=subprocess.CompletedProcess(None,0,output,b'')
            with self.assertRaises(ValueError):self.install(self.make())
            self.assertNotEqual(self.rows[m.JOURNALS[3]]['state'],'INSTALLED')
    def test_command_failure_still_captures_mutated_profile(self):
        r=self.make();self.fail.add('install')
        with self.assertRaisesRegex(RuntimeError,'FIXED_FAILURE'):self.install(r)
        self.assertEqual(self.calls,['inventory','install'])
        self.assertEqual(self.sandbox.capture.call_count,2)
    def test_database_journal_precedes_fchown_and_exact_reopen(self):
        r=self.make();r._database_identity=Mock(return_value=(1003,1006))
        before=db_before();after=dict(before,uid=1003,gid=1006,ctime_ns=124)
        events=[];original=r._create
        def create(*args):events.append('journal');return original(*args)
        r._create=create
        with patch.object(m.os.path,'lexists',return_value=False), \
             patch.object(m.os.path,'realpath',side_effect=lambda p:p), \
             patch.object(m.os,'open',return_value=12),patch.object(m.os,'close') as close, \
             patch.object(m.os,'fstat',side_effect=[info(before),info(after)]), \
             patch.object(m.os,'lstat',side_effect=[info(before),info(after),info(after)]), \
             patch.object(m.os,'fchown',side_effect=lambda *a:events.append('chown')) as chown, \
             patch.object(m.os,'fsync'):
            result=r.reopen_existing_database(self.ctx,self.diag)
        self.assertEqual(events,['journal','chown']);chown.assert_called_once_with(12,1003,1006)
        close.assert_called_once_with(12);self.assertEqual(self.calls,['database_reopen'])
        self.assertEqual(self.rows[m.JOURNALS[4]]['state'],'REOPENED')
        self.assertEqual(result['operation'],'reopen_existing_database')
    def test_database_sidecar_or_metadata_drift_causes_no_chown(self):
        for sidecar in (True,False):
            self.setUp();r=self.make();r._database_identity=Mock(return_value=(1003,1006))
            with patch.object(m.os.path,'lexists',return_value=sidecar), \
                 patch.object(m.os,'open',return_value=12),patch.object(m.os,'close'), \
                 patch.object(m.os,'fstat',return_value=info(dict(db_before(),inode=9))), \
                 patch.object(m.os,'fchown') as chown:
                with self.assertRaises(ValueError):r.reopen_existing_database(self.ctx,self.diag)
                chown.assert_not_called()
    def test_access_callback_required_actual_observation(self):
        r=self.make();self.rows[m.JOURNALS[4]]={'state':'REOPENED'}
        result=r.verify_runtime_access(self.ctx,self.diag)
        self.assertEqual(result['evidence_sha256'],'c'*64)
        self.access.assert_called_once_with(self.ctx,self.diag)
    def test_access_callback_cannot_claim_unknown(self):
        r=self.make();self.rows[m.JOURNALS[4]]={'state':'REOPENED'}
        self.access.side_effect=None;self.access.return_value=m.observation(self.ctx,'verify_runtime_access',None,'UNKNOWN')
        with self.assertRaises(ValueError):r.verify_runtime_access(self.ctx,self.diag)
    def test_missing_timer_review_holds_before_activation(self):
        r=self.make()
        with self.assertRaisesRegex(ValueError,'RENEWAL_TIMER_REVIEW_REQUIRED'):
            r.activate_new_services(self.ctx,self.diag)
        self.assertEqual(self.calls,[])
    def test_activation_boot_intent_before_enables_and_timer_last(self):
        r=self.make(activate_retained_renewal_timer=True)
        self.descriptor.return_value['state']='ACTIVE'
        with patch.object(m.os.path,'lexists',return_value=False), \
             patch('owner_feishu_https.installed_binding',return_value={'package_sha256':m.MANIFEST}):
            r.activate_new_services(self.ctx,self.diag)
        self.assertEqual(self.rows[m.JOURNALS[5]]['state'],'ENABLED')
        self.assertEqual(self.calls[-2:],['start_12','active_12'])
        self.assertLess(self.calls.index('inspect_activate'),self.calls.index('start_01'))
        self.assertEqual(self.calls.count('daemon_reload'),1)
    def test_boot_snapshot_drift_rejects_before_enable(self):
        r=self.make();self.boot[m.BOOT_UNITS[0]]='enabled';r.phase='activate_new_services'
        with patch.object(m.os.path,'lexists',return_value=False):
            with self.assertRaises(ValueError):r._enable_boot()
        self.assertFalse(any(k.startswith('boot_enable') for k in self.calls))
    def test_cleanup_per_unit_runner_survives_forward_and_other_cleanup_failure(self):
        r=self.make();r.runner.poisoned=True;self.fail.add('stop_00')
        with self.assertRaises(RuntimeError):r.stop_unit(self.ctx,m.STOP_UNITS[0],self.diag)
        r.stop_unit(self.ctx,m.STOP_UNITS[1],self.diag)
        self.assertEqual(self.calls,['stop_00','stop_01'])
        self.assertIsNot(self.runners[-1],self.runners[-2])
    def test_exact_runner_launches_later_cleanup_after_first_failure(self):
        launches=Mock(return_value=Mock())
        def capture(process,phase,operation,epoch,sequence,*limits):
            code=2 if sequence==1 else 0
            e={'schema':1,'failed_stage':phase+'_INTENT','operation':operation,
               'epoch':epoch,'sequence':sequence,'reason':'EXIT_NONZERO' if code else 'SUCCESS',
               'returncode':code,'interruption_requires_propagation':False}
            for name in ('stdout','stderr'):
                e[name]={'prefix_b64':'','retained_bytes':0,'observed_bytes':0,
                         'prefix_sha256':m.sha(b''),'eof_observed':True,'truncated':False}
            return e
        self.diag=m.BoundedDiagnostics(Mock(),capture)
        factory=lambda contract,guard,diag:m.ExactCommandRunner(contract,guard,diag,launches)
        r=self.make(runner_factory=factory);r.runner.poisoned=True
        self.diag.start_scope('stop_first')
        with self.assertRaises(Exception):r.stop_unit(self.ctx,m.STOP_UNITS[0],self.diag)
        self.diag.start_scope('stop_second')
        r.stop_unit(self.ctx,m.STOP_UNITS[1],self.diag)
        self.assertEqual(launches.call_count,2)
        self.assertEqual(launches.call_args_list[0][0][0],['/usr/bin/systemctl','stop',m.STOP_UNITS[0]])
        self.assertEqual(launches.call_args_list[1][0][0],['/usr/bin/systemctl','stop',m.STOP_UNITS[1]])
        self.assertEqual(self.diag.sequence,2)
    def test_cleanup_item_cannot_retry_uncertain_stop(self):
        r=self.make();self.fail.add('stop_00')
        with self.assertRaises(RuntimeError):r.stop_unit(self.ctx,m.STOP_UNITS[0],self.diag)
        with self.assertRaisesRegex(ValueError,'CLEANUP_NO_RETRY'):
            r.stop_unit(self.ctx,m.STOP_UNITS[0],self.diag)
        self.assertEqual(self.calls,['stop_00'])
    def test_stop_unknown_unit_and_observation_scope_refused(self):
        r=self.make()
        with self.assertRaises(ValueError):r.stop_unit(self.ctx,'unreviewed.service',self.diag)
        with self.assertRaises(ValueError):r.observe_stopped(self.ctx,'other',m.STOP_UNITS[0],self.diag)
        self.assertEqual(self.calls,[])
    def test_boot_cleanup_preserves_baseline_enabled_units(self):
        self.boot[m.BOOT_UNITS[0]]='enabled';r=self.make()
        self.rows[m.JOURNALS[5]]={'units':list(m.BOOT_UNITS),'previous':dict(self.boot),'state':'ENABLE_INTENT'}
        self.boot=dict((u,'enabled') for u in m.BOOT_UNITS)
        with patch.object(m.os.path,'lexists',return_value=True):r.preserve_boot_inhibition(self.ctx,self.diag)
        self.assertNotIn('disable_00',self.calls)
        self.assertEqual(self.boot[m.BOOT_UNITS[0]],'enabled')
        self.assertTrue(all(self.boot[u]=='disabled' for u in m.BOOT_UNITS[1:]))
    def test_boot_cleanup_failure_attempts_remaining_units(self):
        r=self.make();self.rows[m.JOURNALS[5]]={'units':list(m.BOOT_UNITS),'previous':dict(self.boot),'state':'ENABLE_INTENT'}
        self.fail.add('disable_00')
        with patch.object(m.os.path,'lexists',return_value=True):
            with self.assertRaises(RuntimeError):r.preserve_boot_inhibition(self.ctx,self.diag)
        self.assertIn('disable_12',self.calls)
        self.assertEqual(self.rows[m.JOURNALS[5]]['state'],'ENABLE_INTENT')
    def test_real_runner_boot_failure_does_not_skip_later_launches(self):
        launches=Mock(return_value=Mock())
        def capture(process,phase,operation,epoch,sequence,*limits):
            code=2 if sequence==1 else (1 if operation=='boot_is_enabled' else 0)
            raw=b'disabled\n' if operation=='boot_is_enabled' else b''
            e={'schema':1,'failed_stage':phase+'_INTENT','operation':operation,
               'epoch':epoch,'sequence':sequence,'reason':'EXIT_NONZERO' if code else 'SUCCESS',
               'returncode':code,'interruption_requires_propagation':False}
            for name,value in (('stdout',raw),('stderr',b'')):
                e[name]={'prefix_b64':base64.b64encode(value).decode(),'retained_bytes':len(value),
                         'observed_bytes':len(value),'prefix_sha256':m.sha(value),
                         'eof_observed':True,'truncated':False}
            return e
        self.diag=m.BoundedDiagnostics(Mock(),capture)
        self.diag.start_scope('cleanup:preserve_boot_inhibition')
        factory=lambda contract,guard,diag:m.ExactCommandRunner(contract,guard,diag,launches)
        r=self.make(runner_factory=factory)
        self.rows[m.JOURNALS[5]]={'units':list(m.BOOT_UNITS),'previous':dict(self.boot),'state':'ENABLE_INTENT'}
        with patch.object(m.os.path,'lexists',return_value=True):
            with self.assertRaises(Exception):r.preserve_boot_inhibition(self.ctx,self.diag)
        self.assertEqual(launches.call_count,25)
        self.assertEqual(launches.call_args_list[1][0][0],['/usr/bin/systemctl','disable',m.BOOT_UNITS[1]])
        self.assertEqual(self.diag.sequence,25)
        self.assertEqual(self.diag.scope,'cleanup:preserve_boot_inhibition')
        self.assertEqual(self.diag.scope_failure.summary['sequence'],1)
        self.assertEqual(self.diag.scope_failure.summary['operation'],'boot_disable')
    def test_full_containment_reuses_frozen_state_and_cgroup_primitive(self):
        import epoch3_service_containment as module
        scanner=Mock();scanner.bounded_file_inventory.return_value={}
        r=self.make(containment_scanner=scanner);unit=m.STOP_UNITS[1]
        self.outputs['show_01']=subprocess.CompletedProcess(None,0,
            b'LoadState=loaded\nActiveState=inactive\nSubState=dead\nMainPID=0\nControlPID=0\nControlGroup=\n',b'')
        directory=types.SimpleNamespace(st_mode=stat.S_IFDIR|0o755,st_uid=0,st_dev=1,st_ino=2)
        with patch.dict(sys.modules,{'epoch3_service_containment':module}), \
             patch.object(m.os.path,'realpath',side_effect=lambda p:p), \
             patch.object(m.os,'open',return_value=12),patch.object(m.os,'close'), \
             patch.object(m.os,'fstat',return_value=directory), \
             patch.object(m.os,'stat',return_value=directory),patch.object(m.os,'listdir',return_value=[]):
            result=r.observe_stopped(self.ctx,'observe_stopped_before',unit,self.diag)
        self.assertEqual(self.calls,['show_01','show_01'])
        scanner.bounded_file_inventory.assert_called_once_with('/sys/fs/cgroup/systemd/system.slice/'+unit,
                                                              optional=True,cgroup=True)
        self.assertEqual(scanner.verify_systemd_controller_mount.call_count,2)
        self.assertEqual(result['operation'],'observe_stopped_before:'+unit)
    def test_containment_requires_real_scanner_dependency(self):
        r=self.make()
        with self.assertRaisesRegex(ValueError,'REVIEWED_CONTAINMENT_SCANNER_REQUIRED'):
            r.observe_stopped(self.ctx,'observe_stopped_before',m.STOP_UNITS[0],self.diag)
        self.assertEqual(self.calls,[])
    def test_plugin_cleanup_only_owned_absence_and_own_sandbox(self):
        r=self.make();self.rows[m.JOURNALS[3]]={'previous':'ABSENT','state':'INSTALLED'}
        with patch.object(m.os.path,'lexists',return_value=True):r.restore_owned_epoch7_sandbox(self.ctx,self.diag)
        self.assertEqual(self.calls,['cleanup_inventory','uninstall','unset_config','unset_entry','cleanup_validate','cleanup_inventory'])
        self.sandbox.rollback.assert_called_once();self.assertEqual(self.rows[m.JOURNALS[3]]['state'],'RESTORED')
    def test_unproven_plugin_ownership_forbids_cleanup(self):
        r=self.make();self.rows[m.JOURNALS[3]]={'previous':'UNKNOWN','state':'INVENTORY_INTENT'}
        with patch.object(m.os.path,'lexists',return_value=True):
            with self.assertRaises(ValueError):r.restore_owned_epoch7_sandbox(self.ctx,self.diag)
        self.assertEqual(self.calls,[]);self.sandbox.rollback.assert_not_called()
    def test_postcheck_requires_bound_callback_not_stale_acme_claim(self):
        r=self.make();self.descriptor.return_value['state']='ACTIVE'
        result=r.post_install_checks(self.ctx,self.diag)
        self.assertEqual(result['evidence_sha256'],'d'*64)
        self.assertEqual(len(self.calls),14);self.post.assert_called_once_with(self.ctx,self.diag)
    def test_secrets_not_echoed_by_json_errors(self):
        with self.assertRaises(ValueError) as ctx:m.strict_json(b'{"secret":PRIVATE_TOKEN}')
        self.assertNotIn('PRIVATE_TOKEN',str(ctx.exception))


class FreshSandboxTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.mkdtemp();os.chmod(self.directory,0o700)
        self.old=m.packed({'agents':{'entries':{'developer':{},'platform-engineer':{}}}})
        candidate=json.loads(self.old.decode())
        for role,access in (('developer','rw'),('platform-engineer','ro')):
            candidate['agents']['entries'][role]['sandbox']={'mode':'all','workspaceAccess':access,'scope':'agent',
                'docker':{'image':m.profile.IMAGE,'user':'1002:1002','network':'none','readOnlyRoot':True,
                          'capDrop':['ALL'],'binds':[],'tmpfs':[]}}
        self.new=m.packed(candidate);self.current=self.old
        self.read=lambda path:open(path,'rb').read()
        self.sandbox=m.FreshSandboxProfile(self.directory,'f'*64,lambda:True)
        self.sandbox.authority=Mock();self.sandbox.prepare=Mock(return_value=(self.old,self.new))
        self.patches=[patch.object(m,'private_read',side_effect=self.read),
                      patch.object(m.profile,'private_read',side_effect=self.read),
                      patch.object(m.profile,'read_profile',side_effect=lambda:self.current),
                      patch.object(m.profile,'publish',side_effect=self.publish)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        shutil.rmtree(self.directory)
    def publish(self,raw):self.current=raw
    def test_fresh_journals_do_not_replay_restored_old_files(self):
        old_path=self.directory+'/sandbox-profile.json'
        with open(old_path,'wb') as f:f.write(b'OLD_RESTORED_SENTINEL')
        self.sandbox.apply({})
        self.assertEqual(self.read(old_path),b'OLD_RESTORED_SENTINEL')
        self.assertEqual(self.current,self.new)
        self.assertEqual(self.sandbox.row()[0]['context_sha256'],'f'*64)
        with self.assertRaises(ValueError):self.sandbox.apply({})
    def test_fresh_profile_capture_and_restore_exact_original(self):
        self.sandbox.apply({});candidate=json.loads(self.new.decode())
        candidate['plugins']={'entries':{m.P2_PLUGIN_ID:{'enabled':True}}}
        self.current=m.packed(candidate);self.sandbox.capture();self.sandbox.rollback()
        self.assertEqual(self.current,self.old);self.assertEqual(self.sandbox.row()[0]['state'],'RESTORED')
    def test_unrelated_profile_drift_holds_restoration(self):
        self.sandbox.apply({});self.current=b'{"unrelated":true}'
        with self.assertRaises(ValueError):self.sandbox.capture()
        with self.assertRaises(ValueError):self.sandbox.rollback()
    def test_foreign_context_journal_rejected(self):
        self.sandbox.apply({});row=json.loads(self.read(self.sandbox.journal).decode());row['context_sha256']='0'*64
        with open(self.sandbox.journal,'wb') as f:f.write(m.packed(row))
        with self.assertRaises(ValueError):self.sandbox.row()


if __name__=='__main__':unittest.main()
