import hashlib,json,pathlib,re,unittest
BASE=pathlib.Path(__file__).resolve().parents[1]
class RuntimeProcessBindings(unittest.TestCase):
 def test_all_dispatcher_commands_pin_actual_controller(self):
  digest=hashlib.sha256((BASE/'runtime-source-checkpoint/stage1/native_gateway_controller.py').read_bytes()).hexdigest()
  unit=(BASE/'runtime-process-checkpoint/xuanjun-development-dispatcher.service').read_text()
  commands=[l for l in unit.splitlines() if l.startswith(('ExecStart=','ExecStartPre='))]
  self.assertEqual(len(commands),3)
  for line in commands:self.assertEqual(re.findall(r'--native-controller-sha256 ([0-9a-f]{64})',line),[digest])
 def test_manifest_binds_all_three_changed_sources(self):
  record=json.loads((BASE/'runtime-process-checkpoint/prepared.json').read_text())
  raw=(BASE/'runtime-process-checkpoint/integration-manifest.json').read_bytes()
  self.assertEqual(hashlib.sha256(raw).hexdigest(),record['manifest_sha256'])
  files=json.loads(raw.decode())['files']
  for relative,(path,wanted) in record['runtime_changes'].items():
   self.assertEqual(hashlib.sha256((BASE/path).read_bytes()).hexdigest(),wanted)
   self.assertEqual(files[relative],wanted)
 def test_gateway_uses_the_packaged_shared_helper(self):
  source=(BASE/'runtime-source-checkpoint/stage1/native_gateway_controller.py').read_text()
  self.assertIn('from ledger_server_identity import _bounded_owned_command',source)
  self.assertNotIn('.communicate(',source)
 def test_existing_runtime_inventory_is_preserved(self):
  previous=json.loads((BASE/'runtime-build-d03e7226/xuanjun-p2-package/deploy/integration-manifest.json').read_text())
  current=json.loads((BASE/'runtime-process-checkpoint/integration-manifest.json').read_text())
  self.assertEqual(set(previous['files']),set(current['files']))
  changed={p for p in previous['files'] if previous['files'][p]!=current['files'][p]}
  self.assertEqual(changed,{'stage1/ledger_server_identity.py','stage1/native_gateway_controller.py','deploy/xuanjun-development-dispatcher.service'})
  self.assertEqual({k:v for k,v in previous.items() if k!='files'},{k:v for k,v in current.items() if k!='files'})
if __name__=='__main__':unittest.main()
