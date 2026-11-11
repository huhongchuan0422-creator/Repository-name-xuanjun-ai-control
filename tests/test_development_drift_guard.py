import copy
import unittest
from scripts.development_drift_guard import BUDGETS, IDENTITY, evaluate_drift


def inputs():
    identity = {'task_id': 'T1', 'spec_sha256': 'a' * 64,
                'checkpoint_sha256': 'b' * 64, 'base_commit': 'c' * 40,
                'run_id': 'R1', 'lease_owner': 'DOTS', 'epoch': 1, 'fence': 2}
    limits = dict.fromkeys(BUDGETS, 10)
    limits.update(model_calls=0, delegation_depth=1, heavy_agents=2, active_agents=6)
    contract = {'schema': 'DRIFT_CONTRACT_V1', 'identity': identity,
                'limits': limits, 'allowed_permissions': ['repo.read', 'branch.write'],
                'max_age_seconds': 300}
    observed = {'schema': 'DRIFT_OBSERVATION_V1', 'identity': copy.deepcopy(identity),
                'usage': dict.fromkeys(BUDGETS, 0), 'permissions': ['repo.read'],
                'observed_at': 100, 'complete': True}
    return contract, observed


class DriftTests(unittest.TestCase):
    def test_match_is_not_grant(self):
        c, o = inputs(); result = evaluate_drift(c, o, 100)
        self.assertEqual(result['status'], 'MATCH')
        self.assertFalse(result['execution_granted'])
        self.assertFalse(result['dispatch_performed'])

    def test_no_mutation(self):
        c, o = inputs(); before = copy.deepcopy((c, o))
        evaluate_drift(c, o, 100)
        self.assertEqual((c, o), before)

    def test_all_identity_mismatches(self):
        for key in IDENTITY:
            c, o = inputs()
            o['identity'][key] = (3 if key in ('epoch', 'fence') else
                                  'd' * len(o['identity'][key]))
            self.assertIn('IDENTITY_MISMATCH_' + key.upper(),
                          evaluate_drift(c, o, 100)['reasons'])

    def test_all_budget_excesses(self):
        for key in BUDGETS:
            c, o = inputs(); o['usage'][key] = c['limits'][key] + 1
            if key == 'heavy_agents':
                o['usage']['active_agents'] = o['usage'][key]
            self.assertIn('BUDGET_EXCEEDED_' + key.upper(),
                          evaluate_drift(c, o, 100)['reasons'])

    def test_exact_budget_allowed(self):
        c, o = inputs(); o['usage'] = copy.deepcopy(c['limits'])
        self.assertEqual(evaluate_drift(c, o, 100)['status'], 'MATCH')

    def test_zero_model_budget(self):
        c, o = inputs(); o['usage']['model_calls'] = 1
        self.assertIn('BUDGET_EXCEEDED_MODEL_CALLS', evaluate_drift(c, o, 100)['reasons'])

    def test_permission_expansion(self):
        c, o = inputs(); o['permissions'].append('host.root')
        self.assertIn('PERMISSION_EXPANSION', evaluate_drift(c, o, 100)['reasons'])

    def test_permissions_not_prefix(self):
        c, o = inputs(); o['permissions'] = ['repo.read.secret']
        self.assertEqual(evaluate_drift(c, o, 100)['status'], 'HOLD')

    def test_permission_duplicates(self):
        c, o = inputs(); o['permissions'] *= 2
        self.assertEqual(evaluate_drift(c, o, 100)['status'], 'HOLD')

    def test_no_wildcard_permission(self):
        c, o = inputs(); c['allowed_permissions'] = ['*']
        self.assertEqual(evaluate_drift(c, o, 100)['status'], 'HOLD')

    def test_unknown_usage_not_zero(self):
        for value in (None, True, -1, 0.5, '0', 2 ** 64):
            c, o = inputs(); o['usage']['model_calls'] = value
            self.assertEqual(evaluate_drift(c, o, 100)['status'], 'HOLD')

    def test_missing_counter(self):
        for key in BUDGETS:
            c, o = inputs(); del o['usage'][key]
            self.assertEqual(evaluate_drift(c, o, 100)['status'], 'HOLD')

    def test_partial_observation(self):
        for value in (False, 1, None, 'true'):
            c, o = inputs(); o['complete'] = value
            self.assertEqual(evaluate_drift(c, o, 100)['status'], 'HOLD')

    def test_invalid_observation_time(self):
        for value in (True, float('nan'), float('inf'), -1, 10 ** 1000):
            c, o = inputs(); o['observed_at'] = value
            self.assertEqual(evaluate_drift(c, o, 100)['status'], 'HOLD')

    def test_stale_future(self):
        for now in (99, 401):
            c, o = inputs()
            self.assertIn('STALE_OR_FUTURE_OBSERVATION', evaluate_drift(c, o, now)['reasons'])

    def test_freshness_boundary(self):
        c, o = inputs()
        self.assertEqual(evaluate_drift(c, o, 400)['status'], 'MATCH')

    def test_invalid_clock(self):
        c, o = inputs()
        self.assertIn('INVALID_CLOCK', evaluate_drift(c, o, True)['reasons'])

    def test_unknown_top_level_keys(self):
        c, o = inputs(); o['secret'] = 'DO_NOT_ECHO'
        result = evaluate_drift(c, o, 100)
        self.assertEqual(result['status'], 'HOLD')
        self.assertNotIn('DO_NOT_ECHO', repr(result))

    def test_invalid_identity_shape(self):
        c, o = inputs(); o['identity']['fence'] = True
        self.assertEqual(evaluate_drift(c, o, 100)['status'], 'HOLD')

    def test_invalid_digest(self):
        c, o = inputs(); c['identity']['spec_sha256'] = 'not-a-hash'
        self.assertEqual(evaluate_drift(c, o, 100)['status'], 'HOLD')

    def test_impossible_heavy_count(self):
        c, o = inputs(); o['usage']['heavy_agents'] = 1
        self.assertEqual(evaluate_drift(c, o, 100)['status'], 'HOLD')

    def test_bad_containers(self):
        for value in (None, [], '', 0):
            c, o = inputs()
            self.assertEqual(evaluate_drift(value, o, 100)['status'], 'HOLD')
            self.assertEqual(evaluate_drift(c, value, 100)['status'], 'HOLD')

    def test_multiple_drifts_retained(self):
        c, o = inputs(); o['identity']['fence'] = 3
        o['permissions'] = ['host.root']; o['usage']['model_calls'] = 1
        self.assertEqual(len(evaluate_drift(c, o, 100)['reasons']), 3)

    def test_bad_freshness_budget(self):
        for value in (True, 0, 3601, '300'):
            c, o = inputs(); c['max_age_seconds'] = value
            self.assertIn('INVALID_CONTRACT', evaluate_drift(c, o, 100)['reasons'])


if __name__ == '__main__':
    unittest.main()
