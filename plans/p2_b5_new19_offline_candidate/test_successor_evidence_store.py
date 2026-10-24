"""Isolated protected registrar records; no live enrollment or cloud reads."""
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
        self.store.revoke_exact(self.binding,'revoke1')
        with self.assertRaisesRegex(Hold,'SUCCESSOR_EVIDENCE_REVOKED'):
            authority.approve_c53_b5_exposure_close(JOB)

    def test_provenance_manual_witness_is_not_grant(self):
        rows=[dict(request_id=rid,object_ref='b5-material-%02d'%(i+1),
                   invoke_id='invoke%02d'%i,bytes=4900 if i<18 else 5392,
                   sha256='%064x'%i,result_ref='tool-result-%02d'%i)
              for i,rid in enumerate(self.binding['ids'])]
        payload=dict(proof_sha256='b'*64,custody_receipt_sha256='c'*64,
                     rows=rows,subject=SUBJECT,scope='project.files.read',
                     catalog_sha256='a'*64,recipient=RECIPIENT)
        self.register('b5_http',payload)
        authority=object.__new__(ExistingRequestAuthority)
        authority.evidence_store=self.store
        authority.batch_id='batch1';authority.attempt_id='attempt1'
        authority.window_start=1000;authority.request_ids=tuple(self.binding['ids'])
        authority.catalog_sha='a'*64
        proof=dict(state='B5_HTTP_BYTES_VALIDATED_SOURCE_ATTESTATION_PENDING',
                   bytes=93592,objects=19,close_approval='NOT_PROVEN',
                   proof_sha256='b'*64)
        result=authority.verify_b5_http_provenance(proof,'a'*64,
                                                   tuple(self.binding['ids']))
        self.assertEqual(result['source'],'ORIGINAL_UK_B5_TOOL_HUMAN_WITNESS')
        proof['proof_sha256']='d'*64
        with self.assertRaisesRegex(c53.Hold,'B5_ORIGINAL_TOOL_WITNESS_CHANGED'):
            authority.verify_b5_http_provenance(proof,'a'*64,
                                                tuple(self.binding['ids']))

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
