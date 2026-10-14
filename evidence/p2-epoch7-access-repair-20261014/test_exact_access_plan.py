import unittest
from exact_access_plan import parse_acl,propose

class AclTests(unittest.TestCase):
    release='user::rwx\ngroup::r-x\nother::---\n'
    def test_release_named_traversal_only(self):
        r=propose(self.release,'release_traversal',[1002,1003,1004]);a=parse_acl(r['after_acl'])
        for uid in (1002,1003,1004):self.assertEqual(a['user',str(uid)],'--x')
        self.assertEqual(a['other',''],'---');self.assertFalse(r['permission_applied'])
    def test_single_binding_reader(self):
        r=propose('user::rw-\ngroup::r--\nother::---\n','ledger_client_binding_read',[1003])
        self.assertEqual(parse_acl(r['after_acl'])['user','1003'],'r--')
    def test_unrelated_masked_rights_preserved(self):
        raw='user::rwx\nuser:9000:rwx\ngroup::r-x\nmask::r-x\nother::---\n'
        a=parse_acl(propose(raw,'release_traversal',[1002,1003,1004])['after_acl'])
        self.assertEqual(a['user','9000'],'rwx');self.assertEqual(a['mask',''],'r-x')
    def test_alias_and_out_of_range_uid_rejected(self):
        for identity in ('01002','4294967295'):
            with self.assertRaises(ValueError):parse_acl(self.release+'user:'+identity+':--x\nmask::r-x\n')
    def test_default_acl_rejected(self):
        with self.assertRaises(ValueError):parse_acl(self.release+'default:user::rwx\n')
    def test_mask_expansion_rejected(self):
        with self.assertRaises(ValueError):propose(self.release+'mask::rwx\n','release_traversal',[1002,1003,1004])
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):parse_acl(self.release+'user::rwx\n')
    def test_existing_consumer_not_overwritten(self):
        with self.assertRaises(ValueError):propose(self.release+'user:1002:r--\nmask::r-x\n','release_traversal',[1002,1003,1004])
    def test_root_or_duplicate_consumers_rejected(self):
        for uids in ([0,1003,1004],[1002,1002,1004],[True,1003,1004]):
            with self.assertRaises(ValueError):propose(self.release,'release_traversal',uids)
    def test_malformed_and_reserved_consumer_ids_rejected(self):
        for value in ([],{},'1002',4294967295,10**100,-1,1.5,None):
            with self.assertRaises(ValueError):
                propose(self.release,'release_traversal',[value,1003,1004])
    def test_maximum_consumer_id_round_trips(self):
        result=propose(self.release,'release_traversal',[4294967294,1003,1004])
        self.assertEqual(parse_acl(result['after_acl'])['user','4294967294'],'--x')
    def test_no_world_expansion(self):
        with self.assertRaises(ValueError):propose(self.release.replace('other::---','other::--x'),'release_traversal',[1002,1003,1004])
    def test_effective_annotation_requires_normalization(self):
        with self.assertRaises(ValueError):parse_acl(self.release+'user:9000:rwx #effective:r-x\n')
    def test_missing_mask_rejected(self):
        with self.assertRaises(ValueError):parse_acl(self.release+'user:1002:--x\n')
    def test_exact_raw_hash_differs_with_header(self):
        a=propose(self.release,'release_traversal',[1002,1003,1004]);b=propose('# file: observed\n'+self.release,'release_traversal',[1002,1003,1004])
        self.assertNotEqual(a['before_sha256'],b['before_sha256']);self.assertEqual(a['after_acl'],b['after_acl'])

if __name__=='__main__':unittest.main()
