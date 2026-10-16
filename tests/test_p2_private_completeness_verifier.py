"""Local synthetic tests; no saved Seed, host operation, or secret fixture."""
import base64
import copy
import gzip
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verify_evidence as verifier


def gzip_bytes(raw):
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode='wb', mtime=0) as handle:
        handle.write(raw)
    return stream.getvalue()


def envelope(raw, compressed=None):
    if compressed is None:
        compressed = gzip_bytes(raw)
    return {'format': verifier.ENVELOPE_FORMAT,
            'uncompressed_bytes': len(raw),
            'uncompressed_sha256': verifier.sha256(raw),
            'compressed_bytes': len(compressed),
            'compressed_sha256': verifier.sha256(compressed),
            'payload_base64': base64.b64encode(compressed).decode('ascii')}


class TransportTests(unittest.TestCase):
    def encode(self, value):
        return verifier.canonical(value) + b'\n'

    def reject(self, raw):
        with self.assertRaises(verifier.Hold):
            verifier.decode_evidence(raw)

    def test_raw_object_and_single_trailing_lf(self):
        self.assertEqual(verifier.decode_evidence(b'{"schema":1}\n'), {'schema': 1})

    def test_exact_single_gzip(self):
        raw = b'{"schema":1}'
        self.assertEqual(verifier.decode_evidence(self.encode(envelope(raw))), {'schema': 1})

    def test_duplicate_keys_any_depth(self):
        for raw in (b'{"schema":1,"schema":1}', b'{"x":{"y":1,"y":2}}'):
            self.reject(raw)

    def test_multiple_json_and_trailing_bytes(self):
        for suffix in (b'{}', b'null', b'garbage', b'\x00'):
            self.reject(b'{"schema":1}' + suffix)

    def test_non_object_root(self):
        for raw in (b'[]', b'null', b'true', b'0', b'"text"'):
            self.reject(raw)

    def test_non_finite_and_float_rejected(self):
        for value in (b'NaN', b'Infinity', b'-Infinity', b'1.0', b'1e0'):
            self.reject(b'{"x":' + value + b'}')

    def test_integer_size_bound(self):
        for value in (str(2 ** 63), str(-(2 ** 63) - 1), '1' * 100):
            self.reject(('{"x":' + value + '}').encode('ascii'))

    def test_invalid_unicode_and_surrogate(self):
        for raw in (b'{"x":"\xff"}', b'{"x":"\\ud800"}', b'\xef\xbb\xbf{}'):
            self.reject(raw)

    def test_depth_bound(self):
        self.reject(b'{"x":' + b'[' * 65 + b'0' + b']' * 65 + b'}')

    def test_string_escapes_do_not_count_as_nesting(self):
        value = {'x': '"[\\{]"'}
        self.assertEqual(verifier.decode_evidence(self.encode(value)), value)

    def test_missing_extra_envelope_fields(self):
        value = envelope(b'{}')
        missing = dict(value)
        del missing['compressed_sha256']
        extra = dict(value, secret='NEVER_PRINT_THIS')
        self.reject(self.encode(missing))
        self.reject(self.encode(extra))

    def test_wrong_transport_format(self):
        value = envelope(b'{}')
        value['format'] = 'UNKNOWN'
        self.reject(self.encode(value))

    def test_type_confusion(self):
        for key in ('compressed_bytes', 'uncompressed_bytes'):
            value = envelope(b'{}')
            value[key] = True
            self.reject(self.encode(value))

    def test_bad_digest_and_payload(self):
        for key in ('compressed_sha256', 'uncompressed_sha256'):
            value = envelope(b'{}')
            value[key] = '0' * 64
            self.reject(self.encode(value))
        value = envelope(b'{}')
        value['payload_base64'] = '!' * len(value['payload_base64'])
        self.reject(self.encode(value))

    def test_base64_whitespace_and_bad_padding(self):
        value = envelope(b'{}')
        value['payload_base64'] += '\n'
        self.reject(self.encode(value))
        value = envelope(b'{}')
        value['payload_base64'] = value['payload_base64'][:-1] + '!'
        self.reject(self.encode(value))

    def test_gzip_multiple_members_trailing_and_truncation(self):
        raw = b'{"schema":1}'
        compressed = gzip_bytes(raw)
        for changed in (compressed + gzip_bytes(b'{}'),
                        compressed + b'\x00', compressed[:-1], compressed[:-8]):
            self.reject(self.encode(envelope(raw, changed)))

    def test_gzip_declared_length_mismatch(self):
        for change in (-1, 1):
            value = envelope(b'{"schema":1}')
            value['uncompressed_bytes'] += change
            self.reject(self.encode(value))

    def test_nested_envelope(self):
        self.reject(self.encode(envelope(self.encode(envelope(b'{}')))))

    def test_compressed_bound(self):
        value = envelope(b'{}')
        value['compressed_bytes'] = verifier.MAX_GZIP_BYTES + 1
        self.reject(self.encode(value))

    def test_raw_bound(self):
        with mock.patch.object(verifier, 'MAX_INPUT_BYTES', 8):
            self.reject(b'{"schema":1}')

    def test_wire_bound(self):
        raw = self.encode(envelope(b'{}'))
        with mock.patch.object(verifier, 'MAX_WIRE_BYTES', len(raw) - 1):
            self.reject(raw)

    def test_expansion_bound(self):
        value = envelope(b'{"x":"' + b'a' * 1000 + b'"}')
        value['uncompressed_bytes'] = 10
        self.reject(self.encode(value))

    def test_inner_duplicate_rejected(self):
        self.reject(self.encode(envelope(b'{"x":1,"x":2}')))


