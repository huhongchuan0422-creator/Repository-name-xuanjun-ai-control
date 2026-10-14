"""Pure epoch7 metadata/delta proposal. NOT an installer or approval verifier.

No filesystem, network, subprocess, database, service or model operations.
All observations are caller-supplied; matching their digest proves consistency,
not host truth, freshness, provenance or permission. No function grants admission.
Python 3.6 compatible. No production CLI is supplied.
"""
import copy
import hashlib
import json
import re
import uuid

TX = 'c529c379-9341-4510-8384-fc6be1e412e5'
OLD_MANIFEST = '153653ebc48d6b20680e513402dad077d50dce953ab3d4b7cc1748bcff0f64e7'
OLD_BINARY = 'd3d546fa491596cc4d82feac9746f0368eb65f20f3fd134164dca8055337dd3e'
NEW_MANIFEST = '26ae77d8fff38c8a69ddcf3e35caeb18d4724ab17eca8fbecf9dc4f76bc797aa'
NEW_BINARY = '1de3690ede78832da9dd2f2607db0b5ae88d6f9d4de87e1cb1ce64f35dab8421'
CONSUMED = frozenset((6160188919, 6161965867, 6167552232, 6170703284))
GENERATION = '/var/lib/xuanjun-development/generations/1'
DB = GENERATION + '/state.sqlite'
SOCKET = '/run/xuanjun-development/ledger.sock'
OWNER_MASKS = frozenset('/etc/systemd/system/' + name for name in (
    'xuanjun-uk-owner-callback.service', 'xuanjun-uk-owner-dashboard.service'))
TARGETS = frozenset((
    '/etc/nginx/conf.d/xuanjun-p2-owner.conf',
    '/etc/systemd/system/nginx.service',
    '/etc/systemd/system/xj-root-broker.service',
    '/etc/systemd/system/xj-root-broker.socket',
    '/etc/systemd/system/xuanjun-development-dispatcher.service',
    '/etc/systemd/system/xuanjun-github-intake.service',
    '/etc/systemd/system/xuanjun-github-intake.timer',
    '/etc/systemd/system/xuanjun-ledger.service',
    '/etc/systemd/system/xuanjun-ledger.socket',
    '/etc/systemd/system/xuanjun-p2-gateway-relay.service',
    '/etc/systemd/system/xuanjun-p2-gateway-relay.socket',
    '/etc/systemd/system/xuanjun-p2-tls-renew.service',
    '/etc/systemd/system/xuanjun-p2-tls-renew.timer',
    '/etc/systemd/system/xuanjun-uk-openclaw.service.d/20-p2-docker.conf',
    '/etc/systemd/system/xuanjun-uk-owner-callback.service',
    '/etc/systemd/system/xuanjun-uk-owner-dashboard.service',
    '/etc/xuanjun-development/dispatcher.json',
    '/etc/xuanjun-development/nginx-main.conf',
    '/etc/xuanjun-development/p2-gateway-relay.json',
    '/etc/xuanjun-development/p2-native-controller.binding.json',
    '/etc/xuanjun-development/p2-native-ledger-client.json',
    '/etc/xuanjun-development/p2-owner-feishu-binding.json',
    '/etc/xuanjun-development/root-broker.json',
    '/etc/xuanjun-development/tls-renewal.json'))
PRESERVED_RECEIPTS = frozenset((
    'recovery-execution.json', 'epoch3-recovery-execution.json',
    'epoch5-recovery-execution.json', 'runtime-provisioning.json',
    'epoch4-runtime-provisioning.json', 'epoch6-runtime-provisioning.json',
    'epoch5-prior-tls-lifecycle.json', 'epoch5-prior-native-binding.json',
    'epoch6-tls-renewal-candidate.json', 'sandbox-profile.json',
    'bootstrap-files.json', 'publisher-bootstrap.json',
    'rpm-prerequisites.json', 'prerequisites.json', 'ledger-cutover.json',
    'legacy-units.json', 'owner-isolation-receipt.json'))
