"""Real descriptor/file/backup CAS in isolated protected directories only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'runtime'))
from approved_config import ApprovedConfiguration,sha
from receipt_provider import Hold
from permit_cycle import policy
class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='config5-',dir='/');os.chmod(self.tmp.name,0o700)
        self.path=Path(self.tmp.name)/'settings.json';self.old=b'{"limit":1}';self.new=b'{"limit":2}'
        self.path.write_bytes(self.old);os.chmod(str(self.path),0o600)
        self.action={'id':'limit','target':str(self.path),'before_sha256':sha(self.old),'after_sha256':sha(self.new),
                     'payload_sha256':sha(self.new),'checkpoint_sha256':'a'*64}
        self.count=0;self.fail=False
        def fence():
            self.count+=1
            if self.fail and self.count==2:raise Hold('LEASE_LOST')
        self.config=ApprovedConfiguration(self.tmp.name,{'limit':('settings.json',self.new)},fence,lambda:'a'*64)
    def tearDown(self):self.config.close();self.tmp.cleanup()
    def test_approved_configuration_real_cas_and_backup(self):
        result=self.config.apply(self.action)
        self.assertEqual(self.path.read_bytes(),self.new)
        self.assertEqual(result['backup_sha256'],sha(self.old))
        self.assertEqual(list(Path(self.tmp.name).glob('backup-*.json'))[0].read_bytes(),self.old)
    def test_committed_replay_is_idempotent(self):
        self.config.apply(self.action);self.config.apply(self.action)
        self.assertEqual(len(list(Path(self.tmp.name).glob('backup-*.json'))),1)
    def test_unapproved_action_refused(self):
        self.action['id']='other'
        with self.assertRaises(Hold):self.config.apply(self.action)
        self.assertEqual(self.path.read_bytes(),self.old)
    def test_source_filename_cannot_be_configuration(self):
        self.config.actions['limit']=('installer.py',self.new)
        with self.assertRaises(Hold):self.config.apply(self.action)
    def test_symlink_refused(self):
        self.path.unlink();self.path.symlink_to('other.json')
        with self.assertRaises(OSError):self.config.apply(self.action)
    def test_partial_output_held_and_preserved(self):
        self.fail=True
        with self.assertRaises(Hold):self.config.apply(self.action)
        self.fail=False
        with self.assertRaises(FileExistsError):self.config.apply(self.action)
        self.assertEqual(self.path.read_bytes(),self.old)
        self.assertEqual(len(list(Path(self.tmp.name).glob('pending-*.json'))),1)
    def test_unproven_checkpoint_never_writes(self):
        self.config.checkpoint=lambda:'f'*64
        with self.assertRaises(Hold):self.config.apply(self.action)
        self.assertEqual(self.path.read_bytes(),self.old)
    def test_concurrent_value_refused(self):
        self.path.write_bytes(b'{"limit":3}')
        with self.assertRaises(Hold):self.config.apply(self.action)
    def test_policy_rejects_per_attempt_approval_and_arbitrary_command(self):
        value=policy();value['new_approval_per_retry']=True
        with self.assertRaises(Hold):policy(value)
        value=policy();value['configuration_actions']=[dict(self.action,command='install')]
        with self.assertRaises(Hold):policy(value)
if __name__=='__main__':unittest.main()
