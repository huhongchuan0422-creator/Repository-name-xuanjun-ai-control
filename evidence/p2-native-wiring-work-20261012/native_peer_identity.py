"""Narrow native-ledger peer authentication for the Gateway bridge.

Python 3.6 compatible. A shared Unix UID is never sufficient: the bridge must
be the exact pinned Python/script/config child of the exact pinned Gateway
process and cgroup described by the root-owned plugin binding.
"""
from __future__ import print_function

import hashlib
import json
import os
import pwd
import re
import stat

SHA256 = re.compile(r'^[0-9a-f]{64}$')
BINDING_FILE = '/etc/xuanjun-development/p2-native-binding.json'


def _protected_bytes(path, maximum=262144):
    if (not isinstance(path, str) or not os.path.isabs(path)
            or os.path.realpath(path) != path):
        raise ValueError('canonical protected path required')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o022 or info.st_size > maximum):
            raise ValueError('protected root-owned file required')
        raw = b''
        while len(raw) <= maximum:
            part = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not part:
                break
            raw += part
        if len(raw) > maximum:
            raise ValueError('protected file size limit')
        return raw
    finally:
        os.close(fd)


def _protected_sha256(path):
    return hashlib.sha256(_protected_bytes(path, maximum=64 * 1024 * 1024)).hexdigest()


def load_native_peer_identity(binding_path=BINDING_FILE):
    raw = _protected_bytes(binding_path, maximum=65536)
    value = json.loads(raw.decode('utf-8'))
    if not isinstance(value, dict):
        raise ValueError('native binding object required')
    ledger = value.get('ledger')
    gateway = value.get('gatewayIdentity')
    if (not isinstance(ledger, dict) or not isinstance(gateway, dict)
            or set(gateway) != {'user', 'exe', 'sha256', 'cgroup'}):
        raise ValueError('native gateway identity configuration required')
    required_ledger = {'python', 'pythonSha256', 'bridge', 'config', 'files'}
    if not required_ledger.issubset(set(ledger)):
        raise ValueError('native ledger binding incomplete')
    user = gateway['user']
    if not isinstance(user, str) or not user or user in ('root', 'toor'):
        raise ValueError('unprivileged Gateway user required')
    uid = pwd.getpwnam(user).pw_uid
    if uid < 1:
        raise ValueError('unprivileged Gateway UID required')
    fields = {
        'uid': uid,
        'gateway_exe': gateway['exe'],
        'gateway_exe_sha256': gateway['sha256'],
        'gateway_cgroup': gateway['cgroup'],
        'bridge_python': ledger['python'],
        'bridge_python_sha256': ledger['pythonSha256'],
        'bridge_path': ledger['bridge'],
        'bridge_config': ledger['config'],
        'bridge_sha256': (ledger.get('files') or {}).get(ledger['bridge']),
        'bridge_config_sha256': (ledger.get('files') or {}).get(ledger['config']),
    }
    for key in ('gateway_exe_sha256', 'bridge_python_sha256',
                'bridge_sha256', 'bridge_config_sha256'):
        if not isinstance(fields[key], str) or not SHA256.fullmatch(fields[key]):
            raise ValueError('native identity digest invalid: ' + key)
    for key in ('gateway_exe', 'bridge_python', 'bridge_path', 'bridge_config'):
        if (not isinstance(fields[key], str) or not os.path.isabs(fields[key])
                or os.path.realpath(fields[key]) != fields[key]):
            raise ValueError('native identity path invalid: ' + key)
    cgroup = fields['gateway_cgroup']
    if (not isinstance(cgroup, str) or not cgroup.startswith('/')
            or '..' in cgroup.split('/') or len(cgroup) > 4096):
        raise ValueError('native Gateway cgroup invalid')
    for path, digest in (
            (fields['gateway_exe'], fields['gateway_exe_sha256']),
            (fields['bridge_python'], fields['bridge_python_sha256']),
            (fields['bridge_path'], fields['bridge_sha256']),
            (fields['bridge_config'], fields['bridge_config_sha256'])):
        if _protected_sha256(path) != digest:
            raise ValueError('native identity protected bytes changed')
    return fields


def _proc_bytes(proc_root, pid, name, maximum=65536):
    path = os.path.join(proc_root, str(pid), name)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        raw = os.read(fd, maximum + 1)
        if len(raw) > maximum:
            raise ValueError('proc identity field too large')
        return raw
    finally:
        os.close(fd)


def _status(raw):
    result = {}
    for line in raw.decode('ascii', 'strict').splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            result[key] = value.strip()
    return result


def verify_native_gateway_peer(peer_pid, peer_uid, identity, proc_root='/proc'):
    if (type(peer_pid) is not int or peer_pid < 1 or type(peer_uid) is not int
            or not isinstance(identity, dict) or peer_uid != identity.get('uid')):
        return False
    try:
        peer_status = _status(_proc_bytes(proc_root, peer_pid, 'status'))
        peer_uids = peer_status.get('Uid', '').split()
        parent_pid = int(peer_status.get('PPid', '0'))
        if (len(peer_uids) != 4 or any(int(v) != peer_uid for v in peer_uids)
                or parent_pid < 1):
            return False

        peer_exe = os.path.realpath(os.path.join(proc_root, str(peer_pid), 'exe'))
        if peer_exe != identity['bridge_python']:
            return False
        if _protected_sha256(peer_exe) != identity['bridge_python_sha256']:
            return False

        cmdline = _proc_bytes(proc_root, peer_pid, 'cmdline').rstrip(b'\0').split(b'\0')
        expected = [identity['bridge_python'].encode('utf-8'), b'-B',
                    identity['bridge_path'].encode('utf-8'), b'--config',
                    identity['bridge_config'].encode('utf-8')]
        if cmdline != expected:
            return False
        if (_protected_sha256(identity['bridge_path']) != identity['bridge_sha256']
                or _protected_sha256(identity['bridge_config']) != identity['bridge_config_sha256']):
            return False

        parent_status = _status(_proc_bytes(proc_root, parent_pid, 'status'))
        parent_uids = parent_status.get('Uid', '').split()
        if len(parent_uids) != 4 or any(int(v) != peer_uid for v in parent_uids):
            return False
        parent_exe = os.path.realpath(os.path.join(proc_root, str(parent_pid), 'exe'))
        if parent_exe != identity['gateway_exe']:
            return False
        if _protected_sha256(parent_exe) != identity['gateway_exe_sha256']:
            return False
        cgroups = _proc_bytes(proc_root, parent_pid, 'cgroup', maximum=131072).decode(
            'utf-8', 'strict').splitlines()
        if not any(line.split(':', 2)[-1] == identity['gateway_cgroup']
                   for line in cgroups if line.count(':') >= 2):
            return False
        return True
    except (IOError, OSError, ValueError, KeyError, UnicodeError):
        return False
