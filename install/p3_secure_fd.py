"""Linux fd-relative read primitive; not integrated into legacy installer.

A caller supplies a pre-opened, independently trusted root directory descriptor
and expected owner UID. It must additionally establish ancestor ownership/ACLs,
secure its root descriptor, and use the returned bytes (not reopen the path).
"""
import hashlib
import os
import stat


def read_member(root_fd, relative, expected_uid, expected_sha256, maximum=4*1024*1024):
    if not isinstance(relative, str) or not relative or relative.startswith('/'):
        raise ValueError('RELATIVE_PATH_REQUIRED')
    parts = relative.split('/')
    if any(p in ('', '.', '..') for p in parts):
        raise ValueError('UNSAFE_PATH')
    if not hasattr(os, 'O_NOFOLLOW') or not hasattr(os, 'O_DIRECTORY'):
        raise RuntimeError('POSIX_NOFOLLOW_REQUIRED')
    current = os.dup(root_fd)
    try:
        def directory_ok(fd):
            info = os.fstat(fd)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != expected_uid or info.st_mode & 0o022:
                raise PermissionError('UNTRUSTED_DIRECTORY')
        directory_ok(current)
        for part in parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = nxt
            directory_ok(current)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != expected_uid
                    or info.st_mode & 0o022 or info.st_size > maximum):
                raise PermissionError('UNTRUSTED_FILE')
            chunks, count = [], 0
            while True:
                data = os.read(fd, min(65536, maximum + 1 - count))
                if not data:
                    break
                count += len(data)
                if count > maximum:
                    raise ValueError('FILE_TOO_LARGE')
                chunks.append(data)
            content = b''.join(chunks)
            if hashlib.sha256(content).hexdigest() != expected_sha256:
                raise ValueError('FILE_HASH_MISMATCH')
            return content
        finally:
            os.close(fd)
    finally:
        os.close(current)
