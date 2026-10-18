"""Pure package reader tests; no helper import, server or publisher invocation."""
import ast,hashlib,io,json,os,tarfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def reader(source):
 tree=ast.parse(source);tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('entries','digest','need')]
 ns=dict(hashlib=hashlib,io=io,json=json,tarfile=tarfile,Path=Path);exec(compile(tree,'package-reader-only','exec'),ns);return ns['entries']
def archive(files):
 b=io.BytesIO()
 with tarfile.open(fileobj=b,mode='w:gz') as t:
  for n,v in sorted(files.items()):
   i=tarfile.TarInfo('pr122-site-hub/'+n);i.size=len(v);t.addfile(i,io.BytesIO(v))
 return b.getvalue()
sha=lambda b:hashlib.sha256(b).hexdigest()
def synthetic():
 files={f'overlay/public/file{i}.txt':b'fixture' for i in range(453)}
 rows=[dict(path=f'page{i}.html',sha256=sha(b'fixture'),size=7) for i in range(1288)]
 stage=dict(status='ISOLATED_INTEGRATION_CANDIDATE',production_approved=False,source_archive_sha256='74545480300d8f5ba9b3bd87c6f7e40930eb914e34330923ab4b5a57d6f66e63',final_files=1288,files={r['path']:r['sha256'] for r in rows})
 files.update({'candidate-manifest.json':json.dumps({'files':rows}).encode(),'FULL_SOURCE_STAGE_MANIFEST.json':json.dumps(stage).encode(),'bin/pr122_website_release.py':b'not executable synthetic publisher','PRODUCTION_EXECUTION.lock':b'REVIEW_ONLY','PUBLISHER_PROVENANCE.json':b'{}'})
 files['BUILD_PROVENANCE.json']=json.dumps(dict(scope='FULL_PINNED_SOURCE_REVIEW_CANDIDATE',production_approved=False,source_archive_sha256=stage['source_archive_sha256'],stage_manifest_sha256=sha(files['FULL_SOURCE_STAGE_MANIFEST.json']))).encode()
 files['PACKAGE_MANIFEST.json']=json.dumps({'files':[dict(path=k,size=len(v),sha256=sha(v)) for k,v in files.items()]}).encode()
 return archive(files)
class SchemaTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.raw=Path(os.environ['PR122_FULL_STATIC_PACKAGE']).read_bytes() if os.environ.get('PR122_FULL_STATIC_PACKAGE') else synthetic();cls.read=staticmethod(reader((ROOT/'scripts/pr122_site_hub_unified_release.py').read_text()))
  with tarfile.open(fileobj=io.BytesIO(cls.raw)) as t:cls.files={m.name.removeprefix('pr122-site-hub/'):t.extractfile(m).read() for m in t}
 def pins(self,files=None,raw=None):
  f=files or self.files;return dict(package_schema='FULL_STATIC_REVIEW_V1',static_artifact_sha256=sha(raw or self.raw),package_manifest_sha256=sha(f['PACKAGE_MANIFEST.json']),candidate_manifest_sha256=sha(f['candidate-manifest.json']),publisher_sha256=sha(f['bin/pr122_website_release.py']),full_stage_manifest_sha256=sha(f['FULL_SOURCE_STAGE_MANIFEST.json']),build_provenance_sha256=sha(f['BUILD_PROVENANCE.json']),source_archive_sha256='74545480300d8f5ba9b3bd87c6f7e40930eb914e34330923ab4b5a57d6f66e63')
 def mutated(self,key,obj):
  f=dict(self.files);f[key]=json.dumps(obj).encode();f['PACKAGE_MANIFEST.json']=json.dumps({'files':[dict(path=k,size=len(v),sha256=sha(v)) for k,v in f.items() if k!='PACKAGE_MANIFEST.json']}).encode();raw=archive(f);return raw,self.pins(f,raw)
 def test_legacy_schema_unchanged_synthetic_shape(self):
  f=dict(self.files);f.pop('FULL_SOURCE_STAGE_MANIFEST.json');f.pop('BUILD_PROVENANCE.json');f['COMPOSITION_MANIFEST.json']=b'{"fixture":true}'
  f['PACKAGE_MANIFEST.json']=json.dumps({'files':[dict(path=k,size=len(v),sha256=sha(v)) for k,v in f.items() if k!='PACKAGE_MANIFEST.json']}).encode()
  raw=archive(f);p=self.pins();p.pop('package_schema');p.update(static_artifact_sha256=sha(raw),package_manifest_sha256=sha(f['PACKAGE_MANIFEST.json']),composition_manifest_sha256=sha(f['COMPOSITION_MANIFEST.json']))
  self.assertEqual(len(self.read(raw,p)),459)
 def test_rebound_stage_map_still_rejected(self):
  f=dict(self.files);stage=json.loads(f['FULL_SOURCE_STAGE_MANIFEST.json']);stage['files']['index.html']='0'*64;f['FULL_SOURCE_STAGE_MANIFEST.json']=json.dumps(stage).encode()
  provenance=json.loads(f['BUILD_PROVENANCE.json']);provenance['stage_manifest_sha256']=sha(f['FULL_SOURCE_STAGE_MANIFEST.json']);f['BUILD_PROVENANCE.json']=json.dumps(provenance).encode()
  f['PACKAGE_MANIFEST.json']=json.dumps({'files':[dict(path=k,size=len(v),sha256=sha(v)) for k,v in f.items() if k!='PACKAGE_MANIFEST.json']}).encode();raw=archive(f)
  with self.assertRaisesRegex(RuntimeError,'FULL_STAGE_FILE_BINDING'):self.read(raw,self.pins(f,raw))
 def test_noncanonical_and_unsafe_members(self):
  for name,kind in [('overlay//public/x','file'),('overlay/./x','file'),('/absolute','file'),('../escape','file'),('overlay/link','symlink'),('overlay/hard','hardlink')]:
   with self.subTest(name=name):
    b=io.BytesIO()
    with tarfile.open(fileobj=b,mode='w:gz') as t:
     for i,(n,v) in enumerate(self.files.items()):
      item=tarfile.TarInfo('pr122-site-hub/'+(name if i==0 else n));item.size=len(v)
      if i==0 and kind!='file':item.type=tarfile.SYMTYPE if kind=='symlink' else tarfile.LNKTYPE;item.linkname='target';item.size=0
      t.addfile(item,io.BytesIO(v) if item.isfile() else None)
    raw=b.getvalue();p=self.pins();p['static_artifact_sha256']=sha(raw)
    with self.assertRaises(RuntimeError):self.read(raw,p)
 def test_duplicate_member_rejected(self):
  b=io.BytesIO();items=list(self.files.items())
  with tarfile.open(fileobj=b,mode='w:gz') as t:
   for i,(n,v) in enumerate(items):
    item=tarfile.TarInfo('pr122-site-hub/'+(items[0][0] if i==1 else n));item.size=len(v);t.addfile(item,io.BytesIO(v))
  raw=b.getvalue();p=self.pins();p['static_artifact_sha256']=sha(raw)
  with self.assertRaisesRegex(RuntimeError,'ARCHIVE_MEMBERS'):self.read(raw,p)
 def test_exact_real_package(self):self.assertEqual(len(self.read(self.raw,self.pins())),460)
 def test_old_reader_rejects_new_package(self):
  p=self.pins();p.pop('package_schema')
  with self.assertRaisesRegex(RuntimeError,'ARCHIVE_MEMBERS'):self.read(self.raw,p)
 def test_default_legacy_does_not_auto_upgrade(self):
  p=self.pins();p.pop('package_schema')
  with self.assertRaisesRegex(RuntimeError,'ARCHIVE_MEMBERS'):self.read(self.raw,p)
 def test_unknown_schema(self):
  p=self.pins();p['package_schema']='anything'
  with self.assertRaisesRegex(RuntimeError,'PACKAGE_SCHEMA'):self.read(self.raw,p)
 def test_outer_hash(self):
  with self.assertRaisesRegex(RuntimeError,'STATIC_PACKAGE_HASH'):self.read(self.raw+b'x',self.pins())
 def test_manifest_pin(self):
  p=self.pins();p['package_manifest_sha256']='0'*64
  with self.assertRaisesRegex(RuntimeError,'PACKAGE_MANIFEST_HASH'):self.read(self.raw,p)
 def test_stage_pin(self):
  p=self.pins();p['full_stage_manifest_sha256']='0'*64
  with self.assertRaisesRegex(RuntimeError,'FULL_STATIC_BINDING'):self.read(self.raw,p)
 def test_stage_map_mismatch(self):
  j=json.loads(self.files['FULL_SOURCE_STAGE_MANIFEST.json']);j['files']['index.html']='0'*64;raw,p=self.mutated('FULL_SOURCE_STAGE_MANIFEST.json',j)
  # provenance remains exact original; both layers must reject any substituted stage.
  with self.assertRaisesRegex(RuntimeError,'BUILD_STAGE_BINDING'):self.read(raw,p)
 def test_production_flag_rejected(self):
  j=json.loads(self.files['FULL_SOURCE_STAGE_MANIFEST.json']);j['production_approved']=True;raw,p=self.mutated('FULL_SOURCE_STAGE_MANIFEST.json',j)
  with self.assertRaisesRegex(RuntimeError,'FULL_STATIC_SCOPE'):self.read(raw,p)
 def test_source_mismatch(self):
  p=self.pins();p['source_archive_sha256']='0'*64
  with self.assertRaisesRegex(RuntimeError,'FULL_SOURCE_BINDING'):self.read(self.raw,p)
if __name__=='__main__':unittest.main()
