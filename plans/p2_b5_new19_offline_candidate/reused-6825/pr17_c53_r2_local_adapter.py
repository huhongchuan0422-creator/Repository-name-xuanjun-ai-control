"""Preparation only. No CLI, execution, token handling or authority fabrication.

The caller supplies private_bytes from the verified c53 oauth_entrypoint module
and the existing legacy I/O object. Never call runtime.main or old R2 entry.
"""
import os
import pr17_c53_r2_review_transaction as c53
from pr17_c53_r2_local_pinned_source_loader import read_fixed_local_source
from pr17_c53_r2_host_backend_candidate import prepare_bound_transaction

PATHS = c53.CONFIGS + c53.SLOTS
LIMIT = 262144


def single_thread():
    try:
        tasks = os.listdir('/proc/self/task')
    except OSError:
        raise c53.Hold('ADAPTER_THREAD_UNKNOWN') from None
    c53.require(len(tasks) == 1, 'ADAPTER_NOT_SINGLE_THREADED')


class ProtectedReads:
    """Stable protected read; backend before/new/CAS owns runtime identity."""
    def __init__(self, legacy, private_bytes):
        self.legacy = legacy
        self.private_bytes = private_bytes

    def __getattr__(self, name):
        return getattr(self.legacy, name)

    def read(self, path):
        c53.require(path in PATHS, 'ADAPTER_READ_SCOPE')
        before = self.private_bytes(path, LIMIT, contents=False)
        raw = self.private_bytes(path, LIMIT, contents=True)
        legacy_raw, identity = self.legacy.read(path)
        after = self.private_bytes(path, LIMIT, contents=False)
        c53.require(type(raw) is bytes and before == after and raw == legacy_raw,
                    'ADAPTER_BASELINE_CHANGED')
        return raw, identity


class BoundReads(ProtectedReads):
    """Preparation-only frozen identities; never passed to the backend."""
    def __init__(self, legacy, private_bytes):
        super().__init__(legacy, private_bytes)
        self.pins = {}

    def read(self, path):
        raw, identity = super().read(path)
        # A second protected observation binds the stable read to this pin.
        before = self.private_bytes(path, LIMIT, contents=False)
        check_raw, check_identity = super().read(path)
        after = self.private_bytes(path, LIMIT, contents=False)
        c53.require(before == after and raw == check_raw and identity == check_identity,
                    'ADAPTER_BASELINE_CHANGED')
        pin = (before, identity)
        c53.require(path not in self.pins or self.pins[path] == pin,
                    'ADAPTER_BASELINE_IDENTITY_CHANGED')
        self.pins[path] = pin
        return raw, identity


def prepare_local_adapter(*, spec_raw, source_root, legacy_io,
                          batch_id, approval_ref, window_start, authority=None,
                          private_bytes=None):
    """Read current six files in memory; prepare only, never execute.

    Production provenance of the supplied primitive/provider remains a caller
    obligation. Introspection.authenticate alone does not prove recipient
    readiness, catalog binding or B5 ACK. Missing provider remains backend HOLD.
    No config bytes or credentials are serialized, printed or returned separately.
    """
    single_thread()
    if private_bytes is None:
        # Direct original primitive; import only, never load_app/runtime.main.
        from production.cloud_connection.oauth_entrypoint import private_bytes
    spec = c53.binder.verify_spec_bytes(spec_raw)
    reads = BoundReads(legacy_io, private_bytes)
    observed = {path: reads.read(path)[0] for path in PATHS}
    c53.verify_observed_bytes(spec, observed)
    sources = read_fixed_local_source(spec, source_root)
    # Catch replacement during source loading before constructing a transaction.
    for path in PATHS:
        c53.require(reads.read(path)[0] == observed[path], 'ADAPTER_BASELINE_CHANGED')
    single_thread()
    return prepare_bound_transaction(
        spec_raw=spec_raw, observed_bytes=observed, source_blobs=sources,
        batch_id=batch_id, approval_ref=approval_ref, window_start=window_start,
        legacy_io=ProtectedReads(legacy_io, private_bytes), authority=authority)
