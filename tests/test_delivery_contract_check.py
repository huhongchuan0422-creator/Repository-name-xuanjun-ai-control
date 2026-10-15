import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('delivery', Path(__file__).parents[1] / 'scripts/delivery_contract_check.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.raw = b'rules fixture'
        self.head = 'a' * 40
        self.value = dict(rules_version=m.VERSION, rules_sha256=hashlib.sha256(self.raw).hexdigest(),
            head_sha=self.head, task='#17', batch='complete governance batch', developer='WORK',
            changed_files=['scripts/check.py'], nodes=[dict(id='gate', state='DONE', criteria=['reject stale HEAD'],
            evidence=['local negative test'], blocker=None, owner=None, next_action=None, next_check=None)],
            coverage={k: dict(state='NOT_APPLICABLE', evidence=['pure metadata validation; no host effects']) for k in m.COVERAGE},
            wiring_evidence=['workflow invokes validator'], continuation=dict(eligible_remaining=[], next_action='independent review'))

    def run_value(self, value=None, suffix=''):
        body = '```xj-delivery\n' + json.dumps(value or self.value) + '\n```\n' + suffix
        return m.validate(body, self.head, ['scripts/check.py'], self.raw)

    def test_valid_metadata_grants_no_authority(self):
        self.assertEqual(self.run_value()['authority_effect'], 'NONE')

    def test_blocking_mutations(self):
        cases = []
        def add(fn):
            v = copy.deepcopy(self.value); fn(v); cases.append(v)
        add(lambda v: v.update(head_sha='b' * 40))
        add(lambda v: v.update(rules_version='old'))
        add(lambda v: v.update(rules_sha256='0' * 64))
        add(lambda v: v.update(changed_files=[]))
        add(lambda v: v['nodes'][0].update(state='RUNNING'))
        add(lambda v: v['nodes'][0].update(evidence=[]))
        add(lambda v: v['nodes'][0].update(state='EXTERNAL_BLOCKED'))
        add(lambda v: v['nodes'].append(copy.deepcopy(v['nodes'][0])))
        add(lambda v: v['coverage'].pop('partial_unknown'))
        add(lambda v: v['coverage']['transaction_cleanup'].update(state='SKIPPED'))
        add(lambda v: v.update(wiring_evidence=[]))
        add(lambda v: v['continuation'].update(eligible_remaining=['unfinished']))
        add(lambda v: v.update(task='new untracked queue'))
        for v in cases:
            with self.subTest(value=v), self.assertRaises(ValueError): self.run_value(v)

    def test_external_blocker_is_explicit_not_done(self):
        self.value['nodes'][0].update(state='EXTERNAL_BLOCKED', blocker='external service unavailable',
                                     owner='existing executor', next_action='check receipt', next_check='2026-10-16T00:00:00+08:00')
        self.assertEqual(self.run_value()['independent_review'], 'NOT_PROVEN_BY_METADATA')

    def test_missing_and_duplicate_contracts(self):
        with self.assertRaises(ValueError): m.validate('report only', self.head, ['scripts/check.py'], self.raw)
        with self.assertRaises(ValueError): self.run_value(suffix='```xj-delivery\n{}\n```\n')

    def test_duplicate_json_keys(self):
        with self.assertRaises(ValueError): m.strict_json('{"x":1,"x":2}')


if __name__ == '__main__': unittest.main()
