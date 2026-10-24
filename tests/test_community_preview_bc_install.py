"""Isolated tests for the fixed STOPPED_HANDOFF_V1 installer. No production path/sudo."""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from scripts import community_preview_bc_build as build
from scripts import community_preview_bc_install as ins

class FixedInstaller(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive,cls.manifest,_=build.build()
        assert hashlib.sha256(cls.archive).hexdigest()==ins.ARCHIVE_SHA256
        assert hashlib.sha256(cls.manifest).hexdigest()==ins.MANIFEST_SHA256
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);os.chmod(self.root,0o700)
        self.parent=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);self.addCleanup(self._close_parent)
        self.uid=os.getuid();self.gid=os.getgid()
        self.a=self.root/'control-oci2330-v1';self.a.mkdir(mode=0o700);(self.a/'sentinel').write_bytes(b'A_V1_SENTINEL')
        os.chmod(self.a/'sentinel',0o600)
    def _close_parent(self):
        if self.parent is not None:
            os.close(self.parent);self.parent=None
    def install(self,archive=None,manifest=None,fault=None):
        return ins.install_bytes(self.archive if archive is None else archive,
                                 self.manifest if manifest is None else manifest,
                                 self.parent,self.uid,self.gid,fault)
    def assert_a(self):self.assertEqual((self.a/'sentinel').read_bytes(),b'A_V1_SENTINEL')
    def mutate_zip(self,entries):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for name,body,mode in entries:
                info=zipfile.ZipInfo(name,(2026,10,24,0,0,0));info.create_system=3;info.external_attr=mode<<16;info.compress_type=zipfile.ZIP_DEFLATED
                z.writestr(info,body)
        return out.getvalue()
    def base_entries(self):
        with zipfile.ZipFile(io.BytesIO(self.archive)) as z:
            return [(i.filename,z.read(i), (i.external_attr>>16)&0xffff) for i in z.infolist()]
    def test_exact_package_binding_and_normal_atomic_publish(self):
        r=self.install();self.assertEqual(r['state'],'V2_CARRIER_INSTALLED')
        target=self.root/ins.TARGET;self.assertTrue(target.is_dir());self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o700)
        manifest=json.loads(self.manifest)
        for rel,meta in manifest['files'].items():
            p=target/rel;self.assertTrue(p.is_file());self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
            self.assertEqual(len(p.read_bytes()),meta['bytes']);self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),meta['sha256'])
        self.assertEqual((target/'manifest.json').read_bytes(),self.manifest);self.assert_a()
    def test_bad_archive_or_manifest_hash_zero_target(self):
        with self.assertRaisesRegex(ins.Hold,'FIXED_ARCHIVE_SHA'):self.install(archive=self.archive+b'x')
        with self.assertRaisesRegex(ins.Hold,'FIXED_MANIFEST_SHA'):self.install(manifest=self.manifest+b' ')
        self.assertFalse((self.root/ins.TARGET).exists());self.assert_a()
    def test_traversal_absolute_backslash_and_unexpected_member_rejected_before_write(self):
        base=self.base_entries()
        for bad in ('../escape','/absolute','scripts\\evil.py','unexpected.txt'):
            entries=base+[(bad,b'x',0o100600)]
            raw=self.mutate_zip(entries)
            with self.subTest(bad=bad),self.assertRaises(ins.Hold):ins.validate_archive_contents(raw,self.manifest)
        self.assertFalse((self.root/ins.TARGET).exists());self.assert_a()
    def test_duplicate_and_nonregular_members_rejected(self):
        base=self.base_entries();name,body,mode=base[0]
        duplicate=self.mutate_zip(base+[(name,body,mode)])
        with self.assertRaisesRegex(ins.Hold,'DUPLICATE_MEMBER'):ins.validate_archive_contents(duplicate,self.manifest)
        bad=[]
        for n,b,m in base:bad.append((n,b,(stat.S_IFLNK|0o600) if n==name else m))
        with self.assertRaisesRegex(ins.Hold,'REGULAR_0600'):ins.validate_archive_contents(self.mutate_zip(bad),self.manifest)
    def test_existing_target_or_partial_temp_holds_without_touching_a(self):
        (self.root/ins.TARGET).mkdir(mode=0o700)
        with self.assertRaisesRegex(ins.Hold,'TARGET_OR_PARTIAL'):self.install()
        self.assert_a()
        os.rmdir(self.root/ins.TARGET);(self.root/ins.TEMP).mkdir(mode=0o700)
        with self.assertRaisesRegex(ins.Hold,'TARGET_OR_PARTIAL'):self.install()
        self.assert_a()
    def test_target_symlink_holds(self):
        os.symlink(self.a,self.root/ins.TARGET)
        with self.assertRaisesRegex(ins.Hold,'TARGET_OR_PARTIAL'):self.install()
        self.assert_a()
    def test_midway_failure_never_publishes_success_name_or_overwrites_a(self):
        def fault(stage,name,index):
            if stage=='after-file' and index==2:raise RuntimeError('SYNTHETIC_MID_WRITE')
        with self.assertRaisesRegex(RuntimeError,'SYNTHETIC_MID_WRITE'):self.install(fault=fault)
        self.assertFalse((self.root/ins.TARGET).exists());self.assertTrue((self.root/ins.TEMP).is_dir());self.assert_a()
    def test_before_publish_failure_leaves_only_nonfinal_temp(self):
        def fault(stage,name,index):
            if stage=='before-publish':raise RuntimeError('SYNTHETIC_PRE_PUBLISH')
        with self.assertRaisesRegex(RuntimeError,'SYNTHETIC_PRE_PUBLISH'):self.install(fault=fault)
        self.assertFalse((self.root/ins.TARGET).exists());self.assertTrue((self.root/ins.TEMP).exists());self.assert_a()
    def test_target_race_before_publish_is_noreplace_hold(self):
        def fault(stage,name,index):
            if stage=='before-publish':
                target=self.root/ins.TARGET;target.mkdir(mode=0o700);(target/'foreign').write_bytes(b'FOREIGN')
        with self.assertRaisesRegex(ins.Hold,'TARGET_OR_PARTIAL'):self.install(fault=fault)
        self.assertEqual((self.root/ins.TARGET/'foreign').read_bytes(),b'FOREIGN');self.assertTrue((self.root/ins.TEMP).exists());self.assert_a()
    def test_extra_member_in_temp_tree_is_rejected_before_publish(self):
        def fault(stage,name,index):
            if stage=='after-file' and index==0:
                p=self.root/ins.TEMP/'rogue';p.write_bytes(b'ROGUE');os.chmod(p,0o600)
        with self.assertRaisesRegex(ins.Hold,'FINAL_MEMBER_SET_CHANGED'):self.install(fault=fault)
        self.assertFalse((self.root/ins.TARGET).exists());self.assertTrue((self.root/ins.TEMP).exists());self.assert_a()
    def test_hardlinked_or_writable_input_is_rejected_by_cli_reader(self):
        p=self.root/'p.zip';p.write_bytes(self.archive);os.chmod(p,0o600)
        q=self.root/'q.zip';os.link(p,q)
        with self.assertRaisesRegex(ins.Hold,'PROTECTED_INPUT'):ins.open_input(str(p),ins.MAX_ARCHIVE)
        q.unlink();os.chmod(p,0o622)
        with self.assertRaisesRegex(ins.Hold,'PROTECTED_INPUT'):ins.open_input(str(p),ins.MAX_ARCHIVE)
    def test_production_identity_is_not_inferred_from_test_fixture(self):
        with patch.object(ins.os,'getuid',return_value=1234),patch.object(ins.os,'geteuid',return_value=1234),self.assertRaisesRegex(ins.Hold,'EXACT_ROOT_HOST'):
            ins.production_identity()
    def test_source_contains_no_extractall_and_shell_is_fixed_sudo_entry(self):
        source=Path(ins.__file__).read_text();self.assertNotIn('extractall(',source)
        shell=(Path(__file__).resolve().parents[1]/'deploy/community-preview/install-stopped-v1.sh').read_text()
        self.assertIn('/usr/bin/sudo -n /usr/bin/python3 -I -B -S scripts/community_preview_bc_install.py',shell)
        self.assertNotIn('control-oci2330-v1',shell)

if __name__=='__main__':unittest.main()
