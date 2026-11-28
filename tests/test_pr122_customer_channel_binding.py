import unittest
from scripts.pr122_customer_channel_binding import bind
from scripts.pr122_customer_core import Denied
from unittest.mock import patch
class BindingTests(unittest.TestCase):
    def archive_bytes(self):
        import tempfile
        from pathlib import Path
        from scripts.pr122_customer_package import build
        if not hasattr(self,'_archive_bytes'):
            with tempfile.TemporaryDirectory(prefix='identity-shape-synthetic-') as folder:
                build(folder,'a'*40,'b'*40)
                self._archive_bytes=(Path(folder)/'PR122_CUSTOMER_CENTER_REVIEW_ONLY.tar.gz').read_bytes()
        return self._archive_bytes
    def identity_members(self):
        import io,tarfile
        with tarfile.open(fileobj=io.BytesIO(self.archive_bytes())) as archive:return archive.getmembers()
    def identity_manifest(self):
        import io,json,tarfile
        with tarfile.open(fileobj=io.BytesIO(self.archive_bytes())) as archive:return json.loads(archive.extractfile('customer-center/CUSTOMER_MANIFEST.json').read())
    def test_manifest_exact_closure_and_legacy_envelope(self):
        import tarfile
        from scripts.pr122_customer_channel_binding import validate_member_shape
        members=self.identity_members();manifest=self.identity_manifest()
        self.assertEqual({m.name for m in members},{'customer-center/CUSTOMER_MANIFEST.json',*['customer-center/'+x['path'] for x in manifest['files']]})
        validate_member_shape(members,manifest)
        validate_member_shape([tarfile.TarInfo('customer-center/a'),tarfile.TarInfo('customer-center/b')])
    def test_identity_incomplete_and_oversize_rejected(self):
        import tarfile
        from scripts.pr122_customer_channel_binding import validate_member_shape
        members=self.identity_members();manifest=self.identity_manifest()
        for drop in (0,1,len(members)//2):
            kept=members[:len(members)-1-drop] if drop<len(members)-1 else members[:1]
            with self.subTest(kept=len(kept)),self.assertRaises(Denied):validate_member_shape(kept,manifest)
        with self.assertRaises(Denied):validate_member_shape(members+[tarfile.TarInfo('customer-center/extra')],manifest)
        with self.assertRaises(Denied):validate_member_shape(members+[tarfile.TarInfo('customer-center/extra')])
    def test_identity_addition_substitution_and_missing_manifest_rejected(self):
        import copy
        from scripts.pr122_customer_channel_binding import validate_member_shape,IDENTITY_ADDITIONS
        members=self.identity_members();manifest=self.identity_manifest()
        for addition in (True,False):
            changed=copy.deepcopy(members)
            entry=next(m for m in changed if (m.name.removeprefix('customer-center/') in IDENTITY_ADDITIONS)==addition and not m.name.endswith('/CUSTOMER_MANIFEST.json'))
            entry.name='customer-center/unapproved.py'
            with self.subTest(addition=addition),self.assertRaises(Denied):validate_member_shape(changed,manifest)
        stripped=copy.deepcopy(members)
        for i,m in enumerate(stripped):
            if m.name=='customer-center/scripts/pr122_customer_identity.py':del stripped[i];break
        with self.assertRaises(Denied):validate_member_shape(stripped,manifest)
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
