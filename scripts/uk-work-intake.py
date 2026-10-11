#!/usr/bin/python3 -I
"""Bounded, non-root delivery receipts; not a task registry or release authority.

Deployment is gated separately. No production services/DBs, sudo or channel send.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
import pwd
import re
import selectors
import signal
import socket
import stat
import subprocess
import time

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
BRANCH = 'feature/uk-autonomous-loop-20261011'
CONFIG = '/etc/xuanjun-work-intake.json'
INBOX = '/var/lib/xuanjun-work-intake/requests'
RECEIPTS = '/var/lib/xuanjun-work-intake/receipts'
CHECKOUT = '/home/githubrunner/actions-runner/_work/Repository-name-xuanjun-ai-control/Repository-name-xuanjun-ai-control'
SPEC_PATH = 'plans/WORK_APPROVED_AB_REPAIR_SPEC_20261011.json'
MODELS = ('openai/gpt-6.1-sol', 'openai/gpt-5.6-sol')
DENIED = ('production_db_write', 'old_coordinator_switch', 'trading_permission_change',
          'formal_webhook_change', 'production_deploy', 'old_coordinator_codex_exec',
          'generic_root_or_systemd_grant')
MANUAL_DIGEST = 'deb334171fdbc10d9ab8abff046493526ca5c992428d514629a86cf32859fc6a'
MANUAL_SOURCE = '76c0cfe7f7a4dd9ed52a9dc719897c95c437ba8b'
MANUAL_DESIGN = 'fbe72ffbcb1e277d808f26c61b178f247dab159ea8c97b1fde0808490d8078cf'
MAX_ENVELOPE = 98304


def parse(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except RecursionError:
        raise ValueError('JSON_DEPTH_LIMIT')


def run_bounded(argv, env, timeout, limit):
    process = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    end = time.monotonic() + timeout
    chunks, total = [], 0
    try:
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('CLI_TIMEOUT_EFFECT_UNKNOWN')
            if not selector.select(min(remaining, 1)):
                continue
            chunk = os.read(process.stdout.fileno(), min(65536, limit - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ValueError('CLI_OUTPUT_LIMIT')
            chunks.append(chunk)
        code = process.wait(timeout=max(0.001, end - time.monotonic()))
        return code, b''.join(chunks)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise
    finally:
        selector.close()
        process.stdout.close()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read_file(path, owners, limit=65536):
    """Keep parent fds open; reject symlinks, writable trust boundaries and pipes."""
    if not os.path.isabs(path) or os.path.normpath(path) != path:
        raise ValueError('NON_CANONICAL_PATH')
    parts = path.strip('/').split('/')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent)
            os.close(parent)
            parent = child
            info = os.fstat(parent)
            if info.st_uid not in owners or info.st_mode & 0o022:
                raise ValueError('UNTRUSTED_PARENT')
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent)
    finally:
        os.close(parent)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid not in owners or info.st_mode & 0o022:
            raise ValueError('UNTRUSTED_FILE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        after = os.fstat(fd)
        if len(raw) > limit or (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('OVERSIZE_OR_UNSTABLE_FILE')
        return raw
    finally:
        os.close(fd)


def validate(envelope):
    if not isinstance(envelope, dict) or type(envelope.get('schema')) is not int or envelope['schema'] != 1:
        raise ValueError('ENVELOPE_SCHEMA')
    fields = ('repository', 'branch', 'control_source_sha', 'spec_sha256',
              'spec_base64', 'design_sha256', 'design_base64')
    if (any(not isinstance(envelope.get(k), str) for k in fields)
            or len(encoded(envelope)) > MAX_ENVELOPE):
        raise ValueError('ENVELOPE_TYPES_OR_LIMIT')
    if envelope.get('repository') != REPO or envelope.get('branch') != BRANCH:
        raise ValueError('CONTROL_ORIGIN')
    if re.fullmatch(r'[0-9a-f]{40}', envelope.get('control_source_sha', '')) is None:
        raise ValueError('CONTROL_SHA')
    raw = base64.b64decode(envelope.get('spec_base64', ''), validate=True)
    if not raw or len(raw) > 24576 or digest(raw) != envelope.get('spec_sha256'):
        raise ValueError('SPEC_DIGEST')
    spec = parse(raw.decode('utf-8'))
    if (not isinstance(spec, dict) or type(spec.get('schema')) is not int or spec['schema'] != 1 or spec.get('control_repository') != REPO
            or spec.get('kind') != 'TRUSTED_CONTROL_PLANE_MAINTENANCE'
            or spec.get('authority') != 'CHATGPT_WORK_OWNER_DELEGATED'
            or spec.get('approval') != 'DESIGN_APPROVED_FOR_BOUNDED_IMPLEMENTATION'):
        raise ValueError('SPEC_NOT_APPROVED')
    if any(not isinstance(spec.get(k), dict) for k in ('permissions', 'models', 'budget')):
        raise ValueError('SPEC_OBJECT_TYPES')
    if any(spec.get('permissions', {}).get(k) is not False for k in DENIED):
        raise ValueError('PRODUCTION_PERMISSION_DENIED')
    models = spec.get('models', {})
    if (models.get('primary'), models.get('sole_fallback')) != MODELS or (
            models.get('route') != 'EXISTING_CHATGPT_OAUTH_CODEX'
            or models.get('paid_api') != 'DENY' or models.get('other_models') != 'DENY'):
        raise ValueError('MODEL_POLICY')
    budget = spec.get('budget', {})
    if (type(budget.get('patch_rounds_total')) is not int
            or not 1 <= budget['patch_rounds_total'] <= 3
            or type(budget.get('seconds_per_model_attempt')) is not int
            or not 1 <= budget['seconds_per_model_attempt'] <= 1200
            or budget.get('repeated_same_failure') != 'HOLD_CHECKPOINT'
            or budget.get('old_failed_budget') != 'PRESERVE'):
        raise ValueError('BUDGET')
    task = spec.get('parent_task')
    if not isinstance(task, str) or re.fullmatch(r'[A-Z0-9_]{1,160}', task) is None:
        raise ValueError('TASK_ID')
    roles = spec.get('roles')
    if (not isinstance(roles, list) or not 1 <= len(roles) <= 8
            or any(not isinstance(role, dict) or not isinstance(role.get('role'), str)
                   or re.fullmatch(r'[A-Z0-9_]{1,40}', role['role']) is None for role in roles)
            or len({role['role'] for role in roles}) != len(roles)):
        raise ValueError('ROLE_CONTRACT')
    design = base64.b64decode(envelope.get('design_base64', ''), validate=True)
    if not design or len(design) > 32768 or digest(design) != envelope.get('design_sha256'):
        raise ValueError('DESIGN_DIGEST')
    if envelope['spec_sha256'] == MANUAL_DIGEST and envelope['design_sha256'] != MANUAL_DESIGN:
        raise ValueError('MANUAL_CONTRACT_CHANGED')
    design.decode('utf-8')
    if not isinstance(spec.get('design'), str) or re.fullmatch(r'plans/[A-Za-z0-9_-]+\.md', spec['design']) is None:
        raise ValueError('DESIGN_PATH')
    # Source SHA is a receipt binding, not a reason to repeat identical work.
    key = digest((task + '\n' + envelope['spec_sha256']).encode('ascii'))
    return key, spec, raw, design


class Store:
    """Private receipt journal; stores no tasks, leases or production DB state."""
    def __init__(self, directory, shared=False):
        info = os.lstat(directory)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != (0o2750 if shared else 0o700)):
            raise ValueError('UNSAFE_RECEIPT_DIRECTORY')
        self.file_mode = 0o640 if shared else 0o600
        self.gid = info.st_gid
        self.fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        actual = os.fstat(self.fd)
        if (info.st_dev, info.st_ino) != (actual.st_dev, actual.st_ino):
            self.close()
            raise ValueError('DIRECTORY_CHANGED')

    def close(self):
        os.close(self.fd)

    def lock(self):
        fd = os.open('intake.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                     0o600, dir_fd=self.fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            os.close(fd)
            raise ValueError('UNSAFE_LOCK')
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def load(self, key, limit=65536):
        try:
            fd = os.open(key + '.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != self.file_mode:
                raise ValueError('UNSAFE_RECEIPT')
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('OVERSIZE_RECEIPT')
        return parse(raw.decode('utf-8'))

    def save(self, key, value):
        if re.fullmatch(r'[0-9a-f]{64}', key) is None:
            raise ValueError('RECEIPT_KEY')
        name = '.' + key + '-' + os.urandom(8).hex()
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     self.file_mode, dir_fd=self.fd)
        try:
            if os.fstat(fd).st_gid != self.gid:
                raise ValueError('SHARED_GROUP_BOUNDARY_NOT_INSTALLED')
            os.fchmod(fd, self.file_mode)  # Preserve read-only sharing under UMask=0077.
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(encoded(value))
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(name, key + '.json', src_dir_fd=self.fd, dst_dir_fd=self.fd)
            os.fsync(self.fd)
        finally:
            os.close(fd)
            try:
                os.unlink(name, dir_fd=self.fd)
            except FileNotFoundError:
                pass


def current_source(envelope, publisher):
    # Actions uses a detached checkout. Read bytes only: no Git hooks/filters,
    # credentials, ls-remote, root impersonation or mutable source-code imports.
    head = read_file(CHECKOUT + '/.git/HEAD', {0, publisher}, limit=128).decode('ascii').strip()
    return head == envelope['control_source_sha']


def clean_agent(response, source, spec_digest, spec_roles=None):
    if (not isinstance(response, dict) or response.get('control_source_sha') != source
            or response.get('spec_sha256') != spec_digest or response.get('server') != HOST
            or response.get('actual_model') != MODELS[1]
            or response.get('state') not in ('RECEIVED', 'STARTED', 'WAITING_HUMAN')
            or not isinstance(response.get('roles'), dict) or not response['roles']):
        raise ValueError('UNBOUND_AGENT_RECEIPT')
    states = ('STARTED', 'NOT_STARTED', 'RECEIVED', 'WAITING_HUMAN',
              'WAITING_A2_CONTRACT_FREEZE', 'DONE', 'FAILED', 'HOLD')
    for role, state in response['roles'].items():
        if (re.fullmatch(r'[A-Z0-9_]{1,40}', role) is None
                or not isinstance(state, str) or state not in states
                or spec_roles is not None and role not in spec_roles):
            raise ValueError('INVALID_ROLE_RECEIPT')
    clean = {k: response[k] for k in ('server', 'control_source_sha',
             'spec_sha256', 'actual_model', 'state', 'roles')}
    clean['blocker'] = response.get('blocker') if response.get('blocker') in (
        None, 'SOURCE_UNAVAILABLE', 'PERMISSION_DENIED', 'QUOTA_UNAVAILABLE',
        'DEPENDENCY_NOT_READY', 'AUTH_REJECTED') else 'REDACTED_UNKNOWN_BLOCKER'
    return clean


def clean_receipt(value, key):
    if not isinstance(value, dict) or type(value.get('schema')) is not int or value['schema'] != 1:
        raise ValueError('RECEIPT_SCHEMA')
    for field, pattern in (('receipt_key', r'[0-9a-f]{64}'),
                           ('parent_task', r'[A-Z0-9_]{1,160}'),
                           ('control_source_sha', r'[0-9a-f]{40}'),
                           ('spec_sha256', r'[0-9a-f]{64}'),
                           ('design_sha256', r'[0-9a-f]{64}')):
        if not isinstance(value.get(field), str) or re.fullmatch(pattern, value[field]) is None:
            raise ValueError('RECEIPT_BINDING')
    expected = digest((value['parent_task'] + '\n' + value['spec_sha256']).encode('ascii'))
    if value['receipt_key'] != key or key != expected:
        raise ValueError('RECEIPT_KEY_MISMATCH')
    states = ('STARTED_OWNER_RELAYED', 'DISPATCHING_EFFECT_UNKNOWN_NO_AUTORETRY',
              'AGENT_RECEIPT_REPORTED', 'WAITING_RECONCILIATION_EFFECT_UNKNOWN')
    if value.get('state') not in states or type(value.get('received_at')) is not int:
        raise ValueError('RECEIPT_STATE')
    clean = {k: value[k] for k in ('schema', 'receipt_key', 'parent_task',
             'control_source_sha', 'spec_sha256', 'design_sha256', 'received_at', 'state')}
    clean.update(production_pass=False, independent_role_start_probe=False,
                 idempotent=value.get('idempotent') is True,
                 wake_executed=value.get('wake_executed') is True)
    if value['state'] == 'STARTED_OWNER_RELAYED':
        if value['spec_sha256'] != MANUAL_DIGEST or value['design_sha256'] != MANUAL_DESIGN:
            raise ValueError('MANUAL_RECEIPT_BINDING')
        clean.update(manual_control_source_sha=MANUAL_SOURCE,
                     roles={'A1': 'STARTED', 'A2': 'STARTED',
                            'B': 'WAITING_A2_CONTRACT_FREEZE', 'C': 'NOT_STARTED'},
                     evidence='evidence/uk-intake/OWNER_RELAYED_REPAIR_START_20261011.json')
    elif value['state'] == 'AGENT_RECEIPT_REPORTED':
        clean['agent_receipt'] = clean_agent(value.get('agent_receipt'),
                                            value['control_source_sha'], value['spec_sha256'])
    return clean


def source_blob(workspace, commit, path, limit):
    """Verify the complete raw commit/tree/blob chain; ignore replace refs."""
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_NO_REPLACE_OBJECTS': '1'}
    def object_bytes(kind, sha, bound):
        code, raw = run_bounded(['/usr/bin/git', '--no-replace-objects', '-C', workspace,
                                 '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null',
                                 'cat-file', kind, sha], env, 15, bound)
        actual = hashlib.sha1(kind.encode('ascii') + b' ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()
        if code or actual != sha:
            raise ValueError('SOURCE_OBJECT_HASH_MISMATCH')
        return raw
    raw_commit = object_bytes('commit', commit, 65536)
    tree = raw_commit.split(b'\n', 1)[0]
    if re.fullmatch(b'tree [0-9a-f]{40}', tree) is None:
        raise ValueError('SOURCE_COMMIT_TREE')
    tree_sha = tree[5:].decode('ascii')
    components = path.split('/')
    if any(re.fullmatch(r'[A-Za-z0-9_.-]+', p) is None or p in ('.', '..', '.git') for p in components):
        raise ValueError('SOURCE_PATH')
    for index, component in enumerate(components):
        raw_tree = object_bytes('tree', tree_sha, 262144)
        matches, position = [], 0
        while position < len(raw_tree):
            zero = raw_tree.index(b'\0', position)
            mode, name = raw_tree[position:zero].split(b' ', 1)
            oid = raw_tree[zero + 1:zero + 21]
            if len(oid) != 20:
                raise ValueError('SOURCE_TREE_FORMAT')
            if name == component.encode('ascii'):
                matches.append((mode, oid.hex()))
            position = zero + 21
        if len(matches) != 1:
            raise ValueError('SOURCE_PATH_NOT_UNIQUE')
        mode, sha = matches[0]
        if index < len(components) - 1:
            if mode != b'40000':
                raise ValueError('SOURCE_DIRECTORY_TYPE')
            tree_sha = sha
        else:
            if mode != b'100644':
                raise ValueError('SOURCE_FILE_TYPE')
            return object_bytes('blob', sha, limit)


def transport_receipt(data):
    # Gateway CLI expected profile; actual installation must verify this schema.
    # No recursive search: unrelated JSON and natural-language assertions cannot
    # attest provider/model. A changed transport profile fails closed.
    if not isinstance(data, dict) or data.get('status') != 'ok' or not isinstance(data.get('result'), dict):
        raise ValueError('GATEWAY_SCHEMA_NOT_VERIFIED')
    result = data['result']
    meta = result.get('meta')
    if not isinstance(meta, dict) or not isinstance(meta.get('agentMeta'), dict):
        raise ValueError('GATEWAY_SCHEMA_NOT_VERIFIED')
    model = meta['agentMeta'].get('model')
    provider = meta['agentMeta'].get('provider')
    if (model not in (MODELS[1], 'gpt-5.6-sol') or provider != 'openai'
            or data.get('error') or result.get('error') or meta.get('aborted') is True):
        raise ValueError('RETURNED_MODEL_NOT_VERIFIED')
    payloads = result.get('payloads')
    if (not isinstance(payloads, list) or len(payloads) != 1
            or not isinstance(payloads[0], dict) or not isinstance(payloads[0].get('text'), str)):
        raise ValueError('EXACT_JSON_RECEIPT_REQUIRED')
    receipt = parse(payloads[0]['text'])
    if not isinstance(receipt, dict) or receipt.get('actual_model') != MODELS[1]:
        raise ValueError('MODEL_RECEIPT_MISMATCH')
    receipt['actual_model'] = MODELS[1]  # mechanically verified transport value
    return receipt


def accept(envelope, store, wake):
    key, spec, raw, design = validate(envelope)
    lock = store.lock()
    try:
        previous = store.load(key)
        if previous is not None:
            previous = clean_receipt(previous, key)
            if previous.get('design_sha256') != envelope['design_sha256']:
                return dict(previous, state='HOLD_DESIGN_CHANGED_NEW_SPEC_REQUIRED',
                            idempotent=True, wake_executed=False)
            # DISPATCHING after a crash is ambiguous: NEVER automatically retry.
            return dict(previous, observed_control_source_sha=envelope['control_source_sha'],
                        idempotent=True, wake_executed=False)
        result = {'schema': 1, 'parent_task': spec['parent_task'], 'receipt_key': key,
                  'control_source_sha': envelope['control_source_sha'],
                  'spec_sha256': envelope['spec_sha256'],
                  'design_sha256': envelope['design_sha256'], 'received_at': int(time.time()),
                  'idempotent': False, 'production_pass': False}
        if envelope['spec_sha256'] == MANUAL_DIGEST:
            result.update(state='STARTED_OWNER_RELAYED', wake_executed=False,
                          manual_control_source_sha=MANUAL_SOURCE,
                          roles={'A1': 'STARTED', 'A2': 'STARTED',
                                 'B': 'WAITING_A2_CONTRACT_FREEZE', 'C': 'NOT_STARTED'},
                          evidence='evidence/uk-intake/OWNER_RELAYED_REPAIR_START_20261011.json')
            store.save(key, clean_receipt(result, key))
            return result
        # Durable at-most-once wake attempt precedes any Gateway call.
        result.update(state='DISPATCHING_EFFECT_UNKNOWN_NO_AUTORETRY', wake_executed=False)
        store.save(key, clean_receipt(result, key))
        try:
            response = wake(envelope, spec, raw, design, key)
            allowed_roles = {role['role'] for role in spec.get('roles', [])}
            clean = clean_agent(response, envelope['control_source_sha'],
                                envelope['spec_sha256'], allowed_roles)
            result.update(state='AGENT_RECEIPT_REPORTED', agent_receipt=clean,
                          wake_executed=True, independent_role_start_probe=False)
        except Exception:
            # Raw model output/errors may contain credentials; do not journal them.
            result.update(state='WAITING_RECONCILIATION_EFFECT_UNKNOWN', wake_executed=True)
        result = clean_receipt(result, key)
        store.save(key, result)
        return result
    finally:
        os.close(lock)


def gateway_wake(config, envelope, spec, raw, design, key):
    """Run as the existing service user; never root/runuser/sudo or --deliver."""
    root = '/home/xuanjun_dev'
    cli = root + '/.openclaw/bin/openclaw'
    env = {'HOME': root, 'LANG': 'C.UTF-8',
           'PATH': root + '/.openclaw/tools/node-v24.21.0/bin:/usr/local/bin:/usr/bin:/bin'}
    code, auth = run_bounded([cli, 'models', 'auth', 'list', '--provider', 'openai', '--json'],
                             env, 20, 65536)
    # Provider-filtered response, reject mixed or unknown routes before inference.
    types = []
    def visit(obj, provider='openai'):
        if isinstance(obj, dict):
            provider = obj.get('provider', provider)
            if provider == 'openai':
                types.extend(obj[k] for k in ('type', 'mode') if k in obj)
            for value in obj.values():
                if isinstance(value, (dict, list)):
                    visit(value, provider)
        elif isinstance(obj, list):
            for value in obj:
                visit(value, provider)
    visit(parse(auth.decode('utf-8')))
    if code or not types or any(t != 'oauth' for t in types):
        raise ValueError('OAUTH_ROUTE_NOT_CONFIRMED')
    # Current verified fallback; this intake never probes an unavailable primary.
    message = ('Work approved bounded maintenance handoff. Receipt key: ' + key +
               '. Control SHA: ' + envelope['control_source_sha'] +
               '. Spec SHA256: ' + envelope['spec_sha256'] +
               '. Preserve existing tasks/checkpoints/budgets; do not restart an already running spec. '
               'Only coordinate approved roles. No production DB/deploy/old Coordinator CODEX_EXEC/'
               'formal Webhook/trade permissions/customer messages. Return exactly one JSON object '
               'with server, control_source_sha, spec_sha256, actual_model, state '
               '(RECEIVED/STARTED/WAITING_HUMAN), roles, blocker. Report STARTED only after role start. '
               'Do not recursively delegate beyond the supplied role contract.\nSPEC:\n' +
               raw.decode('utf-8') + '\nAPPROVED DESIGN:\n' + design.decode('utf-8'))
    if not current_source(envelope, pwd.getpwnam('githubrunner').pw_uid):
        raise ValueError('SOURCE_CHANGED_BEFORE_MODEL_REQUEST')
    code, response = run_bounded([cli, 'agent', '--agent', 'main', '--session-key',
                               'agent:main:work-intake-' + key, '--model', MODELS[1],
                               '--message', message, '--thinking', 'low', '--timeout', '60', '--json'],
                              env, 75, 65536)
    if code:
        raise ValueError('GATEWAY_RESULT_UNKNOWN')
    return transport_receipt(parse(response.decode('utf-8')))


def main():
    if os.getuid() == 0 or socket.gethostname().split('.')[0] != HOST:
        raise SystemExit('STOP_NONROOT_UK_ONLY')
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--publish', action='store_true')
    group.add_argument('--report', action='store_true')
    args = parser.parse_args()
    config = parse(read_file(CONFIG, {0}).decode('utf-8'))
    if config != {'inbox': INBOX, 'consumer_state': RECEIPTS}:
        raise ValueError('FIXED_DELIVERY_PATHS_ONLY')
    publisher = pwd.getpwnam('githubrunner').pw_uid
    consumer = pwd.getpwnam('xuanjun_dev').pw_uid
    expected = publisher if args.publish or args.report else consumer
    if os.getuid() != expected:
        raise SystemExit('STOP_WRONG_SERVICE_ACCOUNT')
    inbox = config['inbox']
    if args.report:
        names = [name for name in os.listdir(RECEIPTS)
                 if re.fullmatch(r'[0-9a-f]{64}\.json', name)]
        if len(names) > 256:
            raise ValueError('RECEIPT_CAPACITY_HOLD')
        for name in sorted(names):
            try:
                value = parse(read_file(os.path.join(RECEIPTS, name), {0, consumer}).decode('utf-8'))
                print(json.dumps(clean_receipt(value, name[:-5]), sort_keys=True))
            except (OSError, ValueError, TypeError, KeyError):
                print(json.dumps({'state': 'REJECTED_INVALID_RECEIPT', 'receipt_file': name}))
        return
    store = Store(inbox if args.publish else config['consumer_state'], shared=True)
    try:
        if args.publish:
            if os.environ.get('GITHUB_REPOSITORY') != REPO or os.environ.get('GITHUB_REF') != 'refs/heads/' + BRANCH:
                raise ValueError('PUSH_ORIGIN_REQUIRED')
            sha = os.environ['GITHUB_SHA']
            if re.fullmatch(r'[0-9a-f]{40}', sha) is None:
                raise ValueError('CONTROL_SHA')
            workspace = os.environ['GITHUB_WORKSPACE']
            if workspace != CHECKOUT:
                raise ValueError('FIXED_CHECKOUT_ONLY')
            raw = source_blob(workspace, sha, SPEC_PATH, 24576)
            spec = parse(raw.decode('utf-8'))
            if not isinstance(spec, dict):
                raise ValueError('SPEC_OBJECT')
            design_path = spec.get('design', '')
            if re.fullmatch(r'plans/[A-Za-z0-9_-]+\.md', design_path) is None:
                raise ValueError('DESIGN_PATH')
            design = source_blob(workspace, sha, design_path, 32768)
            envelope = {'schema': 1, 'repository': REPO, 'branch': BRANCH,
                        'control_source_sha': sha, 'spec_sha256': digest(raw),
                        'spec_base64': base64.b64encode(raw).decode('ascii'),
                        'design_sha256': digest(design),
                        'design_base64': base64.b64encode(design).decode('ascii')}
            key, _, _, _ = validate(envelope)
            publication_key = digest((sha + '\n' + envelope['spec_sha256']).encode('ascii'))
            lock = store.lock()
            try:
                if not current_source(envelope, publisher):
                    raise ValueError('CHECKOUT_SHA_MOVED')
                existing = store.load(publication_key, MAX_ENVELOPE)
                if existing is not None and encoded(existing) != encoded(envelope):
                    raise ValueError('IMMUTABLE_PUBLICATION_CHANGED')
                if existing is None:
                    store.save(publication_key, envelope)
            finally:
                os.close(lock)
            print(json.dumps({'state': 'PUBLISHED', 'receipt_key': key,
                              'control_source_sha': sha, 'spec_sha256': digest(raw)}))
        else:
            # Parent/file checks bind this readonly inbox to the publisher UID.
            names = [name for name in os.listdir(inbox)
                     if re.fullmatch(r'[0-9a-f]{64}\.json', name)]
            if len(names) > 256:
                raise ValueError('INBOX_CAPACITY_HOLD')
            for name in sorted(names):
                if re.fullmatch(r'[0-9a-f]{64}\.json', name) is None:
                    continue
                try:
                    envelope = parse(read_file(os.path.join(inbox, name), {0, publisher}, MAX_ENVELOPE).decode('utf-8'))
                    validate(envelope)
                    publication_key = digest((envelope['control_source_sha'] + '\n' + envelope['spec_sha256']).encode('ascii'))
                    if publication_key != name[:-5]:
                        raise ValueError('ENVELOPE_KEY_MISMATCH')
                    if not current_source(envelope, publisher):
                        continue  # Superseded source is never woken.
                    receipt = accept(envelope, store,
                                     lambda e, s, r, d, k: gateway_wake(config, e, s, r, d, k)
                                     if current_source(e, publisher) else None)
                    print(json.dumps(receipt, sort_keys=True))
                    if receipt.get('wake_executed') and not receipt.get('idempotent'):
                        break
                except (OSError, ValueError, TypeError, KeyError):
                    print(json.dumps({'state': 'REJECTED_INVALID_ENVELOPE', 'receipt_file': name}))
    finally:
        store.close()


if __name__ == '__main__':
    main()
