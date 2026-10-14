"""Source-only selected read-only primitives. No historical capture/resume/pins.
Exact function provenance is recorded in reviewed_sources.json.
"""
import hashlib, json, os, stat, tempfile, types, importlib.util, io, marshal, struct, re, sqlite3
from reviewed_scanner import require
def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def fingerprint(root, owner_uid=1003, owner_gid=1003):
    require(os.path.isabs(root) and os.path.normpath(root) == root and root != '/',
            'PUBLISHER_ROOT_PATH')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    held, links, entries = [], [], []
    count, total = [0], [0]

    def same(left, right):
        require(identity(left) == identity(right), 'PUBLISHER_SCAN_RACE')

    def visit(fd, relative, before, depth):
        count[0] += 1
        require(count[0] <= 10000 and depth <= 32, 'PUBLISHER_ENTRY_BOUND')
        same(before, os.fstat(fd))
        require((before.st_uid, before.st_gid) == (owner_uid, owner_gid),
                'PUBLISHER_OWNER')
        if stat.S_ISDIR(before.st_mode):
            require(stat.S_IMODE(before.st_mode) == 0o700, 'PUBLISHER_DIRECTORY_MODE')
            entries.append([relative, 'DIR', before.st_dev, before.st_ino])
            names = sorted(os.listdir(fd))
            require(len(names) <= 10000, 'PUBLISHER_ENTRY_BOUND')
            for name in names:
                child_info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                directory = stat.S_ISDIR(child_info.st_mode)
                require(directory or stat.S_ISREG(child_info.st_mode), 'PUBLISHER_ENTRY_TYPE')
                require(child_info.st_dev == before.st_dev, 'PUBLISHER_MOUNT_CHANGE')
                child = os.open(name, flags | (os.O_DIRECTORY if directory else os.O_NONBLOCK), dir_fd=fd)
                try:
                    visit(child, name if relative == '.' else relative + '/' + name,
                          child_info, depth + 1)
                    same(child_info, os.stat(name, dir_fd=fd, follow_symlinks=False))
                finally:
                    os.close(child)
            require(sorted(os.listdir(fd)) == names, 'PUBLISHER_ENTRIES_CHANGED')
        else:
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                    stat.S_IMODE(before.st_mode) == 0o600, 'PUBLISHER_FILE_IDENTITY')
            digest = hashlib.sha256()
            while True:
                data = os.read(fd, 65536)
                if not data:
                    break
                total[0] += len(data)
                require(total[0] <= 134217728, 'PUBLISHER_CONTENT_BOUND')
                digest.update(data)
            entries.append([relative, digest.hexdigest(), before.st_dev, before.st_ino,
                            before.st_mtime_ns, before.st_ctime_ns])
        same(before, os.fstat(fd))

    try:
        current = os.open('/', flags | os.O_DIRECTORY)
        held.append(current)
        for name in root.strip('/').split('/'):
            before = os.stat(name, dir_fd=current, follow_symlinks=False)
            require(stat.S_ISDIR(before.st_mode), 'PUBLISHER_ANCESTOR_TYPE')
            child = os.open(name, flags | os.O_DIRECTORY, dir_fd=current)
            held.append(child)
            same(before, os.fstat(child))
            links.append((current, name, before, child))
            current = child
        visit(current, '.', os.fstat(current), 0)
        for parent, name, before, child in reversed(links):
            now = os.stat(name, dir_fd=parent, follow_symlinks=False)
            # Unrelated sibling updates can change ancestor timestamps, but not identity.
            require(identity(now)[:5] == identity(before)[:5] and
                    identity(os.fstat(child))[:5] == identity(before)[:5],
                    'PUBLISHER_ANCESTOR_CHANGED')
        return hashlib.sha256(json.dumps(sorted(entries), separators=(',', ':')).encode()).hexdigest()
    finally:
        for fd in reversed(held):
            os.close(fd)


def verify_row(row):
    targets = ('/var/lib/xuanjun-development/control.git',
               '/var/lib/xuanjun-development/service-home/.config/gh')
    require(row['target'] in targets and row['state'] == 'PUBLISHED', 'PUBLISHER_JOURNAL_SCOPE')
    require(os.path.dirname(row['stage']) == os.path.dirname(row['target']) and
            os.path.basename(row['stage']).startswith('.p2-publisher-'), 'PUBLISHER_STAGE_SCOPE')
    require(not os.path.lexists(row['stage']), 'PUBLISHER_STAGE_PRESENT')
    before = os.lstat(row['target'])
    require((before.st_dev, before.st_ino) == (row['dev'], row['ino']), 'PUBLISHER_ROOT_CHANGED')
    observed = fingerprint(row['target'])
    require(observed == row['fingerprint'], 'PUBLISHER_CONTENT_CHANGED')
    require(identity(before) == identity(os.lstat(row['target'])), 'PUBLISHER_ROOT_CHANGED')
    require(not os.path.lexists(row['stage']), 'PUBLISHER_STAGE_PRESENT')
    return {'target': row['target'], 'content_fingerprint_matches': True,
            'root_identity_matches': True, 'stage_absent': True}

