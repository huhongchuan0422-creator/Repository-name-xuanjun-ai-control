"""Executable, fail-closed UK development dispatcher entry point.

This starts only the new DevelopmentLoop.  It neither creates tasks nor edits
the old Coordinator.  Deployment must run it under the reviewed service unit.
"""
import argparse
import fcntl
import hashlib
import json
import os
import pwd
import re
import signal
import socket
import stat
import struct
import subprocess
import sys

from activation_control import ActivationStore
from codex_app_server_worker import CodexAppServerWorker
from development_loop import DevelopmentLoop
from development_pipeline import CliBackend, DevelopmentPipeline
from execution_ledger import ExecutionLedger


SHA = re.compile(r'^[0-9a-f]{40}$')
SAFE_USER = re.compile(r'^[a-z_][a-z0-9_-]{0,30}$')
REQUIRED = frozenset([
    'config_version', 'control_repository', 'source_commit', 'repositories',
    'db_path', 'dispatcher_lock', 'github_writer_lock', 'workspace_root',
    'service_home', 'worker_home', 'codex_home', 'worker_user', 'codex_bin',
    'gh_bin', 'path', 'required_checks', 'model', 'max_workers',
])
REQUIRED_V2 = REQUIRED | frozenset([
    'activation_descriptor', 'activation_epoch_journal', 'activation_lock',
    'broker_socket', 'broker_client', 'release_sha256', 'ledger_uuid',
    'generation', 'instance', 'ledger_socket',
])


def _canonical(value, name, forbidden=('/', '/home', '/tmp', '/opt', '/var')):
    if (not isinstance(value, str) or not os.path.isabs(value)
            or os.path.realpath(value) != value or value in forbidden):
        raise ValueError(name + ' must be a dedicated canonical absolute path')
    return value


def load_config(path, run=None):
    if (not isinstance(path, str) or not os.path.isabs(path)
            or os.path.realpath(path) != path or os.path.islink(path)):
        raise ValueError('config path must be canonical, absolute and not a symlink')
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    info=os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid not in (0,os.geteuid())
            or info.st_mode & 0o022 or info.st_size>65536):
        os.close(fd); raise ValueError('unsafe configuration file')
    with os.fdopen(fd,'rb') as handle:
        raw_config = handle.read()
    config = json.loads(raw_config.decode('utf-8'))
    if (not isinstance(config, dict) or config.get('config_version') not in (1, 2)
            or set(config) != (REQUIRED_V2 if config.get('config_version') == 2 else REQUIRED)):
        raise ValueError('configuration keys mismatch')
    if config['model'] not in ('gpt-6.1-sol', 'gpt-5.6-sol'):
        raise ValueError('unsupported config/model')
    if not SHA.fullmatch(config['source_commit']):
        raise ValueError('full lowercase source commit required')
    if (not SAFE_USER.fullmatch(config['worker_user'])
            or not config['worker_user'].startswith('xj_')
            or config['worker_user'] in ('root', 'toor')):
        raise ValueError('invalid isolated worker user')
    try:
        account = pwd.getpwnam(config['worker_user'])
    except KeyError:
        account = None  # --check-config before identity provisioning is allowed.
    if account is not None and account.pw_uid in (0,os.geteuid()):
        raise ValueError('privileged/shared worker identity rejected')
    if config['max_workers'] not in (1, 2):
        raise ValueError('max_workers must be 1 or 2')
    if (not isinstance(config['required_checks'], list) or not config['required_checks']
            or len(set(config['required_checks'])) != len(config['required_checks'])
            or any(not isinstance(v, str) or not v.strip() for v in config['required_checks'])):
        raise ValueError('explicit unique CI checks required')
    if (not isinstance(config['repositories'], dict) or
            set(config['repositories']) != {config['control_repository']}):
        raise ValueError('only the configured control repository is allowed')
    for key in ('db_path', 'dispatcher_lock', 'github_writer_lock', 'workspace_root',
                'service_home', 'worker_home', 'codex_home', 'codex_bin', 'gh_bin'):
        _canonical(config[key], key, forbidden=('/', '/home', '/tmp', '/opt', '/var'))
    if config['config_version'] == 2:
        for key in ('activation_descriptor', 'activation_epoch_journal',
                    'activation_lock', 'broker_socket', 'broker_client'):
            _canonical(config[key], key, forbidden=('/', '/home', '/tmp', '/opt', '/var'))
        _canonical(config['ledger_socket'], 'ledger_socket',
                   forbidden=('/', '/home', '/tmp', '/opt', '/var'))
        if (not re.fullmatch(r'[0-9a-f]{64}', config['release_sha256'])
                or type(config['generation']) is not int or config['generation'] < 1
                or not re.fullmatch(r'[0-9a-f-]{36}', config['ledger_uuid'])
                or not re.fullmatch(r'[0-9a-f-]{36}', config['instance'])):
            raise ValueError('invalid activation identity configuration')
    source = _canonical(config['repositories'][config['control_repository']], 'repository source')
    for key in ('codex_bin','gh_bin'):
        info=os.stat(config[key],follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode & 0o022
                or not info.st_mode & 0o111):
            raise ValueError('untrusted executable: '+key)
    if any(os.path.commonpath([root, config['db_path']]) == root for root in
           (config['workspace_root'], config['worker_home'], config['codex_home'])):
        raise ValueError('authoritative DB must be outside worker-accessible roots')
    roots=[config['service_home'],config['worker_home'],config['codex_home'],config['workspace_root']]
    if len(set(roots)) != 4 or any(os.path.commonpath([left,right]) in (left,right)
            for index,left in enumerate(roots) for right in roots[index+1:]):
        raise ValueError('service, auth and workspace roots must be distinct')
    if (not isinstance(config['path'], str) or not config['path'] or
            any(not os.path.isabs(v) for v in config['path'].split(os.pathsep))):
        raise ValueError('explicit absolute PATH required')
    runner = run or subprocess.run
    result = runner(['git', '-c', 'core.hooksPath=/dev/null', 'rev-parse', 'HEAD'],
                    cwd=source, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    timeout=10, check=False)
    observed = result.stdout.decode('ascii', 'replace').strip() if result.returncode == 0 else ''
    if observed != config['source_commit']:
        raise ValueError('control source HEAD does not match approved commit')
    config['_loaded_sha256'] = hashlib.sha256(raw_config).hexdigest()
    return config


