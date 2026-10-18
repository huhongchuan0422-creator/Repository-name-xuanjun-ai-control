"""Durable fence evidence on an original, exclusive output fd; no new ledger.

The admitted original owner supplies the already held fd and original directory
binding. This component cannot create paths, locks, claims, grants or Writers.
Partial/noncanonical output is preserved and cannot be overwritten or resumed.
"""
import fcntl
import json
import os
import stat

from catalogue_binding import encode


class ProofHold(RuntimeError):
    pass


class HeldProof:
    def __init__(self, fd, controller, check_original_output):
        if type(fd) is not int or not callable(check_original_output):
            raise ProofHold('ORIGINAL_PROOF_OUTPUT_REQUIRED')
        self.fd = fd
        self.controller = controller
        self.check = check_original_output
        self.identity = self._bound('query')

    def _bound(self, mode):
        self.controller._bound(mode)
        if self.check() is not True:
            raise ProofHold('ORIGINAL_PROOF_PATH_BINDING_REQUIRED')
        fs = os.fstat(self.fd)
        flags = fcntl.fcntl(self.fd, fcntl.F_GETFL)
        identity = (fs.st_dev, fs.st_ino)
        if not (stat.S_ISREG(fs.st_mode) and fs.st_nlink == 1 and fs.st_uid == os.geteuid()
                and stat.S_IMODE(fs.st_mode) == 0o600 and fs.st_size <= 16384
                and flags & os.O_ACCMODE == os.O_RDWR and not flags & os.O_APPEND
                and getattr(self, 'identity', identity) == identity):
            raise ProofHold('ORIGINAL_PROOF_FD_IDENTITY')
        return identity

    def __call__(self, proof, query_only=False):
        self._bound('query' if query_only else 'record')
        raw = os.pread(self.fd, 16385, 0)
        if raw:
            before = os.fstat(self.fd)
            try:
                stored = json.loads(raw)
            except (ValueError, UnicodeError):
                raise ProofHold('PARTIAL_PROOF_PRESERVE_NO_RETRY') from None
            if encode(stored) != raw or type(stored) is not dict or set(stored) != set(proof):
                raise ProofHold('NONCANONICAL_PROOF_PRESERVE')
            if any(stored[k] != proof[k] for k in proof if k != 'observed_at'):
                raise ProofHold('PROOF_BINDING_CONFLICT')
            after = os.fstat(self.fd)
            if (before.st_size,before.st_mtime_ns,before.st_ctime_ns) != (after.st_size,after.st_mtime_ns,after.st_ctime_ns):
                raise ProofHold('PROOF_CHANGED')
            self._bound('query')
            return stored
        if query_only:
            raise ProofHold('MISSING_PROOF_QUERY_CANNOT_CREATE')
        raw = encode(proof)
        if len(raw) > 16384 or os.fstat(self.fd).st_size != 0:
            raise ProofHold('PROOF_OUTPUT_NOT_EMPTY')
        # One write attempt only. A short write is preserved as UNKNOWN.
        written = os.pwrite(self.fd, raw, 0)
        os.fsync(self.fd)
        self._bound('record')
        if written != len(raw) or os.pread(self.fd,16385,0) != raw:
            raise ProofHold('PARTIAL_PROOF_PRESERVE_NO_RETRY')
        return json.loads(raw)
