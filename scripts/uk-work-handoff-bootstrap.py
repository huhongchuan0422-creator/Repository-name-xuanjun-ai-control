#!/usr/bin/env python3
"""Copy one exact UK candidate into a root-owned data return directory.

No patch execution, import of development code, sudo installation, DB operation,
service change, credential copy, model request or production release.
"""
import hashlib
import json
import os
import pwd
import socket
import stat
import sys
import uuid

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
FROZEN_COMMIT = '4bf32c009c433416ac1ef7ff7038fd4dcd29d7d2'
PATCH_HASH = '82e81c2bbca62ff28dddab409f66ee53106283a1ebb3a9271c5c89b38e11aac0'
OWNER_REPORTED_MANIFEST_HASH = '7a721baadf570decf6fae72747394e84fdac29fe1432fcef4f44a4bd85bf9eaf'
SOURCE = '/home/xuanjun_dev/xuanjun-uk-dev-20261011/integration-ab.patch'
BRIDGE = '/var/lib/xuanjun-work-handoff'
MAX_PATCH = 262144


def read_frozen_source(path, owners, expected_hash):
    if not os.path.isabs(path) or os.path.normpath(path) != path:
        raise ValueError('NON_CANONICAL_SOURCE')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = path.strip('/').split('/')
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
            if os.fstat(parent).st_uid not in owners:
                raise ValueError('UNTRUSTED_SOURCE_PARENT')
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in owners:
            raise ValueError('UNTRUSTED_SOURCE_FILE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(MAX_PATCH + 1)
        after = os.fstat(fd)
        if (not raw or len(raw) > MAX_PATCH or info.st_size != after.st_size
                or info.st_mtime_ns != after.st_mtime_ns):
            raise ValueError('UNSTABLE_OR_OVERSIZED_SOURCE')
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            raise ValueError('FROZEN_PATCH_HASH_MISMATCH')
        raw.decode('utf-8')
        return raw
    finally:
        os.close(fd)


def open_root_directory(path, gid):
    # Every ancestor is held by fd and must be root-owned and not writable by
    # group/others. Only the final directory may be created, without symlinks.
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = path.strip('/').split('/')
        for index, part in enumerate(parts):
            created = False
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            except FileNotFoundError:
                if index != len(parts) - 1:
                    raise ValueError('BRIDGE_PARENT_MISSING')
                os.mkdir(part, 0o750, dir_fd=parent)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                created = True
            info = os.fstat(child)
            if info.st_uid != 0 or info.st_mode & 0o022:
                os.close(child)
                raise ValueError('UNSAFE_ROOT_BRIDGE')
            if index == len(parts) - 1:
                if created:
                    os.fchown(child, 0, gid)
                    os.fchmod(child, 0o750)
                    os.fsync(parent)
                elif info.st_gid != gid or stat.S_IMODE(info.st_mode) != 0o750:
                    os.close(child)
                    raise ValueError('EXISTING_BRIDGE_POLICY_MISMATCH')
            os.close(parent)
            parent = child
        return os.dup(parent)
    finally:
        os.close(parent)


def write_once(directory_fd, raw, uid, gid):
    name = 'candidate.patch'
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    except FileNotFoundError:
        fd = None
    if fd is not None:
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_gid != gid
                    or stat.S_IMODE(info.st_mode) != 0o640):
                raise ValueError('EXISTING_PATCH_POLICY_MISMATCH')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                if stream.read(len(raw) + 1) != raw:
                    raise ValueError('EXISTING_PATCH_CONTENT_MISMATCH')
        finally:
            os.close(fd)
        return
    temporary = '.candidate-' + uuid.uuid4().hex
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory_fd)
    try:
        os.fchown(fd, uid, gid)
        os.fchmod(fd, 0o640)
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
        # Hard-link publication is atomic and refuses an existing destination.
        os.link(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                follow_symlinks=False)
        os.fsync(directory_fd)
    finally:
        os.close(fd)
        os.unlink(temporary, dir_fd=directory_fd)
        os.fsync(directory_fd)


def main():
    if os.geteuid() != 0 or len(sys.argv) != 1 or socket.gethostname().split('.')[0] != HOST:
        raise SystemExit('STOP_WRONG_UK_HOST_OR_ROOT_OR_ARGUMENTS')
    dev, runner = pwd.getpwnam('xuanjun_dev'), pwd.getpwnam('githubrunner')
    # Check the source before creating any directories; never import its code.
    raw = read_frozen_source(SOURCE, {0, dev.pw_uid}, PATCH_HASH)
    for path in (BRIDGE, BRIDGE + '/returns', BRIDGE + '/returns/' + FROZEN_COMMIT):
        fd = open_root_directory(path, runner.pw_gid)
        try:
            if path.endswith('/' + FROZEN_COMMIT):
                write_once(fd, raw, 0, runner.pw_gid)
        finally:
            os.close(fd)
    print(json.dumps({'server': 'UK', 'handoff': 'FROZEN_PATCH_BRIDGE_INITIALIZED',
                      'owner_reported_commit': FROZEN_COMMIT, 'patch_sha256': PATCH_HASH,
                      'bytes': len(raw), 'owner_reported_manifest_sha256': OWNER_REPORTED_MANIFEST_HASH,
                      'manifest_verified': False, 'production_deployment': False,
                      'db_mutation': False, 'model_invocation': False, 'service_restart': False}))


if __name__ == '__main__':
    main()
