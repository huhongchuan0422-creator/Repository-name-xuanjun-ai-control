"""Controlled recovery apply and fresh production admission. Never discovers state.

The socket provider MUST be an existing trusted management executor. This
client does not revoke credentials or invent host/transaction observations.
"""
import fcntl
import json
import os
import socket
import sqlite3
import stat
import struct
import time
import uuid
from urllib.parse import quote

# Injected only by the SHA-pinned bootstrap, never from sys.path.
r = None


class UnixEvidenceProvider(object):
    """Root Unix socket, peer credentials, bounded framing and three signatures."""
    def __init__(self, socket_path, keys):
        self.path, self.keys = r.path(socket_path), keys

    def query(self, request, operation):
        r.need(operation in ('recovery_apply', 'execution_gate'), 'PROVIDER_OPERATION')
        parent = r.directory(os.path.dirname(self.path))
        try:
            before = os.stat(os.path.basename(self.path), dir_fd=parent, follow_symlinks=False)
            r.need(stat.S_ISSOCK(before.st_mode) and before.st_uid == 0 and
                   stat.S_IMODE(before.st_mode) == 0o600, 'PROVIDER_SOCKET')
            probe = {'schema': 1, 'operation': operation,
                     'request_sha256': r.sha(r.canonical(request)),
                     'challenge': uuid.uuid4().hex}
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(5)
                client.connect('/proc/self/fd/' + str(parent) + '/' + os.path.basename(self.path))
                unused_pid, uid, unused_gid = struct.unpack('3i', client.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
                r.need(uid == 0, 'PROVIDER_PEER')
                after = os.stat(os.path.basename(self.path), dir_fd=parent, follow_symlinks=False)
                r.need((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino),
                       'PROVIDER_REPLACED')
                raw = r.canonical(probe)
                client.sendall(struct.pack('!I', len(raw)) + raw)
                def exact(size):
                    data = b''
                    while len(data) < size:
                        chunk = client.recv(size - len(data))
                        r.need(bool(chunk), 'PROVIDER_UNKNOWN')
                        data += chunk
                    return data
                size = struct.unpack('!I', exact(4))[0]
                r.need(0 < size <= r.MAX, 'PROVIDER_BOUND')
                response = r.decode(exact(size))
        finally:
            os.close(parent)
        r.fields(response, 'body signatures')
        body = response['body']
        r.fields(body, 'schema probe issued_utc expires_utc packet reservation')
        now = int(time.time())
        r.need(type(body['schema']) is int and body['schema'] == 1 and r.canonical(body['probe']) == r.canonical(probe) and
               type(body['issued_utc']) is int and type(body['expires_utc']) is int and
               body['issued_utc'] <= now < body['expires_utc'] <= body['issued_utc'] + 30,
               'PROVIDER_REPLAY_OR_EXPIRED')
        r.need(type(response['signatures']) is dict and set(response['signatures']) == r.ROLES,
               'PROVIDER_SIGNATURES')
        for role in sorted(r.ROLES):
            r.signature(body, response['signatures'][role], self.keys[role])
        expected = {'old_authority_id': request['old_authority_id'],
            'authority_id': request['new_authority_id'], 'epoch': request['new_epoch'],
            'fence': request['new_epoch'], 'writer_id': request['writer_id'],
            'grant_id': request['new_grant_id'], 'database': request['target_database'],
            'plan_sha256': self.plan_ref['sha256'], 'exclusive': True}
        r.need(r.canonical(body['reservation']) == r.canonical(expected), 'GLOBAL_AUTHORITY_RESERVATION_REQUIRED')
        # Fresh query must still prove the complete old-authority isolation and
        # historical reconciliation contract. UNKNOWN cannot authorize writes.
        r.need(self.plan_ref in body['packet']['body']['sources'], 'FRESH_PLAN_NOT_SIGNED')
        r.need(r.canonical(body['packet']['body']['restoration']) ==
               r.canonical(self.restoration), 'LIVE_RESTORATION_CHANGED')
        return r.decide(request, body['packet'], self.keys, now)


def historical_recipe(request, packet, keys):
    # A stored signed recipe may outlive its initial evidence window. It is
    # never current permission: the online, nonce-bound three-signature packet
    # must independently pass decide(now) before any production write/entry.
    issued = packet['body']['issued_utc']
    r.need(type(issued) is int and issued <= int(time.time()), 'RECIPE_FUTURE')
    return r.decide(request, packet, keys, now=issued)


def load_plan(ref, request):
    r.reference(ref)
    plan = r.decode(r.read(ref['path'], ref['sha256']))
    r.fields(plan, 'schema request_sha256 config registry_record registry_root assembly_manifest assembly_root kit_root loader_sha256 kit_manifest_sha256 provider_socket checkpoint_root')
    r.need(type(plan['schema']) is int and plan['schema'] == 1 and
           plan['request_sha256'] == r.sha(r.canonical(request)), 'APPLY_PLAN_BINDING')
    for key in ('config', 'registry_record', 'assembly_manifest'):
        r.reference(plan[key])
    for key in ('registry_root', 'assembly_root', 'kit_root', 'provider_socket', 'checkpoint_root'):
        r.path(plan[key])
    for key in ('loader_sha256', 'kit_manifest_sha256'):
        r.pin(plan[key])
    r.ident(request['recovery_id'] + '-apply')
    return plan


def signed_plan(request, packet, plan_ref):
    # The three signatures cover the exact plan reference through sources.
    r.need(plan_ref in packet['body']['sources'], 'PLAN_NOT_SIGNED')
    return load_plan(plan_ref, request)


def database_metadata(path):
    fd = r.opened(path)
    info = os.fstat(fd)
    os.close(fd)
    for suffix in ('-journal', '-wal', '-shm'):
        r.need(not os.path.lexists(path + suffix), 'DATABASE_RECOVERY_REQUIRED')
    db = sqlite3.connect('file:' + quote(path, safe='/') + '?mode=ro', uri=True, timeout=1)
    try:
        db.execute('PRAGMA query_only=ON')
        rows = db.execute('SELECT binding FROM p2_authority_recovery').fetchall()
        r.need(len(rows) == 1, 'AUTHORITY_PROVENANCE')
        return r.decode(rows[0][0].encode('ascii')), (info.st_dev, info.st_ino)
    finally:
        db.close()


def binding(request, plan_ref, cfg):
    return {'request_sha256': r.sha(r.canonical(request)), 'plan_sha256': plan_ref['sha256'],
            'authority_id': request['new_authority_id'], 'epoch': request['new_epoch'],
            'writer_id': request['writer_id'], 'grant_sha256': r.sha(r.canonical(cfg['grant']))}


def validate_config(request, plan, registry, assembly):
    raw = r.read(plan['registry_record']['path'], plan['registry_record']['sha256'])
    record, cfg = registry.verified_record(raw)
    r.need(record['config'] == plan['config'], 'RECOVERY_CONFIG_REF')
    r.need(cfg['database'] == request['target_database'] and
           cfg['principal']['writer_id'] == request['writer_id'] and
           cfg['grant']['grant_id'] == request['new_grant_id'] and
           cfg['grant']['target_host'] == request['host'] and
           cfg['grant']['max_attempts'] == 5 and
           cfg['grant']['recovery_entry'] == 'p2_recovery.entry' and
           cfg['grant']['expires_utc'] > int(time.time()), 'RECOVERY_CONFIG_SCOPE')
    entry = plan['assembly_root'] + '/production/p2_attempt5/entry.py'
    # The new assembly Manifest includes this executor and entry wrapper. The
    # Grant binds its exact Commit/Tree and SHA; old Grants cannot authorize it.
    manifest = r.decode(r.read(plan['assembly_manifest']['path'],
                               plan['assembly_manifest']['sha256']))
    r.need(manifest['inherited_kit_sha256'] == cfg['grant']['kit_sha256'] ==
           '2fdc934a336414086361764a4a77894a597a51a53c7693420eaed5cefed3e1d3' and
           manifest['inherited_manifest_sha256'] == plan['kit_manifest_sha256'] ==
           '243bc01b1e9c7d2cb302f800556002abcebcfa9f96c298e4275e15d8b1346e1e' and
           manifest['runtime_source_commit'] == r.SOURCE and manifest['runtime_source_tree'] == r.TREE,
           'INHERITED_KIT_AND_RUNTIME_BINDING')
    root = plan['assembly_root']
    r.need(os.path.dirname(plan['assembly_manifest']['path']) == root, 'RELEASE_ROOT')
    for name in ('executor.py', 'recovery.py', 'entry.py', 'bootstrap.py'):
        relative = 'production/p2_recovery/' + name
        r.need(relative in manifest['files'] and
               r.sha(r.read(root + '/' + relative, bound=1048576)) == manifest['files'][relative],
               'RECOVERY_EXECUTABLE_CLOSURE')
        # Reject a plan attempting to pin a different executor implementation.
        r.need(r.sha(r.read(root + '/' + relative, bound=1048576)) ==
               r.sha(r.read(os.path.dirname(__file__) + '/' + name, bound=1048576)),
               'RECOVERY_EXECUTABLE_IDENTITY')
    assembly.release_identity(plan['assembly_manifest']['path'],
        plan['assembly_manifest']['sha256'], cfg['grant'], entry,
        manifest['files']['production/p2_attempt5/assembly.py'], plan['kit_manifest_sha256'])
    r.need(cfg['grant']['source_commit'] != r.SOURCE, 'NEW_SOURCE_NEW_GRANT_REQUIRED')
    return record, cfg, manifest


class RecoveryGate(object):
    def __init__(self, request, packet, keys, plan_ref, registry, assembly):
        self.request, self.packet, self.keys, self.ref = request, packet, keys, plan_ref
        self.plan = signed_plan(request, packet, plan_ref)
        self.registry, self.assembly = registry, assembly
        historical_recipe(request, packet, keys)
        self.provider = UnixEvidenceProvider(self.plan['provider_socket'], keys)
        self.provider.plan_ref = plan_ref
        self.provider.restoration = packet['body']['restoration']

    def verify(self, operation='execution_gate', require_committed=True):
        # The initial packet is checked when the gate is constructed. Every
        # subsequent call gets a fresh, challenge-bound management attestation.
        result = self.provider.query(self.request, operation)
        record, cfg, manifest = validate_config(self.request, self.plan, self.registry, self.assembly)
        if require_committed:
            expected = binding(self.request, self.ref, cfg)
            actual, inode = database_metadata(cfg['database'])
            r.need(actual == expected, 'AUTHORITY_RECOVERY_BINDING')
            root = self.plan['checkpoint_root']
            receipt = r.decode(r.read(root + '/' + self.request['recovery_id'] + '.applied.json'))
            r.need(receipt == {'binding': expected, 'database_identity': list(inode),
                'state': 'RECOVERY_APPLIED_NOT_ACTIVATED'}, 'APPLY_NOT_COMMITTED')
            verify_apply_publication(root, self.request, self.ref, receipt)
            registered = self.registry.require_binding(self.plan['registry_root'],
                record['registration_id'], self.plan['registry_record']['sha256'],
                self.plan['config']['path'], self.plan['config']['sha256'])
            r.need(registered == cfg, 'RECOVERY_REGISTRY_CHANGED')
        return record, cfg, manifest


def apply(gate, runtime):
    """A: preserve complete backup/history; B: distinct provenance, after proof.

    No live authority database is ever copied. A uses the authenticated consistent
    backup, preserving the original and every table. The recovered authority has
    a new ID/Epoch; old records are retained but cannot lease/consume again.
    Interrupted uncommitted DB creation is retained and HOLD, never adopted.
    """
    record, cfg, manifest = gate.verify('recovery_apply', require_committed=False)
    request, plan = gate.request, gate.plan
    rootfd = r.directory(plan['checkpoint_root'])
    lock = None
    try:
        r.need(stat.S_IMODE(os.fstat(rootfd).st_mode) == 0o700, 'APPLY_ROOT')
        lock = os.open('.apply.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=rootfd)
        info = os.fstat(lock)
        r.need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == 0 and
               stat.S_IMODE(info.st_mode) == 0o600, 'APPLY_LOCK')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt_path = plan['checkpoint_root'] + '/' + request['recovery_id'] + '.applied.json'
        if os.path.lexists(receipt_path):
            gate.verify()
            return {'state': 'ALREADY_APPLIED_NOT_ACTIVATED'}
        # Authenticate the accurate existing Owner authorization using the
        # unchanged HTTPS worker, not a caller-provided approval dictionary.
        signer = gate.assembly.OpenSSLSigner(cfg['key'], cfg['public_der_sha256'])
        try:
            provider = runtime['receipt_provider'].ReceiptProvider(
                lambda unused: None, signer.modulus, 65537, cfg['issuer'])
            approval = runtime['authorization'].authenticate(cfg['review_id'], cfg['grant'],
                provider, cfg['cycle_policy'])
        finally:
            signer.close()
        parent = r.directory(os.path.dirname(cfg['database']))
        try:
            r.need(stat.S_IMODE(os.fstat(parent).st_mode) == 0o700, 'NEW_AUTHORITY_PARENT')
            for suffix in ('', '-wal', '-shm', '-journal', '.issuer-lock'):
                r.need(not os.path.lexists(cfg['database'] + suffix), 'TARGET_EXISTS_HOLD')
            # Last trusted query immediately precedes the first authority write.
            gate.verify('recovery_apply', require_committed=False)
            store_class = runtime['authority_store'].AuthorityStore
            if request['route'] == 'RESTORE_EXISTING':
                snapshot = gate.packet['body']['restoration']['snapshot']
                r.inspect_snapshot(snapshot)
                raw = r.read(snapshot['path'], snapshot['sha256'], 16777216)
                out = os.open(os.path.basename(cfg['database']), os.O_CREAT | os.O_EXCL |
                              os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=parent)
                try:
                    write_all(out, raw)
                    os.fsync(out)
                finally:
                    os.close(out)
                os.fsync(parent)
                store = store_class(cfg['database'], initialize=False)
            else:
                store = store_class(cfg['database'], initialize=True)
            try:
                def revoke():
                    # Keep consumed, all Attempts, proofs and Audit unchanged.
                    prior = store.db.execute('SELECT id,consumed,terminal,writer,epoch,fence,expiry FROM grants').fetchall()
                    r.need(not any(row[0] == cfg['grant']['grant_id'] for row in prior), 'OLD_GRANT_REPLAY')
                    store.audit(cfg['grant']['grant_id'], 'AUTHORITY_RECOVERY_HISTORY', {'previous': prior,
                        'request_sha256': r.sha(r.canonical(request)), 'route': request['route']})
                    store.db.execute('UPDATE grants SET terminal=1,writer=NULL,expiry=0')
                    if store.db.execute("SELECT 1 FROM sqlite_master WHERE name='cycles'").fetchone():
                        store.db.execute('UPDATE cycles SET stopped=1')
                    store.db.execute('CREATE TABLE p2_authority_recovery(binding TEXT NOT NULL)')
                    store.db.execute('INSERT INTO p2_authority_recovery VALUES(?)',
                        (r.canonical(binding(request, gate.ref, cfg)).decode('ascii'),))
                store.transaction(revoke)
                store.register(cfg['grant'])
                store.register_cycle(cfg['grant'], cfg['cycle_policy'], approval)
                store.transaction(lambda: store.db.execute(
                    'UPDATE grants SET epoch=?,fence=? WHERE id=?',
                    (request['new_epoch'] - 1, request['new_epoch'] - 1, cfg['grant']['grant_id'])))
            finally:
                store.close()
            fd = r.opened(cfg['database'])
            try:
                os.fsync(fd)
                identity = list(r.stamp(os.fstat(fd))[:2])
            finally:
                os.close(fd)
            os.fsync(parent)
        finally:
            os.close(parent)
        gate.registry.register(plan['registry_root'], plan['registry_record']['path'],
                               plan['registry_record']['sha256'])
        receipt = {'binding': binding(request, gate.ref, cfg), 'database_identity': identity,
                   'state': 'RECOVERY_APPLIED_NOT_ACTIVATED'}
        out = os.open(os.path.basename(receipt_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                      os.O_NOFOLLOW, 0o600, dir_fd=rootfd)
        try:
            write_all(out, r.canonical(receipt))
            os.fsync(out)
        finally:
            os.close(out)
        os.fsync(rootfd)
        publish_apply(plan['checkpoint_root'], request, gate.ref, receipt)
        gate.verify()
        return {'state': 'RECOVERY_APPLIED_NOT_ACTIVATED', 'receipt_path': receipt_path,
                'writer_started': False, 'sixteen_stages_executed': False}
    finally:
        if lock is not None:
            os.close(lock)
        os.close(rootfd)


def write_all(fd, data):
    view = memoryview(data)
    while view:
        count = os.write(fd, view)
        r.need(count > 0, 'SHORT_WRITE')
        view = view[count:]


def publication(request, ref, receipt):
    req = dict(request, recovery_id=request['recovery_id'] + '-apply')
    decision = {'schema': 1, 'state': 'RECOVERY_EVIDENCE_VALIDATED_NOT_ACTIVATED',
        'request_sha256': r.sha(r.canonical(req)), 'evidence_sha256': ref['sha256'],
        'route': request['route'], 'authority_id': request['new_authority_id'],
        'epoch': request['new_epoch'], 'expires_utc': 0, 'authority_initialized': False,
        'grant_registered': False, 'writer_started': False, 'activation_permission': 'NOT_INFERRED',
        'applied_receipt_sha256': r.sha(r.canonical(receipt))}
    return req, decision


def publish_apply(root, request, ref, receipt):
    req, decision = publication(request, ref, receipt)
    return r.checkpoint(root, req, decision)


def verify_apply_publication(root, request, ref, receipt):
    req, decision = publication(request, ref, receipt)
    name = req['recovery_id']
    data = r.canonical({'request': req, 'decision': decision}) + b'\n'
    target = root + '/' + name + '.json'
    r.need(r.read(target) == data, 'APPLY_PUBLICATION_CONFLICT')
    info_fd = r.opened(target)
    try:
        info = os.fstat(info_fd)
    finally:
        os.close(info_fd)
    index = root + '/.recovery-commits.sqlite3'
    idx = r.opened(index)
    os.close(idx)
    for suffix in ('-journal', '-wal', '-shm'):
        r.need(not os.path.lexists(index + suffix), 'PUBLICATION_RECOVERY_REQUIRED')
    db = sqlite3.connect('file:' + quote(index, safe='/') + '?mode=ro', uri=True, timeout=1)
    try:
        db.execute('PRAGMA query_only=ON')
        row = db.execute('SELECT sha,device,inode FROM commits WHERE id=?', (name,)).fetchone()
        r.need(row == (r.sha(data), info.st_dev, info.st_ino), 'APPLY_PUBLICATION_NOT_COMMITTED')
    finally:
        db.close()


def guarded_driver(driver, gate):
    # Retains the concrete native Driver, its original controls, lock identity
    # and transaction journals. No replacement Writer or skipped native phase.
    original = driver.check_binding
    def check():
        gate.verify()
        return original()
    driver.check_binding = check
    return driver


def install_entry_gates(original, gate):
    """Wire the existing formal entry. No alternate Issuer or native engine."""
    original._RECOVERY_GATE = gate
    base_issuer = original.ProductionIssuer
    class GuardedService(object):
        def __init__(self, service): self.service = service
        def handle(self, *pos, **kw):
            gate.verify()
            return self.service.handle(*pos, **kw)
    class GuardedIssuer(base_issuer):
        def __init__(self, *pos, **kw):
            gate.verify()
            super(GuardedIssuer, self).__init__(*pos, **kw)
            self.service = GuardedService(self.service)
        def serve_one(self):
            gate.verify()
            return super(GuardedIssuer, self).serve_one()
    original.ProductionIssuer = GuardedIssuer
    transport = original._assembly.UnixTransport
    class GuardedTransport(transport):
        def __call__(self, request):
            gate.verify()
            return super(GuardedTransport, self).__call__(request)
    original._assembly.UnixTransport = GuardedTransport
    native = original.native_cycle
    def cycle(factory, *pos, **kw):
        gate.verify()
        return native(lambda: guarded_driver(factory(), gate), *pos, **kw)
    original.native_cycle = cycle
