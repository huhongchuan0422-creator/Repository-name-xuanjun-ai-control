"""Offline, bounded verifier for one fixed private-completeness evidence package.

Only explicitly supplied local files are read. No frozen-kit code is imported,
no host state is observed, and no evidence content or exception text is printed.
This verifies visible derived preimages and the structure of an Owner report; it does
not authenticate that report or independently prove hidden input contents.
"""
import base64
import binascii
import hashlib
import json
import os
import re
import stat
import sys
import zlib

# Importing the reviewed local schema must not create a bytecode cache.
sys.dont_write_bytecode = True

MAX_RAW_BYTES = 16 * 1024 * 1024
MAX_GZIP_BYTES = 70000
MAX_WIRE_BYTES = 98304
MAX_INPUT_BYTES = MAX_RAW_BYTES
MAX_DEPTH = 64
MAX_NODES = 2000000
MAX_STRING_BYTES = 262144
MAX_OUTPUT_BYTES = 2048
ENVELOPE_FORMAT = 'P2_PRIVATE_COMPLETENESS_GZIP_BASE64_V1'
ENVELOPE_KEYS = frozenset(('format', 'uncompressed_bytes', 'uncompressed_sha256',
    'compressed_bytes', 'compressed_sha256', 'payload_base64'))
SHA_RE = re.compile(r'\A[0-9a-f]{64}\Z')
SOURCE_COMMIT = '105996ed06a0bdb5d025914cf08ebd448425f739'
SOURCE_TREE = '343d315b3ead6266a626b5875dbdd6c2fa0309af'
MANIFEST_SHA256 = '91252ba75c38b4a6d12f9b64eb06cb8793fabd97f03646bece97224178c28392'
PLAN_BYTES = 140648
PLAN_SHA256 = '5b3a34222dc634d95b4e070105de9afb3dc24b5c53f7b6497bc61d392887fb01'
PACKET_BYTES = 29665
PACKET_SHA256 = '2bf597ef911cba70b5c94559ee36d8f90c2a339a3de1bfd2d8f58547900b8dec'
BODY_BYTES = 7968
BODY_SHA256 = '35c6fd49a18845542c01c65b0f870cef1626b841e2daba138a687e4137d4a1f5'
OLD_SEED_BYTES = 769086
OLD_SEED_SHA256 = '6de7d12246826388949723e9238cd464686e6e86847187946837df927c97a550'
NEW_SEED_BYTES = 770702
NEW_SEED_SHA256 = 'd7eabd4c0716bd23c35a210c0ace8493b8a9f23237d1df1eeef231fdda8d16f0'


class Hold(ValueError):
    """A fixed, non-secret verification failure code."""


def need(condition, code):
    if not condition:
        raise Hold(code)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def _sha(value):
    return type(value) is str and SHA_RE.fullmatch(value) is not None


def _int(value, low, high):
    return type(value) is int and low <= value <= high


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'DUPLICATE_KEY')
        result[key] = value
    return result


def _number(text):
    need(len(text) <= 20, 'JSON_NUMBER')
    value = int(text)
    need(-(2 ** 63) <= value < 2 ** 63, 'JSON_NUMBER')
    return value


def _forbidden_number(unused):
    raise Hold('JSON_NUMBER')


def _depth_scan(raw):
    depth = 0
    string = False
    escaped = False
    for byte in raw:
        if string:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                string = False
        elif byte == 34:
            string = True
        elif byte in (91, 123):
            depth += 1
            need(depth <= MAX_DEPTH, 'JSON_DEPTH')
        elif byte in (93, 125):
            depth -= 1
            need(depth >= 0, 'JSON_SYNTAX')
    need(depth == 0 and not string, 'JSON_SYNTAX')


