import sqlite3
import tempfile
import os
import unittest
from scripts.community_order_store import connect, create_order, state, simulated_transition
S={'tenant_id':'t1','merchant_id':'m1','store_id':'s1'}
def ev(identity=S,ref='r1',amount=105,tx='tx1'):
    return {'simulation_only':True,'scope':dict(identity),'reference':ref,'amount_minor':amount,'provider_transaction_id':tx}
class OrderTests(unittest.TestCase):
    def setUp(self):
        self.db=connect()
        create_order(self.db,S,'r1',105)
    def tearDown(self): self.db.close()
    def test_pending(self): self.assertEqual(state(self.db,S,'r1')['state'],'PENDING')
    def test_simulated_success(self):
        self.assertEqual(simulated_transition(self.db,S,'r1','e1','SUCCESS',ev())['state'],'SUCCESS')
        self.assertEqual(state(self.db,S,'r1')['state'],'SUCCESS')
    def test_idempotent(self):
        simulated_transition(self.db,S,'r1','e1','SUCCESS',ev())
        self.assertTrue(simulated_transition(self.db,S,'r1','e1','SUCCESS',ev())['duplicate'])
    def test_cross_scope_denied(self):
        for key in S:
            with self.assertRaises(ValueError): state(self.db,dict(S,**{key:'other'}),'r1')
    def test_amount_mismatch_denied(self):
        with self.assertRaises(ValueError): simulated_transition(self.db,S,'r1','e1','SUCCESS',ev(amount=106))
    def test_proof_required(self):
        with self.assertRaises(ValueError): simulated_transition(self.db,S,'r1','e1','SUCCESS',dict(ev(),simulation_only=False))
    def test_collision_denied(self):
        simulated_transition(self.db,S,'r1','e1','SUCCESS',ev())
        with self.assertRaises(ValueError): simulated_transition(self.db,S,'r1','e1','FAILED',ev())
    def test_terminal_no_second_transition(self):
        simulated_transition(self.db,S,'r1','e1','SUCCESS',ev())
        with self.assertRaises(ValueError): simulated_transition(self.db,S,'r1','e2','FAILED',ev(tx='tx2'))
    def test_duplicate_reference_within_scope_denied(self):
        with self.assertRaises(sqlite3.IntegrityError): create_order(self.db,S,'r1',105)
    def test_same_ref_other_merchant_is_separate(self):
        other=dict(S,merchant_id='m2')
        create_order(self.db,other,'r1',105)
        simulated_transition(self.db,S,'r1','e1','SUCCESS',ev())
        self.assertEqual(state(self.db,other,'r1')['state'],'PENDING')
    def test_tx_unique(self):
        create_order(self.db,S,'r2',105)
        simulated_transition(self.db,S,'r1','e1','SUCCESS',ev())
        with self.assertRaises(sqlite3.IntegrityError):
            simulated_transition(self.db,S,'r2','e2','SUCCESS',ev(ref='r2'))
        self.assertEqual(state(self.db,S,'r2')['state'],'PENDING')
    def test_invalid_bool_amount(self):
        with self.assertRaises(ValueError): create_order(self.db,S,'r2',True)
    def test_persistent_reopen_preserves_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path=os.path.join(directory,'orders.sqlite')
            first=connect(path)
            create_order(first,S,'persist',123)
            first.close()
            second=connect(path)
            self.assertEqual(state(second,S,'persist')['amount_minor'],123)
            second.close()
    def test_incompatible_schema_refused_without_data_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            path=os.path.join(directory,'orders.sqlite')
            raw=sqlite3.connect(path)
            raw.execute('CREATE TABLE orders(sentinel TEXT)')
            raw.execute("INSERT INTO orders VALUES('retain')")
            raw.commit();raw.close()
            with self.assertRaises(ValueError): connect(path)
            verify=sqlite3.connect(path)
            self.assertEqual(verify.execute('SELECT sentinel FROM orders').fetchone()[0],'retain')
            verify.close()
    def test_partial_existing_schema_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path=os.path.join(directory,'orders.sqlite')
            raw=sqlite3.connect(path)
            raw.execute('CREATE TABLE order_events(event_id TEXT)')
            raw.commit();raw.close()
            with self.assertRaises(ValueError): connect(path)
if __name__=='__main__': unittest.main()
