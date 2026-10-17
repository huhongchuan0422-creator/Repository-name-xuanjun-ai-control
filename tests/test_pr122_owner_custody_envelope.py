import base64
import copy
import unittest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from scripts import pr122_owner_custody_envelope as m


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.expected = dict(attempt_id='pr122-test-only', source_commit='a'*40,
                             launcher_sha256='b'*64, review_zip_sha256='c'*64,
                             audit_body_sha256='d'*64)
        self.p = dict(self.expected, purpose=m.PURPOSE, host=m.HOST,
                      owner_principal='fixture-owner', source_writer_principal='fixture-writer',
                      reviewer_principal='fixture-reviewer', external_evidence_sha256='e'*64,
                      issued_unix=100, expires_unix=200, key_id='fixture-key')
        public = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.trust = dict(purpose=m.PURPOSE, enabled=True, revoked=False, valid_until=300,
                          key_id='fixture-key', public_key=base64.b64encode(public).decode(),
                          registration_evidence_sha256='f'*64,
                          **{k:self.p[k] for k in ('owner_principal','source_writer_principal','reviewer_principal')})

    def signed(self):
        return dict(payload=copy.deepcopy(self.p), signature=base64.b64encode(self.key.sign(m.canonical(self.p))).decode())

    def test_valid_is_not_execution_or_independence_approval(self):
        r=m.validate(self.signed(),self.trust,self.expected,150)
        self.assertFalse(r['execution_authorized'])
        self.assertFalse(r['custody_independence_verified'])

    def test_forged_signature(self):
        e=self.signed();e['payload']['owner_principal']='attacker'
        with self.assertRaises(ValueError):m.validate(e,self.trust,self.expected,150)

    def test_each_binding_rejected(self):
        for k in self.expected:
            e=self.signed();wanted=dict(self.expected);wanted[k]='wrong'
            with self.subTest(k=k),self.assertRaises(ValueError):m.validate(e,self.trust,wanted,150)

    def test_author_cannot_self_review(self):
        self.p['reviewer_principal']=self.p['source_writer_principal']
        self.trust['reviewer_principal']=self.p['reviewer_principal']
        with self.assertRaises(ValueError):m.validate(self.signed(),self.trust,self.expected,150)

    def test_expiry_and_future(self):
        for now in (99,200,301):
            with self.subTest(now=now),self.assertRaises(ValueError):m.validate(self.signed(),self.trust,self.expected,now)

    def test_revocation_and_disabled(self):
        for k,v in (('revoked',True),('enabled',False),('valid_until',149),('key_id','other')):
            t=dict(self.trust);t[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):m.validate(self.signed(),t,self.expected,150)

    def test_missing_or_extra_fields(self):
        for k in list(self.p):
            e=self.signed();del e['payload'][k]
            with self.subTest(k=k),self.assertRaises(ValueError):m.validate(e,self.trust,self.expected,150)
        e=self.signed();e['payload']['apply_allowed']=True
        with self.assertRaises(ValueError):m.validate(e,self.trust,self.expected,150)

    def test_private_values_not_in_error(self):
        e=self.signed();e['signature']='private-invalid-value'
        with self.assertRaises(ValueError) as caught:m.validate(e,self.trust,self.expected,150)
        self.assertEqual(str(caught.exception),'CUSTODY_EVIDENCE_HOLD')

if __name__ == '__main__':unittest.main()
