"""Focused local private-completeness producer tests.

Saved host seeds are unavailable. All seed/configuration values are synthetic;
public cached compiler bytes remain real. The suite never runs old test suites,
contacts a host, authorizes C, assembles a driver, or resumes production.
Run only this module with Python 3.6/3.12 -I -B -S. On the locally broken
Python 3.6 build select boundary classes explicitly; healthy Hosted 3.6 runs all.
"""
import ast
import base64
import builtins
import contextlib
import copy
import errno
import gzip
import hashlib
import importlib
import importlib.util
import io
import json
import os
import pathlib
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import tarfile
import types
import unittest
import urllib.request
import warnings
from unittest.mock import Mock, call, patch

HERE = pathlib.Path(__file__).resolve().parent
PATH = HERE / 'validate_private_completeness.py'
SECRET = 'PRIVATE_SENTINEL_NOT_FOR_OUTPUT'


def loaded(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def packed(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii') + b'\n'


def deterministic_gzip(raw):
    stream = io.BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0, compresslevel=9) as output:
        output.write(raw)
    return stream.getvalue()


@contextlib.contextmanager
def no_budget(seconds):
    yield


def info(**updates):
    values = dict(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o600,
                  st_uid=0, st_gid=0, st_nlink=1, st_size=3,
                  st_mtime_ns=123, st_ctime_ns=456)
    values.update(updates)
    return types.SimpleNamespace(**values)


m = loaded(PATH, 'private_completeness_producer_under_test')
FORMAT = {'bounds': {'gzip': 70000, 'raw': 16777216, 'stdout': 98304},
 'candidate': {'admission_expires_at_utc': '2026-10-16T18:00:00Z',
               'body_bytes': 7968,
               'body_sha256': '35c6fd49a18845542c01c65b0f870cef1626b841e2daba138a687e4137d4a1f5',
               'formal_approval': 'NOT_ISSUED',
               'install_admission': 'NOT_GRANTED',
               'packet_sha256': '2bf597ef911cba70b5c94559ee36d8f90c2a339a3de1bfd2d8f58547900b8dec',
               'plan_sha256': '5b3a34222dc634d95b4e070105de9afb3dc24b5c53f7b6497bc61d392887fb01'},
 'checks': {'body_exact_match': True,
            'factory_state': 'COMPILED_NOT_ADMITTED',
            'input_root_recomputed_onsite': True,
            'install_admission': False,
            'plan_exact_match': True,
            'private_values_unchanged': True,
            'original_derived_preimages_recomputed_onsite': True,
            'unresolved_count': 0},
 'compiler': {'cache_files': 256,
              'dependency_commit': 'e2df38160e635af96dcfd63a1b75cf64671e4935',
              'entry_bytes': 56593,
              'entry_sha256': '21a982161bc4cb8ffd7e67e4b9a8e24bf23916df6d78c3dd43376af3cfb34890',
              'manifest_sha256': '91252ba75c38b4a6d12f9b64eb06cb8793fabd97f03646bece97224178c28392',
              'runtime_manifest_sha256': '0ac28c96636ee63364015b375202779e2ef1dd0bd9f1b81e77d4387b6754316c',
              'runtime_payloads': 107,
              'source_commit': '105996ed06a0bdb5d025914cf08ebd448425f739',
              'source_tree': '343d315b3ead6266a626b5875dbdd6c2fa0309af'},
 'file_authority': 'ROOT_ROOT_REGULAR_0600_NLINK1_NOFOLLOW_NO_EXTENDED_ACL',
 'file_metadata_keys': ['dev', 'ino', 'uid', 'gid', 'mode', 'nlink', 'size', 'mtime_ns', 'ctime_ns'],
 'file_row_keys': ['role', 'name', 'bytes', 'sha256', 'metadata', 'reread_match', 'authority'],
 'files_rows': [['new_seed',
                 'epoch7-lifecycle-resume-inputs-d7eabd4c0716bd23.private.json',
                 770702,
                 'd7eabd4c0716bd23c35a210c0ace8493b8a9f23237d1df1eeef231fdda8d16f0'],
                ['old_seed',
                 'epoch7-resume-inputs-6de7d12246826388.private.json',
                 769086,
                 '6de7d12246826388949723e9238cd464686e6e86847187946837df927c97a550'],
                ['plan',
                 'epoch7-lifecycle-approved-plan-5b3a34222dc634d9.private.json',
                 140648,
                 '5b3a34222dc634d95b4e070105de9afb3dc24b5c53f7b6497bc61d392887fb01'],
                ['packet',
                 'epoch7-lifecycle-review-packet-2bf597ef911cba70.private.json',
                 29665,
                 '2bf597ef911cba70b5c94559ee36d8f90c2a339a3de1bfd2d8f58547900b8dec']],
 'hidden_domain': 'P2_PRIVATE_COMPLETENESS_INPUT_FIELD_V1',
 'hidden_inputs_keys': ['scheme',
                        'domain',
                        'session_nonce',
                        'input_root_sha256',
                        'input_field_names',
                        'field_commitments',
                        'key_disclosure',
                        'offline_binding'],
 'hidden_key_disclosure': 'NEVER_EXPORTED_OR_PERSISTED',
 'hidden_offline_binding': 'ONSITE_REPORT_ONLY_NOT_INDEPENDENTLY_RECOMPUTABLE',
 'hidden_scheme': 'HMAC_SHA256_EPHEMERAL_KEY_V1',
 'input_field_names': ['acceptance_access_rows',
                       'acceptance_facts',
                       'access_rows',
                       'activate_retained_renewal_timer',
                       'additive_deltas',
                       'artifact',
                       'boot_before',
                       'candidate',
                       'claim_successor',
                       'compiled',
                       'database_sidecar_policy',
                       'executable_specs',
                       'fresh_release_parent',
                       'identity_payloads',
                       'installer_source',
                       'kit_manifest_sha256',
                       'legacy_units_raw',
                       'manager',
                       'native_before',
                       'observation',
                       'prior_provision_bytes',
                       'process_roles',
                       'publisher_journal_raw',
                       'resource_directories',
                       'resource_views',
                       'sandbox_candidate_raw',
                       'service_facts',
                       'service_role_contract',
                       'snapshot',
                       'snapshot_policy',
                       'source_manifest_raw',
                       'source_payloads',
                       'supporting_evidence',
                       'timer_raw_baseline',
                       'tls_journal_before',
                       'unit_checkpoints',
                       'unit_transition_contract'],
 'kind': 'P2_FIXED_PRIVATE_COMPLETENESS_EVIDENCE_V1',
 'limitations': ['OWNER_TERMINAL_REPORT_NOT_REMOTE_ATTESTATION',
                 'HIDDEN_INPUT_ROOT_ONLY_RECOMPUTED_ONSITE',
                 'AFFECTED_DERIVED_ROOTS_ONLY_RECOMPUTED_ONSITE',
                 'NO_RAW_SEED_OR_CONFIG_DISCLOSED',
                 'NO_CURRENT_WRITER_DATABASE_OR_TIMER_PROOF',
                 'NO_C_DRIVER_ASSEMBLY_OR_EXECUTION',
                 'ATIME_POSSIBLE_NOT_MEASURED'],
 'root_keys': ['schema',
               'kind',
               'state',
               'compiler',
               'files',
               'seed_inheritance',
               'candidate',
               'hidden_inputs',
               'preimages',
               'checks',
               'runtime',
               'limitations'],
 'runtime_call_path': ['entry.verify_kit',
                       'entry._hydrate_seed',
                       'factory.prepare_host_inputs',
                       'factory.compile_host_contract',
                       'factory._proposal',
                       'factory.compile_timer_contract',
                       'schema.build_preimages',
                       'schema.verify_preimages',
                       'schema.privacy_project',
                       'schema.verify_projected_preimages',
                       'protected_final_rereads'],
 'runtime_cleanup': 'COMPLETED',
 'runtime_keys': ['validator',
                  'schema_source_sha256',
                  'started_utc',
                  'finished_utc',
                  'scope',
                  'additional_metadata_reads',
                  'call_path',
                  'cleanup'],
 'runtime_metadata': ['/var/lib/xuanjun-development/generations/1/state.sqlite',
                      '/run/xuanjun-development/ledger.sock'],
 'runtime_scope': 'FIXED_SAVED_INPUTS_AND_AUTHENTICATED_PURE_COMPILERS_ONLY',
 'schema': 1,
 'seed_inheritance': {'claim_equals_packet': True,
                      'new_field_count': 13,
                      'new_schema': 2,
                      'new_without_claim_equals_old': True,
                      'old_field_count': 12,
                      'old_schema': 1,
                      'private_fields_not_disclosed': True},
 'state': 'EVIDENCE_COLLECTED_WITH_LIMITATIONS'}


class DescriptorAndBudgetTests(unittest.TestCase):
    def read_fixture(self, before=None, linked=None, chunks=None, pin=None, after=None, private=True):
        before = before or info(st_mode=stat.S_IFREG | (0o600 if private else 0o444))
        linked = linked or before
        with contextlib.ExitStack() as stack:
            opened = stack.enter_context(patch.object(m.os, 'open', return_value=8))
            stack.enter_context(patch.object(m.os, 'fstat', side_effect=[before, after or before]))
            stack.enter_context(patch.object(m.os, 'stat', return_value=linked))
            read = stack.enter_context(patch.object(m.os, 'read', side_effect=chunks or [b'abc', b'']))
            attrs = stack.enter_context(patch.object(m, 'attributes'))
            close = stack.enter_context(patch.object(m.os, 'close'))
            result = m.read_exact(7, 'synthetic', 3, pin or hashlib.sha256(b'abc').hexdigest(), private=private)
            close.assert_called_once_with(8)
            opened.assert_called_once_with('synthetic', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=7)
            self.assertTrue(all(0 < event[0][1] <= 65536 for event in read.call_args_list))
            self.assertEqual(attrs.call_count, 2)
            return result

    def test_python36_syntax_exact_four_file_pins_and_output_limit(self):
        if sys.version_info >= (3, 8):
            ast.parse(PATH.read_text(), feature_version=(3, 6))
        else:
            ast.parse(PATH.read_text())
        self.assertEqual([list(row) for row in m.INPUTS], FORMAT['files_rows'])
        self.assertEqual(m.ENTRY_SHA, FORMAT['compiler']['entry_sha256'])
        self.assertEqual(m.ENTRY_BYTES, FORMAT['compiler']['entry_bytes'])
        self.assertEqual(m.MANIFEST_SHA, FORMAT['compiler']['manifest_sha256'])
        self.assertEqual(m.MAX_OUTPUT, 98304)
        self.assertEqual(len(m.INPUTS), 4)
        self.assertTrue(all('/' not in row[1] and row[1].endswith('.private.json') for row in m.INPUTS))

    def test_embedded_schema_exact_reviewed_bytes_and_bounded_single_stream(self):
        # No unbound-source skip: this test must fail until final reviewed bytes
        # are actually embedded in the distributable producer.
        reviewed = (HERE / 'evidence_schema.py').read_bytes()
        self.assertEqual(m.SCHEMA_BYTES, len(reviewed))
        self.assertEqual(m.SCHEMA_SHA, hashlib.sha256(reviewed).hexdigest())
        compressed = base64.b64decode(m.SCHEMA_B64, validate=True)
        stream = m.zlib.decompressobj()
        actual = stream.decompress(compressed, len(reviewed) + 1)
        self.assertTrue(stream.eof)
        self.assertFalse(stream.unconsumed_tail or stream.unused_data)
        self.assertTrue(actual == reviewed, 'embedded schema differs from reviewed source')
        schema = m.load_schema()
        self.assertTrue(callable(schema.verify_projected_preimages))
        self.assertTrue(callable(schema.privacy_project))
        with patch.object(m, 'SCHEMA_SHA', '0' * 64), self.assertRaisesRegex(m.Hold, '^SCHEMA_BINDING$'):
            m.load_schema()
        extra = base64.b64encode(compressed + m.zlib.compress(b'UNREVIEWED_EXTRA_MEMBER')).decode('ascii')
        with patch.object(m, 'SCHEMA_B64', extra), self.assertRaisesRegex(m.Hold, '^SCHEMA_BINDING$'):
            m.load_schema()

    def test_exact_private0600_public0444_and_nofollow_flags(self):
        for private in (True, False):
            with self.subTest(private=private):
                self.assertEqual(self.read_fixture(private=private)[0], b'abc')
        with self.assertRaisesRegex(m.Hold, '^FILE_AUTHORITY$'):
            self.read_fixture(before=info(st_mode=stat.S_IFREG | 0o644), private=False)

    def test_root_owner_regular_single_link_and_size_hash_races_refuse(self):
        cases = [('FILE_AUTHORITY', dict(before=info(st_uid=1))),
                 ('FILE_AUTHORITY', dict(before=info(st_gid=1))),
                 ('FILE_AUTHORITY', dict(before=info(st_mode=stat.S_IFREG | 0o640))),
                 ('FILE_AUTHORITY', dict(before=info(st_mode=stat.S_IFLNK | 0o600))),
                 ('FILE_AUTHORITY', dict(before=info(st_nlink=2))),
                 ('FILE_SIZE', dict(before=info(st_size=4))),
                 ('FILE_SIZE', dict(chunks=[b'ab', b''])),
                 ('FILE_SIZE', dict(chunks=[b'abcd'])),
                 ('FILE_HASH', dict(pin='0' * 64)),
                 ('PATH_IDENTITY', dict(linked=info(st_ino=44))),
                 ('FILE_CHANGED', dict(after=info(st_ctime_ns=999)))]
        for code, arguments in cases:
            with self.subTest(code=code), self.assertRaisesRegex(m.Hold, '^' + code + '$'):
                self.read_fixture(**arguments)

    def test_extended_acl_capabilities_and_unreadable_attributes_refuse(self):
        for value in (b'', b'acl'):
            with patch.object(m.os, 'getxattr', return_value=value), self.assertRaisesRegex(m.Hold, '^ATTRIBUTES$'):
                m.attributes(8)
        for code in (errno.ENODATA, errno.ENOTSUP):
            with patch.object(m.os, 'getxattr', side_effect=OSError(code, SECRET)) as get:
                m.attributes(8)
                self.assertEqual([row[0][1] for row in get.call_args_list],
                    ['system.posix_acl_access', 'system.posix_acl_default', 'security.capability'])
        with patch.object(m.os, 'getxattr', side_effect=OSError(errno.EACCES, SECRET)), self.assertRaisesRegex(m.Hold, '^ATTRIBUTES$'):
            m.attributes(8)

    def test_directory_ancestry_metadata_and_link_drift_refuse(self):
        for item in (info(), info(st_mode=stat.S_IFDIR | 0o777), info(st_mode=stat.S_IFDIR | 0o755, st_uid=1)):
            with patch.object(m.os, 'fstat', return_value=item), patch.object(m, 'attributes'), self.assertRaisesRegex(m.Hold, '^DIRECTORY$'):
                m.directory(8)
        with patch.object(m, 'directory', return_value=('changed',)), self.assertRaisesRegex(m.Hold, '^PATH_IDENTITY$'):
            m.recheck([(None, '/', 8, ('original',))])
        with patch.object(m, 'directory', return_value=m.stamp(info())), patch.object(m.os, 'stat', return_value=info(st_ino=50)), self.assertRaisesRegex(m.Hold, '^PATH_IDENTITY$'):
            m.recheck([(7, 'leaf', 8, m.stamp(info()))])

    def test_descriptor_cleanup_attempts_all_and_preserves_primary(self):
        primary = m.Deadline()
        with patch.object(m.os, 'close', side_effect=OSError(SECRET)) as close:
            m.close_all([1, 2, 3], primary)
            self.assertTrue(primary.cleanup_unknown)
            self.assertEqual(close.call_args_list, [call(3), call(2), call(1)])
            with self.assertRaisesRegex(m.Hold, '^CLEANUP$'):
                m.close_all([1])

    def test_deadline_restores_timer_and_handler(self):
        with patch.object(m.signal, 'getitimer', return_value=(0.0, 0.0)), patch.object(m.signal, 'getsignal', return_value='previous'), patch.object(m.signal, 'signal') as change_signal, patch.object(m.signal, 'setitimer') as timer, patch.object(m.time, 'monotonic', side_effect=[100.0, 221.0]):
            with self.assertRaises(m.Deadline):
                with m.budget(120):
                    pass
            self.assertEqual(timer.call_args_list, [call(m.signal.ITIMER_REAL, 120, 0), call(m.signal.ITIMER_REAL, 0)])
            self.assertEqual(change_signal.call_args[0], (m.signal.SIGALRM, 'previous'))
        with patch.object(m.signal, 'getitimer', return_value=(1.0, 0.0)), patch.object(m.signal, 'setitimer') as timer:
            with self.assertRaisesRegex(m.Hold, '^EXISTING_TIMER$'):
                with m.budget(120):
                    self.fail('existing alarm displaced')
            timer.assert_not_called()

    def test_budget_cleanup_failure_cannot_mask_primary(self):
        primary = KeyboardInterrupt(SECRET)
        with patch.object(m.signal, 'getitimer', return_value=(0.0, 0.0)), patch.object(m.signal, 'getsignal', return_value='previous'), patch.object(m.signal, 'signal', side_effect=[None, OSError(SECRET)]), patch.object(m.signal, 'setitimer', side_effect=[None, OSError(SECRET)]):
            with self.assertRaises(KeyboardInterrupt) as raised:
                with m.budget(120):
                    raise primary
        self.assertIs(raised.exception, primary)
        self.assertTrue(primary.cleanup_unknown)


class ImportBoundaryTests(unittest.TestCase):
    def cold(self, tail):
        code = '''import builtins,importlib.util,sys,subprocess,tempfile
spec=importlib.util.spec_from_file_location('private_completeness_validator',%r)
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
assert 'uuid' not in sys.modules
original=builtins.__import__
def forbidden(*a,**k):raise AssertionError('FORBIDDEN_EFFECT')
subprocess.Popen=forbidden
subprocess.call=forbidden
subprocess.check_call=forbidden
subprocess.check_output=forbidden
tempfile.NamedTemporaryFile=forbidden
tempfile.TemporaryFile=forbidden
tempfile.mkstemp=forbidden
''' % str(PATH)
        result = subprocess.run([sys.executable, '-I', '-B', '-S', '-c', code + tail],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
        self.assertEqual(result.stdout, b'')

    def test_genuine_cold_uuid_parser_no_discovery_effects_and_preload_refusal(self):
        self.cold("u=v.cold_uuid_parser();assert u.__name__=='uuid';assert builtins.__import__ is original;assert str(u.UUID('c529c379-9341-4510-8384-fc6be1e412e5'))=='c529c379-9341-4510-8384-fc6be1e412e5';assert 'ctypes.util' not in sys.modules\ntry:v.cold_uuid_parser()\nexcept v.Hold as e:assert e.args==('UUID_PRELOADED',)\nelse:raise AssertionError('preload accepted')\n")

    def test_cold_import_exception_restores_exact_import_object(self):
        self.cold("def broken(name):raise KeyboardInterrupt()\nv.importlib.import_module=broken\ntry:v.cold_uuid_parser()\nexcept KeyboardInterrupt:pass\nelse:raise AssertionError('interruption lost')\nassert builtins.__import__ is original\n")

    def fakekit(self, mode):
        @contextlib.contextmanager
        def imports():
            sys.path.append('SYNTHETIC_LOCAL_TEST_PATH')
            sys.meta_path.append(object())
            sys.modules['synthetic_kit_module'] = types.ModuleType('synthetic_kit_module')
            try:
                yield
            finally:
                if mode == 'failure':
                    raise RuntimeError(SECRET)
                if mode == 'normal':
                    sys.path.pop(); sys.meta_path.pop(); sys.modules.pop('synthetic_kit_module')
        return types.SimpleNamespace(manifest={'modules': {'synthetic_kit_module': 'synthetic.py'}}, imports=imports)

    def test_auth_import_normal_and_silent_drift_restore_exact_global_state(self):
        before = (list(sys.path), list(sys.meta_path))
        with m.authenticated_imports(self.fakekit('normal')):
            pass
        self.assertEqual((sys.path, sys.meta_path), before)
        with self.assertRaisesRegex(m.Hold, '^IMPORT_CLEANUP$'):
            with m.authenticated_imports(self.fakekit('drift')):
                pass
        self.assertEqual((sys.path, sys.meta_path), before)
        self.assertNotIn('synthetic_kit_module', sys.modules)

    def test_auth_import_cleanup_failure_preserves_primary_without_raw_message(self):
        before = (list(sys.path), list(sys.meta_path))
        primary = KeyboardInterrupt(SECRET)
        with self.assertRaises(KeyboardInterrupt) as raised:
            with m.authenticated_imports(self.fakekit('failure')):
                raise primary
        self.assertIs(raised.exception, primary)
        self.assertTrue(primary.cleanup_unknown)
        self.assertEqual((sys.path, sys.meta_path), before)
        self.assertNotIn('synthetic_kit_module', sys.modules)
        self.assertNotIn(SECRET, m.safe_error(primary))


class FixedReadsTests(unittest.TestCase):
    """Boundary mocks test protected read/control flow, never compiler claims."""
    def read_boundary(self, mutation=None, compiler_change=False, compile_error=None, recheck_error=None):
        observation = {'fixture': SECRET}
        raws = [packed({'schema': 2, 'seed': {'observation': observation}}),
                packed({'schema': 1, 'seed': {'observation': observation}}),
                packed({'fixture': 'SYNTHETIC_PLAN'}), packed({'fixture': 'SYNTHETIC_PACKET'})]
        initial = [(raw, m.stamp(info(st_ino=index + 3, st_size=len(raw)))) for index, raw in enumerate(raws)]
        source = (b'SYNTHETIC_ENTRY_BYTES', m.stamp(info(st_mode=stat.S_IFREG | 0o444)))
        reads = [source] + initial + initial + [source]
        if mutation is not None:
            index, replace = mutation
            reads[index] = replace(reads[index])
        kit = types.SimpleNamespace(cache={'fixture.py': b'pass\n'}, raw_manifest=b'MANIFEST', manifest={'modules': {}})
        again = types.SimpleNamespace(cache=dict(kit.cache), raw_manifest=kit.raw_manifest)
        if compiler_change:
            again.cache['fixture.py'] = b'changed\n'
        entry = types.SimpleNamespace(decode=lambda raw: json.loads(raw.decode('utf-8')),
                                      verify_kit=Mock(side_effect=[kit, again]))
        directory = info(st_mode=stat.S_IFDIR | 0o755)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(m, 'cold_uuid_parser'))
            stack.enter_context(patch.object(m, 'open_chain', return_value=([9], [], 9)))
            opened = stack.enter_context(patch.object(m.os, 'open', return_value=10))
            stack.enter_context(patch.object(m, 'directory', return_value=m.stamp(directory)))
            stack.enter_context(patch.object(m.os, 'stat', return_value=directory))
            reader = stack.enter_context(patch.object(m, 'read_exact', side_effect=reads))
            stack.enter_context(patch.object(m, 'module_bytes', return_value=entry))
            stack.enter_context(patch.object(m, 'register_codes'))
            checked = stack.enter_context(patch.object(m, 'check_kit'))
            compiler = stack.enter_context(patch.object(m, 'compile_proof', return_value={'synthetic_boundary': True}, side_effect=compile_error))
            recheck = stack.enter_context(patch.object(m, 'recheck', side_effect=recheck_error))
            close = stack.enter_context(patch.object(m, 'close_all'))
            stack.enter_context(patch.object(m, 'OBSERVATION_SHA', m.sha(m.canonical(observation))))
            try:
                report = m.protected_validate()
            except BaseException as error:
                close.assert_called_once_with([9, 10], error)
                raise
            return report, reader, opened, checked, compiler, recheck, close, entry

    def test_exact_eight_private_reads_final_entry_and_second_kit_verification(self):
        report, read, opened, checked, compiler, recheck, close, entry = self.read_boundary()
        expected_entry = call(10, 'epoch7_recovery_entry.py', m.ENTRY_BYTES, m.ENTRY_SHA, private=False)
        expected_inputs = [call(9, leaf, size, pin) for role, leaf, size, pin in m.INPUTS]
        self.assertEqual(read.call_args_list, [expected_entry] + expected_inputs * 2 + [expected_entry])
        opened.assert_called_once_with(m.COMPILER_LEAF, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=9)
        self.assertEqual(entry.verify_kit.call_args_list, [call(m.COMPILER_ROOT, m.MANIFEST_SHA)] * 2)
        self.assertEqual(checked.call_count, 2)
        compiler.assert_called_once()
        self.assertEqual(recheck.call_count, 2)
        close.assert_called_once_with([9, 10], None)
        self.assertEqual([row['role'] for row in report['files']], ['new_seed', 'old_seed', 'plan', 'packet'])
        for row in report['files']:
            self.assertEqual(set(row), set(FORMAT['file_row_keys']))
            self.assertEqual(set(row['metadata']), set(FORMAT['file_metadata_keys']))
            self.assertTrue(row['reread_match'])
            self.assertEqual(row['authority'], FORMAT['file_authority'])

    def test_each_final_private_read_and_entry_content_or_metadata_drift_refuses(self):
        for index in (5, 6, 7, 8, 9):
            for change in (lambda pair: (pair[0] + b'X', pair[1]),
                           lambda pair: (pair[0], ('CHANGED_METADATA',))):
                with self.subTest(index=index), self.assertRaisesRegex(m.Hold, '^FINAL_CONTENT$'):
                    self.read_boundary(mutation=(index, change))

    def test_final_kit_and_ancestry_drift_refuse(self):
        with self.assertRaisesRegex(m.Hold, '^COMPILER_CHANGED$'):
            self.read_boundary(compiler_change=True)
        with self.assertRaisesRegex(m.Hold, '^PATH_IDENTITY$'):
            self.read_boundary(recheck_error=[None, m.Hold('PATH_IDENTITY')])

    def test_compile_exception_preserves_primary_and_closes_descriptors(self):
        for error in (RuntimeError(SECRET), KeyboardInterrupt(SECRET), m.Deadline(SECRET)):
            with self.subTest(error=type(error).__name__), self.assertRaises(type(error)) as raised:
                self.read_boundary(compile_error=error)
            self.assertIs(raised.exception, error)


class OutputTests(unittest.TestCase):
    def run_main(self, report=None, error=None, output_error=None, identity=None, real_budget=False):
        identity = identity if identity is not None else ('a' * 64, 40000)
        events = []
        def output(raw):
            events.append(('emit', m.signal.getitimer(signal.ITIMER_REAL)))
            if output_error:
                raise output_error
        with contextlib.ExitStack() as stack:
            budgets = None if real_budget else stack.enter_context(patch.object(m, 'budget', side_effect=no_budget))
            stack.enter_context(patch.object(m, 'require_binding'))
            stack.enter_context(patch.object(m, 'SCHEMA_SHA', 'b' * 64))
            stack.enter_context(patch.object(m.os, 'geteuid', return_value=0))
            stack.enter_context(patch.object(m.os, 'getegid', return_value=0))
            stack.enter_context(patch.object(m.socket, 'gethostname', return_value=m.HOST))
            validate = stack.enter_context(patch.object(m, 'protected_validate',
                return_value=copy.deepcopy(report or {'schema': 1, 'state': 'SYNTHETIC_BOUNDARY_ONLY'}), side_effect=error))
            emit = stack.enter_context(patch.object(m, 'emit', side_effect=output))
            result = m.main(*identity)
        return result, emit, validate, budgets, events

    def test_complete_bounded_single_gzip_ready_before_emission_and_timer_restored(self):
        old_handler, old_timer = signal.getsignal(signal.SIGALRM), signal.getitimer(signal.ITIMER_REAL)
        self.assertEqual(old_timer, (0.0, 0.0))
        result, emit, validate, budgets, events = self.run_main(real_budget=True)
        self.assertEqual(result, 0)
        emit.assert_called_once(); validate.assert_called_once()
        self.assertEqual(events, [('emit', (0.0, 0.0))])
        self.assertEqual(signal.getsignal(signal.SIGALRM), old_handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), old_timer)
        raw = emit.call_args[0][0]
        self.assertLessEqual(len(raw), m.MAX_OUTPUT)
        transport = json.loads(raw)
        compressed = base64.b64decode(transport['payload_base64'], validate=True)
        z = m.zlib.decompressobj(16 + m.zlib.MAX_WBITS)
        inner = z.decompress(compressed)
        self.assertTrue(z.eof)
        self.assertFalse(z.unused_data or z.unconsumed_tail)
        self.assertEqual(len(compressed), transport['compressed_bytes'])
        self.assertEqual(m.sha(compressed), transport['compressed_sha256'])
        self.assertEqual(len(inner), transport['uncompressed_bytes'])
        self.assertEqual(m.sha(inner), transport['uncompressed_sha256'])
        report = json.loads(inner)
        self.assertEqual(report['runtime']['cleanup'], 'COMPLETED')
        self.assertEqual(report['runtime']['scope'], FORMAT['runtime_scope'])
        self.assertEqual(report['runtime']['call_path'], FORMAT['runtime_call_path'])
        self.assertEqual(report['runtime']['validator'], {'sha256': 'a' * 64, 'bytes': 40000})

    def test_error_hold_sanitizes_unknown_private_messages_and_preserves_known_codes(self):
        cases = [(RuntimeError(SECRET + '_/secret/path'), 'OTHER'),
                 (m.Hold(SECRET), 'OTHER'), (m.Hold('FILE_HASH'), 'FILE_HASH'),
                 (m.Deadline(SECRET), 'DEADLINE'), (KeyboardInterrupt(SECRET), 'INTERRUPTED'),
                 (SystemExit(SECRET), 'INTERRUPTED')]
        for error, expected in cases:
            with self.subTest(error=type(error).__name__):
                result, emit, validate, budgets, events = self.run_main(error=error)
                self.assertEqual(result, 2); emit.assert_called_once(); validate.assert_called_once()
                raw = emit.call_args[0][0]
                self.assertNotIn(SECRET.encode('ascii'), raw)
                self.assertNotIn(b'Traceback', raw)
                report = json.loads(raw)
                self.assertEqual(report['code'], expected)
                self.assertEqual(report['state'], 'HOLD')
                self.assertFalse(report['private_contents_emitted'])
                self.assertEqual(report['install_admission'], 'NOT_GRANTED')
                budgets.assert_called_once_with(120)

    def test_bad_validator_identity_refuses_before_private_read(self):
        for identity in ((None, None), ('x' * 64, 1), ('a' * 64, True), ('a' * 64, 0), ('a' * 64, 524289)):
            with self.subTest(identity=identity):
                result, emit, validate, budgets, events = self.run_main(identity=identity)
                self.assertEqual(result, 2); validate.assert_not_called()
                self.assertEqual(json.loads(emit.call_args[0][0])['code'], 'VERIFIER_IDENTITY')

    def test_emission_failure_never_emits_second_record_or_retries(self):
        for error in (m.OutputFailed(), OSError(SECRET), m.Deadline()):
            with self.subTest(error=type(error).__name__):
                result, emit, validate, budgets, events = self.run_main(output_error=error)
                self.assertEqual(result, 2); emit.assert_called_once(); validate.assert_called_once()

    def test_gzip_raw_compressed_and_wire_bounds_refuse_before_success_emit(self):
        for name, code in (('MAX_PROOF', 'PROOF_BOUND'), ('MAX_GZIP', 'COMPRESSED_BOUND'), ('MAX_OUTPUT', 'OUTPUT_BOUND')):
            with self.subTest(bound=name), patch.object(m, name, 1), self.assertRaisesRegex(m.Hold, '^' + code + '$'):
                m.encode_evidence({'fixture': 'x' * 1000})
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.assertRaises(ValueError):
                m.encode_evidence({'fixture': value})
        with patch.object(m, 'MAX_GZIP', 1):
            result, emit, validate, budgets, events = self.run_main()
            self.assertEqual(result, 2); emit.assert_called_once()
            self.assertEqual(json.loads(emit.call_args[0][0])['code'], 'COMPRESSED_BOUND')

    def test_emit_chunk_limit_partial_progress_and_short_or_failed_write(self):
        with patch.object(m, 'budget', side_effect=no_budget) as budgets, patch.object(m.os, 'write', side_effect=[2, 1]) as write:
            m.emit(b'abc')
        self.assertEqual(write.call_args_list, [call(1, b'abc'), call(1, b'c')])
        budgets.assert_called_once_with(10)
        for outcome in (0, -1, True, 4, OSError(SECRET), m.Deadline()):
            with self.subTest(outcome=type(outcome).__name__), patch.object(m, 'budget', side_effect=no_budget), patch.object(m.os, 'write', side_effect=outcome if isinstance(outcome, BaseException) else None, return_value=outcome) as write:
                with self.assertRaises(m.OutputFailed):
                    m.emit(b'abc')
                write.assert_called_once()
        with patch.object(m, 'budget', side_effect=no_budget), patch.object(m.os, 'write', side_effect=lambda fd, raw: len(raw)) as write:
            m.emit(b'a' * 40000)
            self.assertEqual([len(row[0][1]) for row in write.call_args_list], [16384, 16384, 7232])


