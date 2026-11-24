import hashlib,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts.community_native_version import native_snapshot
from scripts.community_mini_http import serve
from test_community_health_dependencies import HealthDependencies

class NativeVersion(unittest.TestCase):
 def test_real_file_hashes_and_invalid_baseline(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);(r/'scripts').mkdir();p=r/'scripts/example.py';p.write_bytes(b'actual-source')
   with patch.dict(os.environ,COMMUNITY_SOURCE_SHA='a'*40):
    value=native_snapshot(r)
    self.assertEqual(value['startup_source_pins']['scripts/example.py'],hashlib.sha256(b'actual-source').hexdigest())
    self.assertIn('UNCOMMITTED_OVERLAYS',value['source_coverage'])
    self.assertNotEqual(value['version_source'],'IMAGE_BUILD_STAMP')
   for bad in ('', 'not-a-sha', 'a'*64):
    with patch.dict(os.environ,COMMUNITY_SOURCE_SHA=bad):self.assertIsNone(native_snapshot(r))
 def test_native_health_original_handler_snapshot_no_false_revision(self):
  f=HealthDependencies();f.setUp();self.addCleanup(f.doCleanups)
  root=Path(f.tmp.name)/'native';(root/'scripts').mkdir(parents=True)
  file=root/'scripts/example.py';file.write_text('original')
  with patch('scripts.community_mini_http.__file__',str(root/'scripts/community_mini_http.py')),patch.dict(os.environ,COMMUNITY_SOURCE_SHA='a'*40):
   server=serve(f.app.gateway)
  self.addCleanup(server.server_close)
  file.write_text('later disk replacement')
  with patch.dict(os.environ,COMMUNITY_SOURCE_SHA='b'*40):
   code,health,_=f.get(server)
  self.assertEqual(code,200);self.assertEqual(health['runtime_source_sha'],'a'*40)
  self.assertEqual(health['startup_source_pins']['scripts/example.py'],hashlib.sha256(b'original').hexdigest())
  self.assertIsInstance(health['observed_at'],int)
  self.assertFalse(health['production_acceptance'])

if __name__=='__main__':unittest.main()
