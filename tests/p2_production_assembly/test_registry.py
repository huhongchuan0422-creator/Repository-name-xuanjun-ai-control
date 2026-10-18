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
        self.assertEqual(len(list(self.root.iterdir())), 1)

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


if __name__ == '__main__':
    unittest.main()
