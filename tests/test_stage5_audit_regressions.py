"""Independent-review R1-R7 negative probes. All local, no provider or money."""
import sqlite3
import threading
import tempfile
import os
import json
from unittest.mock import patch
import unittest
from scripts.community_saas_modules import connect,set_price,grant
from scripts.community_saas_offer_catalog import install,create_offer,quote,approve_offer
from scripts.community_saas_order_preparation import (
    install as order_install,install_lifecycle,prepare,advance)
from scripts.community_saas_offline_handoff import (
    install_reviews,create_review,change_review,recovery_check,
    plan_finance_claim,make_test_attestation,inspect_test_attestation)
from scripts.community_saas_offers import (
    open_offer_store,register_offer,add_component,quote_offers,change_offer_status)
from scripts.community_saas_cost_pricing import open_cost_store,save_cost

KEY=b"review-fixture-not-real-provider-validation-key-123"
def price(cny=100,usd=20,cost=30):
    return {"type":"MODULE_FEE","label":"module","cycle":"MONTH","quantity":1,
            "cny_minor":cny,"usd_minor":usd,
            "cost_cny_minor":cost,"cost_usd_minor":1}
class FullScopeAuditProbes(unittest.TestCase):
 def setUp(self):
    self.base=connect();install(self.base)
    self.orders=sqlite3.connect(":memory:")
    order_install(self.orders);install_lifecycle(self.orders);install_reviews(self.orders)
 def tearDown(self):
    self.orders.close();self.base.close()
 def ready(self):
    create_offer(self.base,"offer",1,"storefront_catalog","MONTHLY",[price()],term_days=30)
    approve_offer(self.base,"offer",1,"approval1","costref1",10)
    quote(self.base,"quote","tenantA","offer",1,10,100)
    prepare(self.orders,self.base,"ord","tenantA","quote","CNY",20)
 def test_r1_offer_version_replace_fails(self):
    create_offer(self.base,"offer",1,"storefront_catalog","MONTHLY",[price()],term_days=30)
    with self.assertRaises(sqlite3.IntegrityError):
        self.base.execute("REPLACE INTO saas_offer_versions SELECT * FROM saas_offer_versions")
 def test_r1_offer_lines_replace_fails(self):
    create_offer(self.base,"offer",1,"storefront_catalog","MONTHLY",[price()],term_days=30)
    with self.assertRaises(sqlite3.IntegrityError):
        self.base.execute("INSERT OR REPLACE INTO saas_offer_lines SELECT * FROM saas_offer_lines")
 def test_r1_quote_replace_fails(self):
    create_offer(self.base,"offer",1,"storefront_catalog","MONTHLY",[price()],term_days=30)
    quote(self.base,"q","tenantA","offer",1,10,90)
    with self.assertRaises(sqlite3.IntegrityError):
        self.base.execute("REPLACE INTO saas_quotes SELECT * FROM saas_quotes")
 def test_r1_order_replace_fails(self):
    self.ready()
    with self.assertRaises(sqlite3.IntegrityError):
        self.orders.execute("INSERT OR REPLACE INTO saas_order_preparations SELECT * FROM saas_order_preparations")
 def test_r1_review_terminal_replace_fails(self):
    self.ready();create_review(self.orders,"task","tenantA","ord","FINANCE_EVIDENCE",21,"reason")
    change_review(self.orders,"task","tenantA","event","RESOLVED",22)
    with self.assertRaises(sqlite3.IntegrityError):
        self.orders.execute("REPLACE INTO saas_review_tasks SELECT * FROM saas_review_tasks")
 def test_r1_review_event_replace_fails(self):
    self.ready();create_review(self.orders,"task","tenantA","ord","FINANCE_EVIDENCE",21,"reason")
    change_review(self.orders,"task","tenantA","event","RESOLVED",22)
    with self.assertRaises(sqlite3.IntegrityError):
        self.orders.execute("REPLACE INTO saas_review_events SELECT * FROM saas_review_events")
 def test_r1_lifecycle_event_replace_fails(self):
    self.ready();advance(self.orders,"ord","tenantA","ev1","AWAITING_EXTERNAL",21)
    with self.assertRaises(sqlite3.IntegrityError):
        self.orders.execute("REPLACE INTO saas_order_lifecycle_events SELECT * FROM saas_order_lifecycle_events")
 def test_r1_module_event_replace_fails(self):
    set_price(self.base,"storefront_catalog",1,100,20,30)
    grant(self.base,"tenantA","storefront_catalog",10,40,1)
    with self.assertRaises(sqlite3.IntegrityError):
        self.base.execute("REPLACE INTO module_events SELECT * FROM module_events")
 def test_r2_draft_order_rejected(self):
    create_offer(self.base,"offer",1,"storefront_catalog","MONTHLY",[price()],term_days=30)
    quote(self.base,"q","tenantA","offer",1,10,100)
    with self.assertRaisesRegex(ValueError,"OFFER_APPROVAL_REQUIRED"):
        prepare(self.orders,self.base,"ord","tenantA","q","CNY",20)
 def test_r2_unknown_cost_no_approval(self):
    create_offer(self.base,"offer",1,"storefront_catalog","MONTHLY",[price(cost=None)],term_days=30)
    with self.assertRaisesRegex(ValueError,"COST_EVIDENCE_REQUIRED"):
        approve_offer(self.base,"offer",1,"approval","costref",10)
 def test_r2_immutable_approval(self):
    create_offer(self.base,"offer",1,"storefront_catalog","MONTHLY",[price()],term_days=30)
    approve_offer(self.base,"offer",1,"approval","costref",10)
    with self.assertRaises(sqlite3.IntegrityError):
        self.base.execute("REPLACE INTO saas_offer_approvals SELECT * FROM saas_offer_approvals")
 def test_r3_private_no_scope_rejected(self):
    o=open_offer_store()
    try:
        with self.assertRaisesRegex(ValueError,"TENANT_SCOPE_REQUIRED"):
            register_offer(o,"private","storefront_catalog","MONTHLY",1,30,True,"term","basis",availability="CUSTOMER_PRIVATE")
    finally:o.close()
 def test_r3_private_scope_filter(self):
    o=open_offer_store();costs=open_cost_store()
    try:
        for oid,tenant in (("a","tenantA"),("b","tenantB")):
            register_offer(o,oid,"storefront_catalog","MONTHLY",1,30,True,"term","basis",availability="CUSTOMER_PRIVATE",tenant_scope=tenant)
            add_component(o,oid,"license","MODULE_LICENSE","MONTHLY",100,10,"pricebook")
            save_cost(costs,oid,"license","VERIFIED_ACTUAL",20,2,"invoice","MONTHLY")
            for step in ("PREVIEW","APPROVED","EFFECTIVE"):change_offer_status(o,oid,step,costs)
        self.assertEqual(quote_offers(o,"storefront_catalog",cost_db=costs),[])
        self.assertEqual([x["offer_id"] for x in quote_offers(o,"storefront_catalog",tenant_id="tenantA",cost_db=costs)],["a"])
    finally:o.close();costs.close()
 def test_r4_fake_module_schema_rejected(self):
    with tempfile.TemporaryDirectory() as folder:
        path=os.path.join(folder,"fake.sqlite")
        db=sqlite3.connect(path)
        for name in ("module_prices","module_entitlements","module_events"):
            db.execute("CREATE TABLE "+name+"(fake INTEGER)")
        db.execute("PRAGMA user_version=1")
        db.close()
        with self.assertRaises(ValueError):connect(path)
 def test_r5_missing_projection_held(self):
    self.ready()
    advance(self.orders,"ord","tenantA","ev1","AWAITING_EXTERNAL",21)
    advance(self.orders,"ord","tenantA","ev2","CONFIRMATION_UNKNOWN",22)
    self.orders.execute("DELETE FROM saas_order_lifecycle WHERE order_id='ord'")
    v=recovery_check(self.orders,"tenantA")
    self.assertEqual(v["integrity_hold"],["ord"])
    self.assertIn("ord",v["awaiting_review"])
 def test_r4_offer_extension_install_atomic_on_denied_trigger(self):
    # Fail after some CREATE TABLE operations: rollback cannot leave partial tables.
    db=connect()
    try:
        before={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        def forbid(action,arg1,arg2,db_name,origin):
            return sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_TRIGGER else sqlite3.SQLITE_OK
        db.set_authorizer(forbid)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                install(db)
        finally:db.set_authorizer(None)
        after={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(before,after)
        install(db)
    finally:db.close()
 def test_r4_partial_offer_extension_rejected(self):
    db=connect()
    try:
        db.execute("CREATE TABLE saas_quotes(fake INTEGER)")
        with self.assertRaisesRegex(ValueError,"UNRECOGNIZED_OFFER_INSTALL_SCHEMA"):
            install(db)
    finally:db.close()
 def test_r5_projection_wrong_terminal_state_detected(self):
    self.ready()
    advance(self.orders,"ord","tenantA","ev1","AWAITING_EXTERNAL",21)
    self.orders.execute("UPDATE saas_order_lifecycle SET state='CANCELLED' WHERE order_id='ord'")
    self.assertEqual(recovery_check(self.orders,"tenantA")["integrity_hold"],["ord"])
 def test_r2_approved_components_locked_sqlite(self):
    o=open_offer_store()
    try:
        register_offer(o,"one","storefront_catalog","MONTHLY",1,30,True,"term","basis")
        add_component(o,"one","base","MODULE_LICENSE","MONTHLY",100,20,"pricebook")
        change_offer_status(o,"one","PREVIEW")
        change_offer_status(o,"one","APPROVED")
        with self.assertRaisesRegex(ValueError,"OFFER_COMPONENTS_FROZEN"):
            add_component(o,"one","extra","MODULE_LICENSE","MONTHLY",400,50,"pricebook")
        with self.assertRaises(sqlite3.IntegrityError):
            o.execute("DELETE FROM components WHERE offer_id='one'")
    finally:o.close()
 def test_r6_refund_backup_failure_closes_both_and_preserves_first_exception(self):
    from scripts.community_demo_api import serve_local
    with patch("scripts.community_demo_api.server_database") as primary, \
         patch("scripts.community_demo_api.open_refund_store") as source, \
         patch("scripts.community_demo_api.sqlite3.connect") as runtime:
        source.return_value.backup.side_effect=RuntimeError("backup-original")
        source.return_value.close.side_effect=RuntimeError("source-close-secondary")
        runtime.return_value.close.side_effect=RuntimeError("runtime-close-secondary")
        with self.assertRaisesRegex(RuntimeError,"backup-original"):
            serve_local(port=0)
        self.assertEqual(source.return_value.close.call_count,1)
        self.assertEqual(runtime.return_value.close.call_count,1)
        self.assertEqual(primary.return_value.close.call_count,1)
 def test_r7_pre_order_proof_rejected(self):
    self.ready()
    att=make_test_attestation(plan_finance_claim(self.orders,"ord","tenantA"),"proof",0,KEY)
    with self.assertRaisesRegex(ValueError,"PRE_ORDER_ATTESTATION"):
        inspect_test_attestation(self.orders,"ord","tenantA",att,KEY,30)
 def test_r7_at_creation_time_valid_fixture(self):
    self.ready()
    att=make_test_attestation(plan_finance_claim(self.orders,"ord","tenantA"),"proof",20,KEY)
    self.assertFalse(inspect_test_attestation(self.orders,"ord","tenantA",att,KEY,30)["production_eligible"])
 def test_r1_secondary_unique_replace_rejected(self):
    self.ready()
    previous=self.orders.execute("SELECT order_id,snapshot FROM saas_order_preparations").fetchall()
    with self.assertRaises(sqlite3.IntegrityError):
        self.orders.execute("""INSERT OR REPLACE INTO saas_order_preparations
            SELECT 'replacement_order',tenant_id,quote_id,currency,created_at,snapshot
            FROM saas_order_preparations WHERE order_id='ord'""")
    self.assertEqual(self.orders.execute("SELECT order_id,snapshot FROM saas_order_preparations").fetchall(),previous)
 def test_r1_review_task_id_cannot_change(self):
    self.ready()
    create_review(self.orders,"task","tenantA","ord","FINANCE_EVIDENCE",21,"reason")
    with self.assertRaises(sqlite3.IntegrityError):
        self.orders.execute("UPDATE saas_review_tasks SET task_id='changed',state='RESOLVED' WHERE task_id='task'")
    self.assertEqual(self.orders.execute("SELECT task_id,state FROM saas_review_tasks").fetchall(),[("task","PENDING")])
 def test_r1_mismatched_order_snapshot_rejected(self):
    self.ready()
    row=self.orders.execute("SELECT tenant_id,quote_id,currency,created_at,snapshot FROM saas_order_preparations").fetchone()
    self.orders.execute("DELETE FROM saas_order_preparations WHERE 0")
    fake=json.loads(row[4])
    # Invalid preexisting record fixture, not an application write path.
    self.orders.execute("INSERT INTO saas_order_preparations VALUES(?,?,?,?,?,?)",
                        ("different","tenantB",row[1],row[2],row[3],json.dumps(fake)))
    with self.assertRaisesRegex(ValueError,"ORDER_SNAPSHOT_BINDING_MISMATCH"):
        from scripts.community_saas_order_preparation import read
        read(self.orders,"different","tenantB")
 def test_r2_catalog_approved_line_immutable(self):
    create_offer(self.base,"offer",1,"storefront_catalog","MONTHLY",[price()],term_days=30)
    approve_offer(self.base,"offer",1,"approval","cost",10)
    count=self.base.execute("SELECT COUNT(*) FROM saas_offer_lines").fetchone()[0]
    with self.assertRaises(sqlite3.IntegrityError):
        self.base.execute("INSERT INTO saas_offer_lines VALUES('offer',1,2,'AGENCY_FEE','new','MONTH',1,900,180,NULL,NULL)")
    self.assertEqual(self.base.execute("SELECT COUNT(*) FROM saas_offer_lines").fetchone()[0],count)
 def test_r2_cannot_move_draft_component_to_effective(self):
    o=open_offer_store();costs=open_cost_store()
    try:
        for oid in ("draft","published"):
            register_offer(o,oid,"storefront_catalog","MONTHLY",1,30,True,"term","basis")
            add_component(o,oid,"charge","MODULE_LICENSE","MONTHLY",100,20,"pricebook")
        save_cost(costs,"published","charge","VERIFIED_ACTUAL",10,1,"invoice","MONTHLY")
        for state in ("PREVIEW","APPROVED","EFFECTIVE"):
            change_offer_status(o,"published",state,costs)
        with self.assertRaises(sqlite3.IntegrityError):
            o.execute("UPDATE components SET offer_id='published' WHERE offer_id='draft'")
        self.assertEqual(o.execute("SELECT offer_id FROM components WHERE offer_id='draft'").fetchone()[0],"draft")
    finally:o.close();costs.close()
 def test_r5_corrupt_projection_advance_does_not_commit(self):
    self.ready()
    advance(self.orders,"ord","tenantA","ev1","AWAITING_EXTERNAL",21)
    self.orders.execute("DELETE FROM saas_order_lifecycle WHERE order_id='ord'")
    self.orders.commit()
    before=self.orders.execute("SELECT COUNT(*) FROM saas_order_lifecycle_events").fetchone()[0]
    with self.assertRaisesRegex(ValueError,"LIFECYCLE"):
        advance(self.orders,"ord","tenantA","ev2","CANCELLED",22)
    self.assertEqual(self.orders.execute("SELECT COUNT(*) FROM saas_order_lifecycle_events").fetchone()[0],before)
    self.assertEqual(self.orders.execute("SELECT COUNT(*) FROM saas_order_lifecycle").fetchone()[0],0)
 def test_r5_null_confirmation_proof_held(self):
    self.ready()
    advance(self.orders,"ord","tenantA","ev1","AWAITING_EXTERNAL",21)
    advance(self.orders,"ord","tenantA","ev2","CONFIRMATION_UNKNOWN",22)
    # Fault injection via direct SQLite; public advance must never permit this.
    self.orders.execute("INSERT INTO saas_order_lifecycle_events VALUES('ev3','ord','CONFIRMATION_UNKNOWN','CONFIRMED_EXTERNAL',NULL,23)")
    self.orders.execute("UPDATE saas_order_lifecycle SET state='CONFIRMED_EXTERNAL',proof_ref=NULL,updated_at=23 WHERE order_id='ord'")
    self.orders.commit()
    self.assertEqual(recovery_check(self.orders,"tenantA")["integrity_hold"],["ord"])
    with self.assertRaisesRegex(ValueError,"LIFECYCLE_EVENT_INCONSISTENT"):
        from scripts.community_saas_order_preparation import entitlement_intent
        entitlement_intent(self.orders,"ord","tenantA",24)
class AtomicApprovalConcurrentTests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory()
    self.path=os.path.join(self.tmp.name,"approval.sqlite")
    self.setup=connect(self.path);install(self.setup)
    create_offer(self.setup,"race",1,"storefront_catalog","MONTHLY",
                 [price()],term_days=30)
    self.setup.close()
 def tearDown(self):self.tmp.cleanup()
 def connection(self,timeout=1):
    db=sqlite3.connect(self.path,timeout=timeout)
    db.execute("PRAGMA foreign_keys=ON")
    return db
 def test_r2_atomic_cost_read_prevents_two_connection_unknown_line_race(self):
    ready=threading.Event();resume=threading.Event();result=[]
    import scripts.community_saas_offer_catalog as catalog
    real=catalog.get_offer
    def gated(db,oid,version):
        offer=real(db,oid,version)
        ready.set()
        if not resume.wait(5):
            raise RuntimeError("TEST_BARRIER_TIMEOUT")
        return offer
    def approver():
        db=self.connection()
        try:
            with patch.object(catalog,"get_offer",gated):
                result.append(catalog.approve_offer(db,"race",1,"approval","costref",10))
        except Exception as exc:result.append(exc)
        finally:db.close()
    thread=threading.Thread(target=approver)
    thread.start()
    try:
        self.assertTrue(ready.wait(5))
        writer=self.connection(timeout=0)
        try:
            with self.assertRaises(sqlite3.OperationalError) as failure:
                writer.execute("""INSERT INTO saas_offer_lines VALUES
                    ('race',1,2,'AGENCY_FEE','unapproved','MONTH',1,900,180,NULL,NULL)""")
            self.assertIn("locked",str(failure.exception).lower())
        finally:writer.close()
    finally:
        resume.set();thread.join(6)
    self.assertFalse(thread.is_alive())
    self.assertEqual(len(result),1)
    if isinstance(result[0],Exception):raise result[0]
    db=self.connection()
    try:
        self.assertEqual(db.execute("SELECT COUNT(*) FROM saas_offer_lines").fetchone()[0],1)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM saas_offer_approvals").fetchone()[0],1)
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("""INSERT INTO saas_offer_lines VALUES
                ('race',1,2,'AGENCY_FEE','unapproved','MONTH',1,900,180,NULL,NULL)""")
    finally:db.close()
 def test_r2_unknown_cost_rejected_without_half_approval(self):
    db=self.connection()
    try:
        db.execute("""INSERT INTO saas_offer_lines VALUES
                ('race',1,2,'AGENCY_FEE','unknown','MONTH',1,900,180,NULL,NULL)""")
        db.commit()
        with self.assertRaisesRegex(ValueError,"COST_EVIDENCE_REQUIRED"):
            approve_offer(db,"race",1,"approval","costref",10)
        self.assertFalse(db.in_transaction)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM saas_offer_approvals").fetchone()[0],0)
    finally:db.close()
 def test_r2_nested_transaction_does_not_commit_caller(self):
    db=self.connection()
    try:
        db.execute("BEGIN IMMEDIATE")
        with self.assertRaisesRegex(ValueError,"APPROVAL_REQUIRES_OWN_TRANSACTION"):
            approve_offer(db,"race",1,"approval","costref",10)
        self.assertTrue(db.in_transaction)
        db.rollback()
        self.assertEqual(db.execute("SELECT COUNT(*) FROM saas_offer_approvals").fetchone()[0],0)
    finally:db.close()
 def test_r2_approval_insert_failure_rolls_back(self):
    db=self.connection()
    try:
        db.execute("CREATE TRIGGER block_approval BEFORE INSERT ON saas_offer_approvals BEGIN SELECT RAISE(ABORT,'AUDIT_INJECTED'); END;")
        db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            approve_offer(db,"race",1,"approval","costref",10)
        self.assertFalse(db.in_transaction)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM saas_offer_approvals").fetchone()[0],0)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM saas_offer_lines").fetchone()[0],1)
    finally:db.close()
if __name__=="__main__":unittest.main()
