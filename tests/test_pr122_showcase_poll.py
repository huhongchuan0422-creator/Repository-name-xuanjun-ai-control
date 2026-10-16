"""No network/provider credentials used: explicit fake transport and approvals."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from scripts import pr122_showcase_promote as p
from scripts import pr122_showcase_poll as poller
from scripts.pr122_showcase import canonical

@unittest.skipUnless(os.geteuid()==0,'Disposable root namespace')
class PollTests(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory(dir='/root',prefix='showcase-poll-test-');self.addCleanup(td.cleanup);self.root=Path(td.name);self.base=self.root/'base';self.base.mkdir()
        patch=mock.patch.object(p,'BASE',self.base);patch.start();self.addCleanup(patch.stop);self.engine=p.load_engine()
        self.token=self.root/'token';self.token.write_text('TEST_ONLY_NOT_A_REAL_TOKEN');self.token.chmod(0o600)
        self.policy={'publishers':['owner'],'reviewers':['auditor'],'github_token_file':str(self.token)}
    def test_no_approved_event_has_no_publication_effect(self):
        calls=[]
        def fetch(path):calls.append(path);return []
        self.assertEqual(poller.poll(self.policy,self.engine,fetch)['state'],'NO_NEW_APPROVED_RELEASE')
        self.assertEqual(list(self.base.iterdir()),[]);self.assertEqual(len(calls),1)
    def test_unknown_previous_transaction_stops_before_network_or_retry(self):
        (self.base/'transactions').mkdir(mode=0o700);(self.base/'transactions/showcase-1.json').write_bytes(canonical({'state':'ACTIVATION_INTENT'}))
        with self.assertRaisesRegex(ValueError,'UNKNOWN_TRANSACTION'):
            poller.poll(self.policy,self.engine,lambda *_:self.fail('Unexpected network request'))
    def test_checked_pointer_without_https_receipt_remains_unknown(self):
        (self.base/'transactions').mkdir(mode=0o700);(self.base/'transactions/showcase-1.json').write_bytes(canonical({'state':'CHECKED'}))
        with self.assertRaisesRegex(ValueError,'HTTPS_RESULT_UNKNOWN'):
            poller.poll(self.policy,self.engine,lambda *_:self.fail('Unexpected network request'))
    def test_nonprivate_credential_is_not_used(self):
        self.token.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'TOKEN_MODE'):
            poller.poll(self.policy,self.engine,lambda *_:self.fail('Unexpected network request'))
    def test_consumed_artifact_is_not_applied_again(self):
        folder=self.base/'inputs/showcase-1';folder.mkdir(parents=True,mode=0o700)
        comments=[{'id':90,'user':{'login':'owner'},'body':'XUANJUN_SHOWCASE_RELEASE\n'+json.dumps({'artifact_id':1,'expires_unix':9999999999})}]
        self.assertEqual(poller.poll(self.policy,self.engine,lambda _:comments,lambda *_:self.fail('Unexpected artifact download'))['state'],'NO_NEW_APPROVED_RELEASE')

if __name__=='__main__':unittest.main()
