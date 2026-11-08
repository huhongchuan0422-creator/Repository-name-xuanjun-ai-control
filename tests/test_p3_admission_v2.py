"""TEST_ONLY ephemeral signing keys; never production trust anchors."""
import os
import sqlite3
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from src.p3_admission_v2 import TrustStore, canonical
from src.p3_operation_kernel import MIGRATION, RunnerOperationStore
from src.p3_host_boundaries import AdmissionGate, ReceiptVerifier, RunnerController
from tests.test_p3_host_boundaries import SUBJECT, NOW, admission as gate_v1, Provider, Runner

class CountingStore(RunnerOperationStore):
    def __init__(self, connect):
        super(CountingStore, self).__init__(connect)
        self.reservations = 0
    def reserve(self, *args):
        self.reservations += 1
        return super(CountingStore, self).reserve(*args)

class V2Tests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp()
        os.close(fd)
        self.addCleanup(lambda: os.unlink(self.path))
        def connect(): return sqlite3.connect(self.path, timeout=10)
        db=connect(); db.execute(MIGRATION); db.commit(); db.close()
        self.store=CountingStore(connect)
        self.keys={name: Ed25519PrivateKey.generate() for name in ('authority','provider','adapter')}
        self.trust=TrustStore({name:(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw), name, name+'-id') for name,key in self.keys.items()}, {('provider','provider-id'):{'a'*64}, ('adapter','adapter-id'):{'b'*64}})
        self.provider=Provider(); self.runner=Runner(self.provider)
        self.adapter_calls=[]; self.adapter_identity_calls=[]
        self.a=dict(task_id=SUBJECT['task_id'],spec_id=SUBJECT['spec_hash'],artifact_digest='c'*64,attempt_id='attempt',run_id=SUBJECT['run_id'],session_id=SUBJECT['session_id'],lease_id='lease',fence=SUBJECT['fence'],epoch=SUBJECT['epoch'],generation=SUBJECT['generation'],subject='caller',provider_id='provider-id',adapter_id='adapter-id',permission_scope='p3:launch',operation_id='op-1',issued_at=900,expires_at=1100)
        self.proof=self.make_proof(self.a)
        self.identities={role:self.make_identity(role) for role in ('provider','adapter')}
        self.provider.identity=lambda: self.identities['provider']
        def identity():
            self.adapter_identity_calls.append(1)
            return self.identities['adapter']
        self.runner.identity=identity
        def execute(op, digest, admission, operation):
            self.adapter_calls.append((op,digest))
            return self.runner._ack(operation)
        self.runner.execute=execute
        self.runner.reconcile=lambda op,digest,subject: 'ack-launch'
        self.controller=self.make_controller()
    def sign(self, value, role, domain):
        result=dict(value, key_id=role)
        result['signature']=self.keys[role].sign(domain+canonical(result)).hex()
        return result
    def make_proof(self, value):
        return self.sign(dict(value,authority_identity='authority-id'),'authority',b'P3-GATE-V2\x00')
    def make_identity(self, role):
        return self.sign(dict(id=role+'-id',binary_digest=('a' if role=='provider' else 'b')*64,instance='instance',epoch=SUBJECT['epoch'],capabilities=['launch','resume'],issued_at=900,expires_at=1100),role,b'P3-IDENTITY-V2\x00')
    def make_controller(self):
        gate=AdmissionGate(lambda:gate_v1(),lambda:NOW,execution_enabled=True)
        return RunnerController(gate,ReceiptVerifier(self.provider),self.runner,self.store,self.trust,lambda:self.proof,lambda:1000,'caller')
    def invoke(self): return self.controller.launch(SUBJECT,self.a)
    def assert_denied(self):
        with self.assertRaises((ValueError, PermissionError, TypeError)):
            self.invoke()
        self.assertEqual(0,self.store.reservations)
        self.assertEqual([],self.adapter_calls)
    def test_each_admission_field_mismatch_and_missing_fails_before_reserve(self):
        for key, value in list(self.a.items()):
            old=self.a[key]
            self.a[key] = value+1 if type(value) is int else ('d'*64 if key=='artifact_digest' else value+'x')
            self.assert_denied()
            self.a[key]=old
            del self.a[key]
            self.assert_denied()
            self.a[key]=old
    def test_bad_gate_signature_unknown_key_and_expiration(self):
        valid=self.proof
        for change in ({'key_id':'unknown'}, {'signature':'00'*64}, {'expires_at':999}):
            self.proof=dict(valid,**change)
            self.assert_denied()
            self.assertEqual([],self.adapter_identity_calls)
        self.proof=valid
    def test_identity_mismatch_signature_expiration_and_unknown_key(self):
        for role in ('provider','adapter'):
            good=self.identities[role]
            for change in ({'id':'other'}, {'signature':'00'*64}, {'expires_at':999}, {'key_id':'unknown'}, {'binary_digest':'d'*64}):
                self.identities[role]=dict(good,**change)
                self.assert_denied()
            self.identities[role]=good
    def test_signed_gate_cross_task_attempt_replay_fails(self):
        for field in ('task_id','attempt_id'):
            altered=dict(self.a); altered[field]+='-other'
            self.proof=self.make_proof(altered)
            self.assert_denied()
    def test_validly_signed_expired_gate_and_identities_fail(self):
        self.proof=self.make_proof(dict(self.a, expires_at=999))
        self.assert_denied()
        self.proof=self.make_proof(self.a)
        for role in ('provider','adapter'):
            good=self.identities[role]
            unsigned={k:v for k,v in good.items() if k not in ('key_id','signature')}
            unsigned['expires_at']=999
            self.identities[role]=self.sign(unsigned,role,b'P3-IDENTITY-V2\x00')
            self.assert_denied()
            self.identities[role]=good
    def test_extra_fields_bool_integer_and_revoked_key_fail(self):
        self.a['extra']='x'
        self.assert_denied()
        del self.a['extra']
        old=self.a['epoch']; self.a['epoch']=True
        self.assert_denied(); self.a['epoch']=old
        self.trust.revoked=frozenset(('authority',))
        self.assert_denied()
    def test_operation_id_conflict_never_reexecutes(self):
        self.invoke()
        self.a['attempt_id']='another-attempt'
        self.proof=self.make_proof(self.a)
        with self.assertRaises(ValueError): self.invoke()
        self.assertEqual(1,len(self.adapter_calls))

    def test_normal_replay_and_restart_execute_once(self):
        first=self.invoke(); second=self.invoke()
        self.controller=self.make_controller(); third=self.invoke()
        self.assertEqual(first,second); self.assertEqual(first,third)
        self.assertEqual(1,len(self.adapter_calls))
        self.assertEqual('ACKNOWLEDGED_AWAITING_STARTED',first['state'])
    def test_production_without_trust_and_legacy_admission_denied(self):
        self.controller.trust_store=None
        self.assert_denied()
        self.controller=self.make_controller()
        self.a=gate_v1()
        self.assert_denied()
