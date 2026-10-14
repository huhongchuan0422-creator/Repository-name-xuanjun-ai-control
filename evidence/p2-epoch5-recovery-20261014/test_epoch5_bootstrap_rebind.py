import copy,unittest
import inspect_epoch5 as s
class BootstrapRebindTests(unittest.TestCase):
 def setUp(self):
  self.row={'target':s.NATIVE,'sha256':s.NATIVE_BEFORE_SHA,'state':'PUBLISHED','owner_uid':0,'group_gid':0,'mode':0o644}
  self.value=dict(s.NATIVE_AFTER);self.temp={'state':'ABSENT'}
 def execute(self):return s.recognized_native_rebind(self.row,self.value,self.temp)
 def test_only_exact_recorded_rebind_accepted(self):self.assertTrue(self.execute())
 def test_current_file_each_identity_field_is_pinned(self):
  for k,v in self.value.items():
   old=self.value[k];self.value[k]='changed'
   self.assertFalse(self.execute(),k);self.value[k]=old
 def test_original_journal_each_field_is_pinned(self):
  for k in self.row:
   old=self.row[k];self.row[k]='changed'
   self.assertFalse(self.execute(),k);self.row[k]=old
 def test_retained_temporary_refused(self):
  self.temp={'state':'FILE'};self.assertFalse(self.execute())
 def test_unrelated_bootstrap_never_gets_exception(self):
  self.row['target']='/etc/xuanjun-development/github-intake-token';self.assertFalse(self.execute())
if __name__=='__main__':unittest.main(verbosity=2)
