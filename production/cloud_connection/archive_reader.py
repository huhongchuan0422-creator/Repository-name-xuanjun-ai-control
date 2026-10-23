"""Bounded uncompressed-tar member bytes; no extraction or SDK execution."""
import hashlib
import os
import stat
import tarfile
import time
from .queue import Hold
from .private_transfer import check, directory, stamp


def validate_archive(plan):
    check(type(plan) is dict and set(plan) == {'filename', 'identity', 'member_prefix', 'max_headers', 'max_read_bytes', 'sha256'}, 'ARCHIVE_PLAN')
    check(type(plan['sha256']) is str and len(plan['sha256']) == 64 and all(c in '0123456789abcdef' for c in plan['sha256']), 'ARCHIVE_SHA_FORMAT')
    name = plan['filename']
    check(type(name) is str and 0 < len(name) <= 128 and '/' not in name and name not in ('.', '..')
          and all(c.isalnum() or c in '._-' for c in name) and all(ord(c) < 128 for c in name), 'ARCHIVE_FILENAME')
    ident = plan['identity']
    check(type(ident) is list and len(ident) == 9 and all(type(x) is int and x >= 0 for x in ident)
          and stat.S_ISREG(ident[2]) and not ident[2] & 0o022 and ident[5] == 1
          and 1024 <= ident[6] <= 600 * 1024 * 1024, 'ARCHIVE_IDENTITY')
    check(plan['member_prefix'] in ('', './') and type(plan['member_prefix']) is str, 'ARCHIVE_PREFIX')
    check(type(plan['max_headers']) is int and 0 < plan['max_headers'] <= 65536
          and type(plan['max_read_bytes']) is int and 1024 <= plan['max_read_bytes'] <= 32 * 1024 * 1024, 'ARCHIVE_BUDGET')


class ArchiveView:
    """Every parser read/seek is bounded before allocation or disk access."""
    def __init__(self, fd, size, budget, deadline):
        self.fd, self.size, self.budget, self.deadline = fd, size, budget, deadline
        self.position, self.used = 0, 0
    def tell(self): return self.position
    def seek(self, offset, whence=0):
        check(type(offset) is int and whence in (0, 1, 2), 'ARCHIVE_SEEK')
        pos = offset if whence == 0 else (self.position if whence == 1 else self.size) + offset
        check(0 <= pos <= self.size and time.monotonic() < self.deadline, 'ARCHIVE_SEEK_BOUND')
        self.position = pos
        return pos
    def read(self, count=-1):
        check(type(count) is int and 0 <= count <= 65536 and self.used + count <= self.budget
              and time.monotonic() < self.deadline, 'ARCHIVE_READ_BOUND')
        count = min(count, self.size - self.position)
        parts = []
        while count:
            check(time.monotonic() < self.deadline, 'ARCHIVE_TIMEOUT')
            block = os.pread(self.fd, count, self.position)
            if not block: break
            parts.append(block); self.position += len(block); self.used += len(block); count -= len(block)
        return b''.join(parts)


