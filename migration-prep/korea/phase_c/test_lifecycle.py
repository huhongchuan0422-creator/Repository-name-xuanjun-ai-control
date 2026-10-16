"""Real private files/signatures; account, nft, systemd and window time are models.

No process on a production host is created, started or stopped by these tests.
The production CLI cannot select this Context. Root network proof fixtures below
are SYNTHETIC and do not prove a firewall was installed on any real host.
"""
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest import mock

from gate_common import GateError, canonical_bytes
from korea.phase_c import artifact, entry, lifecycle as live, security
from korea.phase_c import install_controller as install
from korea.phase_c import test_install_controller as fixtures
Model, NOW = fixtures.Model, fixtures.NOW
from korea.shadow_acceptance import _tested_object


class LiveModel(Model, live.Context):
    def __init__(self, root):
        super().__init__(root)
        self.loaded=True;self.created=True;self.started=False;self.stopped=False;self.target=False
        self.stop_exit=0;self.start_exit=0;self.running_states=0;self.exit_status='0'
        self.fail_service=False;self.nft_drift=False;self.revoke_on_sleep=False;self.interrupt_start=False
        self.remain_process=False;self.changed_shared=False;self.key_drift=False;self.drift_lock=False
        self.current_body=None;self.readonly_checked=False;self.bad_window=False;self.restart=False
    def current_approval(self, comment_id):return self.current_body
    def verify_loaded(self, release, sha):
        artifact.verify_runtime(release,sha)
        for n in artifact.RUNTIME_FILES:
            if (Path(__file__).resolve().parents[3]/n).read_bytes()!=(release/n).read_bytes():
                raise GateError('MODEL_LOADED_CODE_DIFFERENT')
    def verify_manager_profiles(self):self.calls.append('modeled_typed_dbus')
    def table_shape(self, table):
        return '0'*64 if self.started and self.nft_drift else 'a'*64
    def verify_custody_and_snapshot(self, config, now, expires):
        # Real signatures/pair/TLS/snapshot operations are covered in separate tests.
        # This synthetic model has no production credential provider or DB.
        self.readonly_checked=True
    def temporary_objects(self,config):
        out={}
        for name in (config['credential_generation'],config['broker_private_key']):
            s=self.path(name).lstat();out[name]=(s.st_dev,s.st_ino)
        if self.stopped and self.key_drift:
            out[config['broker_private_key']]=(0,0)
        return out
    def quiescent(self,config):
        if self.stopped and self.remain_process:raise GateError('MODEL_UID_PROCESS_REMAINS')
    def now_ms(self):return int(self.time*1000)
    def sleep(self, seconds):
        self.time+=30 # Explicit accelerated model, not real elapsed observation.
        if self.revoke_on_sleep:security.write_once(self.path(live.REVOKE),b'synthetic revoke')
    def run(self,args):
        if args[1]=='is-enabled':return super().run(args)
        self.calls.append(tuple(args))
        if args[1]=='start':
            self.target=True
            if '--no-block' in args:
                self.started=True
                if self.interrupt_start:raise KeyboardInterrupt('synthetic interruption after service request')
            return subprocess.CompletedProcess(args,self.start_exit,'','')
        if args[1]=='stop':
            self.stopped=True;self.target=False
            if self.drift_lock:
                old=self.path(live.LOCK);old.rename(old.with_name('lock-preserved'));old.mkdir(mode=0o700)
            return subprocess.CompletedProcess(args,self.stop_exit,'','')
        raise AssertionError('Unexpected modeled command: '+repr(args))
    def units(self,names):
        result=super().units(names)
        if self.changed_shared and self.started:
            for name,row in result.items():
                if name in install.SHARED:row['MainPID']='100'
        if install.UNITS['network-verified.target'] in result and self.target:
            result[install.UNITS['network-verified.target']]['ActiveState']='active'
        return result
    def states(self):
        state='inactive';pid='0';result='success'
        if self.started and not self.stopped and self.time<NOW+60:
            state='active';pid='100';self.running_states+=1
        if self.fail_service and self.started and not self.stopped:state='failed';result='exit-code';pid='0'
        rows={}
        for name in ('worker.service','broker.service'):
            n=install.UNITS[name]
            usepid=pid if name=='worker.service' else ('101' if state=='active' else '0')
            if self.restart and self.running_states>1 and usepid!='0':usepid=str(int(usepid)+1)
            rows[n]=dict(Id=n,ActiveState=state,SubState='running' if state=='active' else ('failed' if state=='failed' else 'dead'),
                         MainPID=usepid,Result=result,ExecMainStatus=self.exit_status,ControlGroup='/synthetic/'+n)
        return rows
    def read_window(self,config,acceptance):
        tested=_tested_object(config)
        resource=dict(rss_mib=20,cgroup_memory_peak_mib=20,mem_available_mib=1000,swap_used_mib=0,cgroup_oom=0)
        state=dict(status='HOLD' if self.bad_window else 'PASS_SHADOW_WINDOW',window_id=acceptance['window_id'],
            acceptance_config_sha256=security.hash_value(acceptance),tested_object=tested,tested_object_sha256=security.hash_value(tested),
            writer_enabled=False,production_authorized=False,started_at_ms=NOW*1000,deadline_ms=NOW*1000+60000,
            initial_cgroup_oom=0,initial_swap_used_mib=0,samples=[dict(sample_started_ms=NOW*1000+i*30000,
            sample_finished_ms=NOW*1000+i*30000,latency_ms=0,cycle_status='PASS_READONLY_SHADOW_CYCLE',
            snapshot_generation_id='gen-'+str(i),resources=resource) for i in range(2)])
        return state