class HiddenCommitmentTests(unittest.TestCase):
    def fixture(self):
        child_hash = hashlib.sha256(SECRET.encode('ascii')).hexdigest()
        factory = types.SimpleNamespace(_fingerprint=lambda value: child_hash, input_digest=lambda values: 'c' * 64)
        inputs = {name: SECRET for name in m.INPUT_FIELD_NAMES}
        return factory, inputs, child_hash

    def test_hmac_ephemeral_key_child_hash_and_secret_never_output(self):
        factory, inputs, child_hash = self.fixture()
        key, nonce = b'K' * 32, b'N' * 16
        with patch.object(m.os, 'urandom', side_effect=[key, nonce]) as random:
            proof = m.hidden_input_commitments(factory, inputs)
        self.assertEqual(random.call_args_list, [call(32), call(16)])
        raw = packed(proof)
        for prohibited in (key, key.hex().encode('ascii'), base64.b64encode(key), child_hash.encode('ascii'), SECRET.encode('ascii')):
            self.assertNotIn(prohibited, raw)
        self.assertEqual(set(proof), set(FORMAT['hidden_inputs_keys']))
        self.assertEqual(proof['key_disclosure'], FORMAT['hidden_key_disclosure'])
        self.assertEqual(proof['offline_binding'], FORMAT['hidden_offline_binding'])
        self.assertEqual(proof['input_field_names'], FORMAT['input_field_names'])
        self.assertEqual(len(set(proof['field_commitments'].values())), 37)

    def test_hmac_domain_nonce_seed_and_field_separation_are_in_preimage(self):
        factory, inputs, child_hash = self.fixture()
        key, nonce = b'K' * 32, b'N' * 16
        with patch.object(m.os, 'urandom', side_effect=[key, nonce]):
            proof = m.hidden_input_commitments(factory, inputs)
        for name in m.INPUT_FIELD_NAMES:
            fields = [FORMAT['hidden_domain'], nonce.hex(), m.INPUTS[0][3], m.INPUTS[1][3], name, child_hash]
            expected = m.hmac.new(key, m.canonical(fields), hashlib.sha256).hexdigest()
            self.assertEqual(proof['field_commitments'][name], expected)
            for index in (0, 1, 2, 3, 4):
                altered = list(fields); altered[index] += 'X'
                self.assertNotEqual(expected, m.hmac.new(key, m.canonical(altered), hashlib.sha256).hexdigest())
        with patch.object(m.os, 'urandom', side_effect=[b'L' * 32, nonce]):
            other = m.hidden_input_commitments(factory, inputs)
        self.assertNotEqual(proof['field_commitments'], other['field_commitments'])

    def test_hidden_fields_closed_and_bad_ephemeral_key_refuses(self):
        factory, inputs, child_hash = self.fixture()
        for malformed in (dict(inputs, secret=SECRET), {name: value for name, value in inputs.items() if name != m.INPUT_FIELD_NAMES[0]}):
            with self.assertRaisesRegex(m.Hold, '^INPUT_FIELDS$'):
                m.hidden_input_commitments(factory, malformed)
        for key in (b'K' * 31, b'K' * 33, 'K' * 32):
            with patch.object(m.os, 'urandom', side_effect=[key, b'N' * 16]), self.assertRaisesRegex(m.Hold, '^RANDOM_KEY$'):
                m.hidden_input_commitments(factory, inputs)
        for nonce in ('', 'a' * 31, 'A' * 32, 'g' * 32, 1, True):
            with self.subTest(nonce=nonce), self.assertRaisesRegex(m.Hold, '^RANDOM_NONCE$'):
                m.hidden_input_commitments(factory, inputs, key=b'K' * 32, nonce=nonce)