def isolation_prefix(config, workdir, claim=None):
    """Build the fixed broker client invocation; never acquire root via sudo."""
    if config.get('config_version') != 2:
        raise ValueError('broker-backed configuration version 2 required')
    required = ('task_id', 'fence', 'generation', 'epoch', 'instance')
    if not isinstance(claim, dict) or any(key not in claim for key in required):
        raise ValueError('fully fenced broker claim required')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', claim['task_id']) or type(claim['fence']) is not int:
        raise ValueError('invalid broker task identity')
    task_key = hashlib.sha256(claim['task_id'].encode('utf-8')).hexdigest()[:24]
    main_root = os.path.join(config['workspace_root'], task_key)
    if workdir == main_root:
        role, artifact_sha = 'DEVELOPMENT', None
    elif (workdir.startswith(main_root + '-qa-')
          and re.fullmatch(r'[0-9a-f]{40}', workdir[len(main_root) + 4:])):
        role, artifact_sha = 'QA', workdir[len(main_root) + 4:]
    else:
        raise ValueError('workdir is not the broker-derived task root')
    prefix = [config['broker_client'], '--socket=' + config['broker_socket'],
            '--operation=launch', '--task-id=' + claim['task_id'],
            '--fence=' + str(claim['fence']), '--generation=' + str(claim['generation']),
            '--epoch=' + str(claim['epoch']), '--instance=' + claim['instance'],
            '--role=' + role]
    if artifact_sha is not None:
        prefix.append('--artifact-sha=' + artifact_sha)
    return prefix + ['--']


