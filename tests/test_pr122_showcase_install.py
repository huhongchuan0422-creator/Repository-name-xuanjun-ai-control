"""Disposable installer filesystem tests; systemd/Nginx/network are explicit fakes."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock
from scripts import pr122_showcase_install as i
from scripts import pr122_showcase_promote as p
from scripts.pr122_showcase import sha,canonical

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.geteuid()==0,'Disposable root files required')
class InstallTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(dir='/root',prefix='showcase-install-test-');self.addCleanup(temp.cleanup);root=Path(temp.name);self.root=root
        paths={'CODE':root/'code','CONFIG':root/'config','NGINX':root/'nginx/showcase/locations.conf','HTTPS':root/'nginx/https.conf','STATE':root/'state','SERVICE':root/'units/showcase.service','TIMER':root/'units/showcase.timer','ENABLE':root/'units/wants/showcase.timer','MAIN_CURRENT':root/'main/current'}
        for path in (root/'config',root/'nginx',root/'units',root/'main'):path.mkdir()
        for name,value in paths.items():
            patch=mock.patch.object(i,name,value);patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(p,'BASE',root/'showcase');patch.start();self.addCleanup(patch.stop)
        (i.CONFIG/'github-readonly-token').write_text('TEST_ONLY_NOT_A_REAL_GITHUB_TOKEN');(i.CONFIG/'github-readonly-token').chmod(0o600)
        self.old=b'server {\n    '+i.ANCHOR+b'\n}\n';i.HTTPS.write_bytes(self.old)
        os.symlink('/var/www/example/releases/retained',i.MAIN_CURRENT)
        self.source=root/'source';self.source.mkdir();files={}
        for name in ('deploy/pr122-showcase/locations.conf','deploy/pr122-showcase/xuanjun-showcase-publish.service','deploy/pr122-showcase/xuanjun-showcase-publish.timer','scripts/pr122_website_release.py'):
            raw=(ROOT/name).read_bytes();target=self.source/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);files[name]=raw
        manifest={'files':[{'path':name,'size':len(raw),'sha256':sha(raw)} for name,raw in files.items()]}
        (self.source/'MECHANISM_MANIFEST.json').write_bytes(canonical(manifest))
        approval={'transaction_id':'pr122-showcase-install-20261016','previous_https_sha256':sha(self.old),'main_current':os.readlink(i.MAIN_CURRENT),'rollback_approved':True,'expires_unix':int(time.time())+600,'previous_nginx_inventory_sha256':'TEST_INVENTORY'}
        patch=mock.patch.object(i,'gate',return_value=approval);patch.start();self.addCleanup(patch.stop)
        for name,value in [('nginx_snapshot','TEST_INVENTORY'),('nginx_identity',{'scope':'FAKE_NGINX_PROCESS'})]:
            patch=mock.patch.object(i,name,return_value=value);patch.start();self.addCleanup(patch.stop)
        def inventory():
            result={str(i.HTTPS):sha(i.HTTPS.read_bytes())}
            if i.EXTRA in i.HTTPS.read_bytes() and i.NGINX.exists():result[str(i.NGINX)]=sha(i.NGINX.read_bytes())
            return result
        patch=mock.patch.object(i,'nginx_files',side_effect=inventory);patch.start();self.addCleanup(patch.stop)
        self.calls=[]
        def command(args):self.calls.append(args);return self.old if '-T' in args else b''
        patch=mock.patch.object(i,'command',side_effect=command);patch.start();self.addCleanup(patch.stop)
    def test_complete_install_restore_does_not_touch_main_current(self):
        r=i.install(self.source,1);self.assertEqual(r['state'],'INSTALLED_AWAIT_FIRST_APPROVED_PUBLICATION')
        self.assertIn(i.EXTRA,i.HTTPS.read_bytes());self.assertEqual(i.rollback()['state'],'ROLLED_BACK');self.assertEqual(i.HTTPS.read_bytes(),self.old)
        self.assertEqual(os.readlink(i.MAIN_CURRENT),'/var/www/example/releases/retained')
    def test_preexisting_objects_are_not_adopted(self):
        i.CODE.mkdir()
        with self.assertRaisesRegex(ValueError,'PREEXISTING_INSTALL_OBJECT'):i.install(self.source,1)
        self.assertFalse(i.STATE.exists())
    def test_missing_credential_stops_before_mutation(self):
        (i.CONFIG/'github-readonly-token').unlink()
        with self.assertRaisesRegex(RuntimeError,'TRUSTED_INPUT_PATH_UNAVAILABLE'):i.install(self.source,1)
        self.assertFalse(i.STATE.exists());self.assertEqual(i.HTTPS.read_bytes(),self.old)
    def test_partial_file_install_can_roll_back_before_service_creation(self):
        real=i.write_new
        def fail(path,raw,mode=0o644):
            if path==i.NGINX:raise RuntimeError('INJECTED_BEFORE_NGINX_FILE')
            return real(path,raw,mode)
        with mock.patch.object(i,'write_new',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'INJECTED'):i.install(self.source,1)
        self.assertEqual(i.rollback()['state'],'ROLLED_BACK');self.assertEqual(i.HTTPS.read_bytes(),self.old)
    def test_partial_after_https_replace_restores_owned_configuration(self):
        def command(args):
            if args==['/usr/sbin/nginx','-t']:raise RuntimeError('INJECTED_NGINX_TEST_FAILURE')
            return self.old if '-T' in args else b''
        with mock.patch.object(i,'command',side_effect=command):
            with self.assertRaisesRegex(RuntimeError,'INJECTED'):i.install(self.source,1)
        self.assertIn(i.EXTRA,i.HTTPS.read_bytes());self.assertEqual(i.rollback()['state'],'ROLLED_BACK');self.assertEqual(i.HTTPS.read_bytes(),self.old)
    def test_foreign_config_blocks_rollback(self):
        i.install(self.source,1);i.HTTPS.write_text('foreign administrator edit')
        with self.assertRaisesRegex(ValueError,'FOREIGN_HTTPS_CONFIG'):i.rollback()

if __name__=='__main__':unittest.main()
