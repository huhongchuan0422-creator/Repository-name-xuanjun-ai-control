"""Pure package reader tests; no helper import, server or publisher invocation."""
import ast,hashlib,io,json,os,tarfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def reader(source=None):
 from scripts import pr122_site_hub_unified_release as release
 return release.entries
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
  cls.raw=Path(os.environ['PR122_FULL_STATIC_PACKAGE']).read_bytes() if os.environ.get('PR122_FULL_STATIC_PACKAGE') else synthetic();cls.read=staticmethod(reader())
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



class BrandSchemaTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.read=staticmethod(reader((ROOT/'scripts/pr122_site_hub_unified_release.py').read_text()))
  cls.contract={'schema':'FULL_STATIC_BRAND_REVIEW_V1','brand':'玄钧AI新','archive_members':1241,'overlay_files':1197,'new_files':101,'public_files':1288}
  cls.fixed=['BUILD_PROVENANCE.json', 'FULL_SOURCE_STAGE_MANIFEST.json', 'PACKAGE_MANIFEST.json', 'PRODUCTION_EXECUTION.lock', 'PUBLISHER_PROVENANCE.json', 'RELEASE_GATE.json', 'RUNTIME_MANIFEST.json', 'bin/pr122_website_release.py', 'candidate-manifest.json', 'runtime-config/RELEASE_AND_ROLLBACK.md', 'runtime-config/http-limit.conf', 'runtime-config/server-location.conf', 'runtime-config/xuanjun-site-hub-preview.service', 'runtime/scripts/community_ad_contract.py', 'runtime/scripts/community_ad_store.py', 'runtime/scripts/community_checkout.py', 'runtime/scripts/community_checkout_read_integration.py', 'runtime/scripts/community_checkout_refund_preview_read.py', 'runtime/scripts/community_demo_api.py', 'runtime/scripts/community_demo_bootstrap.py', 'runtime/scripts/community_finance_preview_extension.py', 'runtime/scripts/community_local_admin.py', 'runtime/scripts/community_merchant_contract.py', 'runtime/scripts/community_merchant_store.py', 'runtime/scripts/community_onboarding_offline.py', 'runtime/scripts/community_order_store.py', 'runtime/scripts/community_refund_preview_store.py', 'runtime/scripts/community_saas_cost_pricing.py', 'runtime/scripts/community_saas_modules.py', 'runtime/scripts/community_saas_offer_catalog.py', 'runtime/scripts/community_saas_offers.py', 'runtime/scripts/community_saas_offline_handoff.py', 'runtime/scripts/community_saas_order_preparation.py', 'runtime/scripts/community_saas_phase2.py', 'runtime/scripts/community_saas_phase2_http.py', 'runtime/scripts/community_saas_phase2_package.py', 'runtime/scripts/community_saas_phase2_recovery.py', 'runtime/scripts/community_saas_schema_guard.py', 'runtime/scripts/community_saas_unit_economics.py', 'runtime/scripts/community_storefront_snapshot.py', 'runtime/scripts/community_ui_contracts.py', 'runtime/scripts/community_visual_feedback_identity.py', 'runtime/scripts/pr122_site_hub_preview.py', 'source-pin.json']
  cls.files={name:b'non-executed synthetic fixture' for name in cls.fixed if name!='PACKAGE_MANIFEST.json'}
  rows=[dict(path=f'page{i}.html',sha256=sha(b'fixture'),size=7) for i in range(1288)]
  overlay={r['path']:(None if i<101 else '0'*64) for i,r in enumerate(rows[:1197])}
  cls.files.update({'overlay/public/'+name:b'fixture' for name in overlay})



class BrandSchemaTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.read=staticmethod(reader())
  cls.contract={'schema':'FULL_STATIC_BRAND_REVIEW_V1','brand':'玄钧AI新','archive_members':1241,'overlay_files':1197,'new_files':101,'public_files':1288}
  cls.fixed=['BUILD_PROVENANCE.json', 'FULL_SOURCE_STAGE_MANIFEST.json', 'PACKAGE_MANIFEST.json', 'PRODUCTION_EXECUTION.lock', 'PUBLISHER_PROVENANCE.json', 'RELEASE_GATE.json', 'RUNTIME_MANIFEST.json', 'bin/pr122_website_release.py', 'candidate-manifest.json', 'runtime-config/RELEASE_AND_ROLLBACK.md', 'runtime-config/http-limit.conf', 'runtime-config/server-location.conf', 'runtime-config/xuanjun-site-hub-preview.service', 'runtime/scripts/community_ad_contract.py', 'runtime/scripts/community_ad_store.py', 'runtime/scripts/community_checkout.py', 'runtime/scripts/community_checkout_read_integration.py', 'runtime/scripts/community_checkout_refund_preview_read.py', 'runtime/scripts/community_demo_api.py', 'runtime/scripts/community_demo_bootstrap.py', 'runtime/scripts/community_finance_preview_extension.py', 'runtime/scripts/community_local_admin.py', 'runtime/scripts/community_merchant_contract.py', 'runtime/scripts/community_merchant_store.py', 'runtime/scripts/community_onboarding_offline.py', 'runtime/scripts/community_order_store.py', 'runtime/scripts/community_refund_preview_store.py', 'runtime/scripts/community_saas_cost_pricing.py', 'runtime/scripts/community_saas_modules.py', 'runtime/scripts/community_saas_offer_catalog.py', 'runtime/scripts/community_saas_offers.py', 'runtime/scripts/community_saas_offline_handoff.py', 'runtime/scripts/community_saas_order_preparation.py', 'runtime/scripts/community_saas_phase2.py', 'runtime/scripts/community_saas_phase2_http.py', 'runtime/scripts/community_saas_phase2_package.py', 'runtime/scripts/community_saas_phase2_recovery.py', 'runtime/scripts/community_saas_schema_guard.py', 'runtime/scripts/community_saas_unit_economics.py', 'runtime/scripts/community_storefront_snapshot.py', 'runtime/scripts/community_ui_contracts.py', 'runtime/scripts/community_visual_feedback_identity.py', 'runtime/scripts/pr122_site_hub_preview.py', 'source-pin.json']
  cls.files={name:b'non-executed synthetic fixture' for name in cls.fixed if name!='PACKAGE_MANIFEST.json'}
  rows=[dict(path=f'page{i}.html',sha256=sha(b'fixture'),size=7) for i in range(1288)]
  overlay={r['path']:(None if i<101 else '0'*64) for i,r in enumerate(rows[:1197])}
  cls.files.update({'overlay/public/'+name:b'fixture' for name in overlay})
  cls.files['candidate-manifest.json']=json.dumps({'files':rows}).encode()
  cls.files['source-pin.json']=json.dumps({'schema_version':2,'source_archive_sha256':'7'*64,'overlay_baselines':overlay}).encode()
  cls.files['FULL_SOURCE_STAGE_MANIFEST.json']=json.dumps({'status':'ISOLATED_INTEGRATION_CANDIDATE','production_approved':False,'source_archive_sha256':'7'*64,'final_files':1288,'files':{r['path']:r['sha256'] for r in rows},'brand_projection':{'brand':'玄钧AI新'}}).encode()
  cls.files['BUILD_PROVENANCE.json']=json.dumps({'scope':'FULL_PINNED_SOURCE_REVIEW_CANDIDATE','production_approved':False,'source_archive_sha256':'7'*64,'stage_manifest_sha256':sha(cls.files['FULL_SOURCE_STAGE_MANIFEST.json']),'brand_contract':cls.contract}).encode()
  if os.environ.get('PR122_BRAND_STATIC_PACKAGE'):
   with tarfile.open(os.environ['PR122_BRAND_STATIC_PACKAGE']) as t:cls.files={m.name.removeprefix('pr122-site-hub/'):t.extractfile(m).read() for m in t}
 def packet(self,files=None):
  f=dict(self.files if files is None else files)
  f['PACKAGE_MANIFEST.json']=json.dumps({'files':[dict(path=k,size=len(v),sha256=sha(v)) for k,v in f.items() if k!='PACKAGE_MANIFEST.json']}).encode()
  raw=archive(f)
  p=SchemaTests.pins(self,files=f,raw=raw)
  p.update(package_schema='FULL_STATIC_BRAND_REVIEW_V1',source_archive_sha256=json.loads(f['BUILD_PROVENANCE.json'])['source_archive_sha256'])
  return raw,p
 def mutation(self,name,change):
  f=dict(self.files);value=json.loads(f[name]);change(value);f[name]=json.dumps(value).encode()
  if name=='FULL_SOURCE_STAGE_MANIFEST.json':
   v=json.loads(f['BUILD_PROVENANCE.json']);v['stage_manifest_sha256']=sha(f[name]);f['BUILD_PROVENANCE.json']=json.dumps(v).encode()
  return self.packet(f)
 def test_exact_brand_contract_and_payload(self):
  raw,p=self.packet();self.assertEqual(len(self.read(raw,p)),1241)
 def test_old_schemas_cannot_accept_brand_packet(self):
  raw,p=self.packet()
  for schema in ('LEGACY_UNIFIED_V1','FULL_STATIC_REVIEW_V1'):
   with self.subTest(schema=schema):
    p['package_schema']=schema
    with self.assertRaisesRegex(RuntimeError,'ARCHIVE_MEMBERS'):self.read(raw,p)
 def test_brand_schema_cannot_accept_old_full_packet(self):
  raw=synthetic()
  with tarfile.open(fileobj=io.BytesIO(raw)) as t:f={m.name.removeprefix('pr122-site-hub/'):t.extractfile(m).read() for m in t}
  raw,p=self.packet(f)
  with self.assertRaisesRegex(RuntimeError,'ARCHIVE_MEMBERS'):self.read(raw,p)
 def test_extra_missing_or_duplicate_member_rejected(self):
  for extra in (True,False):
   f=dict(self.files)
   if extra:f['extra']=b'extra'
   else:f.pop('PRODUCTION_EXECUTION.lock')
   with self.subTest(extra=extra),self.assertRaisesRegex(RuntimeError,'ARCHIVE_MEMBERS'):self.read(*self.packet(f))
  raw,p=self.packet();stream=io.BytesIO()
  with tarfile.open(fileobj=io.BytesIO(raw)) as old,tarfile.open(fileobj=stream,mode='w:gz') as new:
   first=None
   for i,m in enumerate(old):
    value=old.extractfile(m).read()
    if first is None:first=m.name
    if i==1:m.name=first
    new.addfile(m,io.BytesIO(value))
  raw=stream.getvalue();p['static_artifact_sha256']=sha(raw)
  with self.assertRaisesRegex(RuntimeError,'ARCHIVE_MEMBERS'):self.read(raw,p)
 def test_contract_requires_exact_values_and_no_extra_fields(self):
  for field,value in [('schema','FULL_STATIC_REVIEW_V1'),('brand','other'),('archive_members',1242),('archive_members',1241.0),('overlay_files',1198),('new_files',102),('public_files',1289),('extra',True)]:
   with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'BRAND_CONTRACT'):
    self.read(*self.mutation('BUILD_PROVENANCE.json',lambda v:v['brand_contract'].update({field:value})))
  with self.assertRaisesRegex(RuntimeError,'BRAND_CONTRACT'):
   self.read(*self.mutation('BUILD_PROVENANCE.json',lambda v:v.pop('brand_contract')))
 def test_stage_brand_bound_even_after_rehash(self):
  with self.assertRaisesRegex(RuntimeError,'BRAND_STAGE_CONTRACT'):
   self.read(*self.mutation('FULL_SOURCE_STAGE_MANIFEST.json',lambda v:v.update(brand_projection={'brand':'old'})))
 def test_overlay_and_source_pin_sets_are_identical(self):
  def change(v):v['overlay_baselines']['not-in-overlay']=v['overlay_baselines'].pop(next(iter(v['overlay_baselines'])))
  with self.assertRaisesRegex(RuntimeError,'BRAND_OVERLAY_SET'):self.read(*self.mutation('source-pin.json',change))
 def test_new_path_count_is_actual_not_declared(self):
  def change(v):v['overlay_baselines'][next(k for k,x in v['overlay_baselines'].items() if x is None)]='0'*64
  with self.assertRaisesRegex(RuntimeError,'BRAND_NEW_SET'):self.read(*self.mutation('source-pin.json',change))
 def test_source_archive_pin_must_match(self):
  with self.assertRaisesRegex(RuntimeError,'BRAND_SOURCE_PIN'):
   self.read(*self.mutation('source-pin.json',lambda v:v.update(source_archive_sha256='e'*64)))
 def test_fixed_nonpublic_member_set_cannot_be_replaced(self):
  f=dict(self.files);f['runtime/scripts/not-reviewed.py']=f.pop('runtime/scripts/community_ad_contract.py')
  with self.assertRaisesRegex(RuntimeError,'BRAND_FIXED_MEMBERS'):self.read(*self.packet(f))
 def test_overlay_bytes_bound_to_candidate_not_just_outer_manifest(self):
  f=dict(self.files);f[next(k for k in f if k.startswith('overlay/public/'))]=b'tampered'
  with self.assertRaisesRegex(RuntimeError,'BRAND_OVERLAY_BYTES'):self.read(*self.packet(f))
 def test_overlay_must_exist_in_final_candidate(self):
  f=dict(self.files);old=next(k for k in f if k.startswith('overlay/public/'));value=f.pop(old);f['overlay/public/not-in-candidate']=value
  source=json.loads(f['source-pin.json']);source['overlay_baselines']['not-in-candidate']=source['overlay_baselines'].pop(old.removeprefix('overlay/public/'));f['source-pin.json']=json.dumps(source).encode()
  with self.assertRaisesRegex(RuntimeError,'BRAND_CANDIDATE_OVERLAY_SET'):self.read(*self.packet(f))
 def test_existing_baseline_must_be_sha256_and_actually_changed(self):
  first=next(k for k,x in json.loads(self.files['source-pin.json'])['overlay_baselines'].items() if x is not None)
  for value in (True,'x','F'*64,sha(self.files['overlay/public/'+first])):
   def change(v):v['overlay_baselines'][first]=value
   with self.subTest(value=value),self.assertRaisesRegex(RuntimeError,'BRAND_BASELINE_HASH'):self.read(*self.mutation('source-pin.json',change))
 def test_original_source_and_production_scope_checks_remain(self):
  with self.assertRaisesRegex(RuntimeError,'BUILD_SCOPE'):
   self.read(*self.mutation('BUILD_PROVENANCE.json',lambda v:v.update(production_approved=True)))
  raw,p=self.packet();p['source_archive_sha256']='e'*64
  with self.assertRaisesRegex(RuntimeError,'FULL_SOURCE_BINDING'):self.read(raw,p)
 def test_outer_and_manifest_hash_checks_remain(self):
  raw,p=self.packet()
  with self.assertRaisesRegex(RuntimeError,'STATIC_PACKAGE_HASH'):self.read(raw+b'extra',p)
  p['package_manifest_sha256']='f'*64
  with self.assertRaisesRegex(RuntimeError,'PACKAGE_MANIFEST_HASH'):self.read(raw,p)

