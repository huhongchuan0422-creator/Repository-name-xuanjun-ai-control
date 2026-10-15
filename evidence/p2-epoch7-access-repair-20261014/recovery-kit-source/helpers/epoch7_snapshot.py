"""Read-only epoch7 collector core. No CLI, default pins or approval authority.

collect() supports injected read-only IO for fixture tests. collect_host() in
snapshot_io requires protected explicit measured pins and the existing lock.
Only digests/metadata escape; raw private files remain in memory.
"""
import copy
import hashlib
import json
import os
import re
import uuid

import epoch7_delta as d

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
BASE = '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
CAND = BASE + '/complete-install-candidate-38503014520'
TRANSACTION = BASE + '/legacy-isolation-' + d.TX
ACTIVE = '/var/lib/xuanjun-development/activation/active.json'
EPOCHS = '/var/lib/xuanjun-development/activation/epochs.jsonl'
PLAN = CAND + '/protected-core-install-plan.json'
NATIVE = '/etc/xuanjun-development/p2-native-binding.json'
RETAINED_NATIVE_SHA = '91c65c9fbc5c2cf68648672b4c096d7df376ecfbc605bc4cc838300bd302f629'
RETAINED_NATIVE_RELEASE = '338e488c4203e23d6375726ec8067af815c2d0ec9ee74adc6925f8ef49de9c09'
# Historical pins above remain the preserved BEFORE, never the live sidefile.
NATIVE_ORIGINAL_SHA = '94598c41b7b3342ee7be5206577d127a3c3e90f06972a2160ffdd35e6949da98'
NATIVE_ORIGINAL_RELEASE = '9bb1d7ae186e43b4ea9fa720f7368475af3979d225bee830db4ac90b5083b1e3'
NATIVE_CURRENT_SHA = 'c0766fd42f0f4ab25bffa03bb6620910e9d1cd5c6a90315d94a922b5cdf6dd7a'
NATIVE_ATTEMPT_SHA = '4eb5090ee3f094ae73116bf59412756681641be3df613cad183d8f7b06597e3a'
NATIVE_PRIOR = TRANSACTION + '/epoch5-prior-native-binding.json'
NATIVE_ORIGINAL = TRANSACTION + '/epoch3-prior-receipts/native-binding-original.json'
NATIVE_ATTEMPT = TRANSACTION + '/epoch5-recovery-execution.json'
NATIVE_PHASES = ('stage_exact_release', 'preserve_prior_receipts', 'rebind_prepared_epoch',
    'quiesce_exact_epoch', 'provision_from_retained_resources', 'reopen_existing_database',
    'activate_exact_epoch', 'activate_new_services', 'post_install_checks')
PROFILE = '/home/xuanjun_dev/.openclaw/openclaw.json'
TLS = '/var/lib/xuanjun-development/tls-acme'
TLS_CONFIG = '/etc/xuanjun-development/tls-renewal.json'
PLUGIN = 'xuanjun-p2-native-controller'
PLUGIN_PATH = '/home/xuanjun_dev/.openclaw/extensions/' + PLUGIN
INSTALL_LOCK = '/run/xuanjun-p2-install.lock'
ACTIVATION_LOCK = '/var/lib/xuanjun-development/activation/activation.lock'
RUNNER_GUARD = '/run/xuanjun-p2-runner-isolation.guard'
RUNNER = 'actions.runner.huhongchuan0422-creator-Repository-name-xuanjun-ai-control.' + HOST + '.service'
SOURCE_DB = '/home/xuanjun_dev/uk-stage1-minimal/state.sqlite'
ROLLBACK_DB = '/var/lib/xuanjun-development/backups/' + d.TX + '.sqlite'
DATABASES = (SOURCE_DB, ROLLBACK_DB, d.DB)
PUBLISHERS = frozenset(('/var/lib/xuanjun-development/control.git',
                        '/var/lib/xuanjun-development/service-home/.config/gh'))
WRITER_UNITS = frozenset(('xuanjun-github-intake.timer', 'xuanjun-ledger.socket',
    'xj-root-broker.socket', 'xuanjun-github-intake.service',
    'xuanjun-development-dispatcher.service', 'xuanjun-p2-gateway-relay.service',
    'xuanjun-p2-gateway-relay.socket', 'xuanjun-uk-owner-callback.service',
    'xuanjun-uk-owner-dashboard.service', 'xuanjun-ledger.service',
    'xj-root-broker.service', 'nginx.service', 'xuanjun-uk-openclaw.service',
    'xuanjun-p2-tls-renew.timer', 'xuanjun-p2-tls-renew.service',
    'xuanjun-uk-stage1-minimal.service', 'xj-uk-owner-notify.timer',
    'xj-uk-owner-notify.service', RUNNER))
# systemd239 process-property applicability, restricted to this exact writer set.
TIMER_UNITS = frozenset(('xj-uk-owner-notify.timer', 'xuanjun-github-intake.timer',
                         'xuanjun-p2-tls-renew.timer'))
SOCKET_UNITS = frozenset(('xj-root-broker.socket', 'xuanjun-ledger.socket',
                          'xuanjun-p2-gateway-relay.socket'))
UNIT_PROCESS_FIELDS = frozenset(('MainPID', 'ControlPID', 'ControlGroup'))
LEGACY_MASKS = frozenset('/etc/systemd/system/' + n for n in (
    'xuanjun-uk-stage1-minimal.service', 'xuanjun-uk-openclaw.service',
    'xj-uk-owner-notify.timer', 'xj-uk-owner-notify.service')) | d.OWNER_MASKS
SCHEDULER_ROOTS = frozenset(('/etc/crontab', '/etc/cron.d', '/etc/cron.hourly',
    '/etc/cron.daily', '/etc/cron.weekly', '/etc/cron.monthly', '/var/spool/cron',
    '/var/spool/at', '/home/xuanjun_dev/.config/systemd/user'))
