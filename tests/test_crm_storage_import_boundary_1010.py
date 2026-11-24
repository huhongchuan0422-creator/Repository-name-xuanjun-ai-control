import hashlib,sys,types,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from scripts import community_persistent_runtime as runtime
class StorageImportBoundary(unittest.TestCase):
 def test_import_does_not_activate_migration(self):
  self.assertNotIn('scripts.community_stage_migration',sys.modules)
  self.assertTrue(callable(runtime.PersistentRuntime.open))
 def test_initialize_original_contract_failure_before_io(self):
  with patch('pathlib.Path.mkdir') as mkdir,patch('scripts.community_persistent_runtime.os.open') as opening,patch('scripts.community_persistent_runtime.sqlite3.connect') as connect:
   with self.assertRaisesRegex(ImportError,'SCHEMA_V1'):runtime.PersistentRuntime.initialize('/synthetic-not-used',{},clock=lambda:1)
   mkdir.assert_not_called();opening.assert_not_called();connect.assert_not_called()
 def test_open_original_contract_failure_before_io(self):
  with patch('scripts.community_persistent_runtime._directory') as directory,patch.object(runtime.PersistentRuntime,'_lock') as locking,patch('scripts.community_persistent_runtime.sqlite3.connect') as connect:
   with self.assertRaisesRegex(ImportError,'SCHEMA_V1'):runtime.PersistentRuntime.open('/synthetic-not-used',{},clock=lambda:1)
   directory.assert_not_called();locking.assert_not_called();connect.assert_not_called()
 def contract(self):
  return types.SimpleNamespace(SPECS={'merchants':('ORIGINAL_DDL',(2,),())},_catalog=Mock(return_value='expected'),_template=Mock(return_value='expected'),_integrity=Mock())
 def test_schema_delegates_exact_contract_and_integrity(self):
  contract=self.contract();db=Mock();db.execute.return_value.fetchone.return_value=(2,)
  with patch.object(runtime,'_schema_contract',return_value=contract):runtime.PersistentRuntime._schema('merchants',db)
  db.execute.assert_called_once_with('PRAGMA user_version');contract._template.assert_called_once_with('ORIGINAL_DDL');contract._catalog.assert_called_once_with(db);contract._integrity.assert_called_once_with(db)
 def test_wrong_version_or_catalog_still_rejected(self):
  for version,catalog in [(1,'expected'),(2,'wrong')]:
   contract=self.contract();contract._catalog.return_value=catalog;db=Mock();db.execute.return_value.fetchone.return_value=(version,)
   with patch.object(runtime,'_schema_contract',return_value=contract):
    with self.assertRaisesRegex(ValueError,'CURRENT_RUNTIME_SCHEMA_REQUIRED:merchants'):runtime.PersistentRuntime._schema('merchants',db)
   contract._integrity.assert_not_called()
 def test_core_and_all_schema_files_unchanged_from_0959(self):
  root=Path(__file__).resolve().parents[1];before=root.parent/'shared-release-compat-0959'
  names=['pr122_customer_core.py','community_ad_store.py','community_merchant_store.py','community_stage_migration.py','community_saas_modules.py','community_saas_phase2.py','community_ad_contract.py','community_local_admin.py','community_onboarding_offline.py','community_refund_preview_store.py']
  for name in names:self.assertEqual((root/'scripts'/name).read_bytes(),(before/'scripts'/name).read_bytes(),name)
  self.assertEqual(hashlib.sha256((root/'scripts/pr122_customer_core.py').read_bytes()).hexdigest(),'cfd3c9d634ddd41d4b59dd4a3ca374d1f1bbcec009c22878e9560d21ae9365b0')
if __name__=='__main__':unittest.main()
