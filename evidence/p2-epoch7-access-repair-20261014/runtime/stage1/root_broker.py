#!/usr/bin/env python3
"""Root-only socket broker and systemd-239 adapter for fenced Codex workers.

The caller supplies only a task identity and operation.  The policy in
``development_service`` derives the unit, uid, binary and work directory; this
adapter never accepts an arbitrary command, uid, unit or path from the socket.
"""
import argparse
import hashlib
import json
import os
import pwd
import re
import signal
import socket
import stat
import subprocess
import sys
import threading

from activation_control import ActivationStore
from development_service import RootBrokerPolicy, RootBrokerSocketServer
from ledger_read_client import BrokerObservationClient
from ledger_server_identity import load_server_verifier
from ledger_read_transport import AuthenticatedLedgerReadTransport


def _read_config(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
            or info.st_mode & 0o022 or info.st_size > 65536):
        os.close(fd)
        raise ValueError('unsafe broker configuration')
    with os.fdopen(fd, 'rb') as stream:
        value = json.loads(stream.read().decode('utf-8'))
    required = {'schema', 'dispatcher_user', 'worker_user', 'codex_bin',
                'codex_sha256', 'task_root', 'worker_home', 'codex_home',
                'activation_descriptor', 'activation_epoch_journal',
                'activation_lock', 'broker_socket', 'repositories'}
    if not isinstance(value, dict) or set(value) != required or value['schema'] != 1:
        raise ValueError('broker configuration keys mismatch')
    for key in ('codex_bin', 'task_root', 'worker_home', 'codex_home',
                'activation_descriptor', 'activation_epoch_journal',
                'activation_lock', 'broker_socket'):
        if (not isinstance(value[key], str) or not os.path.isabs(value[key])
                or os.path.realpath(value[key]) != value[key]):
            raise ValueError('non-canonical broker path: ' + key)
    if not re.fullmatch(r'[0-9a-f]{64}', value['codex_sha256']):
        raise ValueError('invalid Codex digest')
    if (not isinstance(value['repositories'], list) or not value['repositories']
            or any(not isinstance(item, str) or '/' not in item
                   for item in value['repositories'])):
        raise ValueError('invalid repository allowlist')
    return value


class Systemd239Handler(object):
    """Fixed argv adapter with whole-cgroup stop/status evidence."""
    def __init__(self, worker_home, codex_home, run=None, cgroup_root='/sys/fs/cgroup/systemd'):
        self.worker_home = worker_home
        self.codex_home = codex_home
        self.run = run or subprocess.run
        self.cgroup_root = cgroup_root

    @staticmethod
    def _state(output):
        values = {}
        for raw in output.decode('utf-8', 'replace').splitlines():
            if '=' in raw:
                key, value = raw.split('=', 1)
                values[key] = value
        active = values.get('ActiveState', 'failed')
        status = active if active in ('active', 'inactive', 'failed') else 'stopping'
        return status, values.get('ControlGroup', '')

    def _show(self, unit):
        result = self.run(['/usr/bin/systemctl', 'show', unit,
                           '--property=ActiveState', '--property=ControlGroup'],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          timeout=10, check=False)
        if result.returncode not in (0, 3, 4):
            raise RuntimeError('systemd status failed')
        status, control_group = self._state(result.stdout)
        descendants_exited = status == 'inactive' and self._empty(control_group)
        return status, descendants_exited

    def _empty(self, control_group):
        if not control_group or '..' in control_group.split('/'):
            return False
        path = os.path.join(self.cgroup_root, control_group.lstrip('/'), 'cgroup.procs')
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        except FileNotFoundError:
            return True
        with os.fdopen(fd, 'rb') as stream:
            return not stream.read(2).strip()

    def __call__(self, authorized):
        operation, unit = authorized['operation'], authorized['unit']
        if operation == 'launch':
            raise RuntimeError('delegated model dispatch prohibited by owner policy')
        if operation == 'launch':
            argv = ['/usr/bin/systemd-run', '--quiet', '--collect', '--unit=' + unit,
                    '--uid=' + authorized['uid'],
                    '--property=WorkingDirectory=' + authorized['task_root'],
                    '--setenv=HOME=' + self.worker_home,
                    '--setenv=CODEX_HOME=' + self.codex_home,
                    '--property=NoNewPrivileges=yes', '--property=PrivateTmp=yes',
                    '--property=PrivateDevices=yes', '--property=ProtectSystem=strict',
                    '--property=ProtectHome=yes', '--property=RestrictSUIDSGID=yes',
                    '--property=CPUQuota=100%', '--property=MemoryMax=2G',
                    '--property=TasksMax=256',
                    '--property=InaccessiblePaths=/root /etc/xuanjun-owner-callback /var/lib/xuanjun-development/ledger',
                    '--property=ReadWritePaths=' + authorized['task_root'] + ' ' + self.worker_home + ' ' + self.codex_home,
                    '--', authorized['binary'], '-c', 'model_provider="openai"',
                    '-c', 'approval_policy="never"', '-c', 'features.multi_agent=false',
                    'app-server', '--listen', 'stdio://']
            result = self.run(argv, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=15, check=False)
            if result.returncode:
                raise RuntimeError('systemd launch failed')
        elif operation == 'stop':
            result = self.run(['/usr/bin/systemctl', 'stop', unit],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=30, check=False)
            if result.returncode not in (0, 3, 4):
                raise RuntimeError('systemd stop failed')
        status, descendants_exited = self._show(unit)
        answer = {'ok': True, 'status': status}
        if operation in ('stop', 'status'):
            answer['descendants_exited'] = descendants_exited
        return answer

    def _launch_argv(self, authorized):
        return ['/usr/bin/systemd-run', '--quiet', '--wait', '--collect', '--pipe',
                '--unit=' + authorized['unit'], '--uid=' + authorized['uid'],
                '--property=WorkingDirectory=' + authorized['task_root'],
                '--setenv=HOME=' + self.worker_home,
                '--setenv=CODEX_HOME=' + self.codex_home,
                '--property=NoNewPrivileges=yes', '--property=PrivateTmp=yes',
                '--property=PrivateDevices=yes', '--property=ProtectSystem=strict',
                '--property=ProtectHome=yes', '--property=RestrictSUIDSGID=yes',
                '--property=CPUQuota=100%', '--property=MemoryMax=2G',
                '--property=TasksMax=256',
                '--property=InaccessiblePaths=/root /etc/xuanjun-owner-callback /var/lib/xuanjun-development/ledger',
                '--property=ReadWritePaths=' + authorized['task_root'] + ' ' + self.worker_home + ' ' + self.codex_home,
                '--', authorized['binary'], '-c', 'model_provider="openai"',
                '-c', 'approval_policy="never"', '-c', 'features.multi_agent=false',
                'app-server', '--listen', 'stdio://']

    def serve_launch(self, authorized, connection):
        """Relay one fixed transient app-server without granting manager APIs."""
        raise RuntimeError('delegated model dispatch prohibited by owner policy')
        process = subprocess.Popen(self._launch_argv(authorized), stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   bufsize=0)
        try:
            connection.sendall(b'{"ok":true,"status":"active"}\n')

            def socket_to_child():
                try:
                    while True:
                        data = connection.recv(65536)
                        if not data:
                            break
                        process.stdin.write(data)
                        process.stdin.flush()
                finally:
                    try:
                        process.stdin.close()
                    except OSError:
                        pass

            input_thread = threading.Thread(target=socket_to_child)
            input_thread.daemon = True
            input_thread.start()
            while True:
                data = process.stdout.read(65536)
                if not data:
                    break
                connection.sendall(data)
            process.wait()
            input_thread.join(2)
            if process.returncode:
                raise RuntimeError('transient Codex app-server failed')
        finally:
            if process.poll() is None:
                self.run(['/usr/bin/systemctl', 'stop', authorized['unit']],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         timeout=30, check=False)
                process.wait()
            status, descendants_exited = self._show(authorized['unit'])
            if status != 'inactive' or not descendants_exited:
                raise RuntimeError('broker launch cleanup did not empty cgroup')