SOCKET_PATHS = frozenset(('/run/xuanjun-development/ledger.sock',
    '/run/xuanjun-development/broker.sock', '/run/xuanjun-development/p2-gateway.sock'))
ADDITIVE_PATHS = frozenset(('/etc/xuanjun-development/p2-owner-process-identity.json',
    '/etc/xuanjun-development/p2-ledger-server-identity.json'))
EXTRA_RECEIPTS = ('tls-lifecycle.json', 'sandbox-profile-original.json',
    'sandbox-profile-candidate.json', 'epoch3-prior-receipts/native-binding-original.json')
MANDATORY_FILES = frozenset(TRANSACTION + '/' + n for n in d.PRESERVED_RECEIPTS) | frozenset(
    TRANSACTION + '/' + n for n in EXTRA_RECEIPTS) | (d.TARGETS - d.OWNER_MASKS) | frozenset(
    (ACTIVE, EPOCHS, PLAN, NATIVE, PROFILE, RUNNER_GUARD, INSTALL_LOCK, ACTIVATION_LOCK))
POLICY_KEYS = frozenset(('schema', 'kind', 'hostname', 'transaction_id', 'owner_evidence_sha256',
    'files', 'directories', 'transaction_inventory', 'releases', 'databases',
    'scheduler_files', 'control_units', 'executables'))


def need(value, label):
    if not value:
        raise ValueError(label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    need(isinstance(raw, bytes) and len(raw) <= 16777216, 'JSON_BOUND')
    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, 'JSON_DUPLICATE_KEY')
            result[key] = value
        return result
    def bad(unused):
        raise ValueError('JSON_NONFINITE')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=bad)


def path(value):
    need(isinstance(value, str) and value.startswith('/') and value != '/' and
         os.path.normpath(value) == value and '\x00' not in value and
         not any(ord(c) < 32 for c in value), 'CANONICAL_PATH')
    return value


def relative(value):
    need(isinstance(value, str) and value and not value.startswith('/') and
         os.path.normpath(value) == value and '..' not in value.split('/') and
         '\x00' not in value and not any(ord(c) < 32 for c in value), 'RELATIVE_PATH')
    return value


def _native_transform(raw, before_release, after_release):
    """Exactly the reviewed epoch5 bridge-path-only transform; no I/O."""
    need(type(raw) is bytes and 0 < len(raw) <= 65536, 'NATIVE_TRANSITION_BYTES_BOUND')
    value = decode(raw)
    d.keys(value, ('ledger', 'gatewayIdentity'), 'NATIVE_BINDING_SCHEMA')
    ledger = value['ledger']
    d.keys(ledger, ('python', 'pythonSha256', 'bridge', 'config', 'files'), 'NATIVE_LEDGER_SCHEMA')
    old = '/opt/xuanjun-control-releases/integration-' + before_release[:16] + '/stage1/native_ledger_bridge.py'
    new = '/opt/xuanjun-control-releases/integration-' + after_release[:16] + '/stage1/native_ledger_bridge.py'
    client = '/etc/xuanjun-development/p2-native-ledger-client.json'
    need(ledger['bridge'] == old and ledger['config'] == client and
         type(ledger['files']) is dict and set(ledger['files']) == {old, client}, 'NATIVE_BINDING_PATHS')
    path(ledger['python']); d.hash_value(ledger['pythonSha256'])
    for digest in ledger['files'].values(): d.hash_value(digest)
    gateway = value['gatewayIdentity']
    d.keys(gateway, ('user', 'exe', 'sha256', 'cgroup'), 'NATIVE_GATEWAY_KEYS')
    need(gateway['user'] == 'xuanjun_dev' and
         gateway['cgroup'] == '/system.slice/xuanjun-uk-openclaw.service', 'NATIVE_GATEWAY_IDENTITY')
    path(gateway['exe']); d.hash_value(gateway['sha256'])
    ledger['bridge'] = new; ledger['files'][new] = ledger['files'].pop(old)
    return d.canonical(value) + b'\n'


def _native_transition_evidence():
    return {'schema': 1, 'kind': 'EPOCH5_NATIVE_REBIND_COMPLETED',
        'phase': 'rebind_prepared_epoch', 'approval_id': 6170703284,
        'attempt_sha256': NATIVE_ATTEMPT_SHA, 'original_sha256': NATIVE_ORIGINAL_SHA,
        'before_sha256': RETAINED_NATIVE_SHA, 'after_sha256': NATIVE_CURRENT_SHA,
        'before_release_sha256': RETAINED_NATIVE_RELEASE, 'after_release_sha256': d.OLD_MANIFEST,
        'original_preserved': True}


def validate_native_transition_evidence(evidence, current_raw):
    """Validate a digest-bound collector projection and exact current bytes.

    This pure check does not authenticate caller provenance. Downstream callers
    must bind evidence to the protected observation and complete approval gate.
    """
    need(type(evidence) is dict and d.same(evidence, _native_transition_evidence()),
         'NATIVE_TRANSITION_EVIDENCE')
    need(type(current_raw) is bytes and 0 < len(current_raw) <= 65536 and
         sha(current_raw) == NATIVE_CURRENT_SHA, 'NATIVE_CURRENT_EXACT_BYTES')
    need(_native_transform(current_raw, d.OLD_MANIFEST, d.OLD_MANIFEST) == current_raw,
         'NATIVE_CURRENT_CANONICAL_BYTES')
    need(sha(_native_transform(current_raw, d.OLD_MANIFEST, RETAINED_NATIVE_RELEASE)) == RETAINED_NATIVE_SHA,
         'NATIVE_HISTORICAL_REVERSE_TRANSFORM')
    return copy.deepcopy(evidence)


