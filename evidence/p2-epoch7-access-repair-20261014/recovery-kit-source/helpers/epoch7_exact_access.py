"""Two exact fd-anchored POSIX ACL effects; no recursion, NSS or group edits."""
import copy
import errno
import os
import stat
import struct

import epoch7_delta as d
import epoch7_protected_fs as fs
from epoch7_recovery_sequence import observation
from epoch7_host_phases import HostPhaseFilesystem, need, sha
from exact_access_plan import parse_acl, serialize, propose

TARGETS = {'/opt/xuanjun-control-releases': ('release_traversal', [1002,1003,1004]),
           '/etc/xuanjun-development/p2-native-ledger-client.json': ('ledger_client_binding_read', [1003])}
ACCESS = 'system.posix_acl_access'
DEFAULT = 'system.posix_acl_default'
TAGS = {'user': 0x02, 'group': 0x08, 'mask': 0x10, 'other': 0x20}
BASE_TAGS = {'user': 0x01, 'group': 0x04, 'mask': 0x10, 'other': 0x20}
UNDEFINED = 0xffffffff


def get_attr(fd, name):
    try: return os.getxattr(fd, name)
    except OSError as error:
        if error.errno == errno.ENODATA: return None
        # Unsupported ACL filesystems cannot prove or apply this policy.
        raise


def encode_acl(text):
    entries = parse_acl(text)
    rows = []
    for line in serialize(entries).splitlines():
        kind, identity, rights = line.split(':')
        tag = TAGS[kind] if identity else BASE_TAGS[kind]
        perm = sum(bit for bit, char in ((4,'r'),(2,'w'),(1,'x')) if char in rights)
        rows.append(struct.pack('<HHI', tag, perm, int(identity) if identity else UNDEFINED))
    return struct.pack('<I', 2) + b''.join(rows)


def decode_acl(raw, mode):
    if raw is None:
        def rights(value): return ''.join(c if value & n else '-' for n,c in ((4,'r'),(2,'w'),(1,'x')))
        return 'user::%s\ngroup::%s\nother::%s\n' % (rights((mode>>6)&7),rights((mode>>3)&7),rights(mode&7))
    need(type(raw) is bytes and 4 <= len(raw) <= 16384 and (len(raw)-4)%8 == 0 and
         struct.unpack('<I', raw[:4])[0] == 2, 'ACL_XATTR_FORMAT')
    rows, seen = [], set()
    labels = {1:('user',False),2:('user',True),4:('group',False),8:('group',True),16:('mask',False),32:('other',False)}
    for offset in range(4, len(raw), 8):
        tag, perm, uid = struct.unpack('<HHI', raw[offset:offset+8])
        need(tag in labels and perm <= 7, 'ACL_XATTR_ENTRY')
        kind, named = labels[tag]
        need((named and uid != UNDEFINED) or (not named and uid == UNDEFINED), 'ACL_XATTR_ID')
        identity = str(uid) if named else ''
        key = kind, identity
        need(key not in seen, 'ACL_XATTR_DUPLICATE'); seen.add(key)
        rights = ''.join(c if perm & n else '-' for n,c in ((4,'r'),(2,'w'),(1,'x')))
        rows.append('%s:%s:%s\n' % (kind, identity, rights))
    parsed = parse_acl(''.join(rows))
    return serialize(parsed)


