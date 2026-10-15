"""Synthetic transition regressions; actual UK journal-body validation NOT_RUN.

Hash mapping is scoped to fixtures, never a production option or mocked PASS.
"""
import copy
import pathlib
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent), str(HERE.parent.parent / 'recovery-design-candidate')]
import test_snapshot as f
import epoch7_snapshot as c
import epoch7_delta as d


class NativeTransitionTests(unittest.TestCase):
    def setUp(self):
        self.raws = f.native_transition_fixture()
        self.pins = f.native_pin_context(self.raws); self.pins.start()
    def tearDown(self): self.pins.stop()
    def check(self, raws=None): return c.validate_native_transition(*(self.raws if raws is None else raws))
    def changed_attempt(self, change):
        values = list(self.raws); attempt = c.decode(values[3]); change(attempt); values[3] = f.packed(attempt)
        # Exercise semantic validation past the immutable production hash gate.
        with mock.patch.object(c, 'NATIVE_ATTEMPT_SHA', c.sha(values[3])):
            return self.check(values)
    def test_exact_completed_transition_and_projection(self):
        proof = self.check()
        self.assertEqual(set(proof), {'schema','kind','phase','approval_id','attempt_sha256','original_sha256',
            'before_sha256','after_sha256','before_release_sha256','after_release_sha256','original_preserved'})
        self.assertEqual(proof['before_sha256'], c.sha(self.raws[1]))
        self.assertEqual(proof['after_sha256'], c.sha(self.raws[0]))
        self.assertNotEqual(proof['before_sha256'], proof['after_sha256'])
        self.assertEqual(c.validate_native_transition_evidence(proof,self.raws[0]),proof)
        self.assertNotIn('gatewayIdentity',str(proof))
    def test_original_identity_and_historical_client_hash_preserved(self):
        original = c.decode(self.raws[2]); current = c.decode(self.raws[0])
        self.check(); self.assertEqual(original['gatewayIdentity'],current['gatewayIdentity'])
        for key in ('python','pythonSha256','config'):
            self.assertEqual(original['ledger'][key],current['ledger'][key])
        client=original['ledger']['config']
        self.assertEqual(original['ledger']['files'][client],current['ledger']['files'][client])
    def test_missing_oversized_or_nonbytes_buffer_refused(self):
        for index in range(4):
            for bad in (b'', None, '{}', b'x'*(1048577 if index==3 else 65537)):
                values=list(self.raws);values[index]=bad
                with self.assertRaises(ValueError):self.check(values)
    def test_preserved_and_original_bytes_are_immutable(self):
        for index in (1,2):
            values=list(self.raws);values[index]+=b' '
            with self.assertRaisesRegex(ValueError,'PRESERVED_BEFORE'):self.check(values)
    def test_owned_attempt_bytes_are_immutable(self):
        values=list(self.raws);values[3]+=b' '
        with self.assertRaisesRegex(ValueError,'OWNED_ATTEMPT_PIN'):self.check(values)
    def test_consumed_hold_scope_is_typed(self):
        for key,bad in (('schema',True),('stage','ADMITTED'),('automatic_retry',0),
                        ('historical_replay',None),('legacy_restart',0),('production_acceptance','ACCEPTED')):
            with self.assertRaisesRegex(ValueError,'OWNED_ATTEMPT_SCOPE'):
                self.changed_attempt(lambda a:a.update({key:bad}))
    def test_wrong_review_or_rebound_approval_cannot_authorize(self):
        for bad in (True,6170703285):
            with self.assertRaisesRegex(ValueError,'OWNED_APPROVAL'):
                self.changed_attempt(lambda a:a['authorization'].update(review_id=bad))
        for key,bad in (('expected_epoch',6),('proposed_prepared_epoch',7),('authorized_attempts',True),
                        ('runtime_manifest_sha256','0'*64),('transaction_id','other')):
            with self.assertRaisesRegex(ValueError,'OWNED_APPROVAL_BINDING'):
                self.changed_attempt(lambda a:a['authorization']['approval'].update({key:bad}))
    def test_plan_snapshot_and_kit_hashes_cross_bind(self):
        for key in ('plan_sha256','snapshot_sha256','kit_manifest_sha256'):
            with self.assertRaisesRegex(ValueError,'OWNED_APPROVAL_HASH_BINDING'):
                self.changed_attempt(lambda a:a.update({key:'0'*64}))
    def test_incomplete_reordered_duplicate_or_unknown_phase_refused(self):
        bad_lists = [list(c.NATIVE_PHASES[:2]), list(c.NATIVE_PHASES[1:5]),
                     [c.NATIVE_PHASES[0]]*5, list(c.NATIVE_PHASES[:3])+['unknown']]
        for completed in bad_lists:
            with self.assertRaisesRegex(ValueError,'OWNED_PHASE_ORDER'):
                self.changed_attempt(lambda a:a.update(completed=completed))
    def test_missing_extra_or_empty_phase_evidence_refused(self):
        for mutation in ('missing','extra','empty'):
            def change(a):
                if mutation=='missing':a['phase_evidence'].pop('rebind_prepared_epoch')
                elif mutation=='extra':a['phase_evidence']['unknown']={'fixture':True}
                else:a['phase_evidence']['rebind_prepared_epoch']={}
            with self.assertRaisesRegex(ValueError,'OWNED_PHASE_ORDER'):self.changed_attempt(change)
    def test_rebind_epoch_and_exact_result_keys(self):
        for mutation in ('epoch','key'):
            def change(a):
                row=a['phase_evidence']['rebind_prepared_epoch']
                if mutation=='epoch':row['epoch']=True
                else:row['unknown']=True
            with self.assertRaisesRegex(ValueError,'NATIVE_REBIND_'):self.changed_attempt(change)
    def test_native_old_new_and_preservation_are_exact_typed(self):
        for key,bad in (('old_sha256','0'*64),('new_sha256','0'*64),('original_preserved',1)):
            def change(a):a['phase_evidence']['rebind_prepared_epoch']['native_binding'][key]=bad
            with self.assertRaisesRegex(ValueError,'OWNED_REBIND_HASHES'):self.changed_attempt(change)
    def test_completed_rebind_cannot_leave_historical_live_bytes(self):
        values=list(self.raws);values[0]=values[1]
        with self.assertRaisesRegex(ValueError,'OWNED_REBIND_HASHES'):self.check(values)
    def test_self_consistent_new_hash_cannot_change_identity_or_client(self):
        for field in ('gateway','python','client','bridge'):
            values=list(self.raws);value=c.decode(values[0]);ledger=value['ledger']
            if field=='gateway':value['gatewayIdentity']['sha256']='0'*64
            elif field=='python':ledger['pythonSha256']='0'*64
            elif field=='client':ledger['files'][ledger['config']]='0'*64
            else:ledger['files'][ledger['bridge']]='0'*64
            values[0]=f.packed(value);attempt=c.decode(values[3])
            attempt['phase_evidence']['rebind_prepared_epoch']['native_binding']['new_sha256']=c.sha(values[0])
            values[3]=f.packed(attempt)
            with mock.patch.object(c,'NATIVE_CURRENT_SHA',c.sha(values[0])), mock.patch.object(c,'NATIVE_ATTEMPT_SHA',c.sha(values[3])):
                with self.assertRaisesRegex(ValueError,'EXACT_COMPLETED_TRANSFORM'):self.check(values)
    def test_noncanonical_after_bytes_cannot_be_relabelled(self):
        values=list(self.raws);values[0]+=b' ';attempt=c.decode(values[3])
        attempt['phase_evidence']['rebind_prepared_epoch']['native_binding']['new_sha256']=c.sha(values[0])
        values[3]=f.packed(attempt)
        with mock.patch.object(c,'NATIVE_CURRENT_SHA',c.sha(values[0])),mock.patch.object(c,'NATIVE_ATTEMPT_SHA',c.sha(values[3])):
            with self.assertRaisesRegex(ValueError,'EXACT_COMPLETED_TRANSFORM'):self.check(values)
    def test_projection_rejects_caller_flags_unknown_fields_and_changed_pins(self):
        for key,bad in (('schema',True),('approval_id',True),('original_preserved',1),
                        ('before_sha256','0'*64),('after_sha256','0'*64),('attempt_sha256','0'*64),('unknown',True)):
            proof=self.check();proof[key]=bad
            with self.assertRaisesRegex(ValueError,'TRANSITION_EVIDENCE'):
                c.validate_native_transition_evidence(proof,self.raws[0])
    def test_projection_checks_current_bytes_and_reverse_historical_identity(self):
        proof=self.check()
        with self.assertRaisesRegex(ValueError,'CURRENT_EXACT_BYTES'):
            c.validate_native_transition_evidence(proof,self.raws[1])
        with mock.patch.object(c,'RETAINED_NATIVE_SHA','0'*64):
            proof['before_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'HISTORICAL_REVERSE_TRANSFORM'):
                c.validate_native_transition_evidence(proof,self.raws[0])


class FixedProductionPinsTests(unittest.TestCase):
    def test_reported_pins_are_distinct_and_synthetic_bytes_never_pass_unmapped(self):
        self.assertEqual(c.NATIVE_CURRENT_SHA,'c0766fd42f0f4ab25bffa03bb6620910e9d1cd5c6a90315d94a922b5cdf6dd7a')
        self.assertEqual(c.NATIVE_ATTEMPT_SHA,'4eb5090ee3f094ae73116bf59412756681641be3df613cad183d8f7b06597e3a')
        self.assertEqual(c.RETAINED_NATIVE_SHA,'91c65c9fbc5c2cf68648672b4c096d7df376ecfbc605bc4cc838300bd302f629')
        with self.assertRaises(ValueError):c.validate_native_transition(*f.native_transition_fixture())


if __name__ == '__main__':unittest.main()
