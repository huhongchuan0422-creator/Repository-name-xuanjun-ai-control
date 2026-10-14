"""Measure legacy exclusion before ledger migration; never stop units here.

Caller supplies reviewed unit-file identities and the previously observed
cgroups. Missing evidence fails closed; booleans cannot be supplied as proof.
"""
import hashlib
import os
import re
import stat
import subprocess

ALLOWED_UNITS = frozenset(('xuanjun-uk-stage1-minimal.service',
                          'xuanjun-uk-openclaw.service'))
PROPERTIES = ('Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID',
              'ControlGroup', 'UnitFileState', 'FragmentPath')


def inspect_unit(unit, run=subprocess.run):
    if unit not in ALLOWED_UNITS:
        raise ValueError('UNREVIEWED_LEGACY_UNIT')
    result = run(['/usr/bin/systemctl', 'show', unit,
                  '--property=' + ','.join(PROPERTIES)], stdout=subprocess.PIPE,
                 stderr=subprocess.DEVNULL, timeout=10, check=False)
    if result.returncode:
        raise ValueError('LEGACY_UNIT_INSPECTION_FAILED')
    rows = result.stdout.decode('utf-8', 'strict').splitlines()
    values = {}
    for row in rows:
        key, separator, value = row.partition('=')
        if not separator or key not in PROPERTIES or key in values:
            raise ValueError('INVALID_LEGACY_UNIT_EVIDENCE')
        values[key] = value
    if set(values) != set(PROPERTIES) or values['Id'] != unit:
        raise ValueError('INCOMPLETE_LEGACY_UNIT_EVIDENCE')
    return values


def protected_hash(path, owner_uid=0):
    if not os.path.isabs(path) or os.path.realpath(path) != path:
        raise ValueError('UNSAFE_LEGACY_UNIT_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner_uid
                or info.st_mode & 0o022 or info.st_size > 262144):
            raise ValueError('UNTRUSTED_LEGACY_UNIT_FILE')
        data = os.read(fd, 262145)
        return hashlib.sha256(data).hexdigest()
    finally:
        os.close(fd)


def cgroup_empty(root, group):
    if not os.path.isdir(root) or os.path.realpath(root) != root:
        raise ValueError('CGROUP_ROOT_UNAVAILABLE')
    if (not isinstance(group, str) or not group.startswith('/system.slice/')
            or '..' in group.split('/') or os.path.normpath(group) != group):
        raise ValueError('UNSAFE_LEGACY_CGROUP')
    path = root + group
    # A fully removed cgroup is empty. Existing ancestors must not be symlinks.
    current = root
    for component in group.strip('/').split('/'):
        current = os.path.join(current, component)
        if os.path.islink(current):
            raise ValueError('SYMLINKED_LEGACY_CGROUP')
    if not os.path.exists(path):
        return True
    if not os.path.isdir(path):
        raise ValueError('INVALID_CGROUP_DIRECTORY')
    for directory, children, unused in os.walk(path, followlinks=False):
        if any(os.path.islink(os.path.join(directory, child)) for child in children):
            raise ValueError('SYMLINKED_LEGACY_CGROUP')
        # v1 and v2 use cgroup.procs; tasks additionally catches all v1 threads.
        observed = False
        for name in ('cgroup.procs', 'tasks'):
            target = os.path.join(directory, name)
            if os.path.exists(target):
                observed = True
                fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd) as stream:
                    if stream.read(1048577).strip():
                        return False
        if not observed:
            raise ValueError('CGROUP_MEMBERSHIP_UNAVAILABLE')
    return True


def measure_quiescence(bindings, cgroup_root, run=subprocess.run,
                       hash_file=protected_hash, measure_empty=cgroup_empty):
    if not isinstance(bindings, dict) or set(bindings) != ALLOWED_UNITS:
        raise ValueError('EXACT_LEGACY_UNIT_SET_REQUIRED')
    if cgroup_root not in ('/sys/fs/cgroup', '/sys/fs/cgroup/systemd'):
        raise ValueError('UNREVIEWED_CGROUP_ROOT')
    observed = {}
    for unit in sorted(bindings):
        binding = bindings[unit]
        if (not isinstance(binding, dict)
                or set(binding) != {'fragment_path', 'sha256', 'cgroup'}
                or not re.fullmatch(r'[0-9a-f]{64}', binding.get('sha256', ''))
                or binding.get('fragment_path') != '/etc/systemd/system/' + unit
                or binding.get('cgroup') != '/system.slice/' + unit):
            raise ValueError('INVALID_LEGACY_UNIT_BINDING')
        value = inspect_unit(unit, run)
        if (value['LoadState'] not in ('loaded', 'masked')
                or hash_file(binding['fragment_path']) != binding['sha256']):
            raise ValueError('LEGACY_UNIT_IDENTITY_MISMATCH')
        if value['FragmentPath'] not in (binding['fragment_path'], '/dev/null'):
            raise ValueError('LEGACY_FRAGMENT_CHANGED')
        if (value['ActiveState'] != 'inactive' or value['SubState'] != 'dead'
                or value['MainPID'] != '0'):
            raise ValueError('HOLD_LEGACY_UNIT_STILL_RUNNING')
        if value['UnitFileState'] not in ('masked', 'masked-runtime'):
            raise ValueError('HOLD_LEGACY_RESTART_NOT_INHIBITED')
        if value['ControlGroup'] not in ('', binding['cgroup']):
            raise ValueError('LEGACY_CGROUP_CHANGED')
        if measure_empty(cgroup_root, binding['cgroup']) is not True:
            raise ValueError('HOLD_LEGACY_CGROUP_NOT_EMPTY')
        observed[unit] = value
    proof = {'identity_verified': True, 'coordinator_inactive': True,
             'parent_unit_inactive': True, 'cgroups_empty': True,
             'restart_inhibited': True}
    return {'proof': proof, 'units': observed, 'scope': 'MEASURE_ONLY_NO_STOP'}