def _socket(path):
    inherited = int(os.environ.get('LISTEN_FDS', '0') or '0')
    if inherited == 1 and int(os.environ.get('LISTEN_PID', '0') or '0') == os.getpid():
        return socket.socket(fileno=3)
    parent = os.path.dirname(path)
    info = os.stat(parent, follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError('unsafe broker socket directory')
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    os.chmod(path, 0o660)
    server.listen(32)
    return server


def build(config, server_verifier=None):
    # Missing or unmeasured protected policy fails before any service effects.
    if server_verifier is None:
        server_verifier = load_server_verifier()
    transport = AuthenticatedLedgerReadTransport(server_verifier)
    dispatcher = pwd.getpwnam(config['dispatcher_user'])
    if dispatcher.pw_uid == 0:
        raise ValueError('root dispatcher rejected')
    worker = pwd.getpwnam(config['worker_user'])
    if (worker.pw_uid == 0 or worker.pw_uid == dispatcher.pw_uid
            or config['worker_user'] in ('root', 'toor')
            or not config['worker_user'].startswith('xj_')):
        raise ValueError('dedicated non-root worker required')
    activation = ActivationStore(config['activation_descriptor'],
                                 config['activation_epoch_journal'],
                                 config['activation_lock'])
    activation.read(require_active=True)
    ledger = BrokerObservationClient(activation, transport)
    policy = RootBrokerPolicy(activation, ledger, dispatcher.pw_uid,
                              config['worker_user'], config['codex_bin'],
                              config['codex_sha256'], config['task_root'])
    handler = Systemd239Handler(config['worker_home'], config['codex_home'])
    return RootBrokerSocketServer(config['broker_socket'], policy, handler)


def _serve_client(broker, connection):
    """Own one accepted socket so a long stdio launch cannot block controls."""
    with connection:
        try:
            broker.serve_connection(connection)
        except Exception:
            try:
                connection.sendall(b'{"ok":false,"status":"failed"}\n')
            except OSError:
                pass


def main(argv=None, server_verifier=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        raise SystemExit('ROOT_BROKER_REQUIRED')
    config = _read_config(args.config)
    broker = build(config, server_verifier=server_verifier)
    listener = _socket(config['broker_socket'])
    stopping = [False]
    signal.signal(signal.SIGTERM, lambda *_: stopping.__setitem__(0, True))
    signal.signal(signal.SIGINT, lambda *_: stopping.__setitem__(0, True))
    listener.settimeout(1)
    while not stopping[0]:
        try:
            connection, _ = listener.accept()
        except socket.timeout:
            continue
        worker = threading.Thread(target=_serve_client,
                                  args=(broker, connection))
        worker.daemon = True
        worker.start()
    listener.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
