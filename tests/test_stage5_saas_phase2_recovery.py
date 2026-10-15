import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.community_saas_phase2_recovery import backup,verify_backup,cross_store_audit
class RecoveryTests(unittest.TestCase):
 def setUp(self):
    self.temp=tempfile.TemporaryDirectory()
    self.source=Path(self.temp.name)/"source.sqlite"
    self.target=Path(self.temp.name)/"backup.sqlite"
    db=sqlite3.connect(self.source)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT)")
    db.execute("INSERT INTO sample VALUES(1,'immutable')")
    db.commit();db.close()
 def tearDown(self):self.temp.cleanup()
 def test_01_backup_creates_verified_copy(self):
    x=backup(self.source,self.target)
    self.assertTrue(verify_backup(self.target,x["sha256"])["verified"])
 def test_02_no_in_place_overwrite(self):
    with self.assertRaises(ValueError):backup(self.source,self.source)
 def test_03_no_overwrite_existing_backup(self):
    backup(self.source,self.target)
    with self.assertRaises(ValueError):backup(self.source,self.target)
 def test_04_wrong_digest_rejected(self):
    backup(self.source,self.target)
    with self.assertRaisesRegex(ValueError,"BACKUP_DIGEST_MISMATCH"):
        verify_backup(self.target,"0"*64)
 def test_05_corrupt_backup_not_accepted(self):
    x=backup(self.source,self.target)
    self.target.write_bytes(b"not database")
    with self.assertRaises(ValueError):verify_backup(self.target,x["sha256"])
 def test_06_no_restore_side_effect(self):
    x=backup(self.source,self.target)
    self.assertFalse(x["restored"])
    a=sqlite3.connect(self.target)
    try:self.assertEqual(a.execute("SELECT value FROM sample").fetchone()[0],"immutable")
    finally:a.close()
 def test_07_missing_source_fails(self):
    with self.assertRaises(ValueError):backup(self.target,Path(self.temp.name)/"other.sqlite")
class CrossStoreAuditTests(unittest.TestCase):
 def setUp(self):
    from scripts.community_saas_modules import connect
    from scripts.community_saas_offer_catalog import install as install_quotes,create_offer,approve_offer,quote
    from scripts.community_saas_order_preparation import install as order_install,install_lifecycle,prepare
    from scripts.community_saas_offline_handoff import install_reviews
    self.quotes=connect();install_quotes(self.quotes)
    self.orders=sqlite3.connect(":memory:")
    order_install(self.orders);install_lifecycle(self.orders);install_reviews(self.orders)
    line={"type":"MODULE_FEE","label":"test","cycle":"MONTH","quantity":1,
          "cny_minor":300,"usd_minor":45,"cost_cny_minor":50,"cost_usd_minor":5}
    create_offer(self.quotes,"sku",1,"storefront_catalog","MONTHLY",[line],term_days=30)
    approve_offer(self.quotes,"sku",1,"approval","cost",10)
    quote(self.quotes,"quote","tenantA","sku",1,10,100)
    prepare(self.orders,self.quotes,"order","tenantA","quote","CNY",20)
 def tearDown(self):self.orders.close();self.quotes.close()
 def test_08_valid_two_store_integrity(self):
    view=cross_store_audit(self.quotes,self.orders,"tenantA")
    self.assertEqual(view["orders_checked"],1)
    self.assertEqual(view["integrity_hold"],[])
    self.assertFalse(view["cross_database_atomicity_proven"])
 def test_09_missing_cross_store_quote_hold(self):
    other=sqlite3.connect(":memory:")
    try:
        from scripts.community_saas_modules import SCHEMA
        from scripts.community_saas_offer_catalog import SCHEMA as OFFERS
        other.executescript(SCHEMA+OFFERS)
        view=cross_store_audit(other,self.orders,"tenantA")
        self.assertEqual(view["integrity_hold"],["order"])
    finally:other.close()
 def test_10_tenant_isolation(self):
    self.assertEqual(cross_store_audit(self.quotes,self.orders,"tenantB")["orders_checked"],0)
if __name__=="__main__":unittest.main()
