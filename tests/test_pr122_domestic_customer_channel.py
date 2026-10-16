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
import multiprocessing
import contextlib
import io
import time
import tarfile
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
            for f in (c.grant, c.revoke, c.repair_modes):
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
        self.assertNotIn('--repair-modes',raw)
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
            # Validate a complete isolated sudoers include tree with the real
            # binary; the Hosted runner's unrelated global policy is not ours.
            global_rules=p/'sudoers.global'
            global_rules.write_text('root ALL=(ALL:ALL) ALL\n@includedir '+str(sudoers)+'\n')
            global_rules.chmod(0o440)
            real_run=c.subprocess.run
            def isolated_visudo(args, **kwargs):
                if args == ['/usr/sbin/visudo','-c']:
                    args=['/usr/sbin/visudo','-cf',str(global_rules)]
                return real_run(args, **kwargs)
            staging=p/'frozen.tar.gz';shutil.copyfile(path,staging)
            source=p/'installer.py';source.write_bytes(Path(c.__file__).read_bytes())
            with patch.multiple(c,BASE=base,EXEC=exe/'channel',POLICY=sudoers/'channel',STAGED_ARCHIVE=staging,__file__=str(source)), patch.object(c.pwd,'getpwnam',return_value=Account()), patch.dict(os.environ,{'SUDO_UID':'1000'}),patch.object(c.subprocess,'run',side_effect=isolated_visudo):
                self.assertEqual(c.grant()['state'],'GRANTED')
                self.assertEqual(c.EXEC.stat().st_mode & 0o777,0o755)
                self.assertEqual(c.POLICY.stat().st_mode & 0o777,0o440)
                self.assertEqual((base/'channel.py').stat().st_mode & 0o777,0o444)
                wrapper=c.EXEC.read_bytes()
                self.assertEqual(wrapper.splitlines()[0],b'#!/bin/sh')
                self.assertNotIn(b'\\n',wrapper)
                self.assertTrue(c.POLICY.read_bytes().endswith(b'\n'))
                invoked=real_run([str(c.EXEC),'inspect'],capture_output=True,text=True,env={'SUDO_UID':'1002'})
                # The fixture is not the approved domestic host: the wrapper
                # must actually start Python and fail closed as JSON, not ENOENT.
                self.assertEqual(invoked.returncode,2)
                self.assertEqual(json.loads(invoked.stdout)['state'],'HOLD')
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
                global_rules.chmod(0o600)
                global_rules.write_text('this is invalid sudoers syntax !!!\n')
                global_rules.chmod(0o440)
                with self.assertRaises(c.subprocess.CalledProcessError):
                    c.subprocess.run(['/usr/sbin/visudo','-c'],check=True,stdout=c.subprocess.DEVNULL,stderr=c.subprocess.DEVNULL)

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

    def test_four_processes_only_one_enters_fixed_action(self):
        context=multiprocessing.get_context('fork')
        barrier=context.Barrier(4);queue=context.Queue()
        with tempfile.TemporaryDirectory(prefix='pr122-channel-lock-',dir='/root') as t:
            base=Path(t);(base/'channel.py').write_bytes(b'fixture lock')
            def action(_):
                time.sleep(0.3)
                return {'state':'FIXTURE_LOCK_ENTERED'}
            def worker():
                barrier.wait(timeout=5)
                try:
                    with contextlib.redirect_stdout(io.StringIO()):c.main()
                    queue.put('ENTERED')
                except BlockingIOError:queue.put('LOCKED')
                except BaseException:queue.put('UNEXPECTED')
            with patch.object(c,'BASE',base),patch.object(c.os,'uname') as uname,patch.object(c,'dispatch',side_effect=action),patch.object(c.sys,'argv',['channel','inspect']):
                uname.return_value.nodename=c.HOST
                children=[context.Process(target=worker) for _ in range(4)]
                for p in children:p.start()
                results=[queue.get(timeout=8) for _ in children]
                for p in children:
                    p.join(timeout=5)
                    self.assertEqual(p.exitcode,0)
            self.assertEqual(sorted(results),['ENTERED','LOCKED','LOCKED','LOCKED'])

    def test_exclusive_exact_modes_under_umask_077(self):
        old=os.umask(0o077)
        try:
            with tempfile.TemporaryDirectory() as t:
                for mode in (0o444,0o755,0o440,0o600):
                    p=Path(t)/str(mode);c.exclusive(p,b'fixture',mode)
                    self.assertEqual(p.stat().st_mode & 0o777,mode)
        finally:os.umask(old)

    def recovery_fixture(self):
        # Root-only disposable recreation of the exact observed partial state.
        t=tempfile.TemporaryDirectory(prefix='pr122-channel-recovery-',dir='/root')
        self.addCleanup(t.cleanup);p=Path(t.name);base=p/'base';base.mkdir()
        exe=p/'libexec';exe.mkdir();rules=p/'sudoers';rules.mkdir()
        raw=Path(os.environ['PR122_FROZEN_TAR']).read_bytes()
        (base/'PR122_CUSTOMER_CENTER_REVIEW_ONLY.tar.gz').write_bytes(raw)
        root=base/'candidate';root.mkdir()
        for name,b in c.files_from_tar(raw).items():
            dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
        original=Path(os.environ['PR122_ORIGINAL_CHANNEL_TAR']).read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(),'c16113c86abd543700c380b7f566d3a95cf4bdf7d3667e7a8a2109263c57d1a3')
        with tarfile.open(fileobj=io.BytesIO(original),mode='r:gz') as archive:
            code=archive.extractfile('scripts/pr122_domestic_customer_channel.py').read()
        self.assertEqual(hashlib.sha256(code).hexdigest(),c.ORIGINAL_CHANNEL_SHA)
        (base/'channel.py').write_bytes(code);(base/'channel.py').chmod(0o400)
        (base/'grant-state.json').write_bytes(b'{"state":"PREPARING"}')
        global_rules=p/'sudoers.global';global_rules.write_text('root ALL=(ALL:ALL) ALL\n@includedir '+str(rules)+'\n');global_rules.chmod(0o440)
        return base,exe/'channel',rules/'channel',global_rules

    def test_exact_partial_mode_recovery_preserves_original_code(self):
        base,exe,rules,global_rules=self.recovery_fixture()
        class Account:pw_uid=1002
        real_run=c.subprocess.run
        def run(args,**kwargs):
            if args==['/usr/sbin/visudo','-c']:args=['/usr/sbin/visudo','-cf',str(global_rules)]
            return real_run(args,**kwargs)
        with patch.multiple(c,BASE=base,EXEC=exe,POLICY=rules),patch.object(c.pwd,'getpwnam',return_value=Account()),patch.dict(os.environ,{'SUDO_UID':'1000'}),patch.object(c.subprocess,'run',side_effect=run):
            exe.write_bytes(c.wrapper_bytes());exe.chmod(0o700)
            for path in (rules,base/'sudoers.candidate'):path.write_bytes(c.policy('githubrunner'));path.chmod(0o400)
            self.assertEqual(c.repair_modes()['state'],'GRANTED')
            self.assertEqual(exe.stat().st_mode&0o777,0o755)
            self.assertEqual(rules.stat().st_mode&0o777,0o440)
            self.assertEqual(hashlib.sha256((base/'channel.py').read_bytes()).hexdigest(),c.ORIGINAL_CHANNEL_SHA)
            with self.assertRaises(RuntimeError):c.repair_modes()

    def test_recovery_foreign_code_denied_before_mode_changes(self):
        base,exe,rules,global_rules=self.recovery_fixture()
        (base/'channel.py').chmod(0o600);(base/'channel.py').write_bytes(b'foreign');(base/'channel.py').chmod(0o400)
        with patch.multiple(c,BASE=base,EXEC=exe,POLICY=rules),patch.dict(os.environ,{'SUDO_UID':'1000'}),self.assertRaises(RuntimeError):c.repair_modes()
        self.assertEqual((base/'grant-state.json').read_bytes(),b'{"state":"PREPARING"}')


if __name__=='__main__':unittest.main()
