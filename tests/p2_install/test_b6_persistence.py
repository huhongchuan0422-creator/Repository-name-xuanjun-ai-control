"""Linux temporary application DB fixtures only; no site CP12/13 acceptance."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
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


class PreparationBinding(unittest.TestCase):
    """Original B3 documents/consumer, temporary retained history, no dispatch.

    CP08 is a labelled historical fixture record, NOT a new independent denial
    proof. Its pinned chain tests consumption, not historical authenticity.
    """
    def setUp(self):
        from production.p2_install import b3_ledger as b3
        self.b3 = b3
        self.tmp = tempfile.TemporaryDirectory(prefix='p2-b3-test-')
        self.root = Path(self.tmp.name)/'b3-initialize'
        self.root.mkdir(mode=0o700)
        for name in ('activation', 'data', 'run', 'prepared'):
            (self.root/name).mkdir(mode=0o700)
        self.args = dict(descriptor=str(self.root/'activation/active.json'),
                         epoch_journal=str(self.root/'activation/epochs.jsonl'),
                         lock_path=str(self.root/'activation/activation.lock'), owner_uid=os.geteuid())
        self.store = Activation(**self.args)
        # Hosted setup-python may expose group-writable interpreter metadata.
        # Preserve it; provision only a byte-identical protected fixture copy.
        binary = self.root.parent/'fixture-python'
        shutil.copyfile(os.path.realpath(sys.executable), binary)
        binary.chmod(0o500)
        binary_sha = b3.sha(binary.read_bytes())
        binding = dict(installation_id='fixture-original-b3', batch_id='b3-initialize',
                       attempt_id='fixture-a1', origin='ISOLATED_NEW', scope='ISOLATED_TEST_ONLY',
                       initial_state='PREPARED', initial_epoch=1, generation=1,
                       release_manifest_sha256='a'*64, instance='22222222-2222-4222-8222-222222222222',
                       ledger_uuid='11111111-1111-4111-8111-111111111111',
                       db_path=str(self.root/'data/ledger.sqlite3'), ledger_socket=str(self.root/'run/ledger.sock'),
                       start_services=False, create_database=False, bind_socket=False)
        self.put(self.root/'binding-config.json', binding)
        initial = self.store.prepare('a'*64, b3.sha(b3.encode(binding)), binary_sha,
                                     binding['ledger_uuid'], 1, binding['instance'],
                                     binding['db_path'], binding['ledger_socket'])
        cp03 = dict(schema=1, scope='ISOLATED_TEST_ONLY', origin='ISOLATED_NEW', status='COMMITTED',
                    installation_id=binding['installation_id'], batch_id='b3-initialize', attempt_id='fixture-a1',
                    request_sha256='f'*64, config_sha256=b3.sha(b3.encode(binding)),
                    descriptor_head_sha256=self.store.head(initial),
                    descriptor_file_sha256=b3.sha(Path(self.args['descriptor']).read_bytes()),
                    journal_sha256=b3.sha(Path(self.args['epoch_journal']).read_bytes()),
                    binary_sha256=binary_sha, full_b3_complete=False,
                    database='RESERVED_NOT_CREATED', socket='RESERVED_NOT_BOUND')
        self.put(self.root/'commit-receipt.json', cp03)
        cp03_sha = b3.sha(b3.encode(cp03))
        app = b6.SOURCE_ROOT
        req = dict(schema=1, scope='ISOLATED_TEST_ONLY', root=str(self.root), application=str(app),
                   binary=dict(path=str(binary), bytes=binary.stat().st_size, sha256=binary_sha),
                   sources={n:b3.sha((app/n).read_bytes()) for n in b3.NAMES},
                   operation_id='fixture-b3-original-format', cp03_receipt_sha256=cp03_sha)
        expected = {k:(binding['installation_id'] if k == 'installation_id' else initial[k]) for k in
                    ('installation_id','instance','ledger_uuid','generation','release_sha256',
                     'config_sha256','binary_sha256','db_path','ledger_socket')}
        cfg, profile, invocation, check, identity = b3.documents(req, expected)
        files = dict(zip(('ledger-config.json','profile.json','runtime-invocation.json','expected-identity.json'),
                         (cfg,profile,invocation,identity)))
        for name, value in files.items():
            self.put(self.root/'prepared'/name, value)
        # Real original non-starting config consumer only, no dispatch/identity
        # re-run and no application server. Historical state is still PREPARED.
        fixture_env = dict(os.environ, PYTHONHOME=sys.prefix,
                           LD_LIBRARY_PATH=str(Path(sys.prefix)/'lib'))
        check_result = subprocess.run(check, env=fixture_env, capture_output=True, text=True, timeout=10)
        self.assertEqual(check_result.returncode, 0, check_result.stderr)
        consumer = json.loads(check_result.stdout)
        self.assertEqual(consumer['status'], 'PREPARED_CONFIG_VALIDATED')
        self.request_sha = b3.sha(b3.encode(req))
        self.put(self.root/'prepared/intent.json', dict(request_sha256=self.request_sha, request=req))
        self.evidence = {
            'CP04':dict(status='VALIDATED', scope='NEW_PREPARED_NO_RUNTIME_OBJECTS',
                        cp03_receipt_sha256=cp03_sha, old_instance_stopped='NOT_CLAIMED'),
            'CP05':dict(status='VALIDATED', consumer=consumer, invocation_sha256=b3.sha(b3.encode(invocation))),
            'CP06':dict(status='VALIDATED', identity_sha256=b3.sha(b3.encode(identity)),
                        process_identity='NOT_STARTED', start_role_handoff='NOT_READY'),
            'CP07':dict(status='VALIDATED', subject_uid=os.geteuid(), private_root=str(self.root/'prepared'),
                        access=dict(authorized_access='PASS', unauthorized_denial='NOT_EXECUTED'),
                        files={n:b3.sha(b3.encode(v)) for n,v in files.items()}, service_uid='UNKNOWN',
                        callback_uid=1004, runtime_roles_granted_access=False),
            'CP08':dict(status='VALIDATED', denial=dict(status='PASS',uid=65534,gid=65534,operation='OPEN_DIRECTORY',
                                    scope='EXACT_PATH_ONLY'),
                        scope='PREPARATION_HANDOFF_DIRECTORY_ONLY'),
            'CP09':dict(status='VALIDATED', tls=consumer['tls'], global_p2_tls='NOT_CLAIMED')}
        self.anchors = dict(cp03_receipt_sha256=cp03_sha, preparation_receipt_sha256='')
        self.rechain()
        # DB schema exists ONLY as temporary test fixture; no activation or
        # production schema creation by the B6 adapter.
        with sqlite3.connect(binding['db_path']) as conn:
            for table, columns in Ledger.SCHEMAS.items():
                conn.execute('CREATE TABLE '+table+' ('+','.join(
                    n+' '+t+(' PRIMARY KEY' if pk else '') for n,t,pk in columns)+')')
            conn.execute('CREATE TABLE execution_specs (task_id TEXT PRIMARY KEY REFERENCES tasks(id), '
                         'spec TEXT NOT NULL, revision INTEGER NOT NULL, hash TEXT NOT NULL)')
            conn.execute('CREATE TABLE worker_heartbeats (worker_id TEXT NOT NULL, '
                         'task_id TEXT PRIMARY KEY REFERENCES tasks(id), fence INTEGER NOT NULL, '
                         'seen_at REAL NOT NULL, phase TEXT NOT NULL)')
        os.chmod(binding['db_path'], 0o600)
        self.store.transition('PREPARED','QUIESCED',1,initial['instance'],
                              {k:True for k in ('identity_verified','coordinator_inactive','parent_unit_inactive',
                                               'cgroups_empty','restart_inhibited')})
        self.req = dict(scope='ISOLATED_TEST_ONLY', profile='B6_EXISTING_APPLICATION_DATABASE_OBSERVATION',
                        root=str(self.root), db_path=binding['db_path'], uid=os.geteuid(), gid=os.getegid(),
                        activation=self.args, task_ids=[])
        self.snapshot = {str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def put(self, path, value):
        if path.exists():
            path.chmod(0o600)  # deliberate mutation of this temporary fixture only
        path.write_bytes(self.b3.encode(value))
        path.chmod(0o400)

    def rechain(self):
        previous = self.anchors['cp03_receipt_sha256']
        for stage in self.b3.STAGES:
            value = dict(schema=1, scope='ISOLATED_TEST_ONLY', stage=stage,
                         status='PREPARATION_CHECKPOINT_COMMITTED', request_sha256=self.request_sha,
                         previous_receipt_sha256=previous, evidence=self.evidence[stage])
            path = self.root/'prepared'/(stage+'-committed.json')
            self.put(path, value)
            previous = self.b3.sha(path.read_bytes())
        final = dict(schema=1, scope='ISOLATED_TEST_ONLY', status='PREPARATION_COMMITTED',
                     request_sha256=self.request_sha, last_checkpoint_sha256=previous,
                     service_started=False, production_permission=False, full_b3_complete=False)
        path = self.root/'prepared/preparation-receipt.json'
        self.put(path, final)
        self.anchors['preparation_receipt_sha256'] = self.b3.sha(path.read_bytes())

    def tearDown(self):
        self.tmp.cleanup()

    def call(self):
        return b6.observe_prepared(self.req, self.anchors, 'CP13', 'UNKNOWN')

    def rejected(self):
        value = self.call()
        self.assertEqual(value['status'], 'HOLD', value)
        self.assertNotIn('preparation_evidence', value, value)
        self.assertFalse(value['phase_complete'])
        return value

    def test_original_format_positive_binding_and_separate_process(self):
        value = self.call()
        self.assertEqual(value['preparation_evidence']['status'], 'BOUND_HISTORY_ONLY', value)
        self.assertEqual(value['preparation_evidence']['historical_state'], 'PREPARED')
        self.assertEqual(value['preparation_evidence']['current_state'], 'QUIESCED')
        self.assertEqual(value['preparation_evidence']['roles']['service_uid'], 'UNKNOWN')
        self.assertFalse(value['preparation_evidence']['runtime_roles_granted_access'])
        self.assertEqual(value['database_evidence']['status'], 'RECONCILED_READBACK')
        self.assertEqual(value['status'], 'HOLD')
        p = subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--prepared',
                            json.dumps(self.req),json.dumps(self.anchors)], capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['preparation_evidence']['identity'],
                         value['preparation_evidence']['identity'])
        for path, raw in self.snapshot.items():
            self.assertEqual(Path(path).read_bytes(),raw)

    def test_original_two_link_publication_is_readable(self):
        # Original publish intentionally retains .pending and terminal links.
        for path in (self.root/'commit-receipt.json',
                     self.root/'prepared/preparation-receipt.json',
                     self.root/'prepared/CP07-committed.json'):
            os.link(path, path.parent/('.'+path.name+'.pending-fixture'))
        self.assertEqual(self.call()['preparation_evidence']['status'],'BOUND_HISTORY_ONLY')

    def test_tampered_source_and_wrong_version(self):
        path = self.root/'prepared/ledger-config.json'
        cfg = json.loads(path.read_bytes()); cfg['source_commit'] = '0'*40
        self.put(path,cfg)
        self.evidence['CP07']['files']['ledger-config.json'] = self.b3.sha(path.read_bytes())
        self.rechain()
        self.assertEqual(self.rejected()['error']['code'],'HISTORY_DOCUMENT_CONFLICT')

    def test_broken_checkpoint_chain(self):
        path = self.root/'prepared/CP06-committed.json'
        value = json.loads(path.read_bytes());value['previous_receipt_sha256'] = '0'*64
        self.put(path,value)
        self.rejected()

    def test_missing_original_and_untrusted_anchor(self):
        path = self.root/'prepared/expected-identity.json'
        path.unlink()
        self.assertEqual(self.rejected()['error']['type'],'FileNotFoundError')
        self.anchors['preparation_receipt_sha256'] = '0'*64
        self.rejected()

    def test_alien_instance_and_generation(self):
        path = self.root/'prepared/expected-identity.json'
        original = json.loads(path.read_bytes())
        for key, value in [('instance','33333333-3333-4333-8333-333333333333'),('generation',2)]:
            changed = copy.deepcopy(original);changed['expected'][key] = value
            self.put(path,changed)
            # Even reanchoring later checkpoints cannot make a contradictory
            # identity document match the original CP03/native journal.
            pin = self.b3.sha(path.read_bytes())
            self.evidence['CP06']['identity_sha256'] = pin
            self.evidence['CP07']['files']['expected-identity.json'] = pin
            self.rechain()
            self.assertEqual(self.rejected()['error']['code'],'HISTORY_DOCUMENT_CONFLICT')

    def test_path_escape_and_symlink_parent(self):
        self.req['db_path'] = str(self.root.parent/'escaped.sqlite3')
        self.assertEqual(self.rejected()['error']['code'],'HISTORY_RESERVED_PATHS')
        self.req['db_path'] = str(self.root/'data/ledger.sqlite3')
        folder = self.root/'prepared'; retained = self.root/'retained-prepared'
        folder.rename(retained);folder.symlink_to(retained,target_is_directory=True)
        self.rejected()

    def test_prepared_and_active_are_not_current_quiesced(self):
        # Native fence makes a new PREPARED epoch; no hand-built descriptor.
        current = self.store.read()
        fenced = self.store.fence(current['epoch'],current['instance'])
        self.assertEqual(self.rejected()['error']['code'],'HISTORY_CURRENT_QUIESCED_IDENTITY')
        self.store.transition('PREPARED','QUIESCED',fenced['epoch'],fenced['instance'],
                              {k:True for k in ('identity_verified','coordinator_inactive','parent_unit_inactive',
                                               'cgroups_empty','restart_inhibited')})
        # Test only: ACTIVE rejection independently proves no early B7 credit.
        self.store.transition('QUIESCED','ACTIVE',fenced['epoch'],fenced['instance'],dict(database_reopened=True))
        self.rejected()

    def test_descriptor_journal_drift(self):
        path = Path(self.args['descriptor'])
        value = json.loads(path.read_bytes());value['state'] = 'ACTIVE'
        self.put(path,value)
        self.assertEqual(self.rejected()['error']['type'],'ActivationError')

    def test_hand_expected_or_pass_not_an_input(self):
        self.req['expected'] = self.store.read()
        self.assertEqual(self.rejected()['error']['code'],'BOUND_REQUEST_FIELDS')
        del self.req['expected']
        self.req['runtime_access'] = dict(status='PASS')
        self.rejected()


    def test_history_ignores_runtime_directory_owner_but_observer_refuses_it(self):
        # Metadata contract fixture only: NO chown/setuid/permission changes.
        # Actual multi-UID filesystem access remains NOT_EXECUTED.
        actual_lstat = os.lstat
        runtime_paths = {self.root/'data', self.root/'run', Path(self.req['db_path'])}
        foreign_uid = os.geteuid()+1
        def runtime_metadata(path, *args, **kwargs):
            info = actual_lstat(path, *args, **kwargs)
            if Path(path) in runtime_paths:
                value = {k:getattr(info,k) for k in dir(info) if k.startswith('st_')}
                value['st_uid'] = foreign_uid
                return SimpleNamespace(**value)
            return info
        with patch.object(b6.os,'lstat',side_effect=runtime_metadata):
            value = self.call()
        self.assertIn('preparation_evidence',value,value)
        self.assertEqual(value['preparation_evidence']['status'],'BOUND_HISTORY_ONLY',value)
        self.assertEqual(value['database_evidence']['status'],'HOLD',value)
        self.assertFalse(value['phase_complete'])
        self.assertFalse(value['preparation_evidence']['runtime_roles_granted_access'])

    def test_history_owner_is_not_inferred_from_reader(self):
        # Identity branch fixture only, not an actual cross-UID OS execution.
        owner_uid = os.geteuid()
        req = copy.deepcopy(self.req)
        req['uid'] += 1;req['gid'] += 1
        with patch.object(b6.os,'geteuid',return_value=req['uid']), \
             patch.object(b6.os,'getegid',return_value=req['gid']):
            value = b6.observe_prepared(req,self.anchors,'CP13')
        self.assertIn('preparation_evidence',value,value)
        self.assertEqual(value['preparation_evidence']['history_owner_uid'],owner_uid,value)
        self.assertEqual(value['preparation_evidence']['reader'],dict(uid=req['uid'],gid=req['gid']))
        self.assertEqual(value['database_evidence']['status'],'HOLD',value)
        self.assertFalse(value['phase_complete'])


    def test_history_wrong_file_owner_is_still_refused(self):
        original = os.lstat
        target = self.root/'prepared/expected-identity.json'
        def wrong_owner(path,*args,**kwargs):
            info = original(path,*args,**kwargs)
            if Path(path) == target:
                value = {k:getattr(info,k) for k in dir(info) if k.startswith('st_')}
                value['st_uid'] += 1
                return SimpleNamespace(**value)
            return info
        with patch.object(b6.os,'lstat',side_effect=wrong_owner):
            value = self.rejected()
        self.assertEqual(value['error']['code'],'HISTORY_FILE_OWNER')

    def test_history_wrong_directory_owner_is_still_refused(self):
        original = os.lstat
        def wrong_owner(path,*args,**kwargs):
            info = original(path,*args,**kwargs)
            if Path(path) == self.root/'prepared':
                value = {k:getattr(info,k) for k in dir(info) if k.startswith('st_')}
                value['st_uid'] += 1
                return SimpleNamespace(**value)
            return info
        with patch.object(b6.os,'lstat',side_effect=wrong_owner):
            value = self.rejected()
        self.assertEqual(value['error']['code'],'HISTORY_DIRECTORY_PROTECTION')

    def test_history_same_bytes_new_inode_during_pinned_read_refused(self):
        from production.p2_install import b3_contracts
        original = b3_contracts.pinned_file
        target = self.root/'prepared/ledger-config.json'
        replaced = []
        def swapped(path,pin,limit=1048576):
            raw = original(path,pin,limit)
            if Path(path) == target and not replaced:
                retained = target.parent/'fixture-before-read-swap.json'
                # Preserve original fixture file and its bytes; no real input.
                target.rename(retained)
                target.write_bytes(raw);target.chmod(0o400)
                replaced.append(retained)
            return raw
        with patch.object(b3_contracts,'pinned_file',side_effect=swapped):
            value = self.rejected()
        self.assertTrue(replaced)
        self.assertEqual(value['error']['code'],'HISTORY_PATH_CHANGED')

    def test_history_same_bytes_new_inode_between_rechecks_refused(self):
        from production.p2_install import b3_contracts
        original = b3_contracts.pinned_file
        target = self.root/'prepared/ledger-config.json'
        replaced = []
        def swapped(path,pin,limit=1048576):
            raw = original(path,pin,limit)
            if Path(path).name == 'fixture-python' and not replaced:
                retained = target.parent/'fixture-before-recheck-swap.json'
                target.rename(retained)
                target.write_bytes(retained.read_bytes());target.chmod(0o400)
                replaced.append(retained)
            return raw
        with patch.object(b3_contracts,'pinned_file',side_effect=swapped):
            value = self.rejected()
        self.assertTrue(replaced)
        self.assertEqual(value['error']['code'],'HISTORY_FILE_IDENTITY_CHANGED')

    def test_database_same_name_new_inode_is_still_refused(self):
        original = sqlite3.connect
        target = Path(self.req['db_path'])
        replaced = []
        def swapped(*args,**kwargs):
            conn = original(*args,**kwargs)
            if not replaced:
                retained = target.parent/'fixture-original-inode.sqlite3'
                target.rename(retained)
                shutil.copyfile(retained,target);target.chmod(0o600)
                replaced.append(retained)
            return conn
        with patch.object(b6.sqlite3,'connect',side_effect=swapped):
            value = self.call()
        self.assertEqual(value['preparation_evidence']['status'],'BOUND_HISTORY_ONLY',value)
        self.assertEqual(value['database_evidence']['status'],'HOLD',value)
        self.assertEqual(value['database_evidence']['error']['code'],'DATABASE_PATH_CHANGED',value)
        self.assertFalse(value['phase_complete'])

    def test_activation_drift_after_bound_history_is_refused(self):
        original = b6.observe
        def drift(*args,**kwargs):
            result = original(*args,**kwargs)
            current = self.store.read()
            # Real native transition in a temporary fixture, not a fake store.
            self.store.fence(current['epoch'],current['instance'])
            return result
        with patch.object(b6,'observe',side_effect=drift):
            value = self.rejected()
        self.assertEqual(value['error']['code'],'HISTORY_ACTIVATION_DRIFT')


    def test_run_owner_guard_moved_to_database_observation_not_removed(self):
        original = os.lstat
        def wrong_owner(path,*args,**kwargs):
            info = original(path,*args,**kwargs)
            if Path(path) == self.root/'run':
                value = {k:getattr(info,k) for k in dir(info) if k.startswith('st_')}
                value['st_uid'] += 1
                return SimpleNamespace(**value)
            return info
        with patch.object(b6.os,'lstat',side_effect=wrong_owner):
            value = self.call()
        self.assertEqual(value['preparation_evidence']['status'],'BOUND_HISTORY_ONLY',value)
        self.assertEqual(value['database_evidence']['status'],'HOLD',value)
        self.assertEqual(value['database_evidence']['error']['code'],'RUNTIME_DIRECTORY_PROTECTION',value)
        self.assertFalse(value['phase_complete'])


if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--writer':
        writer(json.loads(sys.argv[2]))
    elif len(sys.argv)>1 and sys.argv[1]=='--prepared':
        print(json.dumps(b6.observe_prepared(json.loads(sys.argv[2]),json.loads(sys.argv[3]),'CP13','UNKNOWN'),sort_keys=True))
    elif len(sys.argv)>1 and sys.argv[1]=='--observe':
        print(json.dumps(b6.observe_database_evidence(json.loads(sys.argv[2]),sys.argv[3]),sort_keys=True))
    else:
        unittest.main()
