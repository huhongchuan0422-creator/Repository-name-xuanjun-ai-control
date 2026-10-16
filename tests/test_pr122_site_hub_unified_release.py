"""Real disposable filesystem/publisher; fake host services. Not production evidence."""
import copy,json,os,shutil,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from tests import test_pr122_site_hub_experience_release as prior
from tests.test_pr122_site_hub_combined import synthetic_source_fixture
from scripts import pr122_site_hub_unified_release as r
from scripts import pr122_site_hub_unified_package as package
from scripts import pr122_community_experience_package as mobile

ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(os.geteuid()==0,'Disposable root filesystem required')
class UnifiedTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prior.ExperienceTests.setUpClass()
        cls.folder=Path(tempfile.mkdtemp(prefix='pr122-unified-input-',dir='/root'))
        cls.realpins=json.loads(r.PINS.read_bytes())
        with mock.patch.dict(os.environ,{'GITHUB_SHA':'790937a5c96afcf3b3660e36cf36cfaab2002a72'}):mobile.build(cls.folder/'mobile')
        package.build(ROOT/'evidence/pr122-public-presentation/PR122_PUBLIC_PRESENTATION_REVIEW_ONLY.tar.gz',cls.folder/'mobile/COMMUNITY_EXPERIENCE_REVIEW_ONLY.tar.gz',cls.folder/'candidate')
        cls.bundle=cls.folder/'candidate/PR122_UNIFIED_REVIEW_ONLY.tar.gz'
        if os.environ.get('XJ_COMBINED_SYNTHETIC_FIXTURE')=='1' or not (ROOT/'source/PR122_TOKYO_WEBROOT_MIGRATION_SOURCE_0363531ee2f8.tar.gz').exists():
            data=r.entries(cls.bundle.read_bytes(),cls.realpins);folder=cls.folder/'synthetic';folder.mkdir()
            cls.bundle,_,cls.realpins,data=synthetic_source_fixture(data,cls.realpins,folder)
            cls.realpins['candidate_manifest_sha256']=r.digest(data['candidate-manifest.json'])
            print('UNIFIED_TEST_SOURCE=SYNTHETIC_1187_PLUS_101; NO_REAL_HOST_SERVICES')
    @classmethod
    def tearDownClass(cls):shutil.rmtree(cls.folder);prior.ExperienceTests.tearDownClass()
    def setUp(self):
        old=prior.ExperienceTests('test_complete_static_update_and_rollback');old.setUp();self.addCleanup(old.doCleanups);old.tx.apply(old.approval)
        self.old=old;self.ops=old.old.ops;self.temp=old.old.temp;c=r.c
        for name in ('BASE','CONTROL','RUNTIME','UNIT','ENABLE','HTTPS','LIMIT','LOCATIONS','INSTALLED_PUBLISHER','HERE','PINS_PATH','PREFLIGHT_PATH'):
            patch=mock.patch.object(c,name,getattr(old.c,name));patch.start();self.addCleanup(patch.stop)
        self.c=c;self.inputs=self.temp/'unified-inputs';self.inputs.mkdir(mode=0o700)
        shutil.copyfile(self.bundle,self.inputs/'PR122_SITE_HUB_REVIEW_ONLY.tar.gz')
        shutil.copyfile(old.old.source,self.inputs/old.old.source.name)
        pins=copy.deepcopy(self.realpins);pins['previous_release']=os.readlink(c.BASE/'current')
        baseline=(old.tx.folder/'bundle/candidate-manifest.json').read_bytes()
        (self.inputs/'R2_CANDIDATE_MANIFEST.json').write_bytes(baseline);pins['previous_manifest_sha256']=r.digest(baseline)
        pins['previous_receipt_sha256']=r.digest(old.tx.receipt.read_bytes())
        oldcsp=str(Path(old.pins['previous_release'])/'release-metadata/inline-csp.conf')
        names=set(old.pins['nginx'])-{oldcsp};names.add(str(Path(pins['previous_release'])/'release-metadata/inline-csp.conf'))
        pins['nginx']={p:r.digest(Path(p).read_bytes()) for p in names}
        code=self.temp/'code/unified-wrapper.py';code.write_bytes((ROOT/'scripts/pr122_site_hub_unified_release.py').read_bytes())
        pp=self.temp/'code/unified-pins.json';pp.write_bytes(c.canonical(pins))
        for name,value in [('HERE',code),('PINS',pp)]:
            patch=mock.patch.object(r,name,value);patch.start();self.addCleanup(patch.stop)
        original=old.c.load_module
        def loader(path,name):
            if path==c.PREFLIGHT_PATH:
                def inventory():
                    current=os.readlink(c.BASE/'current')
                    names=set(pins['nginx'])-{str(Path(pins['previous_release'])/'release-metadata/inline-csp.conf')}
                    names.add(str(Path(current)/'release-metadata/inline-csp.conf'))
                    return {'status':'SOURCE_INVENTORY_COMPLETE','disk_config_trust':True,'files':{p:{'sha256':r.digest(Path(p).read_bytes())} for p in names}}
                return SimpleNamespace(nginx_source=inventory)
            return original(path,name)
        patch=mock.patch.object(c,'load_module',side_effect=loader);patch.start();self.addCleanup(patch.stop)
        self.pins=pins;self.tx=r.Transaction(self.inputs,self.ops,pins)
        self.gate={**old.gate,'operation':'PR122_PUBLIC_MOBILE_UNIFIED','transaction_id':pins['transaction_id'],'source_head':pins['source_head'],'wrapper_sha256':r.digest(code.read_bytes()),'host_pins_sha256':r.digest(pp.read_bytes()),'static_artifact_sha256':pins['static_artifact_sha256'],'package_manifest_sha256':pins['package_manifest_sha256'],'previous_receipt_sha256':pins['previous_receipt_sha256'],'issued_unix':int(time.time())-1,'expires_unix':int(time.time())+600}
        self.approval=self.temp/'unified-approval.json';self.approval.write_bytes(c.canonical(self.gate));self.approval.chmod(0o600)
        self.runtime_before={p:r.digest(p.read_bytes()) for p in (c.RUNTIME/c.RELEASE/'scripts').iterdir()};self.unit_before=c.UNIT.read_bytes();self.calls=len(self.ops.calls)
    def preserved(self):
        self.assertEqual(self.c.UNIT.read_bytes(),self.unit_before)
        self.assertEqual({p:r.digest(p.read_bytes()) for p in (self.c.RUNTIME/self.c.RELEASE/'scripts').iterdir()},self.runtime_before)
        self.assertFalse(set(self.ops.calls[self.calls:])&{'start','stop','manager-reload','unit-verify','vacant'})
    def test_full_1288_publish_and_1279_restore(self):
        self.assertEqual(self.tx.apply(self.approval)['state'],'HTTPS_SMOKE_PASS_AWAIT_BROWSER')
        self.assertEqual(sum(p.is_file() for p in (self.c.BASE/'current/public').rglob('*')),1288)
        self.preserved();self.assertEqual(self.tx.rollback()['state'],'ROLLED_BACK');self.preserved()
        self.assertEqual(sum(p.is_file() for p in (self.c.BASE/'current/public').rglob('*')),1279)
    def test_consumed_old_scope_rejected(self):
        self.gate['operation']='PR122_STATIC_EXPERIENCE';self.approval.write_bytes(self.c.canonical(self.gate))
        with self.assertRaisesRegex(RuntimeError,'RELEASE_GATE'):self.tx.apply(self.approval)
        self.assertFalse(self.tx.folder.exists())
    def test_current_baseline_drift_rejected(self):
        (Path(self.pins['previous_release'])/'public/index.html').write_text('drift')
        with self.assertRaisesRegex(RuntimeError,'R2_PUBLIC_DRIFT'):self.tx.apply(self.approval)
        self.assertFalse(self.tx.folder.exists())
    def test_no_retry_and_foreign_config_rollback_refused(self):
        self.tx.apply(self.approval)
        with self.assertRaisesRegex(RuntimeError,'TRANSACTION_ALREADY_EXISTS'):self.tx.apply(self.approval)
        self.c.LOCATIONS.write_text('foreign')
        with self.assertRaisesRegex(RuntimeError,'FOREIGN_NGINX_CONFIG'):self.tx.rollback()
        self.preserved()
    def test_expired_gate_rejected(self):
        self.gate.update(issued_unix=1,expires_unix=2);self.approval.write_bytes(self.c.canonical(self.gate))
        with self.assertRaisesRegex(RuntimeError,'GATE_EXPIRED'):self.tx.apply(self.approval)
        self.assertFalse(self.tx.folder.exists())
    def test_failure_after_all_ten_phases_restores_previous_site(self):
        phases=['BACKUP_VERIFIED','SEALED_BUNDLE','STATIC_PREPARED','NGINX_STAGED','NGINX_VALIDATED','ACTIVATION_DRIFT_CHECK','STATIC_ACTIVATED','NGINX_RELOADED','HTTPS_SMOKE','STATIC_CHECK']
        for phase in phases:
            with self.subTest(phase=phase):
                if phase!=phases[0]:self.doCleanups();self.setUp()
                step=self.tx.step
                def fail(name,action):
                    result=step(name,action)
                    if name==phase:raise RuntimeError('INJECTED_FAILURE')
                    return result
                with mock.patch.object(self.tx,'step',side_effect=fail):
                    with self.assertRaisesRegex(RuntimeError,'INJECTED_FAILURE'):self.tx.apply(self.approval)
                self.assertEqual(self.tx.data['state'],'HOLD_PARTIAL');self.assertEqual(self.tx.rollback()['state'],'ROLLED_BACK');self.preserved()
