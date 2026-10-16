# FEATURE_ID: PR122_DOMESTIC_WEBSITE_OFFLINE_CANDIDATE
"""Root-only temporary fixtures. No target host, sudoers or services touched."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import shutil
from scripts import pr122_domestic_customer_channel as c


class ChannelTests(unittest.TestCase):
    def test_no_arbitrary_actions(self):
        for action in ('sh', 'bash', 'prepare', 'inspect;id', '--grant', '--revoke', ''):
            with self.subTest(action=action), self.assertRaises(RuntimeError):
                c.dispatch(action)

    def test_wrong_runner(self):
        for uid in ('0', '1000', '', '1002 '):
            with self.subTest(uid=uid), patch.dict(os.environ, {'SUDO_UID':uid}), self.assertRaises(RuntimeError):
                c.dispatch('inspect')

    def test_owner_actions_denied_to_runner(self):
        with patch.dict(os.environ, {'SUDO_UID':'1002'}):
            for f in (c.grant, c.revoke):
                with self.subTest(action=f.__name__), self.assertRaises(RuntimeError):
                    f()

    def test_policy_has_exact_commands(self):
        class Account:
            pw_uid=1002
        with patch.object(c.pwd,'getpwnam',return_value=Account()):
            raw=c.policy('githubrunner').decode()
        self.assertNotIn('*',raw)
        self.assertNotIn('ALL)',raw)
        self.assertNotIn('--grant',raw)
        self.assertNotIn('--revoke',raw)
        for a in c.ACTIONS:self.assertIn(str(c.EXEC)+' '+a,raw)

    def test_policy_uid_mismatch(self):
        class Account:
            pw_uid=1001
        with patch.object(c.pwd,'getpwnam',return_value=Account()), self.assertRaises(RuntimeError):
            c.policy('githubrunner')

    def test_archive_rejects_wrong_hash_before_parse(self):
        with patch.object(c.tarfile,'open',side_effect=AssertionError('must not parse')), self.assertRaises(RuntimeError):
            c.files_from_tar(b'bad archive')

    def test_extra_arguments_rejected(self):
        with patch.object(c.os,'geteuid',return_value=0), patch.object(c.os,'uname') as uname:
            uname.return_value.nodename=c.HOST
            with patch.object(c.sys,'argv',['channel','inspect','extra']), self.assertRaises(RuntimeError):
                c.main()

    def test_wrong_host_rejected(self):
        with patch.object(c.os,'geteuid',return_value=0), patch.object(c.os,'uname') as uname:
            uname.return_value.nodename='other-host'
            with patch.object(c.sys,'argv',['channel','inspect']), self.assertRaises(RuntimeError):c.main()

    def test_nonroot_rejected(self):
        with patch.object(c.os,'geteuid',return_value=1002), self.assertRaises(RuntimeError):c.main()

    def test_secure_rejects_relative(self):
        with self.assertRaises(RuntimeError):c.secure('relative')

    def test_secure_rejects_writable_parent(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x';p.write_text('x')
            with self.assertRaises(RuntimeError):c.secure(p)

    def test_exclusive_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x';c.exclusive(p,b'old',0o600)
            with self.assertRaises(FileExistsError):c.exclusive(p,b'new',0o600)
            self.assertEqual(p.read_bytes(),b'old')

    def test_exclusive_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x';target=Path(t)/'target';target.write_bytes(b'old');p.symlink_to(target)
            with self.assertRaises(FileExistsError):c.exclusive(p,b'new',0o600)
            self.assertEqual(target.read_bytes(),b'old')

    def test_actual_frozen_archive_when_supplied(self):
        path=os.environ.get('PR122_FROZEN_TAR')
        if not path:
            self.skipTest('frozen artifact not supplied; CI supplies exact downloaded bytes')
        files=c.files_from_tar(Path(path).read_bytes())
        self.assertEqual(len(files),34)
        self.assertEqual(json.loads(files['CUSTOMER_MANIFEST.json'])['source_commit'],c.SOURCE)

    def test_grant_real_visudo_bundle_tamper_and_revoke(self):
        path=os.environ.get('PR122_FROZEN_TAR')
        self.assertIsNotNone(path, 'CI must supply frozen artifact')
        self.assertEqual(os.geteuid(),0,'root-only disposable fixture')
        class Account:pw_uid=1002
        with tempfile.TemporaryDirectory(prefix='pr122-channel-test-',dir='/root') as t:
            p=Path(t);base=p/'channel';exe=p/'libexec';exe.mkdir();sudoers=p/'sudoers';sudoers.mkdir()
            staging=p/'frozen.tar.gz';shutil.copyfile(path,staging)
            source=p/'installer.py';source.write_bytes(Path(c.__file__).read_bytes())
            with patch.multiple(c,BASE=base,EXEC=exe/'channel',POLICY=sudoers/'channel',STAGED_ARCHIVE=staging,__file__=str(source)), patch.object(c.pwd,'getpwnam',return_value=Account()), patch.dict(os.environ,{'SUDO_UID':'1000'}):
                self.assertEqual(c.grant()['state'],'GRANTED')
                self.assertEqual(c.validate_bundle(),base/'candidate')
                with self.assertRaises(RuntimeError):c.grant()
                extra=base/'candidate'/'unexpected.py';extra.write_bytes(b'raise Exception()')
                with self.assertRaises(RuntimeError):c.validate_bundle()
                extra.unlink()
                victim=base/'candidate'/'boot.py';old=victim.read_bytes();victim.chmod(0o600);victim.write_bytes(old+b'\n')
                with self.assertRaises(RuntimeError):c.validate_bundle()
                victim.write_bytes(old);victim.chmod(0o400)
                link=base/'candidate'/'link';link.symlink_to(victim)
                with self.assertRaises(RuntimeError):c.validate_bundle()
                link.unlink()
                os.link(victim,link)
                with self.assertRaises(RuntimeError):c.validate_bundle()
                link.unlink()
                with patch.dict(os.environ,{'SUDO_UID':'1002'}):
                    self.assertEqual(c.dispatch('inspect')['production_mutations'],0)
                self.assertEqual(c.revoke()['state'],'CHANNEL_REVOKED')
                self.assertFalse(c.POLICY.exists())
                self.assertTrue((base/'channel.py').exists())

    def test_partial_grant_retains_evidence_and_rejects_retry(self):
        class Account:pw_uid=1002
        with tempfile.TemporaryDirectory(prefix='pr122-channel-fault-',dir='/root') as t:
            p=Path(t);exe=p/'libexec';exe.mkdir();rules=p/'sudoers';rules.mkdir()
            source=p/'installer.py';source.write_bytes(Path(c.__file__).read_bytes())
            staging=p/'frozen.tar.gz';shutil.copyfile(os.environ['PR122_FROZEN_TAR'],staging)
            with patch.multiple(c,BASE=p/'base',EXEC=exe/'channel',POLICY=rules/'channel',STAGED_ARCHIVE=staging,__file__=str(source)),patch.object(c.pwd,'getpwnam',return_value=Account()),patch.dict(os.environ,{'SUDO_UID':'1000'}),patch.object(c.subprocess,'run',side_effect=RuntimeError('failure')):
                with self.assertRaises(RuntimeError):c.grant()
                self.assertFalse(c.POLICY.exists())
                self.assertEqual(json.loads((c.BASE/'grant-state.json').read_text()),{'state':'PREPARING'})
                with self.assertRaises(RuntimeError):c.grant()
                with patch.dict(os.environ,{'SUDO_UID':'1002'}),self.assertRaises(RuntimeError):c.dispatch('inspect')


if __name__=='__main__':unittest.main()