class FileAndOutputTests(unittest.TestCase):
    def test_regular_read_and_final_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'one.json'
            path.write_bytes(b'{}')
            self.assertEqual(verifier.read_local(str(path), 20), b'{}')
            link = pathlib.Path(directory) / 'link'
            link.symlink_to(path)
            with self.assertRaises(verifier.Hold):
                verifier.read_local(str(link), 20)

    def test_fifo_refused_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'fifo')
            os.mkfifo(path)
            with self.assertRaises(verifier.Hold):
                verifier.read_local(path, 20)

    def test_file_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'one.json'
            path.write_bytes(b'12345')
            with self.assertRaises(verifier.Hold):
                verifier.read_local(str(path), 4)

    def test_usage_is_bounded_no_private_argument_echo(self):
        writes = []
        def output(fd, raw):
            writes.append((fd, raw))
            return len(raw)
        status = verifier.run_cli(['VERY_PRIVATE_ARGUMENT'], writer=output)
        self.assertEqual(status, 1)
        self.assertEqual(len(writes), 1)
        self.assertNotIn(b'VERY_PRIVATE', writes[0][1])
        self.assertLessEqual(len(writes[0][1]), verifier.MAX_OUTPUT_BYTES)

    def test_failed_output_is_not_retried(self):
        writes = []
        def output(fd, raw):
            writes.append(raw)
            raise OSError('DO_NOT_PRINT_EXCEPTION_OR_RETRY')
        self.assertEqual(verifier.run_cli([], writer=output), 3)
        self.assertEqual(len(writes), 1)

    def test_short_output_is_not_retried(self):
        writes = []
        def output(fd, raw):
            writes.append(raw)
            return len(raw) - 1
        self.assertEqual(verifier.run_cli([], writer=output), 3)
        self.assertEqual(len(writes), 1)

    def test_unexpected_exception_is_not_echoed(self):
        writes = []
        def output(fd, raw):
            writes.append(raw)
            return len(raw)
        with mock.patch.object(verifier, 'read_local', side_effect=RuntimeError('PRIVATE_SENTINEL')):
            self.assertEqual(verifier.run_cli(['a', '--plan', 'b', '--packet', 'c'], writer=output), 1)
        self.assertEqual(len(writes), 1)
        self.assertNotIn(b'PRIVATE_SENTINEL', writes[0])

    def test_reference_hash_checked_before_json(self):
        with mock.patch.object(verifier, 'strict_json') as decoder:
            with self.assertRaises(verifier.Hold):
                verifier.load_reference_pair(b'PRIVATE_NOT_JSON', b'{}')
        decoder.assert_not_called()


