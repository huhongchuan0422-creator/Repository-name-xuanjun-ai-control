import os,pathlib,tempfile,unittest
from unittest.mock import patch,Mock
import observe_epoch5 as obs
class ObservationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=self.tmp.name
 def test_read_regular(self):
  p=self.root+'/file';pathlib.Path(p).write_bytes(b'abc');self.assertEqual(obs.read(p)[0],b'abc')
 def test_read_bound(self):
  p=self.root+'/file';pathlib.Path(p).write_bytes(b'abc')
  with self.assertRaisesRegex(ValueError,'BOUND'):obs.read(p,2)
 def test_read_alias_refused(self):
  p=self.root+'/file';pathlib.Path(p).write_bytes(b'abc');os.symlink(p,self.root+'/link')
  with self.assertRaisesRegex(ValueError,'ALIAS'):obs.read(self.root+'/link')
 def test_directory_not_read_as_file(self):
  with self.assertRaisesRegex(ValueError,'REGULAR'):obs.read(self.root)
 def test_metadata_missing(self):self.assertEqual(obs.meta(self.root+'/missing'),{'state':'ABSENT'})
 def test_tree_permission_failure_propagates(self):
  with patch.object(obs.os,'scandir',side_effect=PermissionError('denied')):
   with self.assertRaises(PermissionError):obs.tree(self.root)
 def test_tree_external_link_refused(self):
  os.symlink('/etc/passwd',self.root+'/link')
  with self.assertRaisesRegex(ValueError,'ESCAPE'):obs.tree(self.root)
 def test_parse_never_invokes_certbot_main_or_issuance(self):
  fake=Mock(returncode=0,stdout=b'RENEWAL_MODE_PARSE_ONLY_PASS\n',stderr=b'')
  with patch.object(obs.subprocess,'run',return_value=fake) as run:
   self.assertTrue(obs.parse_only()['pass'])
  self.assertEqual(run.call_count,2)
  self.assertEqual([c[0][0][-1] for c in run.call_args_list],['renew','dry-run'])
  command=run.call_args[0][0];self.assertEqual(command[:3],['/usr/bin/python3','-B','-c'])
  self.assertIn('prepare_and_parse_args',command[3]);self.assertNotIn('certonly',command[3]);self.assertNotIn('main(',command[3])
 def test_parse_failure_not_pass(self):
  fake=Mock(returncode=2,stdout=b'',stderr=b'bad flag')
  with patch.object(obs.subprocess,'run',return_value=fake):self.assertFalse(obs.parse_only()['pass'])
if __name__=='__main__':unittest.main(verbosity=2)
