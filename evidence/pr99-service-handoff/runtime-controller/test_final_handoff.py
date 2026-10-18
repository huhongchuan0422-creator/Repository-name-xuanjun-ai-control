"""Real temporary received bytes/fds; fixture ownership/authority, not live trust."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import catalogue_binding as c
import existing_fd_controller as f
import final_handoff as h
import migration_transaction as original
import owner_contract
from test_capture_session import CaptureFixture
from test_runtime_controller import OriginalJournalFixture


class HandoffTests(CaptureFixture,unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.target_temp=tempfile.TemporaryDirectory();self.target=Path(self.target_temp.name)
        self.fdmap={};self.fdowners={};self.assignment_calls=0;self.query_calls=0;self.target_valid=True
        self.native_file=self.root/'fixture-native-assignment.json'
        static=b'ordinary fixed application fixture\n'
        self.handoff={'schema':1,'host':h.HOST,'release':h.RELEASE,'identity':{'name':'xuanjun-s07','uid':992,'gid':991},
          'files':{'opt/trading-system/data/project.db':{'job_id':'database','sha256':None,'bytes':None,'uid':992,'gid':991,'mode':0o600},
                   'opt/trading-system/runtime/settings.fixture':{'job_id':'settings','sha256':None,'bytes':None,'uid':992,'gid':991,'mode':0o600},
                   'opt/trading-system/fixture.py':{'job_id':None,'sha256':h.file_sha(static),'bytes':len(static),'uid':0,'gid':0,'mode':0o644}},
          'links':dict(h.LINKS),'database_job_id':'database','start_source_sha256':'a'*64}
        self.config['handoff']=self.handoff
        self.journal.close();os.close(self.txn_fd)
        for path in self.journal.path.iterdir():path.unlink()
        self.journal.path.rmdir()
        self.plan['bindings']['runtime_identity']=c.digest(self.handoff['identity'])
        self.plan['bindings']['final_manifest_contract']=c.digest(self.config)
        self.plan.pop('independent_review_comment_id')
        self.plan['owner_authority']=copy.deepcopy(owner_contract.OWNER_AUTHORITY)
        self.plan_digest=original.digest(self.plan)
        self.journal=original.Journal(self.root,'fixture-original');self.journal.claim(self.plan,self.plan_digest)
        self.txn_fd=os.open(self.journal.path,os.O_RDONLY|os.O_DIRECTORY)
        self.binding.update(plan_digest=self.plan_digest,
            transaction_identity=[os.fstat(self.txn_fd).st_dev,os.fstat(self.txn_fd).st_ino],
            lock_identity=[os.fstat(self.journal.lock.fileno()).st_dev,os.fstat(self.journal.lock.fileno()).st_ino],
            extension_manifest_sha256=original.digest(f.extension_manifest()))
        self.owner_contract_active=True
        self.controller=self.make_controller();req=original.request(self.plan,'inspect_protected',self.plan_digest)
        with patch.object(original,'source_manifest',return_value=self.plan['source_hashes']):first=self.controller.perform(req,self.dispatch,self.query)
        self.fence_req=original.request(self.plan,'fence_source',original.digest(first))
        self.session=self.build();self.fence();captured=self.capture()
        materials={'opt/trading-system/data/project.db':self.io.read('/var/lib/pr99-test-only/output/final.db',67108864),
                   'opt/trading-system/runtime/settings.fixture':self.io.read('/var/lib/pr99-test-only/settings',67108864),
                   'opt/trading-system/fixture.py':static}
        for name,raw in materials.items():
            p=self.target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            row=self.handoff['files'][name];p.chmod(row['mode'])
            fd=os.open(p,os.O_RDONLY);self.fdmap[name]=fd;self.fdowners[fd]=(row['uid'],row['gid'])
        for name,destination in self.handoff['links'].items():
            p=self.target/name;p.parent.mkdir(parents=True,exist_ok=True);p.symlink_to(destination)
        # CI cannot chown to the real dedicated host UID. Only target-file owner
        # metadata is a fixture; identity/content/mode/descriptor I/O is native.
        real_fstat=os.fstat
        owners=self.fdowners
        class OwnerView:
            def __init__(self,s,owner):self.original=s;self.st_uid,self.st_gid=owner
            def __getattr__(self,k):return getattr(self.original,k)
        def fixture_fstat(fd):
            s=real_fstat(fd)
            return OwnerView(s,owners[fd]) if fd in owners else s
        self.stat_patch=patch.object(os,'fstat',fixture_fstat);self.stat_patch.start()
        self.checkpoint_fd=os.open(self.root/'original-final-checkpoint',os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
        self.assignment_fd=os.open(self.root/'original-writer-assignment',os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
        self.receive_req=original.request(self.plan,'receive_final',original.digest(captured))
        with patch.object(original,'source_manifest',return_value=self.plan['source_hashes']):received=self.controller.perform(self.receive_req,self.dispatch,self.query)
        self.reconcile_req=original.request(self.plan,'reconcile_final',original.digest(received))
        self.source_view=h.OriginalSourceEvidence(self.controller,self.session.config,self.source_query,self.source_verify)
        self.receiver=self.receiver_build()

    def members(self):
        files=[];links={}
        for directory,dirs,names in os.walk(self.target,followlinks=False):
            for name in list(dirs)+names:
                p=Path(directory)/name;rel=p.relative_to(self.target).as_posix()
                if p.is_symlink():links[rel]=os.readlink(p)
                elif p.is_file():files.append(rel)
        return {'files':sorted(files),'links':links}

    def make_controller(self):
        if not getattr(self,'owner_contract_active',False):return super().make_controller()
        return f.ExistingFdController(self.journal,owner_contract,self.root_fd,self.txn_fd,self.binding,
            lambda mode,b:self.allowed and b==self.binding,lambda:self.paths_valid,self.history)

    def check_target(self,config,identities):
        if not self.target_valid:return False
        return all((s.st_dev,s.st_ino)==identities[name] for name in identities for s in [(self.target/name).stat()])

    def assign_native(self,req,binding):
        self.assignment_calls+=1
        if self.native_file.exists():raise AssertionError('NATIVE_CAS_REPLAY')
        record={'binding':binding,'status':'TARGET_ASSIGNED_NOT_STARTED','exclusive':True}
        proof={**record,'authority_receipt_sha256':c.digest(record)}
        self.native_file.write_bytes(c.encode(proof))
        return proof

    def query_native(self,req,binding):
        self.query_calls+=1
        return json.loads(self.native_file.read_bytes())

    def verify_native(self,req,binding,proof):
        return self.native_file.exists() and json.loads(self.native_file.read_bytes())==proof

    def receiver_build(self):
        return h.FinalHandoff(self.controller,self.source_view,self.fdmap,self.check_target,self.members,
            self.checkpoint_fd,lambda:True,self.assignment_fd,lambda:True,
            self.assign_native,self.query_native,self.verify_native)

    def source_query(self,req,expected):
        result=self.session._snapshot(req,query_only=True)
        fence=os.pread(self.proof_fd,16385,0);snapshot=os.pread(self.capture_fd,2097153,0)
        proof={'source_host':'iZ6wee8q9z4t03hvqumwfhZ','transaction_id':self.binding['transaction_id'],
          'plan_digest':self.binding['plan_digest'],'epoch':self.binding['epoch'],'snapshot_result':result,
          'fence_raw':fence,'snapshot_raw':snapshot,'current_fence_sha256':self.session._fence(),
          'captured_outputs_verified':True}
        self.last_source_proof=copy.deepcopy(proof)
        return proof

    def source_verify(self,req,expected,proof):return proof==self.last_source_proof

    def perform(self,req):
        with patch.object(original,'source_manifest',return_value=self.plan['source_hashes']):return self.receiver.perform(req)

    def reconciled(self):
        result=self.perform(self.reconcile_req)
        self.assign_req=original.request(self.plan,'assign_writer',original.digest(result))
        return result

    def tearDown(self):
        self.stat_patch.stop()
        for fd in self.fdmap.values():os.close(fd)
        os.close(self.checkpoint_fd);os.close(self.assignment_fd);self.target_temp.cleanup()
        super().tearDown()

    def test_nonempty_wal_to_reconciled_checkpoint_to_original_assignment(self):
        self.assertIs(self.controller.m,owner_contract)
        self.assertNotIn('independent_review_comment_id',self.plan)
        self.reconciled();result=self.perform(self.assign_req)
        checkpoint=json.loads(os.pread(self.checkpoint_fd,2097153,0));assignment=json.loads(os.pread(self.assignment_fd,16385,0))
        self.assertEqual(checkpoint['class'],'FINAL_CANONICAL_CHECKPOINT')
        self.assertEqual(len(checkpoint['files']),2);self.assertEqual(checkpoint['database_integrity'],'PASS')
        self.assertEqual(assignment['checkpoint_sha256'],c.digest(checkpoint));self.assertFalse(assignment['source_writer_resumed'])
        self.assertEqual(self.assignment_calls,1);self.assertEqual(result['status'],'SUCCEEDED')
        # Exact byte formats are accepted by the already published start helper.
        import production_start as start
        fence=os.pread(self.proof_fd,16385,0);cp=os.pread(self.checkpoint_fd,2097153,0);a=os.pread(self.assignment_fd,16385,0)
        p={'source_writer_fence_receipt_sha256':h.file_sha(fence),'final_checkpoint_receipt_sha256':h.file_sha(cp),
           'canonical_writer_assignment_sha256':h.file_sha(a),'writer_inventory_sha256':self.inventory,'writer_epoch':7,
           'final_data_file_hashes':checkpoint['files'],'file_hashes':{**checkpoint['files'],'static':'a'*64},
           'database_schema_sha256':checkpoint['database_schema_sha256']}
        self.assertTrue(start.validate_final_receipts(p,fence,cp,a,int(h.time.time())))

    def test_changed_received_data_holds_before_checkpoint_or_cas(self):
        (self.target/'opt/trading-system/runtime/settings.fixture').write_bytes(b'changed')
        with self.assertRaises(f.ControllerHold):self.reconciled()
        self.assertEqual(os.fstat(self.checkpoint_fd).st_size,0);self.assertEqual(self.assignment_calls,0)

    def test_additional_unlisted_file_holds(self):
        (self.target/'unlisted').write_bytes(b'never in manifest')
        with self.assertRaises(f.ControllerHold):self.reconciled()
        self.assertEqual(os.fstat(self.checkpoint_fd).st_size,0)

    def test_changed_symlink_holds(self):
        p=self.target/'venv/bin/python';p.unlink();p.symlink_to('/bin/bash')
        with self.assertRaises(f.ControllerHold):self.reconciled()

    def test_revoked_target_path_binding_holds_before_journal_intent(self):
        self.target_valid=False;count=len(self.controller.load()[1])
        with self.assertRaises(h.HandoffHold):self.reconciled()
        self.assertEqual(len(self.controller.load()[1]),count)

    def test_replaced_target_descriptor_holds(self):
        name=next(iter(self.fdmap));original_fd=self.fdmap[name];self.fdmap[name]=self.fdmap['opt/trading-system/fixture.py']
        with self.assertRaises(h.HandoffHold):self.receiver_build()
        self.fdmap[name]=original_fd

    def test_missing_capture_job_mapping_holds(self):
        self.source_view.config['handoff']['files']['opt/trading-system/runtime/settings.fixture']['job_id']=None
        with self.assertRaises(RuntimeError):self.receiver_build()

    def test_cached_assignment_does_not_call_cas_again(self):
        self.reconciled();first=self.perform(self.assign_req);second=self.perform(self.assign_req)
        self.assertEqual(first,second);self.assertEqual(self.assignment_calls,1)

    def test_crash_after_durable_assignment_queries_without_cas_replay(self):
        self.reconciled();self.controller._append({'type':'INTENT','request':self.assign_req})
        direct=self.receiver._assign(self.assign_req)
        self.receiver=self.receiver_build()
        self.receiver.assign=lambda *a:(_ for _ in ()).throw(AssertionError('CAS_REPLAY'))
        result=self.perform(self.assign_req)
        self.assertEqual(result,direct);self.assertEqual(self.assignment_calls,1);self.assertEqual(self.query_calls,1)

    def test_native_commit_without_document_preserves_unknown_no_republish_on_query(self):
        self.reconciled()
        real_assign=self.receiver.assign
        def lost(req,binding):real_assign(req,binding);raise TimeoutError('lost after native effect')
        self.receiver.assign=lost
        with self.assertRaises(f.ControllerHold):self.perform(self.assign_req)
        self.assertEqual(self.assignment_calls,1);self.assertEqual(os.fstat(self.assignment_fd).st_size,0)
        self.receiver=self.receiver_build()
        with self.assertRaises(f.ControllerHold):self.perform(self.assign_req)
        self.assertEqual(self.assignment_calls,1);self.assertEqual(os.fstat(self.assignment_fd).st_size,0)
        with self.assertRaises(h.HandoffHold):self.receiver._assign(self.assign_req)
        self.assertEqual(self.assignment_calls,1)

    def test_unverified_assignment_ack_is_not_authority(self):
        self.reconciled();self.receiver.verify=lambda *a:False
        with self.assertRaises(f.ControllerHold):self.perform(self.assign_req)
        self.assertEqual(os.fstat(self.assignment_fd).st_size,0)

    def test_reconcile_pending_intent_reads_existing_proof_only(self):
        self.controller._append({'type':'INTENT','request':self.reconcile_req})
        direct=self.receiver._reconcile(self.reconcile_req)
        before=os.pread(self.checkpoint_fd,2097153,0)
        result=self.perform(self.reconcile_req)
        self.assertEqual(result,direct);self.assertEqual(os.pread(self.checkpoint_fd,2097153,0),before)

    def test_missing_reconcile_proof_query_cannot_create_it(self):
        self.controller._append({'type':'INTENT','request':self.reconcile_req})
        with self.assertRaises(f.ControllerHold):self.reconciled()
        self.assertEqual(os.fstat(self.checkpoint_fd).st_size,0)

    def test_partial_checkpoint_preserved_without_overwrite(self):
        os.pwrite(self.checkpoint_fd,b'{partial',0)
        with self.assertRaises(f.ControllerHold):self.reconciled()
        self.assertEqual(os.pread(self.checkpoint_fd,100,0),b'{partial')

    def test_final_configuration_drift_holds(self):
        self.receiver.config['identity']['uid']=993
        with self.assertRaises(h.HandoffHold):self.reconciled()

    def test_preliminary_target_is_not_final(self):
        self.source_view.config['handoff']['release']='/opt/xuanjun-migration-s07/releases/domestic-r2'
        with self.assertRaises(RuntimeError):self.receiver_build()

    def test_host_start_or_route_stage_is_not_exposed(self):
        with self.assertRaises(h.HandoffHold):self.perform(original.request(self.plan,'start_owned',self.plan_digest))
        self.assertEqual(self.assignment_calls,0)

    def test_final_checkpoint_supports_bound_file_map_above_old_16k_limit(self):
        payload={'files':{('runtime/object-'+str(i)):('a'*64) for i in range(400)},'observed_at':1}
        self.assertGreater(len(c.encode(payload)),16384)
        stored=self.receiver.checkpoint(payload)
        self.assertEqual(stored,payload)
        self.assertEqual(self.receiver.checkpoint(payload,query_only=True),payload)

    def test_receipt_capacity_cannot_be_unbounded_or_boolean(self):
        from held_proof import HeldProof,ProofHold
        for limit in (False,0,2097153):
            with self.assertRaises(ProofHold):HeldProof(self.checkpoint_fd,self.controller,lambda:True,limit=limit)
        self.assertEqual(os.fstat(self.checkpoint_fd).st_size,0)

    def test_unverified_source_query_holds_without_checkpoint(self):
        self.source_view.verify=lambda *a:False
        with self.assertRaises(f.ControllerHold):self.reconciled()
        self.assertEqual(os.fstat(self.checkpoint_fd).st_size,0)

    def test_wrong_source_host_is_rejected_even_with_fixture_transport_ack(self):
        query=self.source_view.query
        def wrong(req,expected):
            proof=query(req,expected);proof['source_host']=h.HOST;return proof
        self.source_view.query=wrong;self.source_view.verify=lambda *a:True
        with self.assertRaises(f.ControllerHold):self.reconciled()
        self.assertEqual(os.fstat(self.checkpoint_fd).st_size,0)


class OwnerContractTests(OriginalJournalFixture,unittest.TestCase):
    def owner_plan(self):
        plan=copy.deepcopy(self.plan);plan.pop('independent_review_comment_id')
        plan['owner_authority']=copy.deepcopy(owner_contract.OWNER_AUTHORITY)
        return plan

    def test_owner_direct_plan_without_review_id(self):
        p=self.owner_plan();self.assertIs(owner_contract.Journal,original.Journal)
        self.assertEqual(owner_contract.validate_plan(p,original.digest(p),original.time.time()),p)

    def test_reviewer_field_does_not_create_owner_authority(self):
        with self.assertRaises(original.Hold):owner_contract.validate_plan(self.plan,original.digest(self.plan),original.time.time())

    def test_wrong_owner_scope_rejected(self):
        p=self.owner_plan();p['owner_authority']['scope']='UK_P2'
        with self.assertRaises(original.Hold):owner_contract.validate_plan(p,original.digest(p),original.time.time())

    def test_preliminary_release_rejected(self):
        p=self.owner_plan();p['release']='/opt/xuanjun-migration-s07/releases/domestic-r2'
        with self.assertRaises(original.Hold):owner_contract.validate_plan(p,original.digest(p),original.time.time())

    def test_expired_plan_still_rejected(self):
        p=self.owner_plan()
        with self.assertRaises(original.Hold):owner_contract.validate_plan(p,original.digest(p),p['expires_at'])

    def test_boolean_issue_time_is_not_timestamp(self):
        p=self.owner_plan();p['issued_at']=True
        with self.assertRaises(original.Hold):owner_contract.validate_plan(p,original.digest(p),original.time.time())
