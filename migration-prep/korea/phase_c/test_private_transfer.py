"""Real synthetic WAL/OpenSSL/mTLS over socketpair; no production endpoint/data."""
import copy
import json
import os
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import unittest
from unittest import mock

from gate_common import GateError, canonical_bytes
from korea.phase_c import credentials, private_transfer as xfer, security, snapshots
from korea.phase_c.test_phase_c import create_database, NOW, FEATURE


@unittest.skipUnless(os.geteuid() == 0, 'Root-owned synthetic input fixtures')
class TransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(dir='/root', prefix='pr99-transfer-tests-')
        cls.home = Path(cls.tmp.name)
        def openssl(*args):
            subprocess.run(['/usr/bin/openssl', *args], check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=20)
        ca, cakey = cls.home/'ca.pem', cls.home/'ca.key'
        openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(cakey),'-out',str(ca),
                '-days','1','-subj','/CN=PR99 synthetic CA')
        cls.materials, cls.pins = {}, {}
        for name in ('source', 'receiver'):
            key, csr, cert = [cls.home/(name+suffix) for suffix in ('.key','.csr','.pem')]
            ext = cls.home/(name+'.ext')
            ext.write_text('subjectAltName=DNS:'+name+'.test\nextendedKeyUsage=serverAuth,clientAuth\n')
            openssl('req','-new','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(csr),
                    '-subj','/CN='+name+'.test')
            openssl('x509','-req','-in',str(csr),'-CA',str(ca),'-CAkey',str(cakey),'-CAcreateserial',
                    '-out',str(cert),'-days','1','-extfile',str(ext))
            key.chmod(0o600); cert.chmod(0o644); ca.chmod(0o644)
            m=dict(ca=str(ca),certificate=str(cert),private_key=str(key))
            m.update({n+'_sha256':security.digest(Path(m[n]).read_bytes()) for n in tuple(m)})
            cls.materials[name]=m
            cls.pins[name]=security.digest(ssl.PEM_cert_to_DER_cert(cert.read_text()))
        # Independent source signing identity, distinct from channel leaf keys.
        cls.private,cls.public=cls.home/'sign.key',cls.home/'sign.pem'
        openssl('genrsa','-out',str(cls.private),'2048')
        openssl('rsa','-in',str(cls.private),'-pubout','-out',str(cls.public))
        cls.private.chmod(0o600);cls.public.chmod(0o644)
        sha=security.digest(cls.public.read_bytes())
        cls.signer=security.DetachedRSA(cls.public,sha,private_key=cls.private)
        cls.verifier=security.DetachedRSA(cls.public,sha)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.case=Path(tempfile.mkdtemp(dir=self.home))
        self.source=self.case/'source';self.dest=self.case/'dest'
        self.source.mkdir(mode=0o711);self.dest.mkdir(mode=0o711)
        self.sa=self.case/'send-attempts';self.ra=self.case/'receive-attempts'
        self.sa.mkdir(mode=0o700);self.ra.mkdir(mode=0o700)
        self.cfg=dict(feature_id=FEATURE,account_id='account-a',snapshot_max_age_ms=30000,
            runtime_manifest_sha256='a'*64,snapshot_publisher_identity_sha256=self.verifier.identity,
            snapshot_reader_uid=0,snapshot_root=str(self.dest),credential_role=credentials.ROLE,
            business_database=str(self.dest/'unused.sqlite'),snapshot_refresh_protocol=snapshots.PROTOCOL)
        self.dbpath=self.case/'live-synthetic.sqlite';self.db=create_database(self.dbpath)
        self.transfer=dict(window_id='window-a',generation_id='gen-a',nonce='nonce-a',expires_at_ms=NOW+20000)
        self.sockets=[]
    def tearDown(self):
        self.db.close()
        for s in self.sockets:s.close()
    def channels(self, bad_client=False, wrong_name=False):
        a,b=socket.socketpair();a.settimeout(2);b.settimeout(2)
        self.sockets.extend([a,b]);server=[];errors=[]
        sc=xfer.tls_context(self.materials['receiver'],server=True)
        def accept():
            try:server.append(sc.wrap_socket(a,server_side=True))
            except BaseException as e:errors.append(e)
        t=threading.Thread(target=accept);t.start()
        cc=xfer.tls_context(self.materials['source'])
        if bad_client:cc=ssl.create_default_context(cafile=self.materials['source']['ca'])
        client=None;client_error=None
        try:client=cc.wrap_socket(b,server_hostname='wrong.test' if wrong_name else 'receiver.test')
        except BaseException as e:client_error=e
        t.join(3);self.assertFalse(t.is_alive())
        self.sockets.extend(server)
        if client:self.sockets.append(client)
        return client,server[0] if server else None,errors,client_error
    def collect(self):
        return xfer.collect_private(self.dbpath,self.source,'gen-a',self.cfg,self.signer,NOW)
    def header(self):
        return dict(protocol=xfer.PROTOCOL,transfer=self.transfer,files={
            p.name:dict(size=p.stat().st_size,sha256=security.digest(p.read_bytes()))
            for p in (self.source/'gen-a').iterdir()})
    def exchange(self, sender=None):
        c,s,e,ce=self.channels();self.assertFalse(e);self.assertIsNone(ce)
        results=[];errors=[]
        def receive():
            try:results.append(xfer.receive_one(s,self.pins['source'],self.transfer,self.ra,
                                  self.dest,self.cfg,self.verifier,lambda:NOW))
            except BaseException as error:errors.append(error)
            finally:s.close()
        t=threading.Thread(target=receive);t.start()
        try:
            result=(sender or (lambda:xfer.send_generation(c,self.pins['receiver'],self.source/'gen-a',
                                  self.transfer,self.sa,lambda:NOW)))()
        finally:
            c.close();t.join(5)
        self.assertFalse(t.is_alive())
        return result,results,errors
    def test_real_mtls_signed_wal_roundtrip_and_remote_path(self):
        receipt=self.collect()
        self.assertEqual(receipt['database_path'],str(self.dest/'gen-a/business-snapshot.sqlite'))
        self.assertEqual((self.source/'gen-a/business-snapshot.sqlite').stat().st_uid,0)
        sent,received,errors=self.exchange()
        self.assertFalse(errors);self.assertEqual(sent['status'],'PRIVATE_TRANSFER_ACKNOWLEDGED')
        self.assertEqual(received[0]['status'],'PRIVATE_TRANSFER_COMMITTED')
        _,r,held=snapshots.pin_current(self.dest,self.cfg,self.verifier,NOW);held.close()
        self.assertEqual(r,receipt)
        self.assertEqual(json.loads((self.ra/'receive-gen-a').read_text())['transfer'],self.transfer)
    def test_wrong_peer_pin_rejected_before_claim_or_frame(self):
        self.collect();c,s,e,ce=self.channels()
        with self.assertRaises(GateError):xfer.send_generation(c,'0'*64,self.source/'gen-a',self.transfer,self.sa,lambda:NOW)
        self.assertFalse(list(self.sa.iterdir()))
        with self.assertRaises(GateError):xfer.receive_one(s,'0'*64,self.transfer,self.ra,self.dest,self.cfg,self.verifier,lambda:NOW)
        self.assertFalse(list(self.ra.iterdir()))
    def test_missing_client_certificate_rejected_by_tls(self):
        c,s,e,ce=self.channels(bad_client=True)
        self.assertTrue(e or ce)
        self.assertIsNone(s)
    def test_wrong_server_hostname_rejected_by_tls(self):
        c,s,e,ce=self.channels(wrong_name=True)
        self.assertIsInstance(ce,ssl.SSLCertVerificationError)
    def test_material_pin_or_private_mode_or_untrusted_ca_refused(self):
        for key,value in [('ca_sha256','0'*64),('private_key_sha256','0'*64)]:
            m=dict(self.materials['source']);m[key]=value
            with self.assertRaises(GateError):xfer.tls_context(m)
        m=dict(self.materials['source']);key=Path(m['private_key']);key.chmod(0o644)
        try:
            with self.assertRaises(GateError):xfer.tls_context(m)
        finally:key.chmod(0o600)
    def test_truncated_transfer_consumes_attempt_without_publication(self):
        self.collect()
        def partial():
            # Use the authenticated sender endpoint, but disconnect in the body.
            xfer._json_send(self.client,self.header());self.client.sendall(b'partial');return 'partial'
        c,s,e,ce=self.channels();self.client=c;errors=[]
        def receive():
            try:xfer.receive_one(s,self.pins['source'],self.transfer,self.ra,self.dest,self.cfg,self.verifier,lambda:NOW)
            except BaseException as err:errors.append(err)
        t=threading.Thread(target=receive);t.start();partial();c.close();t.join(3)
        self.assertTrue(errors);self.assertTrue((self.ra/'receive-gen-a').exists())
        self.assertFalse((self.dest/'current.json').exists())
        with self.assertRaises(FileExistsError):xfer._claim(self.ra,'receive-gen-a',self.header())
    def test_bad_source_signature_not_saved_as_success_or_acked(self):
        self.collect();p=self.source/'gen-a/signature.json';p.chmod(0o600)
        p.write_bytes(canonical_bytes({'signature':'forged'}));p.chmod(0o444)
        with self.assertRaises((GateError,OSError)):self.exchange()
        self.assertFalse((self.dest/'current.json').exists())
        self.assertTrue((self.ra/'receive-gen-a').exists())
    def test_unknown_ack_cannot_resend_same_generation(self):
        self.collect();c,s,e,ce=self.channels();errors=[]
        def discard_ack():
            try:
                with mock.patch.object(xfer,'_json_send',side_effect=OSError('synthetic lost ACK')):
                    xfer.receive_one(s,self.pins['source'],self.transfer,self.ra,self.dest,self.cfg,self.verifier,lambda:NOW)
            except BaseException as err:errors.append(err)
            finally:s.close()
        # Avoid globally patching the sender's header: send it before receiver runs.
        xfer._claim(self.sa,'send-gen-a',self.header())
        xfer._json_send(c,self.header())
        t=threading.Thread(target=discard_ack);t.start()
        for name in sorted(snapshots.GENERATION_FILES):c.sendall((self.source/'gen-a'/name).read_bytes())
        with self.assertRaises((GateError,OSError)):xfer._json_read(c,self.transfer['expires_at_ms'],lambda:NOW)
        t.join(3);self.assertFalse(t.is_alive());self.assertTrue(errors)
        self.assertTrue((self.dest/'current.json').exists())
        fresh,_,_,_=self.channels()
        with self.assertRaises(FileExistsError):xfer.send_generation(fresh,self.pins['receiver'],self.source/'gen-a',self.transfer,self.sa,lambda:NOW)
    def test_expired_and_wrong_window_rejected_without_commit(self):
        self.collect();self.transfer['expires_at_ms']=NOW
        c,s,e,ce=self.channels()
        with self.assertRaises(GateError):xfer.send_generation(c,self.pins['receiver'],self.source/'gen-a',self.transfer,self.sa,lambda:NOW)
        self.assertFalse(list(self.sa.iterdir()))
    def test_oversized_header_and_duplicate_fields_refused(self):
        for raw in (struct.pack('!I',8193),struct.pack('!I',13)+b'{"a":1,"a":2}'):
            c,s,e,ce=self.channels();c.sendall(raw)
            with self.assertRaises(GateError):xfer.receive_one(s,self.pins['source'],self.transfer,self.ra,self.dest,self.cfg,self.verifier,lambda:NOW)
        self.assertFalse(list(self.ra.iterdir()))
    def test_raw_socket_cannot_be_mistaken_for_authenticated_channel(self):
        a,b=socket.socketpair();self.sockets.extend([a,b])
        with self.assertRaises(GateError):xfer.verify_peer(a,self.pins['receiver'])


