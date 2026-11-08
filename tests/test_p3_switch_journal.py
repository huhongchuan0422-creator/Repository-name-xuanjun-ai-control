import os
import sqlite3
import tempfile
import unittest
from install.p3_switch_journal import SwitchCoordinator
from src.p3_operation_kernel import MIGRATION, RunnerOperationStore

class SwitchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=os.path.join(self.tmp.name,'root'); os.mkdir(self.root,0o700)
        self.path=os.path.join(self.tmp.name,'db')
        def connect(): return sqlite3.connect(self.path,timeout=10)
        db=connect(); db.execute(MIGRATION); db.commit(); db.close()
        self.store=RunnerOperationStore(connect)
        self.fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        self.addCleanup(lambda:os.close(self.fd))
        self.switch=SwitchCoordinator(self.fd,self.store); self.addCleanup(self.switch.close)
        self.make('staged',b'new')
    def make(self,name,data):
        os.mkdir(os.path.join(self.root,name),0o700)
        with open(os.path.join(self.root,name,'file'),'wb') as f:f.write(data)
    def read(self,name):
        with open(os.path.join(self.root,name,'file'),'rb') as f:return f.read()
    def test_install_rollback_repeat_and_restart(self):
        self.make('current',b'old')
        self.assertEqual('SWITCHED',self.switch.switch('install','staged','current')['state'])
        self.assertEqual(b'new',self.read('current'))
        self.assertEqual('ROLLED_BACK',self.switch.rollback('rollback','install')['state'])
        self.assertEqual(b'old',self.read('current'))
        self.assertEqual('ROLLED_BACK',self.switch.rollback('rollback','install')['state'])
    def test_duplicate_rollback_rechecks_target_tree(self):
        self.make('current',b'old')
        self.switch.switch('install','staged','current')
        self.switch.rollback('rollback','install')
        with open(os.path.join(self.root,'current','file'),'wb') as f: f.write(b'changed')
        self.assertEqual('UNKNOWN',self.switch.rollback('rollback','install')['state'])
    def test_changed_prestate_before_switch_holds(self):
        self.make('current',b'old')
        def mutate(phase):
            if phase=='before_rename':
                with open(os.path.join(self.root,'current','file'),'wb') as f:f.write(b'changed')
        with self.assertRaises(RuntimeError):self.switch.switch('op','staged','current',mutate)
        self.assertEqual('UNKNOWN',self.switch.reconcile('op')['state'])
        self.assertEqual(b'new',self.read('staged'))
    def test_rollback_interrupted_after_rename_reconciles(self):
        self.make('current',b'old');self.switch.switch('install','staged','current')
        def crash(phase):
            if phase=='after_rename':raise RuntimeError('crash')
        with self.assertRaises(RuntimeError):self.switch.rollback('rollback','install',crash)
        self.assertEqual('ROLLED_BACK',self.switch.rollback('rollback','install')['state'])
        self.assertEqual(b'old',self.read('current'))

    def test_formal_install_switch_rejects_missing_owner_guard(self):
        with self.assertRaisesRegex(PermissionError,'INSTALL_OWNERSHIP_GUARD_REQUIRED'):
            self.switch.switch('p3-install:attempt','staged','current')
        self.assertFalse(os.path.exists(os.path.join(self.root,'current')))

    def test_first_install_and_rollback(self):
        self.assertEqual('SWITCHED',self.switch.switch('install','staged','current')['state'])
        self.assertEqual('ROLLED_BACK',self.switch.rollback('rollback','install')['state'])
        self.assertFalse(os.path.exists(os.path.join(self.root,'current')))
    def test_crash_windows_reconcile_without_redial(self):
        for point in ('before_rename','after_rename','after_fsync'):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as td:
                root=os.path.join(td,'r');os.mkdir(root,0o700);os.mkdir(os.path.join(root,'staged'),0o700)
                with open(os.path.join(root,'staged','f'),'wb') as f:f.write(point.encode('ascii'))
                fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
                c=SwitchCoordinator(fd,self.store)
                def crash(phase):
                    if phase==point: raise RuntimeError('crash')
                try:
                    with self.assertRaises(RuntimeError): c.switch('op-'+point,'staged','current',crash)
                    state=c.reconcile('op-'+point)['state']
                    self.assertEqual('NOT_SWITCHED_HOLD' if point=='before_rename' else 'SWITCHED',state)
                finally: c.close();os.close(fd)
    def test_process_restart_with_prepared_running_is_hold(self):
        self.assertTrue(self.switch.prepare('op','staged','current'))
        resumed=SwitchCoordinator(self.fd,RunnerOperationStore(self.store.connect))
        try:
            self.assertEqual('NOT_SWITCHED_HOLD',resumed.reconcile('op')['state'])
            self.assertEqual('UNKNOWN',self.store.get('op')['state'])
            self.assertFalse(os.path.exists(os.path.join(self.root,'current')))
        finally: resumed.close()

    def test_conflicting_tree_holds(self):
        def crash(phase):
            if phase=='after_rename':raise RuntimeError('crash')
        with self.assertRaises(RuntimeError):self.switch.switch('op','staged','current',crash)
        with open(os.path.join(self.root,'current','file'),'wb') as f:f.write(b'changed')
        self.assertEqual('UNKNOWN',self.switch.reconcile('op')['state'])
    def test_symlink_target_and_hardlink_file_rejected(self):
        os.symlink('staged',os.path.join(self.root,'current'))
        with self.assertRaises(OSError):self.switch.switch('op','staged','current')
        os.unlink(os.path.join(self.root,'current'))
        os.link(os.path.join(self.root,'staged','file'),os.path.join(self.root,'staged','extra'))
        with self.assertRaises(PermissionError):self.switch.switch('op2','staged','current')
