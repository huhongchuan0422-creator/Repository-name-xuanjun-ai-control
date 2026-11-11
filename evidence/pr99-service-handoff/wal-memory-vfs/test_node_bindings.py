"""Normal synthetic file/FD and original-transport integration, NOT M99 races.

FixtureIO deliberately is not a production guard or authority implementation.
No directory replacement, bwrap, network, host service or migration is exercised.
"""
import hashlib
import importlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import node_bindings as binding
import lost_invoke_reconciliation as lost
from test_sqlite_wal_vfs import fixture, restored_rows

ORIGINAL = Path(__file__).resolve().parents[1]/'s09-install-candidate'
DEPENDENCIES = {
    'production_transport.py': '625fa7adf78e545ffa99c84329b3929fb6a7ee907eaebe6f122fa9261c140b16',
    'production_start.py': 'd645edc0013af34804626315a6ddce1b47b870c012b6b632131c320ed4c20688',
}
for name, expected in DEPENDENCIES.items():
    if hashlib.sha256((ORIGINAL/name).read_bytes()).hexdigest() != expected:
        raise RuntimeError('ORIGINAL_PUBLISHED_TRANSPORT_DEPENDENCY_DRIFT')
sys.path.insert(0, str(ORIGINAL))
original = importlib.import_module('production_transport')


