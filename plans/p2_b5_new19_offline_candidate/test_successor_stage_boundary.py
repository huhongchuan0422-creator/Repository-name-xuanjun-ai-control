import json
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT/'reused-6825'),str(ROOT/'successor_controller')]

import pr17_b5_successor_review as transaction
import pr17_b5_successor_binder as binder
from pr17_b5_successor_backend import R2HostBackend


class StageBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.spec=binder.verify_spec_bytes((ROOT/'SUCCESSOR_SPEC.json').read_bytes())
        self.bundle={'files':{x:b'' for x in transaction.CONFIGS+transaction.SLOTS},
                     'requests':[{'request_id':r} for r in
                                 self.spec['batch']['draft_request_ids']]}
        self.backend=R2HostBackend(legacy_io=object(),spec=self.spec,
                                   source_blobs={},observed_bytes={})

    def test_old_maintenance_body_entry_refuses_before_any_read(self):
        called=[]
        self.backend.read_original_project_body=lambda *args:called.append(args)
        candidate=transaction.Transaction(self.spec,self.bundle,self.backend)
        candidate.stage='READY_FOR_B5_HTTP_NOT_RECEIVED'
        with self.assertRaisesRegex(transaction.Hold,'B5_HTTP_REQUEST_LOCAL_ONLY'):
            candidate.receive_and_verify_19()
        self.assertEqual(called,[])

    def test_close_requires_provenance_before_approval_or_effect(self):
        candidate=transaction.Transaction(self.spec,self.bundle,self.backend)
        candidate.stage='READY_FOR_B5_HTTP_NOT_RECEIVED'
        effects=[]
        self.backend.approve_precise_b5_exposure_close=lambda *args:effects.append('approve')
        self.backend.close_b5_exposure_success_successor_only=lambda:effects.append('close')
        with self.assertRaisesRegex(transaction.Hold,'B5_HTTP_PROOF_BOUNDARY'):
            candidate.close_after_b5_http({'sha256':'not-an-attestation'})
        self.assertEqual(effects,[])

    def test_window_maintenance_gate_does_not_borrow_http_files_grant(self):
        now=int(time.time())
        bundle={'window_start':now-1,'window_end':now+60}
        self.backend.activation_committed=True
        self.backend.bundle=bundle
        called=[]
        self.backend.verify_activation_admission=lambda *args:called.append('owner')
        self.backend.verify_analyst_ack=lambda *args:called.append('ack')
        class Original:
            def preflight(self):called.append('provider')
        class Authority:
            def _bound_original(self,active=False):
                called.append(('runtime',active));return Original()
        self.backend.authority=Authority()
        self.backend.verify_post_activation_b5_read_admission=(
            lambda *args:self.fail('HTTP files grant borrowed into maintenance'))
        self.backend.verify_window_admission(bundle,self.spec)
        self.assertEqual(called,['owner','ack',('runtime',False),'provider'])


if __name__=='__main__':
    unittest.main()