ABSENT_EFFECT_PATHS = frozenset((
    'runtime-boot.json', 'ledger-access.json', 'epoch7-recovery-execution.json',
    'epoch7-recovery-sequence.json', 'epoch7-owner-identity-publication.json',
    'epoch7-server-identity-publication.json', 'epoch7-plugin-effects.json',
    'epoch8-runtime-provisioning.json', 'epoch7-generation-access.json',
    'epoch7-prior-tls-lifecycle.json', 'epoch7-prior-native-binding.json',
    'epoch8-tls-renewal-candidate.json', 'epoch7-sandbox-profile.json',
    'epoch7-sandbox-profile-original.json', 'epoch7-sandbox-profile-candidate.json'))
HASH = re.compile(r'^[0-9a-f]{64}$')
ACTIVATION_KEYS = frozenset(('schema', 'state', 'release_sha256',
    'config_sha256', 'binary_sha256', 'ledger_uuid', 'generation', 'epoch',
    'instance', 'db_path', 'ledger_socket'))
CANONICAL_IDENTITY = ('schema', 'ledger_uuid', 'generation', 'instance',
                      'db_path', 'ledger_socket')
FILE_STAMP_KEYS = frozenset(('size', 'mtime_ns', 'ctime_ns'))
DIRECTORY_STAMP_KEYS = FILE_STAMP_KEYS | {'nlink'}


def need(value, reason):
    if not value:
        raise ValueError(reason)


def canonical(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'),
                     allow_nan=False).encode('utf-8')
    need(len(raw) <= 2097152, 'PROPOSAL_SIZE_BOUND')
    return raw


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def same(a, b):
    return canonical(a) == canonical(b)


def hash_value(value):
    need(isinstance(value, str) and HASH.fullmatch(value), 'HASH_REQUIRED')


def keys(value, expected, reason):
    need(isinstance(value, dict) and set(value) == set(expected), reason)


def integer(value, minimum=0):
    need(type(value) is int and value >= minimum, 'INTEGER_REQUIRED')


def validate_activation(value, epoch, release):
    keys(value, ACTIVATION_KEYS, 'ACTIVATION_KEYS')
    need(type(value['schema']) is int and value['schema'] == 1 and
         value['state'] == 'PREPARED' and type(value['epoch']) is int and
         value['epoch'] == epoch and type(value['generation']) is int and
         value['generation'] == 1, 'EXACT_PREPARED_ACTIVATION')
    for key in ('release_sha256', 'config_sha256', 'binary_sha256'):
        hash_value(value[key])
    for key in ('instance', 'ledger_uuid'):
        need(isinstance(value[key], str) and str(uuid.UUID(value[key])) == value[key],
             'CANONICAL_UUID')
    pairs = {7: (OLD_MANIFEST, OLD_BINARY), 8: (NEW_MANIFEST, NEW_BINARY)}
    need(epoch in pairs and (release, value['binary_sha256']) == pairs[epoch] and
         value['release_sha256'] == release and value['db_path'] == DB and
         value['ledger_socket'] == SOCKET,
         'ACTIVATION_IDENTITY')


def controller_transition(before, after):
    """The sole reviewed controller replacement; canonical ledger identity stays."""
    validate_activation(before, 7, OLD_MANIFEST)
    validate_activation(after, 8, NEW_MANIFEST)
    need(all(same(before[key], after[key]) for key in CANONICAL_IDENTITY),
         'CANONICAL_IDENTITY_CHANGED')
    return {'operation': 'REPLACE_EXACT_REVIEWED_CONTROLLER',
            'before': copy.deepcopy(before), 'after': copy.deepcopy(after),
            'preserved_identity': {key: copy.deepcopy(before[key]) for key in CANONICAL_IDENTITY}}


def validate_controller_transition(value):
    keys(value, ('operation', 'before', 'after', 'preserved_identity'),
         'CONTROLLER_TRANSITION_FIELDS')
    expected = controller_transition(value['before'], value['after'])
    need(same(value, expected), 'CONTROLLER_TRANSITION_BINDING')
    return expected


