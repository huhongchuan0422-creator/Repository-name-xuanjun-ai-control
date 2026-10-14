"""Concrete finite epoch7 host primitives. No CLI and no default admission.

The protected loader must authenticate these module bytes, the complete plan,
source package, snapshot policy, fresh snapshot and complete approval first.
These primitives never run the frozen v4 retained-runtime/TLS apply methods.
"""
import copy
import errno
import fcntl
import hashlib
import json
import os
import socket
import stat
import time

import epoch7_delta as d
import epoch7_snapshot as snap
import epoch7_protected_fs as fs
from epoch7_recovery_sequence import OUTER_NAME, PHASES, CLEANUP, observation
from epoch7_complete_approval import CompleteApprovalVerifier
from epoch7_bounded_stager import FrozenBoundedInstaller
from activation_control import ActivationStore

MANIFEST = '26ae77d8fff38c8a69ddcf3e35caeb18d4724ab17eca8fbecf9dc4f76bc797aa'
SOURCE = '101b465ca3554bf34fef2d53d6006b96d85c4a63'
SOURCE_TREE = '3ae50b40c38d9a807876c175818299e344d53134'
BRIDGE_SHA256 = '3a5e72e5c3f24c718807ad1d87299358440469dc18c87339721008a93fdcb0c3'
READY = 'READY_ISSUED_AND_RENEWAL_DRYRUN_VERIFIED'
TLS_JOURNAL = fs.TRANSACTION + '/tls-lifecycle.json'
TLS_CANDIDATE = fs.TRANSACTION + '/epoch8-tls-renewal-candidate.json'
ARCHIVES = frozenset(('epoch7-prior-tls-lifecycle.json',
                     'epoch7-prior-native-binding.json'))
PHASE_PATHS = {'rebind_prepared_epoch': frozenset((snap.NATIVE, TLS_CANDIDATE)),
              'rebind_tls_metadata_only': frozenset((TLS_JOURNAL,))}
MAXIMUM = 1048576


def need(value, reason):
    if not value:
        raise ValueError('EPOCH7_HOST_' + reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    return snap.decode(raw)


def packed(value):
    return d.canonical(value) + b'\n'


def record_digest(record):
    return d.digest({k: sha(v) if k == 'data' else v for k, v in record.items()})


class ExistingInstallLock(object):
    """Open only the measured existing lock; never create, repair or replace it."""
    def __init__(self, expected, root='/'):
        need(type(expected) is dict and set(expected) == set(fs.metadata(os.stat(__file__))) |
             {'kind', 'sha256'}, 'LOCK_EXACT_MEASURED_RECORD')
        need(expected['kind'] == 'FILE' and expected['uid'] == 0 and
             expected['gid'] == 0 and expected['mode'] == 0o600 and
             expected['nlink'] == 1, 'LOCK_IDENTITY')
        self.expected, self.root = copy.deepcopy(expected), root
        self.fd = None
        self.entered = False
        self.path = (root.rstrip('/') if root != '/' else '') + snap.INSTALL_LOCK

    def __enter__(self):
        need(self.fd is None and not self.entered, 'LOCK_OBJECT_SINGLE_USE')
        self.entered = True
        need(os.path.realpath(self.path) == self.path, 'LOCK_PATH_ALIAS')
        fd = os.open(self.path, fs.READ_FLAGS)
        try:
            info = os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and fs.metadata(info) ==
                 {k: v for k, v in self.expected.items() if k not in ('kind', 'sha256')}, 'LOCK_CHANGED')
            need(fs.stamp(os.lstat(self.path)) == fs.stamp(info), 'LOCK_PATH_CHANGED')
            raw = os.read(fd, MAXIMUM + 1)
            need(len(raw) <= MAXIMUM and sha(raw) == self.expected['sha256'], 'LOCK_BYTES_CHANGED')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.fd = fd
            need(self.held(), 'LOCK_POST_ACQUIRE_CHANGED')
            return self
        except BaseException:
            if self.fd == fd: self.fd = None
            os.close(fd)
            raise

    def held(self):
        if self.fd is None: return False
        need(fs.metadata(os.fstat(self.fd)) ==
             {k: v for k, v in self.expected.items() if k not in ('kind', 'sha256')} and
             fs.stamp(os.lstat(self.path)) == fs.stamp(os.fstat(self.fd)), 'LOCK_REPLACED')
        return True

    def __exit__(self, unused_type, unused_value, unused_tb):
        fd, self.fd = self.fd, None
        if fd is not None: os.close(fd)
        return False


