import hashlib
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch

path=os.path.join(os.path.dirname(os.path.dirname(__file__)),'scripts','uk-p2-install.py')
spec=importlib.util.spec_from_file_location('p2_cli_tests',path)
cli=importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class CliTests(unittest.TestCase):
    def test_arbitrary_installer_rejected_before_import(self):
        with self.assertRaisesRegex(ValueError,'FIXED_RELEASE_INSTALLER'):
            cli._installer('/tmp/unreviewed.py')

    def test_reviewed_plan_bytes_and_digest(self):
        with tempfile.TemporaryDirectory() as d:
            p=os.path.join(d,'plan.json')
            with open(p,'wb') as stream:stream.write(b'{"schema":1}')
            os.chmod(p,0o600)
            real=cli.os.fstat
            def info(fd):
                value=real(fd)
                from types import SimpleNamespace
                return SimpleNamespace(st_mode=value.st_mode,st_size=value.st_size,st_uid=0)
            with patch.object(cli.os,'fstat',side_effect=info):
                self.assertEqual(cli.read_plan(p,hashlib.sha256(b'{"schema":1}').hexdigest()),{'schema':1})
                with self.assertRaisesRegex(ValueError,'SHA256_MISMATCH'):
                    cli.read_plan(p,'a'*64)
                os.chmod(p,0o666)
                with self.assertRaisesRegex(ValueError,'ROOT_PROTECTED'):
                    cli.read_plan(p,'a'*64)

    def test_plan_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=os.path.join(d,'plan')
            with open(p,'w') as stream:stream.write('{}')
            os.symlink(p,p+'-link')
            with self.assertRaises(OSError):cli.read_plan(p+'-link','a'*64)

    def test_busy_lock_closes_descriptor(self):
        from types import SimpleNamespace
        with patch.object(cli.os,'open',return_value=17), \
             patch.object(cli.os,'fstat',return_value=SimpleNamespace(st_mode=0o100600,st_uid=0,st_nlink=1)), \
             patch.object(cli.fcntl,'flock',side_effect=BlockingIOError), \
             patch.object(cli.os,'close') as close:
            with self.assertRaises(BlockingIOError):cli.installation_lock()
            close.assert_called_once_with(17)


if __name__=='__main__':unittest.main()
