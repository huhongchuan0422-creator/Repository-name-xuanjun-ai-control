"""Preparation only. No CLI, execution, token handling or authority fabrication.

The caller supplies private_bytes from the verified c53 oauth_entrypoint module
and the existing legacy I/O object. Never call runtime.main or old R2 entry.
"""
import os
import pr17_b5_successor_review as c53
from pr17_b5_successor_loader import read_fixed_local_source
from pr17_b5_successor_backend import prepare_bound_transaction

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
    def __init__(self, legacy, private_bytes, journal_job=None, request_ids=()):
        self.legacy = legacy
        self.private_bytes = private_bytes
        self.journal_job = journal_job
        self.request_ids = tuple(request_ids)

    def __getattr__(self, name):
        return getattr(self.legacy, name)

    def read(self, path):
        allowed = path in PATHS
        if self.journal_job is not None:
            c53.require(self.journal_job ==
                        '/opt/xuanjun-cloud-connection/l2-b5-staged-f0fe0d3978b7' and
                        len(self.request_ids) == 19 and
                        len(set(self.request_ids)) == 19,
                        'ADAPTER_JOURNAL_BINDING')
            fixed = ('reservation.json', 'window-open.json',
                     'activation-identity.json', 'NEW_WORKER_START_ATTEMPT.json')
            journal = self.journal_job + '/'
            allowed = allowed or path in tuple(journal + name for name in fixed)
            allowed = allowed or path in tuple(
                journal + 'checkpoint-%03d.json' % number
                for number in range(1, 65))
            allowed = allowed or path in tuple(
                journal + 'intake-' + rid + suffix
                for rid in self.request_ids
                for suffix in ('.intent.json', '.sent.json'))
        c53.require(allowed, 'ADAPTER_READ_SCOPE')
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
                          private_bytes=None, release_gate=None):
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
    backend_reads = ProtectedReads(
        legacy_io, private_bytes,
        journal_job=spec['fixed_paths']['job_proposed'],
        request_ids=spec['batch']['draft_request_ids'])
    return prepare_bound_transaction(
        spec_raw=spec_raw, observed_bytes=observed, source_blobs=sources,
        batch_id=batch_id, approval_ref=approval_ref, window_start=window_start,
        legacy_io=backend_reads, authority=authority,
        release_gate=release_gate)
