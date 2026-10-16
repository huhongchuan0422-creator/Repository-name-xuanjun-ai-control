# FEATURE_ID: PR122_DOMESTIC_WEBSITE_OFFLINE_CANDIDATE
"""Owner-installed fixed channel. No checkout, package manager or arbitrary root command.
Grant/revoke are manual Owner-root actions, never present in the sudo allowlist.
The original customer's signed review and exact install gate remain authoritative.
"""
import contextlib
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
import tarfile

HOST = 'iZvt5t8tlrm8oiZ'
RUNNER_UID = 1002
BASE = Path('/var/lib/xuanjun-customer-channel')
EXEC = Path('/usr/local/libexec/xuanjun-customer-channel')
POLICY = Path('/etc/sudoers.d/xuanjun-customer-channel')
TAR_SHA = '7dd77ef573c338201ddc886b23585422ad4a07ae563a9c6ff92fe5b2f9d97b98'
MANIFEST_SHA = '570bb453bb13b372a9fed1900ec37594be979be3e423c14955db539ae7056b89'
SOURCE = 'feaef687ee296dcd55f094bf240fe843445d5ad7'
STAGED_ARCHIVE = Path('/root/PR122_CUSTOMER_CENTER_REVIEW_ONLY.tar.gz')
ACTIONS = ('inspect', 'plan', 'apply', 'rollback')


def need(ok):
    if not ok:
        raise RuntimeError('HOLD')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def secure(path, directory=False):
    """Check the entire root-owned, non-writable path before root reads/imports."""
    path = Path(path)
    need(path.is_absolute())
    for p in reversed((path,) + tuple(path.parents)):
        s = p.lstat()
        need(s.st_uid == 0 and not s.st_mode & 0o022 and not stat.S_ISLNK(s.st_mode))
        if p != path or directory:
            need(stat.S_ISDIR(s.st_mode))
        else:
            need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_size <= 10_000_000)
    return path


def files_from_tar(raw):
    need(sha(raw) == TAR_SHA)
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as t:
        items = t.getmembers()
        need(len(items) == 34 and len({m.name for m in items}) == 34)
        need(all(m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts
                 and m.name.startswith('customer-center/') and m.size <= 8_000_000 for m in items))
        files = {m.name.removeprefix('customer-center/'): t.extractfile(m).read() for m in items}
    raw_manifest = files.pop('CUSTOMER_MANIFEST.json')
    need(sha(raw_manifest) == MANIFEST_SHA)
    m = json.loads(raw_manifest)
    need(m['source_commit'] == SOURCE and len(m['files']) == 33)
    need(set(files) == {r['path'] for r in m['files']})
    for row in m['files']:
        need(len(files[row['path']]) == row['size'] and sha(files[row['path']]) == row['sha256'])
    files['CUSTOMER_MANIFEST.json'] = raw_manifest
    return files


def validate_bundle():
    root = secure(BASE / 'candidate', directory=True)
    raw = secure(BASE / 'PR122_CUSTOMER_CENTER_REVIEW_ONLY.tar.gz').read_bytes()
    files = files_from_tar(raw)
    actual = set()
    for folder, dirs, names in os.walk(root, followlinks=False):
        secure(folder, directory=True)
        for name in dirs:
            secure(Path(folder) / name, directory=True)
        for name in names:
            p = secure(Path(folder) / name)
            relative = p.relative_to(root).as_posix()
            need(relative in files and p.read_bytes() == files[relative])
            actual.add(relative)
    need(actual == set(files))
    return root


def exclusive(path, raw, mode):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def policy(runner):
    need(runner == 'githubrunner' and pwd.getpwnam(runner).pw_uid == RUNNER_UID)
    return (runner + ' ALL=(root) NOPASSWD: ' + ', '.join(str(EXEC) + ' ' + a for a in ACTIONS) + '\n').encode()


