"""Read the already received S06 copy; print an allowlisted planning projection.

No network, subprocess, key/EnvironmentFile/database access, writes or installation.
Never print raw unit text, command arguments, environment values or private logs.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat

ROOT = Path('/root/pr99-s06-runtime-received-v1')
COLLECTOR = Path('/root/pr99-s06-approved.66ER1spv/run.py')
COLLECTOR_SHA = '9ca936d3935732c0b4161f7599286ed63a022a142cb1e6cac69601f64bfb9eca'
ARCHIVE_SHA = 'ec11ca6f579beb681adfd739bfeca5b836a22812676fd86a298340913c5243fd'
CIPHER_SHA = 'd9bb83a859e0bfc307890539aa22ed872d9ab51c63db79a63f1e5cbeaa683e06'
KOREA = 'iZmj7a5kwr75qc1tul4kf9Z'
TOKYO = 'iZ6wee8q9z4t03hvqumwfhZ'


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_collector():
    for p in reversed(COLLECTOR.parents):
        s = p.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
             'UNTRUSTED_COLLECTOR_PARENT')
    fd = os.open(COLLECTOR, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        a = os.fstat(f.fileno())
        need(stat.S_ISREG(a.st_mode) and a.st_uid == 0 and a.st_nlink == 1
             and stat.S_IMODE(a.st_mode) in (0o400, 0o600) and a.st_size < 100000,
             'COLLECTOR_IDENTITY')
        raw = f.read(100001)
        b = os.fstat(f.fileno())
    c = COLLECTOR.lstat()
    need(all(getattr(a, k) == getattr(b, k) == getattr(c, k) for k in
             ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
         and len(raw) == a.st_size and digest(raw) == COLLECTOR_SHA,
         'COLLECTOR_CHANGED')
    return raw


def safe_path(value):
    # Known working-directory/script roots only; no arbitrary argument echo.
    if not isinstance(value, str) or '..' in value.split('/'):
        return 'UNKNOWN_REDACTED'
    if value in ('', '/', '/home/admin', '/opt/trading-system'):
        return value
    if re.fullmatch(r'/(?:opt/trading-system|home/admin)/[A-Za-z0-9_./-]{1,180}', value):
        return value
    return 'UNKNOWN_REDACTED'


def entry_summary(raw):
    """Recognize an executable and direct Python entry; never echo other argv."""
    service, starts = False, []
    lines = raw.decode('utf-8', errors='strict').replace('\\\n', ' ').splitlines()
    for line in lines:
        s = line.strip()
        if s.startswith('[') and s.endswith(']'):
            service = s == '[Service]'
        elif service and s.startswith('ExecStart='):
            value = s.partition('=')[2].strip()
            if not value:
                starts.clear()
            else:
                starts.append(value)
    result = {'exec_start_count': len(starts), 'program': 'UNKNOWN',
              'entrypoint': 'UNKNOWN', 'arguments_disclosed': False}
    if len(starts) != 1:
        return result
    try:
        args = shlex.split(starts[0])
    except ValueError:
        return result
    if not args:
        return result
    exe = args[0]
    allowed = {
        '/usr/bin/ssh': 'SSH', '/bin/ssh': 'SSH',
        '/bin/bash': 'SHELL', '/usr/bin/bash': 'SHELL',
        '/bin/sh': 'SHELL', '/usr/bin/sh': 'SHELL',
        '/usr/bin/docker': 'DOCKER', '/bin/docker': 'DOCKER',
    }
    result['program'] = allowed.get(exe, 'UNKNOWN')
    if re.fullmatch(r'(?:/usr/bin/|/opt/trading-system/venv/bin/)python(?:3(?:\.11)?)?', exe):
        result['program'] = 'PYTHON'
        rest = args[1:]
        while rest and re.fullmatch(r'-[uIB]+', rest[0]):
            rest = rest[1:]
        if rest and rest[0].endswith('.py'):
            value = rest[0]
            if re.fullmatch(r'(?:scripts|ai_service)/[A-Za-z0-9_/-]+\.py', value) and '..' not in value.split('/'):
                result['entrypoint'] = value
            elif value.startswith('/opt/trading-system/') and safe_path(value) != 'UNKNOWN_REDACTED':
                result['entrypoint'] = value
    return result


def projection(files, unit_names):
    private = json.loads(files['private-runtime.json'])
    need(private.get('environment_files_opened') is False
         and private.get('database_opened') is False
         and private.get('argv_read') is False, 'PRIVATE_METADATA_SCOPE')
    units = private['units']
    rows = []
    known_dependencies = set(unit_names) | {'provider-neutral-tunnel.service', 'docker.service'}
    for name in unit_names:
        m = units[name]
        row = {'unit': name, 'unit_sha256': digest(files['units/' + name]),
               'working_directory': safe_path(m.get('WorkingDirectory')),
               'environment_files_configured': bool(m.get('EnvironmentFiles')),
               'dependencies': {}, 'entry': entry_summary(files['units/' + name])}
        for field in ('User', 'Group', 'LoadState', 'ActiveState', 'SubState', 'MainPID'):
            value = m.get(field, '')
            row[field] = value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.@-]{0,80}', value) else 'UNKNOWN_REDACTED'
        for field in ('Requires', 'Wants', 'After'):
            names = m.get(field, '').split()
            row['dependencies'][field] = sorted(set(names) & known_dependencies)
            row['dependencies'][field + '_other_count'] = len(set(names) - known_dependencies)
        rows.append(row)
    listeners = []
    for item in private.get('listeners', []):
        if item.get('port') not in (443, 18080, 18443, 18761, 18770, 18780, 18781, 19443, 19444):
            continue
        owners = []
        for owner in item.get('visible_process_metadata', []):
            pid = owner.get('pid', '')
            owners.append({'pid': pid if isinstance(pid, str) and pid.isdigit() else 'UNKNOWN',
                           'units': sorted(set(owner.get('systemd_units', [])) & known_dependencies),
                           'owner_known': type(owner.get('uid')) is int})
        listeners.append({'port': item['port'], 'owners': owners,
                          'owner_observed': item.get('owner_observed') is True})
    return {'status': 'RECEIVED_CONTRACT_PLANNING_PROJECTION_PASS', 'units': rows,
            'tokyo_listener_owners_at_capture': listeners,
            'generic_tunnel_load_state': units.get('provider-neutral-tunnel.service', {}).get('LoadState')
                if units.get('provider-neutral-tunnel.service', {}).get('LoadState') in ('loaded', 'not-found') else 'UNKNOWN',
            'dropin_sha256': digest(files['dropins/provider-health-alert.conf']),
            'raw_unit_or_arguments_or_environment_printed': False,
            'configuration_complete': False, 'production_deployed': False,
            'analysis_limitations': ['SYSTEMD_UNIT_TEXT_IS_NOT_EXECUTED_OR_FULLY_INTERPRETED',
                                     'UNKNOWN_ENTRYPOINTS_REQUIRE_PRIVATE_FOLLOWUP',
                                     'ENVIRONMENT_FILES_AND_CHANNEL_KEY_MATERIAL_NOT_READ']}


def main():
    need(os.geteuid() == 0 and os.uname().nodename == KOREA, 'KOREA_ROOT_REQUIRED')
    raw = read_collector()
    ns = {'__name__': 's06_approved_functions', '__file__': str(COLLECTOR)}
    exec(compile(raw, str(COLLECTOR), 'exec'), ns)
    ns['private_directory'](ROOT)
    read = lambda name, limit: ns['stable_file'](ROOT / name, limit, private=True)
    final = json.loads(read('final-receipt.json', 20000))
    need(final.get('status') == 'S06_PRIVATE_RUNTIME_CONTRACT_RECEIVED_PASS'
         and final.get('approval_comment_id') == 6218349901 and final.get('host') == KOREA
         and final.get('archive_sha256') == ARCHIVE_SHA and final.get('cipher_sha256') == CIPHER_SHA
         and final.get('service_actions') == 0 and final.get('database_opened') is False,
         'ACCEPTED_RECEIPT_MISMATCH')
    receipt = json.loads(read('receipt.json', 20000))
    need(receipt.get('host') == TOKYO and receipt.get('file_count') == 12
         and receipt.get('archive_sha256') == ARCHIVE_SHA, 'SOURCE_RECEIPT_MISMATCH')
    archive = read('payload.tar.gz', 4 * 1024 * 1024 + 65536)
    need(digest(archive) == ARCHIVE_SHA, 'ARCHIVE_CHANGED')
    files = ns['verify_archive'](archive, receipt)
    result = projection(files, ns['UNITS'])
    result.update({'input': 'ALREADY_RECEIVED_COPY_ONLY_NOT_NEW_COLLECTION',
                   'archive_sha256': ARCHIVE_SHA, 'service_actions': 0,
                   'network_requests': 0, 'files_written': 0,
                   'environment_files_opened': False, 'database_opened': False,
                   'key_files_opened': False})
    print(json.dumps(result, sort_keys=True, ensure_ascii=True, separators=(',', ':')), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Exception text can contain private paths or unit tokens; do not echo it.
        reason = str(exc) if isinstance(exc, RuntimeError) and re.fullmatch(r'[A-Z0-9_]{1,80}', str(exc)) else type(exc).__name__
        print('CONTRACT_PROJECTION=HOLD REASON=' + reason + ' INPUT_UNCHANGED NO_INSTALL NO_CAPTURE', flush=True)
        raise SystemExit(2)
