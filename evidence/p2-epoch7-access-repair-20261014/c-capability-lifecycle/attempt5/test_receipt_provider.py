"""Real signature/nonce tests using a disposable RSA key, never production proof."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path[:0] = [str(Path(__file__).resolve().parent/'runtime')]
from receipt_provider import ReceiptProvider, Hold, canonical, digest

class ProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.key = str(Path(cls.tmp.name)/'TEST_ONLY_NOT_A_PRODUCTION_KEY.pem')
        subprocess.check_call(['openssl','genrsa','-out',cls.key,'2048'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raw = subprocess.check_output(['openssl','rsa','-in',cls.key,'-noout','-modulus'],stderr=subprocess.DEVNULL)
        cls.modulus = int(raw.decode().strip().split('=')[1],16)
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def setUp(self): self.change = lambda body: None; self.last = None
    def transport(self, request):
        body = {'schema':1,'issuer':'TEST_ONLY','request_sha256':digest(request),
                'issued_utc':100,'expires_utc':130,'result':{'status':'VERIFIED'}}
        self.change(body)
        signature = subprocess.check_output(['openssl','dgst','-sha256','-sign',self.key],input=canonical(body))
        envelope = {'body':body,'signature':base64.b64encode(signature).decode()}
        self.last = envelope
        return envelope
    def provider(self, transport=None, clock=101):
        return ReceiptProvider(transport or self.transport,self.modulus,65537,'TEST_ONLY',clock=lambda:clock)
    def test_real_rsa_signature(self): self.assertEqual(self.provider().request({},'attempt','verify')['status'],'VERIFIED')
    def test_fresh_nonce_refuses_replay(self):
        p=self.provider();p.request({},'attempt','verify');old=self.last
        with self.assertRaises(Hold):self.provider(lambda request:old).request({},'attempt','verify')
    def test_modified_result_refuses(self):
        def transport(request):
            v=self.transport(request);v['body']['result']['status']='SUCCESS';return v
        with self.assertRaises(Hold):self.provider(transport).request({},'attempt','verify')
    def test_wrong_issuer(self):
        self.change=lambda body:body.update(issuer='OTHER')
        with self.assertRaises(Hold):self.provider().request({},'attempt','verify')
    def test_expired(self):
        with self.assertRaises(Hold):self.provider(clock=130).request({},'attempt','verify')
    def test_future_issued(self):
        with self.assertRaises(Hold):self.provider(clock=99).request({},'attempt','verify')
    def test_unknown(self):
        self.change=lambda body:body.update(result={'status':'UNKNOWN'})
        with self.assertRaises(Hold):self.provider().request({},'attempt','verify')
    def test_missing_transport(self):
        with self.assertRaises(Hold):ReceiptProvider(None,self.modulus,65537,'TEST_ONLY')
    def test_weak_key(self):
        with self.assertRaises(Hold):ReceiptProvider(self.transport,257,65537,'TEST_ONLY')
    def test_verified_flag_is_not_signature(self):
        with self.assertRaises(Hold):self.provider(lambda request:{'verified':True}).request({},'attempt','verify')

if __name__=='__main__':unittest.main()
