import hashlib
import os
import tempfile
import unittest
from install.p3_secure_fd import read_member, copy_member, open_absolute_dir

class SecureFDTests(unittest.TestCase):
    def test_copy_rejects_ancestor_symlink_hardlink_fifo_and_traversal(self):
        with tempfile.TemporaryDirectory() as base:
            src=os.path.join(base,'src'); dst=os.path.join(base,'dst')
            os.mkdir(src,0o700); os.mkdir(dst,0o700)
            os.mkdir(os.path.join(src,'real'),0o700)
            path=os.path.join(src,'real','file')
            with open(path,'wb') as f: f.write(b'abc')
            os.chmod(path,0o600)
            os.symlink('real',os.path.join(src,'link'))
            s=open_absolute_dir(src,os.getuid()); d=open_absolute_dir(dst,os.getuid())
            digest=hashlib.sha256(b'abc').hexdigest()
            try:
                with self.assertRaises(OSError): copy_member(s,d,'link/file',os.getuid(),digest)
                with self.assertRaises(ValueError): copy_member(s,d,'../file',os.getuid(),digest)
                os.link(path,os.path.join(src,'real','hard'))
                with self.assertRaises(PermissionError): copy_member(s,d,'real/file',os.getuid(),digest)
                os.unlink(os.path.join(src,'real','hard'))
                os.mkfifo(os.path.join(src,'real','fifo'))
                with self.assertRaises(PermissionError): copy_member(s,d,'real/fifo',os.getuid(),digest)
                copy_member(s,d,'real/file',os.getuid(),digest)
                with open(os.path.join(dst,'real','file'),'rb') as f: self.assertEqual(b'abc',f.read())
            finally:
                os.close(s); os.close(d)

    def test_copy_keeps_open_source_when_path_replaced_mid_read(self):
        from install import p3_secure_fd as secure
        with tempfile.TemporaryDirectory() as base:
            src=os.path.join(base,'src'); dst=os.path.join(base,'dst')
            os.mkdir(src,0o700); os.mkdir(dst,0o700)
            path=os.path.join(src,'file')
            with open(path,'wb') as f: f.write(b'original')
            os.chmod(path,0o600)
            s=open_absolute_dir(src,os.getuid()); d=open_absolute_dir(dst,os.getuid())
            original=secure.os.read; swapped=[False]
            def read(fd, count):
                if not swapped[0]:
                    swapped[0]=True
                    os.rename(path,path+'.old')
                    with open(path,'wb') as f: f.write(b'replaced')
                return original(fd,count)
            secure.os.read=read
            try:
                copy_member(s,d,'file',os.getuid(),hashlib.sha256(b'original').hexdigest())
                with open(os.path.join(dst,'file'),'rb') as f: self.assertEqual(b'original',f.read())
            finally:
                secure.os.read=original; os.close(s); os.close(d)

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
