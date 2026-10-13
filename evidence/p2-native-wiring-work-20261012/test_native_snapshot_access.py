"""Regression tests for native snapshot ACL scope and fail-closed imports."""
import os, sys, stat, pathlib, tempfile, unittest, types
from unittest import mock
ROOT=pathlib.Path(os.environ['P2_SOURCE_ROOT'])
sys.path.insert(0,str(ROOT/'stage1'))
from native_snapshot_access import NativeSnapshotAccess, encode, decode, USER, USER_OBJ, MASK, OTHER, UNDEFINED
from development_pipeline import CliBackend

class ACLValidation(unittest.TestCase):
    def setUp(self):
        self.policy=NativeSnapshotAccess('/tmp/p2-unit-worktrees',1003,1002)
    def file(self, entries=None, mode=0o660, owner=1003, nlink=1):
        info=types.SimpleNamespace(st_uid=owner,st_mode=stat.S_IFREG|mode,st_nlink=nlink)
        entries=self.policy._entries(6) if entries is None else entries
        with mock.patch('native_snapshot_access.os.fstat',return_value=info),mock.patch('native_snapshot_access.os.getxattr',return_value=encode(entries)):
            return self.policy.validate(7)
    def test_encoding_roundtrip(self):
        entries=self.policy._entries(6);self.assertEqual(decode(encode(entries)),entries)
    def test_reject_encoding_version(self):
        with self.assertRaises(ValueError):decode(b'\x01\x00\x00\x00')
    def test_exact_dispatcher_and_gateway_files(self):
        for uid in (1003,1002):self.assertEqual(self.file(owner=uid),0o100644)
    def test_reject_foreign_file_owner(self):
        with self.assertRaises(ValueError):self.file(owner=1005)
    def test_reject_device_file_type(self):
        info=types.SimpleNamespace(st_uid=1003,st_mode=stat.S_IFCHR|0o660,st_nlink=1)
        with mock.patch('native_snapshot_access.os.fstat',return_value=info):
            with self.assertRaises(ValueError):self.policy.validate(7)
    def test_reject_hardlink(self):
        with self.assertRaises(ValueError):self.file(nlink=2)
    def test_reject_world_access(self):
        with self.assertRaises(ValueError):self.file(mode=0o664)
    def test_reject_missing_acl(self):
        with self.assertRaises(ValueError):self.file(entries=[])
    def test_reject_additional_user(self):
        entries=self.policy._entries(6);entries.insert(3,(USER,6,1005))
        with self.assertRaises(ValueError):self.file(entries=entries)
    def test_reject_wrong_named_user(self):
        entries=self.policy._entries(6);entries[1]=(USER,6,1005)
        with self.assertRaises(ValueError):self.file(entries=entries)
    def test_reject_group_access_hidden_by_mask(self):
        entries=self.policy._entries(6);entries[3]=(4,6,UNDEFINED)
        with self.assertRaises(ValueError):self.file(entries=entries)
    def test_reject_world_acl_hidden_by_mode(self):
        entries=self.policy._entries(6);entries[-1]=(OTHER,4,UNDEFINED)
        with self.assertRaises(ValueError):self.file(entries=entries)
    def test_reject_read_only_named_user(self):
        entries=self.policy._entries(6);entries[1]=(USER,4,1002)
        with self.assertRaises(ValueError):self.file(entries=entries)
    def test_reject_same_uid(self):
        with self.assertRaises(ValueError):NativeSnapshotAccess('/tmp/p2-unit-worktrees',1003,1003)
    def test_reject_general_workspace(self):
        with self.assertRaises(ValueError):NativeSnapshotAccess('/tmp',1003,1002)
    def test_importer_scope_denied(self):
        with self.assertRaises(ValueError):self.policy.share('/var/lib/service-home/.importer')
    def test_changed_directory_default_acl_denied(self):
        info=types.SimpleNamespace(st_uid=1003,st_mode=stat.S_IFDIR|0o770,st_nlink=2)
        raw=encode(self.policy._entries(7))
        with mock.patch('native_snapshot_access.os.fstat',return_value=info),mock.patch('native_snapshot_access.os.getxattr',side_effect=[raw,encode(self.policy._entries(6))]):
            with self.assertRaises(ValueError):self.policy.validate(7,True)