class BoundedActivationStore(ActivationStore):
    """Frozen activation journal implementation with existing, nonblocking lock."""
    def __init__(self, lock_record, fixture_root=None):
        root = ''
        owner = 0
        if fixture_root is not None:
            base = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'fixtures')
            need(fixture_root.startswith(base + '/') and os.path.realpath(fixture_root) == fixture_root,
                 'ACTIVATION_FIXTURE_CONFINEMENT')
            root, owner = fixture_root, os.geteuid()
        need(type(lock_record) is dict and set(lock_record) == set(fs.metadata(os.stat(__file__))) |
             {'kind','sha256'} and lock_record['kind'] == 'FILE' and
             (lock_record['uid'], lock_record['mode'], lock_record['nlink']) == (owner,0o644,1),
             'ACTIVATION_MEASURED_EXISTING_LOCK')
        self.lock_record = copy.deepcopy(lock_record)
        super(BoundedActivationStore,self).__init__(root+snap.ACTIVE,root+snap.EPOCHS,
                                                   root+snap.ACTIVATION_LOCK,owner_uid=owner)

    def _locked(self):
        self._check_parent()
        need(os.path.realpath(self.lock_path) == self.lock_path, 'ACTIVATION_LOCK_PATH')
        fd = os.open(self.lock_path,fs.READ_FLAGS)
        try:
            info = os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and fs.metadata(info) ==
                 {k:v for k,v in self.lock_record.items() if k not in ('kind','sha256')} and
                 fs.stamp(info) == fs.stamp(os.lstat(self.lock_path)), 'ACTIVATION_LOCK_DRIFT')
            raw = os.read(fd,MAXIMUM+1)
            need(len(raw) <= MAXIMUM and sha(raw) == self.lock_record['sha256'], 'ACTIVATION_LOCK_BYTES')
            fcntl.flock(fd,fcntl.LOCK_EX | fcntl.LOCK_NB)
            need(fs.stamp(info) == fs.stamp(os.fstat(fd)) == fs.stamp(os.lstat(self.lock_path)),
                 'ACTIVATION_LOCK_ACQUIRE_RACE')
            return fd
        except BaseException:
            os.close(fd)
            raise


class ClaimAuthority(object):
    """Independent receipt authority, deliberately not RecoveryGate.check().

    Runtime failure cannot revoke the held lock + authenticated claim binding
    needed to write HOLD. Live phase effects additionally need exact phase INTENT.
    """
    def __init__(self, lock, verifier, context, binding):
        need(isinstance(lock, ExistingInstallLock) and
             isinstance(verifier, CompleteApprovalVerifier), 'EXACT_AUTHORITY_TYPES')
        self.lock, self.verifier = lock, verifier
        self.context, self.binding = copy.deepcopy(context), copy.deepcopy(binding)
        self.digest = d.digest({'context': context, 'binding': binding})
        self.io = None

    def receipt(self):
        need(self.lock.held() is True, 'INSTALL_LOCK_REQUIRED')
        need(d.digest({'context': self.context, 'binding': self.binding}) == self.digest,
             'AUTHORITY_BINDING_MUTATED')
        self.verifier._bound()
        need(self.verifier.checked_under_lock is True and self.verifier.cached is not None and
             d.same(self.verifier.context, self.context) and
             self.verifier.cached['body_sha256'] == self.binding['approval_body_sha256'] and
             self.verifier.review_id == self.binding['review_id'], 'AUTHENTICATED_LOCKED_REVIEW_REQUIRED')

    def validate_outer(self, raw):
        value = decode(raw)
        need(packed(value) == raw and set(value) == {'schema', 'name', 'transaction_id',
             'context_sha256', 'binding', 'state'} and value['schema'] == 1 and
             value['name'] == OUTER_NAME and value['transaction_id'] == d.TX and
             value['context_sha256'] == self.context['context_sha256'] and
             d.same(value['binding'], self.binding) and type(value['state']) is dict,
             'OUTER_CLAIM_BINDING')
        return value

    def cleanup(self, operation, unit=None):
        self.receipt()
        need((operation, unit) in CLEANUP and self.io is not None, 'FIXED_CLEANUP_REQUIRED')
        value = self.validate_outer(self.io.read_journal(OUTER_NAME)['data'])
        need(value['state'].get('admission') == 'ADMITTED', 'CLEANUP_ADMITTED_OUTER_CLAIM')
        return value

    def phase(self, phase):
        self.receipt()
        need(phase in PHASES and self.io is not None, 'FIXED_PHASE_REQUIRED')
        value = self.validate_outer(self.io.read_journal(OUTER_NAME)['data'])
        need(value['state'].get('admission') == 'ADMITTED' and
             value['state'].get('stage') == phase + '_INTENT' and
             value['state'].get('completed') == list(PHASES[:PHASES.index(phase)]),
             'DURABLE_EXACT_PHASE_INTENT')
        return value


