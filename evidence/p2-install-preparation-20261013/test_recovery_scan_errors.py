"""B1/B2 fail-closed traversal regressions; Python 3.6, scratch only."""
import errno
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent))
import recover_exact_hold as r


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.tree = self.root / 'jobs'
        self.tree.mkdir()
        self.sub = self.tree / 'nested'
        self.sub.mkdir()
        (self.sub / 'job').write_bytes(b'safe')
    def tearDown(self):
        self.tmp.cleanup()
    def scan(self):
        return r.bounded_file_inventory(str(self.tree), optional=True)
    def test_nested_files_are_included(self):
        self.assertEqual(self.scan(), {str(self.sub/'job'): r.sha(b'safe')})
    def test_optional_genuine_absence(self):
        self.assertEqual(r.bounded_file_inventory(str(self.root/'missing'), optional=True), {})
    def test_required_absence_fails(self):
        with self.assertRaises(ValueError): r.bounded_file_inventory(str(self.root/'missing'))
    def test_denied_root_listing_fails(self):
        with mock.patch.object(r.os, 'listdir', side_effect=PermissionError(errno.EACCES, 'denied')):
            with self.assertRaises(PermissionError): self.scan()
    def test_denied_nested_listing_fails(self):
        orig=os.listdir; inode=self.sub.stat().st_ino
        def listing(fd):
            if os.fstat(fd).st_ino == inode: raise PermissionError(errno.EACCES, 'nested')
            return orig(fd)
        with mock.patch.object(r.os, 'listdir', side_effect=listing):
            with self.assertRaises(PermissionError): self.scan()
    def test_vanished_nested_listing_fails(self):
        orig=os.listdir; inode=self.sub.stat().st_ino
        def listing(fd):
            if os.fstat(fd).st_ino == inode: raise FileNotFoundError(errno.ENOENT, 'race')
            return orig(fd)
        with mock.patch.object(r.os, 'listdir', side_effect=listing):
            with self.assertRaises(FileNotFoundError): self.scan()
    def test_root_stat_permission_is_not_absence(self):
        with mock.patch.object(r.os, 'stat', side_effect=PermissionError(errno.EACCES, 'stat')):
            with self.assertRaises(PermissionError): self.scan()
    def test_absence_parent_listing_error_fails(self):
        with mock.patch.object(r.os,'listdir',side_effect=PermissionError(errno.EACCES,'parent')):
            with self.assertRaises(PermissionError):
                r.bounded_file_inventory(str(self.root/'missing'),optional=True)
    def test_nested_alias_rejected(self):
        (self.sub/'alias').symlink_to(self.root)
        with self.assertRaises(ValueError): self.scan()
    def test_root_alias_rejected(self):
        alias=self.root/'alias'; alias.symlink_to(self.tree)
        with self.assertRaises(ValueError): r.bounded_file_inventory(str(alias), optional=True)
    def test_special_file_rejected_without_open(self):
        os.mkfifo(str(self.sub/'fifo'))
        with self.assertRaises(ValueError): self.scan()
    def test_entries_changed_during_scan(self):
        orig=os.listdir; inode=self.tree.stat().st_ino; calls=[0]
        def listing(fd):
            names=orig(fd)
            if os.fstat(fd).st_ino==inode:
                calls[0]+=1
                if calls[0]==2: names.append('phantom')
            return names
        with mock.patch.object(r.os,'listdir',side_effect=listing):
            with self.assertRaises(ValueError): self.scan()
    def test_file_read_permission_fails(self):
        with mock.patch.object(r.os,'read',side_effect=PermissionError(errno.EACCES,'read')):
            with self.assertRaises(PermissionError): self.scan()
    def test_file_vanish_between_stat_and_open(self):
        orig=os.open
        def opening(path,*args,**kwargs):
            if path=='job': raise FileNotFoundError(errno.ENOENT,'race')
            return orig(path,*args,**kwargs)
        with mock.patch.object(r.os,'open',side_effect=opening):
            with self.assertRaises(FileNotFoundError): self.scan()
    def test_file_content_drift_rejected(self):
        orig=os.read; changed=[False]
        def reading(fd,n):
            data=orig(fd,n)
            if data and not changed[0]:
                changed[0]=True; (self.sub/'job').write_bytes(b'changed')
            return data
        with mock.patch.object(r.os,'read',side_effect=reading):
            with self.assertRaises(ValueError): self.scan()
    def test_depth_bound(self):
        path=self.sub
        for i in range(33): path=path/'d'; path.mkdir()
        with self.assertRaisesRegex(ValueError,'BOUND'): self.scan()
    def test_listing_bound(self):
        with mock.patch.object(r.os,'listdir',return_value=['x']*8193):
            with self.assertRaisesRegex(ValueError,'BOUND'): self.scan()
    def test_file_size_bound(self):
        (self.sub/'job').write_bytes(b'x'*1048577)
        with self.assertRaisesRegex(ValueError,'BOUND'): self.scan()


