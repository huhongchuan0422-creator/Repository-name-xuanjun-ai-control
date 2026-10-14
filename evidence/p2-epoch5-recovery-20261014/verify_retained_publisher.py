"""Read-only retained publisher verification; compatible with original journal.

No Git commands, credential output, imports from the installed package, deletion,
repair, or installation admission. Directory traversal is descriptor anchored.
"""
import hashlib
import json
import os
import stat


def require(value, label):
    if not value:
        raise ValueError(label)


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


def main():
    import socket
    require(os.geteuid() == 0 and socket.gethostname().split('.')[0] ==
            'iZd7oeikknn1z21sq6ji6zZ', 'FIXED_ROOT_HOST')
    path = ('/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/'
            'legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/publisher-bootstrap.json')
    expected = 'dde7083c8141d254eb254d90b4d442d8da31678995ce7aa21188e279cb4e5da8'
    def read_journal():
        require(os.path.realpath(path) == path, 'PUBLISHER_JOURNAL_ALIAS')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and
                    before.st_gid == 0 and stat.S_IMODE(before.st_mode) == 0o600 and
                    before.st_nlink == 1, 'PUBLISHER_JOURNAL_IDENTITY')
            data = stream.read(1048577)
            require(len(data) <= 1048576 and identity(before) == identity(os.fstat(stream.fileno())),
                    'PUBLISHER_JOURNAL_CHANGED')
        require(hashlib.sha256(data).hexdigest() == expected, 'PUBLISHER_JOURNAL_HASH')
        return data
    raw = read_journal()
    value = json.loads(raw.decode('utf-8'))
    require(value['schema'] == 1 and len(value['directories']) == 2 and
            len(set(row['target'] for row in value['directories'])) == 2,
            'PUBLISHER_JOURNAL_COMPLETENESS')
    rows = [verify_row(row) for row in value['directories']]
    require(read_journal() == raw, 'PUBLISHER_JOURNAL_CHANGED')
    print('RETAINED_PUBLISHER_CONTENT=' + json.dumps(rows, sort_keys=True))
    print('READ_ONLY_CONTENT_CHECK_NOT_INSTALL_ADMISSION')


if __name__ == '__main__':
    main()