class ForbiddenEffect(BaseException):
    pass


@contextlib.contextmanager
def deny_effects():
    """Block application effects; retain documented fixed DB/socket metadata checks."""
    events = []
    def denied(label):
        def effect(*arguments, **keywords):
            events.append(label)
            raise ForbiddenEffect('FORBIDDEN_EFFECT_' + label)
        return effect
    targets = [(builtins, 'open'), (io, 'open'), (sqlite3, 'connect'),
               (socket, 'socket'), (socket, 'create_connection'), (socket, 'getaddrinfo'),
               (socket, 'gethostbyname'), (socket, 'gethostbyaddr'),
               (urllib.request, 'urlopen')]
    targets += [(subprocess, name) for name in ('Popen', 'run', 'call', 'check_call', 'check_output')]
    targets += [(os, name) for name in ('open', 'read', 'write', 'system', 'fork', 'execv',
        'execve', 'spawnv', 'spawnve', 'mkdir', 'makedirs', 'unlink', 'remove', 'rmdir',
        'rename', 'replace', 'chmod', 'chown', 'truncate', 'ftruncate', 'utime', 'link',
        'symlink', 'kill', 'killpg', 'setuid', 'setgid', 'setgroups') if hasattr(os, name)]
    with contextlib.ExitStack() as stack:
        for target, name in targets:
            stack.enter_context(patch.object(target, name, side_effect=denied(target.__name__ + '.' + name)))
        try:
            yield events
        finally:
            if events:
                raise ForbiddenEffect('EFFECT_ATTEMPTED_' + ','.join(events))



