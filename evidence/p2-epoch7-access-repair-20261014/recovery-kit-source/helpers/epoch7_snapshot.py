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
    for name in set(TRANSACTION + '/' + n for n in d.PRESERVED_RECEIPTS) | {PLAN}:
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


def validate_writers(value):
    d.keys(value, ('units', 'masks', 'scheduler_sha256', 'control_files', 'processes', 'manager'), 'WRITER_EVIDENCE_KEYS')
    d.keys(value['units'], WRITER_UNITS, 'WRITER_UNIT_SET')
    d.keys(value['masks'], LEGACY_MASKS, 'LEGACY_MASK_SET')
    for unit, row in value['units'].items():
        d.keys(row, ('state', 'cgroup_entries'), 'WRITER_UNIT_EVIDENCE')
        state = row['state']
        need(state.get('Id') == unit and state.get('LoadState') in ('loaded', 'masked') and
             state.get('ActiveState') in ('inactive', 'failed') and
             state.get('MainPID', '0' if unit.endswith(('.timer', '.socket')) else None) == '0' and
             state.get('ControlPID', '0' if unit.endswith(('.timer', '.socket')) else None) == '0' and
             state.get('ControlGroup') in ('', '/system.slice/' + unit) and
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
    need(sha(raw[NATIVE]) == RETAINED_NATIVE_SHA, 'NATIVE_RETAINED_EXACT_BYTES')
    native = decode(raw[NATIVE]); original = decode(raw[TRANSACTION + '/epoch3-prior-receipts/native-binding-original.json'])
    need(set(native) == set(original) == {'ledger', 'gatewayIdentity'}, 'NATIVE_BINDING_SCHEMA')
    transformed = copy.deepcopy(original); ledger = transformed['ledger']; old_bridge = ledger['bridge']
    new_bridge = '/opt/xuanjun-control-releases/integration-' + RETAINED_NATIVE_RELEASE[:16] + '/stage1/native_ledger_bridge.py'
    need(old_bridge in ledger['files'] and ledger['config'] == '/etc/xuanjun-development/p2-native-ledger-client.json', 'NATIVE_BINDING_PATH')
    ledger['bridge'] = new_bridge; ledger['files'][new_bridge] = ledger['files'].pop(old_bridge)
    need(native == transformed, 'NATIVE_BINDING_REBIND_DRIFT')
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
        'bootstrap': bootstrap_evidence, 'native_components': native_components, 'prerequisites': prerequisites, 'publishers': publishers, 'control_git': control_git, 'release_evidence': caches,
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
