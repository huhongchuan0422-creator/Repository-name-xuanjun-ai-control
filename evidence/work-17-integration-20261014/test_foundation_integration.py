"""Real isolated SQLite/WAL tests; never installed UK or release evidence."""
import copy
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
DEPS = Path(os.environ.get('XJ_FOUNDATION_FIXTURES', str(HERE / 'deps')))
for pin in json.loads((HERE / 'pins.json').read_text()):
    if hashlib.sha256((DEPS / pin['name']).read_bytes()).hexdigest() != pin['sha256']:
        raise RuntimeError('TEST_DEPENDENCY_HASH_MISMATCH')
sys.path.insert(0, str(DEPS))
sys.path.insert(0, str(HERE))
import bootstrap
for name, expected in bootstrap.FIXTURE.items():
    if hashlib.sha256((DEPS / name).read_bytes()).hexdigest() != expected:
        raise RuntimeError('TEST_ORIGINAL102_HASH_MISMATCH')
from execution_ledger import ExecutionLedger
from owner_dashboard import snapshot as original_dashboard
from canary_evidence_coverage import CASES
from resume_prerequisite_view import FIELDS
from handoff_evidence_view import PROOFS
from run_usage_projection import COUNTERS
from foundation_integration import (foundation_snapshot, canonical_page, bound_receipt,
                                   chinese_summary, digest, KINDS)