class RootContractTests(unittest.TestCase):
    """Root checks isolated from real reference/preimage validation on purpose."""
    def setUp(self):
        self.identity = {'validator': {'bytes': 1234, 'sha256': '4' * 64},
                         'schema_source_sha256': '5' * 64}
        self.plan = {'host_contract': {'input_sha256': '6' * 64}}
        self.evidence = {
            'schema': 1, 'kind': verifier.KIND, 'state': verifier.STATE,
            'compiler': copy.deepcopy(verifier.EXPECTED_COMPILER),
            'files': [],
            'seed_inheritance': copy.deepcopy(verifier.EXPECTED_INHERITANCE),
            'candidate': copy.deepcopy(verifier.EXPECTED_CANDIDATE),
            'hidden_inputs': {
                'scheme': verifier.HIDDEN_SCHEME, 'domain': verifier.HIDDEN_DOMAIN,
                'session_nonce': '7' * 32, 'input_root_sha256': '6' * 64,
                'input_field_names': list(verifier.INPUT_FIELD_NAMES),
                'field_commitments': {name: verifier.sha256(name.encode('ascii'))
                                      for name in verifier.INPUT_FIELD_NAMES},
                'key_disclosure': verifier.HIDDEN_KEY_DISCLOSURE,
                'offline_binding': verifier.HIDDEN_OFFLINE_BINDING},
            'preimages': {'synthetic_unit_test_marker': True, 'context': {
                'session_nonce': '7' * 32, 'new_seed_sha256': verifier.NEW_SEED_SHA256,
                'old_seed_sha256': verifier.OLD_SEED_SHA256}},
            'checks': copy.deepcopy(verifier.EXPECTED_CHECKS),
            'runtime': {'validator': copy.deepcopy(self.identity['validator']),
                        'schema_source_sha256': self.identity['schema_source_sha256'],
                        'started_utc': '2026-10-16T16:00:00Z',
                        'finished_utc': '2026-10-16T16:00:01Z',
                        'scope': verifier.RUNTIME_SCOPE,
                        'additional_metadata_reads': list(verifier.RUNTIME_METADATA),
                        'call_path': list(verifier.RUNTIME_CALL_PATH),
                        'cleanup': verifier.RUNTIME_CLEANUP},
            'limitations': list(verifier.EXPECTED_LIMITATIONS)}
        for index, (role, name, size, digest) in enumerate(verifier.EXPECTED_FILES):
            self.evidence['files'].append({
                'role': role, 'name': name, 'bytes': size, 'sha256': digest,
                'metadata': {'dev': 1, 'ino': index + 1, 'uid': 0, 'gid': 0,
                             'mode': 0o600, 'nlink': 1, 'size': size,
                             'mtime_ns': 0, 'ctime_ns': 0},
                'reread_match': True, 'authority': verifier.FILE_AUTHORITY})

    def verify(self, evidence=None, preimage_result=None):
        callback = mock.Mock(return_value=synthetic_preimage_result() if preimage_result is None else preimage_result)
        with mock.patch.object(verifier, 'load_reference_pair', return_value=(self.plan, {}, {})), \
             mock.patch.object(verifier, 'load_verification_components', return_value=(self.identity, callback)):
            return verifier.verify_evidence(self.evidence if evidence is None else evidence,
                                            b'unit-test-plan', b'unit-test-packet')

    def reject(self, evidence=None):
        with self.assertRaises(verifier.Hold):
            self.verify(evidence)

    def test_root_accepts_closed_report_only_not_onsite_authenticity(self):
        result = self.verify()
        self.assertEqual(result['status'], 'PASS_VISIBLE_PREIMAGES_AND_OWNER_REPORT_STRUCTURE')
        self.assertFalse(result['remote_attestation'])
        self.assertFalse(result['current_host_state_verified'])
        self.assertIn('NOT_AUTHENTICATED', result['hidden_inputs'])
        self.assertNotIn('field_commitments', result)

    def test_each_root_section_required(self):
        for key in verifier.ROOT_KEYS:
            changed = copy.deepcopy(self.evidence)
            del changed[key]
            self.reject(changed)

    def test_extra_root_secret_rejected(self):
        for key in ('observation', 'sandbox_candidate_raw', 'compiled', 'identity_payloads', 'secret'):
            changed = copy.deepcopy(self.evidence)
            changed[key] = 'PRIVATE_SENTINEL'
            self.reject(changed)

    def test_wrong_compiler_pin_or_extra_field_rejected(self):
        changed = copy.deepcopy(self.evidence)
        changed['compiler']['manifest_sha256'] = '0' * 64
        self.reject(changed)
        changed = copy.deepcopy(self.evidence)
        changed['compiler']['source_code'] = 'PRIVATE_SENTINEL'
        self.reject(changed)

    def test_boolean_type_not_equal_integer(self):
        for section, key in (('checks', 'private_values_unchanged'),
                             ('seed_inheritance', 'claim_equals_packet')):
            changed = copy.deepcopy(self.evidence)
            changed[section][key] = 1
            self.reject(changed)
        changed = copy.deepcopy(self.evidence)
        changed['schema'] = True
        self.reject(changed)

    def test_bad_or_extra_file_metadata_rejected(self):
        for key, value in (('mode', 0o644), ('uid', 1000), ('nlink', 2),
                           ('ino', 0), ('size', 1), ('mtime_ns', -1)):
            changed = copy.deepcopy(self.evidence)
            changed['files'][0]['metadata'][key] = value
            self.reject(changed)
        changed = copy.deepcopy(self.evidence)
        changed['files'][0]['metadata']['raw_bytes'] = 'PRIVATE_SENTINEL'
        self.reject(changed)

    def test_file_count_order_name_and_reread(self):
        changed = copy.deepcopy(self.evidence)
        changed['files'].pop()
        self.reject(changed)
        changed = copy.deepcopy(self.evidence)
        changed['files'].reverse()
        self.reject(changed)
        changed = copy.deepcopy(self.evidence)
        changed['files'][0]['name'] = '../other-seed'
        self.reject(changed)
        changed = copy.deepcopy(self.evidence)
        changed['files'][0]['reread_match'] = False
        self.reject(changed)

    def test_raw_child_digests_and_hmac_key_rejected(self):
        for key in ('child_sha256', 'fingerprints', 'field_sha256', 'hmac_key', 'key'):
            changed = copy.deepcopy(self.evidence)
            changed['hidden_inputs'][key] = '8' * 64
            self.reject(changed)

    def test_missing_extra_and_malformed_hmac_rejected(self):
        for key, value in ((verifier.INPUT_FIELD_NAMES[0], 'not-a-hmac'),
                           (verifier.INPUT_FIELD_NAMES[0], 'A' * 64),
                           ('unreviewed_field', '8' * 64)):
            changed = copy.deepcopy(self.evidence)
            changed['hidden_inputs']['field_commitments'][key] = value
            self.reject(changed)
        changed = copy.deepcopy(self.evidence)
        del changed['hidden_inputs']['field_commitments'][verifier.INPUT_FIELD_NAMES[0]]
        self.reject(changed)

    def test_valid_hmac_change_not_claimed_authenticated(self):
        # Without the memory-only key, a verifier cannot distinguish arbitrary
        # well-formed commitments from the Owner's actual HMAC values.
        self.evidence['hidden_inputs']['field_commitments'][verifier.INPUT_FIELD_NAMES[0]] = '9' * 64
        self.assertIn('NOT_AUTHENTICATED', self.verify()['hidden_inputs'])

    def test_hidden_root_binding(self):
        self.evidence['hidden_inputs']['input_root_sha256'] = '9' * 64
        self.reject()

    def test_projection_session_and_fixed_seed_context_are_cross_bound(self):
        for key, value in (('session_nonce', '9' * 32),
                           ('new_seed_sha256', '9' * 64),
                           ('old_seed_sha256', '9' * 64),
                           ('extra_private_field', 'PRIVATE_SENTINEL')):
            changed = copy.deepcopy(self.evidence)
            changed['preimages']['context'][key] = value
            self.reject(changed)

    def test_visible_summary_cannot_claim_opaque_roots_were_recomputed(self):
        result = self.verify()
        self.assertFalse(result['resource_views_recomputed_offline'])
        self.assertEqual(result['onsite_only_roots'], verifier.ONSITE_ONLY_ROOTS)
        self.assertEqual(result['retained_target_coverage'], 24)
        self.assertNotIn('retained_targets', result)
        self.assertNotIn('unique_resource_records', result)

    def test_runtime_source_pin_mismatch(self):
        self.evidence['runtime']['validator']['sha256'] = 'a' * 64
        self.reject()

    def test_schema_source_pin_mismatch(self):
        self.evidence['runtime']['schema_source_sha256'] = 'a' * 64
        self.reject()

    def test_bad_timestamp_and_reverse_order(self):
        for value in ('2026-13-01T01:02:03Z', '2026-10-16T15:59:59Z',
                      '2026-10-16 16:00:01', 'PRIVATE_SENTINEL'):
            changed = copy.deepcopy(self.evidence)
            changed['runtime']['finished_utc'] = value
            self.reject(changed)

    def test_report_claiming_remote_attestation_rejected(self):
        self.evidence['limitations'][0] = 'REMOTE_ATTESTATION_VERIFIED'
        self.reject()

    def test_preimage_failure_is_static(self):
        callback = mock.Mock(side_effect=ValueError('PRIVATE_SENTINEL'))
        with mock.patch.object(verifier, 'load_reference_pair', return_value=(self.plan, {}, {})), \
             mock.patch.object(verifier, 'load_verification_components', return_value=(self.identity, callback)):
            with self.assertRaises(verifier.Hold) as result:
                verifier.verify_evidence(self.evidence, b'plan', b'packet')
        self.assertEqual(str(result.exception), 'PREIMAGE_REJECTED')


