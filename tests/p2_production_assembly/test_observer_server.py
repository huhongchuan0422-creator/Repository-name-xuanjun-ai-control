"""Isolated real Observer protocol, RSA, root files, SQLite and formal entry.

SyntheticReader is a TEST ONLY fact source. Production attach requires the real
native Driver/FiniteLiveControls/Epoch7HostObserver; no test mode ships in source.
These tests do not claim UK/native-16-phase positive installation acceptance.
"""
import base64
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import types
import unittest
from unittest import mock
import test_native_adapter as fixture
from receipt_provider import ReceiptProvider, Hold
from authority_store import AuthorityStore
from permit_cycle import policy

ROOT = Path(__file__).resolve().parents[2]
PROD = ROOT / 'production/p2_attempt5'
assembly = fixture.assembly
server = fixture.module('observer_server_test', PROD / 'observer_server.py')


class HeldTestLock(object):
    """A real disposable flock; never the UK install lock."""
    def __init__(self, path):
        self.fd = os.open(str(path),os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600)
        self.active = False
    def held(self):
        return self.active
    def __enter__(self):
        fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.active = True
        return self
    def __exit__(self,*unused):
        self.active = False
        fcntl.flock(self.fd,fcntl.LOCK_UN)
    def close(self):
        os.close(self.fd)


class SyntheticReader(object):
    def observe(self, operation, payload):
        if operation == 'verify_cycle_binding':
            return {'status':'UNCHANGED','binding':payload}
        if operation == 'reconcile_unadmitted':
            return {'status':'RECONCILED','binding':payload,'proof':{
                'outcome':'NO_WRITE','evidence_sha256':'a'*64,
                'checkpoint_sha256':'b'*64,'log_sha256':'c'*64}}
        raise RuntimeError('SYNTHETIC_ONLY_UNIMPLEMENTED_FACT')


class ObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.NativeAdapterTests.setUpClass()
        cls.keys = {}
        for name in ('observer','attestor'):
            private = fixture.NativeAdapterTests.base / (name+'.pem')
            subprocess.check_call(['/usr/bin/openssl','genrsa','-out',str(private),'2048'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            os.chmod(str(private),0o600)
            public = subprocess.check_output(['/usr/bin/openssl','pkey','-in',str(private),'-pubout'],
                stderr=subprocess.DEVNULL)
            der = subprocess.check_output(['/usr/bin/openssl','pkey','-in',str(private),
                '-pubout','-outform','DER'],stderr=subprocess.DEVNULL)
            cls.keys[name] = (private,public,hashlib.sha256(der).hexdigest())

    @classmethod
    def tearDownClass(cls):
        fixture.NativeAdapterTests.tearDownClass()

    def setUp(self):
        self.f = fixture.NativeAdapterTests(methodName='test_public_modulus_uses_pinned_public_pem')
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.directory = self.f.directory
        self.sessions = []
        self.lock = HeldTestLock(self.directory / 'fixture-native.lock')
        self.addCleanup(self.lock.close)
        self.cfg = dict(self.f.cfg, database=str(self.directory/'authority.sqlite'),
            ledger_directory=str(self.directory/'ledger'),cycle_policy=policy())
        Path(self.cfg['ledger_directory']).mkdir(mode=0o700)
        self.cfg['command_sha256'] = 'a'*64
        self.context_dir = self.directory/'contexts'
        self.context_dir.mkdir(mode=0o700)
        self.source = self.directory/'unchanged-source'
        self.source.write_bytes(b'SYNTHETIC_ONLY_PINNED_SOURCE')
        os.chmod(str(self.source),0o600)
        self.spec = {'socket':str(self.directory/'observer.sock'),
            'key':str(self.keys['observer'][0]),'public_der_sha256':self.keys['observer'][2],
            'issuer':'FIXTURE_OBSERVER','context_directory':str(self.context_dir),
            'attestor_public_key':self.write('attestor-public.pem',self.keys['attestor'][1]),
            'configuration_payloads':{}}
        self.backup = self.write('backup.json',b'{"SYNTHETIC_ONLY_BACKUP":true}')
        self.checkpoint = self.write('checkpoint.json',b'{"SYNTHETIC_ONLY_CHECKPOINT":true}')
        self.f.binding.update(schema=2,observer_service=self.spec,
            receipt_socket=self.spec['socket'],
            receipt_public_key=self.write('observer-public.pem',self.keys['observer'][1]))
        self.f.cfg = self.cfg

    def tearDown(self):
        for session in reversed(self.sessions):
            session.close()

    def write(self, name, raw):
        path = self.directory/name
        path.write_bytes(raw)
        os.chmod(str(path),0o600)
        return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()}

    def store(self, initialize=True):
        value = AuthorityStore(self.cfg['database'],initialize=initialize)
        if initialize:
            value.register(self.cfg['grant'])
        token = value.lease(self.cfg['grant'],self.cfg['principal']['writer_id'])
        value.close()
        return token

    def attest(self, **changes):
        with open('/proc/self/stat','rb') as stream:
            start = int(stream.read().rsplit(b')',1)[1].split()[19])
        token = self.store(initialize=not Path(self.cfg['database']).exists())
        body = {'schema':1,'hostname':os.uname().nodename,
            'principal':self.cfg['principal'],'grant_sha256':server.digest(self.cfg['grant']),
            'source_identity':{k:self.cfg['grant'][k] for k in
                ('source_commit','source_tree','kit_sha256','manifest_sha256')},
            'writer_pid':os.getpid(),'writer_start_ticks':start,
            'lease_epoch':token['lease_epoch'],'fence':token['fence'],
            'run_id':'SYNTHETIC_ONLY_RUN','job_id':'SYNTHETIC_ONLY_JOB',
            'invoke_id':'SYNTHETIC_ONLY_INVOKE','issued_utc':int(time.time())-1,
            'expires_utc':self.cfg['grant']['expires_utc'],
            'backup':self.backup,'checkpoint':self.checkpoint}
        body.update(changes)
        signer = assembly.OpenSSLSigner(str(self.keys['attestor'][0]),self.keys['attestor'][2])
        try:
            signature = base64.b64encode(signer(server.canonical(body))).decode('ascii')
        finally:
            signer.close()
        path = self.context_dir/('writer-%d-%d.json'%(os.getpid(),start))
        path.write_bytes(server.canonical({'body':body,'signature':signature}))
        os.chmod(str(path),0o600)
        self.context_path = path
        return body

    def create(self, initialized=False):
        if not initialized:
            self.attest()
        api = types.SimpleNamespace(read=self.f.adapter.read,decode=self.f.adapter.decode,
            reference=self.f.adapter.reference,public_key=self.f.adapter.public_key,
            protected=self.f.adapter.protected)
        def source_check():
            return self.source.read_bytes() == b'SYNTHETIC_ONLY_PINNED_SOURCE'
        session = server.ObserverSession(api,assembly,self.cfg,self.spec,source_check)
        self.sessions.append(session)
        return session

    def start(self):
        session = self.create()
        # Test-only backend fixture. Production attach rejects this object.
        authority = types.SimpleNamespace(receipt=lambda:None)
        controls = types.SimpleNamespace(install_lock=lambda:self.lock)
        session.driver = types.SimpleNamespace(controls=controls,
            journal_io=types.SimpleNamespace(authority=authority))
        session.reader = SyntheticReader()
        session.start()
        return session

    def consume(self):
        store = AuthorityStore(self.cfg['database'],initialize=False)
        token = store.lease(self.cfg['grant'],self.cfg['principal']['writer_id'])
        store.consume(self.cfg['grant'],'attempt-1',1,'a'*64,token)
        store.close()

    def pending(self,operation='reconcile_unadmitted'):
        return {'schema':1,'grant_sha256':server.digest(self.cfg['grant']),
            'attempt_id':'attempt-1','operation':operation,'nonce':'a'*32,'payload':{}}

    def client(self):
        # Actual production adapter/client and real RSA verifier.
        self.f.bind()
        return self.f.adapter.build_host_readback(self.cfg)

    def test_signed_context_real_process_and_readonly_fence(self):
        session = self.create()
        before = Path(self.cfg['database']).read_bytes()
        self.assertEqual(session.fence('CANDIDATE')[0],self.cfg['principal']['writer_id'])
        self.assertEqual(before,Path(self.cfg['database']).read_bytes())

    def test_wrong_attestation_signature_rejected(self):
        self.attest()
        value = json.loads(self.context_path.read_text())
        value['signature'] = base64.b64encode(b'0'*256).decode('ascii')
        self.context_path.write_bytes(server.canonical(value))
        with self.assertRaises((RuntimeError,Hold)):
            self.create(initialized=True)

    def test_wrong_process_attestation_rejected(self):
        self.attest(writer_pid=os.getpid()+1)
        with self.assertRaises(RuntimeError):
            self.create(initialized=True)

    def test_expired_attestation_rejected(self):
        self.attest(expires_utc=int(time.time())-1)
        with self.assertRaises(RuntimeError):
            self.create(initialized=True)

    def test_unknown_invocation_rejected(self):
        self.attest(invoke_id='UNKNOWN')
        with self.assertRaises(RuntimeError):
            self.create(initialized=True)

    def test_missing_backup_rejected(self):
        self.attest()
        Path(self.backup['path']).unlink()
        with self.assertRaises(OSError):
            self.create(initialized=True)

    def test_source_change_holds(self):
        session = self.create()
        self.source.write_bytes(b'CHANGED')
        with self.assertRaises(RuntimeError):
            session.fence('CANDIDATE')

    def test_lease_expiry_holds(self):
        session = self.create()
        store = AuthorityStore(self.cfg['database'],initialize=False)
        store.db.execute('UPDATE grants SET expiry=0')
        store.close()
        with self.assertRaises(RuntimeError):
            session.fence('CANDIDATE')

    def test_changed_fence_cannot_reuse_context(self):
        session = self.create()
        store = AuthorityStore(self.cfg['database'],initialize=False)
        store.db.execute('UPDATE grants SET fence=fence+1')
        store.close()
        with self.assertRaises(RuntimeError):
            session.fence('CANDIDATE')

    def test_other_writer_rejected(self):
        session = self.create()
        store = AuthorityStore(self.cfg['database'],initialize=False)
        store.db.execute("UPDATE grants SET writer='OTHER_WRITER'")
        store.close()
        with self.assertRaises(RuntimeError):
            session.fence('CANDIDATE')

    def test_database_replacement_rejected(self):
        session = self.create()
        session.fence('CANDIDATE')
        path = Path(self.cfg['database'])
        raw = path.read_bytes()
        path.rename(str(path)+'.retained')
        path.write_bytes(raw)
        os.chmod(str(path),0o600)
        with self.assertRaises(RuntimeError):
            session.fence('CANDIDATE')

    def test_unbound_or_non_native_driver_refused(self):
        session = self.create()
        with self.assertRaises((RuntimeError,ImportError)):
            session.attach(types.SimpleNamespace())
        self.assertFalse(Path(self.spec['socket']).exists())

    def test_socket_existing_file_preserved(self):
        session = self.create()
        Path(self.spec['socket']).write_bytes(b'RETAIN_FAILURE')
        with self.assertRaises(RuntimeError):
            session.start()
        self.assertEqual(Path(self.spec['socket']).read_bytes(),b'RETAIN_FAILURE')

    def test_unsolicited_query_holds_without_receipt(self):
        session = self.start()
        response = assembly.UnixTransport(self.spec['socket'])(
            {'schema':1,'nonce':'a'*32,'binding':{},'payload':{}})
        self.assertIn('hold',response)
        self.assertEqual(list(Path(self.cfg['ledger_directory']).glob('observer-receipt-*')),[])

    def test_real_signed_server_client_and_durable_receipt(self):
        session = self.start()
        self.consume()
        client = self.client()
        with session.request(self.pending()):
            result = client(self.cfg['grant'],'attempt-1','reconcile_unadmitted',{})
        self.assertEqual(result['result']['proof']['outcome'],'NO_WRITE')
        records = list(Path(self.cfg['ledger_directory']).glob('observer-receipt-*'))
        self.assertEqual(len(records),1)
        self.assertEqual(json.loads(records[0].read_text())['body']['receipt']['invoke_id'],
                         'SYNTHETIC_ONLY_INVOKE')

    def test_payload_mismatch_holds(self):
        session = self.start()
        self.consume()
        client = self.client()
        with session.request(self.pending()):
            with self.assertRaises((RuntimeError,Hold)):
                client(self.cfg['grant'],'attempt-1','reconcile_unadmitted',{'other':True})

    def test_fsync_failure_never_returns_signed_success(self):
        session = self.start()
        self.consume()
        client = self.client()
        with session.request(self.pending()):
            with mock.patch.object(server.os,'fsync',side_effect=OSError('SYNTHETIC_FSYNC_ERROR')):
                with self.assertRaises((RuntimeError,Hold)):
                    client(self.cfg['grant'],'attempt-1','reconcile_unadmitted',{})
        self.assertTrue(list(Path(self.cfg['ledger_directory']).glob('observer-receipt-*')))

    def test_restart_preserves_shared_consumption(self):
        session = self.start()
        self.consume()
        session.close()
        again = self.create(initialized=True)
        again.fence('attempt-1')
        with again.database() as db:
            self.assertEqual(db.execute('SELECT consumed FROM grants').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT state FROM attempts').fetchone()[0],'UNKNOWN')

    def test_unknown_operation_not_signed(self):
        session = self.start()
        self.consume()
        client = self.client()
        pending = self.pending('diagnose_attempt')
        with session.request(pending):
            with self.assertRaises((RuntimeError,Hold)):
                client(self.cfg['grant'],'attempt-1','diagnose_attempt',{})
        self.assertEqual(list(Path(self.cfg['ledger_directory']).glob('observer-receipt-*')),[])

    def test_configuration_outside_policy_rejected(self):
        session = self.create()
        session.driver = types.SimpleNamespace()
        with self.assertRaises(RuntimeError):
            session.reader.configure(None,None,{'action':{'id':'UNAPPROVED'}})

    def test_two_active_queries_refused(self):
        session = self.start()
        self.consume()
        with session.request(self.pending()):
            with self.assertRaises(RuntimeError):
                with session.request(self.pending()):
                    pass

    def test_real_formal_serve_with_production_observer_service(self):
        # Existing helper builds the actual frozen Kit and strict Registry.
        self.f.cfg = self.cfg
        self.f.make_formal_release()
        self.cfg = self.f.config
        self.f.cfg = self.cfg
        session = self.start()
        process = subprocess.Popen(self.f.command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic()+20
            while not Path(self.cfg['socket']).exists():
                if process.poll() is not None:
                    self.fail(process.communicate()[1].decode())
                self.assertLess(time.monotonic(),deadline)
                time.sleep(0.05)
            modulus,_ = self.f.adapter.public_key(self.f.binding['public_key'])
            transport = assembly.UnixTransport(self.cfg['socket'])
            class ScopedTransport(object):
                def __call__(inner, request):
                    with session.request(request):
                        return transport(request)
            provider = ReceiptProvider(ScopedTransport(),modulus,65537,self.cfg['issuer'])
            consumed = provider.request(self.cfg['grant'],'attempt-1','consume_attempt',
                {'ordinal':1,'command_sha256':'a'*64,'ledger_sha256':'b'*64})
            self.assertEqual(consumed['status'],'CONSUMED')
            result = provider.request(self.cfg['grant'],'attempt-1','reconcile_unadmitted',{})
            self.assertEqual(result['proof']['outcome'],'NO_WRITE')
            committed = provider.request(self.cfg['grant'],'attempt-1','read_committed_outcome',{})
            self.assertEqual(committed['committed']['outcome'],'NO_WRITE')
        finally:
            if process.poll() is None:
                process.terminate()
            out, err = process.communicate(timeout=15)
            self.assertEqual(process.returncode,0,err.decode())
            self.assertEqual(out,b'')

    def test_schema2_formal_run_missing_context_holds_before_attempt(self):
        self.f.cfg = self.cfg
        self.f.make_formal_release()
        self.cfg = self.f.config
        command = list(self.f.command)
        command[5] = 'run'
        result = subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'writer-',result.stderr)
        self.assertFalse((Path(self.cfg['ledger_directory'])/'attempts.json').exists())


if __name__ == '__main__':
    unittest.main()
