"""Actual filesystem/publisher tests; host systemd/Nginx effects use explicit fakes."""
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import time
import unittest
from unittest import mock
from types import SimpleNamespace
from scripts import pr122_site_hub_combined as c

ROOT=Path(__file__).resolve().parents[1]

class FakeOps:
    def __init__(self):self.active=False;self.calls=[]
    def unit(self):return {'LoadState':'loaded' if c.UNIT.exists() else 'not-found','ActiveState':'active' if self.active else 'inactive','FragmentPath':str(c.UNIT) if c.UNIT.exists() else ''}
    def vacant(self):self.calls.append('vacant')
    def nginx_test(self):self.calls.append('nginx-test')
    def nginx_identity(self):return {'scope':'FAKE_HOST_PROCESS'}
    def verify_unit(self):self.calls.append('unit-verify')
    def reload_manager(self):self.calls.append('manager-reload')
    def start(self):self.active=True;self.calls.append('start')
    def stop(self):self.active=False;self.calls.append('stop')
    def reload_nginx(self):self.calls.append('nginx-reload')
    def sandbox(self):return {'scope':'FAKE_HOST_ONLY_NOT_REAL_SANDBOX'}
    def preview_probe(self):return {'scope':'FAKE_HOST_ONLY_NOT_REAL_HTTP'}
    def smoke(self,*args):return {'scope':'FAKE_HOST_ONLY_NOT_REAL_HTTPS'}

def synthetic_source_fixture(entries,pins,folder):
    """Hosted-only fallback: same 1187+90 shape; never substitutes production pins."""
    entries=dict(entries);pins=copy.deepcopy(pins)
    pin=json.loads(entries['source-pin.json']);manifest=json.loads(entries['candidate-manifest.json'])
    new={p for p,v in pin['overlay_baselines'].items() if v is None}
    originals={r['path']:('synthetic-old:'+r['path']+'\n').encode() for r in manifest['files'] if r['path'] not in new}
    def archive_bytes(data,prefix):
        stream=io.BytesIO()
        with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as zipped,tarfile.open(fileobj=zipped,mode='w') as archive:
            for name,raw in sorted(data.items()):
                m=tarfile.TarInfo(prefix+name);m.size=len(raw);m.mode=0o644;archive.addfile(m,io.BytesIO(raw))
        return stream.getvalue()
    source=archive_bytes(originals,'package/public/')
    path=folder/'PR122_TOKYO_WEBROOT_MIGRATION_SOURCE_0363531ee2f8.tar.gz';path.write_bytes(source)
    pin.update(source_archive_sha256=c.sha(source),source_archive_size=len(source))
    for name,value in pin['overlay_baselines'].items():
        if value is not None:pin['overlay_baselines'][name]=c.sha(originals[name])
    entries['source-pin.json']=c.canonical(pin)
    for row in manifest['files']:
        name=row['path'];raw=entries.get('overlay/public/'+name,originals.get(name))
        row.update(size=len(raw),sha256=c.sha(raw))
    entries['candidate-manifest.json']=c.canonical(manifest)
    pm={'schema_version':2,'files':[{'path':name,'size':len(raw),'sha256':c.sha(raw)} for name,raw in sorted(entries.items()) if name!='PACKAGE_MANIFEST.json']}
    entries['PACKAGE_MANIFEST.json']=c.canonical(pm)
    frozen=archive_bytes(entries,'pr122-site-hub/');fp=folder/'fixture-review.tar.gz';fp.write_bytes(frozen)
    pins.update(source_archive_sha256=c.sha(source),static_artifact_sha256=c.sha(frozen),package_manifest_sha256=c.sha(entries['PACKAGE_MANIFEST.json']))
    return fp,path,pins,entries