# Public resource fixture ingredients, already published independently. This
# embedded constructor imports definitions only; it does not run any old suite.
ARCHIVE = pathlib.Path(os.environ.get('EPOCH7_FIXED_SEED_TEST_ARCHIVE', str(
    HERE.parent / 'b-resource-aggregate-fix-candidate/artifact/epoch7-kit-resourcebind.tar.gz')))
ARCHIVE_SHA = '6244cca1b41037b7c240f71b93f867c5660a770d451c4a5a661b283f61ce819e'
MANIFEST_SHA = '6c269db1e20d3cab9877eaa6bde2240ad8a7ffaca3e183fd1180011a4e244030'
ROOT_NAME = 'epoch7-recovery-candidate-r7-resourcebind'
PREPARATION = pathlib.Path(os.environ.get('EPOCH7_FIXED_SEED_TEST_PREPARATION', str(
    HERE.parent / 'b-resource-aggregate-fix-candidate/binding-preparation')))
HISTORICAL_PIN_KEYS = ('NATIVE_CURRENT_SHA', 'RETAINED_NATIVE_SHA',
                       'NATIVE_ORIGINAL_SHA', 'NATIVE_ATTEMPT_SHA')

class OriginalSyntheticSeedFixture:
    """Extract for fixture generation, then compile only authenticated cache."""
    def __init__(self):
        preparation_pins = {
            'epoch7_prepare.py': (55833, '18d3c459bc14f4a3c00317c5a407d18178059209830763564dced41d9af945fd'),
            'epoch7_prepare_data.py': (13888, '71be3f9cb6a58c82083c029fad8f6ba2ba524451bc110443ed3423ef7c9364a1'),
            'epoch7_topology_projection.py': (36482, '0e9817a1474dc4e54cf1779c0b4c243cf16e6204cab3a25210a12e41e03d00b6')}
        for name, (size, digest) in preparation_pins.items():
            raw = (PREPARATION / name).read_bytes()
            if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
                raise AssertionError('public preparation fixture source changed')
        archive_raw = ARCHIVE.read_bytes()
        if hashlib.sha256(archive_raw).hexdigest() != ARCHIVE_SHA:
            raise AssertionError('selected public archive digest changed')
        self.temporary = tempfile.TemporaryDirectory(prefix='fixed-seed-fixture-')
        self.add_cleanup = self.temporary.cleanup
        materialized = pathlib.Path(self.temporary.name)
        with tarfile.open(fileobj=io.BytesIO(archive_raw), mode='r:gz') as archive:
            members = archive.getmembers()
            for item in members:
                path = pathlib.PurePosixPath(item.name)
                if path.parts[0] != ROOT_NAME or '..' in path.parts or not (item.isfile() or item.isdir()):
                    raise AssertionError('unsafe fixture archive member')
            if sys.version_info >= (3, 12):
                archive.extractall(str(materialized), filter='data')
            else:
                # Exact frozen archive hash and every member's regular-file/
                # directory type and confined path were checked above.
                archive.extractall(str(materialized))
        self.local_root = materialized / ROOT_NAME
        self.entry = loaded(self.local_root / 'epoch7_recovery_entry.py',
                                   'fixed_seed_test_actual_entry')
        self.raw_manifest = (self.local_root / 'recovery-kit-manifest.json').read_bytes()
        if hashlib.sha256(self.raw_manifest).hexdigest() != MANIFEST_SHA:
            raise AssertionError('selected kit manifest digest changed')
        self.manifest = json.loads(self.raw_manifest)
        self.cache = {name: (self.local_root / name).read_bytes() for name in self.manifest['files']}
        for name, raw in self.cache.items():
            expected = self.manifest['files'][name]
            pin = expected['sha256'] if isinstance(expected, dict) else expected
            if hashlib.sha256(raw).hexdigest() != pin:
                raise AssertionError('public fixture cache digest mismatch')
        self.entry.validate_manifest(self.manifest)
        # Fixture setup may read the disposable public archive. Those reads are
        # complete before the pure-validator no-effect sentinels are installed.
        self.kit = self.entry.VerifiedKit(self.entry.CANDIDATE_PARENT + '/' + ROOT_NAME,
            self.manifest, self.cache, MANIFEST_SHA, raw_manifest=self.raw_manifest)
        original_path, original_modules = list(sys.path), set(sys.modules)
        variables = {'EPOCH7_RESOURCE_TEST_KIT_ROOT': str(self.local_root),
                     'EPOCH7_RESOURCE_TEST_HELPERS': str(self.local_root / 'helpers'),
                     'EPOCH7_RESOURCE_TEST_PREPARATION_ROOT': str(PREPARATION)}
        try:
            with patch.dict(os.environ, variables):
                x = loaded(self.local_root / 'tests/host_factory/resource_aggregate_fixture.py',
                                  'fixed_seed_test_large_fixture')
                self.seed, tools = x.wrapper_seed()
                preparation, data, topology, unused_entry = x.wrapper_modules()
                # The legacy public full-factory fixture deliberately used
                # placeholder metadata for these raw buffers. Make synthetic
                # retained facts match their exact synthetic bytes, then rebind
                # all dependent observation/probe hashes using its real helper.
                observation = self.seed['observation']
                for name, path in data.RAW_PATHS.items():
                    raw = self.seed[name]
                    row = observation['evidence']['retained']['files'][path]
                    row.update(sha256=hashlib.sha256(raw).hexdigest(), size=len(raw))
                    observation['policy']['files'][path]['sha256'] = row['sha256']
                    prefix = x.factory.snap.TRANSACTION + '/'
                    if path.startswith(prefix):
                        observation['policy']['transaction_inventory'][path[len(prefix):]] = row['sha256']
                x.rebind_synthetic_observation(self.seed)
                inventory, proposal, review = x.synthetic_topology(topology)
                collected = {'observation': observation, 'compiled': self.seed['compiled'],
                    'buffers': {key: self.seed[key] for key in data.RAW_PATHS},
                    'manifest_raw': self.seed['source_manifest_raw'], 'source_payloads': self.seed['source_payloads'],
                    'tool_sources': tools, 'socket_dropins': inventory,
                    'fresh_unit_authority': {'schema': 1, 'kind': 'FRESH_R7_UNIT_DROPIN_AUTHORITY',
                        'saved_unit_dropins_sha256': data.sha(data.canonical(inventory)),
                        'units': {}, 'reread': 'EXACT_PRE_POST_AND_FINAL'},
                    'fresh_release_parent': copy.deepcopy(self.seed['fresh_release_parent'])}
                with x.native_pins(self.seed):
                    self.native_pins = {key: getattr(x.factory.snap, key) for key in HISTORICAL_PIN_KEYS}
                    self.bundle = preparation.compile_private_bundle(self.kit, collected,
                        proposal['topology_raw'], review, True, data)
        finally:
            sys.path[:] = original_path
            for name in set(sys.modules) - original_modules:
                candidate = sys.modules.get(name)
                filename = str(getattr(candidate, '__file__', ''))
                if filename.startswith((str(self.local_root), str(PREPARATION))):
                    sys.modules.pop(name, None)
        self.seed_raw = self.bundle['seed_raw']
        self.private = json.loads(self.seed_raw)['seed']


