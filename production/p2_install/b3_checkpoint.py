"""Immutable B3 evidence publication, reusing initialization's file primitives.

No CP is inferred complete by this module. It records explicitly scoped evidence
after the caller's validator, without replaying CP03 or starting any process.
Not yet wired to a complete CP04--09 consumer; not an installation CLI.
"""
import fcntl
import os
from pathlib import Path
import stat

from .initialize import directory, encode, need, publish, read, sha


def _checkpoint(_name):
    pass  # deterministic interruption injection in tests only


def retain(root, cp03_sha256, contract_sha256, stage, evidence, action='execute'):
    """Return the same immutable reference on response loss or recover.

Only CP04--09 names allowed. CP03 source is read-only and its original receipt
is pinned before any new write. Evidence status remains explicit; a HOLD record
cannot later be overwritten with a success or consumed as a completed stage.
    """
    need(action in ('execute', 'inspect', 'recover'), 'ACTION')
    need(stage in ('CP04','CP05','CP06','CP07','CP08','CP09'), 'CHECKPOINT_STAGE')
    need(isinstance(evidence, dict) and evidence.get('status') in
         ('VALIDATED', 'HOLD', 'UNAVAILABLE'), 'EVIDENCE_STATUS')
    need(isinstance(contract_sha256, str) and len(contract_sha256) == 64
         and all(x in '0123456789abcdef' for x in contract_sha256), 'CONTRACT_SHA')
    root = Path(root)
    need(str(root) == '/var/lib/xuanjun-p2-isolated-test/b3-initialize' or
         (str(root).startswith('/tmp/p2-b3-test-') and root.name == 'b3-initialize'),
         'ROOT_SCOPE')
    need(root.is_absolute() and '..' not in root.parts and
         str(root.resolve()) == str(root), 'ROOT_CANONICAL')
    s = os.lstat(root)
    need(stat.S_ISDIR(s.st_mode) and s.st_uid == os.geteuid()
         and stat.S_IMODE(s.st_mode) == 0o700, 'ROOT_PRIVATE')
    original = root/'commit-receipt.json'
    need(sha(read(original)) == cp03_sha256, 'CP03_RECEIPT_CHANGED')
    # Share the already existing initializer lock; never create a second lock
    # identity or silently recreate a missing initialization lock.
    lock = os.open(str(root/'.initialize.lock'), os.O_RDWR|os.O_NOFOLLOW)
    try:
        s = os.fstat(lock)
        need(stat.S_ISREG(s.st_mode) and s.st_uid == os.geteuid() and
             s.st_nlink == 1 and stat.S_IMODE(s.st_mode) == 0o600, 'LOCK_IDENTITY')
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        need(sha(read(original)) == cp03_sha256, 'CP03_RECEIPT_CHANGED')
        folder = root/'checkpoints'
        if action == 'inspect' and not os.path.lexists(folder):
            return {'status': 'NOT_EXECUTED', 'reference': None}
        if action != 'inspect':
            directory(folder)
        else:
            s = os.lstat(folder)
            need(stat.S_ISDIR(s.st_mode) and s.st_uid == os.geteuid() and
                 stat.S_IMODE(s.st_mode) == 0o700, 'CHECKPOINT_DIRECTORY')
        payload = {'schema': 1, 'scope': 'ISOLATED_TEST_ONLY',
                   'cp03_receipt_sha256': cp03_sha256,
                   'contract_sha256': contract_sha256, 'stage': stage,
                   'evidence': evidence, 'installation_stage_complete': False}
        raw = encode(payload)
        target = folder/(stage+'-'+contract_sha256+'.json')
        if action != 'inspect':
            publish(target, raw)
            _checkpoint('after_publication')
        elif not os.path.lexists(target):
            return {'status': 'NOT_EXECUTED', 'reference': None}
        need(read(target) == raw, 'CHECKPOINT_CONFLICT')
        need(sha(read(original)) == cp03_sha256, 'CP03_RECEIPT_CHANGED')
        return {'status': evidence['status'],
                'reference': {'path': str(target), 'sha256': sha(raw)},
                'installation_stage_complete': False}
    finally:
        os.close(lock)