class ExactAccessApplier(object):
    def __init__(self, io, context, rows, security_sha256, live_check, before_resolver):
        need(isinstance(io, HostPhaseFilesystem) and callable(live_check) and
             callable(before_resolver), 'ACL_PROTECTED_ADAPTERS')
        need(type(rows) is list and len(rows) == 2 and {r['path'] for r in rows} == set(TARGETS), 'ACL_EXACT_TWO_PATHS')
        self.rows = copy.deepcopy(rows)
        for row in self.rows:
            need(set(row) == {'path','before_binding','proposal'}, 'ACL_REVIEW_ROW')
            before = row['before_binding']
            purpose, uids = TARGETS[row['path']]
            is_dir = purpose == 'release_traversal'
            keys = {'kind','uid','gid','mode','access_acl','default_acl','sha256','state_source'}
            if is_dir: keys |= {'dev','ino'}
            need(type(before) is dict and set(before) == keys, 'ACL_STATIC_BEFORE_BINDING')
            need(before['uid'] == io.owner and before['default_acl'] == '' and
                 before['mode'] == (0o750 if is_dir else 0o640) and
                 before['kind'] == ('DIRECTORY' if is_dir else 'FILE') and
                 before['state_source'] == ('stage_exact_release_observed' if is_dir else 'inner_provision_observed_after'),
                 'ACL_BEFORE_SCOPE')
            if is_dir:
                need(before['sha256'] is None and type(before['dev']) is int and
                     type(before['ino']) is int and before['ino'] > 0, 'ACL_PARENT_IDENTITY')
            else: d.hash_value(before['sha256'])
            need(d.same(row['proposal'], propose(before['access_acl'], purpose, uids)), 'ACL_COMPILED_DELTA')
        d.hash_value(security_sha256)
        need(d.digest(self.rows) == security_sha256, 'ACL_SECURITY_DELTA_HASH')
        self.io, self.context, self.live = io, copy.deepcopy(context), live_check
        self.resolve_before = before_resolver
        self.digest, self.started, self.observed = security_sha256, False, {}

    def _read(self, parent, leaf, fd, path):
        info = os.fstat(fd); current = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        need(fs.stamp(info) == fs.stamp(current), 'ACL_PATH_FD_CHANGED')
        is_dir = path == '/opt/xuanjun-control-releases'
        need((stat.S_ISDIR(info.st_mode) if is_dir else stat.S_ISREG(info.st_mode)) and
             info.st_uid == self.io.owner and (is_dir or info.st_nlink == 1), 'ACL_TARGET_AUTHORITY')
        access = decode_acl(get_attr(fd, ACCESS), stat.S_IMODE(info.st_mode))
        need(get_attr(fd, DEFAULT) is None, 'ACL_DEFAULT_FORBIDDEN')
        digest = None
        if not is_dir:
            need(info.st_size <= 1048576, 'ACL_FILE_BOUND')
            os.lseek(fd, 0, os.SEEK_SET)
            chunks, count = [], 0
            while True:
                part = os.read(fd, min(65536,1048577-count))
                if not part: break
                count += len(part); need(count <= 1048576, 'ACL_FILE_BOUND'); chunks.append(part)
            need(count == info.st_size, 'ACL_FILE_SIZE'); digest = sha(b''.join(chunks))
        need(fs.stamp(os.fstat(fd)) == fs.stamp(info) and
             fs.stamp(os.stat(leaf, dir_fd=parent, follow_symlinks=False)) == fs.stamp(info), 'ACL_READ_RACE')
        return dict(fs.metadata(info), kind='DIRECTORY' if is_dir else 'FILE',
                    access_acl=access, default_acl='', sha256=digest)

    def __call__(self, context, diagnostics):
        phase = 'apply_reviewed_access'
        need(not self.started and d.same(context, self.context) and d.digest(self.rows) == self.digest,
             'ACL_ONE_EXACT_ATTEMPT')
        self.io.require_phase(phase); need(self.live(context, phase) is True, 'ACL_LIVE_GUARD')
        self.started = True
        for row in self.rows:
            path, binding = row['path'], row['before_binding']
            before = self.resolve_before(path)
            need(type(before) is dict and set(before) == set(fs.metadata(os.stat(__file__))) |
                 {'kind','access_acl','default_acl','sha256'} and all(before[k] == v for k,v in binding.items()
                 if k != 'state_source'), 'ACL_OWNED_PHASE_BEFORE_REQUIRED')
            parent, leaf = self.io._parent(path)
            fd = None
            try:
                fd = os.open(leaf, fs.DIR_FLAGS if before['kind'] == 'DIRECTORY' else fs.READ_FLAGS, dir_fd=parent)
                first = self._read(parent, leaf, fd, path)
                need(d.same(first, before), 'ACL_FULL_BEFORE_CAS')
                self.io.require_phase(phase); need(self.live(context, phase) is True, 'ACL_LIVE_GUARD')
                need(d.same(self._read(parent, leaf, fd, path), before), 'ACL_SECOND_CAS')
                os.setxattr(fd, ACCESS, encode_acl(row['proposal']['after_acl']))
                os.fsync(fd); os.fsync(parent)
                after = self._read(parent, leaf, fd, path)
                fixed = set(before) - {'access_acl', 'ctime_ns'}
                need(all(after[k] == before[k] for k in fixed) and
                     after['ctime_ns'] >= before['ctime_ns'] and
                     after['access_acl'] == row['proposal']['after_acl'], 'ACL_POSTCONDITION')
                self.observed[path] = after
            finally:
                if fd is not None: os.close(fd)
                os.close(parent)
        return observation(context, phase, d.digest(self.observed))
