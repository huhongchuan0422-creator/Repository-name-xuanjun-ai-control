import sys, unittest
from production_boundary import validate_authority, production_authority, RealAuthorityNotConnected

class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.g = {'grant_id': 'grant-new-five', 'target_host':'fixed-uk-host'}
        self.row = dict(grant_id='grant-new-five',attempt_id='a1',host='fixed-uk-host',
            lease_epoch=1,fence_token='token',writer_id='writer',lease_expiry_utc=300,
            issuer='independent-authority',evidence_sha256='a'*64,
            issued_utc=100,source='INDEPENDENT_EXTERNAL_VERIFIED',bound_operation_sha256='b'*64)
    def valid(self):
        return validate_authority(self.row,self.g,'a1','b'*64,200)
    def test_well_formed_envelope_not_issuer(self):
        self.assertTrue(self.valid())
        with self.assertRaises(RealAuthorityNotConnected): production_authority()
    def test_synthetic_rejected(self):
        self.row['source']='TEST_MOCK'
        with self.assertRaisesRegex(ValueError,'SYNTHETIC'): self.valid()
    def test_wrong_grant(self):
        self.row['grant_id']='other'
        with self.assertRaisesRegex(ValueError,'SCOPE'): self.valid()
    def test_wrong_attempt(self):
        self.row['attempt_id']='a2'
        with self.assertRaisesRegex(ValueError,'SCOPE'): self.valid()
    def test_wrong_host(self):
        self.row['host']='other'
        with self.assertRaisesRegex(ValueError,'SCOPE'): self.valid()
    def test_wrong_operation(self):
        self.row['bound_operation_sha256']='c'*64
        with self.assertRaisesRegex(ValueError,'SCOPE'): self.valid()
    def test_expired_lease(self):
        self.row['lease_expiry_utc']=200
        with self.assertRaisesRegex(ValueError,'EXPIRED'):self.valid()
    def test_missing_fence(self):
        self.row['fence_token']=''
        with self.assertRaisesRegex(ValueError,'IDENTITY'):self.valid()
    def test_unknown_epoch(self):
        self.row['lease_epoch']=0
        with self.assertRaisesRegex(ValueError,'EPOCH'):self.valid()
    def test_extra_field_rejected(self):
        self.row['bypass']=True
        with self.assertRaisesRegex(ValueError,'SCHEMA'):self.valid()
if __name__ == '__main__':unittest.main()
