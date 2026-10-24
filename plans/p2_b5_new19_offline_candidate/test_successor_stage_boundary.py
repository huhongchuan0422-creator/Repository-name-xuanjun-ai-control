import contextlib
import json
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT/'reused-6825'),
              str(ROOT/'new19-source'),str(ROOT/'successor_controller')]

import pr17_b5_successor_review as transaction
import pr17_b5_successor_binder as binder
from pr17_b5_successor_backend import R2HostBackend
from pr17_b5_successor_authority import ExistingRequestAuthority
from pr17_b5_successor_runtime import attachment_for_prepared


class StageBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.spec=binder.verify_spec_bytes((ROOT/'SUCCESSOR_SPEC.json').read_bytes())
        self.bundle={'files':{x:b'' for x in transaction.CONFIGS+transaction.SLOTS},
                     'catalog_sha':'a'*64,
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

    def test_first_close_stop_unknown_enters_two_service_fail_closed(self):
        calls=[]
        class Legacy:
            def command(self,argv,*args):
                calls.append(tuple(argv))
                if argv[1]=='stop' and argv[-1]=='xuanjun-cloud-connection.service' and len(calls)==1:
                    raise RuntimeError('stop effect unknown')
                return 0
        backend=R2HostBackend(legacy_io=Legacy(),spec=self.spec,
                              source_blobs={},observed_bytes={})
        backend.job=self.spec['fixed_paths']['job_proposed']
        backend._receipt=lambda name,*args:{'approved':True,'job':backend.job}
        with self.assertRaisesRegex(RuntimeError,'stop effect unknown'):
            backend.close_b5_exposure_success_c53_only()
        self.assertIn(('/usr/bin/systemctl','stop',
                       'xuanjun-cloud-connection.service'),calls[1:])
        self.assertIn(('/usr/bin/systemctl','stop',
                       'xuanjun-cloud-oauth-resource.service'),calls[1:])
        self.assertNotEqual(getattr(backend,'stop_outcome',{}).get('state'),
                            'ALL_STOPPED')

    def test_prestart_restore_branch_requires_scoped_action(self):
        effects=[]
        class Backend:
            def checkpoint(self,phase):effects.append(('checkpoint',phase))
            def canonical_state_unknown(self):return False
            def prove_no_new_operations_canonically(self):return True
            @contextlib.contextmanager
            def successor_evidence_action(self,kind):
                self.kind=kind;yield
            def restore_exact_backups_pre_start_only(self,changed,spec):
                effects.append(('restore',self.kind,tuple(changed)));return True
        backend=Backend()
        candidate=transaction.Transaction(self.spec,self.bundle,backend)
        candidate.stage='BACKUP';candidate.backup_done=True
        candidate.worker_start_attempted=False;candidate.worker_stop_attempted=True
        candidate.changed=['/etc/xuanjun-cloud-executor/connection.json']
        candidate.fail_closed()
        self.assertIn(('restore','PRE_START_RESTORE',
                       ('/etc/xuanjun-cloud-executor/connection.json',)),effects)

    def test_successor_factory_type_and_close_sources_fail_closed(self):
        candidate=transaction.Transaction(self.spec,self.bundle,self.backend)
        self.backend.authority=object.__new__(ExistingRequestAuthority)
        self.backend.authority.original=object()
        self.assertTrue(callable(attachment_for_prepared(candidate)))
        self.backend.bundle=self.bundle
        self.backend.authority.catalog_sha='a'*64
        self.backend.authority.request_ids=tuple(
            self.spec['batch']['draft_request_ids'])
        proof={'state':'B5_HTTP_BYTES_VALIDATED_SOURCE_ATTESTATION_PENDING',
               'bytes':93592,'objects':19,'close_approval':'NOT_PROVEN',
               'proof_sha256':'b'*64}
        with self.assertRaisesRegex(transaction.Hold,
                                    'B5_ORIGINAL_TOOL_PROVENANCE_SOURCE_UNKNOWN'):
            self.backend.verify_b5_http_provenance(proof,self.bundle,self.spec)
        with self.assertRaisesRegex(transaction.Hold,
                                    'C53_CLOSE_APPROVAL_SOURCE_UNKNOWN'):
            self.backend.approve_precise_b5_exposure_close(self.bundle,self.spec)
        self.assertTrue(callable(self.backend.close_b5_exposure_success_successor_only))


if __name__=='__main__':
    unittest.main()