@unittest.skipUnless(os.geteuid()==0,'Root-owned private synthetic filesystem fixtures')
class LifecycleTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.InstallTests.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.InstallTests.tearDownClass.__func__)
    make_plan=fixtures.InstallTests.make_plan
    baseline=fixtures.InstallTests.baseline
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(dir=self.home));self.ctx=LiveModel(self.root)
        for path in ('/var/lib','/run','/etc/systemd/system','/etc/xuanjun-binance','/etc/xuanjun-pr99-release',
                     '/opt/xuanjun-binance/releases','/input'):
            self.ctx.path(path).mkdir(parents=True,exist_ok=True)
        self.ctx.path('/etc/xuanjun-pr99-release').chmod(0o700)
        self.ctx.path('/etc/xuanjun-pr99-release/phase-c-public-inputs').mkdir(mode=0o700)
        self.plan=self.make_plan();self.cfg=self.plan['runtime_config'];self.baseline()
        release=self.ctx.path(self.plan['render_values']['C_RELEASE']);release.mkdir(parents=True)
        _,files=install.package_bytes(self.raw)
        for name in (*artifact.RUNTIME_FILES,'PHASE_C_RUNTIME_MANIFEST.json'):
            p=release/name;p.parent.mkdir(parents=True,exist_ok=True);security.write_once(p,files[name],mode=0o444)
        config_root=self.ctx.path('/etc/xuanjun-binance-phase-c');config_root.mkdir()
        self.ctx.path(self.cfg['snapshot_root']).mkdir(parents=True)
        self.ctx.path(self.cfg['evidence_root']).mkdir(mode=0o700)
        keys=config_root/'keys';keys.mkdir()
        for name,raw in self.keys.items():security.write_once(keys/(name+'.pem'),raw,mode=0o444)
        security.write_once(self.ctx.path(live.CONFIG),canonical_bytes(self.cfg),mode=0o444)
        security.write_once(self.ctx.path(self.cfg['acceptance_path']),canonical_bytes(self.plan['acceptance_config']),mode=0o444)
        from korea.phase_c.prepare import render_units
        for name,raw in render_units(self.plan['render_values']).items():
            security.write_once(self.ctx.path('/etc/systemd/system')/install.UNITS[name],raw.encode(),mode=0o644)
        oldwork=self.ctx.path(install.WORK);oldwork.mkdir(mode=0o700)
        installedplan=canonical_bytes(self.plan);security.write_once(oldwork/'input-plan.json',installedplan)
        installed=dict(status='C_OFFLINE_CANDIDATE_INSTALLED_NOT_STARTED',lock_released=True,
            runtime_manifest_sha256=self.cfg['runtime_manifest_sha256'],source_commit='c'*40,
            plan_sha256=security.digest(installedplan))
        security.write_once(oldwork/'receipt.json',canonical_bytes(installed))
        pair=self.ctx.path(self.cfg['credential_generation']);pair.mkdir(parents=True);pair.chmod(0o711)
        for name in ('api_key','api_secret','custody.json'):security.write_once(pair/name,b'synthetic-only')
        key=self.ctx.path(self.cfg['broker_private_key']);key.parent.mkdir(mode=0o711);security.write_once(key,b'synthetic-only',mode=0o400)
        self.acceptance=copy.deepcopy(self.plan['acceptance_config'])
        self.acceptance.update(owner_approved=True,owner_approval_id='1234567',window_id='window-fixture',
            duration_seconds=60,sample_interval_seconds=30,minimum_samples=2,max_sample_gap_seconds=60)
        admit=dict(schema_version=1,action='PR99_PHASE_C_READONLY_SHADOW_V1',host=live.HOST,
            window_id=self.acceptance['window_id'],config_sha256=security.hash_value(self.cfg),
            acceptance_sha256=security.hash_value(self.acceptance),issued_at_ms=NOW*1000-1000,
            expires_at_ms=NOW*1000+120000,approval_comment_id=1234567,max_attempts=1,
            network_enforcement_verified=True,credential_readonly_verified=True,source_identity_verified=True)
        signer=security.DetachedRSA(self.home/'authority.pem',security.digest(self.keys['authority']),private_key=self.home/'authority.private')
        proof=dict(schema_version=1,host=live.HOST,policy_sha256=security.hash_value(self.cfg['network_policy']),
            table_shape_sha256='a'*64,observed_at_ms=NOW*1000-1000,expires_at_ms=NOW*1000+172800000,
            root_evidence_id='SYNTHETIC_NOT_HOST',negative_probes=[dict(uid=uid,family=family,drop_counter_delta=1,connected=False)
                for uid in (986,1986) for family in ('IPv4','IPv6')])
        proof_raw=canonical_bytes(proof);security.write_once(self.ctx.path(live.NETWORK_PROOF),proof_raw)
        self.liveplan=dict(acceptance=self.acceptance,signed_admission=dict(admission=admit,signature=signer.sign(admit)),
            network_proof_sha256=security.digest(proof_raw),installed_receipt_sha256=security.digest(canonical_bytes(installed)),stop_grace_seconds=30)
        self.path=self.ctx.path('/input/live-plan.json');security.write_once(self.path,canonical_bytes(self.liveplan))
        self.grant=dict(schema_version=1,decision='APPROVED_WITH_EXACT_PRECONDITIONS',host=live.HOST,action=live.ACTION,
            max_attempts=1,service_start_allowed=True,service_stop_allowed=True,temporary_quarantine_allowed=True,
            credential_validation_allowed=True,network_changes_allowed=False,database_export_allowed=False,writer_allowed=False,
            source_commit='c'*40,runtime_manifest_sha256=self.cfg['runtime_manifest_sha256'],plan_sha256=security.digest(self.path.read_bytes()),
            controller_sha256=security.digest(files[artifact.PREFIX+'lifecycle.py']),approval_comment_id=1234567,issued_at=NOW-1,expires_at=NOW+3600)
        self.set_pin()
    def set_pin(self,**change):
        self.grant.update(change)
        body='SYNTHETIC ONLY\n<!-- '+live.MARKER+'\n'+json.dumps(self.grant)+'\n'+live.MARKER+' -->'
        self.ctx.current_body=body
        pin=dict(approval_comment_id=1234567,approval_body_sha256=security.digest(body.encode()),approval_body=body)
        p=self.ctx.path(live.PIN)
        if p.exists():p.write_bytes(canonical_bytes(pin))
        else:security.write_once(p,canonical_bytes(pin))
    def run_live(self):return live.supervise(self.path,self.ctx)
    def receipt(self):return json.loads((self.ctx.path(live.WORK)/'receipt.json').read_bytes())
    def test_success_stop_precedes_quarantine_and_unlock(self):
        before=install.frozen_b(self.ctx);result=self.run_live()
        self.assertEqual(result['status'],'PASS_READONLY_WINDOW_STOPPED_AND_QUARANTINED')
        self.assertTrue(result['temporary_quarantined']);self.assertFalse(self.ctx.path(live.LOCK).exists())
        self.assertEqual(install.frozen_b(self.ctx),before)
        self.assertFalse(self.ctx.path(self.cfg['credential_generation']).exists())
        self.assertTrue(self.ctx.path(live.QUARANTINE).is_dir());self.assertTrue(self.ctx.readonly_checked)
        commands=[c for c in self.ctx.calls if isinstance(c,tuple)]
        self.assertEqual(sum('stop' in c for c in commands),1)
        self.assertFalse(any('daemon-reload' in c or 'enable' in c for c in commands))
        with self.assertRaises((GateError,FileNotFoundError)):self.run_live()
    def test_missing_or_edited_approval_stops_without_start(self):
        self.ctx.current_body='revoked'
        with self.assertRaises(GateError):self.run_live()
        self.assertFalse(self.ctx.path(live.WORK).exists());self.assertFalse(self.ctx.started)
    def test_old_action_wrong_scope_expired_or_wrong_controller_refused(self):
        for change in ({'action':'PR99_PHASE_B_OFFLINE_REPAIR_FINALIZE_V1'},{'writer_allowed':True},
                       {'expires_at':NOW},{'controller_sha256':'0'*64},{'network_changes_allowed':True}):
            old=copy.deepcopy(self.grant);self.set_pin(**change)
            with self.subTest(change=change),self.assertRaises(GateError):self.run_live()
            self.assertFalse(self.ctx.started);self.grant=old
        self.set_pin()
    def test_missing_kernel_proof_or_no_drop_counter_stops_before_claim(self):
        p=self.ctx.path(live.NETWORK_PROOF);proof=json.loads(p.read_bytes());proof['negative_probes'][0]['drop_counter_delta']=0
        p.write_bytes(canonical_bytes(proof))
        with self.assertRaises(GateError):self.run_live()
        self.assertFalse(self.ctx.path(live.WORK).exists());self.assertFalse(self.ctx.started)
    def test_changed_installed_unit_or_configuration_stops_before_claim(self):
        p=self.ctx.path('/etc/systemd/system')/install.UNITS['broker.service'];p.chmod(0o600);p.write_bytes(b'changed');p.chmod(0o644)
        with self.assertRaises(GateError):self.run_live()
        self.assertFalse(self.ctx.started)
    def test_network_drift_after_start_stops_but_never_reports_pass(self):
        self.ctx.nft_drift=True
        with self.assertRaises(GateError):self.run_live()
        self.assertTrue(self.ctx.stopped);r=self.receipt();self.assertEqual(r['status'],'HOLD_PRESERVE_EVIDENCE')
        self.assertTrue(r['temporary_quarantined']);self.assertTrue(self.ctx.path(live.LOCK).exists())
    def test_owner_revoke_stops_current_window_without_second_start(self):
        self.ctx.revoke_on_sleep=True
        with self.assertRaises(GateError):self.run_live()
        self.assertTrue(self.ctx.stopped);self.assertTrue(self.receipt()['temporary_quarantined'])
    def test_interrupted_start_is_unknown_until_stopped_and_preserved(self):
        self.ctx.interrupt_start=True
        with self.assertRaises(KeyboardInterrupt):self.run_live()
        self.assertTrue(self.ctx.stopped);self.assertTrue(self.receipt()['start_attempted'])
        self.assertEqual(self.receipt()['status'],'HOLD_PRESERVE_EVIDENCE')
    def test_stop_failure_never_revokes_material_from_running_processes(self):
        self.ctx.fail_service=True;self.ctx.stop_exit=1
        with self.assertRaises(GateError):self.run_live()
        r=self.receipt();self.assertFalse(r['temporary_quarantined']);self.assertEqual(r['stop_result'],'UNKNOWN_PRESERVE_EVIDENCE')
        self.assertTrue(self.ctx.path(self.cfg['credential_generation']).exists())
    def test_uid_process_remaining_blocks_quarantine(self):
        self.ctx.remain_process=True
        with self.assertRaises(GateError):self.run_live()
        self.assertFalse(self.receipt()['temporary_quarantined']);self.assertTrue(self.ctx.path(self.cfg['broker_private_key']).exists())
    def test_changed_temporary_identity_blocks_quarantine(self):
        self.ctx.key_drift=True
        with self.assertRaises(GateError):self.run_live()
        self.assertFalse(self.receipt()['temporary_quarantined'])
    def test_nonpass_or_nonzero_window_is_not_success(self):
        self.ctx.bad_window=True
        with self.assertRaises(GateError):self.run_live()
        self.assertTrue(self.ctx.stopped);self.assertEqual(self.receipt()['status'],'HOLD_PRESERVE_EVIDENCE')
    def test_protected_shared_change_aborts_only_c(self):
        self.ctx.changed_shared=True
        with self.assertRaises(GateError):self.run_live()
        self.assertTrue(self.ctx.stopped)
        self.assertFalse(any(c==('/usr/bin/systemctl','stop',*install.SHARED) for c in self.ctx.calls))
    def test_restart_pid_drift_is_rejected(self):
        self.ctx.restart=True
        with self.assertRaises(GateError):self.run_live()
        self.assertTrue(self.ctx.stopped)
    def test_lock_identity_drift_preserves_hold_after_stop(self):
        self.ctx.drift_lock=True
        with self.assertRaises(GateError):self.run_live()
        self.assertTrue(self.ctx.stopped);self.assertTrue(self.ctx.path(live.LOCK).exists())