def validate_native_transition(current_raw, prior_raw, original_raw, attempt_raw):
    """Recognize only the already completed owned epoch5 native rebind.

    Callers read the four fixed paths with protected metadata/no-follow checks.
    No live file, journal, approval or historical pin is changed here.
    """
    for raw in (current_raw, prior_raw, original_raw):
        need(type(raw) is bytes and 0 < len(raw) <= 65536, 'NATIVE_TRANSITION_BYTES_BOUND')
    need(type(attempt_raw) is bytes and 0 < len(attempt_raw) <= 1048576, 'NATIVE_ATTEMPT_BOUND')
    need(sha(prior_raw) == RETAINED_NATIVE_SHA and sha(original_raw) == NATIVE_ORIGINAL_SHA,
         'NATIVE_PRESERVED_BEFORE_PIN')
    need(sha(attempt_raw) == NATIVE_ATTEMPT_SHA, 'NATIVE_OWNED_ATTEMPT_PIN')
    attempt = decode(attempt_raw)
    need(type(attempt) is dict and type(attempt.get('schema')) is int and attempt['schema'] == 1 and
         attempt.get('stage') == 'HOLD' and attempt.get('automatic_retry') is False and
         attempt.get('historical_replay') is False and attempt.get('legacy_restart') is False and
         attempt.get('production_acceptance') == 'PENDING', 'NATIVE_OWNED_ATTEMPT_SCOPE')
    authorization = attempt.get('authorization', {})
    need(type(authorization) is dict and type(authorization.get('review_id')) is int and
         authorization['review_id'] == 6170703284, 'NATIVE_OWNED_APPROVAL')
    approval = authorization.get('approval')
    expected = {'schema': 1, 'reviewer': 'CHATGPT_NATIVE_TASK5',
        'decision': 'APPROVED_ONE_EXACT_EPOCH5_RESUME_WITH_FENCED_RETAIN_ON_FAILURE',
        'transaction_id': d.TX, 'runtime_manifest_sha256': d.OLD_MANIFEST,
        'expected_epoch': 5, 'proposed_prepared_epoch': 6, 'authorized_attempts': 1,
        'failure_policy': 'FENCE_STOP_RETAIN_NO_REPLAY', 'legacy_restart': False,
        'historical_notification_replay': False, 'production_acceptance': 'PENDING'}
    need(type(approval) is dict and all(k in approval and d.same(approval[k], v) for k, v in expected.items()),
         'NATIVE_OWNED_APPROVAL_BINDING')
    d.hash_value(authorization.get('body_sha256'))
    for attempt_key, approval_key in (('plan_sha256', 'recovery_plan_sha256'),
            ('kit_manifest_sha256', 'recovery_kit_manifest_sha256'), ('snapshot_sha256', 'snapshot_sha256')):
        d.hash_value(attempt.get(attempt_key))
        need(attempt[attempt_key] == approval.get(approval_key), 'NATIVE_OWNED_APPROVAL_HASH_BINDING')
    completed = attempt.get('completed'); phases = attempt.get('phase_evidence')
    need(type(completed) is list and 3 <= len(completed) <= len(NATIVE_PHASES) and
         completed == list(NATIVE_PHASES[:len(completed)]) and type(phases) is dict and
         set(phases) == set(completed) and all(type(v) is dict and v for v in phases.values()),
         'NATIVE_OWNED_PHASE_ORDER')
    phase = phases['rebind_prepared_epoch']
    d.keys(phase, ('descriptor_sha256', 'epoch', 'native_binding', 'tls_reference_sha256'), 'NATIVE_REBIND_PHASE_KEYS')
    need(type(phase['epoch']) is int and phase['epoch'] == 6, 'NATIVE_REBIND_EPOCH')
    for key in ('descriptor_sha256', 'tls_reference_sha256'): d.hash_value(phase[key])
    need(d.same(phase['native_binding'], {'old_sha256': sha(prior_raw), 'new_sha256': sha(current_raw),
                                        'original_preserved': True}), 'NATIVE_OWNED_REBIND_HASHES')
    need(_native_transform(original_raw, NATIVE_ORIGINAL_RELEASE, RETAINED_NATIVE_RELEASE) == prior_raw and
         _native_transform(original_raw, NATIVE_ORIGINAL_RELEASE, d.OLD_MANIFEST) == current_raw,
         'NATIVE_EXACT_COMPLETED_TRANSFORM')
    return validate_native_transition_evidence(_native_transition_evidence(), current_raw)


