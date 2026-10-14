"""Authorization adapter fixtures, not a real Owner session acceptance."""
import unittest
from unittest.mock import patch
import test_foundation_integration  # Loads the existing SHA-pinned fixtures.
import owner_foundation_reader as reader


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


if __name__ == '__main__':
    unittest.main()
