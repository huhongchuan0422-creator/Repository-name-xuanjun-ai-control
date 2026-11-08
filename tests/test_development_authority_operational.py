import base64, json, os, tempfile, unittest
from unittest import mock
import sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','scripts'))
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import development_authority_reader as reader
from development_authority import canonical_bytes, sign_payload
from development_authority_runtime import preflight
from development_identity_adapter import verify_registration
from development_authority_release import manifest

class Response(object):
    status=200
    def __init__(self,value): self.value=value
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self): return json.dumps(self.value).encode()

class OperationalTests(unittest.TestCase):
    def setUp(self): self.root=tempfile.TemporaryDirectory(); self.private=Ed25519PrivateKey.generate()
    def tearDown(self): self.root.cleanup()
    def secret(self,name,value):
        path=os.path.join(self.root.name,name)
        with open(path,'w') as stream: stream.write(value)
        os.chmod(path,0o600); return path
    def config(self):
        public=self.private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        return {'url':'http://127.0.0.1:8787/api/v3/development-authority',
          'bearer_token_file':self.secret('token','x'*32),'public_key_file':self.secret('public',public),
          'replay_db':os.path.join(self.root.name,'replay.db'),'anchor_id':'anchor-1',
          'issuer':'formal-issuer','instance_id':'provider-1','version':'3.0.1','service_id':'reader-1',
          'attempt_id':'attempt-1','lease_id':'lease-1','fence':1,'epoch':1,
          'resource_scope_digest':'a'*64,'max_age':5.0}
    def payload(self,authorized=True):
        return {'schema':3,'kind':'DEVELOPMENT_WRITER_AUTHORITY','issuer':'formal-issuer',
          'provider':{'instance_id':'provider-1','version':'3.0.1'},
          'reader':{'service_identity':'reader-1','permission':'development-authority:read'},
          'request':{'request_id':'request-1','task_id':'task-1'},'observed_at':1000.0,
          'task':{'task_id':'task-1','state':'RUNNING','spec_sha256':'b'*64,'checkpoint_sha256':'c'*64},
          'writer':{},'assignment':{'attempt_id':'attempt-1','lease_id':'lease-1','fence':1,'epoch':1,
          'lock_provider_id':'p','resource_scope_digest':'a'*64,'resource_keys':['git:x']},
          'authority':{'state':'VALID','valid_until':1010.0,'authorized':authorized},
          'revocation':{'state':'VALID','old_fence_invalidated':0}}
    def test_http_200_authorized_false_and_reader_exit_69(self):
        config=self.config(); envelope=sign_payload(self.payload(False),'anchor-1',self.private)
        config_file=self.secret('config',json.dumps(config))
        with mock.patch.object(reader,'urlopen',return_value=Response(envelope)), mock.patch.object(reader.time,'time',return_value=1001.0):
            self.assertEqual(reader.main(['--config-file',config_file,'--task-id','task-1','--request-id','request-1']),69)
    def test_reader_69_is_never_success_for_bad_anchor_or_future_time(self):
        config=self.config(); config['anchor_id']='wrong'; config_file=self.secret('config2',json.dumps(config))
        envelope=sign_payload(self.payload(True),'anchor-1',self.private)
        with mock.patch.object(reader,'urlopen',return_value=Response(envelope)), mock.patch.object(reader.time,'time',return_value=999.0):
            self.assertEqual(reader.main(['--config-file',config_file,'--task-id','task-1','--request-id','request-1']),69)
    def test_authenticated_first_registration_bundle(self):
        contract={'task_id':'task-1','developer':{'issuer':'native','subject':'developer'}}
        developer=contract['developer']; unsigned={'issuer':'owner-auth','subject':'owner','developer':developer,
          'contract_sha256':__import__('hashlib').sha256(canonical_bytes(contract)).hexdigest(),'valid_until':2000.0}
        grant=dict(unsigned,signature=base64.b64encode(self.private.sign(canonical_bytes(unsigned))).decode())
        value=verify_registration({'contract':contract,'owner_grant':grant,'developer_identity':developer},self.private.public_key(),1000.0)
        self.assertEqual(value['developer'],developer)
        with self.assertRaisesRegex(ValueError,'OWNER_GRANT'):
            verify_registration({'contract':contract,'owner_grant':dict(grant,valid_until=999.0),'developer_identity':developer},self.private.public_key(),1000.0)
    def test_runtime_preflight_is_verifiable_and_manifest_hash_is_fixed(self):
        result=preflight(); self.assertEqual(set(result),{'ok','facts','errors','requirements'})
        artifact=self.secret('artifact','application bytes'); value=manifest(artifact,'a'*40,'b'*40)
        self.assertEqual(value['artifact_sha256'],__import__('hashlib').sha256(b'application bytes').hexdigest())
        self.assertFalse(value['deployment_authorized'])

if __name__=='__main__': unittest.main()