def validate_policy(p):
    d.keys(p, POLICY_KEYS, 'MEASURED_POLICY_KEYS')
    need(type(p['schema']) is int and p['schema'] == 1 and
         p['kind'] == 'EPOCH7_MEASURED_READ_ONLY_PINS' and p['hostname'] == HOST and
         p['transaction_id'] == d.TX, 'MEASURED_POLICY_SCOPE')
    d.hash_value(p['owner_evidence_sha256'])
    files = p['files']
    need(isinstance(files, dict) and MANDATORY_FILES <= set(files) and len(files) <= 4096,
         'MISSING_EXPECTED_FILE_PINS')
    for name, pin in files.items():
        path(name); d.keys(pin, ('sha256', 'uid', 'gid', 'mode'), 'FILE_PIN_KEYS')
        d.hash_value(pin['sha256'])
        for key in ('uid', 'gid', 'mode'): d.integer(pin[key])
        need(pin['mode'] <= 0o777 and not pin['mode'] & 0o022, 'PIN_FILE_AUTHORITY')
    for name in set(TRANSACTION + '/' + n for n in d.PRESERVED_RECEIPTS) | {PLAN, NATIVE_ORIGINAL}:
        need(tuple(files[name][k] for k in ('uid', 'gid', 'mode')) == (0, 0, 0o600),
             'PROTECTED_RECEIPT_PIN')
    for name, expected in ((NATIVE,(0,0,0o644)),(PROFILE,(1002,1002,0o600)),
            (ACTIVE,(0,0,0o644)),(EPOCHS,(0,0,0o644)),
            (INSTALL_LOCK,(0,0,0o600)),(ACTIVATION_LOCK,(0,0,0o644))):
        need(tuple(files[name][k] for k in ('uid','gid','mode')) == expected, 'FIXED_FILE_AUTHORITY')
    dirs = p['directories']
    need(isinstance(dirs, dict) and '/' in dirs and len(dirs) <= 4096, 'DIRECTORY_PIN_SET')
    for name, pin in dirs.items():
        if name != '/': path(name)
        d.keys(pin, ('uid', 'gid', 'mode'), 'DIRECTORY_PIN_KEYS')
        for key in pin: d.integer(pin[key])
        need(pin['mode'] <= 0o777 and not pin['mode'] & 0o022, 'DIRECTORY_PIN_AUTHORITY')
        if name == TRANSACTION or name.startswith(TRANSACTION + '/'):
            need(pin == {'uid': 0, 'gid': 0, 'mode': 0o700}, 'PRIVATE_TRANSACTION_DIRECTORY')
    for name in files:
        parent = os.path.dirname(name)
        while True:
            need(parent in dirs, 'UNMEASURED_FILE_ANCESTOR')
            if parent == '/': break
            parent = os.path.dirname(parent)
    need(dirs.get(TRANSACTION) == {'uid': 0, 'gid': 0, 'mode': 0o700}, 'TRANSACTION_PIN')
    need(dirs.get(d.GENERATION) == {'uid': 1003, 'gid': 1006, 'mode': 0o750}, 'GENERATION_PIN')
    inventory = p['transaction_inventory']
    need(isinstance(inventory, dict) and inventory, 'TRANSACTION_INVENTORY_REQUIRED')
    for rel, digest in inventory.items():
        relative(rel); d.hash_value(digest)
        need(TRANSACTION + '/' + rel in files and files[TRANSACTION + '/' + rel]['sha256'] == digest,
             'TRANSACTION_PIN_COMPLETENESS')
    need(set(inventory) == {n[len(TRANSACTION)+1:] for n in files if n.startswith(TRANSACTION + '/')},
         'TRANSACTION_INVENTORY_EXACT')
    releases = p['releases']
    need(isinstance(releases, dict) and 3 <= len(releases) <= 16 and
         '/opt/xuanjun-control-releases/integration-' + d.OLD_MANIFEST[:16] in releases,
         'RELEASE_SET_REQUIRED')
    for root, pin in releases.items():
        need(re.fullmatch(r'/opt/xuanjun-control-releases/integration-[0-9a-f]{16}', root), 'RELEASE_PATH')
        d.keys(pin, ('manifest_sha256', 'payloads', 'caches', 'cache_staging'), 'RELEASE_PIN_KEYS')
        d.hash_value(pin['manifest_sha256'])
        need(root.endswith(pin['manifest_sha256'][:16]), 'RELEASE_MANIFEST_IDENTITY')
        need(isinstance(pin['payloads'], dict) and pin['payloads'], 'RELEASE_PAYLOAD_PINS')
        need(isinstance(pin['caches'], dict), 'CACHE_PINS_REQUIRED')
        need(re.fullmatch(r'/opt/xuanjun-control-releases/\.integration-[0-9a-f]{16}', pin['cache_staging']),
             'CACHE_STAGING_PIN_REQUIRED')
        for rel, digest in list(pin['payloads'].items()) + list(pin['caches'].items()):
            relative(rel); d.hash_value(digest)
        need(not set(pin['payloads']) & set(pin['caches']), 'CACHE_PAYLOAD_OVERLAP')
        need(all(re.fullmatch(r'stage1/__pycache__/[a-z][a-z0-9_]*\.cpython-36\.pyc', n)
                 for n in pin['caches']), 'CACHE_SCOPE')
    d.keys(p['databases'], DATABASES, 'DATABASE_SET_PINS_REQUIRED')
    for name, pin in p['databases'].items():
        d.keys(pin, ('sha256', 'uid', 'gid', 'mode', 'sidecars', 'logical_manifest_sha256'), 'DATABASE_PIN_KEYS')
        for key in ('sha256', 'logical_manifest_sha256'): d.hash_value(pin[key])
        need(isinstance(pin['sidecars'], dict) and set(pin['sidecars']) <= {'-wal', '-shm', '-journal'}, 'SIDECAR_PINS')
        need(name == SOURCE_DB or not pin['sidecars'], 'STAGED_DATABASE_SIDECARS')
        for side in pin['sidecars'].values():
            d.keys(side, ('sha256', 'uid', 'gid', 'mode'), 'SIDECAR_PIN_KEYS'); d.hash_value(side['sha256'])
    need(isinstance(p['scheduler_files'], dict) and isinstance(p['control_units'], dict) and
         WRITER_UNITS - {RUNNER, 'nginx.service'} <= set(p['control_units']), 'SCHEDULER_AND_CONTROL_PINS')
    for name, digest in p['scheduler_files'].items(): path(name); d.hash_value(digest)
    for name, value in p['control_units'].items():
        need(re.fullmatch(r'(?:xj-|xuanjun-)[a-zA-Z0-9_.@-]+', name), 'CONTROL_UNIT_NAME')
        need(isinstance(value, dict) and value, 'CONTROL_UNIT_FILES_REQUIRED')
        for file_name, digest in value.items(): path(file_name); d.hash_value(digest)
    d.keys(p['executables'], ('systemctl', 'openssl', 'rpm', 'systemd', 'git'), 'EXECUTABLE_PINS')
    for command in p['executables'].values():
        d.keys(command, ('path', 'sha256'), 'COMMAND_PIN_KEYS'); path(command['path']); d.hash_value(command['sha256'])
        need(command['path'] in files and files[command['path']]['sha256'] == command['sha256'] and
             files[command['path']]['uid'] == 0 and files[command['path']]['mode'] & 0o111, 'COMMAND_FILE_PIN')
    return copy.deepcopy(p)