class ImportIsolationTests(unittest.TestCase):
 def setUp(self):
  import tempfile
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name)

 def fresh(self):
  import importlib.util
  spec=importlib.util.spec_from_file_location('synthetic_unified_import_test',ROOT/'scripts/pr122_site_hub_unified_release.py')
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  return module

 def synthetic_helper(self,module,source=None):
  import sys
  from unittest.mock import patch
  self.enterContext(patch.object(sys,'dont_write_bytecode',sys.dont_write_bytecode))
  raw=(source or '''from pathlib import Path
import os
class Transaction:
    pass
def read(path):return Path(path).read_bytes()
def trusted(*args):pass
def mkdir(path,mode):Path(path).mkdir(mode=mode)
''').encode()
  module.HELPER=self.root/'synthetic_helper.py';module.HELPER.write_bytes(raw)
  module.HELPER_SHA=sha(raw)

 def test_direct_import_has_no_helper_read_load_or_global_bytecode_change(self):
  import importlib.util,sys
  from unittest.mock import patch
  spec=importlib.util.spec_from_file_location('synthetic_unified_import_test',ROOT/'scripts/pr122_site_hub_unified_release.py')
  module=importlib.util.module_from_spec(spec);before=sys.dont_write_bytecode
  with patch.object(Path,'read_bytes',side_effect=AssertionError('unexpected helper read')),patch.object(importlib.util,'module_from_spec',side_effect=AssertionError('unexpected helper load')):
   spec.loader.exec_module(module)
  self.assertNotIn('c',vars(module));self.assertNotIn('Transaction',vars(module))
  self.assertEqual(sys.dont_write_bytecode,before)

 def test_real_entries_import_not_ast_extraction(self):
  module=self.fresh();raw=synthetic()
  with tarfile.open(fileobj=io.BytesIO(raw)) as t:files={m.name.removeprefix('pr122-site-hub/'):t.extractfile(m).read() for m in t}
  pins=SchemaTests.pins(self,files,raw)
  from unittest.mock import patch
  with patch.object(module,'_load_helper',side_effect=AssertionError('production helper')):
   self.assertEqual(len(module.entries(raw,pins)),460)
   with self.assertRaisesRegex(RuntimeError,'STATIC_PACKAGE_HASH'):module.entries(raw+b'bad',pins)
  self.assertNotIn('c',vars(module));self.assertNotIn('Transaction',vars(module))

 def test_routes_and_smoke_remain_pure(self):
  module=self.fresh();data={'source-pin.json':json.dumps({'overlay_baselines':{f'p{i}.html':None for i in range(101)}}).encode(),'runtime-config/server-location.conf':b'# synthetic\n','overlay/public/index.html':b'fixture'}
  from unittest.mock import patch
  with patch.object(module,'_load_helper',side_effect=AssertionError('production helper')):
   self.assertEqual(len(module.routes(data)[1]),101)
   self.assertEqual(module.smoke_routes(data)['/'],('file','/index.html'))

 def test_unknown_attribute_never_loads_helper(self):
  module=self.fresh()
  from unittest.mock import patch
  with patch.object(module,'_load_helper',side_effect=AssertionError('production helper')):
   with self.assertRaises(AttributeError):getattr(module,'not_an_entry')

 def test_help_never_loads_helper(self):
  import sys
  from contextlib import redirect_stdout
  from unittest.mock import patch
  module=self.fresh();output=io.StringIO()
  with patch.object(sys,'argv',['unified','--help']),patch.object(module,'_load_helper',side_effect=AssertionError('production helper')),redirect_stdout(output),self.assertRaises(SystemExit) as caught:
   module.main()
  self.assertEqual(caught.exception.code,0);self.assertIn('controlled-apply',output.getvalue())

 def test_wrong_identity_rejected_before_helper_load(self):
  import sys
  from unittest.mock import patch
  module=self.fresh()
  with patch.object(sys,'argv',['unified','status','--inputs',str(self.root)]),patch.object(module.os,'geteuid',return_value=123),patch.object(module,'_load_helper',side_effect=AssertionError('production helper')):
   with self.assertRaisesRegex(RuntimeError,'FIXED_HOST_ROOT_REQUIRED'):module.main()

 def test_real_main_help_path_without_subprocess_or_helper(self):
  import runpy,sys
  from contextlib import redirect_stdout
  from unittest.mock import patch
  output=io.StringIO()
  with patch.object(sys,'argv',['unified','--help']),patch.object(Path,'read_bytes',side_effect=AssertionError('helper read')),redirect_stdout(output),self.assertRaises(SystemExit) as caught:
   runpy.run_path(str(ROOT/'scripts/pr122_site_hub_unified_release.py'),run_name='__main__')
  self.assertEqual(caught.exception.code,0);self.assertIn('controlled-apply',output.getvalue())

 def test_wrong_helper_hash_never_executes_or_caches(self):
  import importlib.util
  from unittest.mock import patch
  module=self.fresh();self.synthetic_helper(module);module.HELPER_SHA='0'*64
  with patch.object(importlib.util,'spec_from_file_location',side_effect=AssertionError('unverified import')):
   with self.assertRaisesRegex(RuntimeError,'HELPER_SOURCE_DRIFT'):module._load_transaction_type()
  self.assertNotIn('c',vars(module));self.assertNotIn('Transaction',vars(module))

 def test_failed_synthetic_helper_not_cached_and_explicit_retry_works(self):
  module=self.fresh();self.synthetic_helper(module,"raise RuntimeError('SYNTHETIC_FAILURE')\n")
  with self.assertRaisesRegex(RuntimeError,'SYNTHETIC_FAILURE'):module._load_transaction_type()
  self.assertNotIn('c',vars(module));self.assertNotIn('Transaction',vars(module))
  self.synthetic_helper(module);cls=module._load_transaction_type()
  self.assertIs(cls,module.Transaction);self.assertIs(module.c,module._load_helper())

 def test_helper_only_cache_does_not_skip_class_initialization(self):
  module=self.fresh();self.synthetic_helper(module)
  helper=module.c;self.assertNotIn('Transaction',vars(module))
  cls=module.Transaction;self.assertIs(cls.__bases__[0],helper.Transaction)
  self.assertIs(cls,module._load_transaction_type());self.assertEqual(cls.__qualname__,'Transaction')

 def test_concurrent_synthetic_load_has_one_helper_and_type_identity(self):
  import threading,importlib.util
  from unittest.mock import patch
  module=self.fresh();self.synthetic_helper(module);values=[];errors=[]
  original=importlib.util.module_from_spec
  def worker():
   try:values.append((module.Transaction,module.c))
   except BaseException as error:errors.append(type(error).__name__)
  with patch.object(importlib.util,'module_from_spec',wraps=original) as builds:
   threads=[threading.Thread(target=worker) for _ in range(8)]
   for thread in threads:thread.start()
   for thread in threads:thread.join(timeout=5)
   self.assertFalse(any(thread.is_alive() for thread in threads));self.assertEqual(builds.call_count,1)
  self.assertEqual(errors,[]);self.assertEqual(len(values),8)
  self.assertTrue(all(cls is values[0][0] and helper is values[0][1] for cls,helper in values))

 def canonical_ast_dump(self,node):
  # Python 3.12 added empty type_params fields to class/function AST nodes.
  # Canonicalize 3.11 to that fixed 3.12 representation only; a non-empty
  # type_params value is semantic and is never discarded.
  import copy
  node=copy.deepcopy(node)
  for item in ast.walk(node):
   if isinstance(item,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
    if 'type_params' not in item._fields:
     item._fields=tuple(item._fields)+('type_params',)
     item.type_params=[]
    elif item.type_params:
     raise AssertionError('NONEMPTY_TYPE_PARAMS_NOT_NORMALIZED')
  return ast.dump(node,include_attributes=False)

 def fixed_ast_nodes(self):
  tree=ast.parse((ROOT/'scripts/pr122_site_hub_unified_release.py').read_text())
  return {name:next(n for n in ast.walk(tree) if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name==name)
          for name in ('Transaction','entries')}

 def test_original_class_and_entries_ast_exactly_preserved(self):
  # Fixed expected digests were captured from the reviewed IMPORT_ISOLATION
  # candidate under Python 3.12. Canonicalization makes Python 3.11 emit that
  # same shape by adding only absent empty type_params fields.
  expected={'Transaction':'20511fb4466bd12942b2b8fc0187c34e6b2cdc04827fa4b3f67dd25b252e8117','entries':'b63f583e12d4525a11f63c738f1f6b41563f315533818266515415fdfec62d6b'}
  for name,node in self.fixed_ast_nodes().items():
   self.assertEqual(sha(self.canonical_ast_dump(node).encode()),expected[name])

 def test_ast_normalization_rejects_semantic_security_check_deletion(self):
  import copy
  expected={'Transaction':'20511fb4466bd12942b2b8fc0187c34e6b2cdc04827fa4b3f67dd25b252e8117','entries':'b63f583e12d4525a11f63c738f1f6b41563f315533818266515415fdfec62d6b'}
  for name,original in self.fixed_ast_nodes().items():
   node=copy.deepcopy(original);removed=False
   for owner in ast.walk(node):
    for field in getattr(owner,'_fields',()):
     value=getattr(owner,field,None)
     if not isinstance(value,list):continue
     for index,item in enumerate(value):
      if isinstance(item,ast.Expr) and isinstance(item.value,ast.Call) and isinstance(item.value.func,ast.Name) and item.value.func.id=='need':
       del value[index];removed=True;break
     if removed:break
    if removed:break
   self.assertTrue(removed,name+':NO_SECURITY_CHECK_FIXTURE')
   self.assertNotEqual(sha(self.canonical_ast_dump(node).encode()),expected[name])

 def test_methods_keep_module_globals_and_no_helper_closures(self):
  import types
  module=self.fresh();self.synthetic_helper(module)
  for value in vars(module.Transaction).values():
   if isinstance(value,types.FunctionType):
    self.assertIs(value.__globals__,vars(module))
    self.assertFalse({'c','os','Path','Transaction'}&set(value.__code__.co_freevars))
    self.assertTrue(set(value.__code__.co_freevars)<={'__class__'})



 def test_existing_adapter_clone_still_checks_lease_before_mutation(self):
  from scripts import pr122_static_operations as adapter
  from scripts.pr122_customer_core import Denied
  from types import SimpleNamespace
  module=self.fresh();self.synthetic_helper(module);cls=module.Transaction
  transaction=object.__new__(cls);transaction.folder=self.root/'never-created';transaction.ops=SimpleNamespace()
  target=object.__new__(adapter.OriginalStaticOperations);target.t=transaction;target.u=module;target.c=module.c
  calls=[]
  def guard():
   calls.append('lease')
   if len(calls)>1:raise Denied('SYNTHETIC_EXPIRED_LEASE')
  with self.assertRaisesRegex(Denied,'SYNTHETIC_EXPIRED_LEASE'):
   target._original_action('backup',SimpleNamespace(assert_active=guard),{})
  self.assertEqual(len(calls),2);self.assertFalse(transaction.folder.exists())

 def test_actual_source_gate_uses_authenticated_synthetic_helper(self):
  module=self.fresh();self.synthetic_helper(module)
  root=self.root/'source';(root/'scripts').mkdir(parents=True)
  p=root/'scripts/pr122_site_hub_unified_release.py';p.write_bytes(b'# synthetic source')
  manifest={'schema':1,'source_commit':'a'*40,'files':[{'path':'scripts/'+p.name,'size':p.stat().st_size,'sha256':sha(p.read_bytes())}]}
  raw=json.dumps(manifest).encode();(root/'STATIC_SOURCE_MANIFEST.json').write_bytes(raw)
  pins={'static_source_manifest_sha256':sha(raw)}
  self.assertEqual(module.verify_static_source_before_import(root,pins),manifest)
  p.write_bytes(b'changed')
  with self.assertRaisesRegex(RuntimeError,'STATIC_SOURCE_BYTES'):module.verify_static_source_before_import(root,pins)

 def test_actual_gate_retains_scope_and_expiry_checks(self):
  from unittest.mock import patch
  module=self.fresh();self.synthetic_helper(module)
  module.HERE=self.root/'wrapper';module.HERE.write_bytes(b'wrapper')
  module.PINS=self.root/'pins';module.PINS.write_bytes(b'pins')
  pins={key:'synthetic' for key in ('transaction_id','source_head','static_artifact_sha256','package_manifest_sha256','previous_receipt_sha256')}
  value={**pins,'decision':'RELEASE_APPROVED','operation':'PR122_PUBLIC_MOBILE_UNIFIED','wrapper_sha256':sha(b'wrapper'),'host_pins_sha256':sha(b'pins'),'rollback_approved':True,'max_executions':1,'independent_review':'PASS','reviewer_role':'INDEPENDENT_AUDITOR','review_comment_id':6209244058,'release_comment_id':6209244059,'issued_unix':100,'expires_unix':200}
  with patch.object(module.time,'time',return_value=150):
   module.gate(value,pins)
   with self.assertRaisesRegex(RuntimeError,'RELEASE_GATE:operation'):module.gate({**value,'operation':'other'},pins)
   with self.assertRaisesRegex(RuntimeError,'INDEPENDENT_REVIEW_REQUIRED'):module.gate({**value,'independent_review':'PENDING'},pins)
  with patch.object(module.time,'time',return_value=201):
   with self.assertRaisesRegex(RuntimeError,'GATE_EXPIRED'):module.gate(value,pins)

if __name__=='__main__':unittest.main()
