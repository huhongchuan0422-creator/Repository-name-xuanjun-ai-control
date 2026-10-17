"""Owner-authorized Korea -> domestic private code/dependency installation.

Creates one NEW private prefix only. No service/user/unit/proxy/DB/credential setup,
no application import or activation. Root passwords remain SSH terminal input.
"""
import base64
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time

KOREA = 'iZmj7a5kwr75qc1tul4kf9Z'
DOMESTIC = 'iZvt5t8tlrm8oiZ'
BASE = Path('/opt/xuanjun-migration-s07')
ATTEMPT = Path('/var/lib/xuanjun-pr99-s07-stage-v1')
LOCAL_ATTEMPT = Path('/root/pr99-s07-domestic-stage-v1')
RESOLVER = Path('/root/pr99-handoff-resolve-51c23aaa/resolve.py')
RESOLVER_SHA = '10d24ddfea39347930115a4dc57e81b0b41461c10bd71e70b7f7d15afeb3fea4'
HOST_KEY = '47.101.152.210 ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBF1HeuGyjt1sqB50tPRqy3bhKqukn2ztSk+RlcQix2J+sLAPplEMnmjG2lGQQS49KV1qNjO1itysOwlJFezlEOM=\n'
PINS = {'cryptography': '50.0.1', 'requests': '2.34.2', 'sqlalchemy': '2.0.54'}
PORTAL_SHA = '57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1'
ROLES = {
    'portal': ('scripts/secure_secrets_portal_server.py', '622a0723974cbf27209a9ad75d5d2a621a7414270c66dc8be8f4e5c25e2fdd02'),
    'wecom-contact': ('ai_service/wecom_customer_contact_service.py', '06937f3a724ed47c5f543c4e209ce7f58d660d0735b6242067059c7a13fbb6ae'),
    'wecom-service': ('ai_service/wecom_customer_service.py', 'd873a08ceaf6a436c9ddfd37499016b5f1dd26dc29465b70e47d8a4847f59795'),
}
UNITS = ('nginx.service', 'provider-neutral-domestic-bridge.service', 'xuanjun-site-hub-preview.service',
         'secure-secrets-portal.service', 'xuanjun-wecom-customer-contact.service', 'xuanjun-wecom-customer-service.service')
CLEAN = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C', 'PYTHONDONTWRITEBYTECODE': '1'}
MAX_BYTES = 32 * 1024 * 1024


class Hold(RuntimeError):
    pass


