"""Fixed-host adapter for a reviewed P2 legacy stop and direct unit restore.

No OAuth copying, package download, new activation or customer message. The
caller must finish review and prerequisite admission before invoking effects.
"""
import hashlib
import json
import os
import pwd
import socket
import stat
import subprocess
import tempfile

from legacy_quiescence import (ALLOWED_UNITS, inspect_unit, protected_hash,
                               measure_quiescence)
from ledger_cutover_transaction import _atomic_receipt
from ledger_backup import database_manifest

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
SOURCE = '/home/xuanjun_dev/uk-stage1-minimal/state.sqlite'


class LegacyHostAdapter(object):
    def __init__(self, transaction_directory, run=subprocess.run):
        if (not os.path.isabs(transaction_directory)
                or os.path.realpath(transaction_directory) != transaction_directory):
            raise ValueError('UNSAFE_HOST_TRANSACTION_PATH')
        self.directory, self.run = transaction_directory, run
        self.state_path = os.path.join(transaction_directory, 'legacy-units.json')

    def _authority(self):
        if os.geteuid() != 0 or socket.gethostname().split('.')[0] != HOST:
            raise ValueError('FIXED_UK_ROOT_ADAPTER_REQUIRED')
        info = os.lstat(self.directory)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError('PROTECTED_TRANSACTION_DIRECTORY_REQUIRED')

    def _command(self, *args):
        result = self.run(['/usr/bin/systemctl'] + list(args),
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          timeout=45, check=False)
        if result.returncode:
            raise RuntimeError('LEGACY_SYSTEMCTL_OPERATION_FAILED')

    def preflight(self, plan):
        self._authority()
        if plan['source'] != SOURCE or os.path.realpath(SOURCE) != SOURCE:
            raise ValueError('EXACT_CANONICAL_LEGACY_DATABASE_REQUIRED')
        info = os.lstat(SOURCE)
        if (not stat.S_ISREG(info.st_mode)
                or info.st_uid != pwd.getpwnam('xuanjun_dev').pw_uid):
            raise ValueError('LEGACY_DATABASE_IDENTITY_MISMATCH')
        for key in ('rollback_snapshot', 'staged_generation'):
            value = plan[key]
            if (not value.startswith('/var/lib/xuanjun-development/')
                    or os.path.realpath(value) != value
                    or os.path.lexists(value)):
                raise ValueError('UNSAFE_NEW_DATABASE_PATH')
        bindings = plan['legacy_bindings']
        if not isinstance(bindings, dict) or set(bindings) != ALLOWED_UNITS:
            raise ValueError('EXACT_LEGACY_UNIT_SET_REQUIRED')
        if os.path.lexists(self.state_path):
            raise ValueError('HOLD_EXISTING_LEGACY_UNIT_SNAPSHOT')
        for unit, binding in bindings.items():
            path = '/etc/systemd/system/' + unit
            if (set(binding) != {'fragment_path','sha256','cgroup'}
                    or binding['fragment_path'] != path
                    or binding['cgroup'] != '/system.slice/' + unit
                    or protected_hash(path) != binding['sha256']):
                raise ValueError('LEGACY_UNIT_IDENTITY_MISMATCH')
            value = inspect_unit(unit, self.run)
            if (value['LoadState'] != 'loaded' or value['FragmentPath'] != path
                    or value['UnitFileState'] not in ('enabled','disabled','static')
                    or value['ActiveState'] not in ('active','inactive')
                    or value['SubState'] not in ('running','dead')
                    or value['ControlGroup'] not in ('', binding['cgroup'])):
                raise ValueError('UNREVIEWED_LEGACY_SERVICE_STATE')
        return True

    def stop_and_inhibit(self, bindings):
        self._authority()
        if not isinstance(bindings, dict) or set(bindings) != ALLOWED_UNITS:
            raise ValueError('EXACT_LEGACY_UNIT_SET_REQUIRED')
        for unit, binding in bindings.items():
            if (not isinstance(binding, dict)
                    or set(binding) != {'fragment_path','sha256','cgroup'}
                    or binding['fragment_path'] != '/etc/systemd/system/' + unit
                    or binding['cgroup'] != '/system.slice/' + unit):
                raise ValueError('INVALID_EFFECT_UNIT_BINDING')
        units = {}
        # Preserve ALL direct unit bytes before the first service effect.
        for unit in sorted(ALLOWED_UNITS):
            path = bindings[unit]['fragment_path']
            if protected_hash(path) != bindings[unit]['sha256']:
                raise ValueError('LEGACY_UNIT_CHANGED_AFTER_PREFLIGHT')
            value = inspect_unit(unit, self.run)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                data = stream.read(262145)
            if hashlib.sha256(data).hexdigest() != bindings[unit]['sha256']:
                raise ValueError('LEGACY_BACKUP_IDENTITY_MISMATCH')
            backup = os.path.join(self.directory, unit + '.backup')
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as output:
                output.write(data); output.flush(); os.fsync(output.fileno())
            units[unit] = {'path':path, 'backup':backup,
                           'sha256':bindings[unit]['sha256'],
                           'mode':stat.S_IMODE(info.st_mode), 'uid':info.st_uid,
                           'gid':info.st_gid, 'was_active':value['ActiveState']=='active'}
        _atomic_receipt(self.state_path, {'schema':1, 'units':units,
                                         'source_before':database_manifest(SOURCE)})
        # Stop the parent first, preventing it from spawning another child.
        self._command('stop', 'xuanjun-uk-openclaw.service',
                      'xuanjun-uk-stage1-minimal.service')
        for unit in sorted(ALLOWED_UNITS):
            path = units[unit]['path']
            if protected_hash(path) != units[unit]['sha256']:
                raise ValueError('LEGACY_UNIT_CHANGED_DURING_STOP')
            temporary = path + '.p2-mask'
            # Never overwrite a previous transaction's unclassified artifact.
            os.symlink('/dev/null', temporary)
            try: os.replace(temporary, path)
            finally:
                if os.path.lexists(temporary): os.unlink(temporary)
            directory = os.open(os.path.dirname(path), os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(directory)
            finally: os.close(directory)
        self._command('daemon-reload')

    def _state(self):
        self._authority()
        fd = os.open(self.state_path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if (info.st_uid != 0 or not stat.S_ISREG(info.st_mode)
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 65536):
                raise ValueError('UNSAFE_LEGACY_RESTORE_STATE')
            state = json.load(stream)
        if (set(state) != {'schema','units','source_before'} or state['schema'] != 1
                or set(state['units']) != ALLOWED_UNITS):
            raise ValueError('INVALID_LEGACY_RESTORE_STATE')
        return state

    def measure_quiescence(self, bindings):
        state = self._state()
        paths = {v['path']:v['backup'] for v in state['units'].values()}
        return measure_quiescence(bindings, '/sys/fs/cgroup/systemd', self.run,
                                  hash_file=lambda path: protected_hash(paths[path]))

    def restore_legacy_files(self):
        state = self._state()
        payloads = {}
        # Validate every backup before restoring even the first unit.
        for unit, value in state['units'].items():
            if (set(value) != {'path','backup','sha256','mode','uid','gid','was_active'}
                    or value['path'] != '/etc/systemd/system/' + unit
                    or value['backup'] != os.path.join(self.directory, unit+'.backup')
                    or value['uid'] != 0 or value['mode'] & 0o022
                    or protected_hash(value['backup']) != value['sha256']):
                raise ValueError('INVALID_DIRECT_UNIT_RESTORE_BINDING')
            fd = os.open(value['backup'], os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as stream: data = stream.read(262145)
            if hashlib.sha256(data).hexdigest() != value['sha256']:
                raise ValueError('RESTORE_BACKUP_CHANGED')
            payloads[unit] = data
        for unit, data in payloads.items():
            value = state['units'][unit]
            path = value['path']
            if (not os.path.islink(path) or os.readlink(path) != '/dev/null'):
                if protected_hash(path) != value['sha256']:
                    raise ValueError('RESTORE_TARGET_UNEXPECTEDLY_CHANGED')
        for unit, data in payloads.items():
            value = state['units'][unit]
            path = value['path']
            if (not os.path.islink(path) or os.readlink(path) != '/dev/null'):
                # Allow an interrupted restore only when exact original bytes
                # and metadata are already back in place.
                if protected_hash(path) != value['sha256']:
                    raise ValueError('RESTORE_TARGET_UNEXPECTEDLY_CHANGED')
                continue
            fd, temporary = tempfile.mkstemp(prefix='.p2-restore-', dir=os.path.dirname(path))
            try:
                os.fchmod(fd, value['mode']); os.fchown(fd, value['uid'], value['gid'])
                with os.fdopen(fd,'wb') as stream:
                    stream.write(data); stream.flush(); os.fsync(stream.fileno())
                os.replace(temporary,path)
                directory = os.open(os.path.dirname(path),os.O_RDONLY|os.O_DIRECTORY)
                try: os.fsync(directory)
                finally: os.close(directory)
            finally:
                if os.path.exists(temporary): os.unlink(temporary)
        self._command('daemon-reload')
        # Restoring files is not permission to restart old/new writers. Caller
        # must reconcile leases, activation and DB state before any restart.
        return {'unit_files_restored':True, 'services_restarted':False}
