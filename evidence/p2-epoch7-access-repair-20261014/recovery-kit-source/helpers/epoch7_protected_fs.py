"""Protected fd-relative recovery IO. No CLI, service call or implicit authority.

Mutation methods require the supplied reviewed gate immediately before effects.
Production namespace is / with fixed logical target/journal paths. Fixture mode
is confined to this candidate's fixtures/ subtree and never maps to host paths.
This is a cooperating-root/install-lock CAS protocol, not an atomic kernel
compare-and-rename primitive against hostile concurrent root writers.
"""
import errno
import hashlib
import json
import os
import secrets
import stat

import epoch7_delta as d
import epoch7_additive_identity as additive
import epoch7_additive_server as server_additive

TRANSACTION = ('/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/'
               'legacy-isolation-' + d.TX)
NEW_JOURNALS = frozenset(('epoch7-recovery-execution.json', 'epoch8-runtime-provisioning.json',
                        'epoch7-generation-access.json', 'epoch7-owner-identity-publication.json',
                        'epoch7-server-identity-publication.json'))
MAXIMUM = 1048576
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, 'O_CLOEXEC', 0)


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def metadata(info):
    return {'uid': info.st_uid, 'gid': info.st_gid, 'mode': stat.S_IMODE(info.st_mode),
        'dev': info.st_dev, 'ino': info.st_ino, 'nlink': info.st_nlink,
        'size': info.st_size, 'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


def raw_sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ProtectedFilesystem(object):
    def __init__(self, gate, fixture_root=None):
        d.need(gate is not None and callable(getattr(gate, 'check', None)), 'FILESYSTEM_GATE_REQUIRED')
        self.gate = gate
        self.fixture = fixture_root is not None
        if self.fixture:
            base = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'fixtures')
            d.need(isinstance(fixture_root, str) and fixture_root.startswith(base + '/') and
                   os.path.normpath(fixture_root) == fixture_root and
                   os.path.realpath(fixture_root) == fixture_root, 'FIXTURE_ROOT_CONFINEMENT')
            self.root = fixture_root
            self.owner, self.group = os.geteuid(), os.getegid()
        else:
            self.root = '/'; self.owner, self.group = 0, 0
            d.need(os.geteuid() == 0, 'PRODUCTION_ROOT_REQUIRED')
            # External approval provenance and exact current state remain the
            # outer gate's responsibility; there is no Boolean bypass parameter.
            from epoch7_injected_recovery import RecoveryGate
            d.need(isinstance(gate, RecoveryGate), 'PRODUCTION_REVIEWED_GATE_REQUIRED')
        fd = os.open(self.root, DIR_FLAGS)
        try:
            info = os.fstat(fd)
            self._check_parent(info)
            self.root_identity = (info.st_dev, info.st_ino)
        finally: os.close(fd)

    def _authorize(self):
        self.gate.check()
        info = os.stat(self.root, follow_symlinks=False)
        d.need(stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == self.root_identity,
               'FILESYSTEM_NAMESPACE_CHANGED')
        self._check_parent(info)

    def _check_parent(self, info):
        d.need(stat.S_ISDIR(info.st_mode) and info.st_uid == self.owner and
               not stat.S_IMODE(info.st_mode) & 0o022, 'UNSAFE_ROOT_PROTECTED_PARENT')

    @staticmethod
    def _xattr(fd, name):
        try: return os.getxattr(fd, name)
        except OSError as error:
            if error.errno in (errno.ENODATA, errno.ENOTSUP, errno.EOPNOTSUPP): return None
            raise

    def _no_acl(self, fd, directory=False):
        d.need(self._xattr(fd, 'system.posix_acl_access') is None, 'EXTENDED_ACCESS_ACL_REQUIRES_REVIEW')
        if directory:
            d.need(self._xattr(fd, 'system.posix_acl_default') is None, 'DEFAULT_ACL_REQUIRES_REVIEW')

    def _open_dir(self, logical):
        additive.lexical_path(logical)
        fd = os.open(self.root, DIR_FLAGS)
        try:
            info = os.fstat(fd)
            d.need((info.st_dev, info.st_ino) == self.root_identity, 'FILESYSTEM_NAMESPACE_CHANGED')
            self._check_parent(info)
            self._no_acl(fd, directory=True)
            for part in logical.split('/')[1:]:
                child = os.open(part, DIR_FLAGS, dir_fd=fd)
                try:
                    self._check_parent(os.fstat(child))
                    self._no_acl(child, directory=True)
                except BaseException:
                    os.close(child); raise
                os.close(fd); fd = child
            return fd
        except BaseException:
            os.close(fd); raise

    def _parent(self, logical):
        additive.lexical_path(logical)
        parent, name = logical.rsplit('/', 1)
        return self._open_dir(parent), name

    def _journal_parent(self):
        fd = self._open_dir(TRANSACTION)
        info = os.fstat(fd)
        if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (self.owner, self.group, 0o700):
            os.close(fd); raise ValueError('PRIVATE_TRANSACTION_DIRECTORY_REQUIRED')
        return fd

    @staticmethod
    def _write_all(fd, raw):
        position = 0
        while position < len(raw):
            written = os.write(fd, raw[position:])
            d.need(type(written) is int and written > 0, 'RECOVERY_SHORT_WRITE')
            position += written

    def _set_identity(self, fd, uid, gid, mode):
        d.need(type(uid) is int and type(gid) is int and type(mode) is int and
               uid == self.owner and gid >= 0 and mode in (0o600, 0o640, 0o644),
               'PROTECTED_PUBLICATION_IDENTITY')
        if self.fixture: d.need(gid == self.group, 'FIXTURE_GROUP_SCOPE')
        info = os.fstat(fd)
        if (info.st_uid, info.st_gid) != (uid, gid): os.fchown(fd, uid, gid)
        os.fchmod(fd, mode)

    def _read_at(self, parent, name, allow_mask=False, maximum=MAXIMUM):
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if stat.S_ISLNK(before.st_mode):
            d.need(allow_mask and before.st_uid == self.owner and before.st_gid == self.group and
                   before.st_nlink == 1, 'UNEXPECTED_TARGET_SYMLINK')
            target = os.readlink(name, dir_fd=parent)
            after = os.stat(name, dir_fd=parent, follow_symlinks=False)
            d.need(target == '/dev/null' and stamp(before) == stamp(after), 'EXACT_STABLE_OWNER_MASK_REQUIRED')
            return dict(metadata(after), kind='MASK', link=target), None
        fd = os.open(name, READ_FLAGS, dir_fd=parent)
        try:
            opened = os.fstat(fd)
            d.need(stat.S_ISREG(opened.st_mode) and opened.st_uid == self.owner and
                   opened.st_nlink == 1 and 0 <= opened.st_size <= maximum and
                   stat.S_IMODE(opened.st_mode) in (0o600, 0o640, 0o644) and
                   stamp(opened) == stamp(before), 'PROTECTED_REGULAR_FILE_REQUIRED')
            self._no_acl(fd)
            chunks = []; total = 0
            while True:
                part = os.read(fd, min(65536, maximum + 1 - total))
                if not part: break
                total += len(part); d.need(total <= maximum, 'RECOVERY_READ_BOUND')
                chunks.append(part)
            raw = b''.join(chunks)
            after = os.fstat(fd)
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            d.need(stamp(before) == stamp(after) == stamp(current) and len(raw) == before.st_size,
                   'RECOVERY_FILE_READ_RACE')
            return dict(metadata(after), kind='FILE', sha256=raw_sha(raw)), raw
        finally: os.close(fd)

    @staticmethod
    def _matches(observed, expected):
        d.need(isinstance(expected, dict) and all(k in observed and
               (type(observed[k]) is bytes and observed[k] == v if isinstance(v, bytes) else d.same(observed[k], v))
                                                for k, v in expected.items()), 'RECOVERY_EXACT_BEFORE_STATE')

    def _approved_effect(self, kind, path, before, after=None):
        # Fixture authority cannot publish in the production namespace. Real IO
        # independently binds every effect to the already reviewed gate delta.
        if self.fixture: return
        if kind == 'generation':
            change = self.gate.delta['generation_change']
            d.need(d.same(before, change['before']) and d.same(after, change['after']), 'REVIEWED_GENERATION_EFFECT')
        elif kind == 'additive':
            rows = [x for x in self.gate.additions if x['path'] == path]
            d.need(len(rows) == 1 and d.same(before, rows[0]['before']) and
                   d.same(after, rows[0]['after']), 'REVIEWED_ADDITIVE_EFFECT')
        else:
            rows = [x for x in self.gate.delta['changes'] if x['path'] == path]
            d.need(len(rows) == 1 and rows[0]['operation'] in ('REPLACE_EXACT_FILE', 'REPLACE_EXACT_OWNER_MASK') and
                   d.same(before, rows[0]['before']) and
                   (after is None or d.same(after, rows[0]['after'])), 'REVIEWED_RETAINED_EFFECT')

    @staticmethod
    def _before(observed, expected):
        d.need(set(observed) == set(expected) and d.same(observed, expected),
               'RECOVERY_EXACT_BEFORE_STATE')

    def _require_intent(self, journal_name, stage, path=None, before=None, after=None):
        record = self.read_journal(journal_name)
        value = json.loads(record['data'].decode('utf-8'))
        d.need(d.canonical(value) + b'\n' == record['data'] and value.get('schema') == 1 and
               value.get('name') == journal_name and value.get('transaction_id') == d.TX and
               d.same(value.get('binding'), self.gate.journal_binding()), 'DURABLE_BOUND_INTENT_REQUIRED')
        state = value.get('state')
        d.need(isinstance(state, dict), 'DURABLE_BOUND_INTENT_REQUIRED')
        if path is not None:
            rows = state.get('targets')
            d.need(isinstance(rows, list), 'DURABLE_TARGET_INTENT_REQUIRED')
            matched = [row for row in rows if isinstance(row, dict) and row.get('path') == path]
            d.need(len(matched) == 1, 'DURABLE_TARGET_INTENT_REQUIRED'); state = matched[0]
            d.need(state.get('state') == stage, 'DURABLE_TARGET_INTENT_REQUIRED')
        else:
            d.need(state.get('stage') == stage, 'DURABLE_PHASE_INTENT_REQUIRED')
        if before is not None: d.need(d.same(state.get('before'), before), 'INTENT_BEFORE_BINDING')
        if after is not None: d.need(d.same(state.get('after'), after), 'INTENT_AFTER_BINDING')
        return state

    def read_target(self, path):
        d.need(path in d.TARGETS or path in (additive.PATH, server_additive.PATH), 'RECOVERY_TARGET_SCOPE')
        parent, name = self._parent(path)
        try: return self._read_at(parent, name, path in d.OWNER_MASKS)[0]
        finally: os.close(parent)

    def journal_exists(self, name):
        d.need(name in NEW_JOURNALS, 'NEW_JOURNAL_NAME_REQUIRED')
        parent = self._journal_parent()
        try:
            try: os.stat(name, dir_fd=parent, follow_symlinks=False); return True
            except FileNotFoundError: return False
        finally: os.close(parent)

    def read_journal(self, name):
        d.need(name in NEW_JOURNALS, 'NEW_JOURNAL_NAME_REQUIRED')
        parent = self._journal_parent()
        try:
            info, raw = self._read_at(parent, name)
            info.pop('kind'); info.pop('sha256'); info['data'] = raw
            d.need((info['uid'], info['gid'], info['mode']) == (self.owner, self.group, 0o600),
                   'PROTECTED_JOURNAL_REQUIRED')
            return info
        finally: os.close(parent)

    def _exclusive_at(self, parent, name, raw, uid, gid, mode):
        d.need(isinstance(raw, bytes) and len(raw) <= MAXIMUM, 'RECOVERY_WRITE_BOUND')
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
        fd = os.open(name, flags, 0o600, dir_fd=parent)
        try:
            self._set_identity(fd, uid, gid, mode)
            self._write_all(fd, raw); os.fsync(fd)
        finally: os.close(fd)
        os.fsync(parent)

    def create_exclusive(self, name, raw, uid, gid, mode):
        d.need(name in NEW_JOURNALS and (uid, gid, mode) == (self.owner, self.group, 0o600),
               'NEW_PRIVATE_JOURNAL_ONLY')
        self._authorize(); parent = self._journal_parent()
        try: self._exclusive_at(parent, name, raw, uid, gid, mode)
        finally: os.close(parent)

    def _replace_at(self, parent, name, expected, raw, uid, gid, mode, allow_mask=False):
        # Stage only after a durable caller INTENT. The target's before-state is
        # checked again immediately before publication under the same parent fd.
        temporary = '.epoch7-recovery-' + secrets.token_hex(16)
        temporary_identity = None
        try:
            self._exclusive_at(parent, temporary, raw, uid, gid, mode)
            temporary_identity = os.stat(temporary, dir_fd=parent, follow_symlinks=False)
            current, old_raw = self._read_at(parent, name, allow_mask)
            if 'data' in expected:
                current.pop('kind'); current.pop('sha256'); current['data'] = old_raw
            self._matches(current, expected)
            self._authorize()
            # gate.check may inspect files; repeat CAS after it, not before it.
            current, old_raw = self._read_at(parent, name, allow_mask)
            if 'data' in expected:
                current.pop('kind'); current.pop('sha256'); current['data'] = old_raw
            self._matches(current, expected)
            os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                current = os.stat(temporary, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError: current = None
            if current is not None and temporary_identity is not None:
                d.need(stamp(current) == stamp(temporary_identity), 'STAGING_FILE_CHANGED_KEEP_EVIDENCE')
                os.unlink(temporary, dir_fd=parent); os.fsync(parent)

    def replace_exact(self, name, expected, raw, uid, gid, mode):
        d.need(name in NEW_JOURNALS and (uid, gid, mode) == (self.owner, self.group, 0o600),
               'NEW_PRIVATE_JOURNAL_ONLY')
        self._authorize(); parent = self._journal_parent()
        try: self._replace_at(parent, name, expected, raw, uid, gid, mode)
        finally: os.close(parent)

    def backup_target_exact(self, path, expected, name):
        d.need(path in d.TARGETS and name == 'epoch7-target-before-' +
               hashlib.sha256(path.encode('utf-8')).hexdigest() + '.private', 'EXACT_TARGET_BACKUP_SCOPE')
        self._authorize()
        self._approved_effect('retained', path, expected)
        self._require_intent('epoch7-recovery-execution.json', 'TARGET_DELTA_INTENT')
        self._require_intent('epoch8-runtime-provisioning.json', 'BACKUP_INTENT', path, expected)
        parent, leaf = self._parent(path)
        try:
            observed, raw = self._read_at(parent, leaf, path in d.OWNER_MASKS)
            self._before(observed, expected)
            if observed['kind'] == 'MASK': raw = d.canonical(expected)
            archive = self._journal_parent()
            try: self._exclusive_at(archive, name, raw, self.owner, self.group, 0o600)
            finally: os.close(archive)
            after, unused = self._read_at(parent, leaf, path in d.OWNER_MASKS)
            d.need(d.same(after, observed), 'TARGET_CHANGED_DURING_BACKUP')
            return {'name': name, 'sha256': raw_sha(raw), 'kind': observed['kind']}
        finally: os.close(parent)

    def replace_target_exact(self, path, expected, raw, after):
        d.need(path in d.TARGETS, 'EXACT_RETAINED_TARGET_ONLY')
        d.keys(after, ('kind', 'sha256', 'uid', 'gid', 'mode'), 'TARGET_AFTER_KEYS')
        d.need(after['kind'] == 'FILE' and raw_sha(raw) == after['sha256'], 'EXACT_TARGET_PAYLOAD')
        self._authorize()
        self._require_intent('epoch7-recovery-execution.json', 'TARGET_DELTA_INTENT')
        self._approved_effect('retained', path, expected, after)
        intent = self._require_intent('epoch8-runtime-provisioning.json', 'REPLACE_INTENT', path, expected, after)
        backup_name = 'epoch7-target-before-' + hashlib.sha256(path.encode('utf-8')).hexdigest() + '.private'
        backup_hash = expected['sha256'] if expected['kind'] == 'FILE' else d.digest(expected)
        d.need(intent.get('backup') == {'name': backup_name, 'sha256': backup_hash, 'kind': expected['kind']},
               'DURABLE_EXACT_BACKUP_REQUIRED')
        archive = self._journal_parent()
        try:
            saved, unused = self._read_at(archive, backup_name)
            d.need(saved['sha256'] == backup_hash and saved['mode'] == 0o600, 'PRIVATE_BACKUP_CHANGED')
        finally: os.close(archive)
        parent, name = self._parent(path)
        try:
            current, unused = self._read_at(parent, name, path in d.OWNER_MASKS)
            self._before(current, expected)
            self._replace_at(parent, name, expected, raw, after['uid'], after['gid'], after['mode'],
                             path in d.OWNER_MASKS)
            observed, unused = self._read_at(parent, name)
            self._matches(observed, after)
        finally: os.close(parent)

    def read_additive_absence(self, path=additive.PATH):
        d.need(path in (additive.PATH, server_additive.PATH), 'EXACT_ADDITIVE_PATH')
        parent, name = self._parent(path)
        try:
            try: os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError: pass
            else: raise ValueError('ADDITIVE_TARGET_ALREADY_EXISTS')
            info = os.fstat(parent); self._no_acl(parent, directory=True)
            # Only the known basic0755 parent is in this additive contract.
            d.need(stat.S_IMODE(info.st_mode) == 0o755, 'ADDITIVE_PARENT_MODE')
            acl = b'user::rwx\ngroup::r-x\nother::r-x\n'
            return {'path': path, 'kind': 'ABSENT', 'parent': {
                'path': additive.PARENT, 'kind': 'DIRECTORY', 'uid': info.st_uid,
                'gid': info.st_gid, 'mode': 0o755, 'dev': info.st_dev, 'ino': info.st_ino,
                'acl_sha256': raw_sha(acl)}}
        finally: os.close(parent)

    def read_additive_target(self, path=additive.PATH):
        d.need(path in (additive.PATH, server_additive.PATH), "EXACT_ADDITIVE_PATH")
        return self.read_target(path)

    def publish_additive_exact(self, before, raw, after):
        d.need(isinstance(raw, bytes) and len(raw) <= 65536 and
               after == {'kind': 'FILE', 'uid': self.owner, 'gid': self.group,
                         'mode': 0o644, 'sha256': raw_sha(raw)}, 'ADDITIVE_EXACT_PUBLICATION')
        self._authorize()
        path = before.get('path')
        d.need(path in (additive.PATH, server_additive.PATH), 'EXACT_ADDITIVE_PATH')
        journal = ('epoch7-owner-identity-publication.json' if path == additive.PATH else
                   'epoch7-server-identity-publication.json')
        self._approved_effect('additive', path, before, after)
        self._require_intent('epoch7-recovery-execution.json', 'ADDITIVE_PUBLICATION_INTENT')
        self._require_intent(journal, 'ADDITIVE_PUBLICATION_INTENT', before=before, after=after)
        d.need(d.same(self.read_additive_absence(path), before), 'ADDITIVE_ABSENCE_CAS')
        parent, name = self._parent(path)
        temporary = '.epoch7-identity-' + secrets.token_hex(16)
        temporary_identity = None
        try:
            self._exclusive_at(parent, temporary, raw, self.owner, self.group, 0o644)
            temporary_identity = os.stat(temporary, dir_fd=parent, follow_symlinks=False)
            self._authorize()
            d.need(d.same(self.read_additive_absence(path), before), 'ADDITIVE_ABSENCE_CAS')
            # Atomic no-overwrite publication. A crash with two links fails the
            # pin loader's nlink1 rule and remains an explicit journal HOLD.
            os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            os.fsync(parent)
            os.unlink(temporary, dir_fd=parent); os.fsync(parent)
            current, unused = self._read_at(parent, name)
            self._matches(current, after)
            return current
        finally:
            try: current = os.stat(temporary, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError: current = None
            if current is not None and temporary_identity is not None:
                d.need((current.st_dev, current.st_ino, current.st_uid, current.st_gid,
                        stat.S_IMODE(current.st_mode)) ==
                       (temporary_identity.st_dev, temporary_identity.st_ino,
                        temporary_identity.st_uid, temporary_identity.st_gid,
                        stat.S_IMODE(temporary_identity.st_mode)), 'ADDITIVE_STAGING_CHANGED')
                os.unlink(temporary, dir_fd=parent); os.fsync(parent)
            os.close(parent)

    def _open_generation(self):
        parent, name = self._parent(d.GENERATION)
        try: fd = os.open(name, DIR_FLAGS, dir_fd=parent)
        except BaseException: os.close(parent); raise
        return parent, name, fd

    def _generation_at(self, parent, name, fd):
        info = os.fstat(fd); current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        d.need(stat.S_ISDIR(info.st_mode) and stamp(info) == stamp(current), 'GENERATION_PATH_FD_CHANGED')
        self._no_acl(fd, directory=True)
        mode = stat.S_IMODE(info.st_mode)
        d.need(mode in (0o750, 0o700), 'EXACT_GENERATION_MODE')
        expected_uid, expected_gid = ((self.owner, self.group) if self.fixture else (1003, 1006))
        d.need((info.st_uid, info.st_gid) == (expected_uid, expected_gid), 'EXACT_GENERATION_OWNER')
        return dict(metadata(info), path=d.GENERATION, kind='DIRECTORY', default_acl='',
                    access_acl='user::rwx\ngroup::' + ('r-x' if mode == 0o750 else '---') + '\nother::---\n')

    def read_generation(self):
        parent, name, fd = self._open_generation()
        try: return self._generation_at(parent, name, fd)
        finally: os.close(fd); os.close(parent)

    def chmod_generation_exact(self, before, after):
        d.need(before.get('path') == d.GENERATION and before.get('mode') == 0o750 and
               after.get('path') == d.GENERATION and after.get('mode') == 0o700,
               'EXACT_GENERATION_CHMOD_SCOPE')
        desired = dict(before)
        for key in d.DIRECTORY_STAMP_KEYS: desired.pop(key, None)
        desired.update(mode=0o700, access_acl='user::rwx\ngroup::---\nother::---\n')
        d.need(d.same(after, desired), 'CHMOD_ONLY_NO_IDENTITY_OR_ACL_EXPANSION')
        self._authorize()
        self._approved_effect('generation', d.GENERATION, before, after)
        self._require_intent('epoch7-recovery-execution.json', 'GENERATION_ACCESS_INTENT')
        self._require_intent('epoch7-generation-access.json', 'GENERATION_ACCESS_INTENT', before=before, after=after)
        parent, name, fd = self._open_generation()
        try:
            observed = self._generation_at(parent, name, fd)
            self._before(observed, before)
            self._authorize()
            d.need(d.same(self._generation_at(parent, name, fd), observed), 'GENERATION_CHANGED_BEFORE_CHMOD')
            os.fchmod(fd, 0o700); os.fsync(fd); os.fsync(parent)
            current = self._generation_at(parent, name, fd)
            self._matches(current, after)
            d.need(all(current[k] == observed[k] for k in ('dev', 'ino', 'uid', 'gid', 'size', 'nlink', 'mtime_ns'))
                   and current['ctime_ns'] >= observed['ctime_ns'], 'GENERATION_POSTCONDITION_DRIFT')
            return current
        finally: os.close(fd); os.close(parent)