def validate_file(row, observed=True):
    required = {'kind', 'sha256', 'uid', 'gid', 'mode'}
    if observed:
        required |= {'dev', 'ino', 'nlink'}
        if isinstance(row, dict) and FILE_STAMP_KEYS & set(row):
            required |= FILE_STAMP_KEYS
    keys(row, required, 'FILE_METADATA_KEYS')
    need(row['kind'] == 'FILE', 'REGULAR_FILE_REQUIRED')
    hash_value(row['sha256'])
    for key in ('uid', 'gid', 'mode'):
        integer(row[key])
    need(row['uid'] == 0 and row['mode'] in (0o600, 0o640, 0o644),
         'ROOT_PROTECTED_TARGET')
    if observed:
        integer(row['dev']); integer(row['ino'], 1)
        need(type(row['nlink']) is int and row['nlink'] == 1, 'SINGLE_LINK_REQUIRED')
        for key in FILE_STAMP_KEYS & set(row): integer(row[key])


def validate_generation(row, mode=0o750):
    required = {'path', 'kind', 'uid', 'gid', 'mode', 'dev', 'ino', 'access_acl', 'default_acl'}
    if isinstance(row, dict) and DIRECTORY_STAMP_KEYS & set(row): required |= DIRECTORY_STAMP_KEYS
    keys(row, required, 'GENERATION_METADATA_KEYS')
    need(row['path'] == GENERATION and row['kind'] == 'DIRECTORY', 'GENERATION_PATH')
    for key in ('uid', 'gid', 'mode', 'dev', 'ino'):
        integer(row[key], 1 if key == 'ino' else 0)
    need((row['uid'], row['gid'], row['mode']) == (1003, 1006, mode),
         'GENERATION_OWNER_MODE')
    group = 'r-x' if mode == 0o750 else '---'
    need(row['access_acl'] == 'user::rwx\ngroup::' + group + '\nother::---\n'
         and row['default_acl'] == '', 'GENERATION_EXTENDED_ACL_REQUIRES_REVIEW')
    for key in DIRECTORY_STAMP_KEYS & set(row): integer(row[key], 1 if key == 'nlink' else 0)


