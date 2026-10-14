#!/usr/bin/env python3
"""Versioned passive UK metadata collector. Python 3.6. No ledger connections.

Only fixed-target systemctl show, metadata/ACL and selected proc reads. No
service actions, database access, secret bytes, permission changes or writes.
This program is NOT an admission check or a socket-identity attestation.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import errno
import hashlib
import json
import os
import re
import selectors
import stat
import struct
import subprocess
import time

VERSION = 'p2-passive-topology-v1'
TOTAL_SECONDS = 30.0
MAX_OUTPUT = 131072
UNITS = (
    'xuanjun-ledger.socket', 'xuanjun-ledger.service',
    'xj-root-broker.socket', 'xj-root-broker.service',
    'xuanjun-uk-owner-dashboard.service', 'xuanjun-uk-owner-callback.service',
    'xuanjun-development-dispatcher.service', 'xuanjun-github-intake.service',
    'xuanjun-p2-gateway-relay.socket', 'xuanjun-p2-gateway-relay.service')
PROPERTIES = ('Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID', 'User', 'Group',
    'SupplementaryGroups', 'ControlGroup', 'CapabilityBoundingSet', 'AmbientCapabilities',
    'NoNewPrivileges', 'ProtectHome', 'ProtectSystem', 'PrivateTmp', 'PrivateDevices',
    'RestrictAddressFamilies', 'ReadOnlyPaths', 'ReadWritePaths', 'InaccessiblePaths',
    'FragmentPath', 'DropInPaths', 'NeedDaemonReload', 'InvocationID',
    'ExecMainStartTimestampMonotonic', 'Listen', 'Accept', 'Service', 'SocketUser',
    'SocketGroup', 'SocketMode', 'DirectoryMode', 'RemoveOnStop')
SOCKETS = ('/run/xuanjun-development/ledger.sock', '/run/xuanjun-development/broker.sock',
           '/run/xuanjun-development/p2-gateway.sock')
ACTIVATION = '/var/lib/xuanjun-development/activation/active.json'
SECRET_NAMES = ('owner-callback-auth', 'owner-callback-hmac', 'owner-user-id',
                'owner-chat-id', 'owner-dashboard-token')
FIXED_PATHS = ('/', '/run', '/run/xuanjun-development',
    '/opt/xuanjun-control-releases', '/etc/xuanjun-development',
    '/etc/xuanjun-development/p2-native-ledger-client.json',
    '/etc/xuanjun-development/dispatcher.json',
    '/var/lib/xuanjun-development/generations',
    '/var/lib/xuanjun-development/generations/1',
    '/var/lib/xuanjun-development/generations/1/state.sqlite',
    '/var/lib/xuanjun-development/activation', ACTIVATION,
    '/var/lib/xuanjun-development/activation/epochs.jsonl',
    '/var/lib/xuanjun-development/activation/activation.lock',
    '/etc/xuanjun-owner-callback') + SOCKETS + tuple(
        '/etc/xuanjun-owner-callback/' + name for name in SECRET_NAMES)
UNIT_ROOTS = ('/etc/systemd/system/', '/run/systemd/system/',
              '/usr/lib/systemd/system/', '/lib/systemd/system/')
STATUS_FIELDS = {'Uid', 'Gid', 'Groups', 'CapEff', 'CapBnd', 'NoNewPrivs', 'Seccomp'}


class ProbeLimit(Exception):
    pass


def failure(code, number=None):
    value = {'status': 'NOT_VERIFIED', 'reason': code}
    if type(number) is int: value['errno'] = number
    return value


def _error(error):
    if isinstance(error, ProbeLimit): return failure('DEADLINE_OR_SIZE_BOUND')
    if isinstance(error, OSError): return failure('READ_UNAVAILABLE', error.errno)
    return failure('INVALID_OR_UNSUPPORTED_EVIDENCE')


def valid_unit_file(path, unit):
    if not isinstance(path, str) or '\x00' in path or '..' in path.split('/'):
        return False
    for root in UNIT_ROOTS:
        if path == root + unit: return True
        prefix = root + unit + '.d/'
        if path.startswith(prefix) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}\.conf', path[len(prefix):]):
            return True
    return False


class Backend(object):
    """OS implementation. Tests inject a fixture backend instead."""
    def __init__(self, clock=None):
        self.clock = clock or time.monotonic
        self.end = self.clock() + TOTAL_SECONDS
    def check(self):
        if self.clock() >= self.end: raise ProbeLimit()
    def metadata(self, path):
        self.check(); info = os.lstat(path)
        result = {'status': 'PASS_OBSERVED', 'kind': 'socket' if stat.S_ISSOCK(info.st_mode)
            else 'directory' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode)
            else 'symlink' if stat.S_ISLNK(info.st_mode) else 'other',
            'uid': info.st_uid, 'gid': info.st_gid, 'mode': stat.S_IMODE(info.st_mode),
            'dev': info.st_dev, 'inode': info.st_ino, 'nlink': info.st_nlink,
            'size': info.st_size, 'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}
        try:
            raw = os.getxattr(path, 'system.posix_acl_access', follow_symlinks=False)
            if (len(raw) > 1028 or len(raw) < 4 or (len(raw)-4) % 8
                    or struct.unpack('<I', raw[:4])[0] != 2): raise ProbeLimit()
            result['acl'] = {'status': 'PASS_OBSERVED', 'entries': [
                list(struct.unpack('<HHI', raw[i:i+8])) for i in range(4, len(raw), 8)]}
        except OSError as error:
            result['acl'] = ({'status': 'ABSENT'} if error.errno in (errno.ENODATA,
                getattr(errno, 'ENOATTR', errno.ENODATA)) else _error(error))
        self.check(); return result
    def read(self, path, maximum):
        self.check()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode): raise ValueError('regular file required')
            raw = bytearray()
            while len(raw) <= maximum:
                self.check()
                chunk = os.read(fd, min(65536, maximum + 1 - len(raw)))
                if not chunk: break
                raw.extend(chunk)
            if len(raw) > maximum: raise ProbeLimit()
            self.check(); return bytes(raw)
        finally: os.close(fd)
    def link(self, path):
        self.check(); result = os.readlink(path)
        if len(result) > 4096: raise ProbeLimit()
        self.check(); return result
    def unit(self, unit, properties=PROPERTIES):
        if unit not in UNITS or any(p not in PROPERTIES for p in properties):
            raise ValueError('fixed unit/property allowlist required')
        self.check(); end = min(self.end, self.clock() + 2)
        argv = ['/usr/bin/systemctl', 'show', '--no-pager',
                '--property=' + ','.join(properties), unit]
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, bufsize=0, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
            'SYSTEMD_PAGER': ''}, close_fds=True)
        selector = selectors.DefaultSelector()
        raw = bytearray()
        try:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = end - self.clock()
                if remaining <= 0: raise ProbeLimit()
                if not selector.select(remaining): raise ProbeLimit()
                chunk = os.read(process.stdout.fileno(), 16385-len(raw))
                if not chunk: break
                raw.extend(chunk)
                if len(raw) > 16384: raise ProbeLimit()
            remaining = end - self.clock()
            if remaining <= 0: raise ProbeLimit()
            code = process.wait(timeout=remaining)
            if code: raise ValueError('manager read failed')
            result = {}
            for line in raw.decode('utf-8', 'strict').splitlines():
                key, separator, value = line.partition('=')
                if not separator or key not in properties or key in result or len(value) > 4096:
                    raise ValueError('manager property mismatch')
                result[key] = value
            return result
        finally:
            selector.close(); process.stdout.close()
            if process.poll() is None:
                process.kill()
                try: process.wait(timeout=0.2)
                except subprocess.TimeoutExpired: pass


def _attempt(call):
    try: return call()
    except (OSError, ValueError, TypeError, IndexError, KeyError, OverflowError, ProbeLimit, UnicodeError, subprocess.TimeoutExpired) as error:
        return _error(error)


def _start(raw):
    # comm can contain spaces/parentheses; starttime is field22 after final ')'.
    fields = raw.decode('ascii', 'strict').rsplit(')', 1)[1].split()
    value = int(fields[19])
    if value < 1: raise ValueError('invalid starttime')
    return value


def process_evidence(backend, pid, unit=None):
    if type(pid) is not int or not 1 <= pid <= 2147483647:
        return failure('NO_LIVE_MAINPID')
    prefix = '/proc/%d/' % pid
    before = _start(backend.read(prefix+'stat', 16384))
    status = {}
    for line in backend.read(prefix+'status', 16384).decode('ascii', 'strict').splitlines():
        key, separator, value = line.partition(':')
        if separator and key in STATUS_FIELDS:
            value = value.strip()
            if len(value) > 1024 or re.fullmatch(r'[0-9a-fA-F \t]+', value) is None:
                raise ValueError('invalid process status')
            status[key] = value
    result = {'status': 'PASS_OBSERVED', 'pid': pid, 'start_ticks': before, 'selected_status': status}
    for name, suffix in (('exe_link', 'exe'), ('mount_namespace', 'ns/mnt'),
                         ('pid_namespace', 'ns/pid')):
        result[name] = _attempt(lambda suffix=suffix: backend.link(prefix+suffix))
    raw = _attempt(lambda: backend.read(prefix+'cgroup', 16384))
    if isinstance(raw, bytes):
        groups = raw.decode('utf-8', 'strict').splitlines()
        result['cgroup_sha256'] = hashlib.sha256(raw).hexdigest()
        result['exact_unit_cgroup'] = (any(line.split(':',2)[-1] == '/system.slice/'+unit
            for line in groups if line.count(':') >= 2) if unit else None)
    else: result['cgroup'] = raw
    raw = _attempt(lambda: backend.read(prefix+'cmdline', 65536))
    if isinstance(raw, bytes):
        result['argv_sha256'] = hashlib.sha256(raw).hexdigest()
        result['argv_count'] = len(raw.rstrip(b'\0').split(b'\0')) if raw else 0
    else: result['argv'] = raw
    if unit == 'xuanjun-ledger.service':
        result['fd3_link'] = _attempt(lambda: backend.link(prefix+'fd/3'))
    after = _start(backend.read(prefix+'stat', 16384))
    if after != before: return failure('PROCESS_LIFETIME_CHANGED')
    return result


def collect(backend=None):
    backend = backend or Backend()
    report = {'schema': 1, 'version': VERSION, 'mode': 'PASSIVE_METADATA_ONLY',
        'no_effects': True, 'production_admission': False, 'overall_budget_seconds': TOTAL_SECONDS,
        'effects_contract': {'service_actions': False, 'production_socket_connects': False,
            'database_access': False, 'secret_content_reads': False, 'permission_changes': False,
            'filesystem_writes': False},
        'creator_peercred': failure('NO_PRODUCTION_CONNECTION_ALLOWED'),
        'actual_sender_credentials': failure('NO_PRODUCTION_CONNECTION_ALLOWED'),
        'actual_broker_connect': failure('NOT_TESTED_IN_SERVICE_CONTEXT'),
        'actual_dashboard_connect': failure('NOT_TESTED_IN_SERVICE_CONTEXT'),
        'same_uid_owner_boundary': failure('REQUIRES_PROTECTED_PROCESS_GATE_AND_ISOLATION_PROOF'),
        'paths': {}, 'units': {}, 'processes': {}}
    for path in FIXED_PATHS:
        report['paths'][path] = _attempt(lambda path=path: backend.metadata(path))
    report['boot_id'] = _attempt(lambda: backend.read('/proc/sys/kernel/random/boot_id', 64).decode('ascii').strip())
    report['pid1'] = _attempt(lambda: process_evidence(backend, 1))
    meta = report['paths'][ACTIVATION]
    if (meta.get('kind') == 'file' and meta.get('uid') == 0
            and type(meta.get('mode')) is int and not meta['mode'] & 0o022):
        def activation():
            raw = backend.read(ACTIVATION, 65536)
            value = json.loads(raw.decode('utf-8'))
            selected = ('state','ledger_uuid','generation','epoch','instance','release_sha256',
                        'config_sha256','binary_sha256','ledger_socket')
            if not isinstance(value, dict): raise ValueError('activation object required')
            after=backend.metadata(ACTIVATION)
            keys=('uid','gid','mode','dev','inode','size','mtime_ns','ctime_ns')
            if any(meta.get(key)!=after.get(key) for key in keys):
                return failure('DESCRIPTOR_CHANGED_DURING_READ')
            result = {key:value[key] for key in selected if key in value}
            if any(type(v) not in (str,int) or (isinstance(v,str) and len(v)>512) for v in result.values()):
                raise ValueError('activation metadata shape')
            return {'status':'PASS_OBSERVED','descriptor_sha256':hashlib.sha256(raw).hexdigest(),
                    'selected_fields':result,'journal_consistency':'NOT_VERIFIED'}
        report['activation'] = _attempt(activation)
    else: report['activation'] = failure('PROTECTED_DESCRIPTOR_NOT_ESTABLISHED')
    for unit in UNITS:
        def observe(unit=unit):
            properties = backend.unit(unit)
            if properties.get('LoadState') != 'loaded':
                result=failure('UNIT_NOT_LOADED')
                result['properties']=properties
                return result
            result = {'status':'PASS_OBSERVED','properties':properties,
                      'missing_properties':[key for key in PROPERTIES if key not in properties], 'files':{}}
            paths = [properties.get('FragmentPath','')] + properties.get('DropInPaths','').split()
            if len(paths)>9: raise ProbeLimit()
            for path in paths:
                if not path: continue
                if not valid_unit_file(path,unit):
                    result['files'][path[:256]] = failure('UNEXPECTED_UNIT_FILE_PATH'); continue
                def unitfile(path=path):
                    metadata = backend.metadata(path)
                    if (metadata.get('kind')!='file' or metadata.get('uid')!=0
                            or metadata.get('mode',0o777)&0o022):
                        return failure('UNPROTECTED_UNIT_FILE')
                    raw=backend.read(path,65536)
                    after=backend.metadata(path)
                    keys=('uid','gid','mode','dev','inode','size','mtime_ns','ctime_ns')
                    if any(metadata.get(key)!=after.get(key) for key in keys):
                        return failure('UNIT_FILE_CHANGED_DURING_READ')
                    metadata['sha256']=hashlib.sha256(raw).hexdigest()
                    return metadata
                result['files'][path] = _attempt(unitfile)
            if properties.get('ActiveState') != 'active':
                result['process'] = failure('UNIT_NOT_ACTIVE')
            else:
                pid_text=properties.get('MainPID','0')
                pid=int(pid_text) if re.fullmatch(r'[0-9]{1,10}',pid_text) else 0
                result['process'] = _attempt(lambda: process_evidence(backend,pid,unit))
                after=backend.unit(unit,('MainPID','ActiveState','InvocationID'))
                if any(after.get(key)!=properties.get(key) for key in ('MainPID','ActiveState','InvocationID')):
                    result['process']=failure('UNIT_LIFETIME_CHANGED')
            return result
        report['units'][unit]=_attempt(observe)
    report['kernel_socket_map'] = _attempt(lambda: socket_map(backend.read('/proc/net/unix',262144)))
    report['evidence_complete'] = False
    return report


def socket_map(raw):
    rows=[]
    for line in raw.decode('utf-8','strict').splitlines():
        fields=line.split()
        if len(fields)==8 and fields[-1] in SOCKETS:
            if not fields[6].isdigit(): raise ValueError('invalid socket inode')
            rows.append({'path':fields[-1], 'kernel_socket_inode':int(fields[6]), 'flags':fields[3],
                         'type':fields[4], 'state':fields[5]})
    return {'status':'PASS_OBSERVED' if rows else 'NOT_VERIFIED', 'entries':rows,
            'creator_credentials':'NOT_VERIFIED', 'acceptor_identity':'NOT_VERIFIED'}


def encode_report(report):
    raw=(json.dumps(report,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode('utf-8')
    if len(raw)>MAX_OUTPUT:
        raw=(json.dumps({'schema':1,'version':VERSION,'mode':'PASSIVE_METADATA_ONLY',
            'no_effects':True,'production_admission':False,'status':'NOT_VERIFIED',
            'reason':'TOTAL_OUTPUT_BOUND',
            'collector_sha256':report.get('collector_sha256','NOT_VERIFIED')})+'\n').encode('utf-8')
    return raw


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=VERSION)
    parser.parse_args(argv)
    report=collect()
    try:
        with open(os.path.realpath(__file__),'rb') as stream:
            raw=stream.read(131073)
        report['collector_sha256']=hashlib.sha256(raw).hexdigest() if len(raw)<=131072 else 'NOT_VERIFIED'
    except OSError: report['collector_sha256']='NOT_VERIFIED'
    import sys
    sys.stdout.buffer.write(encode_report(report))
    return 0


if __name__=='__main__': raise SystemExit(main())
