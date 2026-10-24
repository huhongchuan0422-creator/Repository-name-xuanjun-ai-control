"""Offline admission checks; no original service or network operations."""
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent / 'reused-6825'))
sys.path.insert(0, str(pathlib.Path(__file__).parent / 'new19-source'))
import pr17_c53_r2_review_transaction as c53
from pr17_c53_r2_authority_adapter import ExistingRequestAuthority
from pr17_c53_r2_host_backend_candidate import R2HostBackend


class AdmissionTests(unittest.TestCase):
    def test_missing_original_operations_hold_before_any_effect(self):
        authority = ExistingRequestAuthority.__new__(ExistingRequestAuthority)
        backend = R2HostBackend.__new__(R2HostBackend)
        backend.authority = authority
        with self.assertRaisesRegex(c53.Hold,
                                    'ORIGINAL_DEPLOYMENT_COMPOSITION_UNAVAILABLE'):
            backend.preflight_original_capabilities()

    def test_rejected_authority_type_cannot_supply_capability(self):
        backend = R2HostBackend.__new__(R2HostBackend)
        backend.authority = mock.Mock()
        with self.assertRaisesRegex(c53.Hold, 'ORIGINAL_AUTHORITY_TYPE'):
            backend.preflight_original_capabilities()

    def test_transaction_preflight_precedes_reservation_and_stop(self):
        effects = []
        class Backend:
            def get_generator_inputs_verified(self, spec):
                effects.append('read_inputs')
                return {}, {}
            def preflight_original_capabilities(self):
                effects.append('preflight')
                raise c53.Hold('ORIGINAL_ELEVEN_CAPABILITIES_NOT_BOUND')
            def checkpoint(self, phase):
                effects.append('checkpoint')
            def canonical_state_unknown(self):
                return True
            def prove_no_new_operations_canonically(self):
                return False
            def reserve_batch_and_targets(self, *args):
                effects.append('reservation')
            def stop_worker_bounded(self):
                effects.append('stop')
        transaction = c53.Transaction.__new__(c53.Transaction)
        transaction.spec = {}
        transaction.bundle = {}
        transaction.b = Backend()
        transaction.stage = 'NEW'
        transaction.trace = []
        transaction.worker_stop_attempted = False
        transaction.worker_start_attempted = None
        transaction.state_unknown = True
        transaction.locked = False
        transaction.backup_done = False
        transaction.changed = []
        transaction.stop_outcome = {'state': 'NOT_ATTEMPTED'}
        with mock.patch.object(c53, 'validate_bundle'):
            result = transaction.execute()
        self.assertEqual(result['state'], 'HOLD_PRESERVE_HISTORY')
        self.assertEqual(result['phase'], 'NEW')
        self.assertEqual(result['stop_outcome']['state'], 'NOT_ATTEMPTED')
        self.assertEqual(effects[:2], ['read_inputs', 'preflight'])
        self.assertNotIn('reservation', effects)
        self.assertNotIn('stop', effects)

    def test_exact_eleven_names_cover_backend_calls(self):
        self.assertEqual(len(ExistingRequestAuthority.ORIGINAL_REQUIRED), 11)
        # The fixed contract is explicit and contains no old five-attempt gate.
        self.assertEqual(len(set(ExistingRequestAuthority.ORIGINAL_REQUIRED)), 11)
        self.assertIn('read_project_chunk_complete',
                      ExistingRequestAuthority.ORIGINAL_REQUIRED)

    def test_runtime_attachment_missing_holds_before_reservation_and_stop(self):
        effects=[]
        class Backend:
            def get_generator_inputs_verified(self,spec):return {},{}
            def preflight_original_capabilities(self):effects.append('original')
            def preflight_runtime_attachment(self):
                effects.append('runtime');raise c53.Hold('ORIGINAL_RUNTIME_ATTACHMENT_UNAVAILABLE')
            def checkpoint(self,phase):pass
            def canonical_state_unknown(self):return True
            def prove_no_new_operations_canonically(self):return False
            def reserve_batch_and_targets(self,*args):effects.append('reserve')
            def stop_worker_bounded(self):effects.append('stop')
        tx=c53.Transaction.__new__(c53.Transaction)
        tx.spec={};tx.bundle={};tx.b=Backend();tx.stage='NEW';tx.trace=[]
        tx.worker_stop_attempted=False;tx.worker_start_attempted=None
        tx.state_unknown=True;tx.locked=False;tx.backup_done=False
        tx.changed=[];tx.stop_outcome={'state':'NOT_ATTEMPTED'}
        with mock.patch.object(c53,'validate_bundle'):
            result=tx.execute()
        self.assertEqual(result['state'],'HOLD_PRESERVE_HISTORY')
        self.assertEqual(effects,['original','runtime'])

    def test_close_without_precise_source_cannot_stop_worker(self):
        calls=[]
        authority=ExistingRequestAuthority.__new__(ExistingRequestAuthority)
        backend=R2HostBackend.__new__(R2HostBackend)
        backend.authority=authority
        backend.job='/opt/xuanjun-cloud-connection/l2-c53-recovery-once'
        backend.legacy=type('Legacy',(),{'command':lambda *a:calls.append(a)})()
        with self.assertRaisesRegex(c53.Hold,'C53_CLOSE_APPROVAL_SOURCE_UNKNOWN'):
            backend.close_b5_exposure_success_c53_only()
        self.assertEqual(calls,[])


if __name__ == '__main__':
    unittest.main()