def synthetic_preimage_result():
    return {'retained_delta': False, 'additive_targets': True, 'access_rows': False,
            'acceptance_contract': False, 'timer_contract': True, 'resource_views': False,
            'resource_directories': True, 'coverage_inventory_only': True,
            'retained_target_count': 24, 'additive_target_count': 2,
            'checkpoint_count': 17, 'section_count': 255, 'withheld_commitments': 4,
            'directory_count': 100, 'onsite_only_roots': list(verifier.ONSITE_ONLY_ROOTS),
            'original_seed_independently_read': False,
            'hidden_input_root_independently_recomputed': False, 'host_freshness_verified': False,
            'hidden_commitments_independently_verified': False}


class SourceIdentityTests(unittest.TestCase):
    def package(self, directory):
        root = pathlib.Path(directory)
        rows = []
        for name, raw in (('validate_private_completeness.py', b'# synthetic producer\n'),
                          ('evidence_schema.py', b'# synthetic schema\n')):
            (root / name).write_bytes(raw)
            rows.append({'path': name, 'bytes': len(raw), 'sha256': verifier.sha256(raw)})
        manifest = {'schema': 1, 'files': rows}
        (root / 'SOURCE_MANIFEST.json').write_bytes(verifier.canonical(manifest))
        return root, manifest

    def test_local_sources_authenticated_against_reviewed_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root, manifest = self.package(directory)
            identity = verifier.load_source_identity(str(root))
            self.assertEqual(identity['validator']['sha256'], manifest['files'][0]['sha256'])
            self.assertEqual(identity['schema_source_sha256'], manifest['files'][1]['sha256'])

    def test_local_source_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, unused = self.package(directory)
            (root / 'evidence_schema.py').write_bytes(b'# CHANGED\n')
            with self.assertRaises(verifier.Hold):
                verifier.load_source_identity(str(root))

    def test_unknown_missing_duplicate_and_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, original = self.package(directory)
            variants = []
            changed = copy.deepcopy(original); changed['files'].pop(); variants.append(changed)
            changed = copy.deepcopy(original); changed['files'].append(changed['files'][0]); variants.append(changed)
            changed = copy.deepcopy(original); changed['files'][0]['path'] = '../private'; variants.append(changed)
            changed = copy.deepcopy(original); changed['source'] = 'PRIVATE_SENTINEL'; variants.append(changed)
            changed = copy.deepcopy(original); changed['schema'] = True; variants.append(changed)
            for changed in variants:
                (root / 'SOURCE_MANIFEST.json').write_bytes(verifier.canonical(changed))
                with self.assertRaises(verifier.Hold):
                    verifier.load_source_identity(str(root))


