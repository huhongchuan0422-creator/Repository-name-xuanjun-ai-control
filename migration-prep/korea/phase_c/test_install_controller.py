"""Root-filesystem install model; subprocess/account/systemd actions are fakes.

No installed source, credentials, DB, nft or real host account is operated on.
Production CLI has no model override. Hosted CI additionally exercises real
file ownership on the isolated runner, not Korea server execution.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from gate_common import canonical_bytes, GateError
from korea.phase_c import artifact, authorization as auth, install_controller as ctl, security

NOW = 1792140000


class Model(ctl.Context):
    def __init__(self, root):
        self.root=root;self.calls=[];self.loaded=False;self.created=False;self.fail_at=None
        self.time=NOW;self.reload_exit=0;self.preexisting=False;self.mutate_shared=False
        self.clock_callback=None
    def path(self, value):return self.root/str(value).lstrip('/')
    def now(self):return self.time
    def check_identity(self):pass  # Model explicitly does not claim actual hostname or host root.
    def current_approval(self, comment_id):
        return json.loads(self.path(ctl.PIN).read_bytes())['approval_body']
    def loaded_source(self, files):
        origin=Path(__file__).resolve().parents[3]
        for name in artifact.RUNTIME_FILES:
            if (origin/name).read_bytes()!=files[name]:raise GateError('C_EXECUTING_SOURCE_NOT_PACKAGE')
    def account_preflight(self, uid, gid):
        return dict(create_worker=not self.created,worker_uid=uid,worker_gid=gid)
    def create_worker(self, identity):self.created=True;self.calls.append('create_worker')
    def verify_units(self):self.calls.append('verify_units')
    def verify_manager_profiles(self):self.calls.append('typed_manager_profiles')
    def checkpoint(self, name):
        if self.clock_callback:self.clock_callback(name)
        if self.fail_at==name:raise RuntimeError('synthetic interruption')
    def run(self, args):
        self.calls.append(tuple(args))
        if args[0]=='/usr/bin/openssl':
            return subprocess.run(args,capture_output=True,text=True,timeout=10)
        if args[1:] == ['daemon-reload']:
            self.loaded=True
            return subprocess.CompletedProcess(args,self.reload_exit,'','')
        if args[1]=='is-enabled':
            value='disabled' if args[2]=='xuanjun-binance-shadow.service' else 'static'
            return subprocess.CompletedProcess(args,1 if value=='disabled' else 0,value+'\n','')
        raise AssertionError('Unexpected root command in model: '+repr(args))
    def units(self,names):
        rows={}
        for name in names:
            is_b=name=='xuanjun-binance-shadow.service'
            new=name in ctl.UNITS.values()
            loaded=is_b or not new or self.loaded or self.preexisting
            rows[name]=dict(Id=name,LoadState='loaded' if loaded else 'not-found',ActiveState='inactive',
                SubState='dead',MainPID='0',FragmentPath=str(self.path('/etc/systemd/system')/name) if loaded else '',
                DropInPaths='',User='xuanjun_binance',Group='xuanjun_binance')
            if new and name.endswith('.service'):
                rows[name]['Group']='xuanjun_binance_shadow'
                if name==ctl.UNITS['worker.service']:rows[name]['User']='xuanjun_binance_shadow'
            if self.mutate_shared and self.loaded and name in ctl.SHARED:rows[name]['MainPID']='1234'
        return rows


@unittest.skipUnless(os.geteuid()==0,'Root-owned synthetic fixtures require hosted root')
class InstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(dir='/root',prefix='pr99-c-install-tests-')
        cls.home=Path(cls.tmp.name);cls.keys={}
        for name in ('broker','source','authority'):
            private=cls.home/(name+'.private');public=cls.home/(name+'.pem')
            subprocess.run(['/usr/bin/openssl','genrsa','-out',str(private),'2048'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            subprocess.run(['/usr/bin/openssl','rsa','-in',str(private),'-pubout','-out',str(public)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            public.chmod(0o644);private.chmod(0o600);cls.keys[name]=public.read_bytes()
        cls.origin=Path(__file__).resolve().parents[3]
        cls.archive=cls.home/'review.tar.gz'
        cls.build=artifact.build(cls.origin,'c'*40,cls.archive)
        cls.raw=cls.archive.read_bytes()
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(dir=self.home))
        self.ctx=Model(self.root)
        for path in ('/var/lib','/run','/etc/systemd/system','/etc/xuanjun-binance','/etc/xuanjun-pr99-release',
                     '/opt/xuanjun-binance/releases','/input'):
            self.ctx.path(path).mkdir(parents=True,exist_ok=True)
        self.ctx.path('/etc/xuanjun-pr99-release').chmod(0o700)
        self.ctx.path('/etc/xuanjun-pr99-release/phase-c-public-inputs').mkdir(mode=0o700)
        self.install_archive=self.ctx.path('/input/review.tar.gz');security.write_once(self.install_archive,self.raw)
        self.plan=self.make_plan()
        self.plan_path=self.ctx.path('/input/plan.json');security.write_once(self.plan_path,canonical_bytes(self.plan))
        self.baseline()
        self.pin_path=self.ctx.path(ctl.PIN)
        self.approval,self.pin=self.make_pin()
        security.write_once(self.pin_path,canonical_bytes(self.pin))
    def make_plan(self):
        sha=self.build['runtime_manifest_sha256'];root='/etc/xuanjun-binance-phase-c'
        network=dict(schema_version=1,table='xj_pr99_c_fixture',broker_uid=986,worker_uid=1986,
                     pinned_ips=['8.8.8.8'],issued_at_ms=NOW*1000-1000,expires_at_ms=NOW*1000+172800000)
        config=dict(schema_version=1,feature_id='TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1',
            account_id='synthetic-account',symbols=['BTCUSDT','ETHUSDT','SOLUSDT'],
            business_database='/var/lib/xuanjun-binance-phase-c/snapshots/unused.sqlite',
            evidence_root='/var/lib/xuanjun-binance-phase-c/evidence',credential_role='BINANCE_ACCOUNT_READONLY',
            snapshot_max_age_ms=30000,capture_timeout_ms=30000,runtime_manifest_sha256=sha,
            snapshot_refresh_protocol='XUANJUN_SQLITE_WAL_BACKUP_ATOMIC_HANDOFF_V1',
            snapshot_publisher_identity_sha256=security.digest(self.keys['source']),
            verifier_sha256=security.digest((self.origin/'migration-prep/korea/phase_c/security.py').read_bytes()),
            writer_enabled=False,scheduler_enabled=False,snapshot_reader_uid=1986,network_policy=network,
            snapshot_root='/var/lib/xuanjun-binance-phase-c/snapshots',socket_path='/run/xuanjun-phase-c-broker/broker.sock',
            credential_generation='/run/xuanjun-phase-c-credentials/synthetic-generation',secret_ref='SecretRef:READONLY_FIXTURE',
            custody_attestation_sha256='a'*64,broker_private_key='/run/xuanjun-phase-c-private-keys/broker.pem',
            admission_path=root+'/live-admission.json',acceptance_path=root+'/acceptance.json')
        inputs={}
        for name,data in self.keys.items():
            config[name+'_public_key']=root+'/keys/'+name+'.pem'
            config[name+'_public_key_sha256']=security.digest(data)
            source='/etc/xuanjun-pr99-release/phase-c-public-inputs/'+name+'.pem';security.write_once(self.ctx.path(source),data,mode=0o644)
            inputs[name]=dict(path=source,sha256=security.digest(data))
        acceptance=json.loads((self.origin/'migration-prep/korea/shadow-acceptance.template.json').read_text())
        values=dict(C_RELEASE='/opt/xuanjun-binance-phase-c/releases/'+sha,PYTHON='/usr/bin/python3.11',
            C_CONFIG=root+'/runtime.json',C_CONFIG_ROOT=root,C_CREDENTIAL_ROOT='/run/xuanjun-phase-c-credentials',
            C_KEY_ROOT=root+'/keys',C_PRIVATE_KEY_ROOT='/run/xuanjun-phase-c-private-keys',
            C_SNAPSHOT_ROOT=config['snapshot_root'],C_EVIDENCE_ROOT=config['evidence_root'],RUNTIME_SECONDS=86400)
        return dict(schema_version=1,host=auth.HOST,runtime_config=config,acceptance_config=acceptance,
                    render_values=values,worker_gid=1986,public_key_inputs=inputs)
    def baseline(self):
        release=self.ctx.path(ctl.B_RELEASE);release.mkdir(parents=True)
        files=[]
        for index in range(17):
            name='migration-prep/f%d.py'%index;target=release/name;target.parent.mkdir(exist_ok=True)
            raw=('synthetic frozen B %d'%index).encode();security.write_once(target,raw,mode=0o444)
            files.append(dict(path=name,sha256=security.digest(raw),size=len(raw)))
        raw=canonical_bytes(dict(files=files));security.write_once(release/'minimal-runtime-manifest.json',raw,mode=0o444)
        self.ctx.b_manifest_sha=security.digest(raw)
        security.write_once(self.ctx.path('/etc/systemd/system/xuanjun-binance-shadow.service'),b'synthetic B unit',mode=0o644)
        self.ctx.b_unit_sha=security.digest(b'synthetic B unit')
        security.write_once(self.ctx.path('/etc/xuanjun-binance/install-transaction.json'),b'{"synthetic":"B"}')
        self.ctx.b_transaction_sha=security.digest(b'{"synthetic":"B"}')
        os.symlink(ctl.B_RELEASE,self.ctx.path('/opt/xuanjun-binance/current'))
    def make_pin(self,**changes):
        name=artifact.PREFIX+'install_controller.py'
        a=dict(schema_version=1,decision='APPROVED_WITH_EXACT_PRECONDITIONS',host=auth.HOST,
               action=auth.INSTALL_ACTION,max_attempts=1,source_commit='c'*40,
               artifact_sha256=security.digest(self.raw),controller_sha256=security.digest((self.origin/name).read_bytes()),
               handoff_sha256=security.digest((self.origin/(artifact.PREFIX+'root_handoff.py')).read_bytes()),
               plan_sha256=security.digest(self.plan_path.read_bytes()),create_dedicated_worker_allowed=True,
               service_start_allowed=False,network_changes_allowed=False,credentials_allowed=False,
               database_export_allowed=False,writer_allowed=False,approval_comment_id=987654,
               issued_at=NOW-1,expires_at=NOW+3600)
        a.update(changes)
        body='SYNTHETIC TEST APPROVAL ONLY\n<!-- '+auth.MARKER+'\n'+json.dumps(a)+'\n'+auth.MARKER+' -->'
        return a,dict(approval_comment_id=a['approval_comment_id'],approval_body_sha256=security.digest(body.encode()),approval_body=body)
    def replace_pin(self,**changes):
        self.approval,self.pin=self.make_pin(**changes);self.pin_path.write_bytes(canonical_bytes(self.pin))
    def run_install(self):return ctl.install(self.install_archive,self.plan_path,self.ctx)
    def require_multiuid(self):
        p=self.ctx.path('/input/uid-probe');security.write_once(p,b'fixture')
        try:os.chown(p,1986,1986)
        except OSError as error:
            if error.errno==22:self.skipTest('UID1986 not mapped locally; hosted root required')
            raise
    def test_production_constants_retain_accepted_b_exact_hashes(self):
        self.assertEqual(ctl.Context.b_manifest_sha,'f887b085508e3ed4831dbed22152e35af5e8aba95b85b899b4697c61449917de')
        self.assertEqual(ctl.Context.b_unit_sha,'824fc0cbe3d879b61ea36b0bd7c45fb8c1e9fb6c463f46ada741ac3f2299899b')
        self.assertEqual(ctl.Context.b_transaction_sha,'ee81a70bb417e66dbb58bad5a79a776d1e7a0bce35d0e72bf638a2fe0844eb75')
    def test_no_root_or_wrong_host_cli_identity_rejected(self):
        with mock.patch.object(os,'geteuid',return_value=1986),self.assertRaises(GateError):ctl.Context().check_identity()
    def test_python_locale_coercion_accepted_but_injected_python_env_rejected(self):
        host=mock.Mock(nodename=auth.HOST)
        with mock.patch.object(os,'geteuid',return_value=0),mock.patch.object(os,'uname',return_value=host),\
             mock.patch.dict(os.environ,dict(ctl.ENV,LC_CTYPE='C.UTF-8'),clear=True):
            ctl.Context().check_identity()
            os.environ['PYTHONPATH']='/untrusted'
            with self.assertRaises(GateError):ctl.Context().check_identity()
    def test_production_loaded_source_check_from_actual_private_root_extraction(self):
        _,files=ctl.package_bytes(self.raw)
        extracted=self.ctx.path('/input/root-source');extracted.mkdir(mode=0o700)
        for name in artifact.RUNTIME_FILES:
            target=extracted/name;target.parent.mkdir(parents=True,exist_ok=True)
            security.write_once(target,files[name],mode=0o400)
        code="import sys;sys.path.insert(0,sys.argv[1]);from korea.phase_c.install_controller import Context,package_bytes;raw=open(sys.argv[2],'rb').read();Context().loaded_source(package_bytes(raw)[1]);print('ROOT_SOURCE_PASS')"
        def run():return subprocess.run([sys.executable,'-I','-B','-c',code,str(extracted/'migration-prep'),str(self.install_archive)],capture_output=True,text=True,timeout=15)
        result=run();self.assertEqual(result.returncode,0,result.stderr);self.assertIn('ROOT_SOURCE_PASS',result.stdout)
        (extracted/'migration-prep/korea/phase_c/network.py').chmod(0o666)
        result=run();self.assertNotEqual(result.returncode,0);self.assertNotIn('ROOT_SOURCE_PASS',result.stdout)
    def test_missing_private_pin_has_no_root_command_or_attempt(self):
        self.pin_path.unlink()
        with self.assertRaises(FileNotFoundError):self.run_install()
        self.assertEqual(self.ctx.calls,[]);self.assertFalse(self.ctx.path(ctl.WORK).exists())
    def test_edited_or_deleted_github_approval_does_not_consume_attempt(self):
        with mock.patch.object(self.ctx,'current_approval',return_value='revoked'),self.assertRaises(GateError):self.run_install()
        self.assertFalse(self.ctx.path(ctl.WORK).exists());self.assertEqual(self.ctx.calls,[])
        with mock.patch.object(self.ctx,'current_approval',side_effect=OSError('unavailable')),self.assertRaises(OSError):self.run_install()
        self.assertFalse(self.ctx.path(ctl.WORK).exists())
    def test_invalid_old_action_wrong_bytes_expiry_and_scope_fail_before_effect(self):
        changes=[dict(action='PR99_PHASE_B_OFFLINE_REPAIR_FINALIZE_V1'),dict(artifact_sha256='0'*64),
                 dict(controller_sha256='0'*64),dict(plan_sha256='0'*64),dict(source_commit='0'*40),
                 dict(service_start_allowed=True),dict(network_changes_allowed=True),dict(max_attempts=2),dict(expires_at=NOW)]
        for change in changes:
            self.replace_pin(**change)
            with self.subTest(change=change),self.assertRaises(GateError):self.run_install()
            self.assertEqual(self.ctx.calls,[]);self.assertFalse(self.ctx.path(ctl.WORK).exists())
    def test_private_pin_owner_mode_and_symlink_rejected(self):
        self.pin_path.chmod(0o644)
        with self.assertRaises(GateError):self.run_install()
        self.pin_path.chmod(0o600);moved=self.pin_path.with_suffix('.saved');self.pin_path.rename(moved)
        os.symlink(moved,self.pin_path)
        with self.assertRaises(OSError):self.run_install()
        self.assertEqual(self.ctx.calls,[])
    def test_frozen_b_actual_file_mutation_fails_before_attempt(self):
        p=self.ctx.path(ctl.B_RELEASE)/'migration-prep/f3.py';p.chmod(0o600);p.write_bytes(b'changed')
        with self.assertRaises(GateError):self.run_install()
        self.assertFalse(self.ctx.path(ctl.WORK).exists())
    def test_old_current_pointer_mutation_fails_before_attempt(self):
        p=self.ctx.path('/opt/xuanjun-binance/current');p.unlink();os.symlink('/other',p)
        with self.assertRaises(GateError):self.run_install()
        self.assertFalse(self.ctx.path(ctl.WORK).exists())
    def test_candidate_existing_in_manager_is_not_overwritten(self):
        self.ctx.preexisting=True
        with self.assertRaises(GateError):self.run_install()
        self.assertFalse(self.ctx.path(ctl.WORK).exists())
    def test_public_key_changed_after_plan_prevents_durable_claim(self):
        self.ctx.path('/etc/xuanjun-pr99-release/phase-c-public-inputs/source.pem').write_bytes(self.keys['broker'])
        with self.assertRaises(GateError):self.run_install()
        self.assertFalse(self.ctx.path(ctl.WORK).exists())
    def test_interruption_after_claim_preserves_attempt_lock_and_old_files(self):
        before=ctl.frozen_b(self.ctx);self.ctx.fail_at='after_claim'
        with self.assertRaises(RuntimeError):self.run_install()
        receipt=json.loads((self.ctx.path(ctl.WORK)/'receipt.json').read_text())
        self.assertEqual(receipt['status'],'HOLD_PRESERVE_EVIDENCE')
        self.assertEqual(ctl.frozen_b(self.ctx),before);self.assertTrue(self.ctx.path(ctl.LOCK).exists())
        with self.assertRaises(GateError):self.run_install()
    def test_authorization_expiring_before_changes_stops(self):
        self.ctx.clock_callback=lambda step:setattr(self.ctx,'time',NOW+3601) if step=='after_claim' else None
        with self.assertRaises(GateError):self.run_install()
        self.assertFalse(self.ctx.created)
    def test_new_runtime_partial_failure_preserved_without_reload(self):
        self.ctx.fail_at='after_runtime'
        with self.assertRaises(RuntimeError):self.run_install()
        self.assertTrue(self.ctx.path(self.plan['render_values']['C_RELEASE']).is_dir())
        self.assertNotIn(('/usr/bin/systemctl','daemon-reload'),self.ctx.calls)
        self.assertTrue(self.ctx.path(ctl.LOCK).is_dir())
    def test_install_success_old_b_shared_unchanged_new_units_stopped_no_live_admission(self):
        self.require_multiuid();before=ctl.frozen_b(self.ctx);shared=self.ctx.units(ctl.SHARED)
        result=self.run_install()
        self.assertEqual(result['status'],'C_OFFLINE_CANDIDATE_INSTALLED_NOT_STARTED')
        self.assertEqual(ctl.frozen_b(self.ctx),before);self.assertEqual(self.ctx.units(ctl.SHARED),shared)
        self.assertFalse(self.ctx.path(ctl.LOCK).exists())
        self.assertFalse(self.ctx.path(self.plan['runtime_config']['admission_path']).exists())
        self.assertEqual(self.ctx.calls.count(('/usr/bin/systemctl','daemon-reload')),1)
        self.assertFalse(any('start' in c or 'enable' in c or 'nft' in c for c in self.ctx.calls if isinstance(c,tuple)))
        self.assertFalse(json.loads(self.ctx.path('/etc/xuanjun-binance-phase-c/acceptance.json').read_text())['owner_approved'])
        with self.assertRaises(GateError):self.run_install()
    def test_reload_failure_preserves_no_public_success(self):
        self.require_multiuid();self.ctx.reload_exit=1
        with self.assertRaises(GateError):self.run_install()
        self.assertFalse(self.ctx.path(ctl.PUBLIC).exists());self.assertTrue(self.ctx.path(ctl.LOCK).exists())
    def test_shared_change_is_hold_not_success(self):
        self.require_multiuid();self.ctx.mutate_shared=True
        with self.assertRaises(GateError):self.run_install()
        self.assertFalse(self.ctx.path(ctl.PUBLIC).exists())
    def test_lock_drift_is_hold_not_success(self):
        self.require_multiuid()
        def drift(name):
            if name=='before_unlock':
                p=self.ctx.path(ctl.LOCK);p.rename(p.with_name(p.name+'.retained'));p.mkdir(mode=0o700)
        self.ctx.clock_callback=drift
        with self.assertRaises(GateError):self.run_install()
        self.assertFalse(self.ctx.path(ctl.PUBLIC).exists())
    def test_empty_existing_destination_cannot_be_overwritten(self):
        p=self.ctx.path('/etc/xuanjun-binance-phase-c');p.mkdir()
        with self.assertRaises(GateError):self.run_install()
        self.assertEqual(list(p.iterdir()),[])
    def test_plan_rejects_activated_window_shared_paths_and_identity_reuse(self):
        _,files=ctl.package_bytes(self.raw)
        for change in ('window','path','identity'):
            plan=copy.deepcopy(self.plan)
            if change=='window':plan['acceptance_config']['owner_approved']=True
            elif change=='path':plan['runtime_config']['evidence_root']='/var/lib/shared'
            else:plan['runtime_config']['authority_public_key_sha256']=plan['runtime_config']['source_public_key_sha256']
            with self.subTest(change=change),self.assertRaises(GateError):ctl.validate_plan(plan,files,NOW)
    def test_c_archive_tamper_rejected(self):
        import tarfile
        with self.assertRaises((EOFError,tarfile.ReadError)):ctl.package_bytes(self.raw[:100])

    def test_typed_manager_profiles_systemd239_order_and_false_allowlist(self):
        ctx=ctl.Context()
        def run(args):
            if args[-1]=='PrivateNetwork':
                output='b true' if 'worker' in args[3] else 'b false'
            else:output='(bas) true 1 "AF_UNIX"' if 'worker' in args[3] else '(bas) true 3 "AF_INET6" "AF_INET" "AF_UNIX"'
            return subprocess.CompletedProcess(args,0,output,'')
        with mock.patch.object(ctx,'run',side_effect=run):ctx.verify_manager_profiles()
        with mock.patch.object(ctx,'run',return_value=subprocess.CompletedProcess([],0,'(bas) false 1 "AF_UNIX"','')):
            with self.assertRaises(GateError):ctx.verify_manager_profiles()
    def test_concurrent_install_only_one_permanent_attempt_claim(self):
        self.ctx.fail_at='after_claim';outcomes=[]
        def run():
            try:self.run_install();outcomes.append('unexpected-success')
            except (GateError,OSError,RuntimeError):outcomes.append('hold')
        threads=[threading.Thread(target=run) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join(timeout=20)
        self.assertTrue(all(not t.is_alive() for t in threads));self.assertEqual(outcomes,['hold','hold'])
        self.assertEqual(len(list(self.ctx.path('/var/lib').glob('xuanjun-pr99-phase-c-install-v1'))),1)
        self.assertEqual(json.loads((self.ctx.path(ctl.WORK)/'receipt.json').read_text())['phase'],'claim')


if __name__=='__main__':unittest.main()
