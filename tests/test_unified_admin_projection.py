import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from unified_admin_projection import build_projection


class UnifiedAdminProjectionTest(unittest.TestCase):
    def fixtures(self):
        tasks = {'mode': 'TEST_ONLY', 'tenant_id': 'tenant-a',
                 'observed_at': 99, 'tasks': [
            {'task_id': 'T1', 'project_id': 'P1', 'node_id': 'N1',
             'board_id': 'research-development', 'state': 'RUNNING',
             'runtime_status': 'LIVENESS_UNKNOWN', 'attempt_id': 'A1',
             'responsible_party': 'writer', 'run_id': 'R1',
             'session_id': 'S1', 'epoch': 7, 'checkpoint_sha256': 'cp'}],
                 'timeline': [
            {'task_id': 'T1', 'attempt_id': 'A1', 'event_id': 'E1',
             'kind': 'PROGRESS', 'evidence_ref': 'sha256:abc'}]}
        models = {'mode': 'TEST_ONLY', 'tenant_id': 'tenant-a',
                  'providers': [{'provider_id': 'free',
                                 'display_name': 'Free model',
                                 'secret_configured': True,
                                 'secret_mask': 'must-not-leak',
                                 'secret_cipher': 'must-not-leak-either'}],
                  'quota_status': [], 'modules': [],
                  'usage': [
                      {'provider_id': 'free', 'model_id': 'model-free',
                       'request_count': 2, 'input_tokens': 10,
                       'output_tokens': 4, 'cost_state': 'KNOWN_ZERO',
                       'known_cost': 0},
                      {'provider_id': 'paid', 'model_id': 'model-unknown',
                       'request_count': 1, 'input_tokens': 3,
                       'output_tokens': 1, 'cost_state': 'UNKNOWN',
                       'known_cost': 999}]
                  }
        return tasks, models

    def test_builds_read_only_fail_closed_projection(self):
        value = build_projection(*self.fixtures(), observed_at=123)
        self.assertEqual(value['projection'], 'UNIFIED_ADMIN_PROJECTION_V1')
        self.assertEqual(value['mode'], 'TEST_ONLY')
        self.assertEqual(value['capability']['mutation'], 'NONE')
        self.assertEqual(value['observed_at'], 123)
        self.assertEqual(value['source_observed_at'], 99)
        self.assertEqual(value['modules']['research-development']['records'][0]
                         ['task_id'], 'T1')
        ordinary = value['modules']['research-development']['records'][0]
        for key in ('attempt_id', 'run_id', 'session_id', 'epoch',
                    'checkpoint_sha256'):
            self.assertNotIn(key, ordinary)
        audit = value['modules']['research-development']['advanced'][
            'audit_records'][0]
        self.assertEqual(audit['attempt_id'], 'A1')
        self.assertEqual(audit['run_id'], 'R1')
        self.assertEqual(audit['evidence'][0]['evidence_ref'], 'sha256:abc')
        self.assertEqual(value['modules']['finance']['status'], 'NOT_CONNECTED')
        self.assertEqual(value['modules']['finance']['metrics']['profit'],
                         'UNKNOWN')
        for name in ('project', 'social_media', 'servers'):
            self.assertEqual(value['modules'][name]['status'], 'NOT_CONNECTED')
            self.assertEqual(value['modules'][name]['capability'][
                'allowed_actions'], [])

    def test_disconnected_sources_expose_exact_gaps_without_claiming_connection(self):
        value = build_projection(*self.fixtures(), observed_at=123)
        finance = value['sources']['finance']
        self.assertEqual(finance['status'], 'NOT_CONNECTED')
        self.assertEqual(finance['source_level'],
                         'CANDIDATE_ONLY_UNVERIFIED')
        self.assertEqual(finance['evidence_refs'], [
            'git:0b47f98d656f0ac7b182a724746a72b7f7028e40:'
            'scripts/community_saas_offer_catalog.py',
            'git:0cd56648867bcb6bc0d8c35fda82f05e4fe58a5f:'
            'scripts/owner_finance_takeover_combined_inspect.py'])
        for gap in ('CANONICAL_ADAPTER', 'IDENTITY', 'SCHEMA_VERSION',
                    'TENANT_MAPPING', 'CURRENT_WRITER', 'INSTALL_EVIDENCE'):
            self.assertIn(gap, finance['gaps'])
        social = value['sources']['social_media']
        self.assertEqual(social['source_candidates'],
                         ['Channel Registry', 'Channel Metrics projection'])
        self.assertEqual(social['evidence_refs'], [
            'git:b021d8059654570aa8caeb0ee88befe3214fc9a3:'
            'deploy/pr122-oauth-candidate/',
            'git:ce76432a7050cfd0bd3410a1967624f969a253d9:'
            'deploy/pr122-minimal-cutover/tokyo-nginx-source-inventory.json'])
        for gap in ('CHANNEL_REGISTRY', 'METRICS', 'RBAC',
                    'INSTALL_EVIDENCE'):
            self.assertIn(gap, social['gaps'])
        servers = value['sources']['servers']
        self.assertEqual(servers['source_candidates'],
                         ['Infrastructure Registry',
                          'Blueprint HTTP adapter'])
        self.assertEqual(servers['evidence_refs'], [
            'git:3398098ffffe741fd087e854a8f3c75007113481:'
            'scripts/v27-batch-readonly.sh',
            'git:ce76432a7050cfd0bd3410a1967624f969a253d9:'
            'scripts/pr122_domestic_channel_inventory.py'])
        for gap in ('INFRA_REGISTRY', 'BLUEPRINT_HTTP', 'CAPABILITY',
                    'CURRENT_INVENTORY'):
            self.assertIn(gap, servers['gaps'])
        self.assertEqual({finance['status'], social['status'],
                          servers['status']}, {'NOT_CONNECTED'})

    def test_secrets_are_reduced_to_status_and_reference(self):
        value = build_projection(*self.fixtures(), observed_at=123)
        encoded = json.dumps(value)
        self.assertNotIn('must-not-leak', encoded)
        provider = value['modules']['configuration']['records'][0]
        self.assertEqual(provider['secret']['state'], 'CONFIGURED')
        self.assertEqual(provider['secret']['ref'],
                         'PROTECTED_PROVIDER_SECRET:free')

    def test_existing_secret_mask_implies_configured_without_leaking_mask(self):
        tasks, models = self.fixtures()
        models['providers'][0].pop('secret_configured')
        value = build_projection(tasks, models, observed_at=123)
        provider = value['modules']['configuration']['records'][0]
        self.assertEqual(provider['secret']['state'], 'CONFIGURED')
        self.assertNotIn('must-not-leak', json.dumps(value))

    def test_model_usage_is_read_only_estimate_not_a_finance_fact(self):
        value = build_projection(*self.fixtures(), observed_at=123)
        advanced = value['modules']['configuration']['advanced']
        self.assertEqual(advanced['model_usage_semantic'],
                         'MODEL_ESTIMATE_NOT_BILLING_OR_ACTUAL_CHARGE')
        usage = advanced['model_usage']
        self.assertEqual(usage[0]['estimated_cost'], 0)
        self.assertEqual(usage[0]['cost_unit'], 'UNKNOWN')
        self.assertEqual(usage[1]['estimated_cost'], 'UNKNOWN')
        self.assertEqual(usage[1]['semantic'],
                         'MODEL_ESTIMATE_NOT_BILLING_OR_ACTUAL_CHARGE')
        self.assertEqual(value['modules']['finance']['status'],
                         'NOT_CONNECTED')

    def test_rejects_production_or_cross_tenant_sources(self):
        tasks, models = self.fixtures()
        tasks['mode'] = 'PRODUCTION'
        with self.assertRaisesRegex(ValueError, 'TEST_ONLY'):
            build_projection(tasks, models, 1)
        tasks, models = self.fixtures()
        models['tenant_id'] = 'tenant-b'
        with self.assertRaisesRegex(ValueError, 'SAME_TENANT'):
            build_projection(tasks, models, 1)


if __name__ == '__main__':
    unittest.main()
