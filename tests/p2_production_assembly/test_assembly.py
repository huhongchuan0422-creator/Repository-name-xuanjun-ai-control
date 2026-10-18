"""Real Linux sockets/processes/RSA/SQLite; synthetic host effects, never UK."""
import hashlib
import importlib.util
import multiprocessing
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/attempt5'
sys.path[:0] = [str(CORE / 'runtime'), str(CORE / 'original'), str(CORE)]
spec = importlib.util.spec_from_file_location('assembly', str(ROOT / 'production/p2_attempt5/assembly.py'))
assembly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assembly)
from authority_store import AuthorityStore
from receipt_provider import ReceiptProvider, Hold, digest
from test_authority_store import grant


def host(grant, attempt, operation, payload):
    # Deliberately isolated synthetic observations. Signer/socket/store are real.
    outcome = 'SUCCESS' if operation == 'verify_terminal' else 'NO_WRITE'
    result = {'status': 'RECONCILED', 'proof': {
        'outcome': outcome, 'evidence_sha256': 'a' * 64,
        'checkpoint_sha256': 'b' * 64, 'log_sha256': 'c' * 64}}
    return {'grant_sha256': digest(grant), 'attempt_id': attempt,
            'operation': operation, 'payload_sha256': digest(payload),
            'run_id': 'TEST_ONLY_RUN', 'job_id': 'TEST_ONLY_JOB',
            'invoke_id': 'TEST_ONLY_INVOKE', 'backup_sha256': 'a' * 64,
            'checkpoint_sha256': 'b' * 64, 'log_sha256': 'c' * 64,
            'result': result}


def service_process(directory, pin, grant_value, ready, stop, fail_signature=False):
    signer = assembly.OpenSSLSigner(directory + '/key.pem', pin)
    principal = {'host': os.uname().nodename, 'actor_id': 'fixture-actor',
                 'writer_id': 'isolated-test-writer'}
    failed = [False]
    def sign(raw):
        if fail_signature and not failed[0]:
            failed[0] = True
            raise IOError('TEST_ONLY_POST_COMMIT_SIGNING_FAILURE')
        return signer(raw)
    server = None
    try:
        server = assembly.ProductionIssuer(directory + '/authority.sqlite',
            directory + '/issuer.sock', principal, sign, 'ASSEMBLY_TEST', host, grant_value)
        ready.send(('READY', signer.modulus))
        while not stop.is_set():
            try:
                server.serve_one()
            except (socket.timeout, OSError, RuntimeError, ValueError):
                pass
    except Exception as exc:
        ready.send(('ERROR', type(exc).__name__ + ':' + str(exc)))
    finally:
        if server is not None:
            server.close()
        signer.close()
        ready.close()


class AssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # CI containers run root. Do not weaken production parent protection
        # for /tmp or GitHub's group/world writable checkout hierarchy.
        assert os.geteuid() == 0
        cls.base = tempfile.TemporaryDirectory(prefix='p2-assembly-test-', dir='/root')
        cls.key = cls.base.name + '/fixture-key.pem'
        subprocess.check_call(['/usr/bin/openssl', 'genrsa', '-out', cls.key, '2048'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.chmod(cls.key, 0o600)
        public = subprocess.check_output(['/usr/bin/openssl', 'pkey', '-in', cls.key,
                                          '-pubout', '-outform', 'DER'], stderr=subprocess.DEVNULL)
        cls.pin = hashlib.sha256(public).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.base.name)
        self.directory = self.temp.name
        shutil.copyfile(self.key, self.directory + '/key.pem')
        os.chmod(self.directory + '/key.pem', 0o600)
        self.g = grant()
        self.g.update(target_host=os.uname().nodename, actor_id='fixture-actor',
                      expires_utc=int(time.time()) + 3600)
        store = AuthorityStore(self.directory + '/authority.sqlite', initialize=True)
        store.register(self.g)
        store.close()
        self.process = None

    def tearDown(self):
        self.stop_service()
        self.temp.cleanup()

    def start_service(self, fail=False):
        self.stop = multiprocessing.Event()
        parent, child = multiprocessing.Pipe(False)
        self.process = multiprocessing.Process(target=service_process,
            args=(self.directory, self.pin, self.g, child, self.stop, fail))
        self.process.start()
        child.close()
        self.assertTrue(parent.poll(15))
        status, self.modulus = parent.recv()
        parent.close()
        self.assertEqual(status, 'READY', self.modulus)
        self.provider = ReceiptProvider(assembly.UnixTransport(self.directory + '/issuer.sock'),
                                       self.modulus, 65537, 'ASSEMBLY_TEST')

    def stop_service(self):
        if self.process is not None:
            self.stop.set()
            self.process.join(15)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(5)
                self.fail('test service failed to stop')
            self.assertEqual(self.process.exitcode, 0)
            self.process = None

    def consume(self, ordinal=1, command='a' * 64):
        return self.provider.request(self.g, 'assembly-attempt-' + str(ordinal),
            'consume_attempt', {'ordinal': ordinal, 'command_sha256': command,
                                'ledger_sha256': 'b' * 64})

    def reconcile(self, ordinal, success=False):
        return self.provider.request(self.g, 'assembly-attempt-' + str(ordinal),
            'verify_terminal' if success else 'reconcile_unadmitted', {})

    def test_real_socket_signer_store_consume(self):
        self.start_service()
        self.assertEqual(self.consume()['status'], 'CONSUMED')

    def test_same_request_does_not_consume_twice(self):
        self.start_service()
        self.consume()
        self.assertEqual(self.consume()['ordinal'], 1)

    def test_five_attempts_same_grant_and_stop(self):
        self.start_service()
        for ordinal in range(1, 6):
            self.assertEqual(self.consume(ordinal)['ordinal'], ordinal)
            self.reconcile(ordinal)
        with self.assertRaises(Hold):
            self.consume(6)

    def test_success_closes_remaining_quota(self):
        self.start_service()
        self.consume()
        self.reconcile(1, success=True)
        with self.assertRaises(Hold):
            self.consume(2)
        value = self.provider.request(self.g, 'assembly-attempt-1', 'read_committed_outcome', {})
        self.assertEqual(value['committed']['outcome'], 'SUCCESS')

    def test_restart_recovers_original_consumption(self):
        self.start_service()
        self.consume()
        self.stop_service()
        self.start_service()
        value = self.provider.request(self.g, 'assembly-attempt-1', 'query_attempt_consumption',
            {'ordinal': 1, 'command_sha256': 'a' * 64, 'ledger_sha256': 'b' * 64})
        self.assertEqual(value['status'], 'CONSUMED')
        self.assertEqual(self.consume()['ordinal'], 1)
        with self.assertRaises(Hold):
            self.consume(2)  # original result remains UNKNOWN, no blind retry

    def test_post_commit_signing_failure_and_restart_query(self):
        self.start_service(fail=True)
        with self.assertRaises(Hold):
            self.consume()
        self.stop_service()
        self.start_service()
        self.assertEqual(self.consume()['ordinal'], 1)
        self.reconcile(1)
        self.assertEqual(self.consume(2)['ordinal'], 2)

    def test_conflicting_original_request_holds(self):
        self.start_service()
        self.consume()
        with self.assertRaises(Hold):
            self.consume(command='c' * 64)

    def test_second_service_same_database_refused(self):
        self.start_service()
        with self.assertRaises((OSError, RuntimeError)):
            assembly.ProductionIssuer(self.directory + '/authority.sqlite',
                self.directory + '/other.sock', {'host': os.uname().nodename,
                'actor_id': 'fixture-actor', 'writer_id': 'other'}, lambda raw: b'',
                'ASSEMBLY_TEST', host, self.g)

    def test_missing_database_never_initialized(self):
        with self.assertRaises(FileNotFoundError):
            assembly.ProductionIssuer(self.directory + '/missing.sqlite',
                self.directory + '/issuer.sock', {'host': os.uname().nodename,
                'actor_id': 'fixture-actor', 'writer_id': 'other'}, lambda raw: b'',
                'ASSEMBLY_TEST', host, self.g)
        self.assertFalse(os.path.exists(self.directory + '/missing.sqlite'))

    def test_unknown_host_refused_before_socket(self):
        with self.assertRaises(RuntimeError):
            assembly.ProductionIssuer(self.directory + '/authority.sqlite',
                self.directory + '/issuer.sock', {'host': 'NOT_THIS_HOST',
                'actor_id': 'fixture-actor', 'writer_id': 'other'}, lambda raw: b'',
                'ASSEMBLY_TEST', host, self.g)

    def test_untrusted_key_pin_refused(self):
        with self.assertRaises(RuntimeError):
            assembly.OpenSSLSigner(self.directory + '/key.pem', 'f' * 64)

    def test_key_symlink_refused(self):
        path = self.directory + '/linked.pem'
        os.symlink(self.directory + '/key.pem', path)
        with self.assertRaises(OSError):
            assembly.OpenSSLSigner(path, self.pin)

    def test_key_world_readable_refused(self):
        os.chmod(self.directory + '/key.pem', 0o644)
        with self.assertRaises(RuntimeError):
            assembly.OpenSSLSigner(self.directory + '/key.pem', self.pin)

    def test_unsafe_parent_refused_without_chmod(self):
        os.chmod(self.directory, 0o777)
        try:
            with self.assertRaises(RuntimeError):
                assembly.protected_file(self.directory + '/key.pem', private=True)
        finally:
            os.chmod(self.directory, 0o700)

    def test_adapter_sha_before_execution(self):
        path = self.directory + '/adapter.py'
        Path(path).write_text('raise AssertionError("must not run")\n')
        with self.assertRaises(RuntimeError):
            assembly.pinned_module(path, '0' * 64)

    def test_adapter_actual_code_loads_exact_pin(self):
        path = self.directory + '/adapter.py'
        raw = b'def deployment_fact():\n    return "TEST_ONLY"\n'
        Path(path).write_bytes(raw)
        value = assembly.pinned_module(path, hashlib.sha256(raw).hexdigest())
        self.assertEqual(value.deployment_fact(), 'TEST_ONLY')

    def test_transport_missing_socket_is_unknown_no_retry(self):
        provider = ReceiptProvider(assembly.UnixTransport(self.directory + '/missing.sock'),
            int(subprocess.check_output(['/usr/bin/openssl','rsa','-in',self.key,
                '-noout','-modulus'],stderr=subprocess.DEVNULL).decode().strip().split('=')[1],16),
            65537, 'ASSEMBLY_TEST')
        with self.assertRaises(Hold):
            provider.request(self.g, 'attempt', 'consume_attempt', {})

    def test_socket_symlink_rejected(self):
        self.start_service()
        path = self.directory + '/alias.sock'
        os.symlink(self.directory + '/issuer.sock', path)
        with self.assertRaises(RuntimeError):
            assembly.UnixTransport(path)({})

    def test_oversized_frame_rejected_before_payload(self):
        left, right = socket.socketpair()
        try:
            left.sendall(struct.pack('!I', assembly.LIMIT + 1))
            with self.assertRaises(RuntimeError):
                assembly.receive(right)
        finally:
            left.close(); right.close()

    def test_duplicate_json_rejected(self):
        left, right = socket.socketpair()
        try:
            raw = b'{"schema":1,"schema":2}'
            left.sendall(struct.pack('!I', len(raw)) + raw)
            with self.assertRaises(RuntimeError):
                assembly.receive(right)
        finally:
            left.close(); right.close()

    def test_root_peer_authenticated_by_kernel(self):
        left, right = socket.socketpair()
        try:
            self.assertEqual(assembly.peer(right)[:2], (os.getpid(), os.geteuid()))
        finally:
            left.close(); right.close()

    def test_native_assembly_rejects_fixture_before_effects(self):
        self.g['target_host'] = 'TEST_ONLY'
        with self.assertRaises(RuntimeError):
            assembly.native_cycle(lambda: None, self.directory, self.g,
                self.directory + '/issuer.sock', 2 ** 2047 + 1, 'TEST_ONLY',
                1, {}, {})


if __name__ == '__main__':
    unittest.main()
