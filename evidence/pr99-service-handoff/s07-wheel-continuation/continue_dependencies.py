"""Complete only the known S07 dependency timeout using Korea-downloaded wheels.

Owner-authorized bounded continuation, not replay of the initial installer.
Preserves old failures and source; no service, proxy, database or key actions.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from email.parser import BytesParser

OLD = Path('/root/pr99-s07-install-launch.a5NZU99H/install.py')
OLD_SHA = '745c67d34cf4b0d546aee28c74c11b1586a315a03d970cbebc37508ebc61f8fd'
LOCAL = Path('/root/pr99-s07-wheels-continuation-v1')
REMOTE = Path('/var/lib/xuanjun-pr99-s07-wheels-continuation-v1')
ALLOWED = {'cryptography', 'requests', 'sqlalchemy', 'cffi', 'pycparser', 'certifi',
           'charset-normalizer', 'idna', 'urllib3', 'greenlet', 'typing-extensions'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def load_old(raw):
    require(digest(raw) == OLD_SHA, 'ORIGINAL_INSTALLER_CHANGED')
    ns = {'__name__': 'original_installer_functions'}
    exec(compile(raw, 'original_installer.py', 'exec'), ns)
    return ns


def wheel_identity(name, raw):
    require(re.fullmatch(r'[A-Za-z0-9_.+-]+\.whl', name) is not None, 'WHEEL_FILENAME')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        require(len(z.namelist()) == len(set(z.namelist())), 'DUPLICATE_ZIP_MEMBER')
        for n in z.namelist():
            p = PurePosixPath(n)
            require(not p.is_absolute() and '..' not in p.parts and '\\' not in n, 'WHEEL_MEMBER_PATH')
        infos = [i for i in z.infolist() if i.filename.endswith('.dist-info/METADATA')]
        require(len(infos) == 1 and infos[0].file_size <= 1024*1024, 'WHEEL_METADATA')
        info = BytesParser().parsebytes(z.read(infos[0]))
    package = re.sub(r'[-_.]+', '-', info['Name']).lower()
    require(package in ALLOWED and bool(info['Version']), 'UNEXPECTED_WHEEL_PACKAGE')
    return package, info['Version']


def inspect_wheels(rows, pins):
    require(3 <= len(rows) <= 16, 'WHEEL_COUNT')
    require(sum(len(b) for b in rows.values()) <= 64*1024*1024, 'WHEEL_TOTAL_SIZE')
    versions = {}
    for name, raw in rows.items():
        package, version = wheel_identity(name, raw)
        require(package not in versions, 'DUPLICATE_PACKAGE')
        versions[package] = version
    require(all(versions.get(k) == v for k, v in pins.items()), 'PINNED_WHEEL_VERSION')
    return versions


def verify_existing(old, header):
    require(os.geteuid() == 0 and os.uname().nodename == old['DOMESTIC']
            and sys.version_info[:2] == (3, 11), 'WRONG_TARGET')
    read = old['stable']
    failure = json.loads(read(old['ATTEMPT']/'failure.json', 20000))
    require(failure == {'status': 'HOLD_PRESERVE_PARTIAL_INSTALL',
                       'reason': 'DEPENDENCY_STEP_TIMEOUT', 'retry_allowed': False}, 'WRONG_PRIOR_FAILURE')
    started = json.loads(read(old['ATTEMPT']/'started.json', 20000))
    require(started['package_sha256'] == header['package_sha256'], 'ORIGINAL_PACKAGE_CHANGED')
    manifest = json.loads(read(old['BASE']/'source-manifest.json', 2*1024*1024))
    require(manifest == header['sources'] and len(manifest) == 79, 'SOURCE_MANIFEST_CHANGED')
    for name, row in manifest.items():
        p = PurePosixPath(name)
        require(not p.is_absolute() and '..' not in p.parts and str(p) == name, 'SOURCE_PATH')
        require(digest(read(old['BASE']/'app'/name, row['bytes'])) == row['sha256'], 'SOURCE_CHANGED')
    require(not os.path.lexists(old['ATTEMPT']/'receipt.json'), 'ORIGINAL_ALREADY_SUCCEEDED')
    r = subprocess.run(['/usr/bin/pgrep', '-f', str(old['BASE'])], capture_output=True, text=True, timeout=10)
    require(r.returncode in (0, 1), 'PROCESS_QUERY_FAILED')
    pids = [int(x) for x in r.stdout.split()]
    require(not [p for p in pids if p != os.getpid()], 'PREFIX_PROCESS_STILL_ACTIVE')
    return manifest


def receive(header, stream):
    os.umask(0o077)
    old = load_old(base64.b64decode(header['original'], validate=True))
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, old['interrupted'])
    manifest = verify_existing(old, header)
    old['absent'](REMOTE)
    raw = stream.read(64*1024*1024 + 1)
    require(len(raw) <= 64*1024*1024 and digest(raw) == header['tar_sha256'], 'TRANSFER_DIGEST')
    wheels = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as tar:
        members = tar.getmembers()
        require(len(members) <= 16, 'ARCHIVE_MEMBER_COUNT')
        for member in members:
            require(member.isfile() and member.name not in wheels and 0 < member.size <= 32*1024*1024,
                    'ARCHIVE_MEMBER_TYPE_OR_SIZE')
            require(re.fullmatch(r'[A-Za-z0-9_.+-]+\.whl', member.name) is not None, 'ARCHIVE_MEMBER_NAME')
            wheels[member.name] = tar.extractfile(member).read()
    require({n: digest(b) for n, b in wheels.items()} == header['wheel_hashes'], 'WHEEL_HASHES')
    versions = inspect_wheels(wheels, old['PINS'])
    before = old['protected_snapshot']()
    REMOTE.mkdir(mode=0o700)
    write = old['write']; encoded = old['encoded']
    write(REMOTE/'started.json', encoded({'tar_sha256': header['tar_sha256'],
          'prior_failure_sha256': digest(old['stable'](old['ATTEMPT']/'failure.json', 20000)),
          'package_sha256': header['package_sha256']}))
    try:
        write(REMOTE/'protected.before.json', encoded(before))
        cache = REMOTE/'wheels'; cache.mkdir(mode=0o700)
        for name, data in wheels.items():
            write(cache/name, data, 0o400)
        # All resolved distributions, including transitive dependencies, are exactly hashed.
        requirements = ''.join(k+'=='+v+' --hash=sha256:'+header['wheel_hashes'][n]+'\n'
            for n in sorted(wheels) for k, v in [wheel_identity(n, wheels[n])])
        write(REMOTE/'requirements.txt', requirements.encode(), 0o400)
        py = str(old['BASE']/'venv/bin/python')
        old['process']([py, '-I', '-B', '-m', 'pip', 'install', '--isolated', '--no-input',
            '--no-index', '--no-cache-dir', '--only-binary=:all:', '--require-hashes',
            '--find-links', str(cache), '-r', str(REMOTE/'requirements.txt')], REMOTE/'offline-install.log', 180)
        old['process']([py, '-I', '-B', '-m', 'pip', 'check'], REMOTE/'pip-check.log', 45)
        code = 'import cryptography,requests,sqlalchemy,importlib.metadata as m;'
        code += 'assert all(m.version(k)==v for k,v in '+repr(versions)+'.items())'
        old['process']([py, '-I', '-B', '-c', code], REMOTE/'dependency-import.log', 45)
        verify_existing(old, header)
        after = old['protected_snapshot']()
        write(REMOTE/'protected.after.json', encoded(after))
        require(before == after, 'PROTECTED_STATE_CHANGED')
        result = {'status': 'DOMESTIC_S07_OFFLINE_DEPENDENCY_CONTINUATION_PASS',
            'host': old['DOMESTIC'], 'package_sha256': header['package_sha256'],
            'source_files': len(manifest), 'source_hashes': 'PASS', 'dependencies': versions,
            'wheel_tar_sha256': header['tar_sha256'], 'pip_check': 'PASS', 'dependency_imports': 'PASS',
            'original_failure_preserved': True, 'services_installed': False, 'service_actions': 0,
            'proxy_changed': False, 'database_opened': False, 'application_imported': False,
            'protected_state_unchanged_during_continuation': True,
            'original_install_after_snapshot': 'NOT_COMPLETED_NOT_RETROACTIVELY_CLAIMED',
            'production_cutover': False, 'runtime_configuration_ready': False,
            'business_api_requests': 0, 'tokyo_retirement': 'HOLD'}
        write(REMOTE/'receipt.json', encoded(result))
        print(json.dumps(result, sort_keys=True), flush=True)
    except BaseException as e:
        write(REMOTE/'failure.json', encoded({'status': 'HOLD_PRESERVE', 'reason': str(e)
            if isinstance(e, (RuntimeError, old['Hold'])) else type(e).__name__, 'retry_allowed': False}))
        raise


def main():
    old_raw = OLD.read_bytes(); old = load_old(old_raw)
    require(os.geteuid() == 0 and os.uname().nodename == old['KOREA']
            and sys.version_info[:2] == (3, 11), 'KOREA_ROOT_PYTHON311_REQUIRED')
    os.umask(0o077)
    old['absent'](LOCAL)
    raw = old['stable'](old['LOCAL_ATTEMPT']/'package.json', 64*1024*1024)
    plan, files = old['unpack'](raw, digest(raw))
    failure = json.loads(old['stable'](old['LOCAL_ATTEMPT']/'failure.json', 20000))
    require(failure['reason'] == 'REMOTE_INSTALL_FAILED_OR_UNKNOWN_PRESERVE', 'LOCAL_FAILURE_CHANGED')
    self_raw = old['stable'](Path(__file__).absolute(), 100000)
    session = Path(tempfile.mkdtemp(prefix='pr99-s07-wheel-auth-', dir='/root'))
    old['write'](session/'known_hosts', old['HOST_KEY'].encode())
    ssh = ['/usr/bin/ssh', '-T', '-S', str(session/'socket'), '-o', 'ControlMaster=auto',
        '-o', 'ControlPersist=900', '-o', 'UserKnownHostsFile='+str(session/'known_hosts'),
        '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'HostKeyAlgorithms=ecdsa-sha2-nistp256', '-o', 'UpdateHostKeys=no',
        '-o', 'ForwardAgent=no', '-o', 'ForwardX11=no', '-o', 'ClearAllForwardings=yes', '-o', 'ConnectTimeout=10']
    remote = 'root@47.101.152.210'
    try:
        print('请输入国内root密码；韩国下载wheel后传输至国内离线续接，不重装源码。', flush=True)
        subprocess.run(ssh+['-n', '-o', 'NumberOfPasswordPrompts=3', remote,
            'test "$(hostname -s)" = '+old['DOMESTIC']+' && test "$(id -u)" = 0'], check=True, timeout=180)
        LOCAL.mkdir(mode=0o700)
        wheels_dir = LOCAL/'wheels'; wheels_dir.mkdir(mode=0o700)
        py = '/opt/xuanjun-binance-offline-env-20261016/venv/bin/python'
        print('KOREA_WHEEL_DOWNLOAD_STARTED', flush=True)
        old['process']([py, '-I', '-B', '-m', 'pip', 'download', '--isolated', '--no-input',
            '--no-cache-dir', '--only-binary=:all:', '--index-url', 'https://pypi.org/simple',
            '--retries', '0', '--timeout', '30', '--dest', str(wheels_dir)]
            +[k+'=='+v for k,v in sorted(old['PINS'].items())], LOCAL/'download.log', 360)
        wheels = {p.name: old['stable'](p, 32*1024*1024, private=False) for p in wheels_dir.iterdir()}
        inspect_wheels(wheels, old['PINS'])
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w') as tar:
            for name, data in sorted(wheels.items()):
                info = tarfile.TarInfo(name); info.size = len(data); info.mode = 0o400
                tar.addfile(info, io.BytesIO(data))
        payload = buf.getvalue()
        header = {'original': base64.b64encode(old_raw).decode(),
            'continuation': base64.b64encode(self_raw).decode(), 'package_sha256': digest(raw),
            'sources': {n:{'bytes':len(b),'sha256':digest(b)} for n,b in files.items()},
            'wheel_hashes': {n:digest(b) for n,b in wheels.items()}, 'tar_sha256': digest(payload)}
        old['write'](LOCAL/'transfer-manifest.json', old['encoded']({k:v for k,v in header.items()
            if k not in ('original','continuation')}))
        bootstrap = ('import sys,json,base64;h=json.loads(sys.stdin.buffer.readline(200000));'
            'n={"__name__":"dependency_continuation"};exec(base64.b64decode(h["continuation"]),n);'
            'n["receive"](h,sys.stdin.buffer)')
        import shlex
        command = '/usr/bin/python3 -I -B -u -c '+shlex.quote(bootstrap)
        wire = json.dumps(header).encode()+b'\n'+payload
        print('WHEELS_READY; TRANSFER_AND_OFFLINE_INSTALL_STARTED bytes='+str(len(payload)), flush=True)
        with (LOCAL/'result.log').open('xb') as out, (LOCAL/'ssh-private.log').open('xb') as err:
            proc = subprocess.Popen(ssh+['-o','BatchMode=yes',remote,command], stdin=subprocess.PIPE, stdout=out, stderr=err)
            deadline = time.monotonic()+600; first = True
            while True:
                try:
                    proc.communicate(input=wire if first else None, timeout=15)
                    break
                except subprocess.TimeoutExpired:
                    first = False
                    print('S07_OFFLINE_CONTINUATION_PROGRESS', flush=True)
                    if time.monotonic() >= deadline:
                        proc.terminate(); proc.wait(timeout=15)
                        raise RuntimeError('REMOTE_RESULT_UNKNOWN_PRESERVE')
        text = old['stable'](LOCAL/'result.log', 100000).decode()
        print(text, end='', flush=True)
        require(proc.returncode == 0, 'REMOTE_FAILED_INSPECT_PRIVATE_LOG_NO_RETRY')
        results = [json.loads(s) for s in text.splitlines() if s.startswith('{')]
        require(results and results[-1]['status'] == 'DOMESTIC_S07_OFFLINE_DEPENDENCY_CONTINUATION_PASS'
            and results[-1]['package_sha256'] == digest(raw), 'SUCCESS_RECEIPT_MISSING')
        old['write'](LOCAL/'receipt.json', old['encoded'](results[-1]))
    finally:
        try:
            subprocess.run(ssh+['-O','exit',remote], capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:
        reason = str(e) if type(e) is RuntimeError and re.fullmatch('[A-Z0-9_]+', str(e)) else type(e).__name__
        print('S07_CONTINUATION_HOLD='+reason+' PRESERVE_ALL_NO_RETRY', flush=True)
        raise SystemExit(2)