class HostPhaseFilesystem(fs.ProtectedFilesystem):
    """Reuse fd-relative protected IO for only outer receipt and finite sidefiles.

    Not a replacement for inner ProtectedFilesystem. The parent namespace and
    journals stay root-only/basic-ACL. It may still record HOLD after TLS,
    sandbox, database ownership or activation state changes.
    """
    def __init__(self, authority, fixture_root=None):
        need(isinstance(authority, ClaimAuthority), 'CLAIM_AUTHORITY_REQUIRED')
        self.authority = authority
        self.fixture = fixture_root is not None
        self.owner, self.group = 0, 0
        if self.fixture:
            base = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'fixtures')
            need(type(fixture_root) is str and fixture_root.startswith(base + '/') and
                 os.path.realpath(fixture_root) == fixture_root, 'FIXTURE_CONFINEMENT')
            self.root = fixture_root
            self.owner, self.group = os.geteuid(), os.getegid()
        else:
            need(os.geteuid() == 0 and socket.gethostname().split('.')[0] == snap.HOST,
                 'FIXED_HOST_ROOT_REQUIRED')
            self.root = '/'
        fd = os.open(self.root, fs.DIR_FLAGS)
        try:
            self._check_parent(os.fstat(fd))
            self.root_identity = (os.fstat(fd).st_dev, os.fstat(fd).st_ino)
        finally: os.close(fd)
        authority.io = self

    def _authorize(self):
        self.authority.receipt()
        info = os.stat(self.root, follow_symlinks=False)
        need((info.st_dev, info.st_ino) == self.root_identity, 'NAMESPACE_CHANGED')
        self._check_parent(info)

    def require_phase(self, phase):
        self._authorize()
        return self.authority.phase(phase)

    def journal_exists(self, name):
        need(name == OUTER_NAME, 'OUTER_ONLY')
        parent = self._journal_parent()
        try:
            try: os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError: return False
            return True
        finally: os.close(parent)

    def read_journal(self, name):
        need(name == OUTER_NAME, 'OUTER_ONLY')
        parent = self._journal_parent()
        try:
            info, raw = self._read_at(parent, name, maximum=262144)
            need((info['uid'], info['gid'], info['mode']) ==
                 (self.owner, self.group, 0o600), 'OUTER_PRIVATE_IDENTITY')
            info.pop('kind'); info.pop('sha256'); info['data'] = raw
            return info
        finally: os.close(parent)

    def create_exclusive(self, name, raw, uid, gid, mode):
        need(name == OUTER_NAME and (uid, gid, mode) == (0, 0, 0o600) and
             len(raw) <= 262144, 'OUTER_CREATE_SCOPE')
        self._authorize(); self.authority.validate_outer(raw)
        parent = self._journal_parent()
        try: self._exclusive_at(parent, name, raw, self.owner, self.group, mode)
        finally: os.close(parent)

    def replace_exact(self, name, expected, raw, uid, gid, mode):
        need(name == OUTER_NAME and (uid, gid, mode) == (0, 0, 0o600) and
             len(raw) <= 262144, 'OUTER_REPLACE_SCOPE')
        self._authorize(); self.authority.validate_outer(raw)
        self.authority.validate_outer(expected['data'])
        need(self.read_journal(name) == expected, 'OUTER_FULL_CAS')
        parent = self._journal_parent()
        try: self._replace_at(parent, name, expected, raw, self.owner, self.group, mode)
        finally: os.close(parent)

    def release_parent(self):
        parent, leaf = self._parent('/opt/xuanjun-control-releases')
        fd = None
        try:
            fd = os.open(leaf, fs.DIR_FLAGS, dir_fd=parent)
            info = os.fstat(fd)
            need(fs.stamp(info) == fs.stamp(os.stat(leaf, dir_fd=parent, follow_symlinks=False)),
                 'RELEASE_PARENT_FD_CHANGED')
            self._check_parent(info); self._no_acl(fd, directory=True)
            need(stat.S_IMODE(info.st_mode) == 0o750, 'RELEASE_PARENT_EXACT_MODE')
            names = sorted(os.listdir(fd))
            need(len(names) <= 128 and fs.stamp(os.fstat(fd)) == fs.stamp(info), 'RELEASE_PARENT_SCAN_RACE')
            return dict(fs.metadata(info), kind='DIRECTORY', access_acl='user::rwx\ngroup::r-x\nother::---\n',
                        default_acl='', sha256=None), names
        finally:
            if fd is not None: os.close(fd)
            os.close(parent)

    def read_exact(self, path):
        need(path in {snap.NATIVE, TLS_JOURNAL, TLS_CANDIDATE} or
             path in {fs.TRANSACTION + '/' + name for name in d.PRESERVED_RECEIPTS | ARCHIVES},
             'FIXED_READ_PATH')
        parent, name = self._parent(path)
        try:
            row, raw = self._read_at(parent, name)
            return raw, row
        finally: os.close(parent)

    def archive_exact(self, phase, name, raw):
        required = {'epoch7-prior-native-binding.json': 'rebind_prepared_epoch',
                    'epoch7-prior-tls-lifecycle.json': 'rebind_tls_metadata_only'}
        need(name in required and required[name] == phase, 'ARCHIVE_SCOPE')
        self.require_phase(phase)
        parent = self._journal_parent()
        try:
            self._exclusive_at(parent, name, raw, self.owner, self.group, 0o600)
            row, observed = self._read_at(parent, name)
            need(observed == raw and row['mode'] == 0o600, 'ARCHIVE_READBACK')
            return row
        finally: os.close(parent)

    def replace_file_exact(self, phase, path, before, raw, uid, gid, mode):
        need(path in PHASE_PATHS.get(phase, ()) and path != TLS_CANDIDATE and
             (uid, gid, mode) == ((0, 0, 0o644) if path == snap.NATIVE else (0, 0, 0o600)),
             'SIDEFILE_EFFECT_SCOPE')
        self.require_phase(phase)
        parent, name = self._parent(path)
        try:
            observed, unused = self._read_at(parent, name)
            need(d.same(observed, before), 'SIDEFILE_FULL_BEFORE_CAS')
            self._replace_at(parent, name, before, raw, self.owner, self.group, mode)
            observed, current = self._read_at(parent, name)
            need(current == raw and observed['mode'] == mode and observed['nlink'] == 1,
                 'SIDEFILE_READBACK')
            return observed
        finally: os.close(parent)

    def publish_tls_candidate(self, raw):
        self.require_phase('rebind_prepared_epoch')
        parent, name = self._parent(TLS_CANDIDATE)
        try:
            self._exclusive_at(parent, name, raw, self.owner, self.group, 0o600)
            row, current = self._read_at(parent, name)
            need(current == raw, 'TLS_CANDIDATE_READBACK')
            return row
        finally: os.close(parent)


