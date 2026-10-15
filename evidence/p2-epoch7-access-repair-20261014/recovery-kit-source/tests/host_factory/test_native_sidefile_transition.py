"""Public retained-native compiler tests; no private plan or host operations.

Uses the actual whole-factory public fixture and central transition validator.
Only its four explicitly synthetic private byte pins are mapped in test scope.
"""
import copy
import unittest

import epoch7_bindings as bindings
import epoch7_host_factory as factory
import epoch7_snapshot as snapshot
from test_epoch7_full_factory_fixture import make_seed,native_pins,native_fixture_raws


class NativeSidefileTransitionTests(unittest.TestCase):
    def setUp(self):
        self.seed=make_seed();self.compiled=factory.compiled_bytes(self.seed['compiled'])
        self.raw=self.seed['native_before'];self.before=bindings.parse(self.raw)
        self.proof=copy.deepcopy(self.seed['observation']['evidence']['retained']['native_binding_transition'])
        ledger=self.before['ledger'];self.bridge_pin=ledger['files'][ledger['bridge']]
        self.client_pin=ledger['files'][ledger['config']]
    def call(self,raw=None,proof=None,bridge_pin=None):
        return bindings.native_sidefile_delta(self.raw if raw is None else raw,self.compiled,
            self.bridge_pin if bridge_pin is None else bridge_pin,self.client_pin,
            self.proof if proof is None else proof)
    def test_owned_current_moves_to_reviewed_pair_and_preserves_identity(self):
        with native_pins(self.seed):after=bindings.parse(self.call())
        self.assertEqual(after['gatewayIdentity'],self.before['gatewayIdentity'])
        self.assertEqual(after['ledger'],bindings.parse(self.compiled['rendered_targets'][bindings.BINDING])['ledger'])
        self.assertIn(snapshot.d.OLD_MANIFEST[:16],self.before['ledger']['bridge'])
        self.assertEqual(bindings.RETAINED_NATIVE_SHA,'91c65c9fbc5c2cf68648672b4c096d7df376ecfbc605bc4cc838300bd302f629')
    def test_unmapped_private_fixture_is_not_production_evidence(self):
        with self.assertRaisesRegex(ValueError,'NATIVE_TRANSITION_EVIDENCE'):self.call()
    def test_old_bridge_or_client_pin_drift_is_rejected(self):
        with native_pins(self.seed):
            with self.assertRaisesRegex(ValueError,'NATIVE_OLD_FILE_PINS'):self.call(bridge_pin='0'*64)
            self.client_pin='0'*64
            with self.assertRaisesRegex(ValueError,'NATIVE_OLD_FILE_PINS'):self.call()
    def test_compiled_target_or_interpreter_drift_is_rejected(self):
        value=bindings.parse(self.compiled['rendered_targets'][bindings.BINDING])
        value['ledger']['python']='/bin/other';raw=bindings.canonical(value)+b'\n'
        self.compiled['rendered_targets'][bindings.BINDING]=raw
        with native_pins(self.seed):
            with self.assertRaisesRegex(ValueError,'NATIVE_COMPILED_TARGET_DRIFT'):self.call()
            row=next(row for row in self.compiled['runtime']['provisioning'] if row['target']==bindings.BINDING)
            row['rendered_sha256']=bindings.sha(raw)
            with self.assertRaisesRegex(ValueError,'NATIVE_INTERPRETER_CHANGED'):self.call()
    def test_missing_or_forged_transition_cannot_replace_history(self):
        with native_pins(self.seed):
            for key,value in (('approval_id',1),('before_sha256','0'*64),('original_preserved',False),
                              ('after_release_sha256',bindings.RETAINED_NATIVE_RELEASE)):
                proof=copy.deepcopy(self.proof);proof[key]=value
                with self.subTest(key=key),self.assertRaisesRegex(ValueError,'NATIVE_TRANSITION_EVIDENCE'):
                    self.call(proof=proof)
            with self.assertRaisesRegex(ValueError,'NATIVE_TRANSITION_EVIDENCE'):
                bindings.native_sidefile_delta(self.raw,self.compiled,self.bridge_pin,self.client_pin,None)
    def test_prior_reformatted_or_changed_bytes_are_not_current(self):
        prior=native_fixture_raws(self.seed)[1]
        with native_pins(self.seed):
            for raw in (prior,self.raw+b' ',self.raw.replace(b'xuanjun_dev',b'other_user')):
                with self.assertRaisesRegex(ValueError,'NATIVE_CURRENT_EXACT_BYTES'):self.call(raw=raw)


if __name__=='__main__':unittest.main()
