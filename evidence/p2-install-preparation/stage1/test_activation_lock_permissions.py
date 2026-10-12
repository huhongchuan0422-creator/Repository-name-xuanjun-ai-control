import os
import stat
import tempfile
import unittest
import uuid
from unittest.mock import patch

from activation_control import ActivationStore, ActivationError


class ActivationLockPermissionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = os.path.realpath(self.temp.name)
        self.store = ActivationStore(root + '/active.json', root + '/epochs.jsonl',
                                     root + '/activation.lock', owner_uid=os.geteuid())

    def test_authority_creates_non_writable_reader_lock(self):
        fd = self.store._locked()
        os.close(fd)
        self.assertEqual(stat.S_IMODE(os.stat(self.store.lock_path).st_mode), 0o644)

    def test_reader_opens_existing_lock_read_only_without_chmod(self):
        os.close(self.store._locked())
        real_open = os.open
        observed = []
        def capture(path, flags, *args):
            observed.append(flags)
            return real_open(path, flags, *args)
        with patch('activation_control.os.geteuid', return_value=self.store.owner_uid + 1), \
             patch('activation_control.os.open', side_effect=capture), \
             patch('activation_control.os.fchmod', side_effect=AssertionError('reader chmod')):
            fd = self.store._locked()
            os.close(fd)
        self.assertEqual(observed[0] & os.O_ACCMODE, os.O_RDONLY)
        self.assertFalse(observed[0] & os.O_CREAT)

    def test_reader_does_not_bootstrap_missing_lock(self):
        with patch('activation_control.os.geteuid', return_value=self.store.owner_uid + 1):
            with self.assertRaises(FileNotFoundError):
                self.store._locked()

    def test_group_writable_lock_is_rejected(self):
        os.close(self.store._locked())
        os.chmod(self.store.lock_path, 0o664)
        with self.assertRaises(ActivationError):
            self.store._locked()

    def test_symlink_lock_is_rejected(self):
        target = self.temp.name + '/untrusted'
        with open(target, 'w') as stream:
            stream.write('')
        os.symlink(target, self.store.lock_path)
        with self.assertRaises(OSError):
            self.store._locked()

    def _prepared(self):
        return self.store.prepare('a'*64,'b'*64,'c'*64,str(uuid.uuid4()),
            1,str(uuid.uuid4()),self.temp.name+'/db.sqlite',self.temp.name+'/ledger.sock',
            expected_epoch=0)

    def test_fence_persists_next_inactive_epoch_and_blocks_stale_cas(self):
        original=self._prepared()
        stopped=self.store.fence(original['epoch'],original['instance'])
        self.assertEqual(stopped['epoch'],2)
        self.assertEqual(stopped['state'],'PREPARED')
        self.assertEqual(self.store.reconcile(),stopped)
        with self.assertRaises(ActivationError): self.store.read(require_active=True)
        with self.assertRaisesRegex(ActivationError,'CAS'):
            self.store.fence(original['epoch'],original['instance'])

    def test_reader_cannot_fence_even_with_valid_identity(self):
        original=self._prepared()
        with patch('activation_control.os.geteuid',return_value=self.store.owner_uid+1):
            with self.assertRaisesRegex(ActivationError,'authority owner'):
                self.store.fence(original['epoch'],original['instance'])
        self.assertEqual(self.store.read(),original)


if __name__ == '__main__':
    unittest.main()
