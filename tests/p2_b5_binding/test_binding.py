"""Synthetic source strings only. No real SDK/module import or acceptance."""
import importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[2]/'scripts/p2_b5_three_file_binding.py'
s=importlib.util.spec_from_file_location('binding',str(P));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_exact_declared_mapping_only(self):
  self.assertEqual(m.static_mapping('export { acquirePluginRegistryForInspection as t, other as x };')['compiled'],'t')
  for source in ('export { acquirePluginRegistryForInspection as a };','export { unrelated as t };','export { acquirePluginRegistryForInspection };','export { acquirePluginRegistryForInspection as t, acquirePluginRegistryForInspection as a };'):
   with self.assertRaises(ValueError):m.static_mapping(source)
 def test_lexical_inventory_does_not_claim_closure(self):
  files={'package.json':b'{"version":"2026.9.9"}',m.LOADER:b'import x from "./child.mjs"; export {acquirePluginRegistryForInspection as t};','dist/context-DyPstb2Q.mjs':b'export {a} from "./context-Dt2Gy7El.mjs";'}
  r=m.analyze(files);self.assertEqual(r['dependency_closure'],'UNKNOWN');self.assertEqual(r['real_loader'],'NOT_EXECUTED');self.assertIn('./child.mjs',r['direct_lexical_references'][m.LOADER])
 def test_wrong_version_holds(self):
  with self.assertRaisesRegex(ValueError,'HOLD_PACKAGE_VERSION'):m.analyze({'package.json':b'{"version":"latest"}'})
 def test_cli_rejects_wrong_archive_and_never_claims_loaded(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'input.tar';p.write_bytes(b'not an SDK')
   r=subprocess.run([sys.executable,'-I','-B','-S',str(P),str(p)],capture_output=True,timeout=5)
   self.assertEqual(r.returncode,2);v=json.loads(r.stdout);self.assertEqual(v['state'],'HOLD');self.assertEqual(v['cp11'],'NOT_EXECUTED')
if __name__=='__main__':unittest.main()
