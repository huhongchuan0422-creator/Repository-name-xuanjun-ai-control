"""Fenced in-process native Observer service. No second installation Writer.

Scanners, Claim receipts, phase resources and recovery state validation are the
unchanged Epoch7 implementations. The Observer has a read lane, never an
execution phase/Fence waiver. No runtime attestation or production fact defaults.
"""
import contextlib
import copy
import hashlib
import json
import os
import re
import socket
import sqlite3
import stat
import threading
import time
from urllib.parse import quote


def need(ok, code):
    if not ok:
        raise RuntimeError('P2_OBSERVER_' + code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class NativeReader(object):
    """Uses the actual coordinator-owned concrete Driver, not another Writer."""
    def __init__(self, session):
        self.session = session

    @contextlib.contextmanager
    def projection(self, state, completed):
        import native_state
        driver = self.session.driver
        objects = native_state.objects(driver)
        saved = {}
        for name, obj in objects.items():
            saved[name] = {field: (hasattr(obj, field), copy.deepcopy(getattr(obj, field, None)))
                           for field in native_state.FIELDS[name]}
        runtime = driver.containment.runtime
        commands = copy.deepcopy(runtime.successful_commands)
        try:
            # Only in-memory finite data, never native journal CAS or SKIP.
            native_state.restore(driver, state, completed)
            import epoch7_protected_fs as fs
            path = fs.TRANSACTION + '/runtime-boot.json'
            if completed:
                try:
                    parent, leaf = driver.journal_io._parent(path)
                    try:
                        info, raw = driver.journal_io._read_at(parent, leaf)
                    finally:
                        os.close(parent)
                except FileNotFoundError:
                    pass
                else:
                    value = self.session.api.decode(raw)
                    need((info['uid'], info['gid'], info['mode'], info['nlink']) == (0,0,0o600,1) and
                         value.get('context_sha256') == driver.context['context_sha256'] and
                         type(value.get('successful_commands')) is dict, 'BOOT_RECEIPT')
                    runtime.successful_commands = copy.deepcopy(value['successful_commands'])
            yield
        finally:
            # Do not roll the diagnostic sequence backwards after bounded scans.
            sequence = driver.diagnostics.sequence
            for name, obj in objects.items():
                for field, (present, value) in saved[name].items():
                    if present:
                        setattr(obj, field, value)
                    elif hasattr(obj, field):
                        delattr(obj, field)
            driver.diagnostics.sequence = max(sequence, driver.diagnostics.sequence)
            runtime.successful_commands = commands

    def scan(self, state, pending=False):
        from epoch7_recovery_sequence import PHASES
        from epoch7_live_controls import SECTIONS, validate_process_view
        driver = self.session.driver
        done = state['completed']
        if pending:
            need(len(done) < len(PHASES), 'PENDING_TERMINAL')
            completed = done + [PHASES[len(done)]]
            checkpoint = state.get('pending_components')
        else:
            completed = done
            checkpoint = state.get('component_checkpoint')
        with self.projection(checkpoint, completed):
            controls = driver.controls
            index = len(completed)
            phase = PHASES[index-1] if index else PHASES[0]
            boundary = 'after' if index else 'before'
            controls._bound(driver.context)
            # receipt proves the original Claim/review/held lock. Deliberately
            # no authority.phase(): COMPLETE is a read, not a reopened INTENT.
            controls.authority.receipt()
            deadline = controls._begin_guard(False)
            first = controls._resources(phase, boundary, index, SECTIONS)
            processes = validate_process_view(
                controls.observer.processes(copy.deepcopy(driver.context), phase, boundary),
                controls.contract, controls.contract['checkpoints'][index], controls.owner_pid,
                context_sha256=driver.context['context_sha256'], checkpoint_index=index)
            need(controls._resources(phase, boundary, index, SECTIONS) == first, 'RESOURCE_RACE')
            controls.authority.receipt()
            controls._finish_guard(deadline)
            return {'completed': completed, 'resources_sha256': first,
                    'processes_sha256': digest(processes)}

    def journals(self):
        import epoch7_recovery_sequence as sequence
        driver = self.session.driver
        outer = driver.journal_io.journal_exists(sequence.OUTER_NAME)
        inner = driver.retained_io.journal_exists(driver.inner.name)
        if not outer:
            need(not inner, 'PARTIAL_NATIVE_CLAIM')
            return None, None, None
        need(inner, 'MISSING_INNER')
        record = driver.journal_io.read_journal(sequence.OUTER_NAME)
        value = driver.journal_io.authority.validate_outer(record['data'])
        inner_record = driver.retained_io.read_journal(driver.inner.name)
        inside = sequence.retained.BoundJournal._validate_record(inner_record)
        need(inside['binding'] == driver.gate.journal_binding(), 'INNER_BINDING')
        state = value['state']
        need(state.get('admission') == 'ADMITTED' and
             type(state.get('completed')) is list and
             state['completed'] == list(sequence.PHASES[:len(state['completed'])]),
             'NATIVE_STATE')
        return record, inner_record, state

    def proof(self, outcome, evidence, checkpoint):
        context = self.session.attestation
        return {'outcome': outcome, 'evidence_sha256': digest(evidence),
                'checkpoint_sha256': checkpoint, 'log_sha256': digest(
                    {'evidence': evidence, 'invocation': context['invoke_id']})}

    def configure(self, record, state, payload):
        from approved_config import ApprovedConfiguration
        session = self.session
        action = payload.get('action')
        actions = session.cfg['cycle_policy']['configuration_actions']
        need(type(action) is dict and action in actions and
             action['id'] in session.spec['configuration_payloads'], 'UNAPPROVED_CONFIG')
        if state is None:
            session.driver.controls.preflight(copy.deepcopy(session.driver.context))
            checkpoint = session.attestation['checkpoint']['sha256']
        else:
            pending = 'pending_components' in state and 'pending_observation' in state
            self.scan(state, pending=pending)
            checkpoint = hashlib.sha256(record['data']).hexdigest()
        need(checkpoint == action['checkpoint_sha256'], 'CONFIG_CHECKPOINT')
        reference = session.spec['configuration_payloads'][action['id']]
        raw = session.api.read(reference['path'],reference['sha256'])
        need(hashlib.sha256(raw).hexdigest() == action['payload_sha256'], 'CONFIG_PAYLOAD')
        attempt = session.pending['attempt_id']
        with session.database() as db:
            row = db.execute('SELECT state FROM attempts WHERE id=? AND grant_id=?',
                (attempt,session.cfg['grant']['grant_id'])).fetchone()
            need(row == ('UNKNOWN',), 'CONFIG_CLOSED_ATTEMPT')
        def fence():
            session.fence(attempt)
            session.driver.journal_io.authority.receipt()
        directory = os.path.dirname(action['target'])
        need(directory == '/var/lib/xuanjun-attempt5/config', 'CONFIG_SCOPE')
        executor = ApprovedConfiguration(directory,
            {action['id']:(os.path.basename(action['target']),raw)},fence,lambda:checkpoint)
        try:
            result = executor.apply(action)
        finally:
            executor.close()
        result['binding'] = payload
        return result

    def observe(self, operation, payload):
        import epoch7_recovery_sequence as sequence
        driver = self.session.driver
        identity = {k: self.session.cfg['grant'][k] for k in
                    ('source_commit','source_tree','kit_sha256','manifest_sha256')}
        if operation == 'verify_cycle_binding':
            return {'status':'UNCHANGED', 'source_identity':identity, 'binding':payload}
        if not driver.gate.verifier.checked_under_lock:
            driver.controls.verify_outer_review(copy.deepcopy(driver.context))
        driver.journal_io.authority.receipt()
        record, inner, state = self.journals()
        if operation == 'apply_approved_configuration':
            return self.configure(record, state, payload)
        if state is None:
            measured = driver.controls.preflight(copy.deepcopy(driver.context))
            proof = self.proof('NO_WRITE', measured,
                               self.session.attestation['checkpoint']['sha256'])
            if operation == 'authorize_first_admission':
                need(payload == {'context_sha256':driver.context['context_sha256']}, 'ADMISSION_BINDING')
                return {'status':'AUTHORIZED','policy':'P2_ATTEMPT5_V1',
                        'context_sha256':driver.context['context_sha256']}
            if operation == 'diagnose_attempt':
                return {'status':'DIAGNOSED','transaction_consistent':True,
                        'recovery':'NO_WRITE','configuration_actions':[],
                        'source_identity':identity,'binding':payload}
            need(operation == 'reconcile_unadmitted' and payload.get('outer_absent') is True and
                 payload.get('inner_absent') is True, 'NO_WRITE_OPERATION')
            return {'status':'RECONCILED','binding':payload,'proof':proof}
        outer_sha = hashlib.sha256(record['data']).hexdigest()
        stable = state.get('stage') in ('ADMITTED',) + tuple(p+'_COMPLETE' for p in sequence.PHASES)
        if operation == 'reconcile_native_intent':
            need(not stable and len(state['completed']) < 16 and
                 payload.get('outer_sha256') == outer_sha and
                 payload.get('phase') == sequence.PHASES[len(state['completed'])] and
                 state['stage'] == payload['phase']+'_INTENT', 'INTENT_BINDING')
            pending = 'pending_components' in state and 'pending_observation' in state
            # No fallback after an ambiguous after-check. Partial/mismatched
            # effects are HOLD, never reclassified as NO_WRITE.
            measured = self.scan(state, pending=pending)
            result = {'status':'COMMITTED' if pending else 'NO_WRITE','binding':payload,
                      'proof':self.proof('SAFE_CHECKPOINT', measured, outer_sha)}
            if pending:
                result['observation'] = sequence.check_observation(
                    state['pending_observation'], driver.context, payload['phase'])
            return result
        if operation == 'verify_phase_commit':
            phase = payload.get('phase')
            need(not stable and phase in sequence.PHASES and
                 state['stage'] == phase+'_INTENT' and
                 state['completed'] == list(sequence.PHASES[:sequence.PHASES.index(phase)]) and
                 digest(sequence.check_observation(state.get('pending_observation'),
                     driver.context, phase)) == payload.get('checkpoint_sha256'), 'PHASE_BINDING')
            self.scan(state, pending=True)
            return {'status':'VERIFIED','checkpoint_sha256':payload['checkpoint_sha256']}
        if operation == 'diagnose_attempt':
            pending = not stable and 'pending_components' in state and 'pending_observation' in state
            measured = self.scan(state, pending=pending)
            return {'status':'DIAGNOSED','transaction_consistent':True,
                    'recovery':'NATIVE_CAS','configuration_actions':[],
                    'source_identity':identity,'binding':payload}
        need(stable, 'PARTIAL_STATE_REQUIRES_RECONCILIATION')
        measured = self.scan(state)
        if operation == 'authenticate_native_recovery':
            need(payload.get('outer_sha256') == outer_sha and
                 payload.get('inner_sha256') == hashlib.sha256(inner['data']).hexdigest() and
                 payload.get('context_sha256') == driver.context['context_sha256'] and
                 payload.get('completed') == state['completed'], 'RECOVERY_BINDING')
            return {'status':'AUTHORIZED','binding':payload,'policy':'P2_ATTEMPT5_V1',
                    'max_attempts':5,'safe_stage':state['stage']}
        if operation == 'verify_completed_phase':
            phase = payload.get('phase')
            need(phase in state['completed'] and digest(sequence.check_observation(
                state['phase_evidence'][phase], driver.context, phase)) ==
                payload.get('checkpoint_sha256'), 'CHECKPOINT_BINDING')
            return {'status':'VERIFIED','checkpoint_sha256':payload['checkpoint_sha256']}
        need(payload.get('outer_sha256') == outer_sha, 'OUTER_BINDING')
        if operation == 'verify_terminal':
            need(state['completed'] == list(sequence.PHASES) and
                 state['stage'] == sequence.PHASES[-1]+'_COMPLETE', 'TERMINAL_UNKNOWN')
            return {'status':'SUCCESS','proof':self.proof('SUCCESS', measured, outer_sha)}
        if operation == 'reconcile_completed_checkpoint':
            return {'status':'RECONCILED','proof':self.proof('SAFE_CHECKPOINT', measured, outer_sha)}
        if operation == 'commit_safe_reconciliation':
            proof = payload.get('proof')
            need(type(proof) is dict and proof.get('outcome') == 'SAFE_CHECKPOINT',
                 'RECONCILIATION_PROOF')
            recovery = state.get('attempt5_recoveries', [])
            need(recovery and self.session.audited_proof(recovery[-1]['proof_sha256'], proof),
                 'RECONCILIATION_NOT_AUDITED')
            return {'status':'RECONCILED','proof':proof}
        # Configuration writes need an explicitly approved executor, not a
        # read-only query impersonating a successful configuration commit.
        need(False, 'OPERATION_NOT_READ_ONLY')


class ObserverSession(object):
    """Root socket in the canonical Writer process, fixed independent key.

    NativeRecovery is unchanged. Only a matching in-flight authenticated host
    operation may query this service. The Writer waits while readback runs.
    """
    def __init__(self, api, assembly, cfg, spec, source_check):
        self.api, self.assembly = api, assembly
        self.cfg, self.spec = copy.deepcopy(cfg), copy.deepcopy(spec)
        self.source_check = source_check
        self.driver = None
        self.pending = None
        self.pending_closing = False
        self.query_done = threading.Event()
        self.query_done.set()
        self.mutex = threading.RLock()
        self.stop = threading.Event()
        self.thread = self.listener = self.signer = self.directory = self.lock = None
        self.socket_identity = None
        self.authority_identity = None
        need(callable(source_check), 'SOURCE_CHECK_REQUIRED')
        directory = api.protected(cfg['ledger_directory'],directory=True)
        try:
            need(stat.S_IMODE(os.fstat(directory).st_mode) == 0o700, 'LEDGER_DIRECTORY')
        finally:
            os.close(directory)
        self.attestation = self.authenticate_context()
        public, der = api.public_key(spec['attestor_public_key'])
        from receipt_provider import ReceiptProvider
        self.attestor = ReceiptProvider(lambda unused: None, public, 65537, 'ATTESTOR')
        # Signature verification occurs before any socket/key/metadata writes.
        self.attestor._signature(self.attestation_envelope['body'],
                                 self.attestation_envelope['signature'])
        self.reader = NativeReader(self)

    def context_path(self):
        # Fixed finite name, no directory discovery and no mutable context pin
        # in the pre-issued Manifest (which would create a Grant hash cycle).
        with open('/proc/self/stat', 'rb') as stream:
            start = int(stream.read().rsplit(b')',1)[1].split()[19])
        return self.spec['context_directory'] + '/writer-' + str(os.getpid()) + '-' + str(start) + '.json'

    def authenticate_context(self):
        api = self.api
        envelope = api.decode(api.read(self.context_path()))
        need(type(envelope) is dict and set(envelope) == {'body','signature'}, 'ATTESTATION_ENVELOPE')
        body = envelope['body']
        fields = {'schema','hostname','principal','grant_sha256','source_identity',
                  'writer_pid','writer_start_ticks','lease_epoch','fence','run_id','job_id','invoke_id',
                  'issued_utc','expires_utc','backup','checkpoint'}
        need(type(body) is dict and set(body) == fields and body['schema'] == 1 and
             type(body['schema']) is int and body['hostname'] == os.uname().nodename and
             body['principal'] == self.cfg['principal'] and
             body['grant_sha256'] == digest(self.cfg['grant']) and
             body['source_identity'] == {k:self.cfg['grant'][k] for k in
                ('source_commit','source_tree','kit_sha256','manifest_sha256')}, 'ATTESTATION_BINDING')
        with open('/proc/self/stat', 'rb') as stream:
            start = stream.read().rsplit(b')',1)[1].split()[19]
        need(type(body['writer_pid']) is int and body['writer_pid'] == os.getpid() and
             body['writer_start_ticks'] == int(start), 'WRITER_PROCESS_BINDING')
        need(type(body['lease_epoch']) is int and body['lease_epoch'] > 0 and
             type(body['fence']) is int and body['fence'] > 0 and
             type(body['writer_start_ticks']) is int, 'ATTESTATION_FENCE_TYPES')
        now = int(time.time())
        need(type(body['issued_utc']) is int and type(body['expires_utc']) is int and
             body['issued_utc'] <= now < body['expires_utc'] <= self.cfg['grant']['expires_utc'],
             'ATTESTATION_EXPIRED')
        for name in ('run_id','job_id','invoke_id'):
            need(type(body[name]) is str and re.fullmatch('[A-Za-z0-9_.:/-]{1,128}', body[name]) and
                 body[name].upper() != 'UNKNOWN', 'INVOCATION_UNKNOWN')
        for name in ('backup','checkpoint'):
            api.reference(body[name])
            api.read(body[name]['path'], body[name]['sha256'])
        self.attestation_envelope = envelope
        return body

    @contextlib.contextmanager
    def database(self):
        path = self.cfg['database']
        fd = self.assembly.protected_file(path, private=True)
        info = os.fstat(fd)
        os.close(fd)
        identity = (info.st_dev, info.st_ino)
        if self.authority_identity is None:
            self.authority_identity = identity
        need(self.authority_identity == identity, 'AUTHORITY_STORE_REPLACED')
        db = sqlite3.connect('file:' + quote(path,safe='/') + '?mode=ro', uri=True,
                             isolation_level=None, timeout=1)
        try:
            db.execute('PRAGMA query_only=ON')
            yield db
            fd = self.assembly.protected_file(path, private=True)
            try:
                after = os.fstat(fd)
                need((after.st_dev,after.st_ino) == identity, 'AUTHORITY_STORE_REPLACED')
            finally:
                os.close(fd)
        finally:
            db.close()

    def fence(self, attempt):
        need(int(time.time()) < self.attestation['expires_utc'] and
             self.source_check() is True, 'SOURCE_OR_CONTEXT_CHANGED')
        # Re-read exact signed context and real backup/checkpoint every time.
        need(self.authenticate_context() == self.attestation, 'ATTESTATION_CHANGED')
        self.attestor._signature(self.attestation_envelope['body'],
                                 self.attestation_envelope['signature'])
        with self.database() as db:
            row = db.execute('SELECT binding,body,consumed,terminal,writer,epoch,fence,expiry '
                'FROM grants WHERE id=?',(self.cfg['grant']['grant_id'],)).fetchone()
            need(row is not None and row[0] == digest(self.cfg['grant']) and
                 json.loads(row[1]) == self.cfg['grant'] and row[4] == self.cfg['principal']['writer_id'] and
                 type(row[5]) is int and row[5] == self.attestation['lease_epoch'] > 0 and
                 type(row[6]) is int and row[6] == self.attestation['fence'] > 0 and
                 time.time() < min(row[7],self.cfg['grant']['expires_utc']), 'WRITER_FENCE_UNKNOWN')
            cycle = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cycles'").fetchone()
            if cycle:
                stopped = db.execute('SELECT stopped FROM cycles WHERE grant_id=?',
                                     (self.cfg['grant']['grant_id'],)).fetchone()
                need(stopped is None or not stopped[0], 'SOURCE_CHANGE_HOLD')
            if attempt != 'CANDIDATE':
                existing = db.execute('SELECT ordinal,state FROM attempts WHERE id=? AND grant_id=?',
                                      (attempt,self.cfg['grant']['grant_id'])).fetchone()
                need(existing is not None and existing[0] == row[2] and
                     existing[1] in ('UNKNOWN','NO_WRITE','SAFE_CHECKPOINT','SUCCESS'), 'ATTEMPT_BINDING')
            return row[4],row[5],row[6]

    def audited_proof(self, expected, proof):
        with self.database() as db:
            rows = db.execute("SELECT body FROM audit WHERE grant_id=? AND event='SIGNED_RECEIPT' ORDER BY id DESC LIMIT 1024",
                              (self.cfg['grant']['grant_id'],)).fetchall()
        for row in rows:
            value = json.loads(row[0])
            result = value.get('signed_body',{}).get('result')
            if type(result) is dict and digest(result) == expected and result.get('proof') == proof:
                return True
        return False

    def attach(self, driver):
        from epoch7_recovery_sequence import InjectedDriver
        from epoch7_live_controls import FiniteLiveControls
        from epoch7_host_observer import Epoch7HostObserver
        from epoch7_host_phases import ClaimAuthority
        need(isinstance(driver,InjectedDriver) and isinstance(driver.controls,FiniteLiveControls) and
             isinstance(driver.controls.observer,Epoch7HostObserver) and
             isinstance(driver.journal_io.authority,ClaimAuthority) and
             driver.controls.authority is driver.journal_io.authority and
             driver.controls.observer.authority is driver.journal_io.authority and
             driver.controls.owner_pid == os.getpid(), 'CONCRETE_NATIVE_OBSERVER_REQUIRED')
        with self.mutex:
            need(self.pending is None, 'CONCURRENT_DRIVER_CHANGE')
            self.driver = driver
        if self.listener is None:
            self.start()

    @contextlib.contextmanager
    def request(self, request):
        from issuer_service import HOST_OPERATIONS
        if request.get('operation') not in HOST_OPERATIONS:
            yield
            return
        with self.mutex:
            need(self.driver is not None and self.pending is None and
                 request.get('grant_sha256') == digest(self.cfg['grant']), 'CONCURRENT_HOST_REQUEST')
            self.pending = copy.deepcopy(request)
            self.pending_closing = False
            authority = self.driver.journal_io.authority
            original = authority.receipt
            base = getattr(authority, '_attempt5_original_receipt', original)
            def receipt(*args, **kwargs):
                if threading.current_thread() is self.thread:
                    self.fence(request['attempt_id'])
                    return base(*args, **kwargs)
                return original(*args, **kwargs)
            authority.receipt = receipt
        try:
            yield
        finally:
            with self.mutex:
                self.pending_closing = True
            need(self.query_done.wait(35), 'READBACK_STILL_RUNNING_HOLD')
            with self.mutex:
                authority.receipt = original
                self.pending = None

    def handle(self, request):
        with self.mutex:
            need(self.pending is not None and not self.pending_closing and
                 self.query_done.is_set(), 'NO_ACTIVE_QUERY_SCOPE')
            self.query_done.clear()
        try:
            return self._handle(request)
        finally:
            self.query_done.set()

    def _handle(self, request):
        from issuer_service import HOST_OPERATIONS
        need(type(request) is dict and set(request) == {'schema','nonce','binding','payload'} and
             type(request['schema']) is int and request['schema'] == 1 and
             type(request['nonce']) is str and re.fullmatch('[0-9a-f]{32}',request['nonce']) and
             type(request['binding']) is dict and type(request['payload']) is dict, 'REQUEST_SCHEMA')
        with self.mutex:
            pending = copy.deepcopy(self.pending)
        need(pending is not None, 'NO_INFLIGHT_NATIVE_REQUEST')
        binding = {'grant_sha256':pending['grant_sha256'],'attempt_id':pending['attempt_id'],
                   'operation':pending['operation'],'payload_sha256':digest(pending['payload'])}
        need(request['binding'] == binding and request['payload'] == pending['payload'] and
             binding['operation'] in HOST_OPERATIONS, 'INFLIGHT_BINDING')
        token = self.fence(binding['attempt_id'])
        if binding['operation'] == 'verify_cycle_binding':
            result = self.reader.observe(binding['operation'],request['payload'])
        else:
            lock = self.driver.controls.install_lock()
            with contextlib.ExitStack() as stack:
                if lock.held() is not True:
                    stack.enter_context(lock)
                result = self.reader.observe(binding['operation'],request['payload'])
        need(self.fence(binding['attempt_id']) == token, 'FENCE_CHANGED')
        need(type(result) is dict and result.get('status') not in (None,'UNKNOWN'), 'RESULT_UNKNOWN')
        receipt = dict(binding, run_id=self.attestation['run_id'], job_id=self.attestation['job_id'],
            invoke_id=self.attestation['invoke_id'], backup_sha256=self.attestation['backup']['sha256'],
            checkpoint_sha256=(result.get('action',{}).get('checkpoint_sha256') or
                               result.get('proof',{}).get('checkpoint_sha256') or
                               self.attestation['checkpoint']['sha256']),
            log_sha256=digest(result), result=result)
        now = int(time.time())
        body = {'schema':1,'issuer':self.spec['issuer'],'request':request,
                'issued_utc':now,'expires_utc':min(now+20,self.attestation['expires_utc'],
                                                self.cfg['grant']['expires_utc']),
                'receipt':receipt}
        import base64
        response = {'body':body,'signature':base64.b64encode(self.signer(canonical(body))).decode('ascii')}
        # Durable private receipt precedes reply. Failure is HOLD; records are
        # never deleted/reused to pretend a failed publication succeeded.
        raw = canonical(response)
        need(len(raw) <= self.assembly.LIMIT, 'REPLY_BOUND')
        directory = self.api.protected(self.cfg['ledger_directory'],directory=True)
        try:
            need(stat.S_IMODE(os.fstat(directory).st_mode) == 0o700, 'LEDGER_DIRECTORY')
            name = 'observer-receipt-' + request['nonce'] + '.json'
            fd = os.open(name,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600,dir_fd=directory)
            try:
                view = memoryview(raw)
                while view:
                    count = os.write(fd,view)
                    need(count > 0,'RECEIPT_WRITE')
                    view = view[count:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(directory)
        finally:
            os.close(directory)
        return response

    def start(self):
        import fcntl
        directory, leaf = self.assembly.parent(self.spec['socket'])
        self.directory, self.leaf = directory, leaf
        try:
            self.lock = os.open(leaf+'.observer-lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,
                                0o600,dir_fd=directory)
            info = os.fstat(self.lock)
            need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1 and
                 stat.S_IMODE(info.st_mode) == 0o600, 'SERVICE_LOCK')
            fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            need(not os.path.lexists(self.spec['socket']), 'SOCKET_EXISTS_HOLD')
            self.signer = self.assembly.OpenSSLSigner(self.spec['key'],self.spec['public_der_sha256'])
            self.listener = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            mask = os.umask(0o177)
            try:
                self.listener.bind('/proc/self/fd/'+str(directory)+'/'+leaf)
            finally:
                os.umask(mask)
            info = os.stat(leaf,dir_fd=directory,follow_symlinks=False)
            need(stat.S_ISSOCK(info.st_mode) and info.st_uid == 0 and
                 stat.S_IMODE(info.st_mode) == 0o600, 'SOCKET_PROTECTION')
            self.socket_identity = (info.st_dev,info.st_ino)
            self.listener.listen(2)
            self.listener.settimeout(0.25)
            self.thread = threading.Thread(target=self.serve, name='P2NativeObserver',daemon=True)
            self.thread.start()
        except BaseException:
            self.close()
            raise

    def serve(self):
        while not self.stop.is_set():
            try:
                connection, unused = self.listener.accept()
            except socket.timeout:
                continue
            try:
                connection.settimeout(30)
                need(self.assembly.peer(connection)[1] == 0, 'ROOT_PEER_REQUIRED')
                response = self.handle(self.assembly.receive(connection))
                self.assembly.send(connection,response)
            except Exception:
                # Never sign an UNKNOWN result or print private exception data.
                try:
                    self.assembly.send(connection,{'hold':'OBSERVER_UNVERIFIED'})
                except Exception:
                    pass
            finally:
                connection.close()

    def close(self):
        self.stop.set()
        if self.thread is not None and threading.current_thread() is not self.thread:
            self.thread.join(35)
            need(not self.thread.is_alive(), 'OBSERVER_QUERY_STILL_RUNNING')
        if self.listener is not None:
            self.listener.close()
            self.listener = None
        if self.signer is not None:
            self.signer.close()
            self.signer = None
        if self.directory is not None:
            try:
                info = os.stat(self.leaf,dir_fd=self.directory,follow_symlinks=False)
                if self.socket_identity == (info.st_dev,info.st_ino):
                    os.unlink(self.leaf,dir_fd=self.directory)
            except FileNotFoundError:
                pass
            os.close(self.directory)
            self.directory = None
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None