def activation_chain(raw, active):
    need(raw and raw.endswith(b'\n'), 'EPOCH_JOURNAL_INCOMPLETE')
    rows = raw.splitlines(keepends=True); need(len(rows) <= 10000, 'EPOCH_JOURNAL_BOUND')
    previous, previous_hash = None, '0' * 64
    for seq, line in enumerate(rows, 1):
        record = decode(line)
        d.keys(record, ('schema', 'seq', 'epoch', 'state', 'previous_sha256',
                       'descriptor_sha256', 'descriptor', 'proof'), 'EPOCH_JOURNAL_KEYS')
        value = record['descriptor']; d.keys(value, d.ACTIVATION_KEYS, 'DESCRIPTOR_KEYS')
        need(type(value['schema']) is int and value['schema'] == 1 and
             type(value['epoch']) is int and value['epoch'] > 0 and
             type(value['generation']) is int and value['generation'] > 0 and
             value['state'] in ('PREPARED', 'QUIESCED', 'ACTIVE'), 'DESCRIPTOR_TYPES')
        for key in ('release_sha256', 'config_sha256', 'binary_sha256'): d.hash_value(value[key])
        for key in ('instance', 'ledger_uuid'):
            need(str(uuid.UUID(value[key])) == value[key], 'DESCRIPTOR_UUID')
        path(value['db_path']); path(value['ledger_socket'])
        need(type(record['schema']) is int and record['schema'] == 1 and
             type(record['seq']) is int and record['seq'] == seq and
             type(record['epoch']) is int and record['epoch'] == value['epoch'] and
             record['state'] == value['state'] and isinstance(record['proof'], dict) and
             record['previous_sha256'] == previous_hash and
             record['descriptor_sha256'] == sha(d.canonical(value) + b'\n'), 'EPOCH_JOURNAL_RECORD')
        if previous is None:
            need(value['epoch'] == 1 and value['state'] == 'PREPARED', 'EPOCH_JOURNAL_BEGIN')
        elif value['epoch'] == previous['epoch']:
            need(value['state'] == {'PREPARED': 'QUIESCED', 'QUIESCED': 'ACTIVE'}.get(previous['state']) and
                 all(value[k] == previous[k] for k in d.ACTIVATION_KEYS - {'state'}), 'EPOCH_TRANSITION')
        else:
            need(value['epoch'] == previous['epoch'] + 1 and value['state'] == 'PREPARED', 'EPOCH_MONOTONIC')
        previous, previous_hash = value, sha(line)
    need(previous == active, 'ACTIVATION_JOURNAL_RECONCILIATION_REQUIRED')
    return {'records': len(rows), 'head_sha256': previous_hash, 'sha256': sha(raw)}


def pin_matches(meta, pin):
    need(meta.get('kind') == 'FILE' and meta.get('nlink') == 1 and
         all(meta.get(k) == v for k, v in pin.items()), 'FILE_PIN_OR_AUTHORITY_CHANGED')


def unit_process_fields(unit):
    """Required/optional process properties for the exact supported units.

    These are property applicability rules, not measured process/cgroup facts.
    In systemd239 timers have no cgroup context or service/socket control PID;
    sockets expose ControlPID/ControlGroup but not the service-only MainPID.
    """
    need(type(unit) is str and unit in WRITER_UNITS, 'UNIT_PROCESS_SCOPE')
    optional = UNIT_PROCESS_FIELDS if unit in TIMER_UNITS else (
        frozenset(('MainPID',)) if unit in SOCKET_UNITS else frozenset())
    return UNIT_PROCESS_FIELDS - optional, optional


def validate_unit_process_fields(unit, state, pid_type=str):
    """Validate without adding absent properties; return semantic PID values.

    Zero for an absent inapplicable PID is only a no-process predicate result.
    It must never be inserted into an observed state or presented as measured.
    Independent unit state, recursive cgroups, process and descriptor checks
    remain mandatory at each caller's existing boundary.
    """
    required, optional = unit_process_fields(unit)
    need(type(state) is dict and required <= set(state), 'UNIT_PROCESS_PROPERTIES_REQUIRED')
    need(pid_type is str or pid_type is int, 'UNIT_PROCESS_PID_REPRESENTATION')
    result = []
    for key in ('MainPID', 'ControlPID'):
        if key not in state:
            need(key in optional, 'UNIT_PROCESS_PROPERTIES_REQUIRED');result.append(0);continue
        value = state[key]
        if pid_type is str:
            need(type(value) is str and re.fullmatch(r'0|[1-9][0-9]{0,9}', value) is not None,
                 'UNIT_PROCESS_PID_VALUE')
            number = int(value)
        else:
            need(type(value) is int and 0 <= value <= 9999999999, 'UNIT_PROCESS_PID_VALUE')
            number = value
        need(key not in optional or number == 0, 'UNIT_INAPPLICABLE_PID_NONZERO')
        result.append(number)
    if 'ControlGroup' in state:
        value = state['ControlGroup']
        allowed = ('',) if unit in TIMER_UNITS else ('', '/system.slice/' + unit)
        need(type(value) is str and value in allowed, 'UNIT_PROCESS_CONTROL_GROUP')
    return tuple(result)