class PreimageResultTests(unittest.TestCase):
    def test_complete_results(self):
        verifier._validate_preimage_result(synthetic_preimage_result())

    def test_false_incomplete_or_exaggerated_results_fail(self):
        variants = []
        changed = synthetic_preimage_result(); changed['retained_delta'] = True; variants.append(changed)
        changed = synthetic_preimage_result(); changed['original_seed_independently_read'] = True; variants.append(changed)
        changed = synthetic_preimage_result(); changed['hidden_commitments_independently_verified'] = True; variants.append(changed)
        changed = synthetic_preimage_result(); changed['section_count'] = 254; variants.append(changed)
        changed = synthetic_preimage_result(); changed['directory_count'] = 0; variants.append(changed)
        changed = synthetic_preimage_result(); changed['secret'] = 'PRIVATE_SENTINEL'; variants.append(changed)
        variants.append({})
        for changed in variants:
            with self.assertRaises(verifier.Hold):
                verifier._validate_preimage_result(changed)


class IntegratedSyntheticTests(unittest.TestCase):
    def test_real_factory_preimages_through_bounded_transport_and_exact_source_loader(self):
        from test_evidence_schema import prepared_preimages
        preimages, plan, body, unused_fixture, unused_inputs, unused_proposal, unused_timer = prepared_preimages()
        builder = RootContractTests()
        builder.setUp()
        evidence = builder.evidence
        import evidence_schema
        context = {'session_nonce': evidence['hidden_inputs']['session_nonce'],
                   'new_seed_sha256': verifier.NEW_SEED_SHA256, 'old_seed_sha256': verifier.OLD_SEED_SHA256}
        evidence['preimages'] = evidence_schema.privacy_project(preimages, b'K' * 32, context)
        evidence['hidden_inputs']['input_root_sha256'] = plan['host_contract']['input_sha256']
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            rows = []
            here = pathlib.Path(__file__).resolve().parent
            for name in ('validate_private_completeness.py', 'evidence_schema.py'):
                raw = (here / name).read_bytes()
                (root / name).write_bytes(raw)
                rows.append({'path': name, 'bytes': len(raw), 'sha256': verifier.sha256(raw)})
            (root / 'SOURCE_MANIFEST.json').write_bytes(verifier.canonical({'schema': 1, 'files': rows}))
            identity = verifier.load_source_identity(str(root))
            evidence['runtime']['validator'] = identity['validator']
            evidence['runtime']['schema_source_sha256'] = identity['schema_source_sha256']
            wire = verifier.canonical(envelope(verifier.canonical(evidence))) + b'\n'
            self.assertLessEqual(len(wire), verifier.MAX_WIRE_BYTES)
            decoded = verifier.decode_evidence(wire)
            # Actual authenticated source loader + actual preimage validator.
            # Only fixed private references are substituted with synthetic ones.
            with mock.patch.object(verifier, 'load_reference_pair', return_value=(plan, {}, body)):
                result = verifier.verify_evidence(decoded, b'synthetic-plan', b'synthetic-packet', str(root))
            self.assertEqual(result['status'], 'PASS_VISIBLE_PREIMAGES_AND_OWNER_REPORT_STRUCTURE')
            self.assertFalse(result['remote_attestation'])


