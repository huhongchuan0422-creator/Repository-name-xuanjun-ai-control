"""Pure protected-context preflight checks; no configuration or server access."""
import copy
import unittest
from scripts.pr122_customer_core import Denied
from scripts.pr122_customer_ops import validate_runtime_contexts, backup
from scripts.pr122_customer_privacy import submit_request
from tests import test_pr122_customer_center as fixture

class ContextConfigTests(unittest.TestCase):
    def test_absent_and_exact_optional_maps(self):
        base={'keys':{},'active_key':'fixture','providers':{}}
        self.assertTrue(validate_runtime_contexts(base,base))
        configured={**base,'message_evidence_context':{'project-a':{'user-a':{'module_id':'module-a'}}},
                    'privacy_policy_context':{'project-a':{'notice_ref':'notice-v1'}},
                    'privacy_processing_context':{'project-a':{'user-a':{'request-a':{'status':'RECEIVED','revision':1}}}}}
        self.assertTrue(validate_runtime_contexts(configured,copy.deepcopy(configured)))

    def test_mismatch_unknown_fields_and_invalid_mapping_fail_closed(self):
        base={'keys':{},'active_key':'fixture','providers':{}}
        attacks=[{'extra_key':{}},{'privacy_policy_context':[]},
                 {'privacy_policy_context':{'project-a':{'arbitrary':True}}},
                 {'message_evidence_context':{'project-a':{'user-a':[]}}},
                 {'privacy_processing_context':{'project-a':{'user-a':{'request-a':{'status':{}}}}}},
                 {'privacy_policy_context':{'bad key':{}}}]
        for attack in attacks:
            with self.subTest(attack=attack),self.assertRaises(Denied):validate_runtime_contexts({**base,**attack},{**base,**attack})
        protected={**base,'privacy_policy_context':{'project-a':{'notice_ref':'notice-v1'}}}
        with self.assertRaisesRegex(Denied,'BINDING'):validate_runtime_contexts(protected,base)
        with self.assertRaisesRegex(Denied,'MINIMUM'):validate_runtime_contexts(base,{'keys':{}})

class PrivacyBackupTests(unittest.TestCase):
    imported=fixture.CustomerTests.imported
    def setUp(self):fixture.CustomerTests.setUp(self)
    def test_corrupt_privacy_receipt_blocks_integrity_and_backup(self):
        submit_request(self.c,self.owner,'project-a','QUERY','Synthetic query',idempotency_key='backup_test_key_001')
        self.c.check_integrity()
        self.c.db.execute('DROP TRIGGER privacy_no_update')
        self.c.db.execute("UPDATE privacy_receipts SET sha=?",('f'*64,))
        with self.assertRaisesRegex(Denied,'PRIVACY_HISTORY_INTEGRITY'):self.c.check_integrity()
        output=self.root/'rejected-backup'
        with self.assertRaisesRegex(Denied,'PRIVACY_HISTORY_INTEGRITY'):backup(self.c,output,b'b'*32,'fixture-key-ref')
        self.assertFalse(output.exists())

    def test_isolated_restore_records_unknown_without_resending(self):
        from scripts.pr122_customer_core import Center
        from scripts.pr122_customer_ops import restore
        from scripts.pr122_customer_providers import enqueue, drain_message
        from scripts.pr122_customer_activity_evidence import verify
        from unittest.mock import Mock
        challenge=self.c.binding_challenge(self.owner,'project-a','TELEGRAM','123')['challenge']
        self.c.channel_event('TELEGRAM','restore_bind','123','/bind '+challenge)
        self.c.confirm_link(self.owner,'project-a',self.c.pending_links(self.owner,'project-a')[0]['id'])
        message=enqueue(self.c,self.owner,'project-a','TELEGRAM','Synthetic outbound')
        output=self.root/'backup.enc';backup(self.c,output,b'b'*32,'fixture-key-ref')
        target=self.root/'isolated';restore(output,target,b'b'*32,{'v1':self.key},'v1')
        restored=Center(target,{'v1':self.key},'v1',clock=lambda:self.now);self.addCleanup(restored.db.close)
        records,_=verify(restored)
        outcomes=[p['delivery_status'] for p,v in records if p['source_kind']=='DELIVERY' and p['source_id']==message['id']]
        self.assertEqual(outcomes,['PENDING','UNKNOWN'])
        self.assertEqual(restored.db.execute("SELECT v FROM settings WHERE k='maintenance'").fetchone()[0],'1')
        self.assertEqual(restored.db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
        provider=Mock();self.assertEqual(drain_message(restored,provider),{'pending':False});provider.send.assert_not_called()
        restored.check_integrity()
