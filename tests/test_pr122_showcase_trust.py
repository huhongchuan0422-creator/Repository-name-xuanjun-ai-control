"""Synthetic Owner custody records; no production enrollment or approval."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock
from scripts import pr122_showcase_trust as t
from scripts import pr122_showcase_sources as source


def anchored(comment, scope):
    now = int(time.time())
    evidence = 'a' * 64
    return {'schema': 1, 'source_writer_principal': 'test-writer',
            'reviewers': {'test-independent': {'status': 'ACTIVE', 'custody_evidence_sha256': evidence}},
            'revoked_review_ids': [], 'anchors': {str(comment['id']): {
                'body_sha256': t.sha(comment['body'].encode()), 'scope': scope,
                'reviewer_principal': 'test-independent', 'custody_evidence_sha256': evidence,
                'issued_unix': now - 1, 'expires_unix': now + 600}}}

class TrustTests(unittest.TestCase):
    def setUp(self):
        self.comment = {'id': 7, 'body': 'XUANJUN_SHOWCASE_REVIEW\n'+json.dumps({
            'reviewer_role': 'INDEPENDENT_AUDITOR', 'decision': 'PUBLIC_CONTENT_APPROVED',
            'commit': 'a'*40, 'ci_run_id': 9, 'object_sha256': ['b'*64]})}
        self.trust = anchored(self.comment, 'CONTENT')

    def test_exact_independent_anchor_accepted(self):
        for scope in t.SCOPES:
            with self.subTest(scope=scope):
                self.assertEqual(t.verify(self.comment, scope, anchored(self.comment, scope))['scope'], scope)

    def test_author_role_string_and_allowlisted_login_cannot_release(self):
        c={**self.comment, 'user': {'login':'same-github-account'}, 'issue_url':'https://api.github.com/repos/'+source.REPO+'/issues/122'}
        policy={**self.trust,'anchors':{}}
        with mock.patch.object(t, 'load', return_value=policy):
            with self.assertRaisesRegex(ValueError,'OWNER_REVIEW_ANCHOR_REQUIRED'):
                source.verify_review(7,[],{'same-github-account'},lambda path:c)

    def test_author_cannot_be_independent_subject(self):
        self.trust['source_writer_principal']='test-independent'
        with self.assertRaisesRegex(ValueError,'INDEPENDENT_ENROLLED_REVIEWER'): t.verify(self.comment,'CONTENT',self.trust)

    def test_all_binding_mutations_fail(self):
        payload=json.loads(self.comment['body'].split('\n',1)[1])
        for key,value in [('decision','PUBLIC_CONTENT_REVOKED'),('commit','c'*40),('ci_run_id',10),('object_sha256',['c'*64])]:
            with self.subTest(key=key):
                changed={**self.comment,'body':'XUANJUN_SHOWCASE_REVIEW\n'+json.dumps({**payload,key:value})}
                with self.assertRaisesRegex(ValueError,'EXACT_REVIEW_ANCHOR'):t.verify(changed,'CONTENT',self.trust)

    def test_revoked_inactive_expired_scope_and_custody_fail(self):
        variants=[]
        a=copy.deepcopy(self.trust);a['revoked_review_ids']=[7];variants.append(a)
        a=copy.deepcopy(self.trust);a['reviewers']['test-independent']['status']='REVOKED';variants.append(a)
        a=copy.deepcopy(self.trust);a['anchors']['7']['expires_unix']=0;variants.append(a)
        a=copy.deepcopy(self.trust);a['anchors']['7']['scope']='PUBLICATION';variants.append(a)
        a=copy.deepcopy(self.trust);a['anchors']['7']['custody_evidence_sha256']='b'*64;variants.append(a)
        for policy in variants:
            with self.subTest(policy=policy):
                with self.assertRaises(ValueError):t.verify(self.comment,'CONTENT',policy)

    @unittest.skipUnless(os.geteuid()==0,'Root-owned isolated fixture')
    def test_loader_enforces_root_private_file_and_no_symlink(self):
        with tempfile.TemporaryDirectory(dir='/root') as td:
            p=Path(td)/'trust.json';p.write_text(json.dumps(self.trust));p.chmod(0o600)
            with mock.patch.object(t,'TRUST',p):
                self.assertEqual(t.load(),self.trust)
                p.chmod(0o644)
                with self.assertRaisesRegex(ValueError,'OWNER_TRUST_FILE'):t.load()
                p.chmod(0o600);link=Path(td)/'link';link.symlink_to(p)
                with mock.patch.object(t,'TRUST',link):
                    with self.assertRaisesRegex(ValueError,'OWNER_TRUST_PATH'):t.load()

    def test_missing_protected_trust_is_fail_closed(self):
        with mock.patch.object(t,'load',side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):t.verify(self.comment,'CONTENT')

if __name__=='__main__':unittest.main()
