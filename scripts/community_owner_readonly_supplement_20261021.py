"""Narrow follow-up to the completed Owner probe; no application imports."""
import ast
import errno
import hashlib
import json
import os
import re
import signal
import socket
import stat
import subprocess
import sys

UK = 'iZd7oeikknn1z21sq6ji6zZ'
CN = 'iZvt5t8tlrm8oiZ'
DOMAIN = 'community-preview.wenwenwenyiyiyi.work'
ROOT = '/home/openclaw_ops/v8-domestic-operations/releases/domestic-real-ai-runtime-20261008-dual-channel-referral-r11/app'


def read_absolute(path, maximum):
    """Open every component without following symlinks, including parents."""
    if not path.startswith('/') or any(x in ('.', '..', '') for x in path.split('/')[1:]):
        raise ValueError('PATH_BOUNDARY')
    parts = path.split('/')[1:]
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(leaf)
            if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
                raise ValueError('FILE_TYPE_OR_SIZE')
            data = os.read(leaf, maximum + 1)
            if len(data) > maximum:
                raise ValueError('READ_SIZE')
            return data
        finally:
            os.close(leaf)
    finally:
        os.close(fd)


def failure(exc):
    if isinstance(exc, PermissionError):
        return 'PERMISSION_DENIED'
    if isinstance(exc, FileNotFoundError):
        return 'PATH_NOT_PRESENT'
    if isinstance(exc, OSError) and exc.errno in (errno.ELOOP, errno.ENOTDIR):
        return 'SYMLINK_OR_NON_DIRECTORY_REJECTED'
    if isinstance(exc, ValueError):
        return str(exc) if str(exc) in ('PATH_BOUNDARY', 'FILE_TYPE_OR_SIZE', 'READ_SIZE', 'MOUNT_LIMIT', 'CGROUP_PATH', 'AST_LIMIT') else 'VALIDATION_REJECTED'
    return type(exc).__name__


def mounts_from(text):
    result = []
    for line in text.splitlines():
        left, sep, right = line.partition(' - ')
        if not sep:
            continue
        fields, tail = left.split(), right.split()
        if len(fields) < 6 or len(tail) < 3 or tail[0] not in ('cgroup', 'cgroup2'):
            continue
        root, path = fields[3:5]
        if not path.startswith('/sys/fs/cgroup') or (path != '/sys/fs/cgroup' and not path.startswith('/sys/fs/cgroup/')):
            continue
        if not re.fullmatch(r'/[A-Za-z0-9_,./-]+', path) or '..' in path.split('/'):
            raise ValueError('CGROUP_PATH')
        controllers = sorted(set(tail[2].split(',')) & {'cpu', 'memory', 'pids'})
        if tail[0] == 'cgroup2' or controllers:
            result.append({'root': root, 'path': path, 'kind': tail[0], 'controllers': controllers})
        if len(result) > 6:
            raise ValueError('MOUNT_LIMIT')
    return result


def group_path(mount, membership):
    root = mount['root'].rstrip('/')
    if not membership.startswith('/') or any(x in ('.', '..') for x in membership.split('/')):
        raise ValueError('CGROUP_PATH')
    if root and membership != root and not membership.startswith(root + '/'):
        raise ValueError('CGROUP_PATH')
    suffix = membership[len(root):].strip('/')
    path = mount['path'] + ('/' + suffix if suffix else '')
    if not re.fullmatch(r'/[A-Za-z0-9_,./-]+', path):
        raise ValueError('CGROUP_PATH')
    return path


def cgroup_probe():
    pid = str(os.getpid())  # Avoid /proc/self symlink; keep strict reader unchanged.
    mounts = mounts_from(read_absolute('/proc/' + pid + '/mountinfo', 131072).decode())
    memberships = read_absolute('/proc/' + pid + '/cgroup', 16384).decode().splitlines()
    output = []
    for mount in mounts:
        files = []
        if mount['kind'] == 'cgroup2':
            files = ['cpu.max', 'memory.max', 'pids.max', 'pids.current']
        else:
            if 'cpu' in mount['controllers']:
                files += ['cpu.cfs_quota_us', 'cpu.cfs_period_us']
            if 'memory' in mount['controllers']:
                files += ['memory.limit_in_bytes']
            if 'pids' in mount['controllers']:
                files += ['pids.max', 'pids.current']
        paths = {mount['path']: 'hierarchy_root_not_project_budget'}
        for row in memberships:
            bits = row.split(':', 2)
            if len(bits) == 3 and ((mount['kind'] == 'cgroup2' and bits[0] == '0' and not bits[1]) or set(bits[1].split(',')) & set(mount['controllers'])):
                own = group_path(mount, bits[2])
                if own != mount['path']:
                    paths[own] = 'collector_process_not_application_budget'
        for path, scope in sorted(paths.items()):
            values = {}
            for name in files:
                try:
                    value = read_absolute(path + '/' + name, 4096).decode().strip()
                    values[name] = value if re.fullmatch(r'(?:max|-?[0-9]+)(?: [0-9]+)?', value) else 'INVALID_VALUE'
                except Exception as exc:
                    values[name] = failure(exc)
            output.append({'mount': mount, 'path': path, 'scope': scope, 'values': values})
    return {'entries': output, 'root_pids_absence': 'NOT_A_PERMISSION_OR_NO_CONTROLLER_PROOF', 'B5_P2_reserved': 'NOT_INFERRED'}


