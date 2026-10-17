import base64
import hashlib
import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]

def load(name):
    s=importlib.util.spec_from_file_location(name,ROOT/(name+'.py'))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

class IntegrityTests(unittest.TestCase):
    def test_approved_probe_and_payload_exact(self):
        expected={'readonly_probe.py':'118e3e972fd94a34647c1a289f449caf4eef40dbb444611d99f53d155cd148ba','approved_account_prepare.py':'885b850864465a554d99adbdfb4b4d4e33abf5dc52e7dcf84f27597c247c0818'}
        for name,h in expected.items():self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),h)
    def test_generated_embedding_and_manifest_reproducible(self):
        b=load('build_domestic');first=b.build();out=ROOT/'domestic-install-package'
        original={p.name:p.read_bytes() for p in out.iterdir() if p.is_file()}
        self.assertEqual(first,b.build())
        self.assertEqual(original,{p.name:p.read_bytes() for p in out.iterdir() if p.is_file()})
        s=importlib.util.spec_from_file_location('generated',out/'domestic-readonly-helper.py')
        m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
        self.assertEqual(base64.b64decode(m.PAYLOAD_B64),(ROOT/'approved_account_prepare.py').read_bytes())
        self.assertEqual(base64.b64decode(m.PROBE_B64),(ROOT/'readonly_probe.py').read_bytes())
        for name in ('domestic_bootstrap.py','domestic-readonly-helper.py'):
            self.assertEqual(first['files'][name]['sha256'],hashlib.sha256((out/name).read_bytes()).hexdigest())
    def test_no_workflow_activation_or_cloud_transport_in_new_runtime(self):
        for name in ('domestic_helper.py','domestic_bootstrap.py'):
            raw=(ROOT/name).read_text()
            for term in ('RunCommand','AssumeRole','ALIBABA_CLOUD_ACCESS_KEY','actions/checkout'):
                self.assertNotIn(term,raw)
        self.assertFalse((ROOT/'.github').exists())

if __name__=='__main__':unittest.main()