class RootBrokerPolicy(object):
    """Fail-closed authorization for the separately installed root broker.

    The socket peer chooses only launch/stop/status and a fenced task identity.
    Binary, UID, task root and unit name are derived from root-owned policy.
    """
    REQUEST_KEYS = frozenset(['operation', 'task_id', 'fence', 'generation',
                              'epoch', 'instance', 'role', 'artifact_sha'])

    def __init__(self, activation, ledger, dispatcher_uid, worker_user,
                 codex_bin, binary_sha256, task_root):
        self.activation, self.ledger = activation, ledger
        self.dispatcher_uid, self.worker_user = dispatcher_uid, worker_user
        self.codex_bin = _canonical(codex_bin, 'broker binary')
        self.task_root = _canonical(task_root, 'broker task root')
        if type(dispatcher_uid) is not int or dispatcher_uid < 1:
            raise ValueError('broker dispatcher UID must be unprivileged')
        if not re.fullmatch(r'[0-9a-f]{64}', binary_sha256):
            raise ValueError('broker binary digest required')
        self.binary_sha256 = binary_sha256

    def _binary_digest(self):
        digest = hashlib.sha256()
        fd = os.open(self.codex_bin, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                    or info.st_mode & 0o022 or not info.st_mode & 0o111):
                raise PermissionError('broker binary is not trusted')
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        finally:
            os.close(fd)
        return digest.hexdigest()

    def authorize(self, peer_uid, request):
        if peer_uid != self.dispatcher_uid:
            raise PermissionError('broker peer UID rejected')
        if not isinstance(request, dict) or set(request) != self.REQUEST_KEYS:
            raise ValueError('broker request keys mismatch')
        operation = request['operation']
        if operation not in ('launch', 'stop', 'status'):
            raise ValueError('unsupported broker operation')
        if (not isinstance(request['task_id'], str)
                or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', request['task_id'])
                or type(request['fence']) is not int or request['fence'] < 1
                or type(request['generation']) is not int or request['generation'] < 1
                or type(request['epoch']) is not int or request['epoch'] < 1
                or not isinstance(request['instance'], str)):
            raise ValueError('invalid broker task authority')
        role, artifact_sha = request['role'], request['artifact_sha']
        if (role == 'DEVELOPMENT' and artifact_sha is not None):
            raise ValueError('development broker request has an artifact')
        if (role == 'QA' and (not isinstance(artifact_sha, str)
                             or not re.fullmatch(r'[0-9a-f]{40}', artifact_sha))):
            raise ValueError('QA broker request lacks a frozen artifact')
        if role not in ('DEVELOPMENT', 'QA'):
            raise ValueError('invalid broker role')
        identity = tuple(request[key] for key in
                         ('task_id', 'fence', 'generation', 'epoch', 'instance',
                          'role', 'artifact_sha'))
        observed = self.ledger.observation(request['task_id'])
        if operation == 'launch':
            active = self.activation.read(require_active=True)
            if any(request[key] != active[key] for key in
                   ('generation', 'epoch', 'instance')):
                raise PermissionError('stale broker activation')
            if (observed['state'] != 'RUNNING' or observed['fence'] != request['fence']
                    or any(observed[key] != request[key] for key in
                           ('generation', 'epoch', 'instance'))):
                raise PermissionError('task is not registered under this fence')
            if role == 'QA' and (observed['checkpoint'].get('phase') != 'IN_FLIGHT_QA'
                                 or observed['checkpoint'].get('sha') != artifact_sha):
                raise PermissionError('QA artifact is not the frozen ledger checkpoint')
            if self._binary_digest() != self.binary_sha256:
                raise PermissionError('trusted broker binary digest changed')
        # Stop/status remain available after a broker restart and after the
        # ledger advances the task fence. They can address only a deterministic
        # unit for an existing task in this exact activation, never a free-form
        # unit name. A future/unseen fence is rejected.
        elif (request['fence'] > observed['fence']
              or any(observed[key] != request[key] for key in
                     ('generation', 'epoch', 'instance'))):
            raise PermissionError('broker task unit is not registered')
        task_key = hashlib.sha256(request['task_id'].encode('utf-8')).hexdigest()[:24]
        role_key = 'dev' if role == 'DEVELOPMENT' else 'qa-' + artifact_sha[:12]
        unit = 'xj-codex-e%d-f%d-%s-%s' % (
            request['epoch'], request['fence'], task_key, role_key)
        main_root = os.path.join(self.task_root, task_key)
        task_path = main_root if role == 'DEVELOPMENT' else main_root + '-qa-' + artifact_sha
        return {'operation': operation, 'unit': unit, 'uid': self.worker_user,
                'binary': self.codex_bin, 'task_root': task_path,
                'identity': identity}

    def completed(self, authorized, descendants_exited):
        """Forget a stopped unit only after the manager proves the cgroup empty."""
        if authorized['operation'] != 'stop' or descendants_exited is not True:
            raise RuntimeError('broker stop has not proved descendant exit')


