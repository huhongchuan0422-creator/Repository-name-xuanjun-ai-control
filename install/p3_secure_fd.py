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


def _directory(fd, expected_uid, sticky_root=False):
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, expected_uid):
        raise PermissionError('UNTRUSTED_DIRECTORY_OWNER')
    if info.st_mode & 0o022:
        if not (sticky_root and info.st_uid == 0 and info.st_mode & stat.S_ISVTX):
            raise PermissionError('WRITABLE_DIRECTORY')
    return info


def open_absolute_dir(path, expected_uid):
    """Pin every component from / without following symlinks.

    Root-owned sticky ancestors are permitted, but each subsequently opened
    directory must be owned by root or the expected UID. ACLs require separate
    platform verification and are not assessed here.
    """
    if not isinstance(path, str) or not path.startswith('/'):
        raise ValueError('ABSOLUTE_DIRECTORY_REQUIRED')
    parts = path.split('/')[1:]
    if any(part in ('', '.', '..') for part in parts):
        raise ValueError('UNSAFE_DIRECTORY')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _directory(fd, expected_uid, sticky_root=True)
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            _directory(fd, expected_uid, sticky_root=True)
        return fd
    except BaseException:
        os.close(fd)
        raise


def copy_member(source_root_fd, staging_root_fd, relative, expected_uid,
                expected_sha256, maximum=4*1024*1024):
    """Copy and verify through pinned fds; target staging must be private."""
    if not isinstance(relative, str) or relative.startswith('/'):
        raise ValueError('RELATIVE_PATH_REQUIRED')
    parts = relative.split('/')
    if any(p in ('', '.', '..') for p in parts):
        raise ValueError('UNSAFE_PATH')
    src, dst = os.dup(source_root_fd), os.dup(staging_root_fd)
    try:
        _directory(src, expected_uid)
        target_info = _directory(dst, expected_uid)
        if target_info.st_uid != expected_uid or target_info.st_mode & 0o077:
            raise PermissionError('PRIVATE_STAGING_REQUIRED')
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=src)
            os.close(src); src = child
            _directory(src, expected_uid)
            try:
                os.mkdir(part, 0o700, dir_fd=dst)
                os.fsync(dst)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dst)
            os.close(dst); dst = child
            info = _directory(dst, expected_uid)
            if info.st_uid != expected_uid or info.st_mode & 0o077:
                raise PermissionError('PRIVATE_STAGING_REQUIRED')
        source = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=src)
        try:
            info = os.fstat(source)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != expected_uid or info.st_mode & 0o022
                    or info.st_size > maximum):
                raise PermissionError('UNTRUSTED_FILE')
            target = os.open(parts[-1], os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400, dir_fd=dst)
            try:
                digest, total = hashlib.sha256(), 0
                while True:
                    chunk = os.read(source, 65536)
                    if not chunk: break
                    total += len(chunk)
                    if total > maximum: raise ValueError('FILE_TOO_LARGE')
                    digest.update(chunk)
                    view = memoryview(chunk)
                    while view:
                        written = os.write(target, view)
                        if written <= 0: raise IOError('SHORT_WRITE')
                        view = view[written:]
                if digest.hexdigest() != expected_sha256:
                    raise ValueError('SOURCE_CHANGED_DURING_COPY')
                os.fsync(target)
                os.lseek(target, 0, os.SEEK_SET)
                check = hashlib.sha256()
                while True:
                    chunk = os.read(target, 65536)
                    if not chunk: break
                    check.update(chunk)
                out = os.fstat(target)
                if (check.hexdigest() != expected_sha256 or not stat.S_ISREG(out.st_mode)
                        or out.st_nlink != 1 or out.st_uid != expected_uid):
                    raise ValueError('STAGED_FILE_MISMATCH')
                os.fsync(dst)
            finally:
                os.close(target)
        finally:
            os.close(source)
    finally:
        os.close(src); os.close(dst)