def validate_writers(value):
    d.keys(value, ('units', 'masks', 'scheduler_sha256', 'control_files', 'processes', 'manager'), 'WRITER_EVIDENCE_KEYS')
    d.keys(value['units'], WRITER_UNITS, 'WRITER_UNIT_SET')
    d.keys(value['masks'], LEGACY_MASKS, 'LEGACY_MASK_SET')
    for unit, row in value['units'].items():
        d.keys(row, ('state', 'cgroup_entries'), 'WRITER_UNIT_EVIDENCE')
        state = row['state']
        main_pid, control_pid = validate_unit_process_fields(unit, state)
        need(state.get('Id') == unit and state.get('LoadState') in ('loaded', 'masked') and
             state.get('ActiveState') in ('inactive', 'failed') and
             main_pid == control_pid == 0 and
             state.get('NeedDaemonReload') == 'no', 'WRITER_NOT_STOPPED')
        entries = row['cgroup_entries']
        need(isinstance(entries, dict) and all(p.startswith('/sys/fs/cgroup/systemd/system.slice/' + unit + '/') and
             p.endswith('/cgroup.procs') and h == sha(b'') for p, h in entries.items()), 'CGROUP_NOT_EMPTY')
    for name, row in value['masks'].items():
        need(row.get('kind') == 'MASK' and row.get('link') == '/dev/null' and
             (row.get('uid'), row.get('gid'), row.get('nlink'), row.get('mode')) == (0, 0, 1, 0o777) and
             value['units'][os.path.basename(name)]['state'].get('UnitFileState') == 'masked', 'MASK_NOT_PRESERVED')
    need(value['units'][RUNNER]['state'].get('ConditionResult') == 'no', 'RUNNER_NOT_EXCLUDED')
    d.hash_value(value['scheduler_sha256'])
    need(isinstance(value['control_files'], dict) and value['control_files'], 'CONTROL_FILES_UNMEASURED')
    d.keys(value['processes'], ('process_identity_sha256', 'fd_count','background_processes','background_processes_sha256'), 'PROCESS_SCAN_EVIDENCE')
    d.hash_value(value['processes']['process_identity_sha256']); d.integer(value['processes']['fd_count'])
    background=value['processes']['background_processes']
    need(type(background) is list and len(background)<=128 and
         d.digest(background)==value['processes']['background_processes_sha256'],'BACKGROUND_PROCESS_EVIDENCE')
    seen=set()
    for pair in background:
        d.keys(pair,('before','after'),'BACKGROUND_PROCESS_PAIR');need(pair['before']==pair['after'],'BACKGROUND_PROCESS_RACE')
        row=pair['before'];d.keys(row,('pid','starttime','uids','gids','groups','comm','executable',
            'executable_sha256','argv_sha256','unit','kernel_thread'),'BACKGROUND_IDENTITY_FIELDS')
        need(type(row['pid']) is int and row['pid']>0 and row['pid'] not in seen and
             type(row['starttime']) is int and row['starttime']>0,'BACKGROUND_PID_IDENTITY');seen.add(row['pid'])
        need(row['uids']==[1002]*4 and row['executable']=='/usr/bin/ssh' and row['comm']=='ssh' and
             row['unit'] is None and row['kernel_thread'] is False,'BACKGROUND_EXACT_SSH_IDENTITY')
        need(type(row['gids']) is list and len(row['gids'])==4 and type(row['groups']) is list and
             row['groups']==sorted(set(row['groups'])) and len(row['groups'])<=128 and
             all(type(x) is int and 0<=x<2**32 for x in row['gids']+row['groups']),'BACKGROUND_GROUPS')
        d.hash_value(row['executable_sha256']);d.hash_value(row['argv_sha256'])
    need(isinstance(value['manager'], dict) and value['manager'], 'ROOT_MANAGER_UNMEASURED')
    return value


