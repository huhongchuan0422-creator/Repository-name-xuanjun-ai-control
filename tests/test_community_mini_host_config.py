"""Formal composition uses existing file-backed stores; synthetic identities only."""
import copy,os,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_community_mini_center_identity as fixture
from scripts.community_stage_local import LocalStage
from scripts.community_mini_application import MiniApplication
from scripts.community_mini_host_config import stores

class ExistingPersistentHost(unittest.TestCase):
 def setUp(self):
  self.fx=fixture.ExistingCenterComposition();self.fx.setUp();self.addCleanup(self.fx.tearDown)
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.stage=LocalStage(self.tmp.name,self.fx.stage.api.bindings,
       self.fx.stage.api.bindings[self.fx.stage.customer],clock=self.fx.center.now)
  self.addCleanup(self.stage.close);self.runtime=self.stage.runtime
  self.config=dict(version=1,appid=self.fx.identity.appid,
      https_origin='https://community-preview.wenwenwenyiyiyi.work',
      scenes={'shop1':dict(project='project1',principal='customer')},
      stores={name:db.execute('PRAGMA database_list').fetchone()[2]
              for name,db in stores(self.fx.center,self.runtime).items()})
  self.principals={'customer':self.fx.stage.customer}
 def compose(self,config=None):
  return MiniApplication.from_existing_runtime(self.fx.center,self.runtime,self.principals,
      self.config if config is None else config,'a'*32)
 def test_no_new_stores_localstage_or_identity_store_and_host_keeps_ownership(self):
  before=set(Path(self.tmp.name).iterdir())
  with patch('scripts.community_mini_application.LocalStage',side_effect=AssertionError('NO_NEW_STAGE')):
   with self.compose() as app:
    self.assertIs(app.identity.center,self.fx.center);self.assertIs(app.identity.runtime,self.runtime)
    self.assertIsNone(app.stage)
    app.configure_operations({'merchant':dict(user_id=self.fx.uid1,project='project1',
        project_roles=['OWNER'],principal=self.fx.stage.merchant)})
    app.configure_commerce()
    with self.assertRaisesRegex(PermissionError,'PROTECTED_HTTPS_ORIGIN_MISMATCH'):
     app.listen_proxy('/unreached.sock','https://wrong.invalid',1,1)
  self.assertEqual(before,set(Path(self.tmp.name).iterdir()))
  self.assertEqual(self.fx.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0],2)
  self.runtime.demo.db.execute('SELECT count(*) FROM orders')
 def test_reject_missing_wrong_store_or_nonprivate_existing_file_without_creating(self):
  for change in ('missing','mismatch','permissions','extra'):
   config=copy.deepcopy(self.config)
   if change=='missing':config['stores'].pop('orders')
   elif change=='mismatch':config['stores']['orders']=config['stores']['merchants']
   elif change=='extra':config['secret']='must-not-be-accepted'
   else:os.chmod(config['stores']['orders'],0o644)
   try:
    with self.subTest(change=change),self.assertRaises((ValueError,PermissionError)):self.compose(config)
   finally:os.chmod(self.config['stores']['orders'],0o600)
 def test_memory_database_unknown_principal_and_revoked_project_are_rejected(self):
  for change in ('memory','principal','project'):
   config=copy.deepcopy(self.config)
   if change=='memory':config['stores']['orders']=':memory:'
   elif change=='principal':config['scenes']['shop1']['principal']='unknown'
   else:self.fx.center.db.execute("UPDATE projects SET active=0 WHERE id='project1'")
   with self.subTest(change=change),self.assertRaises((ValueError,PermissionError)):self.compose(config)
 def test_actual_memory_connection_cannot_claim_a_persistent_path(self):
  original=self.runtime.demo.db
  memory=sqlite3.connect(':memory:')
  try:
   self.runtime.demo.db=memory
   with self.assertRaisesRegex(PermissionError,'EXISTING_PERSISTENT_STORE_BINDING_MISMATCH'):
    self.compose()
  finally:self.runtime.demo.db=original;memory.close()

if __name__=='__main__':unittest.main()