class FixtureIO:
    """Test-only normal-path I/O. Does not claim M99 path-security acceptance."""
    def check(self): return True
    def exists(self, path): return Path(path).exists()
    def read(self, path, limit):
        raw = Path(path).read_bytes()
        assert len(raw) <= limit
        return raw
    def mkdir(self, path, **kwargs): Path(path).mkdir(**kwargs)
    def write(self, path, raw, mode):
        fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, mode)
        try:
            with os.fdopen(os.dup(fd), 'wb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        finally: os.close(fd)
    def create_fd(self, path, mode):
        return os.open(path, os.O_RDWR|os.O_CREAT|os.O_EXCL, mode)
    def sync(self, path):
        fd = os.open(path, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)


class WalBindingTests(unittest.TestCase):
    def test_nonempty_wal_reaches_original_receipt_and_exclusive_fd(self):
        main, wal, schema = fixture(21)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'source.db'
            source.write_bytes(main); source.with_name('source.db-wal').write_bytes(wal)
            receipt = binding.snapshot_sqlite_with_original_io(FixtureIO(), source, root/'output', lambda:'a'*64, schema)
            result = root/'output/final.db'
            self.assertEqual(len(restored_rows(result.read_bytes())), 21)
            self.assertEqual(receipt['class'], 'FINAL_FENCED_SQLITE_CANDIDATE')
            self.assertEqual(receipt['sha256'], binding.sha(result.read_bytes()))
            self.assertTrue(receipt['source_wal_captured'])
            self.assertEqual(result.stat().st_mode & 0o777, 0o400)
            self.assertEqual((source.read_bytes(), source.with_name('source.db-wal').read_bytes()), (main,wal))
            self.assertEqual(json.loads((root/'output/sqlite-checkpoint.receipt.json').read_bytes()), receipt)

    def test_missing_admitted_io_has_no_fallback(self):
        with self.assertRaisesRegex(binding.BindingHold, 'ADMITTED_MATERIAL_IO'):
            binding.snapshot_sqlite_with_original_io(None, '/source.db', '/output', lambda:'a'*64, 'b'*64)

    def test_schema_failure_preserves_capture_without_completion_receipt(self):
        main, wal, schema = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'source.db'; source.write_bytes(main)
            source.with_name('source.db-wal').write_bytes(wal)
            with self.assertRaises(RuntimeError):
                binding.snapshot_sqlite_with_original_io(FixtureIO(), source, root/'output', lambda:'a'*64, 'b'*64)
            self.assertEqual((root/'output/captured/source.db-wal').read_bytes(), wal)
            self.assertEqual((root/'output/final.db').stat().st_size, 0)
            self.assertFalse((root/'output/sqlite-checkpoint.receipt.json').exists())

    def test_existing_nonempty_output_cannot_be_reused_or_truncated(self):
        main, wal, schema = fixture()
        with tempfile.TemporaryFile() as output:
            output.write(b'preserve'); output.flush()
            with self.assertRaisesRegex(binding.BindingHold, 'EMPTY_OUTPUT'):
                binding.finalize_captured_sqlite(main, wal, schema, output.fileno(), 'a'*64, lambda:'a'*64, lambda:True)
            output.seek(0); self.assertEqual(output.read(), b'preserve')

    def test_fence_changed_after_native_recovery_keeps_output_without_receipt(self):
        main, wal, schema = fixture()
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'output'; fd = os.open(p, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0o600)
            try:
                changed = [False]; real = os.pwrite
                def write(*args):
                    count = real(*args); changed[0] = True; return count
                with patch.object(binding.os, 'pwrite', write), self.assertRaisesRegex(binding.BindingHold, 'FENCE_CHANGED'):
                    binding.finalize_captured_sqlite(main, wal, schema, fd, 'a'*64,
                        lambda: 'b'*64 if changed[0] else 'a'*64, lambda:True)
                self.assertGreater(os.fstat(fd).st_size, 0)
            finally: os.close(fd)

    def test_binding_callback_failure_precedes_payload_write(self):
        main, wal, schema = fixture()
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'output'; fd = os.open(p, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0o600)
            try:
                with self.assertRaisesRegex(binding.BindingHold, 'OUTPUT_BINDING'):
                    binding.finalize_captured_sqlite(main, wal, schema, fd, 'a'*64, lambda:'a'*64, lambda:False)
                self.assertEqual(os.fstat(fd).st_size, 0)
            finally: os.close(fd)

    def test_rollback_journal_holds_before_output_creation(self):
        main, wal, schema = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'source.db'; source.write_bytes(main)
            source.with_name('source.db-journal').write_bytes(b'preserve')
            with self.assertRaisesRegex(binding.BindingHold, 'ROLLBACK_JOURNAL'):
                binding.snapshot_sqlite_with_original_io(FixtureIO(), source, root/'output', lambda:'a'*64, schema)
            self.assertFalse((root/'output').exists())

    def test_input_byte_drift_prevents_checkpoint_receipt(self):
        main, wal, schema = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'source.db'; source.write_bytes(main)
            source.with_name('source.db-wal').write_bytes(wal)
            class Drift(FixtureIO):
                def __init__(self): self.n = 0
                def read(self, path, limit):
                    raw = super().read(path, limit)
                    if Path(path) == source:
                        self.n += 1
                        if self.n > 1: return raw+b'drift'
                    return raw
            with self.assertRaisesRegex(binding.BindingHold, 'SOURCE_DRIFT'):
                binding.snapshot_sqlite_with_original_io(Drift(), source, root/'output', lambda:'a'*64, schema)
            self.assertFalse((root/'output/sqlite-checkpoint.receipt.json').exists())


class QueryBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); os.chmod(self.root, 0o700)
        self.fd = os.open(self.root, os.O_RDONLY|os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        self.calls = []; self.status = 'Success'; self.zero = False; self.bad_output = False
        self.transport = original.DomesticStartTransport(self.root, self.rpc,
            ('fixture-id','fixture-secret','fixture-token'), 'a'*64, 'b'*64)
        original.persist(self.root/'cloud-start.intent.json', self.transport.intent)
        self.query = binding.ReconciledQueryTransport(self.transport, self.fd, lambda:True)

    def rpc(self, endpoint, version, action, credentials, **params):
        self.calls.append(action)
        self.assertIn(action, ('DescribeCommandInvocations','DescribeInvocationResult'))
        if action == 'DescribeCommandInvocations':
            rows = [] if self.zero else [{'InvokeId':'t-synthetic-lost',
                'CommandName':'pr99-final-start-'+self.transport.operation_id[:24],
                'CommandContent':self.transport.shell, 'CommandType':'RunShellScript',
                'Username':'root','WorkingDir':'/root','Timeout':240,'Parameters':'{}',
                'InvokeInstances':[{'InstanceId':lost.INSTANCE}]}]
            return {'TotalCount':len(rows), 'CommandInvocations':rows}
        output = {'host':lost.HOST,'uid':0,'source_sha256':self.transport.source_sha,
            'operation_id':self.transport.operation_id, 'receipt':{
                'status':'THREE_APPS_STARTED_NO_TRAFFIC_CUTOVER','production_cutover':False,
                'services_installed':True,'health':{'portal':200,'contact':200,'customer-service':200}}}
        if self.bad_output: output['operation_id'] = 'c'*64
        return {'InvocationResult':{'InstanceId':lost.INSTANCE,'InvokeId':'t-synthetic-lost',
            'InvocationStatus':self.status,'ExitCode':0 if self.status=='Success' else 2,
            'Output':json.dumps(output)}}

    def test_actual_original_transport_receipt_is_recovered_and_cached(self):
        with (patch.object(self.transport,'dispatch_once',side_effect=AssertionError('NO_DISPATCH')),
              patch.object(self.transport,'query_only',side_effect=AssertionError('NO_PATH_QUERY'))):
            result = self.query.query_only()
        self.assertEqual(result['status'],'THREE_APPS_STARTED_NO_TRAFFIC_CUTOVER')
        self.assertFalse(result['retry_allowed']); self.assertFalse(result['production_cutover'])
        self.assertEqual(self.calls, ['DescribeCommandInvocations','DescribeInvocationResult'])
        self.calls.clear(); self.assertEqual(self.query.query_only(), result); self.assertEqual(self.calls, [])
        raw = b''.join(p.read_bytes() for p in self.root.iterdir())
        self.assertNotIn(b'fixture-secret', raw); self.assertNotIn(self.transport.shell.encode(), raw)

    def test_no_match_remains_unknown_without_dispatch_or_result(self):
        self.zero = True
        self.assertEqual(self.query.query_only()['status'], 'UNKNOWN_NO_INVOKE_NO_REPLAY')
        self.assertEqual(self.calls, ['DescribeCommandInvocations'])
        self.assertFalse((self.root/'cloud-start.result.json').exists())

    def test_pending_queries_original_id_without_repeating_search(self):
        self.status = 'Running'
        self.assertEqual(self.query.query_only()['status'], 'PENDING_QUERY_ONLY')
        self.calls.clear(); self.assertEqual(self.query.query_only()['status'], 'PENDING_QUERY_ONLY')
        self.assertEqual(self.calls,['DescribeInvocationResult'])
        self.assertFalse((self.root/'cloud-start.result.json').exists())

    def test_foreign_output_stays_unknown_and_keeps_invocation(self):
        self.bad_output = True
        self.assertEqual(self.query.query_only()['status'], 'UNKNOWN_QUERY_ONLY_NO_REPLAY')
        self.assertTrue((self.root/'cloud-start.invocation.json').exists())
        self.assertFalse((self.root/'cloud-start.result.json').exists())

    def test_remote_failure_is_not_no_effect_or_retry_permission(self):
        self.status = 'Failed'; result = self.query.query_only()
        self.assertEqual(result['status'], 'REMOTE_FAILED_QUERY_HOST_STATE_NO_REPLAY')
        self.assertFalse(result['retry_allowed'])

    def test_partial_result_is_preserved_and_never_requeried(self):
        p = self.root/'cloud-start.result.json'; original.persist(p, {'partial':True})
        raw = p.read_bytes()
        with self.assertRaises(RuntimeError): self.query.query_only()
        self.assertEqual(self.calls,['DescribeCommandInvocations']); self.assertEqual(p.read_bytes(), raw)

    def test_callback_revocation_stops_before_lookup(self):
        self.query.check = lambda:False
        with self.assertRaisesRegex(binding.BindingHold, 'CONTROLLER_BINDING'):
            self.query.query_only()
        self.assertEqual(self.calls, [])

    def test_no_dispatch_method_is_exposed(self):
        with self.assertRaisesRegex(binding.BindingHold, 'NO_DISPATCH'): self.query.dispatch_once()
        self.assertEqual(self.calls, [])

    def test_separate_python_process_reads_original_saved_result_without_rpc(self):
        expected = self.query.query_only()
        program = '''import json,os,sys
sys.path[:0]=sys.argv[1:3]
import node_bindings,production_transport
def forbidden(*a,**k): raise AssertionError('RESTART_MUST_NOT_CALL_CLOUD')
t=production_transport.DomesticStartTransport(sys.argv[3],forbidden,('x','y','z'),'a'*64,'b'*64)
fd=os.open(sys.argv[3],os.O_RDONLY|os.O_DIRECTORY)
try: print(json.dumps(node_bindings.ReconciledQueryTransport(t,fd,lambda:True).query_only(),sort_keys=True))
finally: os.close(fd)
'''
        child = subprocess.run([sys.executable,'-I','-B','-c',program,str(Path(__file__).parent),
                                str(ORIGINAL),str(self.root)],capture_output=True,text=True,timeout=15,check=True)
        self.assertEqual(json.loads(child.stdout), expected)
        self.assertEqual(child.stderr, '')

    def test_fifo_intent_rejected_without_blocking(self):
        # Synthetic special-file rejection only, not ancestor replacement.
        p = self.root/'cloud-start.intent.json'; p.unlink(); os.mkfifo(p, 0o600)
        with self.assertRaises(RuntimeError): self.query.query_only()
        self.assertEqual(self.calls, [])


if __name__ == '__main__': unittest.main()
