#!/usr/bin/python3 -I
"""Fixed read-only UK installation bindings. No credential content or inference."""
import argparse
import hashlib
import json
import os
import pwd
import re
import socket
import sqlite3
import stat
import subprocess

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
HOME_ROOT = '/home/xuanjun_dev'
DB = HOME_ROOT + '/uk-stage1-minimal/state.sqlite'
UNITS = ('xuanjun-uk-stage1-minimal.service', 'xuanjun-uk-openclaw.service',
         'xuanjun-uk-owner-dashboard.service', 'xuanjun-uk-owner-callback.service',
         'xj-uk-domestic-customer-tunnel.service')
AUTH_NAMES = frozenset(('auth.json', 'auth-profiles.json', 'credentials.json'))


def metadata(path, code_hash=False):
    result = {'path': path}
    try:
        info = os.lstat(path)
        result.update(uid=info.st_uid, gid=info.st_gid,
                      mode=oct(stat.S_IMODE(info.st_mode)),
                      symlink=stat.S_ISLNK(info.st_mode),
                      regular=stat.S_ISREG(info.st_mode), size=info.st_size)
        if code_hash and stat.S_ISREG(info.st_mode) and info.st_size <= 100000000:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as stream:
                opened = os.fstat(stream.fileno())
                if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                    raise ValueError('changed file')
                digest = hashlib.sha256()
                for part in iter(lambda: stream.read(1048576), b''):
                    digest.update(part)
                ended = os.fstat(stream.fileno())
                if (ended.st_size, ended.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns):
                    raise ValueError('changed file')
                result['sha256'] = digest.hexdigest()
    except (OSError, ValueError):
        result['status'] = 'UNAVAILABLE_OR_CHANGED'
    return result


def bounded_runtime_inventory():
    result = {'executables': [], 'auth_metadata_only': [], 'complete': True}
    total = 0
    for root in (HOME_ROOT + '/.openclaw', HOME_ROOT + '/.codex',
                 HOME_ROOT + '/.local', HOME_ROOT + '/.config'):
        if not os.path.isdir(root) or os.path.islink(root):
            continue
        for directory, children, files in os.walk(root, followlinks=False):
            children[:] = sorted(x for x in children if x not in
                                  ('.git', '.ssh', '.aws', '__pycache__', 'sessions', 'logs'))
            total += len(children) + len(files)
            if total > 50000:
                result['complete'] = False
                return result
            for name in sorted(files):
                path = os.path.join(directory, name)
                if name in ('codex', 'gh'):
                    result['executables'].append(metadata(path, code_hash=True))
                elif name in AUTH_NAMES:
                    result['auth_metadata_only'].append(metadata(path))
    for path in ('/usr/bin/codex', '/usr/local/bin/codex', '/usr/bin/gh',
                 '/usr/local/bin/gh'):
        if os.path.lexists(path):
            result['executables'].append(metadata(path, code_hash=True))
    return result


def ledger_binding():
    result = {'metadata': metadata(DB)}
    if os.path.realpath(DB) != DB or not result['metadata'].get('regular'):
        result['status'] = 'HOLD_UNSAFE_OR_MISSING_CANONICAL_DB'
        return result
    try:
        # The already-running canonical DB has its own WAL/SHM. Never create
        # missing SQLite sidecars as part of a read-only installation probe.
        if os.path.exists(DB + '-wal') and not os.path.exists(DB + '-shm'):
            raise ValueError('WAL has no existing SHM')
        db = sqlite3.connect('file:' + DB + '?mode=ro', uri=True, timeout=3)
        try:
            db.execute('PRAGMA query_only=ON')
            result['task_columns'] = [r[1] for r in db.execute('PRAGMA table_info(tasks)')]
            result['states'] = {r[0]: r[1] for r in db.execute(
                'SELECT state,count(*) FROM tasks GROUP BY state')}
            result['leased_rows'] = db.execute(
                'SELECT count(*) FROM tasks WHERE lease_owner IS NOT NULL').fetchone()[0]
            result['status'] = 'READ_ONLY_BINDING_OBSERVED_NOT_QUIESCENCE_PROOF'
        finally:
            db.close()
    except (sqlite3.Error, ValueError, OSError):
        result['status'] = 'HOLD_CANONICAL_DB_BINDING_UNAVAILABLE'
    return result


def collect():
    result = {'scope': 'READ_ONLY_NO_MODEL_NO_INSTALL_NO_CREDENTIAL_CONTENT',
              'runtime': bounded_runtime_inventory(), 'ledger': ledger_binding(),
              'units': {}, 'tls_metadata_only': []}
    for unit in UNITS:
        p = subprocess.run(['/usr/bin/systemctl', 'show', unit,
                            '--property=ActiveState,MainPID,ControlGroup,User,Group,WorkingDirectory'],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=8, check=False)
        result['units'][unit] = p.stdout.decode('utf-8', 'replace').strip()
    for directory in ('/etc/letsencrypt/live', '/etc/nginx/ssl', '/etc/pki/tls/certs'):
        if not os.path.isdir(directory):
            continue
        for parent, children, files in os.walk(directory, followlinks=False):
            if parent.count(os.sep) - directory.count(os.sep) >= 2:
                children[:] = []
            for name in files[:200]:
                if name.endswith(('.pem', '.crt', '.key')):
                    result['tls_metadata_only'].append(metadata(os.path.join(parent, name)))
    result['installation_admission'] = 'HOLD_PENDING_FINAL_TRANSACTION_AND_REVIEW'
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        assert HOST == 'iZd7oeikknn1z21sq6ji6zZ'
        assert DB == '/home/xuanjun_dev/uk-stage1-minimal/state.sqlite'
        assert all(re.fullmatch(r'[a-z0-9.-]+\.service', x) for x in UNITS)
        assert not metadata('/nonexistent-p2-preflight-fixture').get('regular')
        print('PREFLIGHT_STATIC_SELF_TEST_PASS_NO_HOST_ACCEPTANCE')
        return
    if os.geteuid() != 0 or socket.gethostname().split('.')[0] != HOST:
        raise SystemExit('STOP_FIXED_UK_ROOT_READ_SCOPE')
    pwd.getpwnam('xuanjun_dev')
    print(json.dumps(collect(), sort_keys=True))


if __name__ == '__main__':
    main()