@unittest.skipUnless(os.geteuid()==0,'Filesystem/publisher integration requires disposable root test environment')
class CombinedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen=ROOT/'evidence/pr122-site-hub/PR122_SITE_HUB_REVIEW_ONLY.tar.gz'
        if not cls.frozen.exists():cls.frozen=ROOT/'review-package-preview-final/PR122_SITE_HUB_REVIEW_ONLY.tar.gz'
        cls.source=ROOT/'source/PR122_TOKYO_WEBROOT_MIGRATION_SOURCE_0363531ee2f8.tar.gz'
        cls.realpins=json.loads((ROOT/'deploy/pr122-site-hub-combined/HOST_PINS.json').read_text())
        cls.entries=c.verified_entries(cls.frozen.read_bytes(),cls.realpins)
        cls.fixture=Path(tempfile.mkdtemp(prefix='pr122-combined-input-',dir='/root'))
        if not cls.source.exists() or os.environ.get('XJ_COMBINED_SYNTHETIC_FIXTURE')=='1':
            cls.frozen,cls.source,cls.realpins,cls.entries=synthetic_source_fixture(cls.entries,cls.realpins,cls.fixture)
            print('COMBINED_TEST_SOURCE=SYNTHETIC_1187_PLUS_90; SYSTEMD_NGINX=FAKE')
        else:print('COMBINED_TEST_SOURCE=ACTUAL_APPROVED_ARCHIVE_1187_PLUS_90; SYSTEMD_NGINX=FAKE')
        cls.seed=Path(tempfile.mkdtemp(prefix='pr122-combined-seed-',dir='/root'))
        with tarfile.open(cls.source) as archive:
            for m in archive.getmembers():
                if m.isfile() and m.name.startswith('package/public/'):
                    p=cls.seed/m.name.removeprefix('package/public/');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(archive.extractfile(m).read())
        (cls.seed/'assets/tiktok-integration.js').write_bytes(cls.entries['overlay/public/assets/tiktok-integration.js'])
    @classmethod
    def tearDownClass(cls):shutil.rmtree(cls.seed);shutil.rmtree(cls.fixture)
    def setUp(self):
        self.temp=Path(tempfile.mkdtemp(prefix='pr122-combined-case-',dir='/root'));self.addCleanup(shutil.rmtree,self.temp)
        for name in ('web','control','inputs','nginx','systemd','code','installed'):(self.temp/name).mkdir(mode=0o700 if name in ('control','inputs') else 0o755)
        base=self.temp/'web';(base/'releases').mkdir();(base/'transactions').mkdir(mode=0o700)
        old=base/'releases/old';old.mkdir();shutil.copytree(self.seed,old/'public');os.chmod(old/'public',0o755);(old/'release-metadata').mkdir()
        (old/'release-metadata/inline-csp.conf').write_text('add_header Content-Security-Policy "default-src self" always;\n')
        (old/'release-metadata/inline-csp.json').write_text('{"policy":"default-src self"}\n')
        os.symlink(str(old),base/'current')
        installed=self.temp/'installed/publisher.py';installed.write_bytes((ROOT/'scripts/pr122_website_release.py').read_bytes())
        https=self.temp/'nginx/apex.conf';https.write_bytes(b'server {\n    '+c.ANCHOR+b'\n}\n')
        static=self.temp/'nginx/static.conf';static.write_bytes(b'old-static-security\n')
        pins=copy.deepcopy(self.realpins);pins['previous_release']=str(old)
        files={p.relative_to(old/'public').as_posix():{'size':p.stat().st_size,'sha256':c.sha(p.read_bytes())} for p in sorted((old/'public').rglob('*')) if p.is_file()}
        self.assertEqual(len(files),1187)
        pins['live_digest']=c.sha(json.dumps(files,sort_keys=True,separators=(',',':')).encode())
        pins['nginx']={str(p):c.sha(p.read_bytes()) for p in (https,static,old/'release-metadata/inline-csp.conf')}
        (self.temp/'systemd/multi-user.target.wants').mkdir()
        code=self.temp/'code/wrapper.py';code.write_bytes((ROOT/'scripts/pr122_site_hub_combined.py').read_bytes())
        pp=self.temp/'code/PINS.json';pp.write_bytes(c.canonical(pins))
        pf=self.temp/'code/preflight.py';pf.write_bytes((ROOT/'scripts/pr122_site_hub_host_preflight.py').read_bytes())
        shutil.copyfile(self.frozen,self.temp/'inputs/PR122_SITE_HUB_REVIEW_ONLY.tar.gz')
        shutil.copyfile(self.source,self.temp/'inputs'/self.source.name)
        self.patches=[]
        for name,value in {'BASE':base,'CONTROL':self.temp/'control','RUNTIME':self.temp/'runtime','UNIT':self.temp/'systemd'/c.SERVICE,
            'ENABLE':self.temp/'systemd/multi-user.target.wants'/c.SERVICE,'HTTPS':https,'LIMIT':self.temp/'nginx/limit.conf',
            'LOCATIONS':self.temp/'nginx/hub/locations.conf','INSTALLED_PUBLISHER':installed,'HERE':code,'PINS_PATH':pp,'PREFLIGHT_PATH':pf}.items():
            patch=mock.patch.object(c,name,value);patch.start();self.addCleanup(patch.stop)
        (c.CONTROL/'transactions').mkdir(mode=0o700)
        self.pins=pins;self.ops=FakeOps();self.tx=c.Transaction(self.temp/'inputs','test-transaction',self.ops,pins)
        original_loader=c.load_module
        def loader(path,name):
            if path==c.PREFLIGHT_PATH:
                def inventory():
                    names=list(pins['nginx'])
                    if c.LIMIT.exists():names.extend([str(c.LIMIT),str(c.LOCATIONS)])
                    return {'status':'SOURCE_INVENTORY_COMPLETE','disk_config_trust':True,'new_location_conflict':False,'new_zone_conflict':False,
                            'files':{p:{'sha256':c.sha(Path(p).read_bytes())} for p in names}}
                return SimpleNamespace(nginx_source=inventory)
            pub=original_loader(path,name)
            # Test-only injected module constant; production CLI has no path override.
            if name=='pr122_combined_frozen_publisher':pub.APPROVED_BASE=c.BASE
            return pub
        patch=mock.patch.object(c,'load_module',side_effect=loader);patch.start();self.addCleanup(patch.stop)
        self.gate={'decision':'RELEASE_APPROVED','operation':'PR122_COMBINED_WEBSITE','transaction_id':self.tx.id,
                   'source_head':pins['source_head'],'wrapper_sha256':c.sha(c.HERE.read_bytes()),'host_pins_sha256':c.sha(c.PINS_PATH.read_bytes()),
                   'static_artifact_sha256':pins['static_artifact_sha256'],'package_manifest_sha256':pins['package_manifest_sha256'],
                   'independent_review':'PASS','reviewer_role':'INDEPENDENT_AUDITOR','review_comment_id':9999999999,'release_comment_id':9999999998,
                   'issued_unix':int(time.time())-1,'expires_unix':int(time.time())+600}
        self.gatepath=self.temp/'approval.json';self.gatepath.write_bytes(c.canonical(self.gate));os.chmod(self.gatepath,0o600)
    def apply(self):return self.tx.apply(self.gatepath)
    def test_complete_1277_file_publish_and_restore(self):
        r=self.apply();self.assertEqual(r['state'],'HTTPS_SMOKE_PASS_AWAIT_BROWSER')
        self.assertEqual(len(list((c.BASE/'current/public').rglob('*')))>1277,True)
        self.assertTrue(self.ops.active);self.assertTrue(c.ENABLE.is_symlink())
        self.assertEqual(self.tx.rollback()['state'],'ROLLED_BACK')
        self.assertEqual(os.readlink(c.BASE/'current'),self.pins['previous_release']);self.assertFalse(self.ops.active)
        self.assertFalse(c.UNIT.exists());self.assertFalse(c.LIMIT.exists());self.assertFalse(c.LOCATIONS.exists())
    def test_no_release_gate_no_production_effect(self):
        for key,value in [('decision','HOLD'),('expires_unix',0),('wrapper_sha256','0'*64),('review_comment_id',6207779869),('transaction_id','other')]:
            with self.subTest(key=key):
                gate={**self.gate,key:value};self.gatepath.write_bytes(c.canonical(gate))
                with self.assertRaises(c.Hold):self.apply()
                self.assertFalse(self.tx.receipt.exists());self.assertFalse(c.RUNTIME.exists());self.assertEqual(self.ops.calls,[])
    def test_config_or_live_drift_rejected_before_intent(self):
        c.HTTPS.write_bytes(b'drift')
        with self.assertRaisesRegex(c.Hold,'NGINX_INCLUDE_SET_OR_HASH_DRIFT'):self.apply()
        self.assertFalse(self.tx.receipt.exists())
    def test_unknown_current_never_overwritten(self):
        self.apply();(c.BASE/'current').unlink();os.symlink('/unknown',c.BASE/'current')
        with self.assertRaisesRegex(c.Hold,'CURRENT_UNKNOWN'):self.tx.rollback()
        self.assertEqual(os.readlink(c.BASE/'current'),'/unknown');self.assertTrue(self.ops.active)
    def test_rollback_refuses_foreign_config(self):
        self.apply();c.LIMIT.write_bytes(b'foreign-admin-change')
        with self.assertRaisesRegex(c.Hold,'RECOVERY_CONFIG_IDENTITY_UNKNOWN'):self.tx.rollback()
        self.assertEqual(c.LIMIT.read_bytes(),b'foreign-admin-change');self.assertTrue(self.ops.active)
    def test_expired_approval_does_not_block_recovery(self):
        self.apply();self.gatepath.unlink()
        self.assertEqual(self.tx.rollback()['state'],'ROLLED_BACK')
    def test_apply_is_not_blindly_retried(self):
        self.apply();starts=self.ops.calls.count('start')
        with self.assertRaises(c.Hold):self.apply()
        self.assertEqual(self.ops.calls.count('start'),starts)
    def test_simulated_post_action_interruptions_restore_only_own_objects(self):
        stages=['STATIC_PREPARED','RUNTIME_INSTALLED','RUNTIME_STARTED','RUNTIME_VERIFIED','LOOPBACK_VERIFIED','NGINX_STAGED','NGINX_VALIDATED','ACTIVATION_DRIFT_CHECK','STATIC_ACTIVATED','NGINX_RELOADED','HTTPS_SMOKE','STATIC_CHECK']
        # Each case gets a clean disposable namespace with actual frozen publisher.
        for stage in stages:
            with self.subTest(stage=stage):
                case=CombinedTests('test_complete_1277_file_publish_and_restore');case.setUp()
                try:
                    real=case.tx.step
                    def step(name,action):
                        value=real(name,action)
                        if name==stage:raise KeyboardInterrupt('injected post-action interruption')
                        return value
                    case.tx.step=step
                    with self.assertRaises(KeyboardInterrupt):case.apply()
                    self.assertEqual(json.loads(case.tx.receipt.read_text())['state'],'HOLD_PARTIAL')
                    self.assertEqual(case.tx.rollback()['state'],'ROLLED_BACK')
                    self.assertFalse(case.ops.active)
                finally:case.doCleanups()
    def test_partial_new_file_is_held_without_deletion(self):
        self.apply();c.UNIT.write_bytes(b'partial-or-foreign')
        with self.assertRaisesRegex(c.Hold,'RECOVERY_UNIT_DRIFT'):self.tx.rollback()
        self.assertEqual(c.UNIT.read_bytes(),b'partial-or-foreign')
    def test_bundle_corruption_rejected_before_host_probes(self):
        p=self.tx.inputs/'PR122_SITE_HUB_REVIEW_ONLY.tar.gz';p.write_bytes(p.read_bytes()+b'changed')
        with self.assertRaisesRegex(c.Hold,'FROZEN_ARCHIVE_HASH'):self.apply()
        self.assertEqual(self.ops.calls,[])
    def test_symlink_input_rejected(self):
        p=self.tx.inputs/'PR122_SITE_HUB_REVIEW_ONLY.tar.gz';p.rename(p.with_suffix('.original'));p.symlink_to(p.with_suffix('.original'))
        with self.assertRaisesRegex(c.Hold,'UNTRUSTED_OWNER_OR_LINK'):self.apply()
    def test_backup_corruption_blocks_recovery(self):
        self.apply();(self.tx.folder/'backup/previous-static.tar.gz').write_bytes(b'corrupt')
        with self.assertRaisesRegex(c.Hold,'BACKUP_ARCHIVE_DRIFT'):self.tx.rollback()
        self.assertTrue(self.ops.active)
    def test_mid_activation_config_change_is_held_before_pointer_switch(self):
        real=self.tx.verify_before_activation
        def drift():
            c.HTTPS.write_bytes(b'foreign');return real()
        self.tx.verify_before_activation=drift
        with self.assertRaisesRegex(c.Hold,'STAGED_CONFIG_DRIFT'):self.apply()
        self.assertEqual(os.readlink(c.BASE/'current'),self.pins['previous_release'])
    def test_unproved_sandbox_stops_before_nginx_and_can_recover(self):
        self.ops.sandbox=mock.Mock(side_effect=c.Hold('UNSUPPORTED_BPF'))
        with self.assertRaisesRegex(c.Hold,'UNSUPPORTED_BPF'):self.apply()
        self.assertFalse(c.LIMIT.exists());self.assertEqual(os.readlink(c.BASE/'current'),self.pins['previous_release'])
        self.assertEqual(self.tx.rollback()['state'],'ROLLED_BACK');self.assertFalse(self.ops.active)
    def test_foreign_runtime_is_not_stopped_or_deleted(self):
        self.apply();p=c.RUNTIME/c.RELEASE/'scripts/pr122_site_hub_preview.py';p.write_bytes(b'foreign-runtime')
        with self.assertRaisesRegex(c.Hold,'SEALED_RUNTIME_MANIFEST_DRIFT'):self.tx.rollback()
        self.assertTrue(self.ops.active);self.assertEqual(p.read_bytes(),b'foreign-runtime')
    def test_approval_expiring_before_activation_is_held_and_recoverable(self):
        real=self.tx.verify_before_activation
        def expired():
            self.tx.data['approval']['expires_unix']=0;return real()
        self.tx.verify_before_activation=expired
        with self.assertRaisesRegex(c.Hold,'EXPIRED_OR_INVALID_GATE'):self.apply()
        self.assertEqual(os.readlink(c.BASE/'current'),self.pins['previous_release'])
        self.assertEqual(self.tx.rollback()['state'],'ROLLED_BACK')
    def test_group_writable_approval_is_rejected(self):
        self.gatepath.chmod(0o660)
        with self.assertRaisesRegex(c.Hold,'WRITABLE_TRUST_CHAIN'):self.apply()
        self.assertFalse(self.tx.receipt.exists());self.assertEqual(self.ops.calls,[])

