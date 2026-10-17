"""Offline-only PR99 transaction specification, durable journal and adapter contract.

No host/network adapter exists in this module. The only bundled adapter is in tests.
Receipts in fixtures are models, never authority. CLI execution always holds.
The existing stopped installer/start candidate are deliberately not called here.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import production_start as existing_start

ACTION = 'PR99_FINAL_DOMESTIC_TRANSACTION_V1'
REPOSITORY = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
BRANCH = 'build/tokyo-korea-migration-prep-20261014'
HOST = existing_start.HOST
# Reserved child directory within production_start.STATE; not a second ledger.
HOST_OPERATION_STORE = str(existing_start.STATE / 'operations')
SOURCE_HOST = 'iZ6wee8q9z4t03hvqumwfhZ'
RELEASE = str(existing_start.RELEASE)
STEPS = ('inspect_protected', 'fence_source', 'final_snapshot', 'receive_final',
         'reconcile_final', 'assign_writer', 'install_stopped', 'start_owned',
         'accept_business', 'snapshot_route', 'cutover_route', 'accept_https')
ROLLBACK = ('restore_route', 'stop_owned')
SHA = re.compile(r'[0-9a-f]{64}')
TOKEN = re.compile(r'[a-zA-Z0-9_-]{1,80}')


class Hold(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Hold(code)


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def exact_keys(value, keys, code):
    require(type(value) is dict and set(value) == set(keys), code)


def source_manifest():
    base = Path(__file__).parent
    return {name: hashlib.sha256((base / name).read_bytes()).hexdigest()
            for name in ('migration_transaction.py', 'production_start.py', 'stopped_transaction.py', 'final_materials.py')}


def validate_plan(plan, expected_digest, now):
    """expected_digest must ultimately come from independent private authority.
    This validator only checks structure/binding; it cannot establish that authority.
    """
    exact_keys(plan, ('action', 'transaction_id', 'head', 'host', 'source_host', 'release',
                     'issued_at', 'expires_at', 'independent_review_comment_id',
                     'source_hashes', 'bindings', 'steps'), 'PLAN_SCHEMA')
    require(SHA.fullmatch(expected_digest or '') and digest(plan) == expected_digest, 'PLAN_DIGEST')
    require(plan['action'] == ACTION and plan['host'] == HOST and
            plan['source_host'] == SOURCE_HOST and plan['release'] == RELEASE, 'FIXED_SCOPE')
    require(type(plan['transaction_id']) is str and TOKEN.fullmatch(plan['transaction_id']), 'TRANSACTION_ID')
    require(type(plan['head']) is str and re.fullmatch(r'[0-9a-f]{40}', plan['head']), 'HEAD')
    require(type(plan['issued_at']) is int and type(plan['expires_at']) is int and
            plan['issued_at'] <= now < plan['expires_at'] <= plan['issued_at'] + 7200, 'PLAN_EXPIRED')
    require(type(plan['independent_review_comment_id']) is int and
            plan['independent_review_comment_id'] > 0, 'REVIEW_REQUIRED')
    require(plan['steps'] == list(STEPS), 'EXACT_STEP_ORDER')
    hashes = plan['source_hashes']
    exact_keys(hashes, ('migration_transaction.py', 'production_start.py', 'stopped_transaction.py', 'final_materials.py'), 'SOURCE_SET')
    require(all(type(v) is str and SHA.fullmatch(v) for v in hashes.values()), 'SOURCE_DIGEST')
    bindings = plan['bindings']
    exact_keys(bindings, ('writer_inventory', 'protected_inventory', 'final_manifest_contract',
                          'runtime_identity', 'unit_manifest', 'business_acceptance_contract',
                          'route_contract'), 'BINDING_SET')
    require(all(type(v) is str and SHA.fullmatch(v) for v in bindings.values()), 'BINDING_DIGEST')
    return plan


def validate_event(event, head):
    exact_keys(event, ('repository', 'action', 'pr', 'head_repository', 'branch', 'actor_id',
                       'label', 'head', 'run_attempt'), 'EVENT_SCHEMA')
    require(event == dict(repository=REPOSITORY, action='labeled', pr=99,
                         head_repository=REPOSITORY, branch=BRANCH, actor_id='332398908',
                         label='pr99-s09-production-' + head[:12], head=head,
                         run_attempt='1'), 'EXACT_EVENT_REQUIRED')


def production_entry(event, plan, expected_digest):
    validate_plan(plan, expected_digest, int(time.time()))
    validate_event(event, plan['head'])
    # Intentionally no environment/flag/label may unlock this candidate.
    raise Hold('REVIEW_ONLY_NO_PRODUCTION_ADAPTER_NO_CLOUD_CALL')


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def exclusive(path, payload):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(encode(payload))
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    sync_directory(Path(path).parent)


def read_private(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid() and
                stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1 and
                before.st_size <= 1048576, 'JOURNAL_FILE_IDENTITY')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(1048577)
        after = os.fstat(fd)
        require((before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'JOURNAL_DRIFT')
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            raise Hold('CORRUPT_JOURNAL_UNKNOWN_NO_REPLAY') from None
        require(encode(value) == raw, 'NONCANONICAL_JOURNAL')
        return value
    finally:
        os.close(fd)


class Journal:
    """One globally serialized transaction store, with durable one-use claim.

    Parent must be pre-created mode 0700 by the trusted local owner. Concurrent
    transactions share a lock; a consumed transaction ID is never replayed.
    An unfinished record is UNKNOWN even when a crash occurred before dispatch.
    """
    def __init__(self, root, transaction_id):
        self.root = Path(root)
        require(type(transaction_id) is str and TOKEN.fullmatch(transaction_id), 'TRANSACTION_ID')
        for p in (self.root, *self.root.parents):
            require(not p.is_symlink(), 'JOURNAL_SYMLINK')
        st = self.root.stat()
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.geteuid() and
                stat.S_IMODE(st.st_mode) == 0o700, 'JOURNAL_DIRECTORY_IDENTITY')
        self.path = self.root / transaction_id
        fd = os.open(self.root / 'lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self.lock = os.fdopen(fd, 'r+b')
        st = os.fstat(fd)
        try:
            require(stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid() and
                    stat.S_IMODE(st.st_mode) == 0o600 and st.st_nlink == 1, 'LOCK_IDENTITY')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.lock.close()
            raise

    def close(self):
        self.lock.close()

    def claim(self, plan, expected_digest):
        require(not any(p.is_dir() or p.is_symlink() for p in self.root.iterdir()),
                'EXISTING_TRANSACTION_PRESERVE_NO_NEW_ATTEMPT')
        # mkdir is itself an irreversible consumption marker, even if next write fails.
        self.path.mkdir(mode=0o700)
        sync_directory(self.root)
        exclusive(self.path / 'claim.json', {'plan_digest': expected_digest, 'plan': plan})

    def load(self):
        st = self.path.lstat()
        require(stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode) and
                st.st_uid == os.geteuid() and stat.S_IMODE(st.st_mode) == 0o700, 'TRANSACTION_DIRECTORY')
        claim = read_private(self.path / 'claim.json')
        exact_keys(claim, ('plan_digest', 'plan'), 'CLAIM_SCHEMA')
        require(digest(claim['plan']) == claim['plan_digest'], 'CLAIM_DIGEST')
        entries = sorted(self.path.iterdir())
        names = [p.name for p in entries if p.name != 'claim.json']
        require(names == [f'{i:04d}.json' for i in range(len(names))], 'JOURNAL_SEQUENCE_UNKNOWN')
        events = []
        previous = claim['plan_digest']
        for name in names:
            event = read_private(self.path / name)
            exact_keys(event, ('index', 'previous', 'body'), 'EVENT_RECORD_SCHEMA')
            require(event['index'] == len(events) and event['previous'] == previous, 'JOURNAL_CHAIN')
            events.append(event['body'])
            previous = digest(event)
        return claim, events, previous

    def append(self, body):
        _, events, previous = self.load()
        exclusive(self.path / f'{len(events):04d}.json',
                  {'index': len(events), 'previous': previous, 'body': body})


def request(plan, stage, previous_receipt):
    return {'transaction_id': plan['transaction_id'], 'plan_digest': digest(plan),
            'head': plan['head'], 'stage': stage, 'previous_receipt': previous_receipt,
            'operation_id': digest([digest(plan), stage]), 'host': HOST}


def validate_receipt(receipt, req):
    exact_keys(receipt, ('request_digest', 'operation_id', 'stage', 'status', 'evidence'), 'RECEIPT_SCHEMA')
    require(receipt['request_digest'] == digest(req) and receipt['operation_id'] == req['operation_id']
            and receipt['stage'] == req['stage'], 'RECEIPT_BINDING')
    require(receipt['status'] in ('SUCCEEDED', 'FAILED'), 'RECEIPT_TERMINAL_REQUIRED')
    require(type(receipt['evidence']) is str and SHA.fullmatch(receipt['evidence']), 'EVIDENCE_DIGEST')
    return receipt


class Transaction:
    """Adapter.execute/query must implement fixed operations with private proofs.

    execute is at most once; query MUST be read-only and keyed by the durable
    operation_id (including dispatch-before-InvokeId crashes). Exceptions, invalid
    receipts and timeouts are UNKNOWN, never treated as known failure/no-effect.
    Adapter receipts carry only hashes; business/private data never enter journal.
    """
    def __init__(self, root, adapter, clock=time.time):
        self.root, self.adapter, self.clock = root, adapter, clock

    def _perform(self, journal, plan, stage, previous):
        require(self.clock() < plan['expires_at'], 'EXPIRED_BEFORE_OPERATION')
        require(source_manifest() == plan['source_hashes'], 'SOURCE_DRIFT')
        req = request(plan, stage, previous)
        journal.append({'type': 'INTENT', 'request': req})
        try:
            receipt = validate_receipt(self.adapter.execute(req), req)
        except BaseException:
            # Error strings may contain secrets; never persist raw exception text.
            journal.append({'type': 'UNKNOWN', 'operation_id': req['operation_id']})
            raise Hold('OPERATION_UNKNOWN_QUERY_ONLY') from None
        journal.append({'type': 'RESULT', 'receipt': receipt})
        return receipt

    def run_fixture(self, plan, expected_digest):
        """Offline test seam only. No bundled live adapter; no CLI dispatch path."""
        validate_plan(plan, expected_digest, self.clock())
        require(source_manifest() == plan['source_hashes'], 'SOURCE_DRIFT')
        journal = Journal(self.root, plan['transaction_id'])
        try:
            journal.claim(plan, expected_digest)
            previous = expected_digest
            attempted = []
            for stage in STEPS:
                attempted.append(stage)
                result = self._perform(journal, plan, stage, previous)
                previous = digest(result)
                if result['status'] == 'FAILED':
                    return self._contain(journal, plan, attempted, previous)
            journal.append({'type': 'TERMINAL', 'status': 'FIXTURE_TRANSACTION_SUCCEEDED'})
            return 'FIXTURE_TRANSACTION_SUCCEEDED'
        finally:
            journal.close()

    def _contain(self, journal, plan, attempted, previous):
        # Even an explicit FAILED result can mean partial effects. Include failed
        # stage in containment. Never resume source writer, erase data or retire Tokyo.
        stages = []
        if 'cutover_route' in attempted:
            stages.append('restore_route')
        if 'install_stopped' in attempted:
            stages.append('stop_owned')
        for stage in stages:
            result = self._perform(journal, plan, stage, previous)
            previous = digest(result)
            if result['status'] != 'SUCCEEDED':
                journal.append({'type': 'TERMINAL', 'status': 'CONTAINMENT_FAILED_HOLD'})
                return 'CONTAINMENT_FAILED_HOLD'
        journal.append({'type': 'TERMINAL', 'status': 'FAILED_PRESERVED_NO_SOURCE_RESUME'})
        return 'FAILED_PRESERVED_NO_SOURCE_RESUME'

    def query_only(self, transaction_id, expected_digest):
        """Settle last in-flight operation without replay, continuation or rollback.
        A recovered success is not an overall migration success. An external exact
        recovery decision is required; this candidate has no recovery write entry.
        """
        journal = Journal(self.root, transaction_id)
        try:
            claim, events, _ = journal.load()
            require(claim['plan_digest'] == expected_digest, 'RECOVERY_PLAN_DIGEST')
            if events and events[-1]['type'] == 'TERMINAL':
                return events[-1]['status']
            intents = [e for e in events if e['type'] == 'INTENT']
            if not intents:
                return 'CLAIM_CONSUMED_NO_REPLAY'
            req = intents[-1]['request']
            require(req == request(claim['plan'], req['stage'], req['previous_receipt']) and
                    req['stage'] in STEPS + ROLLBACK, 'RECOVERY_REQUEST_BINDING')
            if any(e['type'] == 'RESULT' and e['receipt']['operation_id'] == req['operation_id'] for e in events):
                return 'RECORDED_RESULT_HOLD_NO_CONTINUATION'
            try:
                receipt = validate_receipt(self.adapter.query(req), req)
            except BaseException:
                return 'UNKNOWN_QUERY_ONLY_NO_REPLAY'
            journal.append({'type': 'RESULT', 'receipt': receipt})
            return 'RESOLVED_' + receipt['status'] + '_HOLD_NO_CONTINUATION'
        finally:
            journal.close()


if __name__ == '__main__':
    raise SystemExit('REVIEW_ONLY_NO_PRODUCTION_ADAPTER_NO_CLOUD_CALL')