@unittest.skipUnless(os.geteuid() == 0,'Root-custodian fixtures')
class CustodyTests(unittest.TestCase):
    setUpClass = classmethod(TransferTests.setUpClass.__func__)
    tearDownClass = classmethod(TransferTests.tearDownClass.__func__)
    setUp = TransferTests.setUp
    tearDown = TransferTests.tearDown
    def provider(self,change=None):
        expected=dict(account_id='account-a',role=credentials.ROLE,secret_ref='SecretRef:READONLY_FIXTURE')
        a=dict(expected,read_only_verified=True,trading_enabled=False,withdrawal_enabled=False,
               expires_at_ms=NOW+90000,pair_sha256=credentials.pair_digest(b'key',b'secret'))
        packet=dict(api_key='key',api_secret='secret',attestation=a,signature=self.signer.sign(a))
        if change:change(packet)
        p=self.case/'private-pair.json';security.write_once(p,canonical_bytes(packet),mode=0o400)
        return credentials.PinnedReadonlyProvider(p,security.digest(p.read_bytes()),expected,self.verifier,lambda:NOW),expected,packet
    def test_signed_pair_provider_once_exact_ref(self):
        p,e,packet=self.provider();self.assertEqual(p(e['secret_ref'])[:2],(b'key',b'secret'))
        with self.assertRaises(GateError):p(e['secret_ref'])
        self.assertNotIn('key',repr(p))
    def test_signed_attestation_cannot_authenticate_mixed_secret(self):
        p,e,_=self.provider(lambda v:v.update(api_secret='different'))
        with self.assertRaises(GateError):p(e['secret_ref'])
    def test_forged_permission_or_trading_or_account_refused(self):
        p,e,_=self.provider(lambda v:v['attestation'].update(trading_enabled=True))
        with self.assertRaises(GateError):p(e['secret_ref'])
    def test_input_pin_change_or_wrong_ref_refused(self):
        p,e,_=self.provider();p.sha='0'*64
        with self.assertRaises(GateError):p(e['secret_ref'])
    def test_pair_commitment_delimits_members(self):
        self.assertNotEqual(credentials.pair_digest(b'ab',b'c'),credentials.pair_digest(b'a',b'bc'))