class RootBrokerSocketServer(object):
    """Private one-request-per-connection JSON broker transport.

    ``handler`` is the reviewed root/systemd239 adapter. It receives only the
    derived authorization object above, never caller-controlled argv/paths.
    """
    def __init__(self, socket_path, policy, handler):
        self.socket_path = _canonical(socket_path, 'broker socket')
        self.policy, self.handler = policy, handler

    def serve_connection(self, connection):
        credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                             struct.calcsize('3i'))
        unused_pid, peer_uid, unused_gid = struct.unpack('3i', credentials)
        payload = bytearray()
        while b'\n' not in payload:
            chunk = connection.recv(8192 - len(payload))
            if not chunk:
                raise ValueError('truncated broker request')
            payload.extend(chunk)
            if len(payload) >= 8192:
                raise ValueError('oversized broker request')
        line, remainder = bytes(payload).split(b'\n', 1)
        if remainder:
            raise ValueError('multiple broker requests rejected')
        request = json.loads(line.decode('utf-8'))
        authorized = self.policy.authorize(peer_uid, request)
        result = self.handler(authorized)
        expected = ({'ok', 'status', 'descendants_exited'}
                    if authorized['operation'] in ('stop', 'status')
                    else {'ok', 'status'})
        if (not isinstance(result, dict) or set(result) != expected
                or result.get('ok') is not True
                or result.get('status') not in ('active', 'inactive', 'failed', 'stopping')):
            raise RuntimeError('invalid broker handler result')
        if authorized['operation'] == 'launch' and result['status'] != 'active':
            raise RuntimeError('broker launch not active')
        if authorized['operation'] == 'stop':
            if result['status'] != 'inactive' or result['descendants_exited'] is not True:
                raise RuntimeError('broker stop did not prove inactive empty cgroup')
            self.policy.completed(authorized, result.get('descendants_exited'))
        if (authorized['operation'] == 'status'
                and result['descendants_exited'] is not (result['status'] == 'inactive')):
            raise RuntimeError('broker status descendant proof mismatch')
        connection.sendall((json.dumps(result, sort_keys=True,
                                       separators=(',', ':')) + '\n').encode('utf-8'))


def build_loop(config):
    if config.get('config_version') != 2:
        raise ValueError('runtime requires broker-backed configuration version 2')
    activation = ActivationStore(config['activation_descriptor'],
                                 config['activation_epoch_journal'],
                                 config['activation_lock'])
    active = activation.read(require_active=True)
    binary_digest = hashlib.sha256()
    with open(config['codex_bin'], 'rb') as binary:
        for chunk in iter(lambda: binary.read(1024 * 1024), b''):
            binary_digest.update(chunk)
    expected = {'db_path': config['db_path'], 'ledger_socket': config['ledger_socket'],
                'release_sha256': config['release_sha256'],
                'config_sha256': config.get('_loaded_sha256'),
                'binary_sha256': binary_digest.hexdigest(),
                'ledger_uuid': config['ledger_uuid'], 'generation': config['generation'],
                'instance': config['instance']}
    if any(active[key] != value for key, value in expected.items()):
        raise ValueError('configuration does not match active descriptor')
    repo = config['control_repository']
    ledger = ExecutionLedger(config['db_path'], [repo], max_heavy=config['max_workers'],
                             approved_base_shas=[config['source_commit']],
                             activation_store=activation)
    backend = CliBackend(config['repositories'], config['workspace_root'],
                         config['service_home'], config['path'], config['required_checks'],
                         gh_bin=config['gh_bin'], use_gh_credentials=True,
                         github_lock_path=config['github_writer_lock'])
    def pipelines(claim):
        def workers(workdir, sandbox):
            return CodexAppServerWorker(
                config['codex_bin'], workdir, config['worker_home'], config['codex_home'],
                config['path'], sandbox=sandbox, model=config['model'],
                isolation_prefix=isolation_prefix(config, workdir, claim))
        return DevelopmentPipeline(ledger, backend, workers, [repo])
    return DevelopmentLoop(ledger, pipelines, 'uk-codex', max_workers=config['max_workers'])


def acquire_dispatcher_lock(path):
    parent=os.path.dirname(path)
    os.makedirs(parent, mode=0o700, exist_ok=True)
    pinfo=os.stat(parent,follow_symlinks=False)
    if not stat.S_ISDIR(pinfo.st_mode) or pinfo.st_uid!=os.geteuid() or pinfo.st_mode & 0o077:
        raise ValueError('unsafe lock directory')
    fd=os.open(path,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
    os.fchmod(fd,0o600)
    info=os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid():
        os.close(fd); raise ValueError('unsafe lock file')
    handle = os.fdopen(fd,'a+')
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise RuntimeError('another new dispatcher holds the exclusive lock')
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()) + '\n')
    handle.flush()
    return handle


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--check-config', action='store_true')
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.check_config:
        print('CONFIG_OK source_commit=' + config['source_commit'])
        return 0
    lock = acquire_dispatcher_lock(config['dispatcher_lock'])
    loop = build_loop(config)
    signal.signal(signal.SIGTERM, lambda *_: loop.stop())
    signal.signal(signal.SIGINT, lambda *_: loop.stop())
    try:
        loop.serve()
    finally:
        loop.close()
        lock.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
