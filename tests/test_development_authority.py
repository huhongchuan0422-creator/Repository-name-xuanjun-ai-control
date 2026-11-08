from __future__ import print_function

import copy
import os
import tempfile
import unittest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from development_authority import (authority_payload, close_verified_ledger,
    open_verified_ledger, sign_payload, verify_envelope)
from task_supervisor import Supervisor


class DevelopmentAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.TemporaryDirectory(); self.path=os.path.join(self.root.name,'formal.db')
        verifier=lambda owner,developer,task,digest: {
          'task_id':task,'contract_sha256':digest,
          'owner':{'issuer':'owner-auth','subject':'developer'},
          'developer':{'issuer':'native','subject':'developer'}}
        self.s=Supervisor(self.path,lambda:1000.0,verifier)
        self.s.register(dict(task_id='task-1',parent_task_id='parent',stage='dev',
          owner='developer',entry='WORK',checkpoint_sha256='a'*64,
          spec_sha256='b'*64,next_action='implement',dependencies=[],
          completion_conditions=['tests'],progress_deadline=1900,
          receipt_deadline=1100,started_deadline=1200,terminal_deadline=3000,
          handoff_deadline=1800),now=1000)
        self.s.register_development_contract('task-1',dict(task_id='task-1',
          spec_sha256='b'*64,checkpoint_sha256='a'*64,
          target_repository='owner/repo',target_base_sha='c'*40,entry='WORK',
          developer={'issuer':'native','subject':'developer'},allowed_files=['src/f.py'],
          trusted_reviewers=[{'issuer':'native','subject':'qa','key_id':'qa','role':'QA'},
          {'issuer':'native','subject':'sec','key_id':'sec','role':'SECURITY'}]))
        self.ticket=self.s.claim_development_writer('task-1','WORK',
          {'caller_id':'writer','run_id':'run','session_id':'session','gateway_id':'gateway'},
          'provider',['git:owner/repo/main'],2000,'owner-proof','developer-proof')
        self.s.db.execute('PRAGMA wal_checkpoint(TRUNCATE)'); self.s.close()
        self.private=Ed25519PrivateKey.generate(); self.public=self.private.public_key()
        self.trust={'issuer':'formal-issuer','instance_id':'provider-1','version':'3.0.1'}
        connection,fd,_=open_verified_ledger(self.path)
        try:
            payload=authority_payload(connection,{'task_id':'task-1','request_id':'nonce-1',
              'service_id':'reader-1'},self.trust,now=1001.0)
        finally: close_verified_ledger(connection,fd)
        self.envelope=sign_payload(payload,'anchor-1',self.private)
        self.expected={'issuer':'formal-issuer','instance_id':'provider-1','version':'3.0.1',
          'service_id':'reader-1','task_id':'task-1','attempt_id':self.ticket['attempt_id'],
          'lease_id':self.ticket['lease_id'],'fence':1,'epoch':1,
          'resource_scope_digest':self.ticket['resource_scope_digest'],
          'request_id':'nonce-1','now':1002.0,'max_age':5.0}

    def tearDown(self): self.root.cleanup()

    def test_positive_and_all_trusted_request_bindings(self):
        used=set()
        value=verify_envelope(self.envelope,self.public,{'anchor_id':'anchor-1'},
          self.expected,lambda key: False if key in used else not used.add(key))
        self.assertTrue(value['authority']['authorized'])
        with self.assertRaisesRegex(ValueError,'REPLAY'):
            verify_envelope(self.envelope,self.public,{'anchor_id':'anchor-1'},
              self.expected,lambda key: False if key in used else not used.add(key))
        for field in ('issuer','instance_id','version','service_id','task_id','attempt_id',
                      'lease_id','fence','epoch','resource_scope_digest','request_id'):
            wrong=dict(self.expected); wrong[field]='wrong'
            with self.assertRaisesRegex(ValueError,'BINDING'):
                verify_envelope(self.envelope,self.public,{'anchor_id':'anchor-1'},wrong)

    def test_schema_tamper_expiry_revocation_and_signature_are_denied(self):
        tampered=copy.deepcopy(self.envelope); tampered['payload']['schema']=2
        with self.assertRaisesRegex(ValueError,'DIGEST'):
            verify_envelope(tampered,self.public,{'anchor_id':'anchor-1'},self.expected)
        wrong_schema=sign_payload(dict(self.envelope['payload'],schema=2),'anchor-1',self.private)
        with self.assertRaisesRegex(ValueError,'SCHEMA_KIND'):
            verify_envelope(wrong_schema,self.public,{'anchor_id':'anchor-1'},self.expected)
        stale=dict(self.expected); stale['now']=2001.0
        with self.assertRaisesRegex(ValueError,'NOT_AUTHORIZED'):
            verify_envelope(self.envelope,self.public,{'anchor_id':'anchor-1'},stale)
        revoked=copy.deepcopy(self.envelope['payload'])
        revoked['authority']['state']='REVOKED'; revoked['authority']['authorized']=False
        revoked['revocation']['state']='REVOKED'
        with self.assertRaisesRegex(ValueError,'NOT_AUTHORIZED'):
            verify_envelope(sign_payload(revoked,'anchor-1',self.private),self.public,
                            {'anchor_id':'anchor-1'},self.expected)

    def test_formal_ledger_rejects_symlink_and_hardlink_alias(self):
        symlink=os.path.join(self.root.name,'link.db'); os.symlink(self.path,symlink)
        with self.assertRaisesRegex(ValueError,'REGULAR_FILE'):
            open_verified_ledger(symlink)
        hardlink=os.path.join(self.root.name,'hard.db'); os.link(self.path,hardlink)
        with self.assertRaisesRegex(ValueError,'FILE_IDENTITY'):
            open_verified_ledger(self.path,[hardlink])
        forbidden_link=os.path.join(self.root.name,'forbidden-link.db')
        os.symlink(self.path,forbidden_link)
        with self.assertRaisesRegex(ValueError,'FILE_IDENTITY'):
            open_verified_ledger(self.path,[forbidden_link])

    def test_corrupt_resource_scope_never_authorizes(self):
        writer=Supervisor(self.path,lambda:1002.0)
        writer.db.execute("UPDATE tasks SET resource_scope_digest=? WHERE task_id='task-1'",
                          ('0'*64,)); writer.db.commit(); writer.close()
        connection,fd,_=open_verified_ledger(self.path)
        try:
            payload=authority_payload(connection,{'task_id':'task-1','request_id':'nonce-2',
              'service_id':'reader-1'},self.trust,now=1002.0)
        finally: close_verified_ledger(connection,fd)
        self.assertFalse(payload['authority']['authorized'])

    def test_reader_requires_explicit_exact_trust_inputs(self):
        with self.assertRaisesRegex(ValueError,'TRUSTED_EXPECTATIONS'):
            verify_envelope(self.envelope,self.public,{},self.expected)
        with self.assertRaisesRegex(ValueError,'TRUSTED_EXPECTATIONS'):
            verify_envelope(self.envelope,object(),{'anchor_id':'anchor-1'},self.expected)


if __name__ == '__main__': unittest.main()
