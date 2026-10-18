"""Independent offline signature-scope regressions; ephemeral test keys only."""
import copy
import json
import unittest
from scripts import pr122_customer_review as review
from scripts import pr122_customer_workflow as workflow
from scripts.pr122_customer_core import Denied, canonical, digest
from tests import test_pr122_customer_revision as fixtures

class WholeWorkflowSignatureTests(unittest.TestCase):
    setUp = fixtures.ReviewTests.setUp
    prepare = fixtures.ReviewTests.prepare
    fetch = fixtures.ReviewTests.fetch
    def gate(self):
        # Filesystem custody is an existing separate gate; this fixture exercises
        # the real signed-review/Owner-comment/CI checks with an in-memory trust.
        from unittest.mock import patch
        with patch.object(fixtures.release, 'private_config', lambda path: copy.deepcopy(self.trust)):
            return fixtures.ReviewTests.gate(self)

    def whole(self, signed=True):
        self.plan['workflow_contract'] = {'schema': 1, 'stages': [
            {'stage': s, 'input_sha256': digest(s.encode()),
             'implementation_sha256': digest((s+'-impl').encode()),
             'adopt_receipt_sha256': None, 'recovery_actions': sorted(workflow.RECOVERY[s])}
            for s in workflow.STAGES]}
        self.approval.update(attempt_policy=workflow.POLICY, max_executions=5,
                             workflow_contract_sha256=digest(canonical(self.plan['workflow_contract'])))
        if signed:
            self.payload['workflow_contract_sha256'] = self.approval['workflow_contract_sha256']

    def test_old_apply_signature_rejected_for_whole_scope(self):
        self.whole(signed=False); self.prepare()
        with self.assertRaisesRegex(Denied, 'REVIEW_PAYLOAD_SCHEMA'): self.gate()

    def test_exact_whole_contract_signature_passes_original_gate(self):
        self.whole(); self.prepare()
        self.assertEqual(self.gate()['workflow_contract_sha256'], self.payload['workflow_contract_sha256'])

    def test_changed_stage_input_rejected_without_new_independent_signature(self):
        self.whole()
        self.plan['workflow_contract']['stages'][1]['input_sha256'] = 'e'*64
        self.approval['workflow_contract_sha256'] = digest(canonical(self.plan['workflow_contract']))
        self.prepare()
        with self.assertRaisesRegex(Denied, 'EXACT_INDEPENDENT_WORKFLOW_SCOPE'): self.gate()

    def test_changed_recovery_scope_rejected_without_new_independent_signature(self):
        self.whole()
        self.plan['workflow_contract']['stages'][5]['recovery_actions'] = ['RECONCILE_CUSTOMER']
        self.approval['workflow_contract_sha256'] = digest(canonical(self.plan['workflow_contract']))
        self.prepare()
        with self.assertRaisesRegex(Denied, 'EXACT_INDEPENDENT_WORKFLOW_SCOPE'): self.gate()

    def test_changed_stage_order_rejected_by_independent_signature(self):
        self.whole(); self.plan['workflow_contract']['stages'].reverse()
        self.approval['workflow_contract_sha256'] = digest(canonical(self.plan['workflow_contract']))
        self.prepare()
        with self.assertRaisesRegex(Denied, 'EXACT_INDEPENDENT_WORKFLOW_SCOPE'): self.gate()

    def test_updated_digest_without_resigning_rejected(self):
        self.whole(); self.prepare()
        self.plan['workflow_contract']['stages'][1]['input_sha256'] = 'e'*64
        self.approval['workflow_contract_sha256'] = digest(canonical(self.plan['workflow_contract']))
        self.approval['plan_sha256'] = digest(canonical(self.plan))
        envelope = json.loads(self.comments[5]['body'].split('\n',1)[1])
        envelope['payload']['workflow_contract_sha256'] = self.approval['workflow_contract_sha256']
        self.comments[5]['body'] = 'XUANJUN_CUSTOMER_REVIEW_V2\n'+json.dumps(envelope)
        self.comments[4]['body'] = 'XUANJUN_CUSTOMER_INSTALL\n'+json.dumps(self.approval)
        anchor=self.trust['install_anchors'][self.approval['transaction']]
        anchor.update(install_body_sha256=digest(self.comments[4]['body'].encode()),
                      review_body_sha256=digest(self.comments[5]['body'].encode()))
        (self.root/'INDEPENDENT_REVIEW_TRUST.json').write_bytes(canonical(self.trust))
        with self.assertRaisesRegex(Denied,'INDEPENDENT_REVIEW_SIGNATURE'): self.gate()

    def test_original_single_attempt_payload_remains_valid(self):
        self.prepare(); self.assertEqual(self.gate()['max_executions'],1)

    def test_original_v2_payload_remains_valid(self):
        self.approval.update(attempt_policy='CONTROLLED_INSTALL_RESUME_V2',max_executions=5,
                             recovery_actions=['RECONCILE_OWNED_CHECKPOINTS'])
        self.prepare(); self.assertEqual(self.gate()['max_executions'],5)

if __name__ == '__main__': unittest.main()
