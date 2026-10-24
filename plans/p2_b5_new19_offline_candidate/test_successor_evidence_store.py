"""Isolated protected registrar records; no live enrollment or cloud reads."""
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE/'reused-6825'),
              str(HERE/'successor_controller')]
from pr17_b5_successor_witness import (SuccessorEvidenceStore, Hold,
                                        JOB, COMMIT, PROJECT, RECIPIENT, SUBJECT)
from pr17_b5_successor_authority import ExistingRequestAuthority
from pr17_b5_successor_backend import R2HostBackend
import pr17_b5_successor_binder as binder
import pr17_b5_successor_review as c53


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'records'
        self.root.mkdir(mode=0o700)
        (self.root/'register.lock').write_bytes(b'')
        os.chmod(self.root/'register.lock',0o600)
        self.now=1001
        self.store=SuccessorEvidenceStore(str(self.root),enabled=True,
                         test_only=True,clock=lambda:self.now)
        self.binding=dict(batch='batch1',job=JOB,attempt='attempt1',
              ids=['request%02d'%i for i in range(19)],catalog_sha256='a'*64,
              recipient=RECIPIENT,project=PROJECT,subject=SUBJECT,commit=COMMIT,
              valid_from=1000,valid_until=4600)

    def register(self,kind,payload):
        return self.store.register_exact(self.binding,kind,
              source_id='original-'+kind.lower(),source_raw=b'original receipt',
              witness_identity='uk-coordinator',payload=payload)

    def test_decisions_are_distinct_and_persist_across_process(self):
        restore=dict(scope='PRE_START_RESTORE',job=JOB,decision_id='decision1',
                     approved=True,phase='PRE_START')
        self.register('PRE_START_RESTORE',restore)
        authority=object.__new__(ExistingRequestAuthority)
        authority.evidence_store=self.store
        authority.batch_id=self.binding['batch']
        authority.attempt_id=self.binding['attempt']
        authority.window_start=self.binding['valid_from']
        authority.request_ids=tuple(self.binding['ids'])
        authority.catalog_sha=self.binding['catalog_sha256']
        self.assertTrue(authority.approve_precise_pre_start_restore(JOB)['approved'])
        with self.assertRaises(FileNotFoundError):
            authority.approve_c53_b5_exposure_close(JOB)
        program='''import sys
sys.path[:0]=sys.argv[1].split(':')
from pr17_b5_successor_witness import SuccessorEvidenceStore,JOB,COMMIT,PROJECT,RECIPIENT,SUBJECT
s=SuccessorEvidenceStore(sys.argv[2],enabled=True,test_only=True,clock=lambda:1002)
b=dict(batch='batch1',job=JOB,attempt='attempt1',ids=['request%02d'%i for i in range(19)],catalog_sha256='a'*64,recipient=RECIPIENT,project=PROJECT,subject=SUBJECT,commit=COMMIT,valid_from=1000,valid_until=4600)
assert s.read_exact(b,'PRE_START_RESTORE')[0]['payload']['decision_id']=='decision1'
'''
        paths=':'.join(map(str,[HERE,HERE/'reused-6825',HERE/'successor_controller']))
        subprocess.run([sys.executable,'-I','-B','-c',program,paths,str(self.root)],
                       check=True,timeout=10)
        self.register('B5_EXPOSURE_CLOSE',dict(scope='B5_EXPOSURE_CLOSE',
             job=JOB,decision_id='decision2',approved=True,phase='AFTER_B5_HTTP'))
        self.assertTrue(authority.approve_c53_b5_exposure_close(JOB)['approved'])
        backend=object.__new__(R2HostBackend)
        backend.authority=authority;backend.job=JOB
        self.assertEqual(backend._receipt('approve_precise_pre_start_restore',JOB)
                         ['scope'],'PRE_START_RESTORE')
        self.assertEqual(backend._receipt('approve_c53_b5_exposure_close',JOB)
                         ['scope'],'B5_EXPOSURE_CLOSE')
        self.store.revoke_exact(self.binding,'revoke1')
        with self.assertRaisesRegex(Hold,'SUCCESSOR_EVIDENCE_REVOKED'):
            authority.approve_c53_b5_exposure_close(JOB)

    def test_provenance_manual_witness_is_not_grant(self):
        rows=[dict(request_id=rid,object_ref='b5-material-%02d'%(i+1),
                   invoke_id='invoke%02d'%i,bytes=4900 if i<18 else 5392,
                   sha256='%064x'%i,result_ref='tool-result-%02d'%i)
              for i,rid in enumerate(self.binding['ids'])]
        custody_sha='c'*64
        proof_sha=c53.sha(c53.canon(dict(catalog_sha256='a'*64,
            project=PROJECT,recipient=RECIPIENT,
            custody_receipt_sha256=custody_sha,
            rows=[{k:r[k] for k in ('request_id','object_ref','invoke_id',
                                    'bytes','sha256')} for r in rows])))
        payload=dict(proof_sha256=proof_sha,custody_receipt_sha256=custody_sha,
                     rows=rows,subject=SUBJECT,scope='project.files.read',
                     catalog_sha256='a'*64,recipient=RECIPIENT)
        changed=dict(payload,rows=[dict(r) for r in rows])
        changed['rows'][0]['object_ref']='b5-material-02'
        with self.assertRaisesRegex(Hold,'SUCCESSOR_B5_PROVENANCE_ROWS'):
            self.register('b5_http',changed)
        self.register('b5_http',payload)
        authority=object.__new__(ExistingRequestAuthority)
        authority.evidence_store=self.store
        authority.batch_id='batch1';authority.attempt_id='attempt1'
        authority.window_start=1000;authority.request_ids=tuple(self.binding['ids'])
        authority.catalog_sha='a'*64
        proof=dict(state='B5_HTTP_BYTES_VALIDATED_SOURCE_ATTESTATION_PENDING',
                   bytes=93592,objects=19,close_approval='NOT_PROVEN',
                   proof_sha256=proof_sha)
        result=authority.verify_b5_http_provenance(proof,'a'*64,
                                                   tuple(self.binding['ids']))
        self.assertEqual(result['source'],'ORIGINAL_UK_B5_TOOL_HUMAN_WITNESS')
        proof['proof_sha256']='d'*64
        with self.assertRaisesRegex(c53.Hold,'B5_ORIGINAL_TOOL_WITNESS_CHANGED'):
            authority.verify_b5_http_provenance(proof,'a'*64,
                                                tuple(self.binding['ids']))
        for key in ('sha256','bytes'):
            alternate=dict(payload,rows=[dict(r) for r in rows])
            alternate['rows'][0][key]=('d'*64 if key=='sha256' else 4901)
            if key=='bytes':alternate['rows'][-1]['bytes']-=1
            with self.assertRaisesRegex(Hold,'SUCCESSOR_B5_PROOF_CHANGED'):
                self.store._payload('b5_http',alternate,self.binding)
        alternate=dict(payload,custody_receipt_sha256='d'*64)
        with self.assertRaisesRegex(Hold,'SUCCESSOR_B5_PROOF_CHANGED'):
            self.store._payload('b5_http',alternate,self.binding)

    def test_transaction_close_requires_distinct_provenance_and_close_records(self):
        rows=[dict(request_id=rid,object_ref='b5-material-%02d'%(i+1),
                   invoke_id='invoke%02d'%i,bytes=4900 if i<18 else 5392,
                   sha256='%064x'%i,result_ref='tool-result-%02d'%i)
              for i,rid in enumerate(self.binding['ids'])]
        custody_sha='c'*64
        proof_sha=c53.sha(c53.canon(dict(catalog_sha256='a'*64,
            project=PROJECT,recipient=RECIPIENT,
            custody_receipt_sha256=custody_sha,
            rows=[{k:r[k] for k in ('request_id','object_ref','invoke_id',
                                    'bytes','sha256')} for r in rows])))
        self.register('b5_http',dict(proof_sha256=proof_sha,
            custody_receipt_sha256=custody_sha,rows=rows,subject=SUBJECT,
            scope='project.files.read',catalog_sha256='a'*64,recipient=RECIPIENT))
        authority=object.__new__(ExistingRequestAuthority)
        authority.evidence_store=self.store
        authority.batch_id=self.binding['batch'];authority.attempt_id=self.binding['attempt']
        authority.window_start=self.binding['valid_from']
        authority.request_ids=tuple(self.binding['ids']);authority.catalog_sha='a'*64
        spec=binder.verify_spec_bytes((HERE/'SUCCESSOR_SPEC.json').read_bytes())
        backend=object.__new__(R2HostBackend)
        backend.authority=authority;backend.job=JOB;backend.spec=spec
        backend.expected_ids=tuple(self.binding['ids']);backend.reserved=False
        bundle={'catalog_sha':'a'*64,
            'requests':[{'request_id':rid} for rid in self.binding['ids']],
            'files':{p:b'' for p in c53.CONFIGS+c53.SLOTS}}
        backend.bundle=bundle
        backend.successor_evidence_action=R2HostBackend.successor_evidence_action.__get__(backend)
        backend.verify_b5_http_provenance=R2HostBackend.verify_b5_http_provenance.__get__(backend)
        backend.approve_precise_b5_exposure_close=R2HostBackend.approve_precise_b5_exposure_close.__get__(backend)
        backend.witness_action=lambda:contextlib.nullcontext()
        backend.successor_release_action=lambda:contextlib.nullcontext()
        effects=[]
        def close_leaf():
            # The leaf independently re-reads the close record just like the
            # production closeout before any service/config effect.
            receipt=R2HostBackend._receipt(backend,'approve_c53_b5_exposure_close',JOB)
            self.assertEqual(receipt['scope'],'B5_EXPOSURE_CLOSE')
            effects.append('close')
        backend.close_b5_exposure_success_successor_only=close_leaf
        tx=c53.Transaction(spec,bundle,backend);tx.stage='READY_FOR_B5_HTTP_NOT_RECEIVED'
        proof={'state':'B5_HTTP_BYTES_VALIDATED_SOURCE_ATTESTATION_PENDING',
               'bytes':93592,'objects':19,'close_approval':'NOT_PROVEN',
               'proof_sha256':proof_sha}
        with self.assertRaises(FileNotFoundError):
            tx.close_after_b5_http(proof)
        self.assertEqual(effects,[])
        self.register('B5_EXPOSURE_CLOSE',dict(scope='B5_EXPOSURE_CLOSE',
            job=JOB,decision_id='close-independent',approved=True,
            phase='AFTER_B5_HTTP'))
        result=tx.close_after_b5_http(proof)
        self.assertEqual(result,{'state':'RECEIVED_VERIFIED_19_CLOSED',
            'received':19,'bytes':93592,'installed':False})
        self.assertEqual(effects,['close'])
        self.assertEqual(tx.stage,'CLOSED_RECEIVED_19')

    def test_action_rechecks_complete_row_before_side_effect(self):
        payload=dict(scope='PRE_START_RESTORE',job=JOB,decision_id='decision1',
                     approved=True,phase='PRE_START')
        self.register('PRE_START_RESTORE',payload)
        path=self.root/'restore.json'
        row=json.loads(path.read_bytes());row.pop('source_id')
        path.write_bytes(c53.canon(row)+b'\n')
        entered=[]
        with self.assertRaisesRegex(Hold,'SUCCESSOR_EVIDENCE_BINDING'):
            with self.store.action_exact(self.binding,'PRE_START_RESTORE'):
                entered.append('command')
        self.assertEqual(entered,[])
        with self.assertRaisesRegex(Hold,'SUCCESSOR_EVIDENCE_BINDING'):
            self.store.read_exact(self.binding,'PRE_START_RESTORE')

    def test_duplicate_wrong_scope_partial_and_expiry_hold(self):
        restore=dict(scope='PRE_START_RESTORE',job=JOB,decision_id='decision1',
                     approved=True,phase='PRE_START')
        self.register('PRE_START_RESTORE',restore)
        with self.assertRaisesRegex(Hold,'SUCCESSOR_EVIDENCE_ALREADY_REGISTERED'):
            self.register('PRE_START_RESTORE',restore)
        with self.assertRaisesRegex(Hold,'SUCCESSOR_DECISION_SCOPE'):
            self.register('B5_EXPOSURE_CLOSE',restore)
        (self.root/'.close.json.pending').write_bytes(b'partial')
        with self.assertRaisesRegex(Hold,'SUCCESSOR_EVIDENCE_PARTIAL_OR_UNKNOWN'):
            self.store.read_exact(self.binding,'PRE_START_RESTORE')
        (self.root/'.close.json.pending').unlink()
        self.now=4600
        with self.assertRaisesRegex(Hold,'WITNESS_EXPIRED'):
            self.store.read_exact(self.binding,'PRE_START_RESTORE')

    def test_protected_mode_and_link_rejected(self):
        restore=dict(scope='PRE_START_RESTORE',job=JOB,decision_id='decision1',
                     approved=True,phase='PRE_START')
        self.register('PRE_START_RESTORE',restore)
        os.chmod(self.root/'restore.json',0o644)
        with self.assertRaisesRegex(Hold,'WITNESS_FILE_PROTECTION'):
            self.store.read_exact(self.binding,'PRE_START_RESTORE')
        os.chmod(self.root/'restore.json',0o600)
        os.chmod(self.root,0o755)
        with self.assertRaisesRegex(Hold,'WITNESS_ROOT_PROTECTION'):
            self.store.read_exact(self.binding,'PRE_START_RESTORE')

    def test_active_action_fds_reject_closed_reused_and_rebound_lock(self):
        payload=dict(scope='B5_EXPOSURE_CLOSE',job=JOB,
                     decision_id='decision-fd',approved=True,phase='AFTER_B5_HTTP')
        self.register('B5_EXPOSURE_CLOSE',payload)
        with self.store.action_exact(self.binding,'B5_EXPOSURE_CLOSE'):
            fds=self.store.active_action_fds(
                self.binding,('B5_EXPOSURE_CLOSE',))
            self.assertEqual(len(fds),2)
            lock=fds[1]
            os.close(lock)
            reused=os.open('/dev/null',os.O_RDONLY)
            try:
                self.assertEqual(reused,lock)
                with self.assertRaisesRegex(Hold,
                        'SUCCESSOR_EVIDENCE_LEASE_IDENTITY_CHANGED'):
                    self.store.active_action_fds(
                        self.binding,('B5_EXPOSURE_CLOSE',))
            finally:
                # action_exact finalizer owns this descriptor number.
                if reused!=lock:os.close(reused)
        # New action: replace the named lock while the original inode remains
        # held; the dirfd/name identity check must reject it.
        with self.store.action_exact(self.binding,'B5_EXPOSURE_CLOSE'):
            old=self.root/'register.lock'
            moved=self.root/'register.lock.old'
            old.rename(moved)
            old.write_bytes(b'');old.chmod(0o600)
            try:
                with self.assertRaisesRegex(Hold,
                        'SUCCESSOR_EVIDENCE_LEASE_IDENTITY_CHANGED'):
                    self.store.active_action_fds(
                        self.binding,('B5_EXPOSURE_CLOSE',))
            finally:
                old.unlink();moved.rename(old)

    def test_nested_lease_revocation_waits_until_outer_release(self):
        self.register('PRE_START_RESTORE',dict(scope='PRE_START_RESTORE',
            job=JOB,decision_id='nested-restore',approved=True,phase='PRE_START'))
        self.register('B5_EXPOSURE_CLOSE',dict(scope='B5_EXPOSURE_CLOSE',
            job=JOB,decision_id='nested-close',approved=True,phase='AFTER_B5_HTTP'))
        entered=threading.Event();release=threading.Event();done=threading.Event()
        def action():
            with self.store.action_exact(self.binding,'PRE_START_RESTORE'):
                with self.store.action_exact(self.binding,'B5_EXPOSURE_CLOSE'):
                    self.assertEqual(len(self.store.active_action_fds(
                        self.binding,('PRE_START_RESTORE','B5_EXPOSURE_CLOSE'))),4)
                    entered.set();release.wait(2)
        thread=threading.Thread(target=action);thread.start()
        self.assertTrue(entered.wait(2))
        def revoke():
            self.store.revoke_exact(self.binding,'nested-revoke');done.set()
        revoker=threading.Thread(target=revoke);revoker.start()
        self.assertFalse(done.wait(.05))
        release.set();thread.join(2);revoker.join(2)
        self.assertTrue(done.is_set())
        with self.assertRaisesRegex(Hold,'SUCCESSOR_EVIDENCE_REVOKED'):
            self.store.read_exact(self.binding,'B5_EXPOSURE_CLOSE')

    def test_revocation_serializes_with_started_action(self):
        payload=dict(scope='B5_EXPOSURE_CLOSE',job=JOB,
                     decision_id='decision2',approved=True,phase='AFTER_B5_HTTP')
        self.register('B5_EXPOSURE_CLOSE',payload)
        entered=threading.Event();release=threading.Event();completed=threading.Event()
        def action():
            with self.store.action_exact(self.binding,'B5_EXPOSURE_CLOSE'):
                entered.set();release.wait(2)
        thread=threading.Thread(target=action);thread.start()
        self.assertTrue(entered.wait(2))
        def revoke():
            self.store.revoke_exact(self.binding,'withdrawn');completed.set()
        revoker=threading.Thread(target=revoke);revoker.start()
        self.assertFalse(completed.wait(.05))
        release.set();thread.join(2);revoker.join(2)
        self.assertTrue(completed.is_set())
        with self.assertRaisesRegex(Hold,'SUCCESSOR_EVIDENCE_REVOKED'):
            with self.store.action_exact(self.binding,'B5_EXPOSURE_CLOSE'):
                self.fail('action started after completed revoke')

if __name__=='__main__':unittest.main()
