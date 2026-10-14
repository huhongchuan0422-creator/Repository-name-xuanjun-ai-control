import os,sqlite3,tempfile,unittest
from scripts.community_order_store import connect,create_order,simulated_transition,state
from scripts.community_refund_preview_store import open_refund_store,record_preview,preview_total
S={"tenant_id":"t1","merchant_id":"m1","store_id":"s1"}
O={"tenant_id":"t2","merchant_id":"m2","store_id":"s2"}
def successful(orders,scope,reference="r1",amount=120):
 create_order(orders,scope,reference,amount)
 simulated_transition(orders,scope,reference,"paid_"+scope["tenant_id"],"SUCCESS",{
  "simulation_only":True,"scope":scope,"reference":reference,"amount_minor":amount,
  "provider_transaction_id":"tx_"+scope["tenant_id"]})
class RefundPreviewTests(unittest.TestCase):
 def setUp(self):
  self.orders=connect();self.refunds=open_refund_store()
 def tearDown(self):self.orders.close();self.refunds.close()
 def test_preview_never_changes_order_or_provider(self):
  successful(self.orders,S)
  result=record_preview(self.refunds,self.orders,S,"r1","ev1",40)
  self.assertEqual(result,{"recorded":True,"preview_total_minor":40,"provider_refund_executed":False})
  self.assertEqual(state(self.orders,S,"r1")["state"],"SUCCESS")
  self.assertFalse(state(self.orders,S,"r1")["provider_settlement_verified"])
 def test_split_partial_and_over_order_denial(self):
  successful(self.orders,S)
  record_preview(self.refunds,self.orders,S,"r1","ev1",40)
  record_preview(self.refunds,self.orders,S,"r1","ev2",80)
  self.assertEqual(preview_total(self.refunds,S,"r1"),120)
  with self.assertRaisesRegex(ValueError,"EXCEEDS_ORDER"):
   record_preview(self.refunds,self.orders,S,"r1","ev3",1)
  self.assertEqual(preview_total(self.refunds,S,"r1"),120)
 def test_duplicate_replay_and_collision(self):
  successful(self.orders,S)
  record_preview(self.refunds,self.orders,S,"r1","ev1",40)
  self.assertEqual(record_preview(self.refunds,self.orders,S,"r1","ev1",40)["recorded"],False)
  with self.assertRaisesRegex(ValueError,"REFUND_EVENT_COLLISION"):
   record_preview(self.refunds,self.orders,S,"r1","ev1",41)
  self.assertEqual(self.refunds.execute("SELECT COUNT(*) FROM refund_events").fetchone()[0],1)
 def test_cross_tenant_same_reference_cannot_read_or_replay(self):
  successful(self.orders,S);successful(self.orders,O)
  record_preview(self.refunds,self.orders,S,"r1","ev1",30)
  self.assertEqual(preview_total(self.refunds,O,"r1"),0)
  with self.assertRaisesRegex(ValueError,"REFUND_EVENT_COLLISION"):
   record_preview(self.refunds,self.orders,O,"r1","ev1",20)
  self.assertEqual(preview_total(self.refunds,O,"r1"),0)
 def test_requires_existing_simulated_success(self):
  create_order(self.orders,S,"pending",120)
  with self.assertRaises(ValueError):
   record_preview(self.refunds,self.orders,S,"pending","ev1",10)
  with self.assertRaises(ValueError):
   record_preview(self.refunds,self.orders,S,"missing","ev2",10)
  self.assertEqual(self.refunds.execute("SELECT COUNT(*) FROM refund_events").fetchone()[0],0)
 def test_rejects_bool_and_zero_and_float(self):
  successful(self.orders,S)
  for value in (True,0,1.5,-1,100000001):
   with self.assertRaises(ValueError):
    record_preview(self.refunds,self.orders,S,"r1","ev1",value)
 def test_append_only_triggers_and_file_reopen(self):
  successful(self.orders,S)
  with tempfile.TemporaryDirectory() as d:
   path=os.path.join(d,"refund.sqlite")
   a=open_refund_store(path)
   record_preview(a,self.orders,S,"r1","ev1",45)
   a.close()
   b=open_refund_store(path)
   self.assertEqual(preview_total(b,S,"r1"),45)
   with self.assertRaises(sqlite3.IntegrityError):b.execute("DELETE FROM refund_events")
   with self.assertRaises(sqlite3.IntegrityError):b.execute("UPDATE refund_events SET amount_minor=2")
   b.close()
 def test_corrupt_schema_rejected_without_destroying_data(self):
  with tempfile.TemporaryDirectory() as d:
   path=os.path.join(d,"bad.sqlite")
   raw=sqlite3.connect(path);raw.execute("CREATE TABLE refund_events(sentinel TEXT)")
   raw.execute("INSERT INTO refund_events VALUES('keep')");raw.commit();raw.close()
   with self.assertRaises(ValueError):open_refund_store(path)
   raw=sqlite3.connect(path)
   self.assertEqual(raw.execute("SELECT sentinel FROM refund_events").fetchone()[0],"keep")
   raw.close()
 def test_two_connections_cannot_exceed_total(self):
  successful(self.orders,S)
  with tempfile.TemporaryDirectory() as d:
   path=os.path.join(d,"shared.sqlite")
   a=open_refund_store(path);b=open_refund_store(path)
   try:
    record_preview(a,self.orders,S,"r1","e1",80)
    with self.assertRaisesRegex(ValueError,"EXCEEDS_ORDER"):
     record_preview(b,self.orders,S,"r1","e2",50)
    self.assertEqual(preview_total(a,S,"r1"),80)
   finally:a.close();b.close()
if __name__=="__main__":unittest.main()
