"""Disposable root filesystem integration; host service/Nginx/HTTPS are fakes."""
import copy
import json
import os
from pathlib import Path
import shutil
import time
import unittest
from types import SimpleNamespace
from unittest import mock
from tests.test_pr122_site_hub_combined import CombinedTests, synthetic_source_fixture
from scripts import pr122_site_hub_experience_release as r

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'evidence/pr122-site-hub-experience/PR122_SITE_HUB_REVIEW_ONLY.tar.gz'
if not PACKAGE.exists():PACKAGE=Path('/tmp/pr122-experience-release-2ecee38d/PR122_SITE_HUB_REVIEW_ONLY.tar.gz')

@unittest.skipUnless(os.geteuid()==0,'Disposable root filesystem required')
class ExperienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        CombinedTests.setUpClass()
        cls.ui_pins=json.loads((ROOT/'deploy/pr122-site-hub-experience/HOST_PINS.json').read_text())
        cls.ui_package=PACKAGE
        if not (ROOT/'source/PR122_TOKYO_WEBROOT_MIGRATION_SOURCE_0363531ee2f8.tar.gz').exists() or os.environ.get('XJ_COMBINED_SYNTHETIC_FIXTURE')=='1':
            data=r.entries(PACKAGE.read_bytes(),cls.ui_pins)
            ui_fixture=CombinedTests.fixture/'ui';ui_fixture.mkdir()
            cls.ui_package,source,cls.ui_pins,data=synthetic_source_fixture(data,cls.ui_pins,ui_fixture)
            cls.ui_pins['candidate_manifest_sha256']=r.digest(data['candidate-manifest.json'])
            print('UI_RELEASE_TEST_SOURCE=SYNTHETIC_1187_PLUS_92; NOT_PRODUCTION_HTTPS')
    @classmethod
    def tearDownClass(cls):CombinedTests.tearDownClass()
    def setUp(self):
        old=CombinedTests('test_complete_1277_file_publish_and_restore')
        old.setUp();self.addCleanup(old.doCleanups);old.apply();self.old=old
        # Share the explicitly patched dependency namespace, never a CLI override.
        from scripts import pr122_site_hub_combined as original_helper
        c=r.c
        for name in ('BASE','CONTROL','RUNTIME','UNIT','ENABLE','HTTPS','LIMIT','LOCATIONS','INSTALLED_PUBLISHER','HERE','PINS_PATH','PREFLIGHT_PATH'):
            patch=mock.patch.object(c,name,getattr(original_helper,name));patch.start();self.addCleanup(patch.stop)
        self.c=c;self.inputs=old.temp/'ui-inputs';self.inputs.mkdir(mode=0o700)
        shutil.copyfile(self.ui_package,self.inputs/'PR122_SITE_HUB_REVIEW_ONLY.tar.gz')
        shutil.copyfile(old.source,self.inputs/old.source.name)
        pins=copy.deepcopy(self.ui_pins)
        pins['previous_release']=os.readlink(c.BASE/'current')
        oldmanifest=(old.tx.folder/'bundle/candidate-manifest.json').read_bytes()
        (self.inputs/'R2_CANDIDATE_MANIFEST.json').write_bytes(oldmanifest)
        pins['previous_manifest_sha256']=r.digest(oldmanifest)
        receipt=c.CONTROL/'transactions/pr122-hub-icp-20261016-r2';receipt.mkdir(mode=0o700)
        (receipt/'receipt.json').write_bytes(c.canonical(old.tx.data))
        pins['previous_receipt_sha256']=r.digest((receipt/'receipt.json').read_bytes())
        oldcsp=str(Path(old.pins['previous_release'])/'release-metadata/inline-csp.conf')
        names=set(old.pins['nginx'])-{oldcsp}
        names.update((str(c.LIMIT),str(c.LOCATIONS),str(Path(pins['previous_release'])/'release-metadata/inline-csp.conf')))
        pins['nginx']={p:r.digest(Path(p).read_bytes()) for p in names}
        pinpath=old.temp/'code/ui-pins.json';pinpath.write_bytes(c.canonical(pins))
        code=old.temp/'code/ui-wrapper.py';code.write_bytes((ROOT/'scripts/pr122_site_hub_experience_release.py').read_bytes())
        for name,value in [('PINS',pinpath),('HERE',code)]:
            patch=mock.patch.object(r,name,value);patch.start();self.addCleanup(patch.stop)
        original=c.load_module
        def loader(path,name):
            if path==c.PREFLIGHT_PATH:
                def inventory():
                    current=os.readlink(c.BASE/'current')
                    paths=set(pins['nginx'])-{str(Path(pins['previous_release'])/'release-metadata/inline-csp.conf')}
                    paths.add(str(Path(current)/'release-metadata/inline-csp.conf'))
                    return {'status':'SOURCE_INVENTORY_COMPLETE','disk_config_trust':True,'files':{p:{'sha256':r.digest(Path(p).read_bytes())} for p in paths}}
                return SimpleNamespace(nginx_source=inventory)
            pub=original(path,name)
            if name=='pr122_combined_frozen_publisher':pub.APPROVED_BASE=c.BASE
            return pub
        patch=mock.patch.object(c,'load_module',side_effect=loader);patch.start();self.addCleanup(patch.stop)
        self.pins=pins;self.tx=r.Transaction(self.inputs,old.ops,pins)
        self.gate={'decision':'RELEASE_APPROVED','operation':'PR122_STATIC_EXPERIENCE','transaction_id':pins['transaction_id'],'source_head':pins['source_head'],
                   'wrapper_sha256':r.digest(code.read_bytes()),'host_pins_sha256':r.digest(pinpath.read_bytes()),'static_artifact_sha256':pins['static_artifact_sha256'],
                   'package_manifest_sha256':pins['package_manifest_sha256'],'previous_receipt_sha256':pins['previous_receipt_sha256'],
                   'rollback_approved':True,'max_executions':1,'independent_review':'PASS','reviewer_role':'INDEPENDENT_AUDITOR',
                   'review_comment_id':9999999999,'release_comment_id':9999999998,'issued_unix':int(time.time())-1,'expires_unix':int(time.time())+600}
        self.approval=old.temp/'ui-approval.json';self.approval.write_bytes(c.canonical(self.gate));self.approval.chmod(0o600)
        self.runtime_before={p:r.digest(p.read_bytes()) for p in (c.RUNTIME/c.RELEASE/'scripts').iterdir()}
        self.unit_before=c.UNIT.read_bytes();self.oldcalls=len(old.ops.calls)
    def assert_runtime_preserved(self):
        self.assertTrue(self.old.ops.active);self.assertEqual(self.c.UNIT.read_bytes(),self.unit_before)
        self.assertEqual({p:r.digest(p.read_bytes()) for p in (self.c.RUNTIME/self.c.RELEASE/'scripts').iterdir()},self.runtime_before)
        self.assertFalse(set(self.old.ops.calls[self.oldcalls:])&{'start','stop','manager-reload','unit-verify','vacant'})
    def test_complete_static_update_and_rollback(self):
        result=self.tx.apply(self.approval);self.assertEqual(result['state'],'HTTPS_SMOKE_PASS_AWAIT_BROWSER')
        self.assertEqual(len([p for p in (self.c.BASE/'current/public').rglob('*') if p.is_file()]),1279)
        self.assert_runtime_preserved();self.assertEqual(self.tx.rollback()['state'],'ROLLED_BACK');self.assert_runtime_preserved()
        self.assertEqual(os.readlink(self.c.BASE/'current'),self.pins['previous_release'])
    def test_reject_old_gate_without_changes(self):
        self.gate['operation']='PR122_COMBINED_WEBSITE';self.approval.write_bytes(self.c.canonical(self.gate))
        with self.assertRaisesRegex(RuntimeError,'RELEASE_GATE'):self.tx.apply(self.approval)
        self.assertFalse(self.tx.folder.exists());self.assert_runtime_preserved()
    def test_reject_public_drift(self):
        (Path(self.pins['previous_release'])/'public/index.html').write_text('drift')
        with self.assertRaisesRegex(RuntimeError,'R2_PUBLIC_DRIFT'):self.tx.apply(self.approval)
        self.assertFalse(self.tx.folder.exists())
    def test_no_apply_retry(self):
        self.tx.apply(self.approval)
        with self.assertRaisesRegex(RuntimeError,'TRANSACTION_ALREADY_EXISTS'):self.tx.apply(self.approval)
    def test_refuse_foreign_config_rollback(self):
        self.tx.apply(self.approval);self.c.LOCATIONS.write_text('foreign')
        with self.assertRaisesRegex(RuntimeError,'FOREIGN_NGINX_CONFIG'):self.tx.rollback()
        self.assert_runtime_preserved()
    def test_fault_after_every_completed_phase(self):
        # A fresh disposable transaction for each parameter, real prepare/activate.
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
                self.assertEqual(self.tx.data['state'],'HOLD_PARTIAL')
                self.assertEqual(self.tx.rollback()['state'],'ROLLED_BACK');self.assert_runtime_preserved()

if __name__=='__main__':unittest.main()
