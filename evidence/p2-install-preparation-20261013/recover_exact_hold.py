"""One separately reviewed recovery of the frozen P2 QUIESCED failure.

verify-only reads host evidence. resume requires a NEW independent approval
bound to this file and the exact verification snapshot; old approval is never
treated as a second install grant. No receipt deletion, restaging, NSS replay,
release overwrite, historical notification replay or legacy writer restart.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import socket
import stat
import sys
import urllib.request

BASE = '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
TX = 'c529c379-9341-4510-8384-fc6be1e412e5'
CAND = BASE + '/complete-install-candidate-38503014520'
DIRECTORY = BASE + '/legacy-isolation-' + TX
PLAN_SHA = 'ec1d617857845c43eff6bed2b70a0c00a5dad8dc52df95785bed3ee3d775335a'
MANIFEST_SHA = '9bb1d7ae186e43b4ea9fa720f7368475af3979d225bee830db4ac90b5083b1e3'
SOURCE = 'd75b5b6deea22b7e66569096f72f81c639516133'
TREE = '60e0e41ac84ca17db96b5057ff9b2a341a4ec1f3'
DB_SHA = 'a6b3847009ca7ee394772b7cf0144b90f82d1c68a3e9b4d3e9c4656f50c28d60'
REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
MARKER = 'CHATGPT_NATIVE_TASK5_EXACT_HOLD_RECOVERY_ACCEPTANCE\n'
RUNNER = 'actions.runner.huhongchuan0422-creator-Repository-name-xuanjun-ai-control.iZd7oeikknn1z21sq6ji6zZ.service'


def require(value, code):
    if not value:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path, private=False, maximum=16777216, owner_uid=0):
    require(os.path.realpath(path) == path, 'RECOVERY_PATH_ALIAS')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        data = stream.read(maximum + 1)
        end = os.fstat(stream.fileno())
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
            len(data) <= maximum and info.st_uid == owner_uid and
            not info.st_mode & 0o022, 'RECOVERY_FILE_AUTHORITY')
    require((info.st_size, info.st_mtime_ns) == (end.st_size, end.st_mtime_ns),
            'RECOVERY_FILE_CHANGED_DURING_READ')
    if private:
        require(info.st_gid == 0 and stat.S_IMODE(info.st_mode) == 0o600,
                'RECOVERY_PRIVATE_AUTHORITY')
    return data, info


def load_renderer(root, manifest):
    path = root + '/scripts/uk-integration-install.py'
    data, unused = read(path)
    require(sha(data) == manifest['files']['scripts/uk-integration-install.py'],
            'RECOVERY_RENDERER_HASH')
    namespace = {'__name__': 'recovery_reviewed_renderer', '__file__': path}
    exec(compile(data, path, 'exec'), namespace)
    return namespace


def validate_release(root, release, manifest, manifest_sha, reader=read):
    """Verify frozen inputs AND deterministic identity-rendered release bytes."""
    renderer = load_renderer(root, manifest)
    payloads = {}
    for relative, wanted in sorted(manifest['files'].items()):
        require(not relative.startswith('/') and '..' not in relative.split('/'),
                'RECOVERY_MANIFEST_PATH')
        original, unused = reader(root + '/' + relative)
        require(sha(original) == wanted, 'RECOVERY_ORIGINAL_HASH')
        expected = renderer['render_identity_bytes'](relative, original, manifest_sha, manifest)
        installed, unused = reader(release + '/' + relative)
        require(installed == expected, 'RECOVERY_RELEASE_RENDERED_HASH')
        payloads[release + '/' + relative] = (original, expected)
    return payloads


def source_reader(payloads, original_reader):
    """Only provision's exact validated release source paths yield raw inputs.

    Target, backup, receipt and other reads always use the original reader.
    Recheck installed bytes before accepting the captured source. Caller must
    validate all release bytes under the install lock before constructing this.
    """
    def controlled(path, limit=1024 * 1024):
        observed, info = original_reader(path, limit)
        if path in payloads:
            value, expected = payloads[path]
            require(observed == expected, 'RECOVERY_SOURCE_CHANGED_AFTER_VERIFICATION')
            require(len(value) <= limit, 'RECOVERY_SOURCE_BOUND')
            return value, info
        return observed, info
    return controlled


def validate_hold(receipt, plan, active, cutover):
    require(receipt.get('schema') == 1 and receipt.get('transaction_id') == TX and
            receipt.get('stage') == 'HOLD' and receipt.get('failed_stage') == 'LEGACY_QUIESCED' and
            receipt.get('epoch') == 1 and receipt.get('error_type') == 'ValueError' and
            receipt.get('rollback_error_type') == 'ValueError' and
            receipt.get('rollback') == ['ACTIVATION_FENCED_EPOCH_2'] and
            receipt.get('legacy_writer_restarted') is False and
            receipt.get('oauth_copied') is False and receipt.get('new_paid_api_usage') == 'NONE' and
            receipt.get('recovery') == 'MANUAL_RECONCILIATION_REQUIRED_NO_RESTART' and
            receipt.get('plan_sha256') == sha(canonical(plan)) and
            receipt.get('release') == '/opt/xuanjun-control-releases/' + plan['runtime']['release_directory'],
            'RECOVERY_EXACT_HOLD_REQUIRED')
    expected = dict(plan['activation'])
    expected.pop('expected_epoch')
    expected.update(schema=1, state='PREPARED', epoch=2)
    require(active == expected, 'RECOVERY_EXACT_FENCED_IDENTITY')
    require(cutover.get('transaction_id') == TX and cutover.get('stage') == 'STAGED' and
            cutover.get('plan_sha256') == sha(canonical(plan['cutover'])) and
            cutover.get('source_replaced') is False and cutover.get('activation_executed') is False and
            cutover.get('task_replay') is False and
            receipt.get('cutover_receipt_sha256') == sha(canonical(cutover)),
            'RECOVERY_EXACT_STAGED_CUTOVER')


def verify_prerequisites(manager, plan):
    import grp
    import pwd
    data, unused = read(manager.path, private=True)
    receipt = json.loads(data.decode())
    require(receipt.get('schema') == 1 and receipt.get('plan_sha256') == sha(canonical(plan)) and
            receipt.get('restored') is not True and
            all(a.get('state') == 'DONE' for a in receipt.get('actions', [])),
            'RECOVERY_PREREQUISITE_JOURNAL')
    for name, gid in plan['groups'].items():
        group = grp.getgrnam(name)
        require(group.gr_gid == gid, 'RECOVERY_GROUP_IDENTITY')
        allowed = {'xuanjun-dispatcher', 'xuanjun-callback'} if name == 'xuanjun-control-db' else {name}
        require(set(group.gr_mem).issubset(allowed), 'RECOVERY_GROUP_MEMBERS')
    for name, value in plan['users'].items():
        user = pwd.getpwnam(name)
        require((user.pw_uid, user.pw_gid, user.pw_dir, user.pw_shell) ==
                (value['uid'], value['gid'], value['home'], '/sbin/nologin'), 'RECOVERY_USER_IDENTITY')
        require(set(os.getgrouplist(name, value['gid'])) ==
                {value['gid']} | {plan['groups'][g] for g in value['groups']},
                'RECOVERY_USER_MEMBERSHIP')
    for value in plan['directories']:
        manager.directory_matches(value)
    for value in plan['binaries']:
        data, info = read(value['target'], maximum=536870912)
        require(sha(data) == value['sha256'] and info.st_gid == 0 and
                stat.S_IMODE(info.st_mode) == 0o555, 'RECOVERY_BINARY_IDENTITY')
    return sha(read(manager.path, private=True)[0])


def validate_directories(root):
    for parent, dirs, files in os.walk(root, followlinks=False):
        info = os.lstat(parent)
        require(os.path.realpath(parent) == parent and stat.S_ISDIR(info.st_mode) and
                info.st_uid == 0 and not info.st_mode & 0o022, 'RECOVERY_DIRECTORY_AUTHORITY')
        require(not any(os.path.islink(parent + '/' + name) for name in dirs), 'RECOVERY_DIRECTORY_ALIAS')
        require(not any(name.endswith('.pyc') for name in files), 'RECOVERY_BYTECODE_PRESENT')


def no_runner_or_old_worker():
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            with open('/proc/' + pid + '/comm') as stream:
                name = stream.read(256).strip()
            require(not name.startswith(('Runner.Listener', 'Runner.Worker')), 'RECOVERY_RUNNER_PROCESS')
            with open('/proc/' + pid + '/status') as stream:
                status = stream.read(65537)
            uid = next(line.split()[1] for line in status.splitlines() if line.startswith('Uid:'))
            if uid == '1002':
                require(os.readlink('/proc/' + pid + '/exe') == '/usr/bin/ssh', 'RECOVERY_OLD_WORKER_PROCESS')
            if uid in ('1003', '1004', '1005', '1008'):
                raise ValueError('RECOVERY_RETAINED_ACCOUNT_HAS_PROCESS')
        except FileNotFoundError:
            raise ValueError('RECOVERY_PROCESS_SCAN_RACE')


def scheduler_exclusion():
    import subprocess
    path = BASE + '/consolidated-readiness-38503324102/protected-readiness-snapshot.json'
    data, unused = read(path, private=True)
    require(sha(data) == '2eeb429cc186b25f41f00217b6710a0a055d00058418ded0c187e350c6f27fab',
            'RECOVERY_BASELINE_AUDIT_DRIFT')
    baseline = json.loads(data.decode())['sections']['remaining_control_entry_inventory']
    expected = {r['path']: r['sha256'] for r in baseline['scheduler_metadata']}
    observed = {}
    for root in ('/etc/crontab','/etc/cron.d','/etc/cron.hourly','/etc/cron.daily',
                 '/etc/cron.weekly','/etc/cron.monthly','/var/spool/cron','/var/spool/at',
                 '/home/xuanjun_dev/.config/systemd/user'):
        if not os.path.lexists(root):
            continue
        require(not os.path.islink(root), 'RECOVERY_SCHEDULER_ALIAS')
        paths = [root] if os.path.isfile(root) else []
        if not paths:
            for parent, dirs, files in os.walk(root, followlinks=False):
                require(not any(os.path.islink(parent+'/'+n) for n in dirs), 'RECOVERY_SCHEDULER_ALIAS')
                paths.extend(parent+'/'+n for n in files)
                require(len(paths) <= 2048, 'RECOVERY_SCHEDULER_BOUND')
        for path in paths:
            require(os.path.realpath(path) == path, 'RECOVERY_SCHEDULER_ALIAS')
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as stream:
                data = stream.read(1048577)
            require(len(data) <= 1048576, 'RECOVERY_SCHEDULER_BOUND')
            observed[path] = sha(data)
    require(observed == expected, 'RECOVERY_SCHEDULER_DRIFT')
    result = subprocess.run(['/usr/bin/systemctl','list-unit-files','--no-legend','--no-pager'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    require(result.returncode == 0, 'RECOVERY_UNIT_INVENTORY_FAILED')
    names = {line.split()[0] for line in result.stdout.decode().splitlines()
             if line.split() and line.split()[0].startswith(('xj-','xuanjun-'))}
    require(names == set(baseline['registered_control_units']), 'RECOVERY_CONTROL_UNIT_DRIFT')
    for unit, old in baseline['registered_control_units'].items():
        if 'unit_sha256' in old:
            require(sha(read(old['FragmentPath'])[0]) == old['unit_sha256'], 'RECOVERY_CONTROL_SCRIPT_DRIFT')
        for script in old.get('script_metadata', []):
            require(sha(read(script['path'], owner_uid=os.stat(script['path']).st_uid)[0]) == script['sha256'],
                    'RECOVERY_CONTROL_SCRIPT_DRIFT')
    return sha(canonical(observed))


def original_postcheck(plan, root, result):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'complete_install_executor.py')
    code, unused = read(path)
    require(sha(code) == 'e83b769b64547d75e130423b88684459d62f247ee1bd9b604d6740e3445bdb78',
            'RECOVERY_ORIGINAL_POSTCHECK_HASH')
    ns = {'__name__': 'recovery_original_postcheck', '__file__': path}
    exec(compile(code, path, 'exec'), ns)
    return ns['post_install_checks'](plan, root, result)


def fd_exclusion(paths):
    identities = {(os.stat(p).st_dev, os.stat(p).st_ino) for p in paths if os.path.exists(p)}
    checked = 0
    for pid in os.listdir('/proc'):
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        directory = '/proc/' + pid + '/fd'
        try:
            names = os.listdir(directory)
            for name in names:
                checked += 1
                require(checked <= 1000000, 'RECOVERY_FD_BOUND')
                info = os.stat(directory + '/' + name)
                require((info.st_dev, info.st_ino) not in identities, 'RECOVERY_DATABASE_HOLDER')
        except (FileNotFoundError, PermissionError):
            raise ValueError('RECOVERY_FD_SCAN_INCOMPLETE')
    return checked


def snapshot():
    import subprocess
    plan_bytes, unused = read(CAND + '/protected-core-install-plan.json', private=True)
    require(sha(plan_bytes) == PLAN_SHA, 'RECOVERY_ORIGINAL_PLAN_HASH')
    plan = json.loads(plan_bytes.decode())
    root = plan['artifact']['root']
    require(root == CAND + '/xuanjun-p2-package' and plan['transaction_id'] == TX and
            plan['artifact']['source_commit'] == SOURCE and plan['artifact']['source_tree'] == TREE,
            'RECOVERY_ORIGINAL_BUNDLE')
    manifest_bytes, unused = read(plan['artifact']['manifest'])
    require(sha(manifest_bytes) == MANIFEST_SHA, 'RECOVERY_MANIFEST_HASH')
    manifest = json.loads(manifest_bytes.decode())
    require(len(manifest['files']) == 102, 'RECOVERY_RUNTIME_COUNT')
    release = '/opt/xuanjun-control-releases/' + plan['runtime']['release_directory']
    validate_directories(root)
    validate_directories(release)
    payloads = validate_release(root, release, manifest, MANIFEST_SHA)
    sys.path.insert(0, root + '/stage1')
    from activation_control import ActivationStore
    from ledger_backup import database_manifest
    from legacy_host_adapter import LegacyHostAdapter
    from p2_fixed_host_runtime import FixedHostRuntime
    import p2_auxiliary_isolation as auxiliary
    receipt_bytes, unused = read(CAND + '/install-receipt.json', private=True)
    cutover_bytes, unused = read(DIRECTORY + '/ledger-cutover.json', private=True)
    receipt, cutover = json.loads(receipt_bytes.decode()), json.loads(cutover_bytes.decode())
    activation = ActivationStore('/var/lib/xuanjun-development/activation/active.json',
                                 '/var/lib/xuanjun-development/activation/epochs.jsonl',
                                 '/var/lib/xuanjun-development/activation/activation.lock')
    active = activation.read()
    validate_hold(receipt, plan, active, cutover)
    runtime = FixedHostRuntime(DIRECTORY)
    require(not os.path.lexists(runtime.receipt_path) and
            not os.path.lexists(DIRECTORY + '/recovery-execution.json'), 'RECOVERY_ALREADY_ATTEMPTED')
    for name in ('runtime-boot.json', 'tls-lifecycle.json', 'rpm-prerequisites.json',
                 'bootstrap-files.json', 'publisher-bootstrap.json', 'sandbox-profile.json'):
        require(not os.path.lexists(DIRECTORY + '/' + name), 'RECOVERY_UNCLASSIFIED_PROVISION_EFFECT')
    prerequisites_sha = verify_prerequisites(runtime.prerequisites, plan['runtime']['prerequisites'])
    auxiliary.verify(plan['runtime']['auxiliary_isolation'])
    adapter = LegacyHostAdapter(DIRECTORY)
    ref = plan['cutover']['legacy_isolation']
    for path, wanted in ((DIRECTORY + '/legacy-units.json', ref['legacy_state_sha256']),
                         (DIRECTORY + '/owner-isolation-receipt.json', ref['receipt_sha256']),
                         (ref['original_plan_path'], ref['original_plan_sha256'])):
        require(sha(read(path, private=True)[0]) == wanted, 'RECOVERY_LEGACY_ADOPTION_REFERENCE')
    for name in ('xj-uk-owner-notify.timer', 'xj-uk-owner-notify.service'):
        target = '/etc/systemd/system/' + name
        require(os.path.islink(target) and os.readlink(target) == '/dev/null', 'RECOVERY_NOTIFIER_MASK')
        value = subprocess.run(['/usr/bin/systemctl', 'show', name,
                                '--property=ActiveState,MainPID,UnitFileState'],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        states = dict(line.split('=', 1) for line in value.stdout.decode().splitlines() if '=' in line)
        require(value.returncode == 0 and states.get('ActiveState') == 'inactive' and
                states.get('MainPID', '0') == '0' and states.get('UnitFileState') == 'masked',
                'RECOVERY_NOTIFIER_STATE')
        group = '/sys/fs/cgroup/systemd/system.slice/' + name
        for parent, dirs, files in os.walk(group):
            if 'cgroup.procs' in files:
                with open(parent + '/cgroup.procs') as stream:
                    require(not stream.read(65537).strip(), 'RECOVERY_NOTIFIER_CGROUP')
    observation = adapter.measure_quiescence(plan['cutover']['legacy_bindings'])
    require(all(observation['proof'].get(k) is True for k in
                ('identity_verified', 'coordinator_inactive', 'parent_unit_inactive',
                 'cgroups_empty', 'restart_inhibited')), 'RECOVERY_FRESH_QUIESCENCE')
    source, backup, generation = (plan['cutover'][k] for k in
                                   ('source', 'rollback_snapshot', 'staged_generation'))
    for path in (source, backup, generation):
        for suffix in ('-wal', '-shm', '-journal'):
            require(not os.path.lexists(path + suffix), 'RECOVERY_DATABASE_SIDECAR')
    require(sha(read(source, owner_uid=1002)[0]) == DB_SHA, 'RECOVERY_CANONICAL_DATABASE_DRIFT')
    require(database_manifest(backup) == cutover['migration']['rollback'] and
            database_manifest(generation) == cutover['migration']['generation'], 'RECOVERY_STAGED_DATABASE_DRIFT')
    fds = fd_exclusion((source, backup, generation))
    no_runner_or_old_worker()
    scheduler_sha = scheduler_exclusion()
    prior_prereq = runtime.prerequisites.preflight
    prior_gateway = runtime._verify_gateway_preflight
    def retained_preflight(value):
        require(value == plan['runtime']['prerequisites'], 'RECOVERY_PREREQUISITE_PLAN_DRIFT')
        verify_prerequisites(runtime.prerequisites, value)
        return True
    def retained_gateway(value):
        require(value.get('legacy_cutover') == plan['cutover'], 'RECOVERY_CUTOVER_PLAN_DRIFT')
        measured = adapter.measure_quiescence(plan['cutover']['legacy_bindings'])
        require(measured['proof'] == observation['proof'], 'RECOVERY_QUIESCENCE_DRIFT')
    runtime.prerequisites.preflight = retained_preflight
    runtime._verify_gateway_preflight = retained_gateway
    try:
        runtime.preflight(plan['runtime'], plan['auth'], plan['tls'])
    finally:
        runtime.prerequisites.preflight = prior_prereq
        runtime._verify_gateway_preflight = prior_gateway
    check = subprocess.run(['/usr/bin/systemctl', 'show', RUNNER,
                            '--property=MainPID,ActiveState,ConditionResult'],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    states = dict(line.split('=', 1) for line in check.stdout.decode().splitlines() if '=' in line)
    require(check.returncode == 0 and states.get('MainPID') == '0' and
            states.get('ActiveState') == 'inactive' and states.get('ConditionResult') == 'no' and
            os.path.isfile('/run/xuanjun-p2-runner-isolation.guard'), 'RECOVERY_RUNNER_NOT_ISOLATED')
    evidence = {'schema': 1, 'transaction_id': TX, 'artifact': 11865804223,
                'plan_sha256': PLAN_SHA, 'manifest_sha256': MANIFEST_SHA,
                'hold_receipt_sha256': sha(receipt_bytes), 'cutover_sha256': sha(cutover_bytes),
                'prerequisites_sha256': prerequisites_sha, 'active': active,
                'backup_sha256': sha(read(backup)[0]), 'generation_sha256': sha(read(generation)[0]),
                'epoch_journal_sha256': sha(read(activation.epoch_journal)[0]),
                'scheduler_inventory_sha256': scheduler_sha,
                'files_verified': 102, 'fd_scope_complete': True,
                'runner_isolated': True, 'historical_notification_replay': False,
                'effects': 0, 'production_acceptance': 'PENDING'}
    return evidence, (plan, root, runtime, activation, adapter, observation, payloads)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('RECOVERY_APPROVAL_REDIRECT')


def approval(review_id, expected_snapshot):
    url = 'https://api.github.com/repos/' + REPO + '/issues/comments/' + str(review_id)
    with urllib.request.build_opener(NoRedirect()).open(url, timeout=20) as response:
        raw = response.read(65537)
    require(len(raw) <= 65536, 'RECOVERY_APPROVAL_BOUND')
    comment = json.loads(raw.decode())
    require(comment.get('id') == review_id and comment.get('user', {}).get('id') == 332398908 and
            comment.get('user', {}).get('login') == 'huhongchuan0422-creator', 'RECOVERY_APPROVAL_AUTHOR')
    body = comment.get('body', '')
    require(body.startswith(MARKER), 'RECOVERY_NEW_APPROVAL_REQUIRED')
    value = json.loads(body[len(MARKER):])
    code = sha(read(os.path.abspath(__file__))[0])
    expected = {'schema': 1, 'reviewer': 'CHATGPT_NATIVE_TASK5',
                'decision': 'APPROVED_ONE_EXACT_HOLD_RESUME_AND_FENCED_FAILURE_RECOVERY',
                'transaction_id': TX, 'artifact': 11865804223, 'plan_sha256': PLAN_SHA,
                'manifest_sha256': MANIFEST_SHA, 'recovery_executor_sha256': code,
                'snapshot_sha256': expected_snapshot, 'expected_epoch': 2,
                'retain_prerequisites_on_failure': True, 'legacy_restart': False,
                'historical_notification_replay': False}
    require(value == expected, 'RECOVERY_EXACT_NEW_APPROVAL')
    return {'review_id': review_id, 'body_sha256': sha(body.encode()), 'approval': value}


def resume(evidence, context, authorization):
    from ledger_cutover_transaction import _atomic_receipt
    import p2_fixed_host_runtime as runtime_module
    plan, root, runtime, activation, adapter, observation, payloads = context
    attempt = DIRECTORY + '/recovery-execution.json'
    require(not os.path.lexists(attempt), 'RECOVERY_ATTEMPT_ALREADY_EXISTS')
    state = {'schema': 1, 'stage': 'AUTHORIZED', 'transaction_id': TX,
             'snapshot_sha256': sha(canonical(evidence)), 'authorization': authorization,
             'legacy_writer_restarted': False, 'historical_notification_replay': False,
             'prerequisites_policy': 'RETAIN_IN_PLACE_NO_NSS_REPLAY'}
    _atomic_receipt(attempt, state)
    original, unused = read(CAND + '/install-receipt.json', private=True)
    require(sha(original) == evidence['hold_receipt_sha256'], 'RECOVERY_HOLD_CHANGED')
    fd = os.open(DIRECTORY + '/original-install-hold.json', os.O_WRONLY | os.O_CREAT |
                 os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(original); stream.flush(); os.fsync(stream.fileno())
    source_paths = {('/opt/xuanjun-control-releases/' + plan['runtime']['release_directory'] +
                    '/' + b['source']): payloads['/opt/xuanjun-control-releases/' +
                    plan['runtime']['release_directory'] + '/' + b['source']]
                    for b in plan['runtime']['provisioning']}
    original_reader = runtime_module._read_regular
    runtime_module._read_regular = source_reader(source_paths, original_reader)
    receipt = {'schema': 1, 'transaction_id': TX, 'plan_sha256': sha(canonical(plan)),
               'stage': 'LEGACY_QUIESCED', 'legacy_writer_restarted': False,
               'oauth_copied': False, 'new_paid_api_usage': 'NONE',
               'release': '/opt/xuanjun-control-releases/' + plan['runtime']['release_directory'],
               'epoch': 2, 'cutover_receipt_sha256': json.loads(original.decode())['cutover_receipt_sha256']}
    provision = None
    activation_requested = False
    stop_requested = False
    current = evidence['active']
    try:
        current = activation.transition('PREPARED', 'QUIESCED', 2, current['instance'], observation['proof'])
        _atomic_receipt(CAND + '/install-receipt.json', receipt)
        state['stage'] = 'QUIESCED'; _atomic_receipt(attempt, state)
        provision = runtime.provision(receipt['release'], plan['runtime'])
        require(isinstance(provision, dict) and set(provision) ==
                {'schema', 'receipt_sha256', 'rollback_complete'} and provision['schema'] == 1 and
                re.fullmatch('[0-9a-f]{64}', provision['receipt_sha256']) and
                provision['rollback_complete'] is True, 'RECOVERY_PROVISION_RECEIPT')
        receipt.update(stage='RUNTIME_PROVISIONED', provisioning_receipt_sha256=provision['receipt_sha256'])
        _atomic_receipt(CAND + '/install-receipt.json', receipt)
        reopened = runtime.reopen_database(current)
        require(reopened == {'database_reopened': True}, 'RECOVERY_DATABASE_REOPEN')
        current = activation.transition('QUIESCED', 'ACTIVE', 2, current['instance'], reopened)
        activation_requested = True
        require(adapter.restore_legacy_files(gateway_only=True) ==
                {'unit_files_restored': True, 'services_restarted': False}, 'RECOVERY_GATEWAY_REBIND')
        require(runtime.activate(plan['runtime'], current) == {'services_active': True},
                'RECOVERY_RUNTIME_ACTIVATION')
        receipt.update(stage='COMPLETE', status='P2_INSTALL_TRANSACTION_COMPLETE')
        _atomic_receipt(CAND + '/install-receipt.json', receipt)
        state['stage'] = 'COMPLETE_PENDING_POSTINSTALL'; _atomic_receipt(attempt, state)
        state['post_install_checks'] = original_postcheck(plan, root, receipt)
        state['stage'] = 'COMPLETE_POSTCHECKED'; _atomic_receipt(attempt, state)
        return receipt
    except Exception as error:
        state.update(stage='HOLD', error_type=type(error).__name__, automatic_retry=False,
                     prerequisites_retained=True, recovery='MANUAL_RECONCILIATION_REQUIRED_NO_RESTART')
        rollback = []
        try:
            fenced = activation.fence(current['epoch'], current['instance'])
            rollback.append('ACTIVATION_FENCED_EPOCH_' + str(fenced['epoch']))
            if activation_requested:
                stop_requested = True
                runtime.stop_new(plan['runtime']); rollback.append('NEW_RUNTIME_STOPPED')
            if provision is not None:
                runtime.restore(provision); rollback.append('PROVISIONING_RESTORED')
            adapter.restore_legacy_files(preserve_mask=True)
            rollback.append('LEGACY_MASKS_PRESERVED')
        except Exception as rollback_error:
            state['rollback_error_type'] = type(rollback_error).__name__
            if activation_requested and not stop_requested:
                stop_requested = True
                try:
                    runtime.stop_new(plan['runtime'])
                    rollback.append('NEW_RUNTIME_STOPPED_WITH_FENCE_HOLD')
                except Exception:
                    rollback.append('NEW_RUNTIME_STOP_FAILED_HOLD')
        receipt.update(stage='HOLD', failed_stage=receipt['stage'], error_type=type(error).__name__,
                       rollback=rollback, recovery='MANUAL_RECONCILIATION_REQUIRED_NO_RESTART')
        if 'rollback_error_type' in state:
            receipt['rollback_error_type'] = state['rollback_error_type']
        _atomic_receipt(CAND + '/install-receipt.json', receipt)
        state['rollback'] = rollback; _atomic_receipt(attempt, state)
        raise
    finally:
        runtime_module._read_regular = original_reader


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--operation', choices=('verify-only', 'resume'), required=True)
    parser.add_argument('--review-id', type=int)
    parser.add_argument('--snapshot-sha256')
    args = parser.parse_args()
    require(os.geteuid() == 0 and socket.gethostname().split('.')[0] ==
            'iZd7oeikknn1z21sq6ji6zZ', 'RECOVERY_FIXED_ROOT_HOST')
    # No mutations during verify-only: even the lock must already exist.
    import fcntl
    fd = os.open('/run/xuanjun-p2-install.lock', os.O_RDONLY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1 and
            stat.S_IMODE(info.st_mode) == 0o600, 'RECOVERY_INSTALL_LOCK_AUTHORITY')
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        evidence, context = snapshot()
        digest = sha(canonical(evidence))
        if args.operation == 'verify-only':
            print('RECOVERY_SNAPSHOT=' + canonical(evidence).decode())
            print('RECOVERY_SNAPSHOT_SHA256=' + digest)
            print('RECOVERY_VERIFY_ONLY_EFFECTS=0_INSTALL_NOT_AUTHORIZED')
            return
        require(args.review_id is not None and args.review_id > 0 and
                args.snapshot_sha256 == digest, 'RECOVERY_FRESH_APPROVED_SNAPSHOT_REQUIRED')
        authorized = approval(args.review_id, digest)
        result = resume(evidence, context, authorized)
        print('RECOVERY_RESULT=' + canonical(result).decode())
        print('PRODUCTION_ACCEPTANCE=PENDING_POSTINSTALL_CHECKS')
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()
