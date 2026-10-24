"""Exact 42-file source reader for an independently verified release tree.

Reading source never enrolls a maintenance caller or grants an installation.
Every directory component and final file is opened without following links.
"""
import os
import stat

from successor_contract import Hold, decode, require, sha


def _identity(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
            s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def _read_one(root_fd, name, length, digest):
    parts = name.split('/')
    require(parts and all(p not in ('', '.', '..') for p in parts),
            'SOURCE_PATH_SCOPE')
    opened = []
    fd = root_fd
    try:
        for part in parts[:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                         dir_fd=fd)
            opened.append(fd)
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                       dir_fd=fd)
        opened.append(leaf)
        before = os.fstat(leaf)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                type(length) is int and 0 <= length <= 2 * 1024 * 1024 and
                before.st_size == length, 'SOURCE_FILE_IDENTITY')
        chunks = []
        left = length
        while left:
            part = os.read(leaf, min(left, 65536))
            require(bool(part), 'SOURCE_SHORT_READ')
            chunks.append(part)
            left -= len(part)
        after = os.fstat(leaf)
        named = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
        require(_identity(before) == _identity(after) == _identity(named),
                'SOURCE_CHANGED_DURING_READ')
        raw = b''.join(chunks)
        require(sha(raw) == digest, 'SOURCE_SHA_CHANGED')
        return raw
    except (OSError, ValueError, TypeError):
        raise Hold('SOURCE_UNAVAILABLE_OR_CHANGED') from None
    finally:
        for child in reversed(opened):
            os.close(child)


def read_exact_42(root, manifest_raw):
    manifest = decode(manifest_raw)
    rows = manifest.get('files')
    require(manifest.get('schema') == 'B5_RUNTIME_SOURCE_V1' and
            type(rows) is list and len(rows) == 42, 'SOURCE_MANIFEST_SCOPE')
    names = [x.get('path') for x in rows]
    require(all(type(name) is str for name in names) and
            len(set(names)) == 42, 'SOURCE_DUPLICATE_PATH')
    require(type(root) is str and os.path.isabs(root), 'SOURCE_ROOT_SCOPE')
    opened = []
    try:
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        opened.append(fd)
        for component in root.split('/')[1:]:
            require(component not in ('', '.', '..'), 'SOURCE_ROOT_SCOPE')
            fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                         dir_fd=fd)
            opened.append(fd)
    except (OSError, Hold):
        for item in reversed(opened):
            os.close(item)
        raise Hold('SOURCE_ROOT_UNAVAILABLE') from None
    try:
        return {row['path']: _read_one(fd, row['path'], row['bytes'],
                                       row['sha256']) for row in rows}
    finally:
        for item in reversed(opened):
            os.close(item)
