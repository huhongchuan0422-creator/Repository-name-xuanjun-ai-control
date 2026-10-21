"""Linux temporary application DB fixtures only; no site CP12/13 acceptance."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('b6', str(ROOT / 'production/p2_install/b6_persistence.py'))
b6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b6)
Ledger, Activation = b6.application_contract()


def writer(req):
    db = req['db_path']
    anchor = sqlite3.connect(db)
    anchor.execute('PRAGMA journal_mode=WAL')
    anchor.execute('PRAGMA wal_autocheckpoint=0')
    store = Activation(**req['activation'])
    app = Ledger(db, ['fixture/repo'], activation_store=store)
    with app._transaction() as conn:
        conn.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)",
                     ('fixture-task', 'CODEX_EXEC', 'WAITING_HUMAN', '[]', None, None, 7,
                      '{"effect":"UNKNOWN","resume":"READBACK_FIRST"}', 123.0))
        app._event(conn, 'fixture-task', 'FIXTURE_WRITE', 123.0, {'effect': 'UNKNOWN'})
    anchor.execute('PRAGMA journal_mode=WAL')
    anchor.execute("INSERT INTO events(task_id,event,created,details) VALUES(?,?,?,?)",
                   ('fixture-task','FIXTURE_WAL_ANCHOR',124.0,'{}'))
    anchor.commit()
    print('WAL_READY', flush=True)
    # Keep the real WAL connection open until parent SIGKILL; no clean close.
    signal.pause()


class Persistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p2-b6-test-')
        self.root = Path(self.tmp.name)
        os.chmod(self.root, 0o700)
        self.prior = self.root / 'B1-B5-receipt'
        self.prior.write_bytes(b'prior batch immutable fixture')
        self.before = self.prior.read_bytes()
        db = self.root / 'application.sqlite3'
        conn = sqlite3.connect(str(db))
        # Fixture schema from original application contract, not a new business DB.
        for table, columns in Ledger.SCHEMAS.items():
            conn.execute('CREATE TABLE '+table+' ('+','.join(
                name+' '+kind+(' PRIMARY KEY' if pk else '') for name,kind,pk in columns)+')')
        conn.commit()
        conn.close()
        os.chmod(db, 0o600)
        a = self.root / 'activation'
        a.mkdir(mode=0o700)
        args = dict(descriptor=str(a/'active.json'), epoch_journal=str(a/'epochs.jsonl'),
                    lock_path=str(a/'activation.lock'), owner_uid=os.geteuid())
        store = Activation(**args)
        v = store.prepare('1'*64, '2'*64, '3'*64, '11111111-1111-4111-8111-111111111111',
                          1, '22222222-2222-4222-8222-222222222222', str(db), str(self.root/'app.sock'))
        store.transition('PREPARED', 'QUIESCED', v['epoch'], v['instance'],
                         {k:True for k in ('identity_verified','coordinator_inactive','parent_unit_inactive',
                                          'cgroups_empty','restart_inhibited')})
        active = store.transition('QUIESCED', 'ACTIVE', v['epoch'], v['instance'], {'database_reopened':True})
        self.req = dict(scope='ISOLATED_TEST_ONLY', profile='B6_EXISTING_APPLICATION_DATABASE_OBSERVATION',
                        root=str(self.root), db_path=str(db), uid=os.geteuid(), gid=os.getegid(),
                        activation=args, expected=active, task_ids=['fixture-task'])
        proc = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--writer',
                                 json.dumps(self.req)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
        try:
            import select
            self.assertTrue(select.select([proc.stdout], [], [], 10)[0], 'writer deadline')
            self.assertEqual(proc.stdout.readline().strip(), 'WAL_READY')
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
            proc.stdout.close()
            proc.stderr.close()
        self.assertEqual(proc.returncode, -signal.SIGKILL)
        self.wal = Path(str(db)+'-wal')
        self.assertGreater(self.wal.stat().st_size, 32)
        self.db_hash = hashlib.sha256(db.read_bytes()).hexdigest()
        self.wal_hash = hashlib.sha256(self.wal.read_bytes()).hexdigest()

    def tearDown(self):
        self.assertEqual(self.prior.read_bytes(), self.before)
        self.tmp.cleanup()

    def test_nonempty_wal_cross_process_readback(self):
        # Main-only immutable view is TEST FIXTURE proof: the marker lives only in WAL.
        main = self.root/'fixture-main-only.sqlite3'
        main.write_bytes(Path(self.req['db_path']).read_bytes())
        with sqlite3.connect('file:'+str(main)+'?immutable=1', uri=True) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM events WHERE event='FIXTURE_WAL_ANCHOR'").fetchone()[0], 0)
        for stage in ('CP12','CP13'):
            p = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--observe',
                                json.dumps(self.req), stage], capture_output=True, text=True, timeout=10)
            self.assertEqual(p.returncode, 0, p.stderr)
            v = json.loads(p.stdout)
            self.assertEqual(v['status'], 'OBSERVED', v)
            self.assertEqual(v['task_rows'][0]['fence'], 7)
            self.assertEqual(json.loads(v['task_rows'][0]['checkpoint'])['effect'], 'UNKNOWN')
            self.assertTrue(any(row['event']=='FIXTURE_WAL_ANCHOR' for row in v['event_rows']))
            self.assertFalse(v['site_complete'])
            self.assertEqual(hashlib.sha256(Path(self.req['db_path']).read_bytes()).hexdigest(), self.db_hash)
            self.assertEqual(hashlib.sha256(self.wal.read_bytes()).hexdigest(), self.wal_hash)

    def test_unknown_reconciles_without_replay(self):
        v = b6.observe_database_evidence(self.req, 'CP12', 'UNKNOWN')
        self.assertEqual(v['status'], 'RECONCILED_READBACK', v)
        self.assertFalse(v['replay_performed'])
        self.assertEqual(hashlib.sha256(self.wal.read_bytes()).hexdigest(), self.wal_hash)

    def test_missing_does_not_create(self):
        original = Path(self.req['db_path'])
        original.rename(self.root/'fixture-retained-main.sqlite3')
        v = b6.observe_database_evidence(self.req, 'CP12')
        self.assertEqual(v['status'], 'HOLD', v)
        self.assertEqual(v['error']['type'], 'FileNotFoundError')
        self.assertFalse(original.exists())
        self.assertTrue(self.wal.exists())

    def test_schema_rejected_no_rebuild(self):
        conn = sqlite3.connect(self.req['db_path'])
        conn.execute('ALTER TABLE tasks ADD COLUMN invalid TEXT')
        conn.commit()
        conn.close()
        v = b6.observe_database_evidence(self.req, 'CP12')
        self.assertEqual(v['status'], 'HOLD', v)
        self.assertEqual(v['error']['type'], 'SchemaMismatch')

    def test_identity_and_subject_rejected(self):
        for change in ('generation','uid','db_path'):
            req = copy.deepcopy(self.req)
            if change == 'generation':req['expected'][change] += 1
            elif change == 'uid':req[change] += 1
            else:req[change] = '/tmp/outside.sqlite3'
            self.assertEqual(b6.observe_database_evidence(req,'CP12')['status'], 'HOLD')

    def test_preparation_profile_not_runtime(self):
        req = copy.deepcopy(self.req)
        req['profile'] = 'ISOLATED_NEW_PREPARE_ONLY'
        self.assertEqual(b6.observe_database_evidence(req,'CP13')['status'], 'HOLD')

    def test_original_active_guard_not_bypassed(self):
        store = Activation(**self.req['activation'])
        # Test fixture only: preserve native fence transition rather than fake store.
        v = store.fence(self.req['expected']['epoch'], self.req['expected']['instance'])
        req = copy.deepcopy(self.req)
        req['expected'] = v
        self.assertEqual(b6.observe_database_evidence(req,'CP12')['status'], 'OBSERVED')
        self.assertEqual(b6.observe_database_evidence(req,'CP13')['status'], 'HOLD')

    def test_symlink_db_or_wal_rejected(self):
        target = self.root/'alias.sqlite3'
        target.symlink_to(self.req['db_path'])
        req = copy.deepcopy(self.req)
        req['db_path'] = str(target)
        self.assertEqual(b6.observe_database_evidence(req,'CP12')['status'], 'HOLD')
        # Preserve WAL fixture bytes while testing a malicious alternate pathname.
        other = self.root/'other'
        other.write_bytes(b'not a wal')
        self.wal.rename(str(self.wal)+'.retained')
        self.wal.symlink_to(other)
        self.assertEqual(b6.observe_database_evidence(self.req,'CP12')['status'], 'HOLD')


    def test_b6_prepared_does_not_advance_or_activate(self):
        store = Activation(**self.req['activation'])
        state = store.fence(self.req['expected']['epoch'], self.req['expected']['instance'])
        req = copy.deepcopy(self.req)
        req['expected'] = state
        before = Path(req['activation']['descriptor']).read_bytes()
        for stage in ('CP12','CP13'):
            value = b6.observe(req, stage)
            self.assertEqual(value['status'], 'HOLD', value)
            self.assertFalse(value['phase_complete'])
            self.assertEqual(value['error']['code'], 'B6_REQUIRES_QUIESCED_NOT_PREPARED_OR_ACTIVE')
        self.assertEqual(Path(req['activation']['descriptor']).read_bytes(), before)
        self.assertEqual(store.read()['state'], 'PREPARED')

    def test_b6_quiesced_without_access_contract_holds(self):
        store = Activation(**self.req['activation'])
        state = store.fence(self.req['expected']['epoch'], self.req['expected']['instance'])
        state = store.transition('PREPARED','QUIESCED',state['epoch'],state['instance'],
                                {k:True for k in ('identity_verified','coordinator_inactive',
                                 'parent_unit_inactive','cgroups_empty','restart_inhibited')})
        req = copy.deepcopy(self.req)
        req['expected'] = state
        before = Path(req['activation']['descriptor']).read_bytes()
        for stage in ('CP12','CP13'):
            value = b6.observe(req, stage, 'UNKNOWN')
            self.assertEqual(value['status'], 'HOLD', value)
            self.assertEqual(value['database_evidence']['status'], 'RECONCILED_READBACK')
            self.assertFalse(value['activation_performed'])
            self.assertIn('CONTRACT_UNAVAILABLE', value['error']['code'])
        self.assertEqual(Path(req['activation']['descriptor']).read_bytes(), before)
        self.assertEqual(hashlib.sha256(self.wal.read_bytes()).hexdigest(), self.wal_hash)
        self.assertEqual(store.read()['state'], 'QUIESCED')

    def test_active_observation_not_preactivation_cp13(self):
        self.assertEqual(b6.observe_database_evidence(self.req,'CP13')['status'],'OBSERVED')
        value = b6.observe(self.req,'CP13')
        self.assertEqual(value['status'],'HOLD')
        self.assertFalse(value['phase_complete'])

    def test_hand_filled_access_pass_rejected(self):
        req = copy.deepcopy(self.req)
        req['runtime_access'] = {'status':'PASS','database':'REOPENED'}
        value = b6.observe(req,'CP13')
        self.assertEqual(value['status'],'HOLD')
        self.assertEqual(value['error']['code'],'REQUEST_FIELDS')


if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--writer':
        writer(json.loads(sys.argv[2]))
    elif len(sys.argv)>1 and sys.argv[1]=='--observe':
        print(json.dumps(b6.observe_database_evidence(json.loads(sys.argv[2]),sys.argv[3]),sort_keys=True))
    else:
        unittest.main()
