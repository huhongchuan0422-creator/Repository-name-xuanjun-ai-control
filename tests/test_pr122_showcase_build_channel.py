"""Root bridge simulation; no actual systemctl or domestic root operations."""
import base64
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
from scripts import pr122_showcase_build_channel as c
from scripts import pr122_showcase_protected_build as b
from scripts import pr122_showcase_trust as t
from scripts.pr122_showcase import canonical,sha
from tests import test_pr122_showcase_protected_build as fixtures

@unittest.skipUnless(os.geteuid()==0,'Root-owned isolated files')
class ChannelTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.BuilderTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        td=tempfile.TemporaryDirectory(dir='/root');self.addCleanup(td.cleanup);self.root=Path(td.name)
        self.base=self.root/'builder';self.base.mkdir(mode=0o700)
        self.request=self.root/'request.json';self.trust=self.root/'trust.json'
        self.trust.write_bytes(canonical(self.fixture.policy));self.trust.chmod(0o600)
        for target,name,value in [(b,'BASE',self.base),(b,'REQUEST',self.request),(t,'TRUST',self.trust)]:
            p=mock.patch.object(target,name,value);p.start();self.addCleanup(p.stop)
        self.value={k:self.fixture.request[k] for k in ('schema','mechanism_manifest_sha256','shell_tar_sha256','legacy_pages_sha256','reviewer_logins')}
        self.calls=[]
    def command(self,args,**kwargs):
        self.calls.append(args);request=json.loads(self.request.read_bytes());raw=self.request.read_bytes()
        stage=self.base/('build-'+sha(raw));stage.mkdir(mode=0o700)
        result=b.construct(request,stage,None,self.fixture.api)
        result.update(runtime={'effective':True,'mount_namespace':'SYNTHETIC_SANDBOX_NS'},mechanism_source_commit='e'*40,request_sha256=sha(raw),trust_snapshot_sha256=sha(self.trust.read_bytes()),mechanism_manifest_sha256=self.value['mechanism_manifest_sha256'])
        os.rename(stage/'SHOWCASE_RELEASE.pending',stage/'SHOWCASE_RELEASE.tar.gz');(stage/'SHOWCASE_RELEASE.tar.gz').chmod(0o600)
        b.durable_write(stage/'BUILD_RECEIPT.json',canonical(result));return SimpleNamespace(returncode=0)
    def test_build_and_export_full_synthetic_publication_transport(self):
        result=c.execute(self.value,self.fixture.api,self.command)
        self.assertEqual(result['state'],'BUILT');self.assertEqual(self.calls,[['/usr/bin/systemctl','start',c.UNIT]])
        envelope=c.export(self.value,self.fixture.api)
        self.assertEqual(sha(base64.b64decode(envelope['tar_base64'])),result['tar_sha256'])
        self.assertEqual(envelope['receipt']['source_commit'],self.fixture.commit)
        again=c.execute(self.value,self.fixture.api,self.command)
        self.assertTrue(again['duplicate_build_skipped']);self.assertEqual(len(self.calls),1)
    def test_unenrolled_comment_does_not_create_request_or_start_unit(self):
        self.trust.write_bytes(canonical({**self.fixture.policy,'anchors':{}}))
        result=c.execute(self.value,self.fixture.api,self.command)
        self.assertEqual(result['state'],'WAIT_OWNER_CONTENT_ENROLLMENT');self.assertFalse(self.request.exists());self.assertFalse(self.calls)
    def test_failure_consumes_attempt_and_holds_without_blind_retry(self):
        def failed(*args,**kwargs):return SimpleNamespace(returncode=1)
        with self.assertRaisesRegex(ValueError,'BUILDER_UNIT_FAILED'):c.execute(self.value,self.fixture.api,failed)
        with self.assertRaisesRegex(ValueError,'HOLD_NO_RETRY'):c.execute(self.value,self.fixture.api,self.command)
        self.assertFalse(self.calls)
    def test_modified_comment_cannot_start_unit(self):
        self.fixture.comment['body']+=' '
        with self.assertRaisesRegex(ValueError,'EXACT_REVIEW_ANCHOR'):c.execute(self.value,self.fixture.api,self.command)
        self.assertFalse(self.calls)
    def test_export_after_trust_revocation_is_rejected(self):
        c.execute(self.value,self.fixture.api,self.command)
        revoked=copy.deepcopy(self.fixture.policy);revoked['revoked_review_ids']=[7];self.trust.write_bytes(canonical(revoked))
        with self.assertRaisesRegex(ValueError,'EXPORT_REVIEW_DRIFT'):c.export(self.value,self.fixture.api)
    def test_foreign_request_is_not_overwritten(self):
        self.request.write_bytes(b'{}');self.request.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'FOREIGN_BUILDER_REQUEST'):c.execute(self.value,self.fixture.api,self.command)
        self.assertEqual(self.request.read_bytes(),b'{}');self.assertFalse(self.calls)
    def test_output_tampering_rejected(self):
        result=c.execute(self.value,self.fixture.api,self.command)
        (self.base/result['stage_name']/'SHOWCASE_RELEASE.tar.gz').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'BUILDER_EXPORT_HASH'):c.export(self.value,self.fixture.api)
    def test_unknown_state_stops_before_network(self):
        c.store(self.base/'CHANNEL_STATE.json',{'state':'PREPARING'})
        def no_network(path):raise AssertionError('must not fetch')
        with self.assertRaisesRegex(ValueError,'HOLD_NO_RETRY'):c.execute(self.value,no_network,self.command)
    def test_timeout_persists_hold(self):
        def timeout(*args,**kwargs):raise subprocess.TimeoutExpired(args[0],250)
        with self.assertRaises(subprocess.TimeoutExpired):c.execute(self.value,self.fixture.api,timeout)
        self.assertEqual(json.loads((self.base/'CHANNEL_STATE.json').read_bytes())['state'],'HOLD')
    def test_wrapper_actual_executable_interpreter_and_sudoers(self):
        wrapper=self.root/'entry';wrapper.write_bytes(Path('deploy/pr122-showcase/build-channel').read_bytes());wrapper.chmod(0o755)
        result=subprocess.run([str(wrapper),'inspect'],capture_output=True,text=True,timeout=10)
        self.assertNotIn('Unknown option',result.stderr);self.assertNotEqual(result.returncode,0)
        result=subprocess.run(['/usr/sbin/visudo','-cf','deploy/pr122-showcase/build-sudoers'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
