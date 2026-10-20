import ast,importlib.util,os,subprocess,sys,unittest
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
p=REPO/'scripts/p2_b5_sdk_inventory.py'
spec=importlib.util.spec_from_file_location('inventory',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Inventory(unittest.TestCase):
    def test_actual_alias_source_parsing_no_guessed_default(self):
        self.assertEqual(m.loader_exports(b'export { loadOpenClawPlugins as l, other as x };'),{'loadOpenClawPlugins':'l'})
        self.assertEqual(m.loader_exports(b'export { unrelated as l };'),{})
        self.assertEqual(m.loader_exports(b'export { loadPluginRegistryHandle };'),{'loadPluginRegistryHandle':'loadPluginRegistryHandle'})
    def test_no_execution_on_wrong_host_or_uid(self):
        if os.uname().nodename.split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ':self.skipTest('never execute inventory on UK in this test')
        r=subprocess.run([sys.executable,'-I','-B','-S',str(p)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.assertEqual(r.returncode,2);self.assertIn(b'FIXED_UK_UID1002_REQUIRED',r.stdout)
    def test_368_syntax_and_no_subprocess_or_gateway_execution(self):
        ast.parse(p.read_text(),feature_version=(3,6))
        self.assertNotIn('import subprocess',p.read_text())
        self.assertNotIn('execFile',p.read_text())
if __name__=='__main__':unittest.main()
