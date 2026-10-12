#!/bin/bash
set -euo pipefail
test "$(id -u)" = 0 || { echo STOP_ROOT_REQUIRED; exit 2; }
test "$(hostname -s)" = iZd7oeikknn1z21sq6ji6zZ || { echo STOP_WRONG_HOST; exit 2; }
MODE="${1:-}"
case "$MODE" in --install|--rollback) ;; *) echo USAGE_INSTALL_OR_ROLLBACK; exit 2 ;; esac
H=/usr/local/sbin/xuanjun-uk-install-audit
P=/etc/sudoers.d/xuanjun-uk-dev-admin-root
Q=/etc/sudoers.d/xuanjun-uk-install-audit
for path in /usr /usr/local /usr/local/sbin /etc /etc/sudoers.d; do
    test ! -L "$path" && test -d "$path"
    test "$(stat -c '%U' "$path")" = root
done
if test "$MODE" = --rollback; then
    for path in "$H" "$P" "$Q"; do
        test -f "$path" && test ! -L "$path"
        test "$(stat -c '%U' "$path")" = root
    done
    echo "1fa4bf89868de245a82e1a7a22ae6035acd1975b42de3252197b68d08fa676c8  $H" | sha256sum -c -
    echo "a7d9c46d1275ead64fdc7c64099fad5fb38fe41dc414027f85e47d8209a1cb11  $P" | sha256sum -c -
    echo "f2b2a58dad3b3bc5a51d0d0875fa9fa968c7ff94c97004f7ba615a7b3adac1cf  $Q" | sha256sum -c -
    /usr/sbin/visudo -c
    rm -f "$P" "$Q" "$H"
    /usr/sbin/visudo -c
    echo ROOT_CAPABILITY_POLICY_REMOVED_EXISTING_PROCESSES_NOT_TERMINATED
    exit 0
fi
for path in "$H" "$P" "$Q"; do
    test ! -e "$path" && test ! -L "$path" || { echo STOP_EXISTING_TARGET; exit 3; }
done
getent passwd xuanjun_dev >/dev/null
getent passwd githubrunner >/dev/null
test -x /usr/sbin/visudo
STAGE=$(mktemp -d /run/xuanjun-root-capability-XXXXXX)
chmod 700 "$STAGE"
COMMITTED=0
cleanup() {
    if test "$COMMITTED" = 0; then
        rm -f "$H" "$P" "$Q"
    fi
    rm -rf "$STAGE"
}
trap cleanup EXIT
cat > "$STAGE/audit.py" <<'XJ_AUDIT_PYTHON'
#!/usr/bin/python3 -I
"""Fixed read-only UK installation bindings. No credential content or inference."""
import argparse
import glob
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
        if (code_hash and os.path.realpath(path) == path
                and stat.S_ISREG(info.st_mode) and info.st_size <= 536870912):
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
    roots = (HOME_ROOT + '/.openclaw', HOME_ROOT + '/.codex',
             HOME_ROOT + '/.local', HOME_ROOT + '/.config',
             '/root/.openclaw', '/root/.codex')
    for root in roots:
        if not os.path.isdir(root) or os.path.islink(root):
            continue
        for directory, children, files in os.walk(root, followlinks=False):
            children[:] = sorted(x for x in children if x not in
                                  ('.git', '.ssh', '.aws', '__pycache__', 'sessions',
                                   'logs', 'tmp', 'npm', 'node_modules', '.cache',
                                   'cache', 'tools', 'vendor', 'plugin-captures'))
            total += len(children) + len(files)
            if total > 20000:
                result['complete'] = False
                break
            for name in sorted(files):
                if name in AUTH_NAMES:
                    result['auth_metadata_only'].append(metadata(os.path.join(directory, name)))
    patterns = (
        HOME_ROOT + '/.openclaw/npm/projects/*/node_modules/@openai/codex-linux-x64/vendor/*/bin/codex',
        HOME_ROOT + '/.openclaw/tools/*/codex',
        HOME_ROOT + '/.local/bin/codex', HOME_ROOT + '/.local/bin/gh',
        '/usr/bin/codex', '/usr/local/bin/codex', '/usr/bin/gh', '/usr/local/bin/gh')
    paths = set()
    for pattern in patterns:
        paths.update(glob.glob(pattern))
    for path in sorted(paths):
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

XJ_AUDIT_PYTHON
echo "1fa4bf89868de245a82e1a7a22ae6035acd1975b42de3252197b68d08fa676c8  $STAGE/audit.py" | sha256sum -c -
/usr/bin/python3 -I -B "$STAGE/audit.py" --self-test
printf '%s
' 'xuanjun_dev ALL=(root) NOPASSWD: ALL' > "$STAGE/dev-policy"
printf '%s
' 'githubrunner ALL=(root) NOPASSWD: /usr/local/sbin/xuanjun-uk-install-audit ""' > "$STAGE/audit-policy"
chmod 440 "$STAGE/dev-policy" "$STAGE/audit-policy"
/usr/sbin/visudo -cf "$STAGE/dev-policy"
/usr/sbin/visudo -cf "$STAGE/audit-policy"
/usr/sbin/visudo -c
/usr/bin/install -o root -g root -m 0555 "$STAGE/audit.py" "$H"
/usr/bin/install -o root -g root -m 0440 "$STAGE/dev-policy" "$P"
/usr/bin/install -o root -g root -m 0440 "$STAGE/audit-policy" "$Q"
/usr/sbin/visudo -c
test "$(/usr/sbin/runuser -u xuanjun_dev -- /usr/bin/sudo -n /usr/bin/id -u)" = 0
/usr/sbin/runuser -u githubrunner -- /usr/bin/sudo -n "$H" > "$STAGE/result.json"
/usr/bin/python3 -I -B - "$STAGE/result.json" <<'XJ_VERIFY_JSON'
import json,sys
with open(sys.argv[1]) as f:d=json.load(f)
assert d['scope']=='READ_ONLY_NO_MODEL_NO_INSTALL_NO_CREDENTIAL_CONTENT'
print('DEV_ADMIN_ROOT_SUDO=INSTALLED_AND_VERIFIED')
print('RUNNER_ROOT_AUDIT=INSTALLED_AND_VERIFIED')
print('ROOT_AUDIT_BIN_SHA256=1fa4bf89868de245a82e1a7a22ae6035acd1975b42de3252197b68d08fa676c8')
print('P2_INSTALL=NO; P3_PASS=NO; MODEL_INFERENCE=NO')
print(json.dumps(d,sort_keys=True))
XJ_VERIFY_JSON
COMMITTED=1
