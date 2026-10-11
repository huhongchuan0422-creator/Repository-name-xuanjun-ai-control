#!/usr/bin/env python3
"""Receive a hash-bound maintenance patch as data; never execute or admit it."""
import base64
import hashlib
import json
import os
import pwd
import re
import socket
import stat
import sys

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
BASE_COMMIT = '85ad1d7224485f3c57298e71a429eb576b8d943d'
ROOT = '/var/lib/xuanjun-work-handoff/returns'
MAX_PATCH = 262144
INTEGRATED_FROZEN_COMMIT = '93d5b04ed1ced8042e3982125a486e0bd1d43ec8'
INTEGRATED_PATCH_HASH = 'efe8607e8d54bf083ae8e696b953ee18aeb4c390ab7bc746cd2d1d09ddc2e1a6'
OWNER_REPORTED_MANIFEST_HASH = '244a848aa322310a85a2bd0248908c079130cfa494a9dd3c17416eca768a41eb'
B_FROZEN_COMMIT = 'c49238abb9fa8a7fc90206d9d8308ac446f0988c'
B_APPROVED_PATCH_HASH = 'ab58ff792f18b2c8daff53699ab43dd3241a5ae53575c98aaa399cdb1231236b'
A_FROZEN_COMMIT = '85dd740d94f6c8d24979764dcbd40f3c48faabad'
A_APPROVED_PATCH_HASH = '117fbab62fca0ed459e4c45c1b8174f9819b511fbef059ec327f1ab4fc458b03'
EXACT = {
    'A': frozenset(['stage1/codex_worker.py', 'stage1/codex_app_server_worker.py',
                    'stage1/development_loop.py', 'stage1/development_pipeline.py',
                    'stage1/execution_ledger.py', 'stage1/development_service.py']),
    'B': frozenset(['stage1/owner_dashboard.py', 'stage1/owner_dashboard.html',
                    'stage1/owner_approval_dispatch.py', 'stage1/owner_update_router.py',
                    'stage1/uk_owner_callback_core.py', 'stage1/telegram_owner_request_registry.py',
                    'stage1/owner_notification_outbox.py', 'stage1/uk_owner_notify_worker.py',
                    'stage1/telegram_owner_transport.py', 'stage1/owner_https.py'])}
SECRET = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|'
                    r'sk-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|'
                    r'(?i:bearer)\s+[A-Za-z0-9._-]{24,}|'
                    r'\b[0-9]{8,12}:[A-Za-z0-9_-]{30,}\b)')


def safe_path(path, owners):
    if not os.path.isabs(path) or os.path.normpath(path) != path:
        raise ValueError('NON_CANONICAL_PATH')
    current = '/'
    for part in path.strip('/').split('/'):
        current = os.path.join(current, part)
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or info.st_uid not in owners:
            raise ValueError('UNTRUSTED_PATH')
    return info


