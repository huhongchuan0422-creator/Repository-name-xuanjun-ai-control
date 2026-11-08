import base64,os,sys,tempfile,unittest
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','bootstrap'))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
import controller as c
import secure_bootstrap as b

class TreeReceiptTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=os.getcwd());self.root=self.tmp.name;os.mkdir(os.path.join(self.root,'base'),0o700)
  self.rootfd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.base=os.path.join(self.root,'base')
  self.data=b'expected';self.manifest={'members':{'file':{'type':'file','size':len(self.data),'sha256':b.sha(self.data)}}}
  self.write('file',self.data);self.write('.bootstrap-manifest.json',b.canonical(self.manifest))
 def tearDown(self):os.close(self.rootfd);self.tmp.cleanup()
 def write(self,name,data):
  with open(os.path.join(self.base,name),'wb') as f:f.write(data)
  os.chmod(os.path.join(self.base,name),0o600)
 def test_tree_digest_and_tampered_file(self):
  first=c.verified_tree(self.rootfd,'base',os.getuid());self.assertEqual(len(first),64)
  self.write('file',b'tampered')
  with self.assertRaises(c.ControllerError):c.verified_tree(self.rootfd,'base',os.getuid())
 def test_extra_link_and_device_rejected(self):
  for name,target in [('link','file'),('device','/dev/null')]:
   os.symlink(target,os.path.join(self.base,name))
   try:
    with self.assertRaises(c.ControllerError):c.verified_tree(self.rootfd,'base',os.getuid())
   finally:os.unlink(os.path.join(self.base,name))
 def test_hardlink_and_mode_rejected(self):
  os.link(os.path.join(self.base,'file'),os.path.join(self.base,'hard'))
  with self.assertRaises(c.ControllerError):c.verified_tree(self.rootfd,'base',os.getuid())
  os.unlink(os.path.join(self.base,'hard'));os.chmod(os.path.join(self.base,'file'),0o644)
  with self.assertRaises(c.ControllerError):c.verified_tree(self.rootfd,'base',os.getuid())
 def test_signed_receipt_wrong_operation_and_tamper(self):
  key=Ed25519PrivateKey.generate();pub=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
  trust=b.canonical({'mode':'ED25519','environment':'TEST_ONLY','controller':'fixture','public_key':base64.b64encode(pub).decode()})
  payload={'operation':'rollback','attempt':'a','current_tree_sha256':'1'*64,'prestate_tree_sha256':'2'*64,'controller':'fixture','outcome':'SUCCEEDED'}
  sig=base64.b64encode(key.sign(b.canonical(payload))).decode();raw=b.canonical({'payload':payload,'signature':sig})
  c.verify_operation_receipt(raw,trust,'rollback','a','1'*64,'2'*64)
  with self.assertRaises(c.ControllerError):c.verify_operation_receipt(raw,trust,'install','a','1'*64,'2'*64)
  with self.assertRaises(c.ControllerError):c.verify_operation_receipt(b.canonical({'payload':payload,'signature':base64.b64encode(b'bad').decode()}),trust,'rollback','a','1'*64,'2'*64)
if __name__=='__main__':unittest.main()