def _read_archive(root, owner, items, plan, verify_whole):
    validate_archive(plan)
    check(plan['identity'][3] == owner, 'ARCHIVE_OWNER')
    check(type(items) is list and 0 < len(items) <= 5
          and len({x['ref'] for x in items}) == len(items)
          and len({x['relative_path'] for x in items}) == len(items)
          and all(type(x['bytes']) is int and 0 <= x['bytes'] <= 53969 for x in items)
          and sum(x['bytes'] for x in items) <= 93592, 'ARCHIVE_MEMBER_BOUND')
    wanted = {plan['member_prefix'] + x['relative_path']: x for x in items}
    paths = {x['relative_path'] for x in items}
    rootfd = directory(root, owner)
    fd = None
    try:
        fd = os.open(plan['filename'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=rootfd)
        before = os.fstat(fd)
        check(list(stamp(before)) == plan['identity'], 'ARCHIVE_CHANGED')
        deadline = time.monotonic() + 30
        if verify_whole:
            digest, offset = hashlib.sha256(), 0
            while offset < before.st_size:
                check(time.monotonic() < deadline, 'ARCHIVE_TIMEOUT')
                block = os.pread(fd, min(65536, before.st_size - offset), offset)
                check(bool(block), 'ARCHIVE_SHORT_READ')
                digest.update(block); offset += len(block)
            check(digest.hexdigest() == plan['sha256'], 'ARCHIVE_SHA')
        view = ArchiveView(fd, before.st_size, plan['max_read_bytes'], deadline)
        selected, count, seen = {}, 0, set()
        with tarfile.open(fileobj=view, mode='r:') as archive:
            while True:
                next_header = archive.offset
                member = archive.next()
                if member is None:
                    # next() may consume a malformed header before returning
                    # None. Verify from the known next-header boundary, not
                    # from its possibly advanced cursor.
                    view.seek(next_header)
                    check(view.size - next_header >= 1024 and (view.size - next_header) % 512 == 0, 'ARCHIVE_EOF')
                    break
                count += 1
                check(count <= plan['max_headers'] and time.monotonic() < view.deadline, 'ARCHIVE_HEADER_BOUND')
                name = member.name
                check(type(name) is str and len(name) <= 2048 and not name.startswith('/')
                      and '..' not in name.split('/'), 'ARCHIVE_MEMBER_PATH')
                normalized = name[2:] if name.startswith('./') else name
                components = normalized.rstrip('/').split('/')
                check(normalized in ('', '.') or all(x not in ('', '.', '..') for x in components), 'ARCHIVE_MEMBER_ALIAS')
                check(member.sparse is None, 'ARCHIVE_SPARSE_UNSUPPORTED')
                key = normalized.rstrip('/')
                if key == '.': key = ''
                check(key not in seen, 'ARCHIVE_DUPLICATE_NAME')
                seen.add(key)
                if key in paths:
                    check(name == plan['member_prefix'] + key, 'ARCHIVE_MEMBER_ALIAS')
                if name not in wanted: continue
                item = wanted[name]
                check(item['ref'] not in selected, 'ARCHIVE_DUPLICATE_MEMBER')
                check(member.isfile() and not member.issym() and not member.islnk()
                      and member.sparse is None and member.size == item['bytes'], 'ARCHIVE_MEMBER_TYPE_OR_SIZE')
                view.seek(member.offset_data)
                data = view.read(member.size)
                check(len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256'], 'ARCHIVE_MEMBER_SHA')
                selected[item['ref']] = data
            # No concatenated archive or nonzero payload after the first EOF.
            while view.tell() < view.size:
                tail = view.read(min(65536, view.size - view.tell()))
                check(tail and not any(tail), 'ARCHIVE_TRAILING_DATA')
        check(set(selected) == {x['ref'] for x in items}, 'ARCHIVE_MEMBER_MISSING')
        check(stamp(before) == stamp(os.fstat(fd)) == stamp(os.stat(plan['filename'], dir_fd=rootfd, follow_symlinks=False)), 'ARCHIVE_CHANGED')
        current = directory(root, owner)
        try:
            check((os.fstat(current).st_dev, os.fstat(current).st_ino) == (os.fstat(rootfd).st_dev, os.fstat(rootfd).st_ino), 'ARCHIVE_ROOT_MOVED')
        finally: os.close(current)
        return selected
    finally:
        if fd is not None: os.close(fd)
        os.close(rootfd)


def read_archive_member_metadata(root, owner, item, plan):
    """Fixed metadata mode: actual member proof, not a whole-archive claim."""
    return _read_archive(root, owner, [item], plan, False)[item['ref']]


def read_archive_members(root, owner, items, plan):
    """Custody mode: one pinned fd/hash/scan; no body returned before all pass."""
    return _read_archive(root, owner, items, plan, True)


def read_archive_member(root, owner, item, plan):
    return read_archive_members(root, owner, [item], plan)[item['ref']]