class PureTests(unittest.TestCase):
    def test_exact_routes_are_manifest_bounded(self):
        pins=json.loads((ROOT/'deploy/pr122-site-hub-combined/HOST_PINS.json').read_text())
        path=ROOT/'evidence/pr122-site-hub/PR122_SITE_HUB_REVIEW_ONLY.tar.gz'
        if not path.exists():path=ROOT/'review-package-preview-final/PR122_SITE_HUB_REVIEW_ONLY.tar.gz'
        entries=c.verified_entries(path.read_bytes(),pins);raw,routes=c.locations(entries)
        self.assertEqual(routes['/marketplace/'],('file','/marketplace/index.html'))
        self.assertEqual(routes['/marketplace'],('redirect','/marketplace/'))
        self.assertNotIn('/customer/private/',routes);self.assertNotIn('/p/',routes)
        self.assertNotIn(b'location ^~ /customer/',raw)
        self.assertEqual(raw.count(b'location ^~ /_preview/community-api/'),1)
        self.assertIn(b'proxy_set_header Origin $http_origin;',raw)
    def test_production_cli_has_no_test_root_or_host_override(self):
        source=(ROOT/'scripts/pr122_site_hub_combined.py').read_text()
        self.assertNotIn("add_argument('--allow-non-root",source)

if __name__=='__main__':unittest.main()
