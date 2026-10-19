"""Descriptor-only bootstrap of explicitly pinned recovery and reviewed runtime."""
import hashlib
import os
import stat
import types


def load(path, digest):
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.strip('/').split('/')[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise RuntimeError('BOOTSTRAP_PARENT')
        out = os.open(path.rsplit('/', 1)[1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    finally:
        os.close(fd)
    try:
        before = os.fstat(out)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_nlink != 1 or before.st_mode & 0o022:
            raise RuntimeError('BOOTSTRAP_FILE')
        raw = os.read(out, 1048577)
        after = os.fstat(out)
        if (len(raw) > 1048576 or len(raw) != before.st_size or
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) or
                hashlib.sha256(raw).hexdigest() != digest):
            raise RuntimeError('BOOTSTRAP_SHA_OR_RACE')
    finally:
        os.close(out)
    module = types.ModuleType('_p2_pinned_' + path.rsplit('/', 1)[1].replace('.', '_'))
    module.__file__ = path
    exec(compile(raw, path, 'exec'), module.__dict__)
    return module
