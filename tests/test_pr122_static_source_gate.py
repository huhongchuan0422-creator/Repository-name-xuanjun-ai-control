"""Pure loader admission tests; no original helper imports or host operations."""
import ast, hashlib, json, re, tempfile, unittest, os, sys, importlib
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
class SourceGateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);(self.root/'scripts').mkdir()
  tree=ast.parse((ROOT/'scripts/pr122_site_hub_unified_release.py').read_text());tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('digest','need','verify_static_source_before_import','bind_static_source_package','baseline_receipt_state')]
  helper=SimpleNamespace(read=lambda p:p.read_bytes(),trusted=lambda *a:None)
  ns=dict(hashlib=hashlib,json=json,re=re,os=os,sys=sys,c=helper,_load_helper=lambda:helper);exec(compile(tree,'pure-static-source-gate','exec'),ns);self.gate=ns['verify_static_source_before_import'];self.bind_package=ns['bind_static_source_package'];self.baseline_state=ns['baseline_receipt_state']
  self.file=self.root/'scripts/pr122_site_hub_unified_release.py';self.file.write_bytes(b'fixture source only')
  self.manifest={'schema':1,'source_commit':'a'*40,'files':[dict(path='scripts/'+self.file.name,size=self.file.stat().st_size,sha256=hashlib.sha256(self.file.read_bytes()).hexdigest())]};self.bind()
 def bind(self):
  raw=json.dumps(self.manifest).encode();(self.root/'STATIC_SOURCE_MANIFEST.json').write_bytes(raw);self.pins={'static_source_manifest_sha256':hashlib.sha256(raw).hexdigest()}
 def test_exact_manifest(self):self.assertEqual(self.gate(self.root,self.pins),self.manifest)
 def test_changed_source(self):
  self.file.write_bytes(b'changed')
  with self.assertRaisesRegex(RuntimeError,'SOURCE_BYTES'):self.gate(self.root,self.pins)
 def test_unbound_manifest(self):
  self.pins['static_source_manifest_sha256']='0'*64
  with self.assertRaisesRegex(RuntimeError,'MANIFEST_PIN'):self.gate(self.root,self.pins)
 def test_unlisted_python_rejected(self):
  (self.root/'scripts/injected.py').write_text('')
  with self.assertRaisesRegex(RuntimeError,'COMPLETE_INVENTORY'):self.gate(self.root,self.pins)
 def test_bytecode_cache_rejected(self):
  (self.root/'scripts/__pycache__').mkdir()
  with self.assertRaisesRegex(RuntimeError,'UNREVIEWED_ENTRY'):self.gate(self.root,self.pins)
 def test_duplicate_row(self):
  self.manifest['files']*=2;self.bind()
  with self.assertRaisesRegex(RuntimeError,'SOURCE_PATH'):self.gate(self.root,self.pins)
 def test_noncanonical_source(self):
  self.manifest['files'][0]['path']='scripts/../escape.py';self.bind()
  with self.assertRaisesRegex(RuntimeError,'SOURCE_PATH'):self.gate(self.root,self.pins)
 def test_root_module_shadow_rejected(self):
  (self.root/'scripts.py').write_text('raise AssertionError("must not execute")')
  with self.assertRaisesRegex(RuntimeError,'ROOT_SHADOW'):self.gate(self.root,self.pins)
 def test_external_regular_package_cannot_execute(self):
  external=self.root/'external';(external/'scripts').mkdir(parents=True)
  (external/'scripts/__init__.py').write_text('raise AssertionError("external package executed")')
  (self.root/'scripts/safe_fixture.py').write_text('VALUE=42')
  with patch.dict(sys.modules):
   for key in list(sys.modules):
    if key=='scripts' or key.startswith('scripts.'):del sys.modules[key]
   with patch.object(sys,'path',[str(external)]+sys.path):
    self.bind_package(self.root)
    self.assertEqual(importlib.import_module('scripts.safe_fixture').VALUE,42)
    self.assertEqual(sys.modules['scripts'].__path__,[str(self.root/'scripts')])
 def test_preexisting_package_rejected(self):
  with patch.dict(sys.modules,{'scripts':object()}):
   with self.assertRaisesRegex(RuntimeError,'PREEXISTING_PACKAGE'):self.bind_package(self.root)
 def test_new_baseline_state_requires_exact_new_pin(self):
  pins={'package_schema':'FULL_STATIC_REVIEW_V1'};state='STATIC_READONLY_HTTP_COMPLETE_AWAIT_BROWSER'
  self.assertFalse(self.baseline_state(pins,state));pins['previous_receipt_state']=state
  self.assertTrue(self.baseline_state(pins,state));self.assertFalse(self.baseline_state(pins,'HTTPS_SMOKE_PASS_AWAIT_BROWSER'))
 def test_brand_baseline_uses_exact_full_receipt_state_pin(self):
  pins={'package_schema':'FULL_STATIC_BRAND_REVIEW_V1'};state='STATIC_READONLY_HTTP_COMPLETE_AWAIT_BROWSER'
  self.assertFalse(self.baseline_state(pins,state));pins['previous_receipt_state']=state
  self.assertTrue(self.baseline_state(pins,state));self.assertFalse(self.baseline_state(pins,'HTTPS_SMOKE_PASS_AWAIT_BROWSER'))
  pins['previous_receipt_state']='UNKNOWN';self.assertFalse(self.baseline_state(pins,'UNKNOWN'))
 def test_brand_transaction_uses_pinned_previous_id_manifest_and_count(self):
  from unittest.mock import Mock
  tree=ast.parse((ROOT/'scripts/pr122_site_hub_unified_release.py').read_text())
  cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Transaction')
  method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='baseline')
  previous_id='pr122-brand-previous-fixture';previous=Path('/synthetic-control/transactions')/previous_id/'receipt.json'
  receipt=b'{"state":"STATIC_READONLY_HTTP_COMPLETE_AWAIT_BROWSER"}'
  manifest=json.dumps({'files':[{'path':'a','size':1,'sha256':'a'*64},{'path':'b','size':2,'sha256':'b'*64}]}).encode()
 def test_brand_baseline_uses_exact_full_receipt_state_pin(self):
  pins={'package_schema':'FULL_STATIC_BRAND_REVIEW_V1'};state='STATIC_READONLY_HTTP_COMPLETE_AWAIT_BROWSER'
  self.assertFalse(self.baseline_state(pins,state));pins['previous_receipt_state']=state
  self.assertTrue(self.baseline_state(pins,state));self.assertFalse(self.baseline_state(pins,'HTTPS_SMOKE_PASS_AWAIT_BROWSER'))
  pins['previous_receipt_state']='UNKNOWN';self.assertFalse(self.baseline_state(pins,'UNKNOWN'))
 def test_brand_transaction_uses_pinned_previous_id_manifest_and_count(self):
  from unittest.mock import Mock
  tree=ast.parse((ROOT/'scripts/pr122_site_hub_unified_release.py').read_text())
  cls=next(n for n in ast.walk(tree) if isinstance(n,ast.ClassDef) and n.name=='Transaction')
  method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='baseline')
  previous_id='pr122-brand-previous-fixture';previous=Path('/synthetic-control/transactions')/previous_id/'receipt.json'
  receipt=b'{"state":"STATIC_READONLY_HTTP_COMPLETE_AWAIT_BROWSER"}'
  manifest=json.dumps({'files':[{'path':'a','size':1,'sha256':'a'*64},{'path':'b','size':2,'sha256':'b'*64}]}).encode()
  source={previous:receipt,Path('/synthetic-installed-publisher'):b'publisher',Path('/synthetic-inputs/R2_CANDIDATE_MANIFEST.json'):manifest}
  read=Mock(side_effect=lambda p:source[p]);digest=lambda raw:hashlib.sha256(raw).hexdigest()
  c=SimpleNamespace(CONTROL=Path('/synthetic-control'),BASE=Path('/synthetic-base'),INSTALLED_PUBLISHER=Path('/synthetic-installed-publisher'),read=read)
  def need(ok,reason):
   if not ok:raise RuntimeError(reason)
  ns=dict(c=c,os=SimpleNamespace(readlink=lambda p:'/synthetic-previous'),json=json,re=re,digest=digest,need=need,baseline_receipt_state=self.baseline_state)
  exec(compile(ast.Module(body=[method],type_ignores=[]),'baseline-only','exec'),ns)
  pins=dict(package_schema='FULL_STATIC_BRAND_REVIEW_V1',previous_transaction_id=previous_id,previous_receipt_state='STATIC_READONLY_HTTP_COMPLETE_AWAIT_BROWSER',previous_receipt_sha256=digest(receipt),previous_release='/synthetic-previous',installed_publisher_sha256=digest(b'publisher'),previous_manifest_sha256=digest(manifest),previous_file_count=2,nginx={})
  files={r['path']:{'size':r['size'],'sha256':r['sha256']} for r in json.loads(manifest)['files']}
  target=SimpleNamespace(pins=pins,inputs=Path('/synthetic-inputs'),inventory=Mock(),ops=SimpleNamespace(nginx_identity=Mock(return_value='fixture'),nginx_test=Mock()),runtime=Mock(return_value='fixture'),snapshot=Mock(return_value=files))
  self.assertEqual(ns['baseline'](target),files);self.assertEqual(read.call_args_list[0].args,(previous,))
  pins['previous_file_count']=3
  with self.assertRaisesRegex(RuntimeError,'R2_PUBLIC_DRIFT'):ns['baseline'](target)
  pins['previous_transaction_id']='not-valid'
  with self.assertRaisesRegex(RuntimeError,'BASELINE_TRANSACTION_ID'):ns['baseline'](target)
 def test_legacy_baseline_state_not_extended(self):
  self.assertFalse(self.baseline_state({'previous_receipt_state':'STATIC_READONLY_HTTP_COMPLETE_AWAIT_BROWSER'},'STATIC_READONLY_HTTP_COMPLETE_AWAIT_BROWSER'))
  self.assertTrue(self.baseline_state({},'HTTPS_SMOKE_PASS_AWAIT_BROWSER'))
 def test_gate_precedes_new_import(self):
  tree=ast.parse((ROOT/'scripts/pr122_site_hub_unified_release.py').read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
  gate=next(n for n in ast.walk(main) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='verify_static_source_before_import')
  imp=next(n for n in ast.walk(main) if isinstance(n,ast.ImportFrom) and n.module=='scripts')
  self.assertLess(gate.lineno,imp.lineno)
if __name__=='__main__':unittest.main()
