"""Fd-relative installation switch coordinator for controlled installer entry.

Caller supplies a securely opened release-root fd, an existing durable operation
store, and enforces an exclusive authorized writer for the entire operation.
There is no DB creation, deployment, or service operation in this module.
"""
import ctypes
import errno
import hashlib
import json
import os
import stat

RENAME_NOREPLACE = 1
RENAME_EXCHANGE = 2


def _name(value):
    if not isinstance(value, str) or not value or value in ('.', '..') or '/' in value or '\x00' in value:
        raise ValueError('SINGLE_RELATIVE_NAME_REQUIRED')
    return value


def _rename(root_fd, left, right, flags):
    libc = ctypes.CDLL(None, use_errno=True)
    function = getattr(libc, 'renameat2', None)
    if function is None:
        raise RuntimeError('RENAMEAT2_REQUIRED_FAIL_CLOSED')
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    if function(root_fd, os.fsencode(_name(left)), root_fd, os.fsencode(_name(right)), flags):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _tree(fd):
    """Hash exact fd-relative regular-file tree, rejecting links and specials."""
    records = []
    root_info = os.fstat(fd)
    def visit(directory, prefix):
        for entry in sorted(os.listdir(directory)):
            _name(entry)
            path = prefix + entry
            child = os.open(entry, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                info = os.fstat(child)
                if info.st_dev != root_info.st_dev:
                    raise ValueError('CROSS_FILESYSTEM_REFUSED')
                if info.st_uid != root_info.st_uid or info.st_mode & 0o022:
                    raise PermissionError('UNTRUSTED_TREE_MEMBER')
                if stat.S_ISDIR(info.st_mode):
                    records.append((path+'/', stat.S_IMODE(info.st_mode), None))
                    visit(child, path+'/')
                elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 16*1024*1024:
                    digest = hashlib.sha256(); total = 0
                    while True:
                        data = os.read(child, 65536)
                        if not data: break
                        total += len(data)
                        if total > 16*1024*1024: raise ValueError('TREE_FILE_TOO_LARGE')
                        digest.update(data)
                    records.append((path, stat.S_IMODE(info.st_mode), digest.hexdigest()))
                else:
                    raise PermissionError('UNTRUSTED_TREE_MEMBER')
            finally:
                os.close(child)
    visit(fd, '')
    return hashlib.sha256(json.dumps(records, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()


def snapshot(root_fd, name):
    _name(name)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
    except OSError as error:
        if error.errno == errno.ENOENT: return None
        raise
    try:
        info = os.fstat(fd); root = os.fstat(root_fd)
        if info.st_dev != root.st_dev:
            raise ValueError('CROSS_FILESYSTEM_REFUSED')
        if info.st_uid != root.st_uid or info.st_mode & 0o022:
            raise PermissionError('UNTRUSTED_RELEASE_DIRECTORY')
        return {'dev':info.st_dev, 'ino':info.st_ino, 'tree_digest':_tree(fd)}
    finally:
        os.close(fd)


class SwitchCoordinator:
    def __init__(self, root_fd, operation_store):
        self.root_fd = os.dup(root_fd)
        if not stat.S_ISDIR(os.fstat(self.root_fd).st_mode):
            os.close(self.root_fd)
            raise ValueError('DIRECTORY_FD_REQUIRED')
        self.store = operation_store
    def close(self):
        os.close(self.root_fd)
    def _hold(self, op):
        self.store.transition(op, 'RUNNING', 'UNKNOWN', {'phase':'UNKNOWN'})
    def prepare(self, op, staged, current, rollback_of=None, context=None, require_absent=False):
        _name(staged); _name(current)
        if staged == current: raise ValueError('DISTINCT_NAMES_REQUIRED')
        before = snapshot(self.root_fd, current)
        after = snapshot(self.root_fd, staged)
        if require_absent and before is not None:
            raise ValueError('EXISTING_RELEASE_CONFLICT')
        if after is None: raise ValueError('STAGED_DIRECTORY_REQUIRED')
        root = os.fstat(self.root_fd)
        binding = {'root_dev':root.st_dev, 'root_ino':root.st_ino, 'staged':staged, 'current':current, 'prestate':before, 'staged_state':after, 'rollback_of':rollback_of, 'context':context}
        created, row = self.store.reserve(op, {'kind':'install-switch'}, binding, 'switch')
        if not created:
            return False
        if not self.store.transition(op, 'RESERVED', 'RUNNING', {'phase':'SWITCH_PENDING'}):
            raise RuntimeError('RESERVATION_LOST')
        return True
    def switch(self, op, staged, current, hook=None, rollback_of=None, prepared=False,
               ownership_guard=None, owner=None, attempt_id=None, authority_context=None):
        if op.startswith('p3-install:') and (ownership_guard is None or owner is None or attempt_id is None):
            raise PermissionError('INSTALL_OWNERSHIP_GUARD_REQUIRED')
        if not prepared and not self.prepare(op, staged, current, rollback_of):
            return self.reconcile(op)
        row = self.store.get(op)
        if not row or row['state'] != 'RUNNING':
            raise RuntimeError('PREPARED_SWITCH_REQUIRED')
        binding = json.loads(row['request_json'])['admission']
        if binding['staged'] != staged or binding['current'] != current or binding['rollback_of'] != rollback_of:
            raise ValueError('SWITCH_SCOPE_CONFLICT')
        before, after = binding['prestate'], binding['staged_state']
        root = os.fstat(self.root_fd)
        if (root.st_dev,root.st_ino) != (binding['root_dev'],binding['root_ino']):
            raise RuntimeError('SWITCH_ROOT_CHANGED')
        try:
            if hook: hook('before_rename')
            if ownership_guard is not None:
                # For the install entry, revalidate signed authority and owner
                # under the same flock and SQLite write transaction that cover
                # rename, fsync and the journal transition.
                with ownership_guard.with_exclusive_side_effect(op,owner,attempt_id,authority_context) as db:
                    if snapshot(self.root_fd, current) != before or snapshot(self.root_fd, staged) != after:
                        raise RuntimeError('SWITCH_PRESTATE_CHANGED')
                    _rename(self.root_fd,staged,current,RENAME_EXCHANGE if before else RENAME_NOREPLACE)
                    if hook:hook('after_rename')
                    os.fsync(self.root_fd)
                    if hook:hook('after_fsync')
                    changed=db.execute('UPDATE p3_effect_operations SET state=?,receipt_json=?,adapter_correlation=? WHERE operation_id=? AND state=?',
                        ('SUCCEEDED',json.dumps({'phase':'SWITCHED'},sort_keys=True,separators=(',',':')),None,op,'RUNNING')).rowcount
                    if changed != 1:raise RuntimeError('COMMIT_RACE')
            else:
                # Legacy non-install callers remain out of scope for this slice.
                if snapshot(self.root_fd, current) != before or snapshot(self.root_fd, staged) != after:
                    raise RuntimeError('SWITCH_PRESTATE_CHANGED')
                _rename(self.root_fd, staged, current, RENAME_EXCHANGE if before else RENAME_NOREPLACE)
                if hook: hook('after_rename')
                os.fsync(self.root_fd)
                if hook: hook('after_fsync')
                if not self.store.transition(op, 'RUNNING', 'SUCCEEDED', {'phase':'SWITCHED'}):
                    raise RuntimeError('COMMIT_RACE')
            return {'state':'SWITCHED'}
        except BaseException:
            if ownership_guard is None:
                self._hold(op)
            else:
                try:
                    with ownership_guard.with_exclusive_side_effect(op,owner,attempt_id,authority_context) as db:
                        db.execute('UPDATE p3_effect_operations SET state=?,receipt_json=? WHERE operation_id=? AND state=?',
                                   ('UNKNOWN',json.dumps({'phase':'UNKNOWN'},sort_keys=True,separators=(',',':')),op,'RUNNING'))
                except (PermissionError,KeyError):
                    pass
            raise
    def reconcile(self, op):
        if op.startswith('p3-install:'):
            raise PermissionError('SIGNED_INSTALL_RECOVERY_REQUIRED')
        row = self.store.get(op)
        if not row: raise ValueError('OPERATION_NOT_FOUND')
        if row['state'] not in ('RUNNING','UNKNOWN','SUCCEEDED'):
            return {'state':'UNKNOWN'}
        binding = json.loads(row['request_json'])['admission']
        root = os.fstat(self.root_fd)
        if (root.st_dev, root.st_ino) != (binding['root_dev'], binding['root_ino']):
            return {'state':'UNKNOWN'}
        try:
            current = snapshot(self.root_fd, binding['current'])
            staged = snapshot(self.root_fd, binding['staged'])
        except Exception:
            return {'state':'UNKNOWN'}
        if current == binding['staged_state'] and staged == binding['prestate']:
            if row['state'] == 'SUCCEEDED': return {'state':'SWITCHED'}
            os.fsync(self.root_fd)
            if self.store.transition(op, row['state'], 'SUCCEEDED', {'phase':'SWITCHED_RECONCILED'}):
                return {'state':'SWITCHED'}
            return {'state':'UNKNOWN'}
        if current == binding['prestate'] and staged == binding['staged_state']:
            if row['state'] == 'SUCCEEDED': return {'state':'UNKNOWN'}
            self._hold(op)
            return {'state':'NOT_SWITCHED_HOLD'}
        self._hold(op)
        return {'state':'UNKNOWN'}

    def reconcile_install_guarded(self, op, ownership_guard, recovery_owner):
        """Reconcile install only under the newly claimed recovery epoch."""
        with ownership_guard.with_exclusive_reconciliation(op,recovery_owner) as db:
            raw=db.execute('SELECT request_json,state FROM p3_effect_operations WHERE operation_id=?',(op,)).fetchone()
            if not raw: raise ValueError('OPERATION_NOT_FOUND')
            binding=json.loads(raw[0])['admission'];state=raw[1]
            root=os.fstat(self.root_fd)
            if (root.st_dev,root.st_ino)!=(binding['root_dev'],binding['root_ino']):
                return {'state':'UNKNOWN'}
            try:
                current=snapshot(self.root_fd,binding['current'])
                staged=snapshot(self.root_fd,binding['staged'])
            except Exception:
                return {'state':'UNKNOWN'}
            if current==binding['staged_state'] and staged==binding['prestate']:
                os.fsync(self.root_fd)
                if state in ('RUNNING','UNKNOWN'):
                    count=db.execute('UPDATE p3_effect_operations SET state=?,receipt_json=? WHERE operation_id=? AND state=?',
                        ('SUCCEEDED',json.dumps({'phase':'SWITCHED_RECONCILED'},sort_keys=True,separators=(',',':')),op,state)).rowcount
                    if count!=1:raise RuntimeError('RECONCILE_CAS_CONFLICT')
                elif state!='SUCCEEDED':return {'state':'UNKNOWN'}
                return {'state':'SWITCHED'}
            if current==binding['prestate'] and staged==binding['staged_state']:
                if state=='RUNNING':
                    count=db.execute('UPDATE p3_effect_operations SET state=?,receipt_json=? WHERE operation_id=? AND state=?',
                        ('UNKNOWN',json.dumps({'phase':'UNKNOWN'},sort_keys=True,separators=(',',':')),op,state)).rowcount
                    if count!=1:raise RuntimeError('RECONCILE_CAS_CONFLICT')
                return {'state':'NOT_SWITCHED_HOLD'}
            return {'state':'UNKNOWN'}

    def rollback(self, op, original_op, hook=None):
        if op == original_op:
            raise ValueError('DISTINCT_ROLLBACK_OPERATION_REQUIRED')
        existing = self.store.get(op)
        if existing:
            prior = json.loads(existing['request_json'])['admission']
            if prior.get('rollback_of') != original_op:
                raise ValueError('ROLLBACK_SCOPE_CONFLICT')
            result = self.reconcile(op)
            return {'state':'ROLLED_BACK' if result['state'] == 'SWITCHED' else result['state']}
        original = self.store.get(original_op)
        if not original or original['state'] != 'SUCCEEDED':
            raise PermissionError('COMPLETED_INSTALL_OPERATION_REQUIRED')
        binding = json.loads(original['request_json'])['admission']
        root = os.fstat(self.root_fd)
        if (root.st_dev, root.st_ino) != (binding['root_dev'], binding['root_ino']):
            return {'state':'UNKNOWN'}
        current, staged = binding['current'], binding['staged']
        if (snapshot(self.root_fd, current) != binding['staged_state']
                or snapshot(self.root_fd, staged) != binding['prestate']):
            return {'state':'UNKNOWN'}
        # Both directions are a single renameat2 operation. A first install has
        # no prestate: move current to the now-empty original staging name.
        left, right = (staged, current) if binding['prestate'] else (current, staged)
        result = self.switch(op, left, right, hook, rollback_of=original_op)
        return {'state':'ROLLED_BACK' if result['state'] == 'SWITCHED' else result['state']}
