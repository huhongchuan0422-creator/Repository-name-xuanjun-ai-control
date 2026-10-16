"""Resolve already received source/configuration into a non-executable handoff plan.

No network, subprocess, service operations, writes, application imports, key reads,
environment-file reads or database reads. Never output arbitrary command arguments.
"""
import ast
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import sys

PROJECTOR = Path('/root/pr99-contract-plan.KULiMTLo/plan.py')
PROJECTOR_SHA = '4ad3d8cfa5b889632fda2129c9ff92c476a26a8561ba7a185fe39099ae3a7ec5'
R2 = Path('/root/pr99-current-point-received-v2')
SOURCE_AGGREGATE = '7e9859b04806aba717cbd7414d2aff52c041d810c78d5be902168898ae8300de'
DB_SHA = '6d451dfdc4714ca9bc704d719dcb47b02ec1e2ce243f886bfb2578a27fbca232'
R2_CIPHER = '2ac42b9e69c69260c99387b2e1ae339dd2e80b3f01c1984858e458e6c8872d32'


class Hold(RuntimeError):
    pass


def need(ok, code):
    if not ok:
        raise Hold(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bootstrap():
    p = PROJECTOR
    for parent in reversed(p.parents):
        s = parent.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
             'PROJECTOR_PARENT')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        a = os.fstat(f.fileno())
        need(stat.S_ISREG(a.st_mode) and a.st_uid == 0 and a.st_nlink == 1
             and stat.S_IMODE(a.st_mode) in (0o400, 0o600) and a.st_size < 100000,
             'PROJECTOR_IDENTITY')
        raw = f.read(100001)
        b = os.fstat(f.fileno())
    c = p.lstat()
    need(len(raw) == a.st_size and sha(raw) == PROJECTOR_SHA
         and all(getattr(a, k) == getattr(b, k) == getattr(c, k) for k in
                 ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')),
         'PROJECTOR_BYTES_CHANGED')
    projection = {'__name__': 'received_projection_functions', '__file__': str(p)}
    exec(compile(raw, str(p), 'exec'), projection)
    collector_raw = projection['read_collector']()
    ns = {'__name__': 'approved_s06_functions', '__file__': str(projection['COLLECTOR'])}
    exec(compile(collector_raw, ns['__file__'], 'exec'), ns)
    return projection, ns


def unit_service(raw):
    """Conservative unit text recognition. Unknown syntax never executes."""
    section, fields = '', {}
    for line in raw.decode('utf-8').replace('\\\n', ' ').splitlines():
        line = line.strip()
        if not line or line.startswith(('#', ';')):
            continue
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
        elif section == 'Service' and '=' in line:
            k, v = line.split('=', 1)
            k = k.strip()
            if k not in ('ExecStart', 'ExecStartPre', 'ExecStartPost', 'ExecStop',
                          'Environment', 'EnvironmentFile', 'LoadCredential'):
                continue
            if not v.strip():
                fields[k] = []
            else:
                fields.setdefault(k, []).append(v.strip())
    return fields


def address(value):
    if value == 'localhost':
        return value
    if value.startswith('[') and value.endswith(']'):
        value = value[1:-1]
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        if re.fullmatch(r'(?:[a-z0-9-]+\.)*wenwenwenyiyiyi\.work', value):
            return value
    return 'UNKNOWN_REDACTED'


def forwarding(kind, value):
    host = r'(?:\[[0-9a-fA-F:]+\]|[A-Za-z0-9_.-]+)'
    m = re.fullmatch(r'(?:(' + host + r'):)?([0-9]+):(' + host + r'):([0-9]+)', value)
    if m:
        bind, port, dest, destport = m.groups()
        if 0 < int(port) <= 65535 and 0 < int(destport) <= 65535:
            return {'kind': kind, 'bind': address(bind) if bind else 'DEFAULT',
                    'listen_port': int(port), 'target': address(dest), 'target_port': int(destport)}
    if kind == 'D':
        m = re.fullmatch(r'(?:(' + host + r'):)?([0-9]+)', value)
        if m and 0 < int(m[2]) <= 65535:
            return {'kind': kind, 'bind': address(m[1]) if m[1] else 'DEFAULT', 'listen_port': int(m[2])}
    return {'kind': kind, 'status': 'UNKNOWN_REDACTED'}


def ssh_plan(args):
    result = {'destination': 'UNKNOWN', 'forwardings': [], 'identity_file_configured': False,
              'proxy_configuration_present': False, 'unknown_option_count': 0}
    i = 1
    while i < len(args):
        token = args[i]
        if not token.startswith('-'):
            result['destination'] = address(token.rsplit('@', 1)[-1])
            result['remote_command_present'] = i + 1 < len(args)
            break
        if re.fullmatch(r'-[46AaCfGgKkMNnqsTtVvXxYy]+', token):
            i += 1
            continue
        opt, value = token[:2], token[2:]
        if opt not in ('-o', '-L', '-R', '-D', '-i', '-p', '-l', '-F', '-J', '-E', '-S', '-b', '-c', '-m', '-e', '-W', '-w', '-O'):
            result['unknown_option_count'] += 1
            break
        if not value:
            i += 1
            if i >= len(args):
                result['unknown_option_count'] += 1
                break
            value = args[i]
        if opt in ('-L', '-R', '-D'):
            result['forwardings'].append(forwarding(opt[1:], value))
        elif opt == '-i':
            result['identity_file_configured'] = True
        elif opt in ('-J', '-F', '-W'):
            result['proxy_configuration_present'] = True
        elif opt == '-o':
            key, _, val = value.partition('=')
            key = key.lower()
            if key in ('identityfile', 'certificatefile'):
                result['identity_file_configured'] = True
            elif key in ('proxycommand', 'proxyjump', 'include'):
                result['proxy_configuration_present'] = True
            elif key in ('localforward', 'remoteforward'):
                result['forwardings'].append(forwarding('L' if key == 'localforward' else 'R', val.replace(' ', ':', 1)))
            elif key == 'stricthostkeychecking':
                result['strict_host_key_checking'] = val if val in ('yes', 'no', 'ask', 'accept-new') else 'UNKNOWN_REDACTED'
        i += 1
    return result


def python_entry(args, source_names):
    rest = args[1:]
    while rest and re.fullmatch(r'-[uIBEOsS]+', rest[0]):
        rest = rest[1:]
    if not rest:
        return None
    if rest[0] == '-m' and len(rest) > 1 and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', rest[1]):
        module = rest[1].replace('.', '/')
        for path in (module + '.py', module + '/__main__.py'):
            if path in source_names:
                return path
    elif rest[0].endswith('.py'):
        path = rest[0]
        if path.startswith('/opt/trading-system/'):
            path = path[len('/opt/trading-system/'):]
        if path in source_names:
            return path
    return None


def command_plan(raw, source_names):
    f = unit_service(raw)
    result = {'program': 'UNKNOWN', 'source_entry': None, 'exec_start_count': len(f.get('ExecStart', [])),
              'extra_start_stop_commands': sum(len(f.get(k, [])) for k in ('ExecStartPre', 'ExecStartPost', 'ExecStop')),
              'environment_assignment_count': 0, 'environment_file_directives': len(f.get('EnvironmentFile', [])),
              'load_credential_directives': len(f.get('LoadCredential', []))}
    # Count assignments without disclosing their names or values.
    for line in f.get('Environment', []):
        try:
            result['environment_assignment_count'] += sum(bool(re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', x)) for x in shlex.split(line))
        except ValueError:
            result['environment_assignment_count_unknown'] = True
    if result['exec_start_count'] != 1:
        return result
    try:
        args = shlex.split(f['ExecStart'][0])
    except ValueError:
        return result
    if not args:
        return result
    # A single leading '-' is systemd's ignore-exit-status prefix, not shell syntax.
    exe = args[0][1:] if args[0].startswith('-/') else args[0]
    if re.fullmatch(r'(?:/usr/bin/|/opt/trading-system/venv/bin/)python(?:3(?:\.11)?)?', exe):
        result.update(program='PYTHON', source_entry=python_entry([exe] + args[1:], source_names))
    elif exe in ('/usr/bin/ssh', '/bin/ssh'):
        result.update(program='SSH', ssh=ssh_plan(args))
    elif exe in ('/usr/bin/docker', '/bin/docker', '/usr/local/bin/docker', '/usr/bin/docker-compose', '/usr/local/bin/docker-compose'):
        result['program'] = 'DOCKER'
        result['container_operation'] = args[1] if len(args) > 1 and args[1] in ('start', 'run', 'compose', 'up') else 'UNKNOWN'
    elif exe in ('/bin/bash', '/usr/bin/bash', '/bin/sh', '/usr/bin/sh'):
        result['program'] = 'SHELL_PRIVATE_WRAPPER_REQUIRES_REVIEW'
    return result


def module_path(name, names):
    path = name.replace('.', '/')
    return [p for p in (path + '.py', path + '/__init__.py') if p in names]


def closure(entry, sources, reader):
    """Static AST only; source bytes are hashed first and never imported."""
    pending, seen, external, missing, dynamic = [entry], {}, set(), set(), 0
    roots = {p.split('/')[0] for p in sources if '/' in p and not p.startswith(('backup/', 'artifacts/', 'tests/'))}
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        need(len(seen) < 1363 and path in sources, 'STATIC_CLOSURE_BOUND')
        raw = reader(path)
        need(len(raw) == sources[path]['bytes'] and sha(raw) == sources[path]['sha256'], 'RECEIVED_SOURCE_DRIFT')
        seen[path] = sources[path]['sha256']
        # Include package initializers: importing a submodule executes them too.
        parents = path.split('/')[:-1]
        for n in range(1, len(parents) + 1):
            init = '/'.join(parents[:n]) + '/__init__.py'
            if init in sources and init not in seen:
                pending.append(init)
        tree = ast.parse(raw, filename='received-source')
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                package = path.split('/')[:-1]
                if node.level:
                    if node.level > len(package):
                        missing.add('RELATIVE_IMPORT_OUTSIDE_PACKAGE')
                        continue
                    base = '.'.join(package[:len(package) - node.level + 1] + ([node.module] if node.module else []))
                else:
                    base = node.module or ''
                modules = [base]
                for a in node.names:
                    candidate = base + '.' + a.name if base else a.name
                    if a.name != '*' and module_path(candidate, sources):
                        modules.append(candidate)
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in ('__import__', 'exec', 'eval') or isinstance(func, ast.Attribute) and func.attr in ('import_module', 'spec_from_file_location', 'exec_module'):
                    dynamic += 1
            for name in modules:
                if not name:
                    continue
                found = module_path(name, sources)
                if found:
                    pending.extend(found)
                elif name.split('.')[0] in roots:
                    if not any(p.startswith(name.replace('.', '/') + '/') for p in sources):
                        missing.add(name)
                elif name.split('.')[0] not in sys.stdlib_module_names:
                    external.add(name.split('.')[0])
    manifest = ''.join(p + '\0' + seen[p] + '\n' for p in sorted(seen)).encode()
    return {'entry': entry, 'source_files': len(seen), 'closure_sha256': sha(manifest),
            'missing_local_modules': sorted(missing), 'third_party_module_names': sorted(external),
            'dynamic_loading_calls': dynamic, 'runtime_data_or_configuration_closure_proven': False}


def source_manifest(value):
    rows = value['files']
    need(len(rows) == 1364 and len({r['path'] for r in rows}) == 1364, 'RECEIVED_MANIFEST_COUNT')
    sources, db = {}, []
    for row in rows:
        name = row['path']
        p = PurePosixPath(name)
        need(not p.is_absolute() and '..' not in p.parts and str(p) == name
             and '\\' not in name and '\x00' not in name, 'RECEIVED_MANIFEST_PATH')
        need(type(row['bytes']) is int and 0 <= row['bytes'] <= 64 * 1024 * 1024
             and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'RECEIVED_MANIFEST_ROW')
        if name.startswith('code/'):
            sources[name[5:]] = row
        else:
            db.append(row)
    need(len(sources) == 1363 and len(db) == 1 and db[0]['path'] == 'database/trading.db'
         and db[0]['sha256'] == DB_SHA, 'RECEIVED_MANIFEST_SCOPE')
    aggregate = ''.join(p + '\0' + sources[p]['sha256'] + '\0' + str(sources[p]['bytes']) + '\n' for p in sorted(sources)).encode()
    need(sha(aggregate) == SOURCE_AGGREGATE, 'SOURCE_AGGREGATE_CHANGED')
    return sources


def main():
    need(os.geteuid() == 0 and os.uname().nodename == 'iZmj7a5kwr75qc1tul4kf9Z', 'KOREA_ROOT_REQUIRED')
    projection, ns = bootstrap()
    read = lambda p, n: ns['stable_file'](p, n, private=True)
    ns['private_directory'](projection['ROOT'])
    final = json.loads(read(projection['ROOT'] / 'final-receipt.json', 20000))
    need(final.get('status') == 'S06_PRIVATE_RUNTIME_CONTRACT_RECEIVED_PASS'
         and final.get('approval_comment_id') == 6218349901
         and final.get('archive_sha256') == projection['ARCHIVE_SHA']
         and final.get('cipher_sha256') == projection['CIPHER_SHA'], 'ACCEPTED_S06_RECEIPT_CHANGED')
    expected = json.loads(read(projection['ROOT'] / 'receipt.json', 20000))
    need(expected.get('archive_sha256') == projection['ARCHIVE_SHA'], 'S06_ARCHIVE_BINDING')
    files = ns['verify_archive'](read(projection['ROOT'] / 'payload.tar.gz', 4 * 1024 * 1024 + 65536), expected)
    ns['private_directory'](R2)
    r2 = json.loads(read(R2 / 'final-receipt.json', 20000))
    need(r2.get('status') == 'CURRENT_OFFLINE_POINT_RECEIVED_PASS' and r2.get('approval_comment_id') == 6217030577
         and r2.get('database_sha256') == DB_SHA and r2.get('cipher_sha256') == R2_CIPHER, 'ACCEPTED_R2_RECEIPT_CHANGED')
    receipt = json.loads(read(R2 / 'receipt.json', 20000))
    manifest = read(R2 / 'verified/manifest.json', 2 * 1024 * 1024)
    need(sha(manifest) == receipt['manifest_sha256'], 'PRIVATE_MANIFEST_DIGEST')
    sources = source_manifest(json.loads(manifest))
    reader = lambda p: read(R2 / 'verified/code' / p, sources[p]['bytes'])
    rows, cache = [], {}
    for unit in ns['UNITS']:
        row = command_plan(files['units/' + unit], sources)
        row['unit'] = unit
        if row['source_entry']:
            entry = row['source_entry']
            if entry not in cache:
                cache[entry] = closure(entry, sources, reader)
            row['static_source_closure'] = cache[entry]
        rows.append(row)
    # All source reads already verified before any successful result is emitted.
    print(json.dumps({'status': 'RECEIVED_HANDOFF_RESOLUTION_PASS', 'units': rows,
        'source_snapshot_aggregate_sha256': SOURCE_AGGREGATE,
        'scope': 'ALREADY_RECEIVED_COPIES_ONLY_NOT_NEW_CAPTURE_OR_INSTALL',
        'network_requests': 0, 'service_actions': 0, 'files_written': 0,
        'application_imports': 0, 'database_opened': False, 'key_files_opened': False,
        'environment_files_opened': False, 'raw_arguments_or_environment_values_printed': False,
        'full_runtime_closure_proven': False, 'tokyo_retirement': 'HOLD'}, separators=(',', ':')), flush=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:
        reason = str(e) if isinstance(e, Hold) and re.fullmatch('[A-Z0-9_]{1,80}', str(e)) else type(e).__name__
        print('HANDOFF_RESOLUTION=HOLD REASON=' + reason + ' INPUTS_UNCHANGED', flush=True)
        raise SystemExit(2)