def validate_snapshot(snapshot, expected_digest):
    """Check proposed evidence structure; this is NOT a host observation."""
    keys(snapshot, ('schema', 'transaction_id', 'activation', 'epoch_journal_sha256',
        'attempt', 'targets', 'receipts', 'tls', 'cache_inventories',
        'retained_resource_sha256', 'generation', 'database', 'sandbox',
        'plugin_state', 'new_attempt_present', 'writer_exclusion', 'absent_paths'), 'SNAPSHOT_KEYS')
    hash_value(expected_digest)
    need(digest(snapshot) == expected_digest, 'SNAPSHOT_DIGEST_MISMATCH')
    need(type(snapshot['schema']) is int and snapshot['schema'] == 1 and
         snapshot['transaction_id'] == TX, 'SNAPSHOT_TRANSACTION')
    validate_activation(snapshot['activation'], 7, OLD_MANIFEST)
    hash_value(snapshot['epoch_journal_sha256'])
    keys(snapshot['attempt'], ('name', 'sha256', 'state', 'approval_id', 'consumed'),
         'OLD_ATTEMPT_KEYS')
    a = snapshot['attempt']
    need(a['name'] == 'epoch5-recovery-execution.json' and a['state'] == 'HOLD' and
         type(a['approval_id']) is int and a['approval_id'] == 6170703284 and
         a['consumed'] is True, 'CONSUMED_ATTEMPT_REQUIRED')
    hash_value(a['sha256'])
    keys(snapshot['receipts'], PRESERVED_RECEIPTS, 'PRESERVED_RECEIPT_SET')
    for value in snapshot['receipts'].values():
        hash_value(value)
    need(snapshot['receipts'][a['name']] == a['sha256'], 'ATTEMPT_RECEIPT_BINDING')
    keys(snapshot['targets'], TARGETS, 'EXACT_24_TARGETS_REQUIRED')
    for path, row in snapshot['targets'].items():
        if path in OWNER_MASKS:
            required = {'kind', 'link', 'dev', 'ino', 'uid', 'gid'}
            optional = DIRECTORY_STAMP_KEYS | {'mode'}
            if isinstance(row, dict) and optional & set(row): required |= optional
            keys(row, required, 'OWNER_MASK_KEYS')
            need(row['kind'] == 'MASK' and row['link'] == '/dev/null' and
                 type(row['uid']) is int and type(row['gid']) is int and
                 row['uid'] == row['gid'] == 0, 'EXACT_OWNER_MASK_REQUIRED')
            integer(row['dev']); integer(row['ino'], 1)
            if optional <= set(row):
                for key in optional: integer(row[key], 1 if key == 'nlink' else 0)
                need(row['nlink'] == 1 and row['mode'] == 0o777, 'OWNER_MASK_METADATA')
        else:
            validate_file(row)
    need(snapshot['activation']['config_sha256'] ==
         snapshot['targets']['/etc/xuanjun-development/dispatcher.json']['sha256'],
         'OBSERVED_DISPATCHER_CONFIG_BINDING')
    keys(snapshot['tls'], ('state', 'journal_sha256', 'certificate_sha256',
        'tree_fingerprint_sha256', 'config_identity_sha256', 'release_sha256'), 'TLS_KEYS')
    tls = snapshot['tls']
    need(tls['state'] == 'READY_ISSUED_AND_RENEWAL_DRYRUN_VERIFIED' and
         tls['release_sha256'] == OLD_MANIFEST, 'RETAIN_READY_TLS_REQUIRED')
    for key in set(tls) - {'state', 'release_sha256'}:
        hash_value(tls[key])
    caches = snapshot['cache_inventories']
    need(isinstance(caches, dict) and len(caches) >= 3 and len(caches) <= 16,
         'RETAINED_CACHE_INVENTORIES_REQUIRED')
    for path, value in caches.items():
        need(isinstance(path, str) and re.fullmatch(
            r'/opt/xuanjun-control-releases/integration-[0-9a-f]{16}', path),
            'CACHE_RELEASE_PATH')
        hash_value(value)
    need('/opt/xuanjun-control-releases/integration-' + OLD_MANIFEST[:16] in caches,
         'V4_RELEASE_INVENTORY_REQUIRED')
    hash_value(snapshot['retained_resource_sha256'])
    validate_generation(snapshot['generation'])
    db = snapshot['database']
    keys(db, ('path', 'sha256', 'logical_manifest_sha256', 'dev', 'ino', 'uid',
              'gid', 'mode', 'nlink', 'sidecars'), 'DATABASE_KEYS')
    need(db['path'] == DB and db['sidecars'] == [], 'CANONICAL_DATABASE_ONLY')
    for key in ('sha256', 'logical_manifest_sha256'):
        hash_value(db[key])
    for key in ('dev', 'ino', 'uid', 'gid', 'mode', 'nlink'):
        integer(db[key], 1 if key in ('ino', 'nlink') else 0)
    need((db['uid'], db['gid'], db['mode'], db['nlink']) == (0, 0, 0o600, 1),
         'UNREOPENED_DATABASE_REQUIRED')
    keys(snapshot['sandbox'], ('state', 'journal_sha256', 'profile_sha256'), 'SANDBOX_KEYS')
    need(snapshot['sandbox']['state'] == 'RESTORED', 'RESTORED_SANDBOX_REQUIRED')
    hash_value(snapshot['sandbox']['journal_sha256'])
    hash_value(snapshot['sandbox']['profile_sha256'])
    need(snapshot['sandbox']['journal_sha256'] == snapshot['receipts']['sandbox-profile.json'],
         'SANDBOX_RECEIPT_BINDING')
    need(snapshot['plugin_state'] == 'VERIFIED_ABSENT' and
         snapshot['new_attempt_present'] is False, 'UNCLASSIFIED_PRIOR_EFFECT')
    keys(snapshot['absent_paths'], ABSENT_EFFECT_PATHS, 'ABSENCE_INVENTORY_KEYS')
    need(all(v is True for v in snapshot['absent_paths'].values()),
         'UNCLASSIFIED_EFFECT_OR_EXISTING_NEXT_ATTEMPT')
    keys(snapshot['writer_exclusion'], ('all_stopped', 'cgroups_empty',
        'legacy_masks_preserved', 'scheduler_excluded', 'runner_excluded',
        'database_fds_excluded', 'evidence_sha256'), 'EXCLUSION_KEYS')
    for key, value in snapshot['writer_exclusion'].items():
        if key == 'evidence_sha256':
            hash_value(value)
        else:
            need(value is True, 'EXCLUSION_UNPROVEN')
    return copy.deepcopy(snapshot)