class AuthenticatedLoaderIsolationTests(unittest.TestCase):
    def package(self, directory):
        root = pathlib.Path(directory)
        schema = b"def verify_projected_preimages(a, b, c):\n    return {'exact_authenticated_source': True}\n"
        producer = b'# synthetic producer only\n'
        rows = []
        for name, raw in (('validate_private_completeness.py', producer), ('evidence_schema.py', schema)):
            (root / name).write_bytes(raw)
            rows.append({'path': name, 'bytes': len(raw), 'sha256': verifier.sha256(raw)})
        (root / 'SOURCE_MANIFEST.json').write_bytes(verifier.canonical({'schema': 1, 'files': rows}))
        return root

    def test_poisoned_module_and_search_path_never_replace_authenticated_bytes(self):
        import sys
        import types
        with tempfile.TemporaryDirectory() as directory:
            root = self.package(directory)
            poison = root / 'poison'; poison.mkdir()
            (poison / 'evidence_schema.py').write_text("raise RuntimeError('POISONED_PATH')\n")
            module = types.ModuleType('evidence_schema')
            module.verify_preimages = mock.Mock(side_effect=RuntimeError('POISONED_PRELOAD'))
            with mock.patch.dict(sys.modules, {'evidence_schema': module}), \
                 mock.patch.object(sys, 'path', [str(poison)] + sys.path):
                unused_identity, callback = verifier.load_verification_components(str(root))
                self.assertEqual(callback({}, {}, {}), {'exact_authenticated_source': True})
            module.verify_preimages.assert_not_called()
            self.assertFalse((root / '__pycache__').exists())

    def test_cold_isolated_loader_and_cli(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = self.package(directory)
            executable = pathlib.Path(verifier.__file__).resolve()
            program = ("import runpy,sys; n=runpy.run_path(sys.argv[1]); "
                       "i,v=n['load_verification_components'](sys.argv[2]); "
                       "assert v({}, {}, {})=={'exact_authenticated_source':True}; "
                       "print('PASS_COLD_AUTHENTICATED_SCHEMA')")
            result = subprocess.run([sys.executable, '-I', '-B', '-S', '-c', program,
                                     str(executable), str(root)], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=20)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b'PASS_COLD_AUTHENTICATED_SCHEMA\n')
            self.assertEqual(result.stderr, b'')
            result = subprocess.run([sys.executable, '-I', '-B', '-S', str(executable)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)['status'], 'HOLD')
            self.assertEqual(result.stderr, b'')
            self.assertFalse((root / '__pycache__').exists())


if __name__ == '__main__':
    unittest.main()
