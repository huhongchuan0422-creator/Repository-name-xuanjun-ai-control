import hashlib
import os
import tempfile
import unittest
from install.p3_secure_fd import read_member

class SecureFDTests(unittest.TestCase):
    def test_good_bad_paths_links_permissions_and_fifo(self):
        with tempfile.TemporaryDirectory() as root:
            os.mkdir(os.path.join(root, 'd'), 0o700)
            path = os.path.join(root, 'd', 'file')
            with open(path, 'wb') as f: f.write(b'good')
            os.chmod(path, 0o600)
            digest = hashlib.sha256(b'good').hexdigest()
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                self.assertEqual(b'good', read_member(fd, 'd/file', os.getuid(), digest))
                for bad in ('/d/file', '../file', 'd/../file', 'd//file'):
                    with self.assertRaises(ValueError): read_member(fd, bad, os.getuid(), digest)
                os.symlink('file', os.path.join(root,'d','link'))
                with self.assertRaises(OSError): read_member(fd,'d/link',os.getuid(),digest)
                os.link(path,os.path.join(root,'d','hard'))
                with self.assertRaises(PermissionError): read_member(fd,'d/file',os.getuid(),digest)
                os.unlink(os.path.join(root,'d','hard'))
                os.chmod(path, 0o622)
                with self.assertRaises(PermissionError): read_member(fd,'d/file',os.getuid(),digest)
                os.mkfifo(os.path.join(root,'d','fifo'))
                with self.assertRaises(PermissionError): read_member(fd,'d/fifo',os.getuid(),digest)
            finally:
                os.close(fd)