def rebind_prepared_epoch7(store, expected, proposed, proof):
    """Finite reuse of the frozen activation append/publish CAS, epochs7→8."""
    expected, proposed = store.validate(expected), store.validate(proposed)
    need(os.geteuid() == store.owner_uid and expected['state'] == 'PREPARED' and
         expected['epoch'] == 7 and proposed['state'] == 'PREPARED' and
         proposed['epoch'] == 8, 'EXACT_PREPARED_EPOCHS')
    need(all(d.same(expected[k], proposed[k]) for k in d.CANONICAL_IDENTITY),
         'CANONICAL_ACTIVATION_IDENTITY')
    need(expected['release_sha256'] == d.OLD_MANIFEST and
         proposed['release_sha256'] == MANIFEST, 'EXACT_RELEASE_TRANSITION')
    transition = d.controller_transition(expected, proposed)
    required = {'controller_transition_sha256', 'approval_body_sha256', 'snapshot_sha256', 'recovery_plan_sha256',
        'old_descriptor_sha256', 'new_descriptor_sha256', 'all_writers_excluded',
        'install_lock_held', 'retained_resources_verified'}
    need(type(proof) is dict and set(proof) == required, 'REBIND_PROOF_SCHEMA')
    for key in required - {'all_writers_excluded', 'install_lock_held', 'retained_resources_verified'}:
        d.hash_value(proof[key])
    need(all(proof[k] is True for k in ('all_writers_excluded', 'install_lock_held',
         'retained_resources_verified')) and
         proof['old_descriptor_sha256'] == store.head(expected) and
         proof['new_descriptor_sha256'] == store.head(proposed) and
         proof['controller_transition_sha256'] == d.digest(transition), 'REBIND_PROOF_BINDING')
    lock = store._locked()
    try:
        rows = store._journal()
        need(rows and d.same(rows[-1][0]['descriptor'], expected) and
             d.same(store._read_descriptor_unlocked(), expected), 'REBIND_STALE_HEAD')
        store._append(proposed, rows, dict(proof, recovery='EXACT_EPOCH7_RELEASE_REBIND',
                       writer_admission=False, previous_epoch=7))
        store._write_descriptor(proposed)
        need(d.same(store._read_descriptor_unlocked(), proposed) and
             d.same(store._journal()[-1][0]['descriptor'], proposed), 'REBIND_PUBLICATION_UNKNOWN')
        return copy.deepcopy(proposed)
    finally: os.close(lock)


