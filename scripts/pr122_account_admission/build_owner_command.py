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
FILES = ('domestic_bootstrap.py', 'domestic-bootstrap-manifest.json', 'domestic-readonly-helper.py', 'domestic_owner.py')


ACTIONS = ('install', 'enroll', 'execute', 'export', 'verify', 'rollback')


def render(commit, folder, action="install", *, comment_id=None, body_sha256=None, custody_sha256=None):
    stages = action.split(',')
    if not stages or len(set(stages)) != len(stages) or any(x not in ACTIONS for x in stages):
        raise ValueError("FIXED_ACTION_REQUIRED")
    if 'install' in stages and stages[0] != 'install':
        raise ValueError('INSTALL_MUST_BE_FIRST')
    if 'rollback' in stages and stages[-1] != 'rollback':
        raise ValueError('ROLLBACK_MUST_BE_LAST')
    if 'enroll' in stages and 'execute' in stages and stages.index('enroll') > stages.index('execute'):
        raise ValueError('ENROLL_BEFORE_EXECUTE')
    if 'enroll' in stages:
        if type(comment_id) is not int or comment_id <= 0 or any(type(x) is not str or not re.fullmatch('[0-9a-f]{64}', x) for x in (body_sha256, custody_sha256)):
            raise ValueError('EXACT_REAL_APPROVAL_INPUTS_REQUIRED')
    elif any(x is not None for x in (comment_id,body_sha256,custody_sha256)):
        raise ValueError('UNUSED_APPROVAL_INPUTS')
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('IMMUTABLE_COMMIT_REQUIRED')
    root = Path(folder)
    lines = ["sudo -H /bin/bash <<'XUANJUN_REVIEWED_INSTALL'", 'set -euo pipefail',
             'umask 077', '[ "$(/usr/bin/id -u)" = 0 ]',
             '[ "$(/bin/hostname)" = iZvt5t8tlrm8oiZ ]',
             '[ "${SUDO_UID-}" != 1002 ]',
             'd=/root/pr122-readonly-admission-inputs',
             ]
    if 'install' in stages:
        lines += ['[ ! -e "$d" ] && [ ! -L "$d" ]', '/bin/mkdir -m 700 -- "$d"']
    for name in FILES:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('REGULAR_BUILD_FILE_REQUIRED')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        url = f'https://raw.githubusercontent.com/{REPO}/{commit}/{REMOTE}/{name}'
        # No remote data is executed before its final reviewed SHA256 matches.
        if 'install' in stages:
            lines += [f"/usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C /usr/bin/curl --disable --noproxy '*' --fail --silent --show-error --proto =https --tlsv1.2 --max-time 60 --max-filesize 2000000 --output \"$d/{name}\" {shlex.quote(url)}"]
        lines += [f'printf "%s\\n" {shlex.quote(digest + "  /root/pr122-readonly-admission-inputs/" + name)} | /usr/bin/sha256sum --check --status']
        if 'install' in stages:
            lines += [f'/bin/chmod 400 -- "$d/{name}"']
    lines += ['# Every listed stage requires its explicit final Task5/Owner scope; this renderer grants none.']
    for stage in stages:
        if stage == 'install':
            lines += ['/usr/bin/python3 -I -B "$d/domestic_bootstrap.py" plan']
        if stage in ('install','verify','rollback'):
            lines += [f'/usr/bin/python3 -I -B "$d/domestic_bootstrap.py" {stage}']
        elif stage == 'enroll':
            lines += [f'/usr/bin/python3 -I -B "$d/domestic_owner.py" enroll --comment-id {comment_id} --body-sha256 {body_sha256} --custody-sha256 {custody_sha256}']
        else:
            lines += [f'/usr/bin/python3 -I -B "$d/domestic_owner.py" {stage}']
    lines += ['XUANJUN_REVIEWED_INSTALL', '']
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--commit', required=True)
    p.add_argument('--action', default='install', help='Explicit comma-separated stages; default installs only')
    p.add_argument('--comment-id', type=int)
    p.add_argument('--body-sha256')
    p.add_argument('--custody-sha256')
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    text = render(a.commit, a.package, a.action, comment_id=a.comment_id, body_sha256=a.body_sha256, custody_sha256=a.custody_sha256)
    with a.output.open('x') as f:
        f.write(text)


if __name__ == '__main__':
    main()
