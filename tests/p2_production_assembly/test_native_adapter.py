"""Actual RSA/socket/store/entry wiring in isolated Hosted root fixtures.

No production provider substitution. The observer peer emits explicitly
SYNTHETIC_ONLY host facts; this tests the real adapter, never UK acceptance.
"""
import base64
import copy
import hashlib
import importlib.util
import io
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/attempt5'
sys.path[:0] = [str(CORE / 'runtime'), str(CORE / 'original'), str(CORE)]
PROD = ROOT / 'production/p2_attempt5'
def module(name, source):
    spec = importlib.util.spec_from_file_location(name, str(source))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

assembly = module('adapter_test_assembly', PROD / 'assembly.py')
registry = module('adapter_test_registry', PROD / 'registry.py')
from authority_store import AuthorityStore
from receipt_provider import ReceiptProvider, Hold
from test_authority_store import grant
import test_registry as registry_tests


def observer_process(directory, public_pin, ready, stop, mode):
    signer = assembly.OpenSSLSigner(directory + '/key.pem', public_pin)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o177)
    try:
        listener.bind(directory + '/observer.sock')
    finally:
        os.umask(old)
    listener.listen(2)
    listener.settimeout(0.25)
    ready.send('READY')
    try:
        while not stop.is_set():
            try:
                connection, unused = listener.accept()
            except socket.timeout:
                continue
            try:
                request = assembly.receive(connection)
                binding = request['binding']
                result = {'status': 'RECONCILED', 'proof': {'outcome': 'NO_WRITE',
                    'evidence_sha256': 'a'*64, 'checkpoint_sha256': 'b'*64,
                    'log_sha256': 'c'*64}}
                receipt = dict(binding, run_id='SYNTHETIC_ONLY_RUN',
                    job_id='SYNTHETIC_ONLY_JOB', invoke_id='SYNTHETIC_ONLY_INVOKE',
                    backup_sha256='a'*64, checkpoint_sha256='b'*64,
                    log_sha256='c'*64, result=result)
                if mode == 'unknown':
                    receipt['invoke_id'] = 'UNKNOWN'
                if mode == 'drift':
                    receipt['payload_sha256'] = 'f'*64
                now = int(time.time())
                body = {'schema': 1, 'issuer': 'FIXTURE_OBSERVER', 'request': request,
                    'issued_utc': now, 'expires_utc': now+20, 'receipt': receipt}
                if mode == 'nonce':
                    body['request'] = dict(request, nonce='0'*32)
                if mode == 'expired':
                    body.update(issued_utc=now-40, expires_utc=now-10)
                raw = json.dumps(body, sort_keys=True, separators=(',', ':'),
                                 ensure_ascii=True, allow_nan=False).encode('ascii')
                signature = signer(raw)
                if mode == 'signature':
                    signature = b'0' * len(signature)
                assembly.send(connection, {'body': body,
                    'signature': base64.b64encode(signature).decode('ascii')})
            finally:
                connection.close()
    finally:
        listener.close()
        signer.close()
        ready.close()


class NativeAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert os.geteuid() == 0
        cls.tmp = tempfile.TemporaryDirectory(dir='/root', prefix='p2-native-adapter-')
        cls.base = Path(cls.tmp.name)
        cls.key = cls.base / 'key.pem'
        subprocess.check_call(['/usr/bin/openssl','genrsa','-out',str(cls.key),'2048'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.chmod(str(cls.key), 0o600)
        cls.public = subprocess.check_output(['/usr/bin/openssl','pkey','-in',str(cls.key),'-pubout'],
                                             stderr=subprocess.DEVNULL)
        cls.der = subprocess.check_output(['/usr/bin/openssl','pkey','-in',str(cls.key),
            '-pubout','-outform','DER'], stderr=subprocess.DEVNULL)
        cls.public_pin = hashlib.sha256(cls.der).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(self.base))
        self.directory = Path(self.temp.name)
        shutil.copyfile(str(self.key), str(self.directory / 'key.pem'))
        os.chmod(str(self.directory / 'key.pem'), 0o600)
        self.public_path = self.directory / 'public.pem'
        self.public_path.write_bytes(self.public)
        os.chmod(str(self.public_path), 0o600)
        self.adapter = module('isolated_native_adapter', PROD / 'native_adapter.py')
        self.g = grant()
        self.g.update(target_host=os.uname().nodename, actor_id='fixture-actor',
                      expires_utc=int(time.time())+3600)
        self.cfg = {'principal': {'host': os.uname().nodename, 'actor_id': 'fixture-actor',
                    'writer_id': 'fixture-writer'}, 'grant': self.g,
                    'issuer': 'FIXTURE_ISSUER', 'public_der_sha256': self.public_pin}
        ref = {'path': str(self.public_path), 'sha256': hashlib.sha256(self.public).hexdigest()}
        self.binding = {'schema': 1, 'hostname': os.uname().nodename,
            'principal': self.cfg['principal'], 'issuer': self.cfg['issuer'],
            'public_key': ref, 'receipt_public_key': ref,
            'receipt_issuer': 'FIXTURE_OBSERVER',
            'receipt_socket': str(self.directory / 'observer.sock'),
            'legacy_manifest_sha256': 'a'*64,
            'approved_plan': {'path': str(self.directory / 'plan.json'), 'sha256': 'b'*64},
            'private_seed': {'path': str(self.directory / 'seed.json'), 'sha256': 'c'*64},
            'legacy_review_id': 1, 'legacy_approval_body_sha256': 'd'*64}
        self.process = None

    def tearDown(self):
        if self.process is not None:
            self.stop.set()
            self.process.join(5)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(5)
                self.fail('observer fixture did not stop')
            self.assertEqual(self.process.exitcode, 0)
        self.temp.cleanup()

    def bind(self, binding=None, pin=None):
        raw = self.adapter.canonical(self.binding if binding is None else binding)
        self.adapter.bind_deployment(self.cfg, raw,
            pin or hashlib.sha256(raw).hexdigest(), str(self.directory / 'kit'), assembly)

    def start_observer(self, mode='normal'):
        self.stop = multiprocessing.Event()
        parent, child = multiprocessing.Pipe(False)
        self.process = multiprocessing.Process(target=observer_process,
            args=(str(self.directory), self.public_pin, child, self.stop, mode))
        self.process.start()
        child.close()
        self.assertTrue(parent.poll(15))
        self.assertEqual(parent.recv(), 'READY')
        parent.close()

    def readback(self):
        return self.adapter.build_host_readback(self.cfg)(
            self.g, 'attempt-1', 'reconcile_unadmitted', {})

    def test_public_modulus_uses_pinned_public_pem(self):
        self.bind()
        modulus = self.adapter.public_modulus(self.cfg)
        self.assertEqual(modulus.bit_length(), 2048)
        self.assertEqual(self.public_path.read_bytes(), self.public)

    def test_public_pin_mismatch_rejected(self):
        self.bind()
        self.public_path.write_bytes(self.public + b'\n')
        with self.assertRaises(RuntimeError):
            self.adapter.public_modulus(self.cfg)

    def test_public_der_mismatch_rejected(self):
        self.cfg['public_der_sha256'] = 'f'*64
        self.bind()
        with self.assertRaises(RuntimeError):
            self.adapter.public_modulus(self.cfg)

    def test_private_pem_not_accepted_as_public(self):
        self.binding['public_key'] = {'path': str(self.directory / 'key.pem'),
            'sha256': hashlib.sha256((self.directory / 'key.pem').read_bytes()).hexdigest()}
        self.bind()
        with self.assertRaises(RuntimeError):
            self.adapter.public_modulus(self.cfg)

    def test_public_symlink_rejected(self):
        alias = self.directory / 'alias.pem'
        alias.symlink_to(self.public_path)
        self.binding['public_key'] = dict(self.binding['public_key'], path=str(alias))
        self.bind()
        with self.assertRaises(OSError):
            self.adapter.public_modulus(self.cfg)

    def test_unbound_calls_rejected(self):
        for name in ('public_modulus','build_driver','build_host_readback'):
            with self.subTest(name=name):
                with self.assertRaises(RuntimeError):
                    getattr(self.adapter, name)(self.cfg)

    def test_binding_sha_mismatch_rejected(self):
        with self.assertRaises(RuntimeError):
            self.bind(pin='f'*64)

    def test_binding_host_mismatch_rejected(self):
        self.binding['hostname'] = 'NOT_THIS_HOST'
        with self.assertRaises(RuntimeError):
            self.bind()

    def test_binding_rejects_unknown_extra_fields(self):
        self.binding['fixture_mode'] = True
        with self.assertRaises(RuntimeError):
            self.bind()

    def test_binding_is_immutable_and_cannot_rebind(self):
        self.bind()
        with self.assertRaises(RuntimeError):
            self.bind()
        self.cfg['issuer'] = 'OTHER'
        with self.assertRaises(RuntimeError):
            self.adapter.public_modulus(self.cfg)

    def test_live_socket_signed_readback(self):
        self.bind()
        self.start_observer()
        receipt = self.readback()
        self.assertEqual(receipt['result']['proof']['outcome'], 'NO_WRITE')
        self.assertEqual(receipt['invoke_id'], 'SYNTHETIC_ONLY_INVOKE')

    def test_readback_bad_signature_rejected(self):
        self.bind()
        self.start_observer('signature')
        with self.assertRaises((RuntimeError, Hold)):
            self.readback()

    def test_readback_old_nonce_rejected(self):
        self.bind()
        self.start_observer('nonce')
        with self.assertRaises(RuntimeError):
            self.readback()

    def test_readback_expired_rejected(self):
        self.bind()
        self.start_observer('expired')
        with self.assertRaises(RuntimeError):
            self.readback()

    def test_readback_unknown_transaction_rejected(self):
        self.bind()
        self.start_observer('unknown')
        with self.assertRaises(RuntimeError):
            self.readback()

    def test_readback_payload_drift_rejected(self):
        self.bind()
        self.start_observer('drift')
        with self.assertRaises(RuntimeError):
            self.readback()

    def test_missing_observer_does_not_create_socket(self):
        self.bind()
        with self.assertRaises((RuntimeError, OSError)):
            self.readback()
        self.assertFalse((self.directory / 'observer.sock').exists())

    def test_unapproved_host_operation_rejected(self):
        self.bind()
        reader = self.adapter.build_host_readback(self.cfg)
        with self.assertRaises(RuntimeError):
            reader(self.g, 'attempt-1', 'run_arbitrary_command', {})

    def test_changed_grant_rejected(self):
        self.bind()
        reader = self.adapter.build_host_readback(self.cfg)
        with self.assertRaises(RuntimeError):
            reader(dict(self.g, source_commit='f'*40), 'attempt-1',
                   'reconcile_unadmitted', {})

    def make_formal_release(self):
        # Existing full frozen Kit, unchanged source identity, no new payload.
        builder = module('frozen_kit_builder', CORE / 'build_kit.py')
        raw, kit_manifest = builder.build(
            'f4f74fdd0b6aa49e046debabf81e438b17ff20b5',
            '2c2e3c09cbda31df30e0d269b580348c55e6de87')
        kit = self.directory / 'kit'
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
            for item in archive.getmembers():
                self.assertTrue(item.isfile())
                relative = item.name.split('/',1)[1]
                self.assertNotIn('..', relative.split('/'))
                dest = kit / relative
                dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                dest.write_bytes(archive.extractfile(item).read())
                os.chmod(str(dest), 0o600)
        kit_pin = hashlib.sha256((kit / 'attempt5-manifest.json').read_bytes()).hexdigest()
        legacy_pin = hashlib.sha256((kit / 'legacy/recovery-kit-manifest.json').read_bytes()).hexdigest()
        self.binding['legacy_manifest_sha256'] = legacy_pin
        release = self.directory / 'release'
        code = release / 'production/p2_attempt5'
        code.mkdir(parents=True)
        for name in ('entry.py','assembly.py','registry.py','native_adapter.py'):
            shutil.copyfile(str(PROD / name), str(code / name))
        sidecar = code / 'native_adapter.py.binding.json'
        sidecar.write_bytes(self.adapter.canonical(self.binding))
        os.chmod(str(sidecar), 0o600)
        files = {str(p.relative_to(release)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in code.iterdir()}
        manifest = {'source_commit': 'e'*40, 'source_tree': 'd'*40,
            'reviewed_core_commit': kit_manifest['source_commit'],
            'reviewed_core_tree': kit_manifest['source_tree'],
            'inherited_manifest_sha256': kit_pin, 'files': files}
        manifest_raw = registry.canonical(manifest)
        manifest_path = release / 'MANIFEST.json'
        manifest_path.write_bytes(manifest_raw)
        manifest_pin = hashlib.sha256(manifest_raw).hexdigest()
        self.g.update(source_commit='e'*40, source_tree='d'*40,
            manifest_sha256=manifest_pin, recovery_entry='native_recovery.NativeRecovery')
        # Use original registry fixture helper, not a different gate or mock.
        self.fixture = registry_tests.RegistryTests(methodName='test_formal_cli_register_then_independent_process_query')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        cfg = dict(self.fixture.config, principal=self.cfg['principal'], grant=self.g,
            issuer=self.cfg['issuer'], key=str(self.directory / 'key.pem'),
            public_der_sha256=self.public_pin,
            socket=str(self.directory / 'issuer.sock'), database=str(self.directory / 'authority.sqlite'),
            adapter_path=str(code / 'native_adapter.py'),
            adapter_sha256=files['production/p2_attempt5/native_adapter.py'],
            ledger_directory=str(self.directory / 'ledger'))
        self.fixture.rebind_config(cfg)
        self.fixture.register()
        store = AuthorityStore(cfg['database'], initialize=True)
        store.register(self.g)
        store.close()
        self.config = cfg
        self.command = [sys.executable,'-I','-B','-S',str(code / 'entry.py'), 'serve',
            '--kit-root',str(kit),'--loader-sha256',
            hashlib.sha256((kit / 'attempt5/runtime/versioned_entry.py').read_bytes()).hexdigest(),
            '--manifest-sha256',kit_pin,'--config',self.fixture.config_ref['path'],
            '--config-sha256',self.fixture.config_ref['sha256'],
            '--assembly-sha256',files['production/p2_attempt5/assembly.py'],
            '--assembly-manifest',str(manifest_path),'--assembly-manifest-sha256',manifest_pin,
            '--registry-root',str(self.fixture.root),
            '--registry-id',self.fixture.record['registration_id'],
            '--registry-record-sha256',self.fixture.binding['sha256']]

    def test_formal_serve_positive_real_kit_registry_signer_store_and_readback(self):
        self.make_formal_release()
        self.start_observer()
        process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic()+20
            while not Path(self.config['socket']).exists():
                if process.poll() is not None:
                    self.fail(process.communicate()[1].decode())
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.05)
            modulus = int(subprocess.check_output(['/usr/bin/openssl','rsa',
                '-in',str(self.key),'-modulus','-noout'],stderr=subprocess.DEVNULL
                ).decode().strip().split('=')[1],16)
            provider = ReceiptProvider(assembly.UnixTransport(self.config['socket']),
                                       modulus,65537,self.config['issuer'])
            result = provider.request(self.g,'attempt-1','consume_attempt',
                {'ordinal':1,'command_sha256':'a'*64,'ledger_sha256':'b'*64})
            self.assertEqual(result['status'],'CONSUMED')
            result = provider.request(self.g,'attempt-1','reconcile_unadmitted',{})
            self.assertEqual(result['proof']['outcome'],'NO_WRITE')
            result = provider.request(self.g,'attempt-1','read_committed_outcome',{})
            self.assertEqual(result['committed']['outcome'],'NO_WRITE')
        finally:
            if process.poll() is None:
                process.terminate()
            stdout, stderr = process.communicate(timeout=15)
            self.assertEqual(process.returncode,0,stderr.decode())
            self.assertEqual(stdout,b'')

    def test_formal_run_reaches_native_factory_and_holds_missing_original_inputs(self):
        self.make_formal_release()
        # No production permit or original private plan/seed exists in Hosted.
        # Verify real entry/run wiring reaches the inherited native factory.
        command = list(self.command)
        command[5] = 'run'
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,timeout=30)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'PRIVATE_INPUT_PATH',result.stderr)
        self.assertNotIn(b'DEPLOYMENT_NOT_BOUND',result.stderr)
        self.assertFalse((self.directory / 'ledger/attempts.json').exists())


if __name__ == '__main__':
    unittest.main()