def tls_metadata_candidate(before_raw, new_config_raw, expected_tls):
    """Pure release-only transform. No certbot import, subprocess or network."""
    before, config = decode(before_raw), decode(new_config_raw)
    need(sha(before_raw) == expected_tls['journal_sha256'] and
         before.get('state') == expected_tls['state'] == READY and
         before.get('certificate_sha256') == expected_tls['certificate_sha256'] and
         before.get('fingerprint') == expected_tls['tree_fingerprint_sha256'], 'RETAINED_READY_TLS_REQUIRED')
    d.tls_config_rebind(before['config'], config)
    need(config['release_sha256'] == MANIFEST and
         d.digest({k: v for k, v in config.items() if k != 'release_sha256'}) ==
         expected_tls['config_identity_sha256'], 'TLS_CONFIG_BINDING')
    after = copy.deepcopy(before); after['config'] = config
    # Existing state, certificate, tree fingerprint, issuance history and all
    # unrelated metadata remain byte-equivalent as parsed values.
    need(set(before) == set(after) and all(d.same(before[k], after[k])
         for k in before if k != 'config'), 'TLS_METADATA_ONLY')
    return packed(after)


class CoreHostPhases(object):
    """Concrete pre-active effects wired to a phase-aware host observer.

    observer.check(phase) must be the complete live adapter, not RecoveryGate.
    observer.tls_contents() supplies fresh certificate/tree evidence from the
    snapshot collector's concrete TLS routine. No permissive default exists.
    """
    def __init__(self, io, store, observer, context, plan_sha256, snapshot,
                 candidate, native_before, native_after, native_metadata,
                 tls_config_raw, installer, artifact):
        need(isinstance(io, HostPhaseFilesystem) and isinstance(store, BoundedActivationStore),
             'PROTECTED_PHASE_IO_AND_BOUNDED_ACTIVATION_REQUIRED')
        d.hash_value(plan_sha256)
        need(candidate['manifest_sha256'] == context['runtime_manifest_sha256'] == MANIFEST,
             'EXACT_CANDIDATE_MANIFEST')
        need(type(native_before) is bytes and type(native_after) is bytes and
             sha(native_before) == native_metadata['sha256'], 'NATIVE_BYTES_BINDING')
        from epoch7_bindings import RETAINED_NATIVE_SHA
        need(sha(native_before) == RETAINED_NATIVE_SHA, 'RECOGNIZED_NATIVE_BEFORE')
        old, new = decode(native_before), decode(native_after)
        need(set(old) == set(new) == {'ledger', 'gatewayIdentity'} and
             d.same(old['gatewayIdentity'], new['gatewayIdentity']) and
             all(old['ledger'][k] == new['ledger'][k] for k in ('python', 'pythonSha256', 'config')),
             'NATIVE_IDENTITY_RETENTION')
        bridge = '/opt/xuanjun-control-releases/integration-' + MANIFEST[:16] + '/stage1/native_ledger_bridge.py'
        need(new['ledger']['bridge'] == bridge and set(new['ledger']['files']) ==
             {bridge, new['ledger']['config']} and new['ledger']['files'][bridge] == BRIDGE_SHA256 and
             new['ledger']['files'][new['ledger']['config']] ==
             candidate['targets'][new['ledger']['config']]['sha256'], 'NATIVE_AFTER_BINDING')
        need(isinstance(installer, FrozenBoundedInstaller) and artifact['source_commit'] == SOURCE and
             artifact['manifest_sha256'] == MANIFEST and artifact['source_tree'] == SOURCE_TREE and
             artifact['releases'] == '/opt/xuanjun-control-releases', 'PINNED_INSTALLER_CONTRACT')
        tls_config = decode(tls_config_raw)
        need(sha(tls_config_raw) == candidate['targets']['/etc/xuanjun-development/tls-renewal.json']['sha256'] and
             tls_config['release_sha256'] == MANIFEST and
             d.digest({k:v for k,v in tls_config.items() if k != 'release_sha256'}) == snapshot['tls']['config_identity_sha256'],
             'EXACT_TLS_CANDIDATE_BYTES')
        self.io, self.store, self.observer = io, store, observer
        self.context, self.snapshot, self.candidate = copy.deepcopy(context), copy.deepcopy(snapshot), copy.deepcopy(candidate)
        self.plan_sha, self.native_before, self.native_after = plan_sha256, native_before, native_after
        self.native_metadata, self.tls_raw = copy.deepcopy(native_metadata), tls_config_raw
        self.installer, self.artifact = installer, copy.deepcopy(artifact)
        self.started = set(); self.current = copy.deepcopy(snapshot['activation'])

    def _enter(self, context, phase):
        need(d.same(context, self.context) and phase not in self.started, 'PHASE_NO_RETRY_OR_REBIND')
        self.io.require_phase(phase)
        self.observer.check(phase)
        self.started.add(phase)

    def stage_exact_release(self, context, diagnostics):
        phase = 'stage_exact_release'; self._enter(context, phase)
        a = self.artifact
        parent_before, names_before = self.io.release_parent()
        self.installer.verify(a['root'], a['manifest'], SOURCE, MANIFEST, a['source_tree'])
        result = self.installer.install(a['root'], a['manifest'], SOURCE, MANIFEST,
            a['releases'], enforce_root=True, expected_tree=a['source_tree'])
        need(result == a['releases'] + '/integration-' + MANIFEST[:16], 'STAGED_RELEASE_PATH')
        # Exact byte verification happens before and after the frozen stager.
        self.installer.verify(a['root'], a['manifest'], SOURCE, MANIFEST, a['source_tree'])
        parent_after, names_after = self.io.release_parent()
        need(names_after == sorted(names_before + ['integration-' + MANIFEST[:16]]) and
             all(parent_after[k] == parent_before[k] for k in ('dev','ino','uid','gid','mode','access_acl','default_acl')),
             'RELEASE_PARENT_UNRELATED_CHANGE')
        self.staged_release_parent = copy.deepcopy(parent_after)
        return observation(context, phase, d.digest({'release': result, 'manifest_sha256': MANIFEST, 'files': 107,
                                                    'release_parent': parent_after}))

    def preserve_prior_receipts(self, context, diagnostics):
        phase = 'preserve_prior_receipts'; self._enter(context, phase)
        checked = {}
        for name, expected in sorted(self.snapshot['receipts'].items()):
            raw, row = self.io.read_exact(fs.TRANSACTION + '/' + name)
            need(sha(raw) == expected and row['mode'] == 0o600, 'PRESERVED_RECEIPT_CHANGED')
            checked[name] = expected
        return observation(context, phase, d.digest(checked))

    def rebind_prepared_epoch(self, context, diagnostics):
        phase = 'rebind_prepared_epoch'; self._enter(context, phase)
        proposed = self.candidate['activation']
        delta = d.build_delta(self.snapshot, context['snapshot_sha256'], self.candidate)
        need(d.digest(delta) == context['delta_sha256'], 'REBIND_APPROVED_DELTA')
        transition = d.controller_transition(self.current, proposed)
        need(d.same(transition, delta['controller_transition']), 'REBIND_APPROVED_CONTROLLER')
        proof = {'controller_transition_sha256': d.digest(transition),
            'approval_body_sha256': self.io.authority.binding['approval_body_sha256'],
            'snapshot_sha256': context['snapshot_sha256'], 'recovery_plan_sha256': self.plan_sha,
            'old_descriptor_sha256': self.store.head(self.current),
            'new_descriptor_sha256': self.store.head(proposed), 'all_writers_excluded': True,
            'install_lock_held': True, 'retained_resources_verified': True}
        self.current = rebind_prepared_epoch7(self.store, self.current, proposed, proof)
        raw, before = self.io.read_exact(snap.NATIVE)
        need(raw == self.native_before and d.same(before, self.native_metadata), 'NATIVE_BEFORE_CHANGED')
        saved = self.io.archive_exact(phase, 'epoch7-prior-native-binding.json', raw)
        need(self.io.read_exact(snap.NATIVE) == (raw, before), 'NATIVE_ARCHIVE_RACE')
        after = self.io.replace_file_exact(phase, snap.NATIVE, before, self.native_after, 0, 0, 0o644)
        tls = self.io.publish_tls_candidate(self.tls_raw)
        return observation(context, phase, d.digest({'activation': self.current,
            'native_before_sha256': saved['sha256'], 'native_after': after, 'tls_candidate': tls}))

    def quiesce_exact_epoch(self, context, diagnostics):
        phase = 'quiesce_exact_epoch'; self._enter(context, phase)
        proof = self.observer.quiescence()
        need(type(proof) is dict and all(proof.get(k) is True for k in
             ('identity_verified', 'coordinator_inactive', 'parent_unit_inactive', 'cgroups_empty', 'restart_inhibited')),
             'LIVE_QUIESCENCE_REQUIRED')
        self.current = self.store.transition('PREPARED', 'QUIESCED', 8, self.current['instance'], proof)
        need(self.current == dict(self.candidate['activation'], state='QUIESCED'), 'QUIESCED_IDENTITY_CHANGED')
        return observation(context, phase, d.digest(self.current))

    def rebind_tls_metadata_only(self, context, diagnostics):
        phase = 'rebind_tls_metadata_only'; self._enter(context, phase)
        old, before = self.io.read_exact(TLS_JOURNAL)
        new = tls_metadata_candidate(old, self.tls_raw, self.snapshot['tls'])
        wanted = {k: self.snapshot['tls'][k] for k in ('certificate_sha256', 'tree_fingerprint_sha256')}
        need(self.observer.tls_contents() == wanted, 'TLS_CONTENT_BEFORE_CHANGED')
        self.io.archive_exact(phase, 'epoch7-prior-tls-lifecycle.json', old)
        need(self.io.read_exact(TLS_JOURNAL) == (old, before), 'TLS_ARCHIVE_RACE')
        after = self.io.replace_file_exact(phase, TLS_JOURNAL, before, new, 0, 0, 0o600)
        need(self.observer.tls_contents() == wanted, 'TLS_CONTENT_AFTER_CHANGED')
        return {'observation': observation(context, phase, d.digest(after)),
                'tls_change': copy.deepcopy(context['tls_change'])}

    def activate_exact_epoch(self, context, diagnostics):
        phase = 'activate_exact_epoch'; self._enter(context, phase)
        # The phase observer must verify the exact durable database-reopen and
        # runtime-access observations before admitting this irreversible edge.
        self.current = self.store.transition('QUIESCED', 'ACTIVE', 8,
            self.current['instance'], {'database_reopened': True})
        need(self.current == dict(self.candidate['activation'], state='ACTIVE'), 'ACTIVE_IDENTITY_CHANGED')
        return observation(context, phase, d.digest(self.current))

    def handlers(self):
        return {name: getattr(self, name) for name in (
            'stage_exact_release', 'preserve_prior_receipts', 'rebind_prepared_epoch',
            'quiesce_exact_epoch', 'rebind_tls_metadata_only', 'activate_exact_epoch')}
