"""Real service/SQLite/signature coupling; host facts explicitly synthetic."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'runtime'),str(HERE/'original'),str(HERE)]
from authority_store import AuthorityStore
from issuer_service import IssuerService
from receipt_provider import ReceiptProvider,Hold,digest
from test_authority_store import grant
import test_receipt_provider as provider_fixtures

class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):provider_fixtures.ProviderTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();os.chmod(self.folder.name,0o700)
        self.store=AuthorityStore(str(Path(self.folder.name)/'issuer.db'),initialize=True,clock=lambda:100)
        self.g=grant();self.store.register(self.g)
        self.principal={'actor_id':self.g['actor_id'],'host':self.g['target_host'],'writer_id':'trusted-fixture-writer'}
        self.change=lambda result:None
        signer=lambda raw:subprocess.check_output(['openssl','dgst','-sha256','-sign',self.key],input=raw)
        self.service=IssuerService(self.store,self.host,signer,'TEST_ONLY')
        self.provider=ReceiptProvider(lambda request:self.service.handle(request,self.principal),
                                      self.modulus,65537,'TEST_ONLY',clock=lambda:101)
    def tearDown(self):self.store.close();self.folder.cleanup()
    def host(self,g,aid,op,payload):
        result={'status':'AUTHORIZED','policy':'P2_ATTEMPT5_V1'}
        receipt={'grant_sha256':digest(g),'attempt_id':aid,'operation':op,'payload_sha256':digest(payload),
                 'run_id':'TEST_RUN','job_id':'TEST_JOB','invoke_id':'TEST_INVOKE',
                 'backup_sha256':'a'*64,'checkpoint_sha256':'b'*64,'log_sha256':'c'*64,'result':result}
        self.change(receipt);return receipt
    def consume(self):return self.provider.request(self.g,'attempt1','consume_attempt',
                {'ordinal':1,'command_sha256':'a'*64,'ledger_sha256':'b'*64})
    def test_real_service_signed_consumption(self):
        self.assertEqual(self.consume()['status'],'CONSUMED')
        self.assertEqual(self.store.db.execute('SELECT consumed FROM grants').fetchone()[0],1)
    def test_rpc_retry_idempotent_consumption(self):
        self.consume();self.consume()
        self.assertEqual(self.store.db.execute('SELECT consumed FROM grants').fetchone()[0],1)
    def test_private_audit_retains_actual_transaction_binding(self):
        self.consume();self.provider.request(self.g,'attempt1','authorize_first_admission')
        import json
        rows=self.store.db.execute("SELECT body FROM audit WHERE event='SIGNED_RECEIPT' ORDER BY id").fetchall()
        receipt=json.loads(rows[-1][0])['host_receipt']
        self.assertEqual((receipt['run_id'],receipt['job_id'],receipt['invoke_id']),('TEST_RUN','TEST_JOB','TEST_INVOKE'))
        self.assertEqual(receipt['backup_sha256'],'a'*64)
    def test_wrong_authenticated_principal_refused(self):
        self.principal['host']='OTHER'
        with self.assertRaises(Hold):self.consume()
        self.assertEqual(self.store.db.execute('SELECT consumed FROM grants').fetchone()[0],0)
    def test_missing_real_transaction_ids_refused(self):
        self.consume();self.change=lambda receipt:receipt.update(invoke_id='')
        with self.assertRaises(Hold):self.provider.request(self.g,'attempt1','authorize_first_admission')
    def test_wrong_host_readback_binding_refused(self):
        self.consume();self.change=lambda receipt:receipt.update(payload_sha256='f'*64)
        with self.assertRaises(Hold):self.provider.request(self.g,'attempt1','authorize_first_admission')
    def test_no_unsigned_or_unclaimed_admission(self):
        with self.assertRaises(Hold):self.provider.request(self.g,'not_consumed','authorize_first_admission')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM attempts').fetchone()[0],0)
    def cycle_registration(self):
        from permit_cycle import policy
        value=policy()
        self.store.register_cycle(self.g,value,{'grant_sha256':digest(self.g),
            'approval_body_sha256':self.g['approval_body_sha256'],'cycle_policy_sha256':digest(value),'review_id':9000000001})
        return {'policy_sha256':digest(value),'review_id':9000000001,'approval_body_sha256':self.g['approval_body_sha256']}
    def cycle_host(self,receipt):
        receipt['result'].update(status='UNCHANGED',binding=self.cycle_payload,
            source_identity={k:self.g[k] for k in ('source_commit','source_tree','kit_sha256','manifest_sha256')})
    def test_cycle_same_review_policy_service_binding(self):
        self.cycle_payload=self.cycle_registration();self.change=self.cycle_host
        result=self.provider.request(self.g,'CANDIDATE','verify_cycle_binding',self.cycle_payload)
        self.assertEqual(result['status'],'UNCHANGED')
    def test_cycle_registration_requires_authenticated_policy_hash(self):
        from permit_cycle import policy
        with self.assertRaises(Hold):self.store.register_cycle(self.g,policy(),{})
    def test_cycle_cannot_change_approval_per_retry(self):
        self.cycle_payload=self.cycle_registration();self.change=self.cycle_host
        self.cycle_payload['review_id']+=1
        with self.assertRaises(Hold):self.provider.request(self.g,'CANDIDATE','verify_cycle_binding',self.cycle_payload)
    def test_cycle_source_change_permanently_stops_original_round(self):
        self.cycle_payload=self.cycle_registration()
        def changed(receipt):
            self.cycle_host(receipt);receipt['result']['source_identity']['source_commit']='f'*40
        self.change=changed
        with self.assertRaises(Hold):self.provider.request(self.g,'CANDIDATE','verify_cycle_binding',self.cycle_payload)
        self.change=self.cycle_host
        with self.assertRaises(Hold):self.provider.request(self.g,'CANDIDATE','verify_cycle_binding',self.cycle_payload)
        self.assertEqual(self.store.db.execute('SELECT stopped FROM cycles').fetchone()[0],1)
    def test_source_changed_cycle_cannot_bypass_stop_via_raw_consume(self):
        self.cycle_payload=self.cycle_registration()
        self.change=lambda receipt:receipt['result'].update(status='UNCHANGED',binding=self.cycle_payload,source_identity={})
        with self.assertRaises(Hold):self.provider.request(self.g,'CANDIDATE','verify_cycle_binding',self.cycle_payload)
        with self.assertRaises(Hold):self.consume()
        self.assertEqual(self.store.db.execute('SELECT consumed FROM grants').fetchone()[0],0)
    def test_cycle_configuration_not_in_first_scope_denied(self):
        payload=self.cycle_registration();self.consume();payload['action']={'id':'unapproved'}
        with self.assertRaises(Hold):self.provider.request(self.g,'attempt1','apply_approved_configuration',payload)
    def test_cycle_unknown_holds_without_revoking_permit(self):
        self.cycle_payload=self.cycle_registration()
        self.change=lambda receipt:receipt['result'].update(status='UNKNOWN')
        with self.assertRaises(Hold):self.provider.request(self.g,'CANDIDATE','verify_cycle_binding',self.cycle_payload)
        self.change=self.cycle_host
        self.assertEqual(self.provider.request(self.g,'CANDIDATE','verify_cycle_binding',self.cycle_payload)['status'],'UNCHANGED')
    def reconciliation_receipt(self,receipt):
        operation=receipt['operation']
        outcome='SUCCESS' if operation=='verify_terminal' else 'NO_WRITE'
        receipt['result'].update(status='SUCCESS' if outcome=='SUCCESS' else 'RECONCILED',
            proof={'outcome':outcome,'evidence_sha256':'a'*64,'checkpoint_sha256':'b'*64,'log_sha256':'c'*64})
    def test_reconcile_no_write_lost_ack_retries_same_transaction(self):
        self.consume();self.change=self.reconciliation_receipt
        one=self.provider.request(self.g,'attempt1','reconcile_unadmitted',{})
        two=self.provider.request(self.g,'attempt1','reconcile_unadmitted',{})
        self.assertEqual(one,two)
        self.assertEqual(self.store.db.execute('SELECT consumed FROM grants').fetchone()[0],1)
    def test_terminal_readback_fresh_nonce_no_new_execution_lease(self):
        self.consume();self.change=self.reconciliation_receipt
        self.provider.request(self.g,'attempt1','verify_terminal',{'outer_sha256':'d'*64})
        leases=self.store.db.execute("SELECT count(*) FROM audit WHERE event='LEASE'").fetchone()[0]
        for unused in range(2):
            value=self.provider.request(self.g,'attempt1','read_committed_outcome',{'outer_sha256':'d'*64})
            self.assertEqual(value['committed']['outcome'],'SUCCESS')
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM audit WHERE event='LEASE'").fetchone()[0],leases)
        import json
        bodies=[json.loads(row[0])['signed_body'] for row in self.store.db.execute("SELECT body FROM audit WHERE event='SIGNED_RECEIPT' ORDER BY id DESC LIMIT 2")]
        self.assertNotEqual(bodies[0]['request_sha256'],bodies[1]['request_sha256'])
        with self.assertRaises(Hold):self.consume()
    def test_committed_outcome_unclaimed_or_wrong_identity_refused(self):
        self.consume()
        with self.assertRaises(Hold):self.provider.request(self.g,'other','read_committed_outcome',{})
        self.principal['actor_id']='OTHER'
        with self.assertRaises(Hold):self.provider.request(self.g,'attempt1','read_committed_outcome',{})
    def test_conflicting_committed_proof_replay_holds(self):
        self.consume();self.change=self.reconciliation_receipt
        self.provider.request(self.g,'attempt1','reconcile_unadmitted',{})
        def changed(receipt):
            self.reconciliation_receipt(receipt);receipt['result']['proof']['evidence_sha256']='f'*64
        self.change=changed
        with self.assertRaises(Hold):self.provider.request(self.g,'attempt1','reconcile_unadmitted',{})
    def test_reconciled_attempt_cannot_replay_execution_fence(self):
        self.consume();self.change=self.reconciliation_receipt
        self.provider.request(self.g,'attempt1','reconcile_unadmitted',{})
        for step in ('START','BEFORE_stage_exact_release','NATIVE_EFFECT'):
            with self.assertRaises(Hold):self.provider.request(self.g,'attempt1','verify_fence',{'step':step})
    def test_reconciled_attempt_read_only_recovery_fence_allowed(self):
        self.consume();self.change=self.reconciliation_receipt
        self.provider.request(self.g,'attempt1','reconcile_unadmitted',{})
        self.assertEqual(self.provider.request(self.g,'attempt1','verify_fence',{'step':'RECONCILE_UNADMITTED'})['status'],'HELD')
if __name__=='__main__':unittest.main()
