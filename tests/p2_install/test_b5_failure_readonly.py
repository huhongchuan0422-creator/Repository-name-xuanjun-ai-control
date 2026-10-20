import hashlib,importlib.util,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('ro',str(ROOT/'scripts/p2_b5_failure_readonly.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Readonly(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name);self.fd=os.open(self.tmp.name,os.O_RDONLY|os.O_DIRECTORY)
 def tearDown(self):os.close(self.fd);self.tmp.cleanup()
 def test_absent(self):self.assertEqual(m.inspect_file(self.fd,'missing',True),{'status':'ABSENT'})
 def test_stable_sha_redaction(self):
  raw=b'{"state":"HOLD_RETAIN_OUTPUT","secret":"DO_NOT_PRINT","error":"TOKEN=abc","errno":17}'
  p=self.path/'receipt';p.write_bytes(raw);before=p.stat()
  r=m.inspect_file(self.fd,'receipt',True);self.assertEqual(r['sha256'],hashlib.sha256(raw).hexdigest());self.assertNotIn('DO_NOT_PRINT',json.dumps(r));self.assertNotIn('TOKEN',json.dumps(r));self.assertEqual(m.identity(before),m.identity(p.stat()))
 def test_size_bound(self):
  (self.path/'big').write_bytes(b'x'*65537)
  with self.assertRaisesRegex(m.Hold,'SIZE_BOUND'):m.inspect_file(self.fd,'big',True)
 def test_symlink_and_hardlink(self):
  (self.path/'real').write_text('{}');os.symlink('real',str(self.path/'link'))
  with self.assertRaises(m.Hold):m.inspect_file(self.fd,'link',True)
  os.link(str(self.path/'real'),str(self.path/'hard'))
  with self.assertRaises(m.Hold):m.inspect_file(self.fd,'hard',True)
 def test_metadata_special_never_open(self):
  os.mkfifo(str(self.path/'materials.tar'))
  with patch.object(m.os,'open',side_effect=AssertionError('NO_OPEN')):
   self.assertEqual(m.inspect_file(self.fd,'materials.tar',False)['metadata']['type'],'SPECIAL_OR_LINK')
 def test_replace_during_read(self):
  p=self.path/'receipt';p.write_text('{}');original=os.read
  def read(fd,n):
   raw=original(fd,n)
   if raw:
    q=self.path/'new';q.write_text('{}');os.replace(str(q),str(p))
   return raw
  with patch.object(m.os,'read',side_effect=read):
   with self.assertRaisesRegex(m.Hold,'CHANGED_DURING'):m.inspect_file(self.fd,'receipt',True)
 def test_duplicate_json_non_success(self):
  (self.path/'receipt').write_text('{"state":"HOLD","state":"RETURNED"}')
  self.assertEqual(m.inspect_file(self.fd,'receipt',True)['status'],'READ_STABLE_JSON_INVALID')
 def test_metadata_no_content(self):
  (self.path/'report.json').write_text('secret')
  with patch.object(m.os,'read',side_effect=AssertionError('NO_READ')):
   self.assertEqual(m.inspect_file(self.fd,'report.json',False)['status'],'METADATA_ONLY')
 def test_timeout_stops_next_root_main(self):
  class U: nodename='iZd7oeikknn1z21sq6ji6zZ'
  with patch.object(m.os,'getuid',return_value=0),patch.object(m.os,'geteuid',return_value=0),patch.object(m.os,'uname',return_value=U()),patch.object(m.sys,'version_info',(3,6,8)),patch.object(m.pwd,'getpwnam'),patch.object(m.signal,'signal'),patch.object(m.signal,'alarm'),patch.object(m,'inspect_root',side_effect=m.Deadline('QUERY_TIME_BOUND')) as query:
   with self.assertRaises(m.Deadline):m.main()
   self.assertEqual(query.call_count,1)
if __name__=='__main__':unittest.main()