class NotifierTests(unittest.TestCase):
    def setUp(self):
        self.mount=mock.patch.object(r,'verify_systemd_controller_mount'); self.mount.start()
        self.addCleanup(self.mount.stop)
        self.tmp=tempfile.TemporaryDirectory(); self.controller=Path(self.tmp.name)
        self.name='xj-uk-owner-notify.service'; self.group=self.controller/self.name
        self.ok=subprocess.CompletedProcess([],0,b'ActiveState=inactive\nMainPID=0\nUnitFileState=masked\n',b'')
    def tearDown(self): self.tmp.cleanup()
    def check(self):
        with mock.patch('subprocess.run',return_value=self.ok):
            return r.notifier_cgroup_empty(self.name,str(self.controller))
    def make(self):
        self.group.mkdir(); (self.group/'cgroup.procs').write_bytes(b'')
    def test_absent_inactive_masked_zero_pid_is_empty(self): self.assertEqual(self.check(),{})
    def test_nested_empty_groups(self):
        self.make(); sub=self.group/'child';sub.mkdir();(sub/'cgroup.procs').write_bytes(b'')
        self.assertEqual(len(self.check()),2)
    def test_live_descendant_rejected(self):
        self.make();sub=self.group/'child';sub.mkdir();(sub/'cgroup.procs').write_bytes(b'912\n')
        with self.assertRaisesRegex(ValueError,'BUSY'): self.check()
    def test_missing_procs_rejected(self):
        self.group.mkdir()
        with self.assertRaisesRegex(ValueError,'PROCS_MISSING'): self.check()
    def test_denied_procs_rejected(self):
        self.make()
        with mock.patch.object(r.os,'read',side_effect=PermissionError(errno.EACCES,'procs')):
            with self.assertRaises(PermissionError): self.check()
    def test_controller_missing_rejected(self):
        with self.assertRaises(FileNotFoundError): r.notifier_cgroup_empty(self.name,str(self.controller/'missing'))
    def test_controller_alias_rejected(self):
        alias=self.controller/'alias';alias.symlink_to(self.controller)
        with self.assertRaises(ValueError): r.notifier_cgroup_empty(self.name,str(alias))
    def test_unit_alias_rejected(self):
        self.group.symlink_to(self.controller)
        with self.assertRaises(ValueError): self.check()
    def test_absent_but_active_rejected(self):
        bad=subprocess.CompletedProcess([],0,b'ActiveState=active\nMainPID=4\nUnitFileState=masked\n',b'')
        with mock.patch('subprocess.run',return_value=bad):
            with self.assertRaises(ValueError): r.notifier_cgroup_empty(self.name,str(self.controller))
    def test_service_missing_pid_rejected(self):
        bad=subprocess.CompletedProcess([],0,b'ActiveState=inactive\nUnitFileState=masked\n',b'')
        with mock.patch('subprocess.run',return_value=bad):
            with self.assertRaises(ValueError): r.notifier_cgroup_empty(self.name,str(self.controller))
    def test_timer_has_no_main_pid_property(self):
        timer=subprocess.CompletedProcess([],0,b'ActiveState=inactive\nUnitFileState=masked\n',b'')
        with mock.patch('subprocess.run',return_value=timer):
            self.assertEqual(r.notifier_cgroup_empty('xj-uk-owner-notify.timer',str(self.controller)),{})
    def test_state_change_after_scan_rejected(self):
        bad=subprocess.CompletedProcess([],0,b'ActiveState=active\nMainPID=4\nUnitFileState=masked\n',b'')
        with mock.patch('subprocess.run',side_effect=[self.ok,bad]):
            with self.assertRaises(ValueError): r.notifier_cgroup_empty(self.name,str(self.controller))
    def test_cgroup_nested_listing_denied(self):
        self.make();sub=self.group/'child';sub.mkdir();(sub/'cgroup.procs').write_bytes(b'')
        orig=os.listdir;inode=sub.stat().st_ino
        def listing(fd):
            if os.fstat(fd).st_ino==inode: raise PermissionError(errno.EACCES,'nested')
            return orig(fd)
        with mock.patch.object(r.os,'listdir',side_effect=listing):
            with self.assertRaises(PermissionError): self.check()
    def test_cgroup_disappears_after_parent_listing(self):
        self.make();orig=os.open
        def opening(path,*args,**kwargs):
            if path==self.name: raise FileNotFoundError(errno.ENOENT,'raced')
            return orig(path,*args,**kwargs)
        with mock.patch.object(r.os,'open',side_effect=opening):
            with self.assertRaises(FileNotFoundError): self.check()


class MountTests(unittest.TestCase):
    valid=b'21 10 0:20 / /sys/fs/cgroup/systemd rw - cgroup cgroup rw,name=systemd\n'
    def test_real_systemd_v1_mount(self): r.validate_systemd_mountinfo(self.valid)
    def test_missing_controller_mount(self):
        with self.assertRaises(ValueError): r.validate_systemd_mountinfo(b'')
    def test_wrong_filesystem(self):
        with self.assertRaises(ValueError): r.validate_systemd_mountinfo(self.valid.replace(b'- cgroup',b'- tmpfs'))
    def test_wrong_controller(self):
        with self.assertRaises(ValueError): r.validate_systemd_mountinfo(self.valid.replace(b'name=systemd',b'memory'))
    def test_duplicate_mount(self):
        with self.assertRaises(ValueError): r.validate_systemd_mountinfo(self.valid*2)
    def test_mount_read_denied_propagates(self):
        with mock.patch('builtins.open',side_effect=PermissionError(errno.EACCES,'mountinfo')):
            with self.assertRaises(PermissionError): r.verify_systemd_controller_mount()


if __name__=='__main__': unittest.main(verbosity=2)