def tls_config_rebind(before, after):
    """Only release binding may change; never return certificate/key material."""
    need(isinstance(before, dict) and isinstance(after, dict) and
         set(before) == set(after) and 'release_sha256' in before, 'TLS_CONFIG_SHAPE')
    need(before['release_sha256'] == OLD_MANIFEST, 'TLS_OLD_RELEASE')
    hash_value(after['release_sha256'])
    need(after['release_sha256'] != OLD_MANIFEST, 'TLS_NEW_RELEASE')
    old_identity = {k: v for k, v in before.items() if k != 'release_sha256'}
    new_identity = {k: v for k, v in after.items() if k != 'release_sha256'}
    need(same(old_identity, new_identity), 'TLS_OPERATIONAL_IDENTITY_CHANGED')
    return {'old_config_sha256': digest(before), 'new_config_sha256': digest(after),
            'config_identity_sha256': digest(old_identity),
            'issuance_calls': 0, 'renewal_calls': 0, 'dry_run_calls': 0,
            'action_applied': False}


def validate_provision_before(snapshot, prior_provision_bytes):
    """Bind the 22 retained files/two masks to exact epoch6 provisioning bytes.

    The caller must separately verify current receipt-file authority and that
    these bytes were measured on the host. No private receipt content is returned.
    """
    need(isinstance(prior_provision_bytes, bytes) and len(prior_provision_bytes) <= 1048576,
         'PRIOR_PROVISION_BYTES_BOUND')
    actual_hash = hashlib.sha256(prior_provision_bytes).hexdigest()
    need(actual_hash == snapshot['receipts']['epoch6-runtime-provisioning.json'],
         'PRIOR_PROVISION_RAW_HASH')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'PRIOR_PROVISION_DUPLICATE_KEY')
            result[key] = value
        return result
    def reject_constant(unused):
        raise ValueError('PRIOR_PROVISION_NONFINITE')
    value = json.loads(prior_provision_bytes.decode('utf-8'), object_pairs_hook=unique,
                       parse_constant=reject_constant)
    need(isinstance(value, dict) and type(value.get('schema')) is int and value['schema'] == 1,
         'PRIOR_PROVISION_SCHEMA')
    need(value.get('failure_policy') == 'FENCE_STOP_RETAIN_NO_REPLAY' and
         value.get('rollback_complete') is False, 'PRIOR_PROVISION_RETAIN_POLICY')
    rows = value.get('targets')
    need(isinstance(rows, list) and len(rows) == 24, 'PRIOR_PROVISION_TARGET_COUNT')
    seen = set()
    for row in rows:
        need(isinstance(row, dict) and {'target', 'rendered_sha256', 'mode', 'uid', 'gid', 'previous'} <= set(row),
             'PRIOR_PROVISION_TARGET_SCHEMA')
        path = row['target']
        need(isinstance(path, str) and path in TARGETS and path not in seen, 'PRIOR_PROVISION_TARGET_SET')
        seen.add(path)
        old = snapshot['targets'][path]
        expected = {'kind': 'FILE', 'sha256': row['rendered_sha256'],
                    'mode': row['mode'], 'uid': row['uid'], 'gid': row['gid']}
        validate_file(expected, observed=False)
        if path in OWNER_MASKS:
            need(old.get('kind') == 'MASK' and old.get('link') == '/dev/null' and
                 isinstance(row['previous'], dict) and row['previous'].get('masked') is True,
                 'PRIOR_PROVISION_OWNER_MASK_ORIGIN')
        else:
            need(all(same(old.get(key), val) for key, val in expected.items()),
                 'RETAINED_TARGET_DIFFERS_FROM_V4_RECEIPT')
    need(seen == TARGETS, 'PRIOR_PROVISION_TARGET_SET')
    return {'prior_provision_sha256': actual_hash, 'target_count': 24,
            'retained_regular_files': 22, 'restored_owner_masks': 2,
            'host_provenance_verified': False, 'install_admission': 'NOT_GRANTED'}


