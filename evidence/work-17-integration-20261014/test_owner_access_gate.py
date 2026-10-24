"""Authorization adapter fixtures, not a real Owner session acceptance."""
import unittest
from unittest.mock import patch
import test_foundation_integration  # Loads the existing SHA-pinned fixtures.
import owner_foundation_reader as reader
import test_owner_foundation_reader as original_reader_fixture
import copy


class OwnerAccessTests(unittest.TestCase):
    def setUp(self):
        self.binding = {'task_id': 'target', 'spec_sha256': 'a' * 64,
                        'checkpoint_sha256': 'b' * 64, 'commit': 'c' * 40,
                        'artifact_sha256': 'd' * 64, 'fence': 1, 'epoch': 1}

    def test_denied_session_never_reads_database(self):
        for response in (False, None, 1, 'true', {'authenticated': True}):
            with self.subTest(response=response), patch.object(reader, 'read_owner_foundations') as read:
                with self.assertRaisesRegex(ValueError, 'OWNER_READ_ACCESS_DENIED'):
                    reader.read_authorized_owner_foundations(lambda _: response, binding=self.binding)
                read.assert_not_called()

    def test_validator_failure_sanitized_before_read(self):
        def failed(_):
            raise RuntimeError('secret-session-value')
        with patch.object(reader, 'read_owner_foundations') as read:
            with self.assertRaisesRegex(ValueError, '^OWNER_READ_ACCESS_DENIED$'):
                reader.read_authorized_owner_foundations(failed, binding=self.binding)
            read.assert_not_called()

    def test_revocation_during_read_suppresses_result(self):
        verdicts = iter((True, False))
        with patch.object(reader, 'read_owner_foundations', return_value={'summary': 'private'}) as read:
            with self.assertRaisesRegex(ValueError, 'OWNER_READ_ACCESS_DENIED'):
                reader.read_authorized_owner_foundations(lambda _: next(verdicts), binding=self.binding)
            read.assert_called_once()

    def test_binding_mutation_does_not_rebind_read(self):
        observed = []
        def authorized(binding):
            observed.append(dict(binding))
            binding['task_id'] = 'other'
            return True
        with patch.object(reader, 'read_owner_foundations', return_value={'execution_granted': False}) as read:
            result = reader.read_authorized_owner_foundations(authorized, binding=self.binding)
            self.assertFalse(result['execution_granted'])
            self.assertEqual(read.call_args[1]['binding'], self.binding)
            self.assertEqual(observed, [self.binding, self.binding])


class OwnerAccessIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = original_reader_fixture.ReaderTests(methodName='runTest')
        self.fixture.setUp()
        context = self.fixture.context
        self.arguments = dict(db=context.reader, binding=context.binding, now=100,
                              activation_reader=lambda **_: copy.deepcopy(self.fixture.active),
                              expected_activation=copy.deepcopy(self.fixture.active), receipts={},
                              receipt_verifier=test_foundation_integration.verify,
                              producer_envelopes={},
                              inventory_verifier=test_foundation_integration.verify,
                              records_verifier=test_foundation_integration.verify)

    def tearDown(self):
        self.fixture.tearDown()

    def test_authorized_actual_canonical_snapshot_retains_unknown(self):
        before = self.fixture.context.reader.total_changes
        calls = []
        def authorized(binding):
            calls.append(binding['task_id'])
            return binding == self.fixture.context.binding
        result = reader.read_authorized_owner_foundations(authorized, **self.arguments)
        self.assertEqual(len(result['views']), 7)
        self.assertEqual(len(result['summary']), 7)
        self.assertEqual(result['status'], 'HOLD')
        self.assertFalse(result['execution_granted'])
        self.assertEqual(calls, ['target', 'target'])
        self.assertEqual(self.fixture.context.reader.total_changes, before)

    def test_unauthorized_actual_connection_executes_no_sql(self):
        statements = []
        self.fixture.context.reader.set_trace_callback(statements.append)
        with self.assertRaisesRegex(ValueError, 'OWNER_READ_ACCESS_DENIED'):
            reader.read_authorized_owner_foundations(lambda _: False, **self.arguments)
        self.assertEqual(statements, [])

    def test_actual_read_revocation_discards_seven_view_result(self):
        verdicts = iter((True, False))
        statements = []
        self.fixture.context.reader.set_trace_callback(statements.append)
        with self.assertRaisesRegex(ValueError, 'OWNER_READ_ACCESS_DENIED'):
            reader.read_authorized_owner_foundations(lambda _: next(verdicts), **self.arguments)
        self.assertTrue(any('SELECT' in sql.upper() for sql in statements))


if __name__ == '__main__':
    unittest.main()