class LifecycleArchiveFixture:
    """Real exact lifecycle cache, inherited real production-shaped synthetic seed.

    Only unavailable historical native-byte pins and synthetic input-file pins
    are mapped in test scope. No compiler output, schema or factory is mocked.
    """
    def __init__(self):
        import tarfile
        self.original = OriginalSyntheticSeedFixture()
        self.cleanup = self.original.add_cleanup
        archive_path = pathlib.Path(os.environ.get('EPOCH7_PRIVATE_COMPLETENESS_ARCHIVE', str(
            HERE.parent / 'c-capability-lifecycle-candidate/artifact/epoch7-kit-claim-lifecycle.tar.gz')))
        archive_raw = archive_path.read_bytes()
        if m.sha(archive_raw) != 'bd3708d5887c4dc2b866e9e0acb04da426e71ad88d89c23fe2576b5ed943a2c3':
            raise AssertionError('selected exact lifecycle public archive changed')
        prefix = m.COMPILER_LEAF + '/'
        with tarfile.open(fileobj=io.BytesIO(archive_raw), mode='r:gz') as archive:
            self.manifest_raw = archive.extractfile(prefix + 'recovery-kit-manifest.json').read()
            self.manifest = json.loads(self.manifest_raw)
            self.cache = {name: archive.extractfile(prefix + name).read() for name in self.manifest['files']}
            for name, raw in self.cache.items():
                row = self.manifest['files'][name]
                pin = row['sha256'] if isinstance(row, dict) else row
                if m.sha(raw) != pin:
                    raise AssertionError('selected lifecycle cache hash changed')
            entry_info = archive.getmember(prefix + 'epoch7_recovery_entry.py')
            if entry_info.mode != 0o444:
                raise AssertionError('archive entry authority mode changed')
        if m.sha(self.manifest_raw) != m.MANIFEST_SHA:
            raise AssertionError('selected lifecycle manifest changed')
        self.entry = m.module_bytes(self.cache['epoch7_recovery_entry.py'], 'actual_lifecycle_fixture_entry')
        self.entry.validate_manifest(self.manifest)
        self.kit = self.entry.VerifiedKit(m.COMPILER_ROOT, self.manifest, self.cache,
            m.MANIFEST_SHA, raw_manifest=self.manifest_raw)
        m.check_kit(self.kit)
        self.old = {'schema': 1, 'seed': copy.deepcopy(self.original.private)}
        private = copy.deepcopy(self.old['seed'])
        with self.scope():
            claim = importlib.import_module('epoch7_claim_successor')
            factory = importlib.import_module('epoch7_host_factory')
            approval = importlib.import_module('epoch7_complete_approval')
            private['claim_successor'] = {'schema': 1, 'kind': 'EXACT_CLAIM_ONLY_SUCCESSOR',
                'timing_policy': claim.TIMING_POLICY, 'predecessor': claim.predecessor_contract(),
                'implementation': {'source_commit': m.SOURCE, 'source_tree': m.TREE,
                                   'kit_manifest_sha256': self.kit.digest},
                'admission_expires_at_utc': FORMAT['candidate']['admission_expires_at_utc'],
                'authorized_successors': 1, 'automatic_retry': False,
                'effect_scope': 'UNCHANGED_107_PAYLOADS_16_PHASES',
                'measured_predecessor_sha256': factory.d.digest('SYNTHETIC predecessor observation')}
            self.new = {'schema': 2, 'seed': private}
            hydrated = self.kit._hydrate_seed(private, factory)
            prepared = factory.prepare_host_inputs(hydrated)
            if prepared['state'] != 'COMPILED_NOT_ADMITTED':
                raise AssertionError('real synthetic lifecycle factory did not prepare')
            self.inputs = prepared['inputs']
            self.plan = factory.compile_host_contract(self.inputs)
            self.proposal = factory._proposal(self.inputs)
            plan_sha = m.sha(packed(self.plan))
            body = approval.expected_complete_from_inputs(plan_sha, self.proposal[1], self.proposal[2])
            self.packet = {'plan_sha256': plan_sha, 'seed_sha256': m.sha(packed(self.new)),
                'compiler_kit_manifest_sha256': self.kit.digest,
                'claim_successor': copy.deepcopy(private['claim_successor']),
                'fresh_release_parent': copy.deepcopy(private['fresh_release_parent']),
                'final_review_body': body, 'final_review_id': None, 'final_review_body_sha256': None}
        self.raws = [packed(self.new), packed(self.old), packed(self.plan), packed(self.packet)]
        self.pins = tuple((role, leaf, len(raw), m.sha(raw))
                          for (role, leaf, size, pin), raw in zip(m.INPUTS, self.raws))
        self.schema_raw = (HERE / 'evidence_schema.py').read_bytes()
        self.candidate = dict(FORMAT['candidate'], plan_sha256=self.pins[2][3],
            packet_sha256=self.pins[3][3], body_bytes=len(m.canonical(body)), body_sha256=m.sha(m.canonical(body)))

    @contextlib.contextmanager
    def scope(self):
        with self.entry.VerifiedKit.imports(self.kit) as importer:
            snapshot = importlib.import_module('epoch7_snapshot')
            with patch.multiple(snapshot, **self.original.native_pins):
                yield importer

    @contextlib.contextmanager
    def synthetic_pins(self):
        with patch.object(m, 'INPUTS', self.pins), \
             patch.object(m, 'BODY_SHA', self.candidate['body_sha256']), \
             patch.object(m, 'BODY_BYTES', self.candidate['body_bytes']), \
             patch.object(m, 'EXPECTED_CANDIDATE', self.candidate), \
             patch.object(m, 'SCHEMA_SHA', m.sha(self.schema_raw)), \
             patch.object(m, 'SCHEMA_BYTES', len(self.schema_raw)), \
             patch.object(m, 'SCHEMA_B64', base64.b64encode(m.zlib.compress(self.schema_raw)).decode('ascii')):
            yield


