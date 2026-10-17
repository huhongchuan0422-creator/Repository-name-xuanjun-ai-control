"""Render, never execute, the reviewed Owner installation command.
Input hashes come from the local frozen build. Commit is the externally verified
immutable source commit; rendered bytes must be included in final Task5 review.
"""
import argparse
import hashlib
from pathlib import Path
import re
import shlex

REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
REMOTE = 'scripts/pr122_account_admission/domestic-install-package'
FILES = ('domestic_bootstrap.py', 'domestic-bootstrap-manifest.json', 'domestic-readonly-helper.py')


def render(commit, folder, action="install"):
    if action not in ("install", "verify", "rollback"):
        raise ValueError("FIXED_ACTION_REQUIRED")
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('IMMUTABLE_COMMIT_REQUIRED')
    root = Path(folder)
    lines = ["sudo -H /bin/bash <<'XUANJUN_REVIEWED_INSTALL'", 'set -euo pipefail',
             'umask 077', '[ "$(/usr/bin/id -u)" = 0 ]',
             '[ "$(/bin/hostname)" = iZvt5t8tlrm8oiZ ]',
             '[ "${SUDO_UID-}" != 1002 ]',
             'd=/root/pr122-readonly-admission-inputs',
             ]
    if action == 'install':
        lines += ['[ ! -e "$d" ] && [ ! -L "$d" ]', '/bin/mkdir -m 700 -- "$d"']
    for name in FILES:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('REGULAR_BUILD_FILE_REQUIRED')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        url = f'https://raw.githubusercontent.com/{REPO}/{commit}/{REMOTE}/{name}'
        # No remote data is executed before its final reviewed SHA256 matches.
        if action == 'install':
            lines += [f"/usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C /usr/bin/curl --disable --noproxy '*' --fail --silent --show-error --proto =https --tlsv1.2 --max-time 60 --max-filesize 2000000 --output \"$d/{name}\" {shlex.quote(url)}"]
        lines += [f'printf "%s\\n" {shlex.quote(digest + "  /root/pr122-readonly-admission-inputs/" + name)} | /usr/bin/sha256sum --check --status']
        if action == 'install':
            lines += [f'/bin/chmod 400 -- "$d/{name}"']
    lines += ['# Requires final Task5 and Owner exact-file authorization for this action.']
    if action == 'install':
        lines += ['/usr/bin/python3 -I -B "$d/domestic_bootstrap.py" plan']
    lines += [f'/usr/bin/python3 -I -B "$d/domestic_bootstrap.py" {action}',
              'XUANJUN_REVIEWED_INSTALL', '']
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--commit', required=True)
    p.add_argument('--action', choices=('install','verify','rollback'), default='install')
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    text = render(a.commit, a.package, a.action)
    with a.output.open('x') as f:
        f.write(text)


if __name__ == '__main__':
    main()
