import copy
import hashlib
import json
import unittest

from batch_continuation import BatchHold, run_batch


class Contract:
    STEPS = ('inspect_protected', 'fence_source', 'final_snapshot', 'receive_final')

    @staticmethod
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    @classmethod
    def request(cls, plan, stage, previous):
        return {'operation_id': cls.digest([plan, stage]), 'stage': stage,
                'previous_receipt': previous}

    @staticmethod
    def validate_receipt(receipt, req):
        if (receipt['operation_id'] != req['operation_id']
                or receipt['stage'] != req['stage']
                or receipt['status'] not in ('SUCCEEDED', 'FAILED')):
            raise ValueError('invalid receipt')


class ControllerFixture:
    """Interface fixture only; never presented as production acceptance."""
    m = Contract

    def __init__(self):
        self.plan = {'steps': list(Contract.STEPS)}
        self.claim = {'plan': self.plan, 'plan_digest': Contract.digest(self.plan)}
        self.events = []
        self.executed = []
        self.queried = []

    def load(self):
        return copy.deepcopy(self.claim), copy.deepcopy(self.events), 'unused'

    def perform(self, req, execute, query):
        prior = [e for e in self.events if e.get('request') == req]
        result = [e['receipt'] for e in self.events if e.get('receipt', {}).get('operation_id') == req['operation_id']]
        if result:
            return result[0]
        if prior:
            self.queried.append(req['stage'])
            receipt = query(req)
        else:
            self.events.append({'type': 'INTENT', 'request': req})
            self.executed.append(req['stage'])
            receipt = execute(req)
        self.events.append({'type': 'RESULT', 'receipt': receipt})
        return receipt


def success(req):
    return dict(operation_id=req['operation_id'], stage=req['stage'], status='SUCCEEDED')


class Tests(unittest.TestCase):
    def setUp(self):
        self.c = ControllerFixture()
        self.adapters = {s: success for s in Contract.STEPS}
        self.progress = []

    def run_it(self):
        return run_batch(self.c, self.c.plan, self.adapters, self.adapters, self.progress.append)

    def test_runs_all_remaining_in_order(self):
        self.assertEqual(self.run_it()['status'], 'ORIGINAL_STAGES_COMPLETED')
        self.assertEqual(self.c.executed, list(Contract.STEPS))

    def test_missing_late_adapter_prevents_even_fence(self):
        del self.adapters['receive_final']
        with self.assertRaisesRegex(BatchHold, 'MISSING_REAL_ADAPTERS'):
            self.run_it()
        self.assertEqual(self.c.executed, [])

    def test_failed_stage_does_not_continue_or_rollback(self):
        self.adapters['fence_source'] = lambda req: dict(success(req), status='FAILED')
        with self.assertRaisesRegex(BatchHold, 'STAGE_FAILED'):
            self.run_it()
        self.assertEqual(self.c.executed, ['inspect_protected', 'fence_source'])

    def test_unknown_exception_never_advances(self):
        def unknown(req):
            raise TimeoutError()
        self.adapters['fence_source'] = unknown
        with self.assertRaises(TimeoutError):
            self.run_it()
        self.assertEqual(self.c.executed, ['inspect_protected', 'fence_source'])

    def test_cached_results_not_reexecuted(self):
        self.run_it()
        original = list(self.c.executed)
        self.run_it()
        self.assertEqual(self.c.executed, original)

    def test_prior_intent_queries_then_stops(self):
        req = Contract.request(self.c.plan, Contract.STEPS[0], self.c.claim['plan_digest'])
        self.c.events.append({'type': 'INTENT', 'request': req})
        with self.assertRaisesRegex(BatchHold, 'RECOVERED_RESULT'):
            self.run_it()
        self.assertEqual(self.c.executed, [])
        self.assertEqual(self.c.queried, [Contract.STEPS[0]])

    def test_unknown_history_blocks_all_actions(self):
        self.c.events.append({'type': 'UNKNOWN'})
        with self.assertRaisesRegex(BatchHold, 'EXISTING_UNKNOWN'):
            self.run_it()
        self.assertEqual(self.c.executed, [])

    def test_changed_plan_does_not_run(self):
        self.c.claim['plan_digest'] = 'wrong'
        with self.assertRaisesRegex(BatchHold, 'PLAN_MISMATCH'):
            self.run_it()
        self.assertEqual(self.c.executed, [])

    def test_invalid_receipt_stops(self):
        self.adapters['fence_source'] = lambda req: dict(success(req), operation_id='wrong')
        with self.assertRaises(ValueError):
            self.run_it()
        self.assertEqual(self.c.executed, ['inspect_protected', 'fence_source'])


if __name__ == '__main__':
    unittest.main()