# Fixture-only trusted authentication key. Not an Owner/runtime credential.
KEY = b'isolated-test-fixture-only-not-deployment-authority'
def verify(raw, signature):
    return isinstance(signature, str) and hmac.compare_digest(
        hmac.new(KEY, raw, hashlib.sha256).hexdigest(), signature)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'canonical.sqlite'
        self.writer = sqlite3.connect(str(self.path), isolation_level=None)
        self.writer.execute('PRAGMA journal_mode=WAL')
        self.writer.executescript('''
            CREATE TABLE tasks(id TEXT PRIMARY KEY,kind TEXT,state TEXT,depends TEXT,
                               lease_owner TEXT,lease_until REAL,fence INTEGER,checkpoint TEXT,updated REAL);
            CREATE TABLE approvals(task_id TEXT PRIMARY KEY,decision TEXT,requested_at REAL,decided_at REAL);
            CREATE TABLE events(id INTEGER PRIMARY KEY,task_id TEXT,event TEXT,created REAL,details TEXT);
        ''')
        self.cp = '{"phase":"WAITING_HUMAN","secret":"DO_NOT_DISPLAY"}'
        self.add('target')
        # Use original frozen102 producer, not a fabricated spec hash.
        ledger = ExecutionLedger(str(self.path), ['fixture/repo'], clock=lambda: 100)
        spec = {'repo': 'fixture/repo', 'type': 'CODEX_EXEC', 'prompt': 'fixture-only',
                'heavy': False, 'timeout_seconds': 60, 'base_sha': 'a' * 40}
        result = ledger.register_spec('target', spec, 'fixture-owner', True)
        self.binding = {'task_id': 'target', 'spec_sha256': result['hash'],
                        'checkpoint_sha256': hashlib.sha256(self.cp.encode()).hexdigest(),
                        'commit': 'b' * 40, 'artifact_sha256': 'c' * 64, 'fence': 1, 'epoch': 2}
        self.reader = None

    def tearDown(self):
        if self.reader:
            self.reader.close()
        self.writer.close()
        self.temp.cleanup()

    def add(self, identity, state='PENDING', deps=None, checkpoint=None):
        self.writer.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                            (identity, 'CODEX_EXEC', state, json.dumps(deps or []), None,
                             None, 1, self.cp if checkpoint is None else checkpoint, 100))

    def read(self):
        self.reader = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, isolation_level=None)
        self.reader.execute('PRAGMA query_only=ON')
        self.reader.execute('BEGIN')
        return self.reader

    def envelope(self, kind, data, binding=None, stamp=100):
        payload = {'binding': self.binding if binding is None else binding,
                   'kind': kind, 'observed_at': stamp, 'data': data}
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode()
        return {'payload': payload, 'signature': hmac.new(KEY, raw, hashlib.sha256).hexdigest()}

    def view(self, receipts=None, **kwargs):
        return foundation_snapshot(self.reader or self.read(), self.binding, 100,
                                   receipts or {}, verify, **kwargs)

    def test_existing_original_dashboard_reports_missing_cost_usage(self):
        original = original_dashboard(str(self.path), now=100)
        self.assertIsNone(original['foundation_views']['costs'][0]['currencies'].get('CNY'))
        self.assertEqual(original['foundation_views']['usage']['status'], 'HOLD')
        self.assertEqual(original['foundation_views']['evidence_status'], 'HOLD_NO_CANONICAL_COST_USAGE_PRODUCER')
        self.assertNotIn('DO_NOT_DISPLAY', json.dumps(original))

    def test_cost_current_task_authenticated_receipt(self):
        records = [{'task_id': 'target', 'component_id': 'compute', 'currency': 'CNY',
                    'kind': 'ACTUAL', 'amount_micros': 1250000, 'evidence_sha256': 'd' * 64}]
        result = self.view({'costs': self.envelope('costs', records)})
        self.assertEqual(result['views']['costs']['currencies']['CNY']['actual_micros'], 1250000)
        self.assertFalse(result['release_granted'])

    def test_cost_other_task_is_not_counted(self):
        records = [{'task_id': 'other', 'component_id': 'compute', 'currency': 'CNY',
                    'kind': 'ACTUAL', 'amount_micros': 1, 'evidence_sha256': 'd' * 64}]
        self.assertEqual(self.view({'costs': self.envelope('costs', records)})['views']['costs']['status'], 'HOLD')

    def test_cost_unknown_is_not_zero(self):
        records = [{'task_id': 'target', 'component_id': 'compute', 'currency': 'CNY',
                    'kind': 'UNKNOWN', 'amount_micros': None, 'evidence_sha256': None}]
        self.assertIsNone(self.view({'costs': self.envelope('costs', records)})['views']['costs']['currencies']['CNY']['actual_micros'])

    def test_usage_authenticated_cumulative_sample(self):
        data = [{'run_id': 'run-1', 'provider': 'INTERNAL', 'counters': dict.fromkeys(COUNTERS, 4), 'evidence_sha256': 'd' * 64}]
        result = self.view({'usage': self.envelope('usage', data)})['views']['usage']
        self.assertEqual(result['totals']['model_calls'], 4)
        self.assertIsNone(result['quota_remaining'])

    def test_usage_missing_producer_remains_unknown(self):
        self.assertIsNone(self.view()['views']['usage']['totals']['model_calls'])

    def test_done_dependency_is_not_accepted(self):
        self.add('prior', 'DONE')
        self.writer.execute('UPDATE tasks SET depends=? WHERE id=?', ('["prior"]', 'target'))
        self.assertEqual(self.view()['views']['dependencies']['status'], 'HOLD')

    def test_no_dependencies_can_be_evidenced_without_dispatch(self):
        result = self.view()['views']['dependencies']
        self.assertEqual(result['status'], 'DEPENDENCIES_EVIDENCED')
        self.assertFalse(result['execution_granted'])

    def test_missing_dependency_hold(self):
        self.writer.execute('UPDATE tasks SET depends=? WHERE id=?', ('["missing"]', 'target'))
        self.assertIn('MISSING_OR_MALFORMED_NODE', self.view()['views']['dependencies']['reasons'])

    def test_dependency_cycle_hold(self):
        self.add('prior', deps=['target'])
        self.writer.execute('UPDATE tasks SET depends=? WHERE id=?', ('["prior"]', 'target'))
        self.assertIn('DEPENDENCY_CYCLE', self.view()['views']['dependencies']['reasons'])

    def test_truncated_graph_never_ready(self):
        for i in range(220): self.add('task-%03d' % i)
        result = self.view(max_tasks=100)
        self.assertFalse(result['scan_complete'])
        self.assertIsNone(result['remaining_count'])
        self.assertEqual(result['views']['dependencies']['status'], 'HOLD')

    def test_resume_exact_binding_and_no_grant(self):
        data = dict.fromkeys(FIELDS, True)
        data.update(observed_at=100, binding_sha256=digest(self.binding))
        result = self.view({'resume': self.envelope('resume', data)})['views']['resume']
        self.assertEqual(result['status'], 'PREREQUISITES_REPORTED')
        self.assertFalse(result['resume_granted'])

    def test_resume_wrong_inner_binding_hold(self):
        data = dict.fromkeys(FIELDS, True)
        data.update(observed_at=100, binding_sha256='a' * 64)
        self.assertEqual(self.view({'resume': self.envelope('resume', data)})['views']['resume']['status'], 'HOLD')

    def test_resume_missing_old_stop_hold(self):
        data = dict.fromkeys(FIELDS, True); data['old_writer_stopped'] = None
        data.update(observed_at=100, binding_sha256=digest(self.binding))
        self.assertIn('UNPROVEN_OLD_WRITER_STOPPED', self.view({'resume': self.envelope('resume', data)})['views']['resume']['reasons'])

    def test_alert_build_only_verified_origin(self):
        result = self.view({'alert': self.envelope('alert', {'reason': 'HANDOFF', 'deadline': 200})}, workspace_origin='https://owner.example')['views']['alert']
        self.assertEqual(result['workspace_url'], 'https://owner.example/owner/tasks/target')
        self.assertFalse(result['send_performed']); self.assertFalse(result['approval_granted'])

    def test_alert_missing_origin_hold(self):
        result = self.view({'alert': self.envelope('alert', {'reason': 'HANDOFF', 'deadline': 200})})
        self.assertEqual(result['views']['alert']['status'], 'HOLD')

    def test_alert_untrusted_url_and_secret_are_not_reflected(self):
        result = self.view({'alert': self.envelope('alert', {'reason': 'SECRET_ACCESS_TOKEN', 'deadline': 200})}, workspace_origin='https://owner.example/?token=SECRET')
        self.assertNotIn('SECRET', json.dumps(result))

    def test_handoff_all_proofs_no_authority(self):
        data = {k: self.binding[k] for k in ('task_id', 'spec_sha256', 'checkpoint_sha256', 'commit', 'artifact_sha256')}
        data.update(dict.fromkeys(PROOFS, True)); data['evidence_sha256'] = 'd' * 64
        result = self.view({'handoff': self.envelope('handoff', data)})['views']['handoff']
        self.assertEqual(result['status'], 'HANDOFF_PROOFS_REPORTED')
        self.assertFalse(result['execution_granted']); self.assertFalse(result['handoff_performed'])

    def test_handoff_missing_ack_hold(self):
        data = {k: self.binding[k] for k in ('task_id', 'spec_sha256', 'checkpoint_sha256', 'commit', 'artifact_sha256')}
        data.update(dict.fromkeys(PROOFS, True)); data['successor_ack'] = False; data['evidence_sha256'] = 'd' * 64
        self.assertIn('UNPROVEN_SUCCESSOR_ACK', self.view({'handoff': self.envelope('handoff', data)})['views']['handoff']['reasons'])

    def canary(self, environment='UK_RUNTIME'):
        return [{'case': case, 'commit': self.binding['commit'], 'artifact_sha256': self.binding['artifact_sha256'],
                 'evidence_sha256': 'd' * 64, 'environment': environment, 'status': 'PASS', 'run_id': 'fixture-run'} for case in CASES]

    def test_canary_fixture_labels_do_not_count_as_runtime(self):
        result = self.view({'canary': self.envelope('canary', self.canary('FIXTURE'))})
        self.assertEqual(result['views']['canary']['status'], 'HOLD')

    def test_canary_authenticated_supplied_runtime_claim_never_grants(self):
        result = self.view({'canary': self.envelope('canary', self.canary())})['views']['canary']
        self.assertEqual(result['status'], 'COVERAGE_COMPLETE')
        self.assertFalse(result['release_granted']); self.assertFalse(result['dispatch_performed'])
        # Fixture HMAC and UK_RUNTIME label are ONLY a validator positive test.

    def test_summary_chinese_fixed_fields_and_no_free_text(self):
        summary = chinese_summary(self.view())
        self.assertEqual(len(summary), 7); self.assertIn('任务费用', json.dumps(summary, ensure_ascii=False))
        self.assertNotIn('DO_NOT_DISPLAY', json.dumps(summary))
        self.assertTrue(all(row['执行授权'] is False for row in summary))

    def test_read_transaction_required(self):
        with self.assertRaisesRegex(ValueError, 'READ_TRANSACTION'):
            canonical_page(self.writer)

    def test_read_only_without_begin_rejected(self):
        db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)
        try:
            db.execute('PRAGMA query_only=ON')
            with self.assertRaises(ValueError): canonical_page(db)
        finally: db.close()

    def test_stale_fence_rejected(self):
        self.writer.execute('UPDATE tasks SET fence=99 WHERE id=?', ('target',))
        with self.assertRaisesRegex(ValueError, 'TASK_BINDING'): self.view()

    def test_checkpoint_changed_rejected(self):
        self.writer.execute('UPDATE tasks SET checkpoint=? WHERE id=?', ('{}', 'target'))
        with self.assertRaisesRegex(ValueError, 'CHECKPOINT_CHANGED'): self.view()

    def test_canonical_spec_changed_rejected(self):
        self.writer.execute('UPDATE execution_specs SET hash=? WHERE task_id=?', ('f' * 64, 'target'))
        with self.assertRaisesRegex(ValueError, 'SPEC_CHANGED'): self.view()

    def test_boolean_receipt_fence_not_equal_to_integer_one(self):
        changed = dict(self.binding); changed['fence'] = True
        with self.assertRaisesRegex(ValueError, 'INVALID_BINDING'):
            bound_receipt('usage', self.binding, self.envelope('usage', [], changed), verify, 100)

    def test_wal_snapshot_consistent_concurrent_writer_changes(self):
        db = self.read(); db.execute('SELECT COUNT(*) FROM tasks').fetchone()
        self.writer.execute('UPDATE tasks SET fence=99 WHERE id=?', ('target',))
        self.assertFalse(self.view()['execution_granted'])
        # Read snapshot consistency does NOT prove current live authority.
        db.close(); self.reader = None
        with self.assertRaises(ValueError): self.view()

    def test_receipt_all_binding_dimensions_rechecked(self):
        for field in sorted(self.binding):
            changed = dict(self.binding); changed[field] = ('other' if field == 'task_id' else 99 if field in ('fence', 'epoch') else 'a' * len(changed[field]))
            with self.subTest(field=field), self.assertRaises(ValueError):
                bound_receipt('usage', self.binding, self.envelope('usage', [], changed), verify, 100)

    def test_tampered_receipt_signature_rejected(self):
        env = self.envelope('usage', []); env['payload']['data'] = ['SECRET']
        result = self.view({'usage': env})
        self.assertEqual(result['views']['usage']['status'], 'HOLD'); self.assertNotIn('SECRET', json.dumps(result))

    def test_future_and_stale_receipts_rejected(self):
        for stamp in (101, 0):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                bound_receipt('usage', self.binding, self.envelope('usage', [], stamp=stamp), verify, 400 if stamp == 0 else 100)

    def test_paging_over_100_and_malformed_early_row(self):
        for i in range(250): self.add('task-%03d' % i, checkpoint='not-json')
        self.writer.execute('UPDATE tasks SET depends=? WHERE id=?', ('{"unexpected":true}', 'task-000'))
        db = self.read(); seen = []; cursor = None
        while True:
            page = canonical_page(db, cursor, 100); seen.extend(x['id'] for x in page['tasks'])
            if not page['has_more']: break
            cursor = page['next_after_id']
        self.assertEqual(len(seen), 251); self.assertEqual(len(set(seen)), 251)
        self.assertIn('task-249', seen)

    def test_reopen_and_resume_keyset_without_second_queue(self):
        for i in range(220): self.add('task-%03d' % i)
        first = canonical_page(self.read(), limit=100)
        self.reader.close(); self.reader = None
        second = canonical_page(self.read(), first['next_after_id'], 100)
        self.assertFalse(set(x['id'] for x in first['tasks']) & set(x['id'] for x in second['tasks']))

    def test_duplicate_dependency_json_keys_fail_closed(self):
        self.writer.execute('UPDATE tasks SET depends=? WHERE id=?', ('{"x":1,"x":2}', 'target'))
        self.assertEqual(self.view()['views']['dependencies']['status'], 'HOLD')

    def test_view_does_not_mutate_any_canonical_tables(self):
        before = list(self.writer.iterdump())
        self.view()
        self.reader.close(); self.reader = None
        self.assertEqual(before, list(self.writer.iterdump()))

    def test_invalid_clock_and_bounds_rejected(self):
        db = self.read()
        for now in (True, float('nan'), -1):
            with self.subTest(now=now), self.assertRaises(ValueError):
                foundation_snapshot(db, self.binding, now, {}, verify)
        for limit in (0, True, 1001):
            with self.assertRaises(ValueError): self.view(max_tasks=limit)

    def test_oversized_authenticated_receipt_rejected(self):
        with self.assertRaisesRegex(ValueError, 'TOO_LARGE'):
            bound_receipt('usage', self.binding, self.envelope('usage', 'x' * 262145), verify, 100)

    def test_bootstrap_wrong_archive_hash_rejected(self):
        import io, zipfile
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z: z.writestr('p2-candidate.tar.gz', b'bad')
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_HASH'):
            bootstrap.unpack_selected(stream.getvalue(), Path(self.temp.name))


if __name__ == '__main__':
    unittest.main()
