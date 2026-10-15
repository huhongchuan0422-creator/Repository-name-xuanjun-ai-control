import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import trusted_delivery_gate as gate
import test_delivery_contract_check as fixture_module


class TrustedGateTests(unittest.TestCase):
    def setUp(self):
        fixture = fixture_module.DeliveryTests(); fixture.setUp()
        self.fixture = fixture
        self.pr = dict(number=123, head=dict(sha=fixture.head),
            base=dict(ref='main', sha='b' * 40, repo=dict(full_name=gate.REPOSITORY)),
            changed_files=1, body='```xj-delivery\n' + json.dumps(fixture.value) + '\n```\n')
        self.event = dict(repository=dict(full_name=gate.REPOSITORY, default_branch='main'),
                          pull_request=dict(number=123, head=dict(sha=fixture.head)))
        self.rows = [dict(filename='scripts/check.py', status='added')]
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        rules = self.root / gate.RULES; rules.parent.mkdir(parents=True)
        rules.write_bytes(fixture.raw)

    def check(self, rows=None):
        return gate.evaluate(self.root, self.event, self.pr, self.rows if rows is None else rows, 'c' * 40)

    def test_trusted_baseline_accepts_only_metadata_no_authority(self):
        result = self.check()
        self.assertEqual(result['trusted_source_sha'], 'c' * 40)
        self.assertEqual(result['authority_effect'], 'NONE')

    def test_all_workflow_forgeries_and_root_changes_are_held(self):
        for path in list(gate.PROTECTED) + ['.github/workflows/forged-same-job.yml', '.github/workflows/delivery-contract.yml']:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'TRUST_ROOT'):
                self.check([dict(filename=path, status='modified')])

    def test_renamed_trust_root_cannot_hide_behind_new_filename(self):
        with self.assertRaisesRegex(ValueError, 'TRUST_ROOT'):
            self.check([dict(filename='scripts/innocent.py', status='renamed', previous_filename='scripts/trusted_delivery_gate.py')])

    def test_pr_rule_hash_cannot_select_pr_rules(self):
        self.fixture.value['rules_sha256'] = 'd' * 64
        self.pr['body'] = '```xj-delivery\n' + json.dumps(self.fixture.value) + '\n```\n'
        with self.assertRaisesRegex(ValueError, 'RULE_HASH'):
            self.check()

    def test_missing_extra_duplicate_or_racing_inventory_rejected(self):
        self.pr['changed_files'] = 2
        with self.assertRaisesRegex(ValueError, 'COMPLETE_FILES'): self.check()
        with self.assertRaisesRegex(ValueError, 'UNIQUE_FILES'): self.check(self.rows * 2)
        self.pr['changed_files'] = 1
        self.pr['head']['sha'] = 'e' * 40
        with self.assertRaisesRegex(ValueError, 'CURRENT_PR_HEAD'): self.check()

    def test_pr_code_is_never_loaded(self):
        # Data-only evaluator has no candidate-root argument or code loader.
        script = self.root / 'scripts/check.py'; script.parent.mkdir()
        script.write_text('raise AssertionError("UNTRUSTED_PR_EXECUTED")')
        self.check()
        self.pr['body'] = 'invalid contract'
        with self.assertRaisesRegex(ValueError, 'ONE_DELIVERY'): self.check()

    def test_authority_workflow_has_no_pr_checkout_or_candidate_execution(self):
        raw = (ROOT / '.github/workflows/delivery-contract.yml').read_text()
        self.assertIn('pull_request_target:', raw)
        self.assertIn('ref: ${{ github.sha }}', raw)
        for forbidden in ('pull_request.head.sha', 'refs/pull/', 'unittest', 'workflow_run:', 'secrets.', 'write', 'upload-artifact'):
            self.assertNotIn(forbidden, raw)
        self.assertIn('delivery-contract-candidate:', (ROOT / '.github/workflows/delivery-contract-candidate.yml').read_text())


if __name__ == '__main__': unittest.main()