def grant():
    """Run only from Owner's root terminal after independent review of this grant."""
    need(os.environ.get('SUDO_UID') != str(RUNNER_UID) and sys.version_info >= (3, 11))
    need(not any(os.path.lexists(p) for p in (BASE, EXEC, POLICY)))
    secure(EXEC.parent, directory=True)
    secure(POLICY.parent, directory=True)
    # Fixed Owner-private staging input, no GitHub/Runner-supplied path or code.
    archive = secure(STAGED_ARCHIVE).read_bytes()
    files = files_from_tar(archive)
    code = secure(Path(__file__).absolute()).read_bytes()
    rules = policy('githubrunner')
    BASE.mkdir(mode=0o700)
    exclusive(BASE / 'grant-state.json', b'{"state":"PREPARING"}', 0o600)
    exclusive(BASE / 'channel.py', code, 0o444)
    exclusive(BASE / 'PR122_CUSTOMER_CENTER_REVIEW_ONLY.tar.gz', archive, 0o400)
    root = BASE / 'candidate'
    root.mkdir(mode=0o700)
    for relative, raw in sorted(files.items()):
        p = root / relative
        p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        exclusive(p, raw, 0o400)
    validate_bundle()
    wrapper = ('#!/bin/sh\nset -eu\n[ "$#" -eq 1 ] || exit 2\n'
               'exec /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C '
               'SUDO_UID="${SUDO_UID-}" /usr/bin/python3 -I -B ' + str(BASE / 'channel.py') + ' "$1"\n').encode()
    exclusive(EXEC, wrapper, 0o755)
    staged = BASE / 'sudoers.candidate'
    exclusive(staged, rules, 0o440)
    for args in (['/usr/sbin/visudo', '-c'], ['/usr/sbin/visudo', '-cf', str(staged)]):
        subprocess.run(args, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    exclusive(POLICY, rules, 0o440)
    subprocess.run(['/usr/sbin/visudo', '-c'], check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    (BASE / 'grant-state.json').write_text('{"state":"GRANTED"}')
    return {'state': 'GRANTED', 'customer_install_called': False, 'actions': ACTIONS}


def dispatch(action):
    need(action in ACTIONS and os.environ.get('SUDO_UID') == str(RUNNER_UID))
    secure(BASE, directory=True)
    need(json.loads(secure(BASE / 'grant-state.json').read_bytes()) == {'state': 'GRANTED'})
    if action == 'inspect':
        paths = ('/etc/xuanjun-customer-center/config.json', '/etc/xuanjun-customer-center/runtime.json',
                 '/etc/xuanjun-customer-center/INDEPENDENT_REVIEW_TRUST.json', '/etc/xuanjun-customer-center/TARGET_ACCEPTANCE.json')
        objects = {}
        for name in paths:
            try:
                s = Path(name).lstat()
                objects[name] = {'uid': s.st_uid, 'mode': oct(stat.S_IMODE(s.st_mode)), 'symlink': stat.S_ISLNK(s.st_mode)}
            except FileNotFoundError:
                objects[name] = 'ABSENT'
        return {'state': 'INSPECTED', 'objects': objects, 'production_mutations': 0}
    root = validate_bundle()
    # No paths or environment supplied by the Runner reach the reviewed module.
    sys.path.insert(0, str(root))
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from scripts import pr122_customer_release as release
        if action == 'plan':
            result = release.plan(root)
        elif action == 'apply':
            control = secure(Path('/etc/xuanjun-customer-center/CHANNEL_ACTION.json'))
            need(not control.stat().st_mode & 0o077)
            c = json.loads(control.read_bytes())
            need(set(c) == {'action', 'approval_comment_id'} and c['action'] == 'apply'
                 and type(c['approval_comment_id']) is int and c['approval_comment_id'] > 0)
            result = release.apply(root, c['approval_comment_id'])
        else:
            result = release.rollback()
    # Do not expose provider/config data or raw Python exceptions into Actions logs.
    return {k: result[k] for k in ('state', 'transaction', 'manifest_sha256', 'source_commit', 'production_changes') if k in result}


def revoke():
    need(os.environ.get('SUDO_UID') != str(RUNNER_UID))
    expected = policy('githubrunner')
    need(secure(POLICY).read_bytes() == expected)
    POLICY.unlink()
    subprocess.run(['/usr/sbin/visudo', '-c'], check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    return {'state': 'CHANNEL_REVOKED', 'customer_runtime_changed': False, 'evidence_preserved': True}


def main():
    os.umask(0o077)
    need(os.geteuid() == 0 and os.uname().nodename == HOST and len(sys.argv) == 2)
    action = sys.argv[1]
    if action == '--grant':
        result = grant()
    elif action == '--revoke':
        result = revoke()
    else:
        # Global caller/privileged-operation lock; original release also takes its own lock.
        lock = secure(BASE / 'channel.py')
        with lock.open('rb') as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = dispatch(action)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        print('{"state":"HOLD","retry_allowed":false,"raw_error_redacted":true}')
        raise SystemExit(2) from None
