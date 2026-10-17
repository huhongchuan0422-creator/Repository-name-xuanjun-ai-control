import copy
import json
import unittest
from scripts import p2_swas_receipt_validator as v


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.body=dict(hostname=v.HOST,uid=0,python=[3,6,8],nonce='fixture_nonce',private_inputs_read=False)
        self.d=dict(InvokeId='t-fixture',InstanceId=v.INSTANCE,InvocationStatus='Success',ExitCode=0,Output=json.dumps(self.body))

    def test_valid_is_not_p2_acceptance(self):
        r=v.validate(self.d,'t-fixture','fixture_nonce')
        self.assertFalse(r['p2_accepted'])
        self.assertFalse(r['private_inputs_read'])

    def test_wrong_invocation_and_instance(self):
        for k in ('InvokeId','InstanceId'):
            d=dict(self.d);d[k]='other'
            with self.subTest(k=k),self.assertRaises(v.Hold):v.validate(d,'t-fixture','fixture_nonce')

    def test_wrong_host_nonce_uid(self):
        for k,x in (('hostname','other'),('nonce','other'),('uid',True),('uid',1)):
            b=dict(self.body);b[k]=x;d=dict(self.d,Output=json.dumps(b))
            with self.subTest(k=k,x=x),self.assertRaises(v.Hold):v.validate(d,'t-fixture','fixture_nonce')

    def test_private_payload_rejected_and_not_echoed(self):
        b=dict(self.body,seed='PRIVATE_SENTINEL');d=dict(self.d,Output=json.dumps(b))
        with self.assertRaises(v.Hold) as c:v.validate(d,'t-fixture','fixture_nonce')
        self.assertNotIn('PRIVATE_SENTINEL',str(c.exception))

    def test_oversized_output(self):
        with self.assertRaises(v.Hold):v.validate(dict(self.d,Output='x'*2049),'t-fixture','fixture_nonce')

    def test_duplicate_json(self):
        raw=json.dumps(self.body)[:-1]+',"uid":0}'
        with self.assertRaises(v.Hold):v.validate(dict(self.d,Output=raw),'t-fixture','fixture_nonce')

    def test_python_version_constraints(self):
        for ver in ([3,11,0],[3,6,True],'3.6.8',[3,6,-1]):
            b=dict(self.body,python=ver)
            with self.subTest(ver=ver),self.assertRaises(v.Hold):v.validate(dict(self.d,Output=json.dumps(b)),'t-fixture','fixture_nonce')

    def test_unsuccessful_status_and_exit(self):
        for k,x in (('ExitCode',True),('ExitCode',1),('InvocationStatus','Running')):
            d=dict(self.d);d[k]=x
            with self.subTest(k=k,x=x),self.assertRaises(v.Hold):v.validate(d,'t-fixture','fixture_nonce')

if __name__=='__main__':unittest.main()