def build_delta(snapshot, expected_snapshot_digest, candidate):
    """Return review material only; no new attempt or activation is created."""
    s = validate_snapshot(snapshot, expected_snapshot_digest)
    keys(candidate, ('manifest_sha256', 'activation', 'targets',
                     'tls_config_identity_sha256'), 'CANDIDATE_KEYS')
    manifest = candidate['manifest_sha256']; hash_value(manifest)
    need(manifest != OLD_MANIFEST, 'NEW_MANIFEST_REQUIRED')
    validate_activation(candidate['activation'], 8, manifest)
    transition = controller_transition(s['activation'], candidate['activation'])
    need(candidate['tls_config_identity_sha256'] == s['tls']['config_identity_sha256'],
         'TLS_OPERATIONAL_IDENTITY_CHANGED')
    keys(candidate['targets'], TARGETS, 'EXACT_24_TARGETS_REQUIRED')
    changes = []
    for path in sorted(TARGETS):
        old, new = s['targets'][path], candidate['targets'][path]
        validate_file(new, observed=False)
        if path in OWNER_MASKS:
            need((new['uid'], new['gid'], new['mode']) == (0, 0, 0o644),
                 'OWNER_UNIT_METADATA')
            operation = 'REPLACE_EXACT_OWNER_MASK'
        else:
            need(all(same(old[k], new[k]) for k in ('uid', 'gid', 'mode')),
                 'TARGET_PERMISSION_DELTA_REQUIRES_SEPARATE_REVIEW')
            operation = 'RETAIN' if old['sha256'] == new['sha256'] else 'REPLACE_EXACT_FILE'
        changes.append({'path': path, 'operation': operation,
                        'before': copy.deepcopy(old), 'after': copy.deepcopy(new)})
    need(candidate['activation']['config_sha256'] ==
         candidate['targets']['/etc/xuanjun-development/dispatcher.json']['sha256'],
         'CANDIDATE_DISPATCHER_CONFIG_BINDING')
    generation_after = copy.deepcopy(s['generation'])
    for key in DIRECTORY_STAMP_KEYS: generation_after.pop(key, None)
    generation_after.update(mode=0o700, access_acl='user::rwx\ngroup::---\nother::---\n')
    validate_generation(generation_after, 0o700)
    result = {'schema': 1, 'kind': 'OFFLINE_EPOCH7_DELTA_NOT_INSTALL_PLAN',
        'transaction_id': TX, 'expected_epoch': 7, 'proposed_epoch': 8,
        'snapshot_sha256': expected_snapshot_digest, 'candidate_sha256': digest(candidate),
        'runtime_manifest_sha256': manifest, 'changes': changes,
        'controller_transition': transition,
        'generation_change': {'before': s['generation'], 'after': generation_after,
                              'operation': 'FD_ANCHORED_CHMOD_ONLY', 'recursive': False},
        'tls_change': {'operation': 'ARCHIVE_EXACT_THEN_REBIND_RELEASE_METADATA_ONLY',
            'before_journal_sha256': s['tls']['journal_sha256'],
            'archive_name': 'epoch7-prior-tls-lifecycle.json',
            'old_release_sha256': OLD_MANIFEST, 'new_release_sha256': manifest,
            'retained_state': s['tls']['state'], 'certificate_sha256': s['tls']['certificate_sha256'],
            'config_identity_sha256': s['tls']['config_identity_sha256'],
            'issuance_calls': 0, 'renewal_calls': 0, 'dry_run_calls': 0},
        'sandbox_change': {'operation': 'NEW_JOURNAL_FROM_VERIFIED_RESTORED_PROFILE',
            'preserve_journal_sha256': s['sandbox']['journal_sha256'],
            'expected_profile_sha256': s['sandbox']['profile_sha256'],
            'new_journal_name': 'epoch7-sandbox-profile.json'},
        'preserve': {'receipts': s['receipts'], 'database': s['database'],
            'caches': s['cache_inventories'], 'tls': s['tls'],
            'retained_resource_sha256': s['retained_resource_sha256']},
        'new_attempt_name': 'epoch7-recovery-execution.json',
        'attempt_create_policy': 'O_EXCL_FSYNC_NO_RESUME_NO_RESET',
        'failure_policy': 'FENCE_STOP_RETAIN_NO_REPLAY',
        'authorized_attempts': 0, 'effects': 0, 'install_admission': 'NOT_GRANTED',
        'issuance_calls': 0, 'renewal_calls': 0, 'dry_run_calls': 0,
        'prerequisite_replay': False, 'legacy_restart': False,
        'cache_import_delete_or_rewrite': False, 'automatic_retry': False}
    canonical(result)
    return result