def collect(policy, io):
    """Return (exact delta snapshot, private digest-only supporting evidence).

    IO is intentionally injected. Calling this with a fake does not establish
    host provenance. The concrete host entry is separately gated in snapshot_io.
    """
    p = validate_policy(policy)
    need(io.identity() == {'hostname': HOST, 'euid': 0}, 'FIXED_HOST_ROOT_REQUIRED')
    io.check_locks()
    raw, files = {}, {}
    for name, pin in sorted(p['files'].items()):
        data, row = io.read(name); pin_matches(row, pin); raw[name], files[name] = data, row
    tx_inventory = io.inventory(TRANSACTION)
    tx_directories = io.directory_inventory(TRANSACTION)
    need(set(tx_directories) == {n for n in p['directories'] if n == TRANSACTION or n.startswith(TRANSACTION + '/')},
         'TRANSACTION_DIRECTORY_INVENTORY')
    need(tx_inventory == {TRANSACTION + '/' + n: v for n, v in p['transaction_inventory'].items()},
         'TRANSACTION_INVENTORY_CHANGED')
    absent = {n: io.absent(TRANSACTION + '/' + n) for n in d.ABSENT_EFFECT_PATHS}
    need(all(absent.values()), 'EXISTING_OR_UNCLASSIFIED_ATTEMPT')
    need(all(io.absent(n) for n in ADDITIVE_PATHS | SOCKET_PATHS | {PLUGIN_PATH}),
         'UNCLASSIFIED_PLUGIN_POLICY_OR_SOCKET')
    active = decode(raw[ACTIVE]); d.validate_activation(active, 7, d.OLD_MANIFEST)
    chain = activation_chain(raw[EPOCHS], active)
    receipts = {n: sha(raw[TRANSACTION + '/' + n]) for n in d.PRESERVED_RECEIPTS}
    attempt = decode(raw[TRANSACTION + '/epoch5-recovery-execution.json'])
    need(attempt.get('stage') == 'HOLD' and attempt.get('automatic_retry') is False and
         attempt.get('authorization', {}).get('review_id') == 6170703284 and
         attempt.get('production_acceptance') == 'PENDING', 'CONSUMED_HOLD_ATTEMPT')
    targets = {n: io.mask(n) if n in d.OWNER_MASKS else files[n] for n in d.TARGETS}
    generation = io.directory(d.GENERATION); d.validate_generation(generation)
    before_writers = validate_writers(io.writers(p, DATABASES))
    need(isinstance(before_writers, dict) and before_writers, 'WRITER_EVIDENCE_REQUIRED')
    db_sets = {}
    for name, pin in p['databases'].items():
        data, row = io.read(name, maximum=67108864)
        pin_matches(row, {k: pin[k] for k in ('sha256', 'uid', 'gid', 'mode')})
        sidecars = {}
        for suffix in ('-wal', '-shm', '-journal'):
            if suffix in pin['sidecars']:
                side_data, side = io.read(name + suffix); pin_matches(side, pin['sidecars'][suffix])
                sidecars[suffix] = side
                if suffix == '-wal': need(side_data == b'', 'SOURCE_WAL_NOT_EMPTY')
            else:
                need(io.absent(name + suffix), 'UNEXPECTED_DATABASE_SIDECAR')
        logical = io.logical_manifest(data)
        need(logical.get('sha256') == sha(data) and logical.get('size') == len(data) and
             d.digest(logical) == pin['logical_manifest_sha256'], 'DATABASE_LOGICAL_PIN')
        db_sets[name] = {'file': row, 'sidecars': sidecars, 'logical_manifest': logical}
    cutover = decode(raw[TRANSACTION + '/ledger-cutover.json'])
    need(cutover.get('stage') == 'STAGED' and cutover.get('source_replaced') is False and
         cutover.get('activation_executed') is False and cutover.get('task_replay') is False and
         cutover.get('migration', {}).get('rollback') == db_sets[ROLLBACK_DB]['logical_manifest'] and
         cutover.get('migration', {}).get('generation') == db_sets[d.DB]['logical_manifest'], 'CUTOVER_DATABASE_BINDING')
    plan = decode(raw[PLAN])
    need(tuple(plan['cutover'][k] for k in ('source', 'rollback_snapshot', 'staged_generation')) == DATABASES,
         'PLAN_DATABASE_SET')
    prerequisites = io.prerequisites(plan['runtime']['prerequisites'],
        decode(raw[TRANSACTION + '/prerequisites.json']), decode(raw[TRANSACTION + '/rpm-prerequisites.json']))
    tls = decode(raw[TRANSACTION + '/tls-lifecycle.json'])
    config = decode(raw[TLS_CONFIG])
    need(tls.get('state') == 'READY_ISSUED_AND_RENEWAL_DRYRUN_VERIFIED' and tls.get('config') == config and
         config == decode(raw[TRANSACTION + '/epoch6-tls-renewal-candidate.json']) and
         config.get('release_sha256') == d.OLD_MANIFEST and config.get('root') == TLS and
         config.get('transaction_id') == d.TX and config.get('transaction_directory') == TRANSACTION,
         'TLS_READY_CONFIG_BINDING')
    for key in ('instance', 'generation', 'ledger_uuid'): need(config.get(key) == active[key], 'TLS_ACTIVATION_BINDING')
    tls_observed = io.tls(p)
    need(tls_observed['tree_fingerprint_sha256'] == tls.get('fingerprint') and
         tls_observed['certificate_sha256'] == tls.get('certificate_sha256'), 'TLS_RETAINED_CONTENT_DRIFT')
    sandbox = decode(raw[TRANSACTION + '/sandbox-profile.json'])
    need(sandbox.get('state') == 'RESTORED' and sandbox.get('current_sha256') == sandbox.get('original_sha256') == sha(raw[PROFILE]) and
         raw[PROFILE] == raw[TRANSACTION + '/sandbox-profile-original.json'] and
         sandbox.get('candidate_sha256') == sha(raw[TRANSACTION + '/sandbox-profile-candidate.json']), 'RESTORED_SANDBOX_DRIFT')
    profile = decode(raw[PROFILE]); plugins = profile.get('plugins', {})
    need(isinstance(plugins, dict) and all(PLUGIN not in plugins.get(k, {}) for k in ('entries', 'installs')) and
         PLUGIN not in plugins.get('allow', []), 'PLUGIN_REGISTERED')
    native_transition = validate_native_transition(raw[NATIVE], raw[NATIVE_PRIOR], raw[NATIVE_ORIGINAL], raw[NATIVE_ATTEMPT])
    native = decode(raw[NATIVE])
    need(tuple(files[NATIVE][k] for k in ('uid','gid','mode')) == (0,0,0o644), 'NATIVE_BINDING_AUTHORITY')
    native_components = io.native_identity(native, decode(raw['/etc/xuanjun-development/p2-native-controller.binding.json']))
    bootstrap = decode(raw[TRANSACTION + '/bootstrap-files.json'])
    rows = bootstrap.get('files'); need(isinstance(rows, list) and len(rows) == 7 and len({r['target'] for r in rows}) == 7, 'BOOTSTRAP_SET')
    bootstrap_evidence = {}
    for row in rows:
        target = row['target']; need(target in files and row['state'] == 'PUBLISHED' and io.absent(row['temp']), 'BOOTSTRAP_PUBLISHED_REQUIRED')
        if target != NATIVE:
            need(all(files[target][k] == row[k] for k in ('sha256', 'dev', 'ino', 'mode')) and
                 files[target]['uid'] == row['owner_uid'] and files[target]['gid'] == row['group_gid'], 'BOOTSTRAP_IDENTITY')
        bootstrap_evidence[target] = files[target]
    publisher = decode(raw[TRANSACTION + '/publisher-bootstrap.json'])
    rows = publisher.get('directories'); need(isinstance(rows, list) and len(rows) == 2 and {r['target'] for r in rows} == PUBLISHERS, 'PUBLISHER_SET')
    publishers = [io.publisher(row) for row in rows]
    control_row = next(row for row in rows if row['target'] == '/var/lib/xuanjun-development/control.git')
    control_git = io.control_git_source(plan['runtime']['publisher'], control_row,
        receipts['publisher-bootstrap.json'])
    caches = {root: io.release(root, pin) for root, pin in sorted(p['releases'].items())}
    after_writers = validate_writers(io.writers(p, DATABASES))
    need(before_writers == after_writers, 'WRITER_OBSERVATION_CHANGED')
    # Full reread, not only stat/hash of the descriptor or a single database.
    for name, first in files.items():
        data, row = io.read(name); need(row == first and data == raw[name], 'RETAINED_FILE_RACE')
    for name, first in db_sets.items():
        data, row = io.read(name, maximum=67108864); need(row == first['file'], 'DATABASE_RACE')
        for suffix in ('-wal', '-shm', '-journal'):
            if suffix in first['sidecars']:
                need(io.read(name + suffix)[1] == first['sidecars'][suffix], 'DATABASE_SIDECAR_RACE')
            else: need(io.absent(name + suffix), 'DATABASE_SIDECAR_RACE')
    need(io.directory(d.GENERATION) == generation and io.inventory(TRANSACTION) == tx_inventory,
         'DIRECTORY_OR_TRANSACTION_RACE')
    need(io.directory_inventory(TRANSACTION) == tx_directories, 'TRANSACTION_DIRECTORY_RACE')
    for name in d.OWNER_MASKS: need(io.mask(name) == targets[name], 'MASK_RACE')
    need(all(io.absent(TRANSACTION + '/' + n) for n in absent), 'NEW_ATTEMPT_RACE')
    need(all(io.absent(n) for n in ADDITIVE_PATHS | SOCKET_PATHS | {PLUGIN_PATH}), 'ADDITIVE_OR_SOCKET_RACE')
    need(io.tls(p) == tls_observed, 'TLS_SCAN_RACE')
    need([io.publisher(row) for row in rows] == publishers, 'PUBLISHER_SCAN_RACE')
    need(io.control_git_source(plan['runtime']['publisher'], control_row, receipts['publisher-bootstrap.json'])
         == control_git, 'CONTROL_GIT_SCAN_RACE')
    need({root: io.release(root, pin) for root, pin in sorted(p['releases'].items())} == caches, 'RELEASE_SCAN_RACE')
    need(io.native_identity(native, decode(raw['/etc/xuanjun-development/p2-native-controller.binding.json'])) == native_components, 'NATIVE_COMPONENT_RACE')
    need(io.prerequisites(plan['runtime']['prerequisites'], decode(raw[TRANSACTION + '/prerequisites.json']),
        decode(raw[TRANSACTION + '/rpm-prerequisites.json'])) == prerequisites, 'PREREQUISITE_RACE')
    io.check_locks()
    retained = {'schema': 1, 'policy_sha256': d.digest(p), 'files': files, 'activation_chain': chain,
        'transaction_inventory': tx_inventory, 'transaction_directories': tx_directories, 'database_sets': db_sets, 'tls': tls_observed,
        'bootstrap': bootstrap_evidence, 'native_components': native_components,
        'native_binding_transition': native_transition, 'prerequisites': prerequisites, 'publishers': publishers, 'control_git': control_git, 'release_evidence': caches,
        'additive_paths_absent': sorted(ADDITIVE_PATHS), 'production_sockets_absent': sorted(SOCKET_PATHS),
        'plugin_path_absent': PLUGIN_PATH}
    db = db_sets[d.DB]['file']
    result = {'schema': 1, 'transaction_id': d.TX, 'activation': active, 'epoch_journal_sha256': sha(raw[EPOCHS]),
        'attempt': {'name': 'epoch5-recovery-execution.json', 'sha256': receipts['epoch5-recovery-execution.json'],
                    'state': 'HOLD', 'approval_id': 6170703284, 'consumed': True},
        'targets': targets, 'receipts': receipts,
        'tls': {'state': tls['state'], 'journal_sha256': sha(raw[TRANSACTION + '/tls-lifecycle.json']),
                'certificate_sha256': tls['certificate_sha256'], 'tree_fingerprint_sha256': tls['fingerprint'],
                'config_identity_sha256': d.digest({k: v for k, v in config.items() if k != 'release_sha256'}),
                'release_sha256': d.OLD_MANIFEST},
        'cache_inventories': {root: d.digest(value) for root, value in caches.items()},
        'retained_resource_sha256': d.digest(retained), 'generation': generation,
        'database': dict({k: db[k] for k in ('sha256', 'dev', 'ino', 'uid', 'gid', 'mode', 'nlink')},
            path=d.DB, logical_manifest_sha256=p['databases'][d.DB]['logical_manifest_sha256'], sidecars=[]),
        'sandbox': {'state': 'RESTORED', 'journal_sha256': receipts['sandbox-profile.json'], 'profile_sha256': sha(raw[PROFILE])},
        'plugin_state': 'VERIFIED_ABSENT', 'new_attempt_present': False, 'absent_paths': absent,
        'writer_exclusion': dict({k: True for k in ('all_stopped', 'cgroups_empty', 'legacy_masks_preserved',
            'scheduler_excluded', 'runner_excluded', 'database_fds_excluded')}, evidence_sha256=d.digest(after_writers))}
    d.validate_snapshot(result, d.digest(result)); d.validate_provision_before(result, raw[TRANSACTION + '/epoch6-runtime-provisioning.json'])
    evidence = {'schema': 1, 'kind': 'PRIVATE_DIGEST_ONLY_EPOCH7_SNAPSHOT', 'snapshot_sha256': d.digest(result),
        'retained': retained, 'writers': after_writers, 'install_admission': 'NOT_GRANTED',
        'production_acceptance': 'NOT_VERIFIED', 'target_mutations': 0}
    return result, evidence


def public_summary(snapshot, evidence):
    need(evidence['snapshot_sha256'] == d.digest(snapshot), 'SUMMARY_BINDING')
    return {'schema': 1, 'snapshot_sha256': d.digest(snapshot), 'evidence_sha256': d.digest(evidence),
        'install_admission': 'NOT_GRANTED', 'production_acceptance': 'NOT_VERIFIED', 'target_mutations': 0}
