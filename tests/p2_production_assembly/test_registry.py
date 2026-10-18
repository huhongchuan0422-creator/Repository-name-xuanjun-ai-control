"""Actual root-protected registry files and isolated CLI processes; no UK IO."""
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import errno
import stat
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION = ROOT / 'production/p2_attempt5'
spec = importlib.util.spec_from_file_location('registry', str(PRODUCTION / 'registry.py'))
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)


def race_register(root, binding, pin, result):
    try:
        value = registry.register(root, binding, pin)
        result.send(value['state'])
    except Exception:
        result.send('HOLD')
    finally:
        result.close()



def paused_registration(root, binding, pin, ready, release):
    original = registry.os.fsync
    def sync(fd):
        original(fd)
        name = os.readlink('/proc/self/fd/' + str(fd))
        if name.endswith('p2-test-registry-0001.json'):
            ready.send('DATA_WRITTEN_NOT_COMMITTED')
            release.recv()
    try:
        with mock.patch.object(registry.os, 'fsync', sync):
            registry.register(root, binding, pin)
    finally:
        ready.close()
        release.close()


class RegistryTests(unittest.TestCase):
    def setUp(self):
        assert os.geteuid() == 0
        self.tmp = tempfile.TemporaryDirectory(prefix='p2-registry-test-', dir='/root')
        self.base = Path(self.tmp.name)
        self.root = self.base / 'registry'
        self.root.mkdir(mode=0o700)
        self.host = os.uname().nodename
        self.config = {'schema': 1, 'database': str(self.base / 'MUST_NOT_CREATE.sqlite'),
            'socket': str(self.base / 'MUST_NOT_CREATE.sock'),
            'principal': {'host': self.host, 'actor_id': 'TEST_ACTOR', 'writer_id': 'TEST_WRITER'},
            'key': str(self.base / 'MUST_NOT_READ_PRIVATE_KEY.pem'),
            'public_der_sha256': 'a' * 64, 'issuer': 'TEST_ISSUER',
            'adapter_path': str(self.base / 'MUST_NOT_EXECUTE_adapter.py'),
            'adapter_sha256': 'b' * 64, 'ledger_directory': str(self.base / 'MUST_NOT_CREATE_LEDGER'),
            'grant': {'target_host': self.host, 'actor_id': 'TEST_ACTOR'},
            'review_id': 1234, 'cycle_policy': {}, 'command_sha256': 'c' * 64}
        self.config_ref = self.write('config.json', self.config)
        subjects = {'issuer': {'issuer': 'TEST_ISSUER', 'public_der_sha256': 'a' * 64},
            'adapter': {'path': self.config['adapter_path'], 'sha256': 'b' * 64},
            'authority_store': {'database': self.config['database']},
            'writer_fence': {'principal': self.config['principal']}}
        self.sources = {}
        for name, kind in registry.KINDS.items():
            self.sources[name] = self.write(name + '.json',
                {'schema': 1, 'kind': kind, 'hostname': self.host,
                 'source_id': 'TEST_ONLY_ROOT_ADMIN_RECORD:' + name, 'subject': subjects[name]})
        self.record = {'schema': 1, 'registration_id': 'p2-test-registry-0001',
            'hostname': self.host, 'config': self.config_ref, 'sources': self.sources}
        self.binding = self.write('binding.json', self.record)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, value):
        path = self.base / name
        raw = registry.canonical(value)
        path.write_bytes(raw)
        os.chmod(str(path), 0o600)
        return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}

    def rewrite_binding(self):
        self.binding = self.write('binding.json', self.record)

    def register(self):
        return registry.register(str(self.root), self.binding['path'], self.binding['sha256'])

    def query(self):
        return registry.query(str(self.root), self.record['registration_id'], self.binding['sha256'])

    def test_actual_registration_and_query(self):
        self.assertEqual(self.register()['state'], 'REGISTERED_SOURCE_BINDING_ONLY')
        result = self.query()
        self.assertEqual(result['state'], 'ROOT_REGISTERED_SOURCE_BINDINGS_VERIFIED')
        self.assertEqual(result['installation_permission'], 'NOT_INFERRED')

    def test_registration_never_opens_or_creates_authority_store(self):
        self.register()
        self.assertFalse(Path(self.config['database']).exists())
        self.assertFalse(Path(self.config['ledger_directory']).exists())
        self.assertFalse(Path(self.config['socket']).exists())

    def test_registration_never_reads_private_key_or_executes_adapter(self):
        self.register()
        self.assertFalse(Path(self.config['key']).exists())
        self.assertFalse(Path(self.config['adapter_path']).exists())

    def test_query_creates_no_files_and_preserves_all_bytes(self):
        self.register()
        before = {str(p): p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        for unused in range(3):
            self.query()
        after = {str(p): p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_query_redacts_private_paths_and_configuration(self):
        self.register()
        raw = json.dumps(self.query())
        self.assertNotIn(str(self.base), raw)
        self.assertNotIn('TEST_WRITER', raw)
        self.assertNotIn('MUST_NOT_READ', raw)
        self.assertEqual(self.query()['writer_fence_live_state'], 'UNKNOWN')

    def test_idempotent_same_registration_does_not_rewrite(self):
        self.register()
        p = self.root / (self.record['registration_id'] + '.json')
        before = p.stat()
        self.assertEqual(self.register()['state'], 'ALREADY_REGISTERED')
        self.assertEqual((before.st_ino, before.st_mtime_ns), (p.stat().st_ino, p.stat().st_mtime_ns))

    def test_conflicting_id_cannot_overwrite(self):
        self.register()
        original = (self.root / (self.record['registration_id'] + '.json')).read_bytes()
        self.record['sources']['issuer']['sha256'] = 'f' * 64
        self.rewrite_binding()
        with self.assertRaises(RuntimeError):
            self.register()
        self.assertEqual((self.root / (self.record['registration_id'] + '.json')).read_bytes(), original)

    def test_partial_output_retained_and_not_reinitialized(self):
        p = self.root / (self.record['registration_id'] + '.json')
        p.write_bytes(b'{')
        os.chmod(str(p), 0o600)
        with self.assertRaises(RuntimeError):
            self.register()
        self.assertEqual(p.read_bytes(), b'{')

    def test_two_processes_share_one_immutable_record(self):
        processes = []
        pipes = []
        for unused in range(2):
            parent, child = multiprocessing.Pipe(False)
            process = multiprocessing.Process(target=race_register,
                args=(str(self.root), self.binding['path'], self.binding['sha256'], child))
            process.start()
            child.close()
            processes.append(process)
            pipes.append(parent)
        results = []
        for process, pipe in zip(processes, pipes):
            self.assertTrue(pipe.poll(15))
            results.append(pipe.recv())
            pipe.close()
            process.join(15)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode, 0)
        self.assertIn('REGISTERED_SOURCE_BINDING_ONLY', results)
        self.assertTrue(all(r in ('REGISTERED_SOURCE_BINDING_ONLY', 'ALREADY_REGISTERED', 'HOLD') for r in results))
        self.query()
        self.assertEqual({p.name for p in self.root.iterdir()},
            {self.record['registration_id'] + '.json', registry.LOCK, registry.INDEX})

    def test_source_mutation_holds_after_registration(self):
        self.register()
        Path(self.sources['issuer']['path']).write_bytes(b'{}')
        with self.assertRaises(RuntimeError):
            self.query()

    def test_wrong_issuer_subject_rejected(self):
        value = {'schema': 1, 'kind': 'ISSUER_TRUST', 'hostname': self.host,
            'source_id': 'TEST', 'subject': {'issuer': 'OTHER', 'public_der_sha256': 'a' * 64}}
        self.record['sources']['issuer'] = self.write('issuer.json', value)
        self.rewrite_binding()
        with self.assertRaises(RuntimeError):
            self.register()

    def test_wrong_authority_source_rejected(self):
        value = {'schema': 1, 'kind': 'AUTHORITY_STORE_SOURCE', 'hostname': self.host,
            'source_id': 'TEST', 'subject': {'database': '/not-the-approved-database'}}
        self.record['sources']['authority_store'] = self.write('authority_store.json', value)
        self.rewrite_binding()
        with self.assertRaises(RuntimeError):
            self.register()

    def test_unknown_writer_source_not_trusted(self):
        value = {'schema': 1, 'kind': 'WRITER_FENCE_SOURCE', 'hostname': self.host,
            'source_id': 'UNKNOWN', 'subject': {'principal': self.config['principal']}}
        self.record['sources']['writer_fence'] = self.write('writer_fence.json', value)
        self.rewrite_binding()
        with self.assertRaises(RuntimeError):
            self.register()

    def test_source_set_must_be_complete(self):
        del self.record['sources']['adapter']
        self.rewrite_binding()
        with self.assertRaises(RuntimeError):
            self.register()

    def test_wrong_hostname_rejected(self):
        self.record['hostname'] = 'OTHER_HOST'
        self.rewrite_binding()
        with self.assertRaises(RuntimeError):
            self.register()

    def test_registry_root_not_auto_created(self):
        missing = self.base / 'missing-root'
        with self.assertRaises(FileNotFoundError):
            registry.register(str(missing), self.binding['path'], self.binding['sha256'])
        self.assertFalse(missing.exists())

    def test_world_accessible_registry_directory_rejected(self):
        os.chmod(str(self.root), 0o755)
        with self.assertRaises(RuntimeError):
            self.register()

    def test_symlink_record_rejected(self):
        os.symlink(self.binding['path'], str(self.root / (self.record['registration_id'] + '.json')))
        with self.assertRaises(OSError):
            self.register()

    def test_source_parent_protection_not_weakened(self):
        os.chmod(str(self.base), 0o777)
        try:
            with self.assertRaises(RuntimeError):
                self.register()
        finally:
            os.chmod(str(self.base), 0o700)

    def test_config_world_readable_rejected(self):
        os.chmod(self.config_ref['path'], 0o644)
        with self.assertRaises(RuntimeError):
            self.register()

    def test_duplicate_record_keys_rejected(self):
        raw = b'{"schema":1,"schema":2}\n'
        Path(self.binding['path']).write_bytes(raw)
        with self.assertRaises(RuntimeError):
            registry.register(str(self.root), self.binding['path'], hashlib.sha256(raw).hexdigest())

    def test_record_nonfinite_numbers_rejected(self):
        raw = b'{"schema":NaN}\n'
        Path(self.binding['path']).write_bytes(raw)
        with self.assertRaises(RuntimeError):
            registry.register(str(self.root), self.binding['path'], hashlib.sha256(raw).hexdigest())

    def test_record_id_path_traversal_rejected(self):
        self.record['registration_id'] = '../escape'
        self.rewrite_binding()
        with self.assertRaises(RuntimeError):
            self.register()

    def test_wrong_record_pin_rejected(self):
        with self.assertRaises(RuntimeError):
            registry.register(str(self.root), self.binding['path'], 'f' * 64)

    def test_execution_requires_exact_registered_config(self):
        self.register()
        value = registry.require_binding(str(self.root), self.record['registration_id'],
            self.binding['sha256'], self.config_ref['path'], self.config_ref['sha256'])
        self.assertEqual(value, self.config)
        with self.assertRaises(RuntimeError):
            registry.require_binding(str(self.root), self.record['registration_id'],
                self.binding['sha256'], self.config_ref['path'], 'f' * 64)

    def test_query_missing_record_does_not_register(self):
        with self.assertRaises(FileNotFoundError):
            self.query()
        self.assertEqual(list(self.root.iterdir()), [])

    def cli(self, operation):
        folder = self.base / 'code'
        folder.mkdir(exist_ok=True)
        for name in ('registry_cli.py', 'registry.py', 'assembly.py'):
            shutil.copyfile(str(PRODUCTION / name), str(folder / name))
        command = [sys.executable, '-I', '-B', '-S', str(folder / 'registry_cli.py'),
            operation, '--registry-root', str(self.root),
            '--registration-id', self.record['registration_id'],
            '--record-sha256', self.binding['sha256'],
            '--assembly-sha256', hashlib.sha256((folder / 'assembly.py').read_bytes()).hexdigest(),
            '--registry-code-sha256', hashlib.sha256((folder / 'registry.py').read_bytes()).hexdigest()]
        if operation == 'register':
            command += ['--binding-file', self.binding['path']]
        return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)

    def test_formal_cli_register_then_independent_process_query(self):
        result = self.cli('register')
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(json.loads(result.stdout)['state'], 'REGISTERED_SOURCE_BINDING_ONLY')
        result = self.cli('query')
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(json.loads(result.stdout)['record_sha256'], self.binding['sha256'])

    def test_formal_cli_missing_record_holds_without_side_effect(self):
        result = self.cli('query')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['state'], 'HOLD')
        self.assertEqual(list(self.root.iterdir()), [])


    def rebind_config(self, values):
        self.config.update(values)
        self.config_ref = self.write('config.json', self.config)
        self.record['config'] = self.config_ref
        subjects = {
            'issuer': {'issuer': self.config['issuer'], 'public_der_sha256': self.config['public_der_sha256']},
            'adapter': {'path': self.config['adapter_path'], 'sha256': self.config['adapter_sha256']},
            'authority_store': {'database': self.config['database']},
            'writer_fence': {'principal': self.config['principal']}}
        for name, kind in registry.KINDS.items():
            self.record['sources'][name] = self.write(name + '.json',
                {'schema': 1, 'kind': kind, 'hostname': self.host,
                 'source_id': 'TEST_ONLY_ROOT_ADMIN_RECORD:' + name, 'subject': subjects[name]})
        self.rewrite_binding()

    def test_r1_non_string_digests_rejected_before_write(self):
        for name in ('public_der_sha256', 'adapter_sha256', 'command_sha256'):
            original = self.config[name]
            for bad in ({'private_path': '/private/TEST_ONLY.pem'}, [], 1, None, True):
                with self.subTest(field=name, value=bad):
                    self.rebind_config({name: bad})
                    with self.assertRaises(RuntimeError):
                        self.register()
                    self.assertEqual(list(self.root.iterdir()), [])
            self.rebind_config({name: original})

    def test_r1_digest_length_character_and_path_rejected(self):
        for name in ('public_der_sha256', 'adapter_sha256'):
            original = self.config[name]
            for bad in ('', 'a' * 63, 'a' * 65, 'Z' * 64, '/private/TEST_ONLY.py', 'UNKNOWN'):
                with self.subTest(field=name, value=bad):
                    self.rebind_config({name: bad})
                    with self.assertRaises(RuntimeError):
                        self.register()
            self.rebind_config({name: original})

    def test_r1_issuer_type_empty_unknown_format_rejected(self):
        for bad in ('UNKNOWN', 'unknown', '', ' ', 'issuer\nsecret', {'path': '/private/TEST_ONLY'}, 1, None):
            with self.subTest(value=bad):
                self.rebind_config({'issuer': bad})
                with self.assertRaises(RuntimeError):
                    self.register()

    def test_r1_all_config_paths_are_canonical_and_typed(self):
        for name in ('database', 'adapter_path', 'key', 'socket', 'ledger_directory'):
            original = self.config[name]
            for bad in ('UNKNOWN', '', 'relative/path', '/a/../b', '//root/file', '/a\x00b', {}, 1, None):
                with self.subTest(field=name, value=bad):
                    self.rebind_config({name: bad})
                    with self.assertRaises(RuntimeError):
                        self.register()
            self.rebind_config({name: original})

    def test_r1_source_subject_requires_exact_dict(self):
        value = {'schema': 1, 'kind': 'ISSUER_TRUST', 'hostname': self.host,
                 'source_id': 'TEST', 'subject': ['TEST_ISSUER', 'a' * 64]}
        self.record['sources']['issuer'] = self.write('issuer.json', value)
        self.rewrite_binding()
        with self.assertRaises(RuntimeError):
            self.register()

    def test_r1_invalid_legacy_record_query_holds(self):
        self.rebind_config({'public_der_sha256': {'private_path': '/private/TEST_ONLY.pem'}})
        p = self.root / (self.record['registration_id'] + '.json')
        p.write_bytes(Path(self.binding['path']).read_bytes())
        os.chmod(str(p), 0o600)
        with self.assertRaises((RuntimeError, FileNotFoundError)):
            self.query()

    def test_r1_output_exact_whitelist_and_digest_scalars(self):
        self.register()
        value = self.query()
        self.assertEqual(set(value), {'schema','state','registration_id','record_sha256',
            'config_sha256','issuer_public_der_sha256','adapter_sha256','sources',
            'authority_live_state','writer_fence_live_state','installation_permission','release'})
        for name in ('record_sha256','config_sha256','issuer_public_der_sha256','adapter_sha256'):
            self.assertIs(type(value[name]), str)
            self.assertRegex(value[name], r'^[0-9a-f]{64}$')
        for pin in value['sources'].values():
            self.assertRegex(pin, r'^[0-9a-f]{64}$')
        self.assertNotIn('/private/', json.dumps(value))
        self.assertNotIn(str(self.base), json.dumps(value))

    def test_r1_source_impersonation_by_other_principal_holds(self):
        value = {'schema': 1, 'kind': 'WRITER_FENCE_SOURCE', 'hostname': self.host,
            'source_id': 'TEST', 'subject': {'principal': {
                'host': self.host, 'actor_id': 'OTHER_ACTOR', 'writer_id': 'TEST_WRITER'}}}
        self.record['sources']['writer_fence'] = self.write('writer_fence.json', value)
        self.rewrite_binding()
        with self.assertRaises(RuntimeError):
            self.register()

    def test_r1_exact_auditor_counterexample_refused(self):
        self.rebind_config({'public_der_sha256': {'private_path': '/private/SYNTHETIC_ONLY.pem'},
            'adapter_sha256': '/private/SYNTHETIC_ONLY_adapter.py',
            'issuer': 'UNKNOWN', 'adapter_path': 'UNKNOWN', 'database': 'UNKNOWN'})
        with self.assertRaises(RuntimeError):
            self.register()
        self.assertEqual(list(self.root.iterdir()), [])

    def failed_sync(self, directory=False):
        original = registry.os.fsync
        record = self.root / (self.record['registration_id'] + '.json')
        def sync(fd):
            target = os.readlink('/proc/self/fd/' + str(fd))
            is_record = target == str(record)
            is_directory = target == str(self.root) and record.exists()
            if (directory and is_directory) or (not directory and is_record):
                raise OSError(errno.EIO, 'TEST_ONLY_FSYNC_FAILURE')
            return original(fd)
        with mock.patch.object(registry.os, 'fsync', sync):
            with self.assertRaises(OSError):
                self.register()
        self.assertEqual(record.read_bytes(), Path(self.binding['path']).read_bytes())

    def assert_uncommitted(self):
        with self.assertRaises(RuntimeError):
            self.query()
        with self.assertRaises(RuntimeError):
            registry.require_binding(str(self.root), self.record['registration_id'],
                self.binding['sha256'], self.config_ref['path'], self.config_ref['sha256'])

    def test_r2_file_fsync_failure_is_not_committed(self):
        self.failed_sync()
        self.assert_uncommitted()

    def test_r2_directory_fsync_failure_is_not_committed(self):
        self.failed_sync(directory=True)
        self.assert_uncommitted()

    def test_r2_retry_does_not_auto_commit_failed_record(self):
        self.failed_sync()
        with mock.patch.object(registry.os, 'fsync', side_effect=OSError(errno.EIO, 'TEST')):
            with self.assertRaises(RuntimeError):
                self.register()
        self.assert_uncommitted()

    def test_r2_failure_then_new_process_query_remains_hold(self):
        self.failed_sync()
        result = self.cli('query')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['state'], 'HOLD')

    def start_paused_writer(self):
        parent, child = multiprocessing.Pipe(False)
        release_child, release_parent = multiprocessing.Pipe(False)
        process = multiprocessing.Process(target=paused_registration,
            args=(str(self.root), self.binding['path'], self.binding['sha256'], child, release_child))
        process.start()
        child.close()
        release_child.close()
        self.assertTrue(parent.poll(15))
        self.assertEqual(parent.recv(), 'DATA_WRITTEN_NOT_COMMITTED')
        parent.close()
        return process, release_parent

    def test_r2_concurrent_query_and_registration_hold_until_commit(self):
        process, release = self.start_paused_writer()
        try:
            self.assert_uncommitted()
            with self.assertRaises(RuntimeError):
                self.register()
            release.send('CONTINUE')
            process.join(15)
            self.assertEqual(process.exitcode, 0)
            self.query()
        finally:
            release.close()
            if process.is_alive():
                process.terminate()
                process.join(5)

    def test_r2_process_killed_after_write_stays_uncommitted(self):
        process, release = self.start_paused_writer()
        process.terminate()
        process.join(5)
        release.close()
        self.assertFalse(process.is_alive())
        self.assert_uncommitted()
        with self.assertRaises(RuntimeError):
            self.register()

    def formal_entry(self, operation, directory_failure=False):
        release = self.base / 'release'
        code = release / 'production/p2_attempt5'
        code.mkdir(parents=True)
        for name in ('entry.py', 'assembly.py', 'registry.py'):
            shutil.copyfile(str(PRODUCTION / name), str(code / name))
        files = {'production/p2_attempt5/' + p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in code.iterdir()}
        manifest = {'source_commit': 'e' * 40, 'source_tree': 'd' * 40,
            'inherited_manifest_sha256': 'f' * 64,
            'reviewed_core_commit': 'f4f74fdd0b6aa49e046debabf81e438b17ff20b5',
            'reviewed_core_tree': '2c2e3c09cbda31df30e0d269b580348c55e6de87',
            'files': files}
        manifest_raw = registry.canonical(manifest)
        (release / 'MANIFEST.json').write_bytes(manifest_raw)
        pin = hashlib.sha256(manifest_raw).hexdigest()
        grant = dict(self.config['grant'], source_commit='e'*40, source_tree='d'*40,
                     manifest_sha256=pin)
        self.rebind_config({'grant': grant})
        self.failed_sync(directory=directory_failure)
        kit = self.base / 'kit/attempt5/runtime'
        kit.mkdir(parents=True)
        loader_raw = b'raise AssertionError("REGISTRY_GATE_WAS_BYPASSED")\n'
        (kit / 'versioned_entry.py').write_bytes(loader_raw)
        command = [sys.executable, '-I', '-B', '-S', str(code / 'entry.py'), operation,
            '--kit-root', str(self.base / 'kit'),
            '--loader-sha256', hashlib.sha256(loader_raw).hexdigest(),
            '--manifest-sha256', 'f' * 64, '--config', self.config_ref['path'],
            '--config-sha256', self.config_ref['sha256'],
            '--assembly-sha256', files['production/p2_attempt5/assembly.py'],
            '--assembly-manifest', str(release / 'MANIFEST.json'),
            '--assembly-manifest-sha256', pin, '--registry-root', str(self.root),
            '--registry-id', self.record['registration_id'],
            '--registry-record-sha256', self.binding['sha256']]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'REGISTRATION_NOT_COMMITTED', result.stderr)
        self.assertNotIn(b'REGISTRY_GATE_WAS_BYPASSED', result.stderr)
        self.assertFalse(Path(self.config['database']).exists())

    def test_r2_formal_run_refuses_file_sync_failure_before_provider(self):
        self.formal_entry('run')

    def test_r2_formal_serve_refuses_directory_sync_failure_before_issuer(self):
        self.formal_entry('serve', directory_failure=True)

    def test_r2_readonly_query_never_fsyncs_or_modifies_index(self):
        self.register()
        before = {str(p): p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        with mock.patch.object(registry.os, 'fsync', side_effect=AssertionError('READONLY')):
            self.query()
        after = {str(p): p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        self.assertEqual(before, after)

    def test_r2_production_database_cannot_be_registry_metadata_index(self):
        self.rebind_config({'database': str(self.root / registry.INDEX)})
        with self.assertRaises(RuntimeError):
            self.register()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_r2_missing_committed_record_cannot_be_recreated(self):
        self.register()
        (self.root / (self.record['registration_id'] + '.json')).unlink()
        with self.assertRaises(RuntimeError):
            self.register()
        self.assertFalse((self.root / (self.record['registration_id'] + '.json')).exists())

    def test_r2_complete_legacy_record_is_not_auto_committed(self):
        p = self.root / (self.record['registration_id'] + '.json')
        p.write_bytes(Path(self.binding['path']).read_bytes())
        os.chmod(str(p), 0o600)
        with self.assertRaises(RuntimeError):
            self.register()
        self.assert_uncommitted()

    def test_r2_hot_index_journal_requires_explicit_recovery(self):
        self.register()
        journal = self.root / (registry.INDEX + '-journal')
        journal.write_bytes(b'TEST_ONLY_UNRESOLVED_INDEX_JOURNAL')
        with self.assertRaises(RuntimeError):
            self.query()
        self.assertTrue(journal.exists())


if __name__ == '__main__':
    unittest.main()
