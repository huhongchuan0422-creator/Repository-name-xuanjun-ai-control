import hashlib
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import task_center_app as app


class PublicProjectionMetadataDelta(unittest.TestCase):
    def test_public_only_stable_snapshot_and_unknown_freshness(self):
        source = {'mode': 'TEST_ONLY', 'production_status': 'NOT_IMPLEMENTED',
                  'observed_at': 1793105160.570348,
                  'boards': [{'board_id': 'development', 'task_count': 1,
                              'active_count': 1, 'blocked_count': 0,
                              'health': 'ACTIVE', 'private': 'never-publish'}],
                  'tasks': [{'body': 'never-publish'}]}
        with patch.object(app, 'read_only_projection', return_value=source):
            result = app.read_only_public_projection('db', 'key', 'tenant', 'principal')
        old = {k: result[k] for k in ('mode', 'production_status', 'observed_at', 'boards')}
        self.assertEqual(result['snapshot_sha256'], hashlib.sha256(json.dumps(
            old, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest())
        self.assertNotIn('never-publish', json.dumps(result))
        self.assertEqual(result['observed_at'], source['observed_at'])
        self.assertEqual(result['observed_at_unit'], 'unix_seconds')
        self.assertEqual(result['observed_at_semantics'], 'MAX_CANONICAL_TASK_LAST_EVENT_AT')
        self.assertEqual(result['freshness'], 'UNKNOWN')
        self.assertIsNone(result['valid_until'])
        self.assertEqual(result['schema_version'], 1)
        self.assertEqual(result['boards'][0]['active_count'], 1)

    def test_empty_missing_time_and_source_failure(self):
        source = {'mode': 'TEST_ONLY', 'production_status': 'NOT_IMPLEMENTED',
                  'observed_at': None, 'boards': []}
        with patch.object(app, 'read_only_projection', return_value=source):
            result = app.read_only_public_projection('db', 'key', 'tenant', 'principal')
        self.assertIsNone(result['observed_at'])
        self.assertEqual(result['boards'], [])
        with patch.object(app, 'read_only_projection', side_effect=OSError('unavailable')):
            with self.assertRaises(OSError):
                app.read_only_public_projection('db', 'key', 'tenant', 'principal')

if __name__ == '__main__':
    unittest.main()