def _validate_tree(value, max_string_bytes):
    pending = [value]
    nodes = 0
    while pending:
        item = pending.pop()
        nodes += 1
        need(nodes <= MAX_NODES, 'JSON_NODE_BOUND')
        if type(item) is dict:
            for key, child in item.items():
                try:
                    key_bytes = len(key.encode('utf-8'))
                except (AttributeError, UnicodeError):
                    raise Hold('JSON_KEY_BOUND')
                need(type(key) is str and key_bytes <= 256, 'JSON_KEY_BOUND')
                pending.append(child)
        elif type(item) is list:
            pending.extend(item)
        elif type(item) is str:
            try:
                length = len(item.encode('utf-8'))
            except UnicodeError:
                raise Hold('JSON_ENCODING')
            need(length <= max_string_bytes, 'JSON_STRING_BOUND')
        else:
            need(type(item) in (int, bool, type(None)), 'JSON_TYPE')
    return value


def strict_json(raw, max_bytes=MAX_RAW_BYTES, transport=False):
    """Decode exactly one bounded UTF-8 JSON object; reject ambiguous values."""
    need(type(raw) is bytes and 0 < len(raw) <= max_bytes, 'INPUT_BOUND')
    _depth_scan(raw)
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                           parse_int=_number, parse_float=_forbidden_number,
                           parse_constant=_forbidden_number)
    except Hold:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise Hold('JSON_SYNTAX')
    need(type(value) is dict, 'JSON_ROOT')
    return _validate_tree(value, MAX_INPUT_BYTES if transport else MAX_STRING_BYTES)


