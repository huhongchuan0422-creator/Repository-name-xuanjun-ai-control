"""Root-owned release verifier and isolated runtime entry."""
from __future__ import print_function

import argparse
import hashlib
import json
import os
import stat
import sys
import types


REQUIRED = ('scripts/task_supervisor.py',
            'scripts/task_supervisor_runtime.py',
            'scripts/task_supervisor_runtime_entry.py')


def _read_regular(path, trusted_uid, max_bytes):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != trusted_uid
                or info.st_mode & 0o022 or info.st_nlink != 1
                or info.st_size > max_bytes):
            raise ValueError('HOLD_UNTRUSTED_RELEASE_FILE')
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk); total += len(chunk)
            if total > max_bytes:
                raise ValueError('HOLD_RELEASE_FILE_LIMIT')
        return b''.join(chunks)
    finally:
        os.close(fd)


def _trusted_directory(path, trusted_uid):
    info = os.lstat(path)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != trusted_uid
            or info.st_mode & 0o022):
        raise ValueError('HOLD_UNTRUSTED_RELEASE_DIRECTORY')


def verify_release(manifest_path, manifest_sha256, trusted_uid=0):
    root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    _trusted_directory(root, trusted_uid)
    _trusted_directory(os.path.join(root, 'scripts'), trusted_uid)
    if os.path.lexists(os.path.join(root, 'scripts', '__pycache__')):
        raise ValueError('HOLD_RELEASE_BYTECODE_CACHE_FORBIDDEN')
    raw = _read_regular(manifest_path, trusted_uid, 65536)
    if hashlib.sha256(raw).hexdigest() != manifest_sha256:
        raise ValueError('HOLD_RELEASE_MANIFEST_DIGEST')
    value = json.loads(raw.decode('utf-8', 'strict'))
    if (not isinstance(value, dict) or set(value) != {'schema', 'files'}
            or value['schema'] != 1 or not isinstance(value['files'], dict)
            or set(value['files']) != set(REQUIRED)):
        raise ValueError('HOLD_RELEASE_MANIFEST_SCHEMA')
    contents = {}
    for relative in REQUIRED:
        expected = value['files'][relative]
        if (not isinstance(expected, str) or len(expected) != 64
                or any(c not in '0123456789abcdef' for c in expected)):
            raise ValueError('HOLD_RELEASE_MANIFEST_SCHEMA')
        contents[relative] = _read_regular(
            os.path.join(root, relative), trusted_uid, 1024 * 1024)
        actual = hashlib.sha256(contents[relative]).hexdigest()
        if actual != expected:
            raise ValueError('HOLD_RELEASE_SOURCE_DIGEST')
    return root, contents


def _load_verified(name, path, raw):
    module = types.ModuleType(name)
    module.__file__ = path
    module.__package__ = ''
    sys.modules[name] = module
    try:
        exec(compile(raw, path, 'exec'), module.__dict__)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--release-manifest', required=True)
    parser.add_argument('--release-manifest-sha256', required=True)
    args, _ = parser.parse_known_args()
    root, contents = verify_release(args.release_manifest,
                                    args.release_manifest_sha256)
    scripts = os.path.join(root, 'scripts')
    _load_verified('task_supervisor', os.path.join(scripts,
        'task_supervisor.py'), contents['scripts/task_supervisor.py'])
    runtime = _load_verified('task_supervisor_runtime', os.path.join(scripts,
        'task_supervisor_runtime.py'),
        contents['scripts/task_supervisor_runtime.py'])
    runtime.main()


if __name__ == '__main__':
    main()
