import copy,hashlib,io,json,time,unittest
from pathlib import Path
from email.message import Message
from scripts.community_preview_readiness import check
ROOT=Path(__file__).resolve().parents[1]
class NativeVersion(unittest.TestCase):
 def setUp(self):
  self.c=json.loads((ROOT/'deploy/community-preview/native-snapshot-version.json').read_text())
  self.pins=json.loads((ROOT/'tests/fixtures/pomelo-native-startup-pins.json').read_text())
  self.health=dict(status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,observed_at=int(time.time()),startup_source_pins=self.pins,**{k:self.c[k] for k in ('runtime_source_sha','version_source','source_coverage','startup_source_manifest_sha256')})
  self.identity=dict(product_source_sha=self.c['frontend_manifest_sha256'],control_source_sha='c'*40,fixed_product=True,backend_source_sha=self.c['runtime_source_sha'],snapshot_binding=dict(manifest_sha256=self.c['frontend_manifest_sha256'],archive_sha256=self.c['frontend_archive_sha256'],control_source_sha='c'*40,compatibility_evidence_sha256='d'*64))
 def check(self,h=None,identity=None):
  def response(*a,**k):
   r=io.BytesIO(json.dumps(self.health if h is None else h).encode());r.status=200;r.headers=Message();r.headers['Content-Type']='application/json';r.geturl=lambda:'https://uk.wenwenwenyiyiyi.work/community-preview/community/health';return r
  return check(response,profile='uk-path-candidate',product_identity=self.identity if identity is None else identity)
 def test_exact_installed_native_coverage(self):
  r=self.check();self.assertEqual(r['status'],'BACKEND_HEALTH_VERIFIED');self.assertEqual(r['backend_version_source'],self.c['version_source']);self.assertEqual(r['startup_source_pins'],self.pins)
 def test_no_arbitrary_baseline_coverage_manifest_pins_or_stale_health(self):
  for field,value in [('runtime_source_sha','b'*40),('version_source','CLIENT_ENV'),('source_coverage','SINGLE_GIT_REVISION'),('startup_source_manifest_sha256','e'*64),('observed_at',0),('observed_at',True),('startup_source_pins',{}),('startup_source_pins',dict(self.pins,extra='a'*64))]:
   with self.subTest(field=field,value=value if field!='startup_source_pins' else 'mutated'):
    self.assertEqual(self.check(dict(self.health,**{field:value}))['status'],'BACKEND_NOT_READY')
 def test_native_not_allowed_for_other_snapshot_or_non_snapshot(self):
  for i in (dict(self.identity,product_source_sha='e'*64),dict(self.identity,snapshot_binding=dict(self.identity['snapshot_binding'],archive_sha256='e'*64)),dict(self.identity,snapshot_binding=None)):
   self.assertEqual(self.check(identity=i)['status'],'BACKEND_NOT_READY')
 def test_manifest_canonical_matches_installed(self):
  self.assertEqual(hashlib.sha256(json.dumps(self.pins,sort_keys=True,separators=(',',':')).encode()).hexdigest(),self.c['startup_source_manifest_sha256'])
if __name__=='__main__':unittest.main()
