import hashlib,importlib.util,io,json,os,tarfile,unittest
spec=importlib.util.spec_from_file_location('carrier_scanner',os.path.join(os.path.dirname(__file__),'..','carrier-security','safe_archive.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class CarrierScopeTests(unittest.TestCase):
 def archive(self,data,name='TOOL_SCOPE.json'):
  out=io.BytesIO()
  with tarfile.open(fileobj=out,mode='w') as t:
   x=tarfile.TarInfo(name);x.size=len(data);t.addfile(x,io.BytesIO(data))
  return out.getvalue(),{name:{'type':'file','size':len(data),'sha256':hashlib.sha256(data).hexdigest()}}
 def test_required_and_valid_scope(self):
  with open('TOOL_SCOPE.json','rb') as f:data=f.read()
  blob,expected=self.archive(data);self.assertEqual(m.scan(blob,expected),{'TOOL_SCOPE.json'})
  blob,expected=self.archive(data,'other')
  with self.assertRaisesRegex(ValueError,'CARRIER_TOOL_SCOPE_REQUIRED'):m.scan(blob,expected)
 def test_scope_rejects_write_default(self):
  with open('TOOL_SCOPE.json') as f:scope=json.load(f)
  scope['allowed_write_tools']=['task_submit'];blob,expected=self.archive(json.dumps(scope).encode())
  with self.assertRaisesRegex(ValueError,'CARRIER_TOOL_SCOPE_INVALID'):m.scan(blob,expected)
