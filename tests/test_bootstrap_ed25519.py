import os,sys,unittest
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','bootstrap'))
import ed25519_verify as e
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
class Ed25519Tests(unittest.TestCase):
 def test_rfc8032_empty_message(self):
  key=bytes.fromhex('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a')
  sig=bytes.fromhex('e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155'+'5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b')
  self.assertTrue(e.verify(key,b'',sig));self.assertFalse(e.verify(key,b'x',sig));self.assertFalse(e.verify(key,b'',sig[:-1]+bytes([sig[-1]^1])))
 def test_canonical_and_small_order(self):
  key=Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
  self.assertFalse(e.verify(key,b'',bytes(32)+e.L.to_bytes(32,'little')))
  self.assertFalse(e.verify(bytes([1])+bytes(31),b'',bytes([1])+bytes(63)))
  self.assertFalse(e.verify(e.Q.to_bytes(32,'little'),b'',bytes(64)))
 def test_cross_signatures(self):
  for i in range(64):
   k=Ed25519PrivateKey.generate();pub=k.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw);msg=('fixture-'+str(i)).encode();sig=k.sign(msg)
   self.assertTrue(e.verify(pub,msg,sig));self.assertFalse(e.verify(pub,msg+b'!',sig))

class BindingTests(unittest.TestCase):
 def test_signed_binding_and_mutations(self):
  import base64,json,time
  import secure_bootstrap as b
  k=Ed25519PrivateKey.generate();pub=k.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
  trust={'binding_key_id':'test','binding_public_key':base64.b64encode(pub).decode(),'dependency_lock_sha256':'a'*64}
  payload={'schema':1,'production_trust_anchor':'REQUIRED','expiry':int(time.time())+100,'dependency_lock_sha256':'a'*64}
  def enc(p=payload,key='test',sig=None):return b.canonical({'payload':p,'key_id':key,'signature':sig or base64.b64encode(k.sign(b.canonical(p))).decode()})
  self.assertEqual(b.verify_binding(enc(),trust,os.getuid()),payload)
  cases=[enc(key='wrong'),enc(dict(payload,expiry=1)),enc(dict(payload,dependency_lock_sha256='b'*64)),enc(sig=base64.b64encode(b'x'*64).decode())]
  obj=json.loads(enc());obj['payload']['schema']=2;cases.append(b.canonical(obj))
  for item in cases:
   with self.assertRaises(b.Hold):b.verify_binding(item,trust,os.getuid())
