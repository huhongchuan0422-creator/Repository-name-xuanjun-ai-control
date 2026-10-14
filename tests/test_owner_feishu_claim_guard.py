import os
import pathlib
import sqlite3
import sys
import tempfile
import unittest

if 'P2_SOURCE_ROOT' not in os.environ:
    raise unittest.SkipTest('Exact frozen producer absent: integration NOT_RUN')
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, os.environ['P2_SOURCE_ROOT'] + '/stage1')
from execution_ledger import ExecutionLedger
from owner_feishu_claim_guard import OwnerFeishuClaimGuard
from owner_feishu_transport import OwnerFeishuTransport


class ClaimGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = self.tmp.name + '/ledger.sqlite'; self.now = 100
        db = sqlite3.connect(self.path)
        for name, fields in ExecutionLedger.SCHEMAS.items():
            db.execute('CREATE TABLE ' + name + '(' + ','.join(
                n + ' ' + t + (' PRIMARY KEY' if pk else '') for n, t, pk in fields) + ')')
        db.execute("INSERT INTO tasks(id,kind,state,depends,fence) VALUES('T1','CODEX_EXEC','DONE','[]',4)")
        db.commit(); db.close()
        self.active = {'ledger_uuid':'fixture', 'generation':1, 'epoch':2,
                       'instance':'fixture', 'db_path':self.path}
        owner = self
        class Activation:
            def read(self, require_active=False): return dict(owner.active)
        self.ledger = ExecutionLedger(self.path, ['fixture/repo'], clock=lambda:self.now, activation_store=Activation())
        self.supervisor = self.ledger.supervisor()
        db = self.supervisor._tx()
        self.key = self.supervisor._event(db, 'T1', 'COMPLETED', {}, destinations=('OWNER',))
        self.supervisor._commit(db); db.close()
        self.claim = self.supervisor.claim_delivery('fixture-worker', 'OWNER')
        self.supervisor.mark_delivery_sending(self.claim)
        self.guard = OwnerFeishuClaimGuard(self.ledger)

    def test_actual_pinned_ledger_and_claim_accepted(self):
        self.assertTrue(self.guard(self.claim))

    def test_all_claim_fields_bound(self):
        for key in ('event_key','destination','delivery_identity','claim_owner','claim_token',
                    'claim_epoch','claim_attempt','authority_fence','authority_epoch'):
            claim = dict(self.claim); claim[key] = 'wrong'
            self.assertFalse(self.guard(claim), key)

    def test_bool_epoch_rejected(self):
        claim = dict(self.claim); claim['claim_epoch'] = True
        self.assertFalse(self.guard(claim))

    def test_expired_claim_rejected(self):
        self.now = 200; self.assertFalse(self.guard(self.claim))

    def test_current_task_fence_required(self):
        with self.ledger._transaction() as db: db.execute('UPDATE tasks SET fence=99')
        self.assertFalse(self.guard(self.claim))

    def test_activation_drift_rejected(self):
        self.active['epoch'] = 3; self.assertFalse(self.guard(self.claim))

    def test_db_path_replacement_rejected(self):
        os.rename(self.path, self.path + '.original')
        open(self.path, 'wb').close()
        self.assertFalse(self.guard(self.claim))

    def test_valid_database_clone_replacement_rejected(self):
        import shutil
        shutil.copyfile(self.path, self.path + '.clone')
        os.replace(self.path + '.clone', self.path)
        self.assertFalse(self.guard(self.claim))

    def test_uncertain_without_reconciliation_claim_rejected(self):
        self.supervisor.mark_delivery_uncertain(self.claim)
        self.assertFalse(self.guard(self.claim))

    def test_actual_reconciliation_cas_authorizes_only_current_owner(self):
        self.supervisor.mark_delivery_uncertain(self.claim); self.now = 200
        def lookup(destination, identity):
            with self.ledger._transaction() as db:
                row = db.execute('SELECT * FROM supervision_delivery').fetchone()
                claim = dict(self.claim)
                claim.update({k:row[k] for k in ('reconciliation_owner','reconciliation_epoch')})
            self.assertTrue(self.guard(claim))
            claim['reconciliation_owner'] = 'other'
            self.assertFalse(self.guard(claim))
            return 'UNKNOWN'
        self.assertEqual(self.supervisor.reconcile_delivery(self.key,'OWNER','fixture-reconciler',lookup),'HELD')
        self.assertFalse(self.guard(self.claim))

    def test_unbound_ledger_rejected(self):
        ledger = ExecutionLedger(self.path,['fixture/repo'])
        with self.assertRaises(ValueError): OwnerFeishuClaimGuard(ledger)

    def test_real_guard_transport_and_persistent_ack(self):
        # Restore only this isolated fixture row to pending so deliver_once owns its claim.
        with self.ledger._transaction() as db:
            db.execute("UPDATE supervision_delivery SET state='PENDING'")
        calls = []
        def api(path, body):
            calls.append(body)
            return {'code':0,'data':{'message_id':'om_fixture','chat_id':body['receive_id'],
                'msg_type':'text','body':{'content':body['content']}}}
        transport = OwnerFeishuTransport('oc_fixture','a'*64,api,self.guard)
        self.assertEqual(self.supervisor.deliver_once('fixture-worker','OWNER',transport),'om_fixture')
        with self.ledger._transaction() as db:
            self.assertEqual(db.execute('SELECT state,receipt_id FROM supervision_delivery').fetchone()['state'],'ACKED')
        self.assertIsNone(self.supervisor.deliver_once('fixture-worker','OWNER',transport))
        self.assertEqual(len(calls),1)
