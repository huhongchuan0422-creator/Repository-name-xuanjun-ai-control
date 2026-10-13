import copy
import unittest
from scripts.owner_action_digest import build_digest


def task(name='A', fence=1):
    return {'id': name, 'fence': fence, 'state': 'WAITING_HUMAN',
            'checkpoint': {'phase': 'REVIEW', 'error_code': 'OWNER_APPROVAL',
                           'commit': 'a' * 40}}


def snapshot(rows=None):
    rows = [task()] if rows is None else rows
    return {'source': 'CANONICAL_LEDGER_READ_ONLY', 'observed_at': 100,
            'counts': {'WAITING_HUMAN': len(rows)}, 'human_queue': rows}


class DigestTests(unittest.TestCase):
    def test_ready_is_not_permission(self):
        result = build_digest(snapshot(), 101)
        self.assertEqual(result['status'], 'VIEW_READY')
        self.assertFalse(result['approval_granted'])
        self.assertFalse(result['dispatch_performed'])

    def test_does_not_mutate(self):
        source = snapshot(); before = copy.deepcopy(source)
        build_digest(source, 100)
        self.assertEqual(source, before)

    def test_order_independent(self):
        a, b = task('A'), task('B')
        self.assertEqual(build_digest(snapshot([a, b]), 100),
                         build_digest(snapshot([b, a]), 100))

    def test_duplicate(self):
        result = build_digest(snapshot([task(), task()]), 100)
        self.assertEqual(result['duplicate_count'], 1)
        self.assertEqual(result['unique_count'], 1)

    def test_conflicting_fence(self):
        result = build_digest(snapshot([task(), task(fence=2)]), 100)
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(result['conflicting_task_count'], 1)
        self.assertEqual(len(result['items']), 2)

    def test_conflicting_same_fence(self):
        other = task(); other['checkpoint']['phase'] = 'INSTALL'
        self.assertEqual(build_digest(snapshot([task(), other]), 100)
                         ['conflicting_task_count'], 1)

    def test_full_counts_bounded_display(self):
        result = build_digest(snapshot([task(str(n)) for n in range(20)]), 100, limit=2)
        self.assertEqual(result['omitted_count'], 18)
        self.assertEqual(result['group_counts'], {'OWNER_APPROVAL': 20})

    def test_display_limit_not_identity(self):
        source = snapshot([task('A'), task('B')])
        self.assertEqual(build_digest(source, 100, 1)['digest_sha256'],
                         build_digest(source, 100, 2)['digest_sha256'])

    def test_queue_count_mismatch(self):
        source = snapshot(); source['counts']['WAITING_HUMAN'] = 2
        self.assertIn('QUEUE_COUNT_MISMATCH', build_digest(source, 100)['warnings'])

    def test_recent_tasks_window_not_used(self):
        source = snapshot(); source['tasks'] = []; source['truncated'] = True
        self.assertEqual(build_digest(source, 100)['unique_count'], 1)

    def test_empty(self):
        self.assertEqual(build_digest(snapshot([]), 100)['status'], 'VIEW_READY')

    def test_missing_count_not_zero(self):
        source = snapshot([]); source['counts'] = {}
        result = build_digest(source, 100)
        self.assertEqual(result['status'], 'HOLD')
        self.assertIn('QUEUE_COUNT_MISMATCH', result['warnings'])

    def test_invalid_count_not_zero(self):
        for value in (None, True, False, '0', 0.0, -1):
            source = snapshot([]); source['counts']['WAITING_HUMAN'] = value
            self.assertEqual(build_digest(source, 100)['status'], 'HOLD')

    def test_reason_only_checkpoint_not_ready(self):
        row = task(); row['checkpoint'] = {'error_code': 'OWNER_APPROVAL'}
        result = build_digest(snapshot([row]), 100)
        self.assertEqual(result['status'], 'HOLD')
        self.assertIn('UNKNOWN_CHECKPOINT_EVIDENCE', result['warnings'])

    def test_missing_or_invalid_phase_hold(self):
        for value in (None, '', 'UNKNOWN', 'lowercase', '<script>', True):
            row = task(); row['checkpoint']['phase'] = value
            self.assertIn('UNKNOWN_CHECKPOINT_EVIDENCE',
                          build_digest(snapshot([row]), 100)['warnings'])

    def test_missing_or_invalid_commit_hold(self):
        for value in (None, '', 'a' * 39, 'A' * 40, 'UNKNOWN', True):
            row = task(); row['checkpoint']['commit'] = value
            self.assertIn('UNKNOWN_CHECKPOINT_EVIDENCE',
                          build_digest(snapshot([row]), 100)['warnings'])

    def test_producer_checkpoint_aliases(self):
        row = task(); row['checkpoint'] = {'phase': 'REVIEW', 'reason': 'OWNER_APPROVAL',
                                         'sha': 'a' * 40}
        result = build_digest(snapshot([row]), 100)
        self.assertEqual(result['status'], 'VIEW_READY')
        self.assertEqual(result['items'][0]['commit'], 'a' * 40)

    def test_unknown_checkpoint(self):
        row = task(); row['checkpoint'] = None
        result = build_digest(snapshot([row]), 100)
        self.assertEqual(result['status'], 'HOLD')
        self.assertIsNone(result['items'][0]['commit'])

    def test_no_raw_content(self):
        row = task(); row['checkpoint']['prompt'] = 'SECRET'
        row['checkpoint']['error_code'] = '<script>SECRET</script>'
        row['lease_owner'] = 'SECRET'
        self.assertNotIn('SECRET', repr(build_digest(snapshot([row]), 100)))

    def test_invalid_rows_accounted(self):
        for row in (None, {}, task('../bad'), task(fence=True), task(fence=-1)):
            result = build_digest(snapshot([row]), 100)
            self.assertEqual(result['invalid_count'], 1)
            self.assertEqual(result['status'], 'HOLD')

    def test_wrong_state(self):
        row = task(); row['state'] = 'DONE'
        self.assertEqual(build_digest(snapshot([row]), 100)['invalid_count'], 1)

    def test_stale_future_unknown(self):
        for stamp in (None, True, float('nan'), float('inf'), 1000, 0):
            source = snapshot(); source['observed_at'] = stamp
            self.assertIn('STALE_OR_UNKNOWN_SNAPSHOT', build_digest(source, 400)['warnings'])

    def test_wrong_source(self):
        source = snapshot(); source['source'] = 'FAKE'
        self.assertEqual(build_digest(source, 100)['status'], 'HOLD')

    def test_limits(self):
        for limit in (True, 0, 501, 1.5):
            with self.assertRaises(ValueError):
                build_digest(snapshot(), 100, limit)

    def test_invalid_time(self):
        for now in (True, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                build_digest(snapshot(), now)

    def test_invalid_input_bound(self):
        for source in (None, {}, snapshot([task()] * 10001)):
            with self.assertRaises(ValueError):
                build_digest(source, 100)


if __name__ == '__main__':
    unittest.main()
