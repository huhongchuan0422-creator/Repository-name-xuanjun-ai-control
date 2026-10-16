import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.pr122_customer_runtime import WHEELS,wheel_files,build
from scripts.pr122_customer_runtime import Denied

class RuntimeTests(unittest.TestCase):
    def test_root_staging_prohibited(self):
        with patch('os.geteuid',return_value=0),self.assertRaises(Denied):build('/missing','/unused')
    def test_missing_or_extra_vendor_wheel_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(Denied):wheel_files(folder)
            (Path(folder)/'evil.whl').write_bytes(b'bad')
            with self.assertRaises(Denied):wheel_files(folder)
    def test_tampered_vendor_bytes_rejected_before_unzip(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in WHEELS:(Path(folder)/name).write_bytes(b'bad')
            with patch('zipfile.ZipFile',side_effect=AssertionError('hash first')),self.assertRaises(Denied):wheel_files(folder)
    def test_symlink_wheel_is_not_read(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in WHEELS:(Path(folder)/name).symlink_to('/etc/passwd')
            with self.assertRaises(OSError):wheel_files(folder)