def expected_review_binding(delta, review_id, kit_manifest_sha256, security_delta_sha256):
    """Unsigned review template, never evidence of authorization or provenance."""
    need(type(review_id) is int and review_id > 0 and review_id not in CONSUMED,
         'NEW_UNCONSUMED_REVIEW_ID_REQUIRED')
    need(delta.get('kind') == 'OFFLINE_EPOCH7_DELTA_NOT_INSTALL_PLAN' and
         delta.get('install_admission') == 'NOT_GRANTED' and
         delta.get('authorized_attempts') == 0, 'PROPOSAL_ONLY_REQUIRED')
    hash_value(kit_manifest_sha256); hash_value(security_delta_sha256)
    return {'kind': 'UNSIGNED_REVIEW_BINDING_TEMPLATE', 'review_id': review_id,
            'delta_sha256': digest(delta), 'kit_manifest_sha256': kit_manifest_sha256,
            'snapshot_sha256': delta['snapshot_sha256'],
            'runtime_manifest_sha256': delta['runtime_manifest_sha256'],
            'security_delta_sha256': security_delta_sha256,
            'expected_epoch': 7, 'proposed_epoch': 8,
            'authorization_verified': False, 'install_admission': 'NOT_GRANTED'}


def validate_generation_receipt(delta, before, after, receipt):
    """Pure postcondition test for a future approved journalled chmod adapter."""
    change = delta['generation_change']
    need(same(before, change['before']) and
         all(key in after and same(after[key], value) for key, value in change['after'].items()),
         'GENERATION_METADATA_DRIFT')
    keys(receipt, ('state', 'delta_sha256', 'snapshot_sha256', 'approval_body_sha256',
                  'before_sha256', 'after_sha256'), 'GENERATION_RECEIPT_KEYS')
    hash_value(receipt['approval_body_sha256'])
    need(receipt['state'] == 'DONE' and receipt['delta_sha256'] == digest(delta) and
         receipt['snapshot_sha256'] == delta['snapshot_sha256'] and
         receipt['before_sha256'] == digest(before) and
         receipt['after_sha256'] == digest(after), 'GENERATION_RECEIPT_BINDING')
    validate_generation(before); validate_generation(after, 0o700)
    if DIRECTORY_STAMP_KEYS <= set(before):
        need(DIRECTORY_STAMP_KEYS <= set(after) and all(after[key] == before[key] for key in
             ('size', 'nlink', 'mtime_ns')) and after['ctime_ns'] >= before['ctime_ns'],
             'GENERATION_STAMP_DRIFT')
    return {'postcondition_consistent': True, 'authorization_verified': False,
            'install_admission': 'NOT_GRANTED'}