def decode_evidence(raw):
    """Accept raw evidence JSON or one exact, bounded gzip/base64 envelope."""
    value = strict_json(raw, max_bytes=MAX_INPUT_BYTES, transport=True)
    if 'format' not in value:
        return _validate_tree(value, MAX_STRING_BYTES)
    need(len(raw) <= MAX_WIRE_BYTES, 'ENVELOPE_BOUND')
    need(set(value) == ENVELOPE_KEYS and value['format'] == ENVELOPE_FORMAT,
         'ENVELOPE_SCHEMA')
    need(_int(value['uncompressed_bytes'], 1, MAX_RAW_BYTES)
         and _int(value['compressed_bytes'], 1, MAX_GZIP_BYTES)
         and _sha(value['uncompressed_sha256']) and _sha(value['compressed_sha256'])
         and type(value['payload_base64']) is str, 'ENVELOPE_FIELDS')
    encoded = value['payload_base64']
    need(len(encoded) == 4 * ((value['compressed_bytes'] + 2) // 3),
         'BASE64_BOUND')
    try:
        compressed = base64.b64decode(encoded.encode('ascii'), validate=True)
    except (ValueError, UnicodeError, binascii.Error):
        raise Hold('BASE64_INVALID')
    need(base64.b64encode(compressed).decode('ascii') == encoded,
         'BASE64_NONCANONICAL')
    need(len(compressed) == value['compressed_bytes']
         and sha256(compressed) == value['compressed_sha256'], 'GZIP_IDENTITY')
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        unpacked = decoder.decompress(compressed, value['uncompressed_bytes'] + 1)
    except zlib.error:
        raise Hold('GZIP_INVALID')
    need(len(unpacked) == value['uncompressed_bytes'] and decoder.eof
         and not decoder.unused_data and not decoder.unconsumed_tail,
         'GZIP_EOF_BOUND')
    need(sha256(unpacked) == value['uncompressed_sha256'], 'EVIDENCE_IDENTITY')
    result = strict_json(unpacked)
    need('format' not in result, 'NESTED_ENVELOPE')
    return result


def read_local(path, limit):
    """Read one supplied regular file without following its final symlink."""
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(descriptor)
        need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit,
             'LOCAL_FILE_BOUND')
        chunks = []
        total = 0
        while total <= limit:
            chunk = os.read(descriptor, min(65536, limit + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            chunks.append(chunk)
        raw = b''.join(chunks)
        after = os.fstat(descriptor)
        need(total == before.st_size and total <= limit
             and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                  before.st_ctime_ns) ==
                 (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                  after.st_ctime_ns), 'LOCAL_FILE_CHANGED')
        return raw
    except Hold:
        raise
    except (OSError, ValueError, TypeError):
        raise Hold('LOCAL_FILE_READ')
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                raise Hold('LOCAL_FILE_CLOSE')


def load_reference_pair(plan_raw, packet_raw):
    """Bind the already received artifacts before parsing either artifact."""
    need(type(plan_raw) is bytes and len(plan_raw) == PLAN_BYTES
         and sha256(plan_raw) == PLAN_SHA256, 'PLAN_IDENTITY')
    need(type(packet_raw) is bytes and len(packet_raw) == PACKET_BYTES
         and sha256(packet_raw) == PACKET_SHA256, 'PACKET_IDENTITY')
    plan = strict_json(plan_raw, max_bytes=PLAN_BYTES)
    packet = strict_json(packet_raw, max_bytes=PACKET_BYTES)
    need(canonical(plan) + b'\n' == plan_raw
         and canonical(packet) + b'\n' == packet_raw, 'REFERENCE_CANONICAL')
    need(type(packet.get('final_review_body')) is dict, 'BODY_MISSING')
    body = packet['final_review_body']
    body_raw = canonical(body)
    need(len(body_raw) == BODY_BYTES and sha256(body_raw) == BODY_SHA256,
         'BODY_IDENTITY')
    need(packet.get('plan_sha256') == PLAN_SHA256
         and packet.get('seed_sha256') == NEW_SEED_SHA256
         and packet.get('compiler_kit_manifest_sha256') == MANIFEST_SHA256
         and packet.get('final_review_body_sha256') is None
         and packet.get('final_review_id') is None,
         'REFERENCE_BINDING')
    return plan, packet, body


def _parse_arguments(argv):
    need(type(argv) is list and len(argv) == 5, 'ARGUMENTS')
    need(type(argv[0]) is str and 0 < len(argv[0]) <= 4096
         and not argv[0].startswith('--'), 'ARGUMENTS')
    arguments = {'evidence': argv[0]}
    for offset in (1, 3):
        flag, path = argv[offset:offset + 2]
        need(flag in ('--plan', '--packet') and flag[2:] not in arguments
             and type(path) is str and 0 < len(path) <= 4096,
             'ARGUMENTS')
        arguments[flag[2:]] = path
    need(set(arguments) == {'evidence', 'plan', 'packet'}, 'ARGUMENTS')
    return arguments


def run_cli(argv, writer=None):
    """One bounded output attempt, including failures; never retry a write."""
    if writer is None:
        writer = os.write
    status = 1
    try:
        arguments = _parse_arguments(argv)
        evidence_raw = read_local(arguments['evidence'], MAX_INPUT_BYTES)
        plan_raw = read_local(arguments['plan'], PLAN_BYTES)
        packet_raw = read_local(arguments['packet'], PACKET_BYTES)
        result = verify_evidence(decode_evidence(evidence_raw), plan_raw, packet_raw)
        status = 0
    except Hold:
        result = {'status': 'HOLD', 'code': 'EVIDENCE_REJECTED',
                  'retry_performed': False}
    except BaseException:
        result = {'status': 'HOLD', 'code': 'VERIFIER_FAILURE',
                  'retry_performed': False}
    try:
        output = canonical(result) + b'\n'
        if len(output) > MAX_OUTPUT_BYTES:
            return 3
        written = writer(1, output)
        if type(written) is not int or written != len(output):
            return 3
    except BaseException:
        return 3
    return status


# Fixed reviewed identities and closed report shape.
EXPECTED_COMPILER = {'cache_files': 256,
 'dependency_commit': 'e2df38160e635af96dcfd63a1b75cf64671e4935',
 'entry_bytes': 56593,
 'entry_sha256': '21a982161bc4cb8ffd7e67e4b9a8e24bf23916df6d78c3dd43376af3cfb34890',
 'manifest_sha256': '91252ba75c38b4a6d12f9b64eb06cb8793fabd97f03646bece97224178c28392',
 'runtime_manifest_sha256': '0ac28c96636ee63364015b375202779e2ef1dd0bd9f1b81e77d4387b6754316c',
 'runtime_payloads': 107,
 'source_commit': '105996ed06a0bdb5d025914cf08ebd448425f739',
 'source_tree': '343d315b3ead6266a626b5875dbdd6c2fa0309af'}
EXPECTED_CANDIDATE = {'admission_expires_at_utc': '2026-10-16T18:00:00Z',
 'body_bytes': 7968,
 'body_sha256': '35c6fd49a18845542c01c65b0f870cef1626b841e2daba138a687e4137d4a1f5',
 'formal_approval': 'NOT_ISSUED',
 'install_admission': 'NOT_GRANTED',
 'packet_sha256': '2bf597ef911cba70b5c94559ee36d8f90c2a339a3de1bfd2d8f58547900b8dec',
 'plan_sha256': '5b3a34222dc634d95b4e070105de9afb3dc24b5c53f7b6497bc61d392887fb01'}
EXPECTED_CHECKS = {'body_exact_match': True,
 'factory_state': 'COMPILED_NOT_ADMITTED',
 'input_root_recomputed_onsite': True,
 'install_admission': False,
 'plan_exact_match': True,
 'private_values_unchanged': True,
 'original_derived_preimages_recomputed_onsite': True,
 'unresolved_count': 0}
EXPECTED_INHERITANCE = {'claim_equals_packet': True,
 'new_field_count': 13,
 'new_schema': 2,
 'new_without_claim_equals_old': True,
 'old_field_count': 12,
 'old_schema': 1,
 'private_fields_not_disclosed': True}
EXPECTED_LIMITATIONS = ['OWNER_TERMINAL_REPORT_NOT_REMOTE_ATTESTATION',
 'HIDDEN_INPUT_ROOT_ONLY_RECOMPUTED_ONSITE',
 'AFFECTED_DERIVED_ROOTS_ONLY_RECOMPUTED_ONSITE',
 'NO_RAW_SEED_OR_CONFIG_DISCLOSED',
 'NO_CURRENT_WRITER_DATABASE_OR_TIMER_PROOF',
 'NO_C_DRIVER_ASSEMBLY_OR_EXECUTION',
 'ATIME_POSSIBLE_NOT_MEASURED']
EXPECTED_FILES = [['new_seed',
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
  '2bf597ef911cba70b5c94559ee36d8f90c2a339a3de1bfd2d8f58547900b8dec']]
FILE_ROW_KEYS = ['role', 'name', 'bytes', 'sha256', 'metadata', 'reread_match', 'authority']
FILE_METADATA_KEYS = ['dev', 'ino', 'uid', 'gid', 'mode', 'nlink', 'size', 'mtime_ns', 'ctime_ns']
INPUT_FIELD_NAMES = ['acceptance_access_rows',
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
 'unit_transition_contract']
ROOT_KEYS = ['schema',
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
 'limitations']
HIDDEN_KEYS = ['scheme',
 'domain',
 'session_nonce',
 'input_root_sha256',
 'input_field_names',
 'field_commitments',
 'key_disclosure',
 'offline_binding']
RUNTIME_KEYS = ['validator',
 'schema_source_sha256',
 'started_utc',
 'finished_utc',
 'scope',
 'additional_metadata_reads',
 'call_path',
 'cleanup']
RUNTIME_CALL_PATH = ['entry.verify_kit',
 'entry._hydrate_seed',
 'factory.prepare_host_inputs',
 'factory.compile_host_contract',
 'factory._proposal',
 'factory.compile_timer_contract',
 'schema.build_preimages',
 'schema.verify_preimages',
 'schema.privacy_project',
 'schema.verify_projected_preimages',
 'protected_final_rereads']
RUNTIME_METADATA = ['/var/lib/xuanjun-development/generations/1/state.sqlite', '/run/xuanjun-development/ledger.sock']
KIND = 'P2_FIXED_PRIVATE_COMPLETENESS_EVIDENCE_V1'
STATE = 'EVIDENCE_COLLECTED_WITH_LIMITATIONS'
FILE_AUTHORITY = 'ROOT_ROOT_REGULAR_0600_NLINK1_NOFOLLOW_NO_EXTENDED_ACL'
HIDDEN_DOMAIN = 'P2_PRIVATE_COMPLETENESS_INPUT_FIELD_V1'
HIDDEN_KEY_DISCLOSURE = 'NEVER_EXPORTED_OR_PERSISTED'
HIDDEN_OFFLINE_BINDING = 'ONSITE_REPORT_ONLY_NOT_INDEPENDENTLY_RECOMPUTABLE'
HIDDEN_SCHEME = 'HMAC_SHA256_EPHEMERAL_KEY_V1'
RUNTIME_CLEANUP = 'COMPLETED'
RUNTIME_SCOPE = 'FIXED_SAVED_INPUTS_AND_AUTHENTICATED_PURE_COMPILERS_ONLY'


def _exact(value, expected, code):
    need(canonical(value) == canonical(expected), code)


def _validate_files(files):
    need(type(files) is list and len(files) == 4, 'FILES_SCHEMA')
    identities = set()
    for actual, expected in zip(files, EXPECTED_FILES):
        need(type(actual) is dict and set(actual) == set(FILE_ROW_KEYS), 'FILES_SCHEMA')
        _exact([actual['role'], actual['name'], actual['bytes'], actual['sha256']],
               expected, 'FILE_PIN')
        need(actual['reread_match'] is True and actual['authority'] == FILE_AUTHORITY,
             'FILE_REPORT')
        metadata = actual['metadata']
        need(type(metadata) is dict and set(metadata) == set(FILE_METADATA_KEYS)
             and all(_int(value, 0, 2 ** 63 - 1) for value in metadata.values()),
             'FILE_METADATA_SCHEMA')
        need(metadata['dev'] > 0 and metadata['ino'] > 0
             and metadata['uid'] == 0 and metadata['gid'] == 0
             and metadata['mode'] == 0o600 and metadata['nlink'] == 1
             and metadata['size'] == expected[2], 'FILE_METADATA')
        identity = (metadata['dev'], metadata['ino'])
        need(identity not in identities, 'FILE_ALIAS')
        identities.add(identity)


def _validate_hidden(hidden, plan):
    need(type(hidden) is dict and set(hidden) == set(HIDDEN_KEYS), 'HIDDEN_SCHEMA')
    need(hidden['scheme'] == HIDDEN_SCHEME and hidden['domain'] == HIDDEN_DOMAIN
         and hidden['key_disclosure'] == HIDDEN_KEY_DISCLOSURE
         and hidden['offline_binding'] == HIDDEN_OFFLINE_BINDING,
         'HIDDEN_SCHEME')
    _exact(hidden['input_field_names'], INPUT_FIELD_NAMES, 'HIDDEN_FIELDS')
    need(type(hidden['session_nonce']) is str
         and re.fullmatch(r'[0-9a-f]{32}', hidden['session_nonce']) is not None
         and _sha(hidden['input_root_sha256'])
         and hidden['input_root_sha256'] == plan['host_contract']['input_sha256'],
         'HIDDEN_ROOT')
    commitments = hidden['field_commitments']
    need(type(commitments) is dict and set(commitments) == set(INPUT_FIELD_NAMES)
         and all(_sha(value) for value in commitments.values()), 'HMAC_STRUCTURE')
    # HMAC values cannot be independently recomputed because the key is never
    # exported. No raw child fingerprint or unkeyed per-field digest is allowed
    # by the closed shape. This check does not authenticate the commitments.


def _utc(value):
    import datetime
    need(type(value) is str and re.fullmatch(
        r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', value) is not None,
        'RUNTIME_TIME')
    try:
        return datetime.datetime(int(value[0:4]), int(value[5:7]), int(value[8:10]),
                                 int(value[11:13]), int(value[14:16]), int(value[17:19]))
    except ValueError:
        raise Hold('RUNTIME_TIME')


def _validate_runtime(runtime, source_identity):
    need(type(runtime) is dict and set(runtime) == set(RUNTIME_KEYS), 'RUNTIME_SCHEMA')
    need(type(source_identity) is dict and set(source_identity) == {'validator', 'schema_source_sha256'},
         'SOURCE_IDENTITY')
    validator = source_identity['validator']
    need(type(validator) is dict and set(validator) == {'bytes', 'sha256'}
         and _int(validator['bytes'], 1, 4 * 1024 * 1024) and _sha(validator['sha256'])
         and _sha(source_identity['schema_source_sha256']), 'SOURCE_IDENTITY')
    _exact(runtime['validator'], validator, 'VALIDATOR_IDENTITY')
    need(runtime['schema_source_sha256'] == source_identity['schema_source_sha256'],
         'SCHEMA_SOURCE_IDENTITY')
    need(_utc(runtime['finished_utc']) >= _utc(runtime['started_utc']), 'RUNTIME_TIME')
    need(runtime['scope'] == RUNTIME_SCOPE and runtime['cleanup'] == RUNTIME_CLEANUP,
         'RUNTIME_SCOPE')
    _exact(runtime['additional_metadata_reads'], RUNTIME_METADATA, 'RUNTIME_METADATA')
    _exact(runtime['call_path'], RUNTIME_CALL_PATH, 'RUNTIME_CALL_PATH')


def verify_evidence(evidence, plan_raw, packet_raw, package_directory=None):
    """Verify safe projected preimages and the Owner report structure.

    Source identity and executable schema bytes come only from the reviewer's
    trusted local package manifest, never from evidence or an import-name lookup.
    """
    need(type(evidence) is dict and set(evidence) == set(ROOT_KEYS), 'EVIDENCE_SCHEMA')
    _validate_tree(evidence, MAX_STRING_BYTES)
    need(type(evidence['schema']) is int and evidence['schema'] == 1
         and evidence['kind'] == KIND and evidence['state'] == STATE,
         'EVIDENCE_KIND')
    plan, packet, body = load_reference_pair(plan_raw, packet_raw)
    _exact(evidence['compiler'], EXPECTED_COMPILER, 'COMPILER_IDENTITY')
    _exact(evidence['candidate'], EXPECTED_CANDIDATE, 'CANDIDATE_IDENTITY')
    _exact(evidence['checks'], EXPECTED_CHECKS, 'ONSITE_CHECKS')
    _exact(evidence['seed_inheritance'], EXPECTED_INHERITANCE, 'INHERITANCE_REPORT')
    _exact(evidence['limitations'], EXPECTED_LIMITATIONS, 'LIMITATIONS')
    _validate_files(evidence['files'])
    _validate_hidden(evidence['hidden_inputs'], plan)
    projection = evidence['preimages']
    need(type(projection) is dict and 'context' in projection, 'PROJECTION_CONTEXT')
    _exact(projection['context'], {
        'session_nonce': evidence['hidden_inputs']['session_nonce'],
        'new_seed_sha256': NEW_SEED_SHA256, 'old_seed_sha256': OLD_SEED_SHA256},
        'PROJECTION_CONTEXT')
    source_identity, verify_projected_preimages = load_verification_components(package_directory)
    _validate_runtime(evidence['runtime'], source_identity)
    try:
        checks = verify_projected_preimages(evidence['preimages'], plan, body)
    except BaseException:
        raise Hold('PREIMAGE_REJECTED')
    _validate_preimage_result(checks)
    return {'status': 'PASS_VISIBLE_PREIMAGES_AND_OWNER_REPORT_STRUCTURE',
            'retained_target_coverage': 24, 'additive_targets_verified': 2,
            'resource_checkpoint_count_reported': 17, 'resource_section_count_reported': 255,
            'resource_views_recomputed_offline': False, 'opaque_segment_commitments': 4,
            'file_reports': 4, 'hidden_input_commitments': 37,
            'resource_directories_verified': checks['directory_count'],
            'onsite_only_roots': list(checks['onsite_only_roots']),
            'transport_limits': {'raw_bytes': MAX_RAW_BYTES, 'gzip_bytes': MAX_GZIP_BYTES,
                                 'wire_bytes': MAX_WIRE_BYTES},
            'hidden_inputs': 'ONSITE_ONLY_HMAC_STRUCTURE_NOT_AUTHENTICATED',
            'remote_attestation': False, 'current_host_state_verified': False,
            'formal_approval': 'NOT_ISSUED', 'install_admission': 'NOT_GRANTED',
            'retry_performed': False}



ONSITE_ONLY_ROOTS = ['acceptance_contract_sha256', 'complete_delta_sha256',
                     'delta_sha256', 'security_delta_sha256', 'views_sha256']


def _validate_preimage_result(checks):
    true_fields = ('additive_targets', 'timer_contract', 'resource_directories',
                   'coverage_inventory_only')
    false_fields = ('retained_delta', 'access_rows', 'acceptance_contract', 'resource_views',
                    'original_seed_independently_read',
                    'hidden_input_root_independently_recomputed', 'host_freshness_verified',
                    'hidden_commitments_independently_verified')
    counts = {'retained_target_count': 24, 'additive_target_count': 2,
              'checkpoint_count': 17, 'section_count': 255, 'withheld_commitments': 4}
    expected = set(true_fields) | set(false_fields) | set(counts) | {'directory_count', 'onsite_only_roots'}
    need(type(checks) is dict and set(checks) == expected, 'PREIMAGE_RESULT')
    need(all(checks[key] is True for key in true_fields)
         and all(checks[key] is False for key in false_fields), 'PREIMAGE_RESULT')
    need(all(type(checks[key]) is int and checks[key] == value for key, value in counts.items())
         and _int(checks['directory_count'], 1, 32768), 'PREIMAGE_RESULT')
    _exact(checks['onsite_only_roots'], ONSITE_ONLY_ROOTS, 'PREIMAGE_RESULT')


def _load_source_bytes(package_directory=None):
    """Authenticate the two local sources against the reviewed package manifest.

    The manifest is a reviewer-trusted local package artifact, not supplied by
    the Owner report, a signature or a remote-attestation credential.
    """
    if package_directory is None:
        package_directory = os.path.dirname(os.path.abspath(__file__))
    manifest_raw = read_local(os.path.join(package_directory, 'SOURCE_MANIFEST.json'), 65536)
    manifest = strict_json(manifest_raw, max_bytes=65536)
    need(set(manifest) == {'schema', 'files'} and type(manifest['schema']) is int
         and manifest['schema'] == 1 and type(manifest['files']) is list
         and 2 <= len(manifest['files']) <= 128, 'SOURCE_MANIFEST_SCHEMA')
    rows = {}
    for row in manifest['files']:
        need(type(row) is dict and set(row) == {'path', 'bytes', 'sha256'}, 'SOURCE_MANIFEST_ROW')
        path = row['path']
        need(type(path) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', path) is not None
             and path != 'SOURCE_MANIFEST.json' and path not in rows
             and _int(row['bytes'], 1, 4 * 1024 * 1024) and _sha(row['sha256']),
             'SOURCE_MANIFEST_ROW')
        rows[path] = row
    required = ('validate_private_completeness.py', 'evidence_schema.py')
    need(all(name in rows for name in required), 'SOURCE_MANIFEST_MISSING')
    authenticated = {}
    for name in required:
        expected = rows[name]
        raw = read_local(os.path.join(package_directory, name), expected['bytes'])
        need(len(raw) == expected['bytes'] and sha256(raw) == expected['sha256'],
             'SOURCE_FILE_IDENTITY')
        authenticated[name] = raw
    return {'validator': {'bytes': rows[required[0]]['bytes'],
                          'sha256': rows[required[0]]['sha256']},
            'schema_source_sha256': rows[required[1]]['sha256']}, authenticated[required[1]]


def load_source_identity(package_directory=None):
    return _load_source_bytes(package_directory)[0]


def load_verification_components(package_directory=None):
    identity, schema_raw = _load_source_bytes(package_directory)
    namespace = {'__name__': '_reviewed_private_completeness_schema',
                 '__file__': '<authenticated-evidence-schema>'}
    try:
        exec(compile(schema_raw, namespace['__file__'], 'exec', dont_inherit=True), namespace)
        verifier = namespace['verify_projected_preimages']
        need(callable(verifier), 'SCHEMA_ENTRYPOINT')
    except Hold:
        raise
    except BaseException:
        raise Hold('SCHEMA_LOAD')
    return identity, verifier


if __name__ == '__main__':
    sys.exit(run_cli(sys.argv[1:]))