@unittest.skipIf(os.geteuid()==0,'Real unprivileged ACL tests run in hosted CI; cross-UID tests run on UK.')
class KernelSnapshots(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='p2-snapshot-unit-')
        self.root=self.temp.name+'/worktrees';os.mkdir(self.root,0o755)
        self.policy=NativeSnapshotAccess(self.root,os.geteuid(),os.geteuid()+1)
        self.backend=CliBackend({'owner/repo':self.temp.name+'/control.git'},self.root,self.temp.name+'/home','/usr/bin:/bin',['checks'],snapshot_access=self.policy)
    def tearDown(self):self.temp.cleanup()
    def test_write_and_scan_preserve_git_modes(self):
        snapshot=self.root+'/snapshot'
        self.backend._write_snapshot(snapshot,{'a.py':{'mode':0o100644,'data':b'x=1\n'},'bin/run':{'mode':0o100755,'data':b'#!/bin/sh\n'}})
        observed=self.backend._scan_snapshot(snapshot)
        self.assertEqual(observed['a.py']['mode'],0o100644);self.assertEqual(observed['bin/run']['mode'],0o100755)
        self.assertEqual(observed['a.py']['data'],b'x=1\n')
        self.assertEqual(stat.S_IMODE(os.stat(snapshot+'/a.py').st_mode),0o660)
    def test_private_legacy_snapshots_stay_private(self):
        self.backend.snapshot_access=None;snapshot=self.root+'/legacy'
        self.backend._write_snapshot(snapshot,{'a.py':{'mode':0o100644,'data':b'x=1\n'}})
        self.assertEqual(stat.S_IMODE(os.stat(snapshot+'/a.py').st_mode),0o600)
        self.assertEqual(stat.S_IMODE(os.stat(snapshot).st_mode),0o700)
    def test_new_file_inherits_importer_read_access(self):
        snapshot=self.root+'/snapshot';self.backend._write_snapshot(snapshot,{'a.py':{'mode':0o100644,'data':b'x=1\n'}})
        os.mkdir(snapshot+'/newdir')
        with open(snapshot+'/newdir/new.py','w') as f:f.write('x=2\n')
        self.assertEqual(self.backend._scan_snapshot(snapshot)['newdir/new.py']['mode'],0o100644)
    def test_foreign_acl_rejected_during_scan(self):
        snapshot=self.root+'/snapshot';self.backend._write_snapshot(snapshot,{'a.py':{'mode':0o100644,'data':b'x=1\n'}})
        entries=self.policy._entries(6);entries.insert(3,(USER,6,os.geteuid()+2))
        os.setxattr(snapshot+'/a.py','system.posix_acl_access',encode(entries))
        with self.assertRaises(ValueError):self.backend._scan_snapshot(snapshot)
    def test_symlink_rejected_before_acl(self):
        snapshot=self.root+'/snapshot';os.mkdir(snapshot);os.symlink('/etc/passwd',snapshot+'/link')
        with self.assertRaisesRegex(ValueError,'SNAPSHOT_SPECIAL_ENTRY_REJECTED'):self.policy.share(snapshot)
    def test_fifo_rejected_without_blocking(self):
        snapshot=self.root+'/snapshot';os.mkdir(snapshot);os.mkfifo(snapshot+'/fifo')
        with self.assertRaises(ValueError):self.policy.share(snapshot)
    def test_hardlink_rejected(self):
        snapshot=self.root+'/snapshot';os.mkdir(snapshot)
        with open(snapshot+'/a','w') as f:f.write('fixture')
        os.link(snapshot+'/a',snapshot+'/b')
        with self.assertRaises(ValueError):self.policy.share(snapshot)

if __name__=='__main__':unittest.main()
