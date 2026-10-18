"""Durable execution on the ORIGINAL transaction journal and ORIGINAL lock.

No claim, directory, lock, permit, Writer epoch or alternate path guard is created.
The admitted original controller supplies all descriptors and the trust/path
validators. Missing binding is HOLD. This is not production admission or M99.
"""
import fcntl
import hashlib
import json
import os
import re
import stat
from pathlib import Path


def extension_manifest():
    base=Path(__file__).parent
    names=("catalogue_binding.py","existing_fd_controller.py","source_fence.py","held_proof.py","stage_history.py")
    return {n:hashlib.sha256((base/n).read_bytes()).hexdigest() for n in names}


class ControllerHold(RuntimeError):
    pass


def need(ok, code):
    if not ok:
        raise ControllerHold(code)


class ExistingFdController:
    def __init__(self, original_journal, contract, root_fd, transaction_fd,
                 binding, verify_admission, assert_original_paths, verify_history):
        # Trust validation precedes ANY transaction-directory/journal read.
        need(callable(verify_admission) and callable(assert_original_paths) and callable(verify_history),
             'ORIGINAL_TRUST_AND_HISTORY_REQUIRED')
        self.authorize = verify_admission
        self.paths = assert_original_paths
        self.history = verify_history
        self.binding = json.loads(contract.encode(binding))
        self.binding_digest = contract.digest(self.binding)
        self.m = contract
        self.journal = original_journal
        need(isinstance(original_journal,contract.Journal), 'ORIGINAL_JOURNAL_CLASS_REQUIRED')
        self.root = root_fd
        self.directory = transaction_fd
        self.lock = original_journal.lock.fileno()
        self._bound('query')

    def _bound(self, mode):
        need(self.authorize(mode, self.binding) is True, 'ORIGINAL_ADMISSION_REQUIRED')
        need(self.m.digest(self.binding) == self.binding_digest, 'CONTROLLER_BINDING_CHANGED')
        need(self.paths() is True, 'ORIGINAL_ADMITTED_PATH_BINDING_REQUIRED')
        b = self.binding
        need(set(b) == {'transaction_id','plan_digest','epoch','writer_inventory_sha256',
                        'root_identity','transaction_identity','lock_identity','extension_manifest_sha256'}, 'CONTROLLER_BINDING_SCHEMA')
        need(type(b['epoch']) is int and b['epoch'] > 0 and
             all(type(b[k]) is str and re.fullmatch('[0-9a-f]{64}',b[k]) for k in ('plan_digest','writer_inventory_sha256','extension_manifest_sha256')),
             'CONTROLLER_EPOCH_DIGEST')
        need(self.m.digest(extension_manifest()) == b['extension_manifest_sha256'], 'EXTENSION_SOURCE_DRIFT')
        for key in ('root_identity','transaction_identity','lock_identity'):
            need(type(b[key]) is list and len(b[key])==2 and all(type(v)is int and v>=0 for v in b[key]),
                 'CONTROLLER_IDENTITY_SCHEMA')
        need(b['transaction_id'] == self.journal.path.name, 'ORIGINAL_TRANSACTION_REQUIRED')
        for fd, identity in ((self.root,b['root_identity']), (self.directory,b['transaction_identity'])):
            fs = os.fstat(fd)
            need(stat.S_ISDIR(fs.st_mode) and fs.st_uid == os.geteuid() and stat.S_IMODE(fs.st_mode) == 0o700 and
                 [fs.st_dev,fs.st_ino] == identity, 'ORIGINAL_DIRECTORY_IDENTITY')
        fs = os.fstat(self.lock)
        linked_lock = os.stat('lock', dir_fd=self.root, follow_symlinks=False)
        linked_txn = os.stat(b['transaction_id'], dir_fd=self.root, follow_symlinks=False)
        need(stat.S_ISREG(fs.st_mode) and fs.st_uid == os.geteuid() and fs.st_nlink == 1 and
             stat.S_IMODE(fs.st_mode) == 0o600 and [fs.st_dev,fs.st_ino] == b['lock_identity'] and
             (linked_lock.st_dev,linked_lock.st_ino) == (fs.st_dev,fs.st_ino), 'ORIGINAL_LOCK_IDENTITY')
        need([linked_txn.st_dev,linked_txn.st_ino] == b['transaction_identity'] and stat.S_ISDIR(linked_txn.st_mode),
             'TRANSACTION_LINK_DRIFT')
        need(fcntl.fcntl(self.lock,fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDWR, 'ORIGINAL_LOCK_MODE')
        # The same open-file-description retains the original flock. No new lock
        # object/epoch is introduced, and this wrapper never unlocks borrowed fds.
        try:
            fcntl.flock(self.lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ControllerHold('ORIGINAL_WRITER_BUSY') from None

    def _read(self, name):
        need(name == 'claim.json' or re.fullmatch(r'[0-9]{4}\.json',name), 'JOURNAL_NAME')
        self._bound('query')
        fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=self.directory)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == os.geteuid() and
                 stat.S_IMODE(before.st_mode) == 0o600 and before.st_size <= 1048576, 'JOURNAL_FILE_IDENTITY')
            raw = os.pread(fd,1048577,0)
            after = os.fstat(fd); linked = os.stat(name,dir_fd=self.directory,follow_symlinks=False)
            fingerprint = lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            need(fingerprint(before) == fingerprint(after) == fingerprint(linked) and len(raw) == before.st_size,
                 'JOURNAL_DRIFT')
            value = json.loads(raw)
            need(self.m.encode(value) == raw, 'CORRUPT_OR_NONCANONICAL_JOURNAL')
        finally:
            os.close(fd)
        self._bound('query')
        return value

    def load(self):
        self._bound('query')
        names = sorted(os.listdir(self.directory))
        need('claim.json' in names and len(names) <= 10000, 'ORIGINAL_CLAIM_REQUIRED')
        claim = self._read('claim.json')
        self.m.exact_keys(claim,('plan','plan_digest'),'CLAIM_SCHEMA')
        need(claim['plan_digest'] == self.binding['plan_digest'] == self.m.digest(claim['plan']) and
             claim['plan']['transaction_id'] == self.binding['transaction_id'] and
             claim['plan']['bindings']['writer_inventory'] == self.binding['writer_inventory_sha256'], 'ORIGINAL_PLAN_BINDING')
        files = [n for n in names if n != 'claim.json']
        need(files == [f'{i:04d}.json' for i in range(len(files))], 'JOURNAL_SEQUENCE_UNKNOWN')
        events = []; previous = claim['plan_digest']
        for name in files:
            value = self._read(name)
            self.m.exact_keys(value,('index','previous','body'),'EVENT_RECORD_SCHEMA')
            need(type(value['index']) is int and value['index'] == len(events) and value['previous'] == previous,
                 'JOURNAL_HASH_CHAIN')
            events.append(value['body']); previous = self.m.digest(value)
        need(sorted(os.listdir(self.directory)) == names,
             'JOURNAL_DIRECTORY_DRIFT')
        need(self.history(claim['plan'],events) is True, 'ORIGINAL_HISTORY_NOT_VERIFIED')
        self._bound('query')
        return claim,events,previous

    def _append(self, body):
        claim,events,previous = self.load()
        need(self.history(claim['plan'],events+[body]) is True, 'EVENT_SEMANTICS')
        self._bound('record')
        name = f'{len(events):04d}.json'
        raw = self.m.encode({'index':len(events),'previous':previous,'body':body})
        fd = os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=self.directory)
        try:
            self._bound('record')
            position = 0
            while position < len(raw):
                count = os.write(fd,raw[position:]); need(count > 0,'PARTIAL_EVENT_PRESERVE')
                position += count
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.directory)
        self._bound('record')

    def perform(self, request, dispatch, query):
        """Fresh intent -> dispatch once; durable prior intent -> QUERY ONLY.

        All requests use the original contract, history policy and original
        journal. UNKNOWN never permits a replay, next stage, rollback or success.
        """
        claim,events,_ = self.load()
        plan = claim['plan']
        need(request == self.m.request(plan,request.get('stage'),request.get('previous_receipt')) and
             request.get('stage') in self.m.STEPS+self.m.ROLLBACK, 'REQUEST_BINDING')
        results = [e['receipt'] for e in events if e.get('type') == 'RESULT' and e['receipt'].get('operation_id') == request['operation_id']]
        intents = [e for e in events if e.get('type') == 'INTENT' and e.get('request',{}).get('operation_id') == request['operation_id']]
        need(len(results) <= 1 and len(intents) <= 1, 'DUPLICATE_OPERATION')
        if results:
            need(intents and intents[0]['request'] == request, 'CACHED_REQUEST_CONFLICT')
            return self.m.validate_receipt(results[0],request)
        if intents:
            need(intents[0]['request'] == request, 'PENDING_REQUEST_CONFLICT')
            # Query authorization is rechecked on every restart. Never dispatch
            # an intent which could have been consumed before the previous crash.
            self._bound('query')
            try:
                receipt = self.m.validate_receipt(query(request),request)
            except Exception:
                raise ControllerHold('UNKNOWN_QUERY_ONLY_PRESERVE') from None
            self._append({'type':'RESULT','receipt':receipt})
            return receipt
        need(not any(e.get('type') in ('UNKNOWN','TERMINAL') for e in events), 'EXISTING_UNKNOWN_OR_TERMINAL_HOLD')
        self._bound('dispatch')
        self.m.validate_plan(plan,self.binding['plan_digest'],self.m.time.time())
        need(self.m.source_manifest() == plan['source_hashes'], 'ORIGINAL_SOURCE_DRIFT')
        self._append({'type':'INTENT','request':request})
        try:
            self._bound('dispatch')
            receipt = self.m.validate_receipt(dispatch(request),request)
        except Exception:
            self._append({'type':'UNKNOWN','operation_id':request['operation_id']})
            raise ControllerHold('OPERATION_UNKNOWN_QUERY_ONLY') from None
        self._append({'type':'RESULT','receipt':receipt})
        return receipt