def classify_dns(code):
    if code == socket.EAI_AGAIN:
        return 'TEMPORARY_RESOLVER_FAILURE'
    if code == socket.EAI_NONAME:
        return 'LOCAL_RESOLVER_NAME_OR_ADDRESS_NOT_FOUND_NOT_AUTHORITATIVE_NXDOMAIN'
    if code == socket.EAI_FAIL:
        return 'NONRECOVERABLE_RESOLVER_FAILURE'
    return 'OTHER_RESOLVER_FAILURE'


def dns_probe():
    # A separate fixed child bounds resolver blocking; output contains no env/config.
    code = "import socket,json\ntry:\n a=socket.getaddrinfo(%r,443,type=socket.SOCK_STREAM);print(json.dumps({'addresses':sorted(set(x[4][0] for x in a))[:16]}))\nexcept socket.gaierror as e: print(json.dumps({'gai_errno':e.errno}))" % DOMAIN
    child = subprocess.Popen(['/usr/bin/python3', '-I', '-B', '-S', '-c', code], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env={'PATH': '/usr/bin:/bin'})
    try:
        raw = child.communicate(timeout=8)[0]
    except subprocess.TimeoutExpired:
        child.kill()
        child.communicate()
        return {'status': 'RESOLVER_TIMEOUT', 'tls_http': 'NOT_REACHED'}
    if child.returncode or len(raw) > 4096:
        return {'status': 'RESOLVER_CHILD_FAILED', 'tls_http': 'NOT_REACHED'}
    result = json.loads(raw.decode())
    if 'gai_errno' in result:
        result['status'] = classify_dns(result['gai_errno'])
        result['tls_http'] = 'NOT_REACHED'
    else:
        result['status'] = 'RESOLVED_TLS_HTTP_NOT_RETESTED'
    result['domain'] = DOMAIN
    return result


def constraint_structure(source):
    tree = ast.parse(source)
    output = []
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef) or cls.name not in ('Customer', 'CustomerSource'):
            continue
        columns = {}
        for node in cls.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'Column':
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        columns[target.id] = {k.arg: k.value.value for k in node.value.keywords if k.arg in ('unique', 'nullable', 'primary_key', 'index') and isinstance(k.value, ast.NameConstant) and type(k.value.value) is bool}
        constraints = []
        for node in ast.walk(cls):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'UniqueConstraint':
                fields = [arg.s if isinstance(arg, ast.Str) and arg.s in columns else '<UNRESOLVED_FIELD>' for arg in node.args]
                constraints.append(fields)
        output.append({'class': cls.name, 'columns': columns, 'unique_constraints': constraints})
    return output


def transaction_structure(source):
    tree = ast.parse(source)
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'session_scope']
    class Redact(ast.NodeTransformer):
        def visit_Str(self, node):
            return ast.copy_location(ast.Str(s='<REDACTED_LITERAL>'), node)
        def visit_Bytes(self, node):
            return ast.copy_location(ast.Bytes(s=b'<REDACTED_LITERAL>'), node)
        def visit_Num(self, node):
            return ast.copy_location(ast.Num(n=0), node)
    result = [ast.dump(Redact().visit(node), annotate_fields=True, include_attributes=False) for node in selected]
    if sum(map(len, result)) > 16384:
        raise ValueError('AST_LIMIT')
    return {'function': 'session_scope', 'count': len(selected), 'redacted_ast': result, 'executed': False}


def domestic_probe():
    output = []
    for relative, extractor in [('database/models/customer_operations_v8.py', constraint_structure), ('database/connection.py', transaction_structure)]:
        data = read_absolute(ROOT + '/' + relative, 32768)
        output.append({'path': relative, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'structure': extractor(data.decode('utf-8'))})
    return output


def main():
    host = os.uname().nodename.split('.')[0]
    if os.getuid() != 0 or os.geteuid() != 0 or host not in (UK, CN):
        raise SystemExit('HOLD_HOST_OR_ROOT')
    def deadline(*args):
        raise SystemExit('HOLD_30_SECONDS_KEEP_PARTIAL_OUTPUT')
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(30)
    for item, function in [('cgroup_supplement', cgroup_probe)] if host == UK else [('domestic_structure_supplement', domestic_probe)]:
        try:
            value = function()
        except Exception as exc:
            value = {'status': 'UNKNOWN', 'reason': failure(exc)}
        print(json.dumps({'host': host, 'item': item, 'value': value}), flush=True)
    print(json.dumps({'host': host, 'item': 'dns_classification', 'value': dns_probe()}), flush=True)
    print(json.dumps({'host': host, 'item': 'end', 'value': 'SUPPLEMENT_ONLY_NOT_ACCEPTANCE'}), flush=True)
    signal.alarm(0)


if __name__ == '__main__':
    main()
