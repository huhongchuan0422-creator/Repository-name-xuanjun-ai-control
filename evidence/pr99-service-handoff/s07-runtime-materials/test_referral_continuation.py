import os
from pathlib import Path
import runpy,stat,tempfile,types,unittest
from unittest.mock import patch
N=runpy.run_path(str(Path(__file__).with_name('stage_runtime_materials.py')))
G=N['read_file'].__globals__
class BindingTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.target=self.root/'target';self.target.mkdir()
  self.alias=self.root/'alias';self.alias.symlink_to(self.target,target_is_directory=True)
  self.suffix=Path('xuanjun-agent-coordination/CUSTOMER_REFERRAL_CONFIG.json')
  (self.target/self.suffix).parent.mkdir();(self.target/self.suffix).write_bytes(b'fixture-private')
 def tearDown(self):self.temp.cleanup()
 def context(self,wrong=False):
  original=Path.lstat
  def lstat(p):
   s=original(p)
   if p not in (self.alias,self.target):return s
   d={k:getattr(s,k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_mtime_ns','st_ctime_ns')}
   d.update(st_dev=64771 if p==self.alias else 37,st_ino=654102 if p==self.alias else 259,st_uid=1000,st_gid=1000,
            st_mode=(stat.S_IFLNK|0o777) if p==self.alias else stat.S_IFDIR|(0o700 if wrong else 0o755))
   return types.SimpleNamespace(**d)
  import contextlib
  @contextlib.contextmanager
  def ctx():
   with patch.dict(G,REFERRAL_ALIAS=self.alias,REFERRAL_TARGET=self.target),patch.object(Path,'lstat',lstat):yield
  return ctx()
 def test_exact_json_alias_only(self):
  with self.context():self.assertEqual(N['read_file'](self.alias/self.suffix),b'fixture-private')
 def test_different_file_under_alias_rejected(self):
  with self.context():
   with self.assertRaisesRegex(RuntimeError,'SYMLINK_PARENT'):N['read_file'](self.alias/'other.json')
 def test_target_metadata_drift_rejected(self):
  with self.context(wrong=True):
   with self.assertRaisesRegex(RuntimeError,'TARGET_IDENTITY_CHANGED'):N['read_file'](self.alias/self.suffix)
 def test_link_text_change_rejected(self):
  with self.context(),patch.object(os,'readlink',return_value='/unapproved'):
   with self.assertRaisesRegex(RuntimeError,'LINK_TEXT_CHANGED'):N['read_file'](self.alias/self.suffix)
 def test_link_change_during_read_rejected(self):
  with patch.dict(G,REFERRAL_ALIAS=self.alias,REFERRAL_TARGET=self.target,referral_binding=__import__('unittest.mock',fromlist=['Mock']).Mock(side_effect=[('before',),('after',)])):
   with self.assertRaisesRegex(RuntimeError,'BINDING_CHANGED_DURING_READ'):N['read_file'](self.alias/self.suffix)
 def test_prior_failure_required(self):
  def data(p,limit):
   return {'failure.json':b'{"status":"HOLD_PRESERVE_NO_RETRY"}','materials.tar':b'',
           'ssh-private.log':b'RuntimeError: SYMLINK_PARENT'}[p.name]
  with patch.dict(G,read_plain_file=data),patch.object(os.path,'lexists',return_value=False):N['require_prior_failure']()
 def test_nonempty_prior_transfer_rejected(self):
  def data(p,limit):
   return b'{"status":"HOLD_PRESERVE_NO_RETRY"}' if p.name=='failure.json' else b'x'
  with patch.dict(G,read_plain_file=data),patch.object(os.path,'lexists',return_value=False):
   with self.assertRaisesRegex(RuntimeError,'ARCHIVE_NONEMPTY'):N['require_prior_failure']()
if __name__=='__main__':unittest.main()
