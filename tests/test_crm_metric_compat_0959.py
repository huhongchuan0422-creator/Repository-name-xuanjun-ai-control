import ast,hashlib,sqlite3,unittest
from pathlib import Path
from scripts import community_ad_store as ad
from scripts.community_mail_delivery import optional_mail_configuration
class MetricCompat(unittest.TestCase):
 def setUp(self):
  self.db=ad.open_offline();self.addCleanup(self.db.close);self.scope={'tenant_id':'tenant-a','merchant_id':'merchant-a','store_id':'store-a'}
  self.db.execute("INSERT INTO campaigns VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",('tenant-a','merchant-a','store-a','campaign-a','AD_SLOT_PAYMENT_AMOUNT','ACTIVE','APPROVED',1,1,500,'Synthetic','https://example.invalid',1))
  for event,kind,at in [('i0','IMPRESSION',99),('i1','IMPRESSION',100),('i2','IMPRESSION',199),('i3','IMPRESSION',200),('c1','CLICK',150)]:self.db.execute('INSERT INTO metric_events VALUES(?,?,?,?,?,?,?,?)',('tenant-a','merchant-a','store-a','AD_SLOT_PAYMENT_AMOUNT',kind,event,'campaign-a',at))
  self.db.commit()
 def test_original_v1_schema_and_read_only_half_open_counts(self):
  before=self.db.total_changes;schema=self.db.execute('SELECT sql FROM sqlite_master ORDER BY name').fetchall();v=ad.metric_report(self.db,self.scope,100,200)
  self.assertEqual((v['campaigns'][0]['impressions'],v['campaigns'][0]['clicks']),(2,1));self.assertEqual(self.db.total_changes,before);self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],1);self.assertEqual(schema,self.db.execute('SELECT sql FROM sqlite_master ORDER BY name').fetchall())
 def test_other_tenant_no_data(self):
  self.assertEqual(ad.metric_report(self.db,dict(self.scope,tenant_id='tenant-b'),100,200)['campaigns'],[])
 def test_invalid_window_and_page(self):
  for start,end,limit,cursor in [(200,100,50,''),(0,367*86400,50,''),(100,200,0,''),(100,200,50,'bad?')]:
   with self.assertRaises(ValueError):ad.metric_report(self.db,self.scope,start,end,limit,cursor)
 def test_non_ascii_scope_rejected_on_python36(self):
  with self.assertRaises(ValueError):ad.metric_report(self.db,dict(self.scope,tenant_id='非ASCII'),100,200)
 def test_schema_literal_exact_original_and_core_pin(self):
  old=Path(__file__).resolve().parents[2]/'shared-release-source/scripts/community_ad_store.py';tree=ast.parse(old.read_text());literal=next(ast.literal_eval(x.value) for x in tree.body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SCHEMA' for t in x.targets));self.assertEqual(literal,ad.SCHEMA)
  core=Path(ad.__file__).with_name('pr122_customer_core.py');self.assertEqual(hashlib.sha256(core.read_bytes()).hexdigest(),'cfd3c9d634ddd41d4b59dd4a3ca374d1f1bbcec009c22878e9560d21ae9365b0')
 def test_original_protected_loader_import_no_missing_metric(self):
  from scripts.community_mini_host_config import load_protected
  self.assertTrue(callable(load_protected));self.assertEqual(optional_mail_configuration(None),((),{}))
if __name__=='__main__':unittest.main()
