import unittest
from scripts.pr122_customer_channel_binding import bind
from scripts.pr122_customer_core import Denied
from unittest.mock import patch
class BindingTests(unittest.TestCase):
    def identity_members(self):
        import tempfile,tarfile
        from pathlib import Path
        from scripts.pr122_customer_package import build
        from scripts.pr122_customer_channel_binding import HOST_INTEGRATION_ADDITIONS
        with tempfile.TemporaryDirectory(prefix='identity-shape-synthetic-') as folder:
            build(folder,'a'*40,'b'*40)
            with tarfile.open(Path(folder)/'PR122_CUSTOMER_CENTER_REVIEW_ONLY.tar.gz') as archive:
                return [m for m in archive.getmembers() if m.name.removeprefix('customer-center/') not in HOST_INTEGRATION_ADDITIONS]
    def test_exact_identity_103_and_legacy_envelope(self):
        import tarfile
        from scripts.pr122_customer_channel_binding import validate_member_shape
        members=self.identity_members();self.assertEqual(len(members),103);validate_member_shape(members)
        validate_member_shape([tarfile.TarInfo('customer-center/a'),tarfile.TarInfo('customer-center/b')])
    def test_identity_incomplete_counts_and_oversize_rejected(self):
        import tarfile
        from scripts.pr122_customer_channel_binding import validate_member_shape
        members=self.identity_members()
        for count in (100,101,102):
            with self.subTest(count=count),self.assertRaises(Denied):validate_member_shape(members[:count])
        with self.assertRaises(Denied):validate_member_shape(members+[tarfile.TarInfo('customer-center/extra')])
    def test_identity_baseline_substitution_and_missing_addition_rejected(self):
        import copy
        from scripts.pr122_customer_channel_binding import validate_member_shape,IDENTITY_ADDITIONS
        members=self.identity_members()
        for addition in (True,False):
            changed=copy.deepcopy(members)
            entry=next(m for m in changed if (m.name.removeprefix('customer-center/') in IDENTITY_ADDITIONS)==addition and not m.name.endswith('/CUSTOMER_MANIFEST.json'))
            entry.name='customer-center/unapproved.py'
            with self.subTest(addition=addition),self.assertRaises(Denied):validate_member_shape(changed)
    def test_identity_duplicate_link_and_traversal_still_rejected(self):
        import copy,tarfile
        from scripts.pr122_customer_channel_binding import validate_member_shape
        for kind in ('duplicate','link','traversal'):
            changed=copy.deepcopy(self.identity_members())
            if kind=='duplicate':changed[-1].name=changed[0].name
            elif kind=='link':changed[-1].type=tarfile.SYMTYPE
            else:changed[-1].name='customer-center/../escape'
            with self.subTest(kind=kind),self.assertRaises(Denied):validate_member_shape(changed)
    def test_wrong_original_rejected_before_archive_parse(self):
        with patch('tarfile.open',side_effect=AssertionError('original first')),self.assertRaises(Denied):bind(b'bad',b'bad')
    def test_invalid_archive_with_original_hash_seam(self):
        import hashlib
        original=b'x=1\n'
        with patch('scripts.pr122_customer_channel_binding.ORIGINAL_SHA',hashlib.sha256(original).hexdigest()),self.assertRaises(Exception):bind(original,b'bad')

    def test_exact_host_integration_125_shape_and_neighbors_rejected(self):
        import tempfile,tarfile
        from pathlib import Path
        from scripts.pr122_customer_package import build
        from scripts.pr122_customer_channel_binding import validate_member_shape
        with tempfile.TemporaryDirectory(prefix='host-integration-shape-') as folder:
            build(folder,'a'*40,'b'*40)
            with tarfile.open(Path(folder)/'PR122_CUSTOMER_CENTER_REVIEW_ONLY.tar.gz') as archive:members=archive.getmembers()
        self.assertEqual(len(members),125);validate_member_shape(members)
        for changed in (members[:-1],members+[tarfile.TarInfo('customer-center/extra')]):
            with self.assertRaises(Denied):validate_member_shape(changed)
