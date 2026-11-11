import copy
import unittest
from scripts.source_path_ownership import check_source_paths


class Tests(unittest.TestCase):
    def setUp(self):
        self.claim={'claim_id':'C1','task_id':'TASK1','writer':'DOTS','paths':['scripts/owned/','tests/test_owned.py']}
        self.snapshot={'repository':'owner/repo','revision':5,'observed_at':100,'complete':True,'claims':[self.claim]}
        self.changes=[{'status':'modified','path':'scripts/owned/code.py','previous_path':None}]

    def call(self,**kw):
        args=dict(repository='owner/repo',task_id='TASK1',writer='DOTS',expected_revision=5,now=100,base_sha='a'*40,head_sha='b'*40)
        args.update(kw);return check_source_paths(self.snapshot,self.changes,**args)

    def hold(self):self.assertEqual(self.call()['state'],'HOLD')

    def test_owned_no_authority_grant(self):
        r=self.call();self.assertEqual(r['state'],'SOURCE_PATHS_MATCH')
        self.assertFalse(r['writer_granted']);self.assertFalse(r['runtime_lease_granted'])

    def test_no_input_mutation(self):
        before=copy.deepcopy((self.snapshot,self.changes));self.call()
        self.assertEqual(before,(self.snapshot,self.changes))

    def test_exact_file_scope(self):
        self.changes[0]['path']='tests/test_owned.py';self.assertEqual(self.call()['state'],'SOURCE_PATHS_MATCH')

    def test_prefix_segment_boundary(self):
        self.changes[0]['path']='scripts/owned-other/code.py';self.hold()

    def test_unowned(self):
        self.changes[0]['path']='shared/execution_ledger.py';self.hold()

    def test_foreign_path_overlap(self):
        self.snapshot['claims'].append(dict(claim_id='C2',task_id='TASK2',writer='WORK',paths=['scripts/']))
        self.hold()

    def test_same_writer_different_task_overlap(self):
        self.snapshot['claims'].append(dict(claim_id='C2',task_id='TASK2',writer='DOTS',paths=['scripts/owned/']))
        self.hold()

    def test_second_writer_same_task_disjoint_paths(self):
        self.snapshot['claims'].append(dict(claim_id='C2',task_id='TASK1',writer='WORK',paths=['other/']))
        self.assertIn('MULTIPLE_ACTIVE_TASK_WRITERS',self.call()['warnings'])

    def test_unrelated_owner_allowed(self):
        self.snapshot['claims'].append(dict(claim_id='C2',task_id='TASK2',writer='WORK',paths=['other/']))
        self.assertEqual(self.call()['state'],'SOURCE_PATHS_MATCH')

    def test_multiple_own_claims_allowed(self):
        self.snapshot['claims'].append(dict(claim_id='C2',task_id='TASK1',writer='DOTS',paths=['scripts/']))
        self.assertEqual(self.call()['state'],'SOURCE_PATHS_MATCH')

    def test_rename_checks_source(self):
        self.changes[0].update(status='renamed',previous_path='shared/old.py');self.hold()
        self.assertEqual(len(self.call()['paths']),2)

    def test_rename_checks_destination(self):
        self.changes[0].update(status='renamed',previous_path='scripts/owned/old.py',path='shared/new.py');self.hold()

    def test_owned_rename(self):
        self.changes[0].update(status='renamed',previous_path='scripts/owned/old.py')
        self.assertEqual(self.call()['state'],'SOURCE_PATHS_MATCH')

    def test_delete_requires_ownership(self):
        self.changes[0].update(status='removed',path='shared/x.py');self.hold()

    def test_incomplete_snapshot(self):
        self.snapshot['complete']=False;self.hold()

    def test_bool_complete_only(self):
        self.snapshot['complete']=1;self.hold()

    def test_revision_mismatch(self):
        self.snapshot['revision']=4;self.hold()

    def test_repository_mismatch(self):
        self.snapshot['repository']='other/repo';self.hold()

    def test_time_boundaries(self):
        for now in (99,401):self.assertEqual(self.call(now=now)['state'],'HOLD')
        self.assertEqual(self.call(now=400)['state'],'SOURCE_PATHS_MATCH')

    def test_invalid_times(self):
        for value in (True,float('nan'),float('inf'),-1):
            with self.assertRaises(ValueError):self.call(now=value)

    def test_noncanonical_paths_rejected(self):
        for path in ('../x','/x','x//y','x/./y','x/../y','x\\y','x/*','x\n','.git/config','x/.git/config','x/'):
            self.changes[0]['path']=path
            with self.assertRaises(ValueError):self.call()

    def test_glob_scope_not_supported(self):
        self.claim['paths']=['scripts/**']
        with self.assertRaises(ValueError):self.call()

    def test_duplicate_claim_identity(self):
        self.snapshot['claims']*=2
        with self.assertRaises(ValueError):self.call()

    def test_duplicate_change(self):
        self.changes*=2
        with self.assertRaises(ValueError):self.call()

    def test_no_changes_not_success(self):
        self.changes=[]
        with self.assertRaises(ValueError):self.call()

    def test_empty_claims_holds(self):
        self.snapshot['claims']=[];self.hold()

    def test_rename_missing_previous(self):
        self.changes[0]['status']='renamed'
        with self.assertRaises(ValueError):self.call()

    def test_nonrename_previous_rejected(self):
        self.changes[0]['previous_path']='scripts/owned/old.py'
        with self.assertRaises(ValueError):self.call()

    def test_bound(self):
        self.changes*=257
        with self.assertRaises(ValueError):self.call()

    def test_invalid_claim_type(self):
        self.snapshot['claims']=[{}]
        with self.assertRaises(ValueError):self.call()

    def test_exact_commit_binding_returned(self):
        r=self.call();self.assertEqual(r['base_sha'],'a'*40);self.assertEqual(r['head_sha'],'b'*40)

    def test_invalid_commit_binding(self):
        for value in (None,True,'HEAD','b'*39):
            with self.assertRaises(ValueError):self.call(head_sha=value)


if __name__=='__main__':unittest.main()