def need(ok, code):
    if not ok:
        raise Hold(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def interrupted(number, frame):
    raise Hold('SIGNAL_' + str(number))


def stable(path, limit, private=True):
    path = Path(path)
    for parent in reversed(path.parents):
        s = parent.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022, 'UNTRUSTED_PARENT')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        a = os.fstat(f.fileno())
        need(stat.S_ISREG(a.st_mode) and a.st_uid == 0 and a.st_nlink == 1
             and not a.st_mode & 0o022 and 0 <= a.st_size <= limit, 'FILE_IDENTITY')
        if private:
            need(stat.S_IMODE(a.st_mode) in (0o400, 0o600), 'FILE_NOT_PRIVATE')
        raw = f.read(limit + 1)
        b = os.fstat(f.fileno())
    c = path.lstat()
    need(len(raw) == a.st_size and all(getattr(a, k) == getattr(b, k) == getattr(c, k)
         for k in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')), 'FILE_DRIFT')
    return raw


def write(path, raw, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as f:
        os.fchmod(f.fileno(), mode)
        f.write(raw); f.flush(); os.fsync(f.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def encoded(obj):
    return (json.dumps(obj, sort_keys=True, indent=2) + '\n').encode()


def absent(path):
    need(not os.path.lexists(path), 'EXISTING_TARGET_OR_ATTEMPT_NO_RETRY')


def package_bytes(files, facts):
    need(0 < len(files) <= 1000 and sum(map(len, files.values())) <= MAX_BYTES, 'SOURCE_PACKAGE_LIMIT')
    rows = {}
    for name, raw in files.items():
        p = PurePosixPath(name)
        need(p.suffix == '.py' and not p.is_absolute() and str(p) == name and '..' not in p.parts
             and '\\' not in name and re.fullmatch(r'[A-Za-z0-9_./-]+', name), 'SOURCE_PACKAGE_PATH')
        rows[name] = {'bytes': len(raw), 'sha256': sha(raw), 'base64': base64.b64encode(raw).decode()}
    return encoded({'schema_version': 1, 'scope': 'S07_PRIVATE_SOURCE_AND_ENVIRONMENT_ONLY',
                    'source_aggregate_sha256': '7e9859b04806aba717cbd7414d2aff52c041d810c78d5be902168898ae8300de',
                    'roles': facts, 'requirements': PINS, 'files': rows})


def unpack(raw, expected_sha):
    need(len(raw) <= MAX_BYTES * 2 and sha(raw) == expected_sha, 'PACKAGE_DIGEST')
    obj = json.loads(raw)
    need(obj['scope'] == 'S07_PRIVATE_SOURCE_AND_ENVIRONMENT_ONLY' and obj['requirements'] == PINS
         and obj['source_aggregate_sha256'] == '7e9859b04806aba717cbd7414d2aff52c041d810c78d5be902168898ae8300de'
         and set(obj['roles']) == set(ROLES), 'PACKAGE_SCOPE')
    files = {}
    for name, row in obj['files'].items():
        p = PurePosixPath(name)
        need(p.suffix == '.py' and not p.is_absolute() and str(p) == name and '..' not in p.parts
             and '\\' not in name and re.fullmatch(r'[A-Za-z0-9_./-]+', name), 'PACKAGE_MEMBER_PATH')
        data = base64.b64decode(row['base64'], validate=True)
        need(type(row['bytes']) is int and len(data) == row['bytes'] and sha(data) == row['sha256'], 'PACKAGE_MEMBER_HASH')
        files[name] = data
        need(len(files) <= 1000 and sum(map(len, files.values())) <= MAX_BYTES, 'PACKAGE_SIZE')
    for role, (entry, closure_hash) in ROLES.items():
        need(obj['roles'][role]['entry'] == entry and obj['roles'][role]['closure_sha256'] == closure_hash
             and entry in files, 'ROLE_CLOSURE_BINDING')
    need(sha(files['scripts/secure_secrets_portal_server.py']) == PORTAL_SHA, 'R4_PORTAL_SOURCE_REQUIRED')
    return obj, files


def prepare_package():
    raw = stable(RESOLVER, 100000)
    need(sha(raw) == RESOLVER_SHA, 'REVIEWED_RESOLVER_BYTES')
    resolver = {'__name__': 'reviewed_resolver_functions', '__file__': str(RESOLVER)}
    exec(compile(raw, str(RESOLVER), 'exec'), resolver)
    projection, ns = resolver['bootstrap']()
    root, r2 = projection['ROOT'], resolver['R2']
    receipt = json.loads(ns['stable_file'](root / 'final-receipt.json', 20000, private=True))
    need(receipt['status'] == 'S06_PRIVATE_RUNTIME_CONTRACT_RECEIVED_PASS'
         and receipt['archive_sha256'] == projection['ARCHIVE_SHA'], 'S06_ACCEPTED_INPUT_CHANGED')
    point = json.loads(ns['stable_file'](r2 / 'final-receipt.json', 20000, private=True))
    need(point['status'] == 'CURRENT_OFFLINE_POINT_RECEIVED_PASS' and point['approval_comment_id'] == 6217030577
         and point['database_sha256'] == resolver['DB_SHA'] and point['cipher_sha256'] == resolver['R2_CIPHER'], 'R2_ACCEPTED_INPUT_CHANGED')
    expected = json.loads(ns['stable_file'](r2 / 'receipt.json', 20000, private=True))
    manifest = ns['stable_file'](r2 / 'verified/manifest.json', 2 * 1024 * 1024, private=True)
    need(sha(manifest) == expected['manifest_sha256'], 'PRIVATE_SOURCE_MANIFEST')
    sources = resolver['source_manifest'](json.loads(manifest))
    collected, facts = {}, {}
    def reader(name):
        data = ns['stable_file'](r2 / 'verified/code' / name, sources[name]['bytes'], private=True)
        collected[name] = data
        return data
    for role, (entry, closure_hash) in ROLES.items():
        result = resolver['closure'](entry, sources, reader)
        need(result['closure_sha256'] == closure_hash and not result['missing_local_modules'], 'STATIC_ROLE_CLOSURE_CHANGED')
        facts[role] = result
    # Package metadata only: never import the application or existing dependencies.
    site = Path('/opt/xuanjun-binance-offline-env-20261016/venv/lib/python3.11/site-packages')
    for p in list(reversed(site.parents)) + [site]:
        s = p.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022, 'SOURCE_ENVIRONMENT_IDENTITY')
    distributions = {d.metadata['Name'].lower().replace('_', '-'): d.version for d in importlib.metadata.distributions(path=[str(site)])}
    need(all(distributions.get(k) == v for k, v in PINS.items()), 'ACCEPTED_DEPENDENCY_VERSIONS_CHANGED')
    raw = package_bytes(collected, facts)
    unpack(raw, sha(raw))
    return raw


def protected_snapshot():
    r = subprocess.run(['/usr/bin/systemctl', 'show', *UNITS, '-p', 'Id', '-p', 'LoadState',
                        '-p', 'ActiveState', '-p', 'SubState', '-p', 'MainPID', '--no-pager'],
                       capture_output=True, text=True, timeout=15, env=CLEAN)
    need(r.returncode == 0, 'PROTECTED_UNIT_QUERY')
    current = Path('/var/www/wenwenwenyiyiyi.work/current')
    need(current.is_symlink(), 'WORK_CURRENT_IDENTITY')
    # Root-owned website contents may be group-readable; no business endpoint is called.
    homepage = current / 'public/index.html'
    fd = os.open(homepage, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        s = os.fstat(f.fileno()); need(stat.S_ISREG(s.st_mode) and s.st_size < 4 * 1024 * 1024, 'WORK_INDEX_IDENTITY')
        body = f.read(4 * 1024 * 1024)
    return {'units': r.stdout, 'current': os.readlink(current), 'index_sha256': sha(body)}


def process(args, log, timeout):
    with log.open('xb') as out:
        proc = subprocess.Popen(args, stdout=out, stderr=out, env=dict(CLEAN, PIP_CONFIG_FILE='/dev/null',
                                PIP_DISABLE_PIP_VERSION_CHECK='1'), start_new_session=True)
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    rc = proc.wait(timeout=15)
                    break
                except subprocess.TimeoutExpired:
                    print('DOMESTIC_INSTALL_PROGRESS dependency_step_active', flush=True)
                    need(time.monotonic() < deadline, 'DEPENDENCY_STEP_TIMEOUT')
        except BaseException:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait(timeout=10)
            raise
    need(rc == 0, 'DEPENDENCY_STEP_FAILED_PRIVATE_LOG')


def receive(raw, expected_sha):
    need(os.geteuid() == 0 and os.uname().nodename == DOMESTIC and sys.version_info[:2] == (3, 11), 'DOMESTIC_ROOT_PYTHON311_REQUIRED')
    os.umask(0o077)
    for number in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(number, interrupted)
    obj, files = unpack(raw, expected_sha)
    for path in (BASE.parent, ATTEMPT.parent):
        s = path.lstat(); need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022, 'TARGET_PARENT')
    absent(BASE); absent(ATTEMPT)
    import shutil
    need(shutil.disk_usage('/opt').free >= 1024 * 1024 * 1024, 'TARGET_DISK_SPACE')
    before = protected_snapshot()
    ATTEMPT.mkdir(mode=0o700)
    write(ATTEMPT / 'started.json', encoded({'package_sha256': expected_sha, 'epoch': int(time.time())}))
    try:
        write(ATTEMPT / 'protected.before.json', encoded(before))
        BASE.mkdir(mode=0o700)
        app = BASE / 'app'; app.mkdir(mode=0o700)
        for name, data in sorted(files.items()):
            target = app / name
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            write(target, data, mode=0o400)
        write(BASE / 'source-plan.json', encoded({k: v for k, v in obj.items() if k != 'files'}))
        write(BASE / 'source-manifest.json', encoded({p: {'bytes': len(b), 'sha256': sha(b)} for p, b in sorted(files.items())}))
        py = BASE / 'venv/bin/python'
        print('DOMESTIC_SOURCE_INSTALLED; BUILD_ISOLATED_ENVIRONMENT', flush=True)
        process(['/usr/bin/python3', '-I', '-B', '-m', 'venv', str(BASE / 'venv')], ATTEMPT / 'venv-private.log', 120)
        process([str(py), '-I', '-B', '-m', 'pip', 'install', '--isolated', '--no-input', '--no-cache-dir',
                 '--only-binary=:all:', '--index-url', 'https://pypi.org/simple'] + [k + '==' + v for k, v in sorted(PINS.items())],
                ATTEMPT / 'dependency-private.log', 900)
        process([str(py), '-I', '-B', '-m', 'pip', 'check'], ATTEMPT / 'pip-check-private.log', 60)
        process([str(py), '-I', '-B', '-c', 'import cryptography,requests,sqlalchemy'], ATTEMPT / 'dependency-import-private.log', 60)
        result = subprocess.run([str(py), '-I', '-B', '-c',
            'import importlib.metadata,json;print(json.dumps({n:importlib.metadata.version(n) for n in ("cryptography","requests","sqlalchemy")}))'],
            capture_output=True, text=True, timeout=30, env=CLEAN)
        need(result.returncode == 0 and json.loads(result.stdout) == PINS, 'INSTALLED_DEPENDENCY_VERSION')
        for name, data in files.items():
            need(sha(stable(app / name, len(data))) == sha(data), 'INSTALLED_SOURCE_DRIFT')
        after = protected_snapshot()
        write(ATTEMPT / 'protected.after.json', encoded(after))
        need(after == before, 'PROTECTED_STATE_CHANGED_PRESERVE_CANDIDATE')
        receipt = {'status': 'DOMESTIC_S07_PRIVATE_CODE_AND_ENV_INSTALLED_PASS', 'host': DOMESTIC,
            'package_sha256': expected_sha, 'source_files': len(files), 'roles': sorted(ROLES),
            'prefix': str(BASE), 'dependencies': PINS, 'pip_check': 'PASS', 'dependency_imports': 'PASS',
            'application_imported': False, 'services_installed': False, 'service_actions': 0,
            'proxy_changed': False, 'database_opened': False, 'credential_files_imported': False,
            'inline_source_secret_absence_proven': False,
            'website_and_protected_units_unchanged': True, 'production_cutover': False,
            'dependency_network': 'PYPI_WHEEL_INSTALL_ONLY', 'runtime_configuration_ready': False,
            'business_api_requests': 0, 'tokyo_retirement': 'HOLD', 'retry_allowed': False}
        write(ATTEMPT / 'receipt.json', encoded(receipt))
        print(json.dumps(receipt, sort_keys=True), flush=True)
    except BaseException as error:
        reason = str(error) if isinstance(error, Hold) else type(error).__name__
        write(ATTEMPT / 'failure.json', encoded({'status': 'HOLD_PRESERVE_PARTIAL_INSTALL', 'reason': reason, 'retry_allowed': False}))
        raise


def main():
    need(os.geteuid() == 0 and os.uname().nodename == KOREA and sys.version_info[:2] == (3, 11), 'KOREA_ROOT_PYTHON311_REQUIRED')
    os.umask(0o077)
    for number in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(number, interrupted)
    self_raw = stable(Path(__file__).absolute(), 100000)
    absent(LOCAL_ATTEMPT)
    raw = prepare_package()  # Read/validate local copies before any installation action.
    session = Path(tempfile.mkdtemp(prefix='pr99-domestic-auth-', dir='/root'))
    write(session / 'known_hosts', HOST_KEY.encode())
    ssh = ['/usr/bin/ssh', '-T', '-S', str(session / 'socket'), '-o', 'ControlMaster=auto', '-o', 'ControlPersist=120',
           '-o', 'UserKnownHostsFile=' + str(session / 'known_hosts'), '-o', 'GlobalKnownHostsFile=/dev/null',
           '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlgorithms=ecdsa-sha2-nistp256', '-o', 'UpdateHostKeys=no',
           '-o', 'ClearAllForwardings=yes', '-o', 'ForwardAgent=no', '-o', 'ForwardX11=no', '-o', 'ConnectTimeout=10']
    remote = 'root@47.101.152.210'
    try:
        print('请输入国内服务器root密码；本批安装独立代码与依赖目录。', flush=True)
        subprocess.run(ssh + ['-n', '-o', 'BatchMode=no', '-o', 'NumberOfPasswordPrompts=3', remote,
            'test "$(hostname -s)" = ' + DOMESTIC + ' && test "$(id -u)" = 0 && test ! -e /opt/xuanjun-migration-s07 && test ! -L /opt/xuanjun-migration-s07'],
            check=True, timeout=180)
        LOCAL_ATTEMPT.mkdir(mode=0o700)
        write(LOCAL_ATTEMPT / 'package.json', raw)
        write(LOCAL_ATTEMPT / 'started.json', encoded({'package_sha256': sha(raw), 'code_sha256': sha(self_raw)}))
        code = ('import base64,json;ns={"__name__":"fixed_domestic_receiver"};exec(' + repr(self_raw.decode()) + ',ns)\n'
                'try:\n ns["receive"](base64.b64decode(' + repr(base64.b64encode(raw).decode()) + '),' + repr(sha(raw)) + ')\n'
                'except BaseException as e:\n print(json.dumps({"status":"DOMESTIC_STAGE_HOLD_PRESERVE","reason":str(e) if isinstance(e,ns["Hold"]) else type(e).__name__,"retry_allowed":False}),flush=True);raise SystemExit(2)\n').encode()
        with (LOCAL_ATTEMPT / 'public-result.log').open('xb') as out, (LOCAL_ATTEMPT / 'ssh-private.log').open('xb') as err:
            proc = subprocess.Popen(ssh + ['-o', 'BatchMode=yes', remote, '/usr/bin/python3 -I -B -u -'],
                stdin=subprocess.PIPE, stdout=out, stderr=err)
            # Remote stdin contains the fixed receiver and private source payload; never log it.
            proc.stdin.write(code); proc.stdin.close()
            deadline = time.monotonic() + 1200
            try:
                while True:
                    try:
                        rc = proc.wait(timeout=15); break
                    except subprocess.TimeoutExpired:
                        print('S07_INSTALL_PROGRESS 国内独立目录安装中；日志私有保存。', flush=True)
                        need(time.monotonic() < deadline, 'REMOTE_INSTALL_DEADLINE_UNKNOWN_PRESERVE')
            except BaseException:
                proc.terminate(); proc.wait(timeout=20)
                raise
        public = stable(LOCAL_ATTEMPT / 'public-result.log', 100000)
        print(public.decode(), end='', flush=True)
        need(rc == 0, 'REMOTE_INSTALL_FAILED_OR_UNKNOWN_PRESERVE')
        rows = [json.loads(x) for x in public.decode().splitlines() if x.startswith('{')]
        need(rows and rows[-1].get('status') == 'DOMESTIC_S07_PRIVATE_CODE_AND_ENV_INSTALLED_PASS'
             and rows[-1].get('package_sha256') == sha(raw), 'REMOTE_RECEIPT_MISSING')
        write(LOCAL_ATTEMPT / 'receipt.json', encoded(rows[-1]))
    finally:
        try:
            subprocess.run(ssh + ['-o', 'BatchMode=yes', '-O', 'exit', remote], capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:
        reason = str(e) if isinstance(e, Hold) and re.fullmatch('[A-Z0-9_]{1,100}', str(e)) else type(e).__name__
        try:
            info = LOCAL_ATTEMPT.lstat()
            if os.geteuid() == 0 and os.uname().nodename == KOREA and stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700:
                write(LOCAL_ATTEMPT / 'failure.json', encoded({'status': 'HOLD_PRESERVE_EVIDENCE', 'reason': reason, 'remote_result': 'INSPECT_BEFORE_ANY_RETRY', 'retry_allowed': False}))
        except (OSError, Hold):
            pass
        print('S07_INSTALL=HOLD REASON=' + reason + ' PRESERVE_EVIDENCE_NO_RETRY', flush=True)
        raise SystemExit(2)
