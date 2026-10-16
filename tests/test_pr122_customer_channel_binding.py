import unittest
from scripts.pr122_customer_channel_binding import bind
from scripts.pr122_customer_core import Denied
from unittest.mock import patch
class BindingTests(unittest.TestCase):
    def test_wrong_original_rejected_before_archive_parse(self):
        with patch('tarfile.open',side_effect=AssertionError('original first')),self.assertRaises(Denied):bind(b'bad',b'bad')
    def test_invalid_archive_with_original_hash_seam(self):
        import hashlib
        original=b'x=1\n'
        with patch('scripts.pr122_customer_channel_binding.ORIGINAL_SHA',hashlib.sha256(original).hexdigest()),self.assertRaises(Exception):bind(original,b'bad')