class PrimitiveTests(unittest.TestCase):
    def test_nft_shape_ignores_counter_metadata_only_not_semantic_changes(self):
        a={'nftables':[{'metainfo':{'json_schema_version':1}},{'rule':{'family':'inet','table':'fixture','chain':'output',
            'handle':2,'expr':[{'counter':{'packets':1,'bytes':40}},{'match':{'op':'==','left':{'meta':{'key':'skuid'}},'right':986}},{'drop':None}]}}]}
        b=copy.deepcopy(a);b['nftables'][1]['rule']['handle']=3;b['nftables'][1]['rule']['expr'][0]['counter']['packets']=100
        self.assertEqual(live.nft_shape(a),live.nft_shape(b))
        b['nftables'][1]['rule']['expr'][1]['match']['right']=0
        self.assertNotEqual(live.nft_shape(a),live.nft_shape(b))
    def test_nonfinite_exponent_and_normal_numeric_types(self):
        value=security.strict_json(b'{"a":123,"b":1.5}')
        self.assertIs(type(value['a']),int);self.assertIs(type(value['b']),float)
        for raw in (b'1e9999',b'{"x":-1e9999}',b'[NaN]'):
            with self.assertRaises(GateError):security.strict_json(raw)
    def test_notify_ready_is_sent_only_to_systemd_socket(self):
        with mock.patch.dict(os.environ,{},clear=True),self.assertRaises(GateError):entry.notify_ready()
        fake=mock.MagicMock();fake.__enter__.return_value=fake;fake.send.return_value=7
        with mock.patch.dict(os.environ,{'NOTIFY_SOCKET':'@synthetic-notify'},clear=True),\
             mock.patch.object(socket,'socket',return_value=fake):entry.notify_ready()
        fake.connect.assert_called_once_with('\x00synthetic-notify');fake.send.assert_called_once_with(b'READY=1')
