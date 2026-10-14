"""Bounded failure containment for the exact admitted epoch3 transaction.

Must be called after attempt admission. No start/restart, package removal, masks
changes or credential operations. All stop requests are attempted even if one
fails. A successful stop exit alone never proves containment.
"""
import os
import socket
import stat
import subprocess
from p2_fixed_host_runtime import HOST, STOP_SERVICES, GATEWAY_SERVICE
from p2_tls_lifecycle import TIMER, SERVICE

UNITS = tuple(dict.fromkeys((TIMER, SERVICE) + STOP_SERVICES +
                           ('nginx.service', GATEWAY_SERVICE)))


def require(value, label):
    if not value:
        raise ValueError(label)


class ServiceContainment:
    def __init__(self, reviewed_scanner, run=subprocess.run):
        self.scanner = reviewed_scanner
        self.run = run

    def authority(self):
        require(os.geteuid() == 0 and socket.gethostname().split('.')[0] == HOST,
                'CONTAINMENT_EXACT_HOST_ROOT')

    def stop_all(self):
        self.authority()
        results = []
        for unit in UNITS:
            row = {'unit': unit, 'stop_requested': True}
            try:
                value = self.run(['/usr/bin/systemctl', 'stop', unit],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 timeout=45, check=False)
                row['returncode'] = value.returncode
            except Exception as error:
                row['error_type'] = type(error).__name__
            results.append(row)
        # Keep every result, including failure, for the outer durable receipt.
        return {'stop_results': results, 'verified_stopped': False,
                'requires_separate_observation': True}

    def observe_one(self, unit):
        require(unit in UNITS, 'CONTAINMENT_UNIT_SCOPE')
        def state():
            result = self.run(['/usr/bin/systemctl', 'show', unit,
                               '--property=LoadState,ActiveState,SubState,MainPID,ControlPID,ControlGroup'],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=15, check=False)
            rows = result.stdout.decode('utf-8', 'strict').splitlines()
            require(all('=' in r for r in rows), 'CONTAINMENT_QUERY_FORMAT')
            pairs = [r.split('=', 1) for r in rows]
            require(len({r[0] for r in pairs}) == len(pairs), 'CONTAINMENT_DUPLICATE_STATE')
            values = dict(pairs)
            absent = (values.get('LoadState') == 'not-found' and
                      values.get('ActiveState') == 'inactive' and
                      values.get('SubState') == 'dead' and values.get('ControlGroup', '') == '')
            require(result.returncode == 0 or (result.returncode == 1 and absent),
                    'CONTAINMENT_QUERY_FAILED')
            pid_default = '0' if absent or unit.endswith(('.timer', '.socket')) else None
            require(values.get('ActiveState') in ('inactive', 'failed') and
                    values.get('MainPID', pid_default) == '0' and
                    values.get('ControlPID', pid_default) == '0',
                    'CONTAINMENT_PROCESS_STILL_PRESENT')
            require(values.get('ControlGroup', '') in ('', '/system.slice/' + unit),
                    'CONTAINMENT_UNEXPECTED_CGROUP')
            return values
        self.scanner.verify_systemd_controller_mount()
        controller = '/sys/fs/cgroup/systemd/system.slice'
        require(os.path.realpath(controller) == controller, 'CONTAINMENT_CONTROLLER_ALIAS')
        fd = os.open(controller, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0,
                    'CONTAINMENT_CONTROLLER_AUTHORITY')
            os.listdir(fd)
            before = state()
            observed = self.scanner.bounded_file_inventory(
                controller + '/' + unit, optional=True, cgroup=True)
            after = state()
            require(before == after, 'CONTAINMENT_STATE_RACE')
            current = os.stat(controller, follow_symlinks=False)
            require((info.st_dev, info.st_ino, info.st_mode) ==
                    (current.st_dev, current.st_ino, current.st_mode),
                    'CONTAINMENT_CONTROLLER_CHANGED')
        finally:
            os.close(fd)
        self.scanner.verify_systemd_controller_mount()
        return {'unit': unit, 'state': after, 'cgroup': observed}

    def verify_all(self):
        self.authority()
        rows = []
        errors = []
        for unit in UNITS:
            try:
                rows.append(self.observe_one(unit))
            except Exception as error:
                errors.append({'unit': unit, 'error_type': type(error).__name__})
        if errors:
            # Caller records UNKNOWN, never infers success from a stopped subset.
            raise ValueError('CONTAINMENT_UNVERIFIED_UNITS:' + ','.join(r['unit'] for r in errors))
        return {'verified_stopped': True, 'units': rows}