UNSET = object()


class PureCompilationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = LifecycleArchiveFixture()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def proof(self, new=UNSET, old=UNSET, plan=UNSET, packet=UNSET):
        fixture = self.fixture
        @contextlib.contextmanager
        def guarded_scope():
            with fixture.scope() as importer, warnings.catch_warnings():
                warnings.simplefilter('ignore', DeprecationWarning)
                factory = importlib.import_module('epoch7_host_factory')
                targets = [(fixture.kit, 'resume'), (fixture.kit, '_authenticate_probe_receipt')]
                for name in ('assemble', 'compose', 'assemble_driver', 'assemble_host_driver', 'build_driver'):
                    if hasattr(factory, name):
                        targets.append((factory, name))
                with contextlib.ExitStack() as stack:
                    for target, name in targets:
                        stack.enter_context(patch.object(target, name, side_effect=ForbiddenEffect('FORBIDDEN_' + name)))
                    with deny_effects() as events:
                        yield importer
                    self.assertEqual(events, [])
        with fixture.synthetic_pins(), patch.object(fixture.kit, 'imports', guarded_scope):
            return m.compile_proof(fixture.entry, fixture.kit,
                copy.deepcopy(fixture.new) if new is UNSET else new,
                copy.deepcopy(fixture.old) if old is UNSET else old,
                copy.deepcopy(fixture.plan) if plan is UNSET else plan,
                copy.deepcopy(fixture.packet) if packet is UNSET else packet)

    def test_real_exact_archive_hydration_factory_schema_and_complete_output(self):
        fixture = self.fixture
        before = copy.deepcopy((fixture.new, fixture.old))
        with patch.object(fixture.kit, '_hydrate_seed', wraps=fixture.kit._hydrate_seed) as hydrate:
            report = self.proof()
        hydrate.assert_called_once()
        self.assertEqual(report['state'], FORMAT['state'])
        self.assertEqual(report['seed_inheritance'], FORMAT['seed_inheritance'])
        self.assertEqual(report['checks'], FORMAT['checks'])
        self.assertEqual(report['compiler'], FORMAT['compiler'])
        projected = report['preimages']
        self.assertEqual(projected['schema'], 2)
        self.assertEqual(set(projected['withheld']), {'retained_delta', 'access_rows', 'acceptance_contract', 'resource_views'})
        self.assertEqual(len(projected['coverage']['targets']), 24)
        self.assertEqual(len(projected['coverage']['resource_section_counts']), 17)
        self.assertTrue(all(len(point) == 15 for point in projected['coverage']['resource_section_counts']))
        self.assertEqual(projected['context']['session_nonce'], report['hidden_inputs']['session_nonce'])
        onsite_only = ['acceptance_contract_sha256', 'complete_delta_sha256',
                       'delta_sha256', 'security_delta_sha256', 'views_sha256']
        self.assertEqual(projected['onsite_only_roots'], onsite_only)
        for opaque in projected['withheld'].values():
            self.assertEqual(opaque['offline_recomputation'], 'NOT_AVAILABLE')
            self.assertEqual(opaque['original_preimage'], 'NOT_EXPORTED')
        self.assertEqual(report['hidden_inputs']['input_root_sha256'], fixture.plan['host_contract']['input_sha256'])
        self.assertEqual((fixture.new, fixture.old), before)
        self.assertEqual(len(fixture.cache), 256)
        self.assertEqual(len(fixture.inputs['source_payloads']), 107)
        self.assertFalse(set(fixture.manifest['modules']) & set(sys.modules))
        # Compose the actual compiler/schema report with the real producer main
        # transport and the independent offline verifier. Only saved-file pins
        # and descriptor metadata are synthetic; no compiler/schema is mocked.
        report['files'] = []
        for index, (role, name, size, pin) in enumerate(fixture.pins):
            report['files'].append({'role': role, 'name': name, 'bytes': size,
                'sha256': pin, 'reread_match': True, 'authority': FORMAT['file_authority'],
                'metadata': {'dev': 1, 'ino': index + 10, 'uid': 0, 'gid': 0,
                    'mode': 0o600, 'nlink': 1, 'size': size, 'mtime_ns': 123, 'ctime_ns': 456}})
        print('SYNTHETIC_PREIMAGE_SIZE ' + json.dumps({
            'preimage_bytes': len(m.canonical(report['preimages'])),
            'preimage_gzip_bytes': len(deterministic_gzip(m.canonical(report['preimages']))),
            'proof_bytes_before_runtime': len(packed(report)),
            'proof_gzip_bytes_before_runtime': len(deterministic_gzip(packed(report)))}), flush=True)
        producer_raw = PATH.read_bytes()
        with fixture.synthetic_pins(), patch.object(m, 'protected_validate', return_value=report), \
             patch.object(m.os, 'geteuid', return_value=0), patch.object(m.os, 'getegid', return_value=0), \
             patch.object(m.socket, 'gethostname', return_value=m.HOST), patch.object(m, 'emit') as emit:
            status = m.main(m.sha(producer_raw), len(producer_raw))
            emit.assert_called_once()
            self.assertEqual(status, 0, emit.call_args[0][0][:512])
            wire = emit.call_args[0][0]
        verifier = loaded(HERE / 'verify_evidence.py', 'independent_composed_test_verifier')
        verifier_pins = dict(PLAN_BYTES=fixture.pins[2][2], PLAN_SHA256=fixture.pins[2][3],
            PACKET_BYTES=fixture.pins[3][2], PACKET_SHA256=fixture.pins[3][3],
            NEW_SEED_BYTES=fixture.pins[0][2], NEW_SEED_SHA256=fixture.pins[0][3],
            OLD_SEED_BYTES=fixture.pins[1][2], OLD_SEED_SHA256=fixture.pins[1][3],
            BODY_BYTES=fixture.candidate['body_bytes'], BODY_SHA256=fixture.candidate['body_sha256'],
            EXPECTED_FILES=[list(row) for row in fixture.pins], EXPECTED_CANDIDATE=fixture.candidate)
        with tempfile.TemporaryDirectory(prefix='completeness-offline-package-') as folder:
            package = pathlib.Path(folder)
            files = []
            for name, source in (('validate_private_completeness.py', producer_raw),
                                 ('evidence_schema.py', fixture.schema_raw)):
                (package / name).write_bytes(source)
                files.append({'path': name, 'bytes': len(source), 'sha256': m.sha(source)})
            (package / 'SOURCE_MANIFEST.json').write_bytes(packed({'schema': 1, 'files': files}))
            with patch.multiple(verifier, **verifier_pins):
                independent = verifier.verify_evidence(verifier.decode_evidence(wire),
                    fixture.raws[2], fixture.raws[3], package_directory=str(package))
        self.assertEqual(independent['status'], 'PASS_VISIBLE_PREIMAGES_AND_OWNER_REPORT_STRUCTURE')
        self.assertFalse(independent['remote_attestation'])
        self.assertEqual(independent['opaque_segment_commitments'], 4)
        self.assertEqual(independent['retained_target_coverage'], 24)
        self.assertEqual(independent['onsite_only_roots'], onsite_only)
        self.assertFalse(independent['resource_views_recomputed_offline'])
        self.assertEqual(independent['install_admission'], 'NOT_GRANTED')
        transport = json.loads(wire)
        raw = gzip.decompress(base64.b64decode(transport['payload_base64']))
        self.assertEqual(json.loads(raw), report)
        self.assertLessEqual(len(wire), m.MAX_OUTPUT)
        print('SYNTHETIC_PRIVATE_COMPLETENESS_MEASUREMENTS ' + json.dumps({
            'new_seed_bytes': len(fixture.raws[0]), 'old_seed_bytes': len(fixture.raws[1]),
            'plan_bytes': len(fixture.raws[2]), 'packet_bytes': len(fixture.raws[3]),
            'raw_proof_bytes': len(raw), 'gzip_bytes': transport['compressed_bytes'],
            'wire_bytes': len(wire), 'actual_private_seed_available': False}, sort_keys=True))

    def test_success_proof_never_discloses_private_raw_buffers_or_child_fingerprints(self):
        report = self.proof()
        raw = packed(report)
        for name in m.RAW_NAMES:
            self.assertFalse(self.fixture.new['seed'][name].encode('utf-8') in raw, 'raw private buffer disclosed: ' + name)
        for value in self.fixture.new['seed']['identity_payloads'].values():
            self.assertFalse(value.encode('utf-8') in raw, 'raw identity payload disclosed')
        self.assertNotIn(b'"source_payloads":{', raw)
        self.assertNotIn(b'"rendered_targets":', raw)
        self.assertFalse(self.fixture.inputs['installer_source'] in raw, 'raw installer source disclosed')
        # Sensitive nested hashes must not become offline dictionary oracles.
        # These are taken from untouched real factory inputs, not the projected
        # report, so omission is tested independently of projection internals.
        sensitive = set()
        credential_prefix = '/etc/xuanjun-owner-callback/'
        private_prefixes = (credential_prefix, '/etc/xuanjun-development/',
                            '/home/xuanjun/', '/home/xuanjun_dev/', '/var/lib/xuanjun-development/service-home/.config/')
        for view in self.fixture.inputs['resource_views']:
            for rows in view.values():
                for row in rows:
                    path = row.get('path', '')
                    private_path = path.startswith(private_prefixes) and path not in self.fixture.entry.IDENTITY_PATHS
                    if (row.get('kind') == 'SANDBOX_STABLE' or private_path) and type(row.get('sha256')) is str:
                        sensitive.add(row['sha256'])
        acceptance = self.fixture.proposal[8]
        for access in acceptance['access']:
            for row in access['paths']:
                if row['path'].startswith(credential_prefix) and type(row.get('sha256')) is str:
                    sensitive.add(row['sha256'])
        digest_keys = {'config_sha256', 'profile_sha256', 'config_identity_sha256', 'expected_profile_sha256'}
        pending = [self.fixture.proposal[1], self.fixture.inputs['resource_views']]
        while pending:
            value = pending.pop()
            if type(value) is dict:
                for name, child in value.items():
                    if name in digest_keys and type(child) is str:
                        sensitive.add(child)
                    else:
                        pending.append(child)
            elif type(value) in (list, tuple):
                pending.extend(value)
        self.assertGreaterEqual(len(sensitive), 8)
        for digest in sensitive:
            self.assertFalse(digest.encode('ascii') in raw, 'known sensitive nested digest disclosed')
        with self.fixture.scope():
            factory = importlib.import_module('epoch7_host_factory')
            for name in ('native_before', 'source_payloads', 'installer_source', 'identity_payloads'):
                fingerprint = factory._fingerprint(self.fixture.inputs[name])
                self.assertFalse(m.canonical(fingerprint) in raw, 'raw child fingerprint disclosed: ' + name)

    def test_new_and_old_closed_envelopes_type_confusion_and_missing_fields_refuse(self):
        for target, schema_number, code in (('new', 2, 'FIXED_SEED_SCHEMA'), ('old', 1, 'OLD_SEED_SCHEMA')):
            original = getattr(self.fixture, target)
            cases = [None, [], dict(original, extra=SECRET), dict(original, schema=True),
                     dict(original, schema=float(schema_number)), dict(original, seed={})]
            for name in original['seed']:
                changed = copy.deepcopy(original); changed['seed'].pop(name); cases.append(changed)
            for changed in cases:
                with self.subTest(target=target), self.assertRaisesRegex(m.Hold, '^' + code + '$'):
                    self.proof(**{target: changed})

    def test_every_inherited_field_mutation_refuses_before_factory(self):
        for name in self.fixture.old['seed']:
            changed = copy.deepcopy(self.fixture.new)
            changed['seed'][name] = {'injected': SECRET}
            with self.subTest(field=name), self.assertRaisesRegex(m.Hold, '^OLD_NEW_FIELDS_CHANGED$'):
                self.proof(new=changed)
        old = copy.deepcopy(self.fixture.old)
        old['seed']['activate_retained_renewal_timer'] = 1
        with self.assertRaisesRegex(m.Hold, '^OLD_NEW_FIELDS_CHANGED$'):
            self.proof(old=old)

    def test_claim_packet_plan_and_body_mutations_hold(self):
        for name, value in (('claim_successor', {}), ('plan_sha256', '0' * 64),
                            ('seed_sha256', '0' * 64), ('final_review_id', 1),
                            ('final_review_body_sha256', '0' * 64), ('final_review_body', {SECRET: True})):
            changed = copy.deepcopy(self.fixture.packet); changed[name] = value
            with self.subTest(field=name), self.assertRaisesRegex(m.Hold, '^FIXED_INPUT_BINDING$'):
                self.proof(packet=changed)
        changed = copy.deepcopy(self.fixture.packet)
        changed['claim_successor']['authorized_successors'] = True
        with self.assertRaisesRegex(m.Hold, '^FIXED_INPUT_BINDING$'):
            self.proof(packet=changed)
        plan = copy.deepcopy(self.fixture.plan)
        plan['resource_observer']['views_sha256'] = '0' * 64
        with self.assertRaisesRegex(m.Hold, '^EXACT_PLAN_MISMATCH$'):
            self.proof(plan=plan)

    def test_matched_private_raw_mutation_and_secret_injection_fail_without_leak(self):
        for name in sorted(m.RAW_NAMES):
            new, old = copy.deepcopy(self.fixture.new), copy.deepcopy(self.fixture.old)
            new['seed'][name] += SECRET
            old['seed'][name] += SECRET
            with self.subTest(field=name), self.assertRaisesRegex(m.Hold, '^RAW_OBSERVATION_BINDING$') as raised:
                self.proof(new=new, old=old)
            self.assertNotIn(SECRET, m.safe_error(raised.exception))
        new, old = copy.deepcopy(self.fixture.new), copy.deepcopy(self.fixture.old)
        new['seed']['compiled']['private_injection'] = SECRET
        old['seed']['compiled']['private_injection'] = SECRET
        with self.assertRaises(Exception) as raised:
            self.proof(new=new, old=old)
        self.assertNotIn(SECRET, m.safe_error(raised.exception))

    def test_exact_public_kit_identity_refuses_changed_source_root_manifest_and_cache(self):
        fixture = self.fixture
        changes = [('root', fixture.kit.root + '-other'), ('digest', '0' * 64),
                   ('manifest', dict(fixture.manifest, kit_source_commit='0' * 40)),
                   ('manifest', dict(fixture.manifest, kit_source_tree='0' * 40)),
                   ('cache', dict(fixture.cache, extra=SECRET.encode('ascii')))]
        for attribute, value in changes:
            with self.subTest(attribute=attribute), patch.object(fixture.kit, attribute, value), self.assertRaisesRegex(m.Hold, '^FIXED_COMPILER$'):
                m.check_kit(fixture.kit)


if __name__ == '__main__':
    unittest.main(verbosity=2)
