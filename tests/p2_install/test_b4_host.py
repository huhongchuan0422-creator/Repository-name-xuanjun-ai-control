"""Exact Python3.6.8 host API tests; no server/Docker access."""
import base64,hashlib,importlib.util,io,json,os,stat,subprocess,sys,tarfile,tempfile,unittest
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('b4_host',str(REPO/'scripts/p2_b4_owner_sandbox_20261020.py'))
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
class Host(unittest.TestCase):
    def test_exact_368_when_required(self):
        if os.environ.get('REQUIRE_PYTHON368')=='1':self.assertEqual(sys.version_info[:3],(3,6,8))
    def test_reused_transport_is_original_verified_wrapper(self):
        raw=(REPO/'scripts/p2_b3_owner_finalize_20261020.py').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),h.TRANSPORT_SHA)
        buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
            item=tarfile.TarInfo('scripts/p2_b3_owner_finalize_20261020.py');item.size=len(raw);archive.addfile(item,io.BytesIO(raw))
        raw=buffer.getvalue();packet=json.dumps({'tar_bytes':len(raw),'tar_sha256':hashlib.sha256(raw).hexdigest(),'tar_b64':base64.b64encode(raw).decode()}).encode()
        transport=h.transport(packet,hashlib.sha256(packet).hexdigest())
        self.assertTrue(callable(transport.run_container))
        with self.assertRaisesRegex(ValueError,'B4_BUNDLE_SHA'):h.transport(packet,'f'*64)
    def test_no_server_side_effect_on_wrong_host(self):
        if os.uname().nodename.split('.')[0]==h.HOST:self.skipTest('UK guard test never run on UK')
        result=subprocess.run([sys.executable,'-I','-B','-S',str(REPO/'scripts/p2_b4_owner_sandbox_20261020.py'),
           '--bundle','/not-an-input','--bundle-sha256','f'*64],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.assertEqual(result.returncode,2);self.assertIn(b'B4_UK_ROOT_REQUIRED',result.stdout);self.assertIn(b'Traceback',result.stderr)
if __name__=='__main__':unittest.main()
