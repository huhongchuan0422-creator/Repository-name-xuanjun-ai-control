import json, os, sys, tempfile, unittest
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import development_authority_release as release
import development_authority_provider as provider
from development_authority import SQLiteReplayGuard

class SigningTest(unittest.TestCase):
    def test_cli_and_provider(self):
        with tempfile.TemporaryDirectory() as d:
            def put(name, data):
                p=os.path.join(d,name)
                with open(p,'w') as f: f.write(data if isinstance(data,str) else json.dumps(data))
                os.chmod(p,0o600); return p
            key=Ed25519PrivateKey.generate()
            priv=put('key',key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode())
            pub=put('pub',key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode())
            artifact=put('artifact','synthetic'); commit='a'*40; tree='b'*40; source='c'*64
            manifest=put('manifest',release.manifest(artifact,commit,tree,source,key,'test'))
            common=['--artifact',artifact,'--commit',commit,'--tree',tree,'--source-sha256',source,'--anchor-id','test','--manifest',manifest,'--public-key-file',pub,'--private-key-file',priv]
            paths=list(provider.TRUSTED_DEPLOYMENT_CLASSES['formal-primary'])+['/var/lib/xuanjun-task-center-test/v3/task-center-v3.sqlite3']
            policy={'schema':1,'deployment_class':'formal-primary','forbidden_ledger_paths':paths}
            pin=put('policy-in',policy); pout=os.path.join(d,'policy')
            self.assertEqual(release.main(['sign-policy']+common+['--input',pin,'--output',pout]),0)
            self.assertEqual(release.main(['sign-policy']+common+['--input',pin,'--output',pout]),69)
            replay=os.path.join(d,'replay'); guard=SQLiteReplayGuard(replay); guard.close(); st=os.stat(replay)
            token=put('token','t'*40)
            config={'ledger_db':os.path.join(d,'ledger'),'replay_db':replay,'replay_device':st.st_dev,'replay_inode':st.st_ino,'forbidden_ledger_paths':paths,'forbidden_ledger_policy_file':pout,'deployment_class':'formal-primary','issuer':'synthetic','instance_id':'synthetic','version':'1','anchor_id':'test','service_id':'synthetic','bearer_token_file':token,'private_key_file':priv,'deployment_public_key_file':pub,'deployment_anchor_id':'test'}
            cin=put('config-in',config); cout=os.path.join(d,'config')
            self.assertEqual(release.main(['sign-config']+common+['--input',cin,'--output',cout]),0)
            self.assertEqual(provider.load_config(cout)['service_id'],'synthetic')
            signed=json.load(open(cout)); signed['service_id']='tampered'; put('config',signed)
            with self.assertRaises(ValueError): provider.load_config(cout)
            signed['service_id']='synthetic'; signed['replay_inode']+=1
            signed=release._sign_document('config',{k:v for k,v in signed.items() if k!='deployment_signature'},key,'test',key.public_key()); put('config',signed)
            with self.assertRaisesRegex(ValueError,'FORMAL_REPLAY_LEDGER_IDENTITY_REQUIRED'): provider.load_config(cout)
            with self.assertRaises(ValueError): release._sign_document('policy',dict(policy, extra=1),key,'test',key.public_key())
            with self.assertRaises(ValueError): release._sign_document('policy',dict(policy, forbidden_ledger_paths=paths[1:]),key,'test',key.public_key())
            bad=json.load(open(pout)); bad['forbidden_ledger_paths'].append('/tamper'); put('policy',bad)
            with self.assertRaises(ValueError): release._sign_document('config',config,key,'test',key.public_key())
            signed_manifest=json.load(open(manifest)); signed_manifest['commit']='d'*40; put('manifest',signed_manifest)
            self.assertEqual(release.main(['sign-policy']+common+['--input',pin,'--output',os.path.join(d,'bad')]),69)

if __name__=='__main__': unittest.main()
