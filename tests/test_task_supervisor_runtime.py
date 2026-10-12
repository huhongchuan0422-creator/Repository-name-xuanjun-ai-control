import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from task_supervisor import Supervisor
from task_supervisor_runtime import (admitted_ledger, acquire_lock,
                                     open_admitted_ledger, tick)
from task_supervisor_runtime_entry import REQUIRED, verify_release


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        os.chmod(self.directory.name, 0o700)
        self.path = os.path.join(self.directory.name, 'canonical.sqlite')
        self.now = time.time()
        self.s = Supervisor(self.path, clock=lambda: self.now)
        os.chmod(self.path, 0o600)
        st = os.stat(self.path)
        self.identity = '%d:%d' % (st.st_dev, st.st_ino)

    def tearDown(self):
        self.s.close()
        self.directory.cleanup()

    def register(self, role, base=None):
        base = self.now - 301 if base is None else base
        self.s.register(dict(task_id=role, parent_task_id='same-parent',
            stage='develop', owner=role, entry='WORK',
            checkpoint_sha256='a'*64, spec_sha256='b'*64,
            next_action='KEEP_OR_RECONCILE_SAME_TASK', dependencies=[],
            completion_conditions=['exact-artifact'],
            progress_deadline=base+2000, receipt_deadline=base+2000,
            started_deadline=base+2000, terminal_deadline=base+2000,
            handoff_deadline=base+2000), now=base)

    def run_tick(self):
        return tick(self.path, self.identity, self.path+'.supervisor.json',
                    now=self.now)

    def test_all_roles_and_workstreams_remain_visible(self):
        roles = ['Coordinator','Developer','QA','Security','Release',
                 'Work','CHATGPT','DOTS','P2','wake','continue','entry','review']
        for role in roles:
            self.register(role)
        report = self.run_tick()
        self.assertEqual(set(roles), {r['task_id'] for r in report['tasks']})
        self.assertEqual(len(roles), len(report['actions']))
        self.assertFalse(report['dispatch_performed'])
        self.assertEqual('CAPABILITY_UNAVAILABLE', report['provider'])
        self.assertEqual(3, len(report['source_sha256']))

    def test_restart_does_not_duplicate_recovery_events(self):
        self.register('Work')
        first = self.run_tick(); second = self.run_tick()
        self.assertEqual(1, len(first['pending_outbox']))
        self.assertEqual([], second['actions'])
        self.assertEqual(first['pending_outbox'], second['pending_outbox'])

    def test_snapshot_failure_preserves_durable_recovery_for_restart(self):
        self.register('Work')
        with mock.patch('task_supervisor_runtime.publish', side_effect=OSError()):
            with self.assertRaises(OSError):
                self.run_tick()
        report = self.run_tick()
        self.assertEqual(1, len(report['pending_outbox']))
        self.assertEqual([], report['actions'])

    def test_live_heartbeat_cannot_hide_terminal_deadline(self):
        self.register('Developer', self.now-100)
        deadlines = dict(progress_deadline=self.now+1000,
            receipt_deadline=self.now+1000, started_deadline=self.now+1000,
            terminal_deadline=self.now-1, handoff_deadline=self.now+1000)
        self.s.claim('Developer','attempt','Developer','WORK','run','session',
            'lease',1,1,now=self.now-100,deadlines=deadlines)
        self.s.record('Developer','attempt','start','STARTED',self.now-99)
        self.s.record('Developer','attempt','hb','HEARTBEAT',self.now)
        report = self.run_tick()
        self.assertEqual(1,len(report['actions']))
        row = self.s.db.execute('SELECT payload_json FROM outbox').fetchone()
        self.assertEqual('terminal_deadline',json.loads(row[0])['deadline_kind'])

    def test_unacknowledged_handoff_is_visible_and_not_closed(self):
        self.register('Release',self.now-500)
        self.s.claim('Release','attempt','Release','WORK','run','session',
                     'lease',1,1,now=self.now-500)
        self.s.record('Release','attempt','start','STARTED',self.now-499)
        self.s.record('Release','attempt','handoff','HANDOFF_REQUESTED',self.now-400)
        report = self.run_tick()
        self.assertEqual('HANDOFF_PENDING',report['tasks'][0]['state'])
        self.assertEqual('Release',report['tasks'][0]['owner'])
        self.assertTrue(report['pending_outbox'])

    def test_fifteen_minute_stall_survives_restart_as_visible_hold(self):
        self.register('DOTS',self.now-901)
        report=self.run_tick()
        self.assertEqual('HOLD',report['tasks'][0]['state'])
        self.assertEqual('HOLD',self.run_tick()['tasks'][0]['state'])
        self.assertEqual(1,len(self.run_tick()['pending_outbox']))

    def test_missing_ledger_never_creates_second_queue(self):
        missing=self.path+'.missing'
        with self.assertRaises(OSError):
            tick(missing,'0:0',missing+'.supervisor.json')
        self.assertFalse(os.path.exists(missing))

    def test_wrong_identity_has_no_events_or_snapshot(self):
        self.register('Work')
        with self.assertRaisesRegex(ValueError,'IDENTITY_CHANGED'):
            tick(self.path,'0:0',self.path+'.supervisor.json')
        self.assertEqual(0,self.s.db.execute('SELECT count(*) FROM events').fetchone()[0])
        self.assertFalse(os.path.exists(self.path+'.supervisor.json'))

    def test_path_swap_after_pinned_open_fails_before_mutation(self):
        self.register('Work')
        replacement = self.path + '.replacement'
        other = Supervisor(replacement); other.close(); os.chmod(replacement,0o600)
        original_open = open_admitted_ledger
        retained = self.path + '.retained'
        def swap(path, identity):
            fd, db, info = original_open(path, identity)
            os.rename(path, retained)
            os.rename(replacement, path)
            return fd, db, info
        with mock.patch('task_supervisor_runtime.open_admitted_ledger', side_effect=swap):
            with self.assertRaisesRegex(ValueError, 'IDENTITY_CHANGED'):
                self.run_tick()
        check = sqlite3.connect(self.path)
        self.assertEqual(0, check.execute('SELECT count(*) FROM events').fetchone()[0])
        check.close()
        check = sqlite3.connect(retained)
        self.assertEqual(0, check.execute('SELECT count(*) FROM events').fetchone()[0])
        check.close()

    def test_pinned_open_is_existing_only(self):
        missing=self.path+'.missing'
        with self.assertRaises(OSError):
            open_admitted_ledger(missing,'0:0')
        self.assertFalse(os.path.exists(missing))

    def test_foreign_schema_is_not_migrated(self):
        path=os.path.join(self.directory.name,'other.sqlite')
        db=sqlite3.connect(path)
        db.execute('CREATE TABLE original(value TEXT)');db.commit();db.close()
        os.chmod(path,0o600);st=os.stat(path)
        with self.assertRaisesRegex(ValueError,'SCHEMA_MAPPING_REQUIRED'):
            admitted_ledger(path,'%d:%d'%(st.st_dev,st.st_ino))
        db=sqlite3.connect(path)
        self.assertEqual([('original',)],db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
        db.close()

    def test_symlink_ledger_rejected(self):
        path=self.path+'.link';os.symlink(self.path,path)
        with self.assertRaises((ValueError,OSError)):
            admitted_ledger(path,self.identity)

    def test_insecure_directory_rejected(self):
        os.chmod(self.directory.name,0o755)
        with self.assertRaisesRegex(ValueError,'PRIVATE_LEDGER_DIRECTORY'):
            self.run_tick()

    def test_competing_tick_cannot_acquire_lock(self):
        lock=acquire_lock(self.path+'.supervisor.lock')
        try:
            with self.assertRaises(BlockingIOError): self.run_tick()
        finally: os.close(lock)

    def test_symlink_snapshot_never_overwrites_target(self):
        target=self.path+'.target'
        with open(target,'w') as f:f.write('retained')
        os.chmod(target,0o600)
        os.symlink(target,self.path+'.supervisor.json')
        with self.assertRaisesRegex(ValueError,'UNSAFE_SNAPSHOT'):
            self.run_tick()
        with open(target) as f:self.assertEqual('retained',f.read())

    def test_atomic_snapshot_is_private_and_complete(self):
        report=self.run_tick()
        with open(self.path+'.supervisor.json') as f:
            self.assertEqual(report,json.load(f))
        self.assertEqual(0o600,os.stat(self.path+'.supervisor.json').st_mode&0o777)


class ReleaseManifestTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(); self.root=self.directory.name
        os.chmod(self.root,0o755)
        os.makedirs(os.path.join(self.root,'scripts'))
        self.files={}
        for name in REQUIRED:
            path=os.path.join(self.root,name)
            with open(path,'wb') as stream: stream.write(name.encode('ascii'))
            os.chmod(path,0o644)
            self.files[name]=hashlib.sha256(name.encode('ascii')).hexdigest()
        self.manifest=os.path.join(self.root,'manifest.json')
        raw=json.dumps({'schema':1,'files':self.files},sort_keys=True).encode('utf-8')
        with open(self.manifest,'wb') as stream: stream.write(raw)
        os.chmod(self.manifest,0o644); self.digest=hashlib.sha256(raw).hexdigest()

    def tearDown(self): self.directory.cleanup()

    def test_exact_manifest_accepts_release(self):
        entry=os.path.join(self.root,'scripts','task_supervisor_runtime_entry.py')
        old=__import__('task_supervisor_runtime_entry').__file__
        with mock.patch('task_supervisor_runtime_entry.__file__',entry):
            root, contents=verify_release(self.manifest,self.digest,
                                          trusted_uid=os.geteuid())
            self.assertEqual(self.root,root)
            self.assertEqual(set(REQUIRED),set(contents))

    def test_changed_source_fails_closed(self):
        with open(os.path.join(self.root,REQUIRED[0]),'ab') as stream: stream.write(b'x')
        entry=os.path.join(self.root,'scripts','task_supervisor_runtime_entry.py')
        with mock.patch('task_supervisor_runtime_entry.__file__',entry):
            with self.assertRaisesRegex(ValueError,'SOURCE_DIGEST'):
                verify_release(self.manifest,self.digest,trusted_uid=os.geteuid())

    def test_changed_manifest_fails_closed(self):
        entry=os.path.join(self.root,'scripts','task_supervisor_runtime_entry.py')
        with mock.patch('task_supervisor_runtime_entry.__file__',entry):
            with self.assertRaisesRegex(ValueError,'MANIFEST_DIGEST'):
                verify_release(self.manifest,'0'*64,trusted_uid=os.geteuid())

    def test_writable_scripts_directory_fails_closed(self):
        os.chmod(os.path.join(self.root,'scripts'),0o777)
        entry=os.path.join(self.root,'scripts','task_supervisor_runtime_entry.py')
        with mock.patch('task_supervisor_runtime_entry.__file__',entry):
            with self.assertRaisesRegex(ValueError,'RELEASE_DIRECTORY'):
                verify_release(self.manifest,self.digest,trusted_uid=os.geteuid())

    def test_bytecode_cache_fails_closed(self):
        os.mkdir(os.path.join(self.root,'scripts','__pycache__'))
        entry=os.path.join(self.root,'scripts','task_supervisor_runtime_entry.py')
        with mock.patch('task_supervisor_runtime_entry.__file__',entry):
            with self.assertRaisesRegex(ValueError,'BYTECODE_CACHE'):
                verify_release(self.manifest,self.digest,trusted_uid=os.geteuid())


if __name__=='__main__':
    unittest.main()
