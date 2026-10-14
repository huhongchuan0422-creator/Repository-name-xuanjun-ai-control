"""Narrow Linux ACLs for Git-free native snapshots, never importer or credentials.

The dispatcher owns initial snapshots. The existing Gateway UID executes tools
inside the bound Docker namespace. Only these two UIDs receive snapshot access;
the QA bind mount remains read-only. No world access or supplementary groups.
"""
import os
import stat
import struct

USER_OBJ, USER, GROUP_OBJ, MASK, OTHER = 1, 2, 4, 16, 32
UNDEFINED = 0xffffffff
ACCESS = 'system.posix_acl_access'
DEFAULT = 'system.posix_acl_default'

def encode(entries):
    return struct.pack('<I', 2) + b''.join(struct.pack('<HHI', *entry) for entry in entries)

def decode(raw):
    if len(raw) < 4 or (len(raw)-4) % 8 or struct.unpack('<I', raw[:4])[0] != 2:
        raise ValueError('INVALID_SNAPSHOT_ACL_ENCODING')
    return [struct.unpack('<HHI', raw[i:i+8]) for i in range(4, len(raw), 8)]

class NativeSnapshotAccess:
    def __init__(self, workspace_root, dispatcher_uid, gateway_uid):
        if (not isinstance(workspace_root, str) or not os.path.isabs(workspace_root)
                or os.path.realpath(workspace_root) != workspace_root
                or workspace_root in ('/', '/tmp', '/home', '/var', '/opt')
                or any(type(x) is not int or x < 1 for x in (dispatcher_uid, gateway_uid))
                or dispatcher_uid == gateway_uid):
            raise ValueError('BOUND_NATIVE_SNAPSHOT_IDENTITIES_REQUIRED')
        self.root = workspace_root
        self.dispatcher_uid = dispatcher_uid
        self.gateway_uid = gateway_uid
        self.uids = tuple(sorted((dispatcher_uid, gateway_uid)))

    def _entries(self, permission):
        return [(USER_OBJ, permission, UNDEFINED)] + [
            (USER, permission, uid) for uid in self.uids
        ] + [(GROUP_OBJ, 0, UNDEFINED), (MASK, permission, UNDEFINED), (OTHER, 0, UNDEFINED)]

    def share(self, snapshot):
        if (os.geteuid() != self.dispatcher_uid
                or not snapshot.startswith(self.root + '/')
                or os.path.realpath(snapshot) != snapshot):
            raise ValueError('SNAPSHOT_OWNER_SCOPE_REQUIRED')
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_DIRECTORY', 0)
        rootfd = os.open(snapshot, flags)
        count = [0]
        def walk(fd):
            info = os.fstat(fd)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != self.dispatcher_uid:
                raise ValueError('SNAPSHOT_DIRECTORY_OWNER_REQUIRED')
            for name in os.listdir(fd):
                count[0] += 1
                if count[0] > 8192 or name in ('.', '..', '.git'):
                    raise ValueError('SNAPSHOT_ACL_SCOPE_LIMIT')
                entry = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if not (stat.S_ISDIR(entry.st_mode) or stat.S_ISREG(entry.st_mode)):
                    raise ValueError('SNAPSHOT_SPECIAL_ENTRY_REJECTED')
                child = os.open(name, flags if stat.S_ISDIR(entry.st_mode)
                                else os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                try:
                    opened = os.fstat(child)
                    if (entry.st_dev, entry.st_ino) != (opened.st_dev, opened.st_ino):
                        raise ValueError('SNAPSHOT_ENTRY_CHANGED')
                    if stat.S_ISDIR(opened.st_mode):
                        walk(child)
                    elif stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1:
                        if opened.st_uid != self.dispatcher_uid:
                            raise ValueError('SNAPSHOT_FILE_OWNER_REQUIRED')
                        permission = 7 if opened.st_mode & 0o100 else 6
                        os.setxattr(child, ACCESS, encode(self._entries(permission)))
                    else:
                        raise ValueError('SNAPSHOT_SPECIAL_ENTRY_REJECTED')
                finally:
                    os.close(child)
            os.setxattr(fd, DEFAULT, encode(self._entries(7)))
            os.setxattr(fd, ACCESS, encode(self._entries(7)))
        try:
            walk(rootfd)
        finally:
            os.close(rootfd)

    def validate(self, fd, directory=False):
        info = os.fstat(fd)
        if (type(directory) is not bool or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
            raise ValueError('SNAPSHOT_FILE_TYPE_REJECTED')
        if info.st_uid not in self.uids or (not directory and info.st_nlink != 1):
            raise ValueError('SNAPSHOT_IDENTITY_REJECTED')
        mode = stat.S_IMODE(info.st_mode)
        valid_modes = (0o750, 0o770) if directory else (0o640, 0o660, 0o750, 0o770)
        if mode not in valid_modes:
            raise ValueError('SNAPSHOT_SHARED_MODE_REJECTED')
        executable = directory or bool(mode & 0o100)
        owner_perm = 7 if executable else 6
        mask_perm = (mode >> 3) & 7
        entries = decode(os.getxattr(fd, ACCESS))
        if len(entries) != 6:
            raise ValueError('SNAPSHOT_ACL_ENTRIES_REJECTED')
        if (entries[0] != (USER_OBJ, owner_perm, UNDEFINED)
                or entries[3] != (GROUP_OBJ, 0, UNDEFINED)
                or entries[4] != (MASK, mask_perm, UNDEFINED)
                or entries[5] != (OTHER, 0, UNDEFINED)):
            raise ValueError('SNAPSHOT_ACL_AUTHORITY_REJECTED')
        for entry, uid in zip(entries[1:3], self.uids):
            if entry[0] != USER or entry[2] != uid or entry[1] not in ((7,) if directory else (6, 7)):
                raise ValueError('SNAPSHOT_ACL_USER_REJECTED')
        if directory and os.getxattr(fd, DEFAULT) != encode(self._entries(7)):
            raise ValueError('SNAPSHOT_DEFAULT_ACL_REJECTED')
        return 0o100755 if executable else 0o100644