def read_patch(path, owners):
    safe_path(path, owners)
    # Hold each parent fd: a worker cannot redirect the read by replacing an
    # ancestor after the lstat checks. All opens forbid following symlinks.
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = path.strip('/').split('/')
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
            if os.fstat(parent).st_uid not in owners:
                raise ValueError('UNTRUSTED_PARENT')
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in owners:
            raise ValueError('UNTRUSTED_PATCH_FILE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(MAX_PATCH + 1)
        after = os.fstat(fd)
        if (info.st_size != after.st_size or info.st_mtime_ns != after.st_mtime_ns
                or len(raw) > MAX_PATCH or not raw):
            raise ValueError('PATCH_UNSTABLE_OR_TOO_LARGE')
        return raw
    finally:
        os.close(fd)


def allowed(node, path):
    if node == 'INTEGRATED':
        # Receipt of the exact Owner-pinned patch is not code-path admission.
        # Every returned path must be reviewed before applying or publishing.
        return bool(re.fullmatch(r'[A-Za-z0-9_./-]+', path))
    if path in EXACT[node]:
        return True
    if node == 'A':
        return bool(re.fullmatch(r'(?:stage1/test_(?:development|execution|codex)[a-z0-9_]*\.py|'
                                 r'scripts/uk-(?:dev|development|dispatcher|sqlite)[a-z0-9_-]*\.py)', path))
    return bool(re.fullmatch(r'(?:stage1/test_(?:owner|uk_owner|telegram_owner)[a-z0-9_]*\.py|'
                             r'scripts/uk-owner[a-z0-9_-]*\.py)', path))


def validate_patch(raw, node):
    if node not in EXACT and node != 'INTEGRATED':
        raise ValueError('UNKNOWN_NODE')
    if len(raw) > MAX_PATCH or b'\x00' in raw:
        raise ValueError('INVALID_PATCH_BYTES')
    text = raw.decode('utf-8')
    if SECRET.search(text):
        raise ValueError('POTENTIAL_SECRET_BLOCKED')
    paths = []
    for line in text.splitlines():
        if line.startswith('diff --git '):
            match = re.fullmatch(r'diff --git a/([A-Za-z0-9_./-]+) b/([A-Za-z0-9_./-]+)', line)
            if (not match or match.group(1) != match.group(2)
                    or not allowed(node, match.group(1))):
                raise ValueError('PATCH_SCOPE_NOT_APPROVED')
            path = match.group(1)
            if any(part in ('', '.', '..', '.git') for part in path.split('/')) or path in paths:
                raise ValueError('AMBIGUOUS_PATCH_PATH')
            paths.append(path)
        elif line.startswith(('--- ', '+++ ')):
            value = line[4:]
            if (not paths or value not in ('/dev/null', 'a/' + paths[-1], 'b/' + paths[-1])):
                raise ValueError('PATCH_HEADER_MISMATCH')
        elif line.startswith(('new file mode ', 'old mode ', 'new mode ', 'deleted file mode ')):
            mode = line.split()[-1]
            executable_data = (node == 'INTEGRATED' and mode == '100755'
                               and paths and paths[-1].endswith(('.py', '.sh')))
            if mode != '100644' and not executable_data:
                raise ValueError('PATCH_FILE_MODE_BLOCKED')
        elif line.startswith(('GIT binary patch', 'Binary files ', 'rename from ', 'rename to ',
                              'copy from ', 'copy to ')):
            raise ValueError('PATCH_FORMAT_BLOCKED')
    if not paths or '\n@@ ' not in text:
        raise ValueError('NO_TEXT_DIFF')
    return sorted(paths)


def collect(directory, node, owners, control_commit, expected_hash=None):
    if node == 'INTEGRATED' and expected_hash != INTEGRATED_PATCH_HASH:
        raise ValueError('INTEGRATED_FROZEN_HASH_REQUIRED')
    # Exactly one root-level .patch/.diff; never choose an arbitrary latest file.
    info = safe_path(directory, owners)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('WORKDIR_NOT_DIRECTORY')
    with os.scandir(directory) as entries:
        names = []
        for entry in entries:
            if len(names) >= 512:
                raise ValueError('WORKDIR_ENUMERATION_LIMIT')
            names.append(entry.name)
    names = sorted(name for name in names if re.fullmatch(r'[A-Za-z0-9_.-]+\.(patch|diff)', name))
    if not names:
        return {'node': node, 'status': 'NO_ROOT_LEVEL_PATCH', 'production_pass': False}
    if len(names) != 1:
        return {'node': node, 'status': 'AMBIGUOUS_PATCH_REQUIRES_SELECTION', 'production_pass': False}
    raw = read_patch(os.path.join(directory, names[0]), owners)
    if expected_hash is not None and hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError('FROZEN_PATCH_HASH_MISMATCH')
    paths = validate_patch(raw, node)
    return {'node': node, 'status': 'CANDIDATE_PATCH_COLLECTED',
            'control_commit': control_commit, 'expected_base_commit': BASE_COMMIT,
            'base_context_verified': False, 'patch_file': names[0], 'paths': paths,
            'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
            'patch_b64': base64.b64encode(raw).decode('ascii'),
            'qa': 'NOT_VERIFIED', 'security_audit': 'NOT_VERIFIED',
            'actual_model': 'NOT_VERIFIED', 'production_pass': False}


def main():
    if socket.gethostname().split('.')[0] != HOST or len(sys.argv) != 1:
        raise SystemExit('STOP_WRONG_HOST_OR_ARGUMENTS')
    if pwd.getpwuid(os.getuid()).pw_name != 'githubrunner':
        raise SystemExit('STOP_NOT_UK_RUNNER')
    commit = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise SystemExit('STOP_CONTROL_COMMIT_REQUIRED')
    owners = {0, os.getuid(), pwd.getpwnam('xuanjun_dev').pw_uid}
    for node, folder in [('INTEGRATED', INTEGRATED_FROZEN_COMMIT)]:
        try:
            result = collect(ROOT + '/' + folder, node, owners, commit,
                             INTEGRATED_PATCH_HASH)
            if result['status'] == 'CANDIDATE_PATCH_COLLECTED':
                result['owner_reported_frozen_commit'] = INTEGRATED_FROZEN_COMMIT
                result['owner_reported_manifest_sha256'] = OWNER_REPORTED_MANIFEST_HASH
                result['manifest_verified'] = False
                result['maintenance_path_admission'] = 'NOT_VERIFIED'
        except PermissionError:
            result = {'node': node, 'status': 'READ_ACCESS_NOT_VERIFIED'}
        except FileNotFoundError:
            result = {'node': node, 'status': 'WORKDIR_OR_PATCH_NOT_VISIBLE'}
        except ValueError as error:
            # Only our bounded machine codes, never arbitrary filesystem text.
            code = str(error)
            result = {'node': node, 'status': 'PATCH_REJECTED',
                      'reason': code if re.fullmatch(r'[A-Z_]{1,64}', code) else 'INVALID_PATCH'}
        except (UnicodeError, OSError):
            result = {'node': node, 'status': 'PATCH_REJECTED_NO_RAW_DIAGNOSTIC'}
        print('WORK_RESULT_' + node + '=' + json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
