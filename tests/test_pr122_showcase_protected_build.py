"""Data-only builder tests. All approvals/custody records are synthetic fixtures."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock
from scripts import pr122_showcase_protected_build as b
from scripts import pr122_showcase as s
from scripts import pr122_showcase_trust as trust
from tests.test_pr122_showcase_trust import anchored

ROOT=Path(__file__).resolve().parents[1]

class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.stage=Path(self.temp.name)
        self.rows=[];self.blobs={}
        for p in sorted((ROOT/'showcase').rglob('*')):
            if not p.is_file():continue
            name=p.relative_to(ROOT).as_posix()
            if not (name.startswith('showcase/projects/') or name=='showcase/published-main-r2.json'):continue
            raw=p.read_bytes();h=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            self.rows.append({'path':name,'type':'blob','mode':'100644','sha':h});self.blobs[h]={'encoding':'base64','content':base64.b64encode(raw).decode()}
        self.commit='a'*40;self.tree='f'*40
        objects=s.discover(ROOT/'showcase')
        self.review={'decision':'PUBLIC_CONTENT_APPROVED','reviewer_role':'INDEPENDENT_AUDITOR','commit':self.commit,'ci_run_id':9,'object_sha256':[s.sha(s.canonical(o)) for o in objects],'module_admission_sha256':[]}
        self.comment={'id':7,'user':{'login':'fixture-reviewer'},'issue_url':'https://api.github.com/repos/'+b.REPO+'/issues/122','body':'XUANJUN_SHOWCASE_REVIEW\n'+json.dumps(self.review)}
        self.policy=anchored(self.comment,'CONTENT')
        now=int(time.time());self.request={'schema':1,'commit':self.commit,'ci_run_id':9,'review_comment_ids':[7],'reviewer_logins':['fixture-reviewer'],'mechanism_manifest_sha256':'a'*64,'shell_tar_sha256':'b'*64,'legacy_pages_sha256':s.sha((ROOT/'showcase/published-main-r2.json').read_bytes()),'issued_unix':now-1,'expires_unix':now+600}
        patch=mock.patch.object(trust,'load',side_effect=lambda:copy.deepcopy(self.policy));patch.start();self.addCleanup(patch.stop)
        self.calls=[]
    def api(self,path):
        self.calls.append(path)
        if path=='actions/runs/9':return {'head_sha':self.commit,'status':'completed','conclusion':'success','workflow_id':b.WORKFLOW_ID,'event':'push'}
        if path.startswith('git/commits/'):return {'sha':self.commit,'tree':{'sha':self.tree}}
        if path.startswith('git/trees/'):return {'sha':self.tree,'truncated':False,'tree':self.rows}
        if path.startswith('git/blobs/'):return self.blobs[path.rsplit('/',1)[1]]
        if path=='issues/comments/7':return self.comment
        raise AssertionError(path)
    def test_reviewed_data_builds_nonpreview_candidate_without_activation(self):
        result=b.construct(self.request,self.stage,None,self.api)
        self.assertFalse(result['preview_only']);self.assertEqual(result['production_changes'],0)
        self.assertTrue((self.stage/'SHOWCASE_RELEASE.pending').is_file())
        self.assertFalse((self.stage/'SHOWCASE_RELEASE.tar.gz').exists())
        page=(self.stage/'public/showcase/projects/community-payment/index.html').read_text()
        self.assertIn('商家',page);self.assertNotIn('送审预览',page)
        self.assertFalse(any('dispatch' in p for p in self.calls))
    def test_no_anchor_cannot_build_release(self):
        self.policy['anchors']={}
        with self.assertRaisesRegex(ValueError,'OWNER_REVIEW_ANCHOR_REQUIRED'):b.construct(self.request,self.stage,None,self.api)
        self.assertFalse((self.stage/'SHOWCASE_RELEASE.pending').exists())
    def test_source_ci_mismatch_rejected_before_fetching_files(self):
        self.request['commit']='c'*40
        with self.assertRaisesRegex(ValueError,'BUILDER_EXACT_CI'):b.construct(self.request,self.stage,None,self.api)
        self.assertFalse((self.stage/'source').exists())
    def test_blob_tampering_rejected(self):
        first=next(iter(self.blobs));self.blobs[first]['content']=base64.b64encode(b'tampered').decode()
        with self.assertRaisesRegex(ValueError,'BUILDER_BLOB_IDENTITY'):b.construct(self.request,self.stage,None,self.api)
    def test_symlink_tree_mode_rejected(self):
        self.rows[0]['mode']='120000'
        with self.assertRaisesRegex(ValueError,'BUILDER_SOURCE_MODE'):b.construct(self.request,self.stage,None,self.api)
    def test_remote_executable_and_traversal_paths_rejected(self):
        for name in ['showcase/projects/p/views/r/v1/public/../../escape','showcase/projects/p/views/r/v1/public/server.py','showcase/projects/p/.private.json','scripts/evil.py']:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):b.safe_data_path(name)
    def test_unrequested_remote_python_is_not_fetched(self):
        self.rows.append({'path':'scripts/untrusted.py','type':'blob','mode':'100644','sha':'0'*40})
        b.construct(self.request,self.stage,None,self.api)
        self.assertNotIn('git/blobs/'+'0'*40,self.calls)
    def test_truncated_tree_rejected(self):
        def truncated(path):
            r=self.api(path)
            if path.startswith('git/trees/'):r['truncated']=True
            return r
        with self.assertRaisesRegex(ValueError,'BUILDER_SOURCE_TREE'):b.construct(self.request,self.stage,None,truncated)
    def test_expired_request_and_duplicate_review_ids_rejected(self):
        for change in [{'expires_unix':0},{'review_comment_ids':[7,7]}]:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):b.validate_request({**self.request,**change},time.time())
    def test_legacy_mapping_drift_rejected(self):
        self.request['legacy_pages_sha256']='c'*64
        with self.assertRaisesRegex(ValueError,'BUILDER_LEGACY_MAPPING'):b.construct(self.request,self.stage,None,self.api)

@unittest.skipUnless(os.geteuid()==0,'Root-owned isolated fixture')
class PrivateInputTests(unittest.TestCase):
    def test_installed_code_manifest_and_self_binding(self):
        with tempfile.TemporaryDirectory(dir='/root') as td:
            root=Path(td);code=root/'scripts/pr122_showcase_protected_build.py';code.parent.mkdir();code.write_bytes(b'# fixture code')
            manifest={'files':[{'path':str(code.relative_to(root)),'size':len(code.read_bytes()),'sha256':s.sha(code.read_bytes())}]}
            raw=s.canonical(manifest);(root/'MECHANISM_MANIFEST.json').write_bytes(raw)
            with mock.patch.object(b,'CODE',root),mock.patch.object(b,'__file__',str(code)):
                b.verified_code(s.sha(raw))
                code.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'BUILDER_CODE_DRIFT'):b.verified_code(s.sha(raw))
                code.write_bytes(b'# fixture code');code.chmod(0o666)
                with self.assertRaisesRegex(ValueError,'BUILDER_CODE_OWNER'):b.verified_code(s.sha(raw))
    def test_root_private_input_and_no_symlink(self):
        with tempfile.TemporaryDirectory(dir='/root') as td:
            p=Path(td)/'request';p.write_bytes(b'{}');p.chmod(0o600)
            self.assertEqual(b.private_bytes(p),b'{}')
            p.chmod(0o644)
            with self.assertRaisesRegex(ValueError,'BUILDER_PRIVATE_INPUT'):b.private_bytes(p)
            p.chmod(0o600);link=Path(td)/'link';link.symlink_to(p)
            with self.assertRaisesRegex(ValueError,'BUILDER_TRUSTED_PATH'):b.private_bytes(link)

@unittest.skipUnless(os.geteuid()==0,'Root-owned isolated fixture')
class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.fixture=BuilderTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        td=tempfile.TemporaryDirectory(dir='/root');self.addCleanup(td.cleanup);root=Path(td.name)
        self.base=root/'builds';self.base.mkdir(mode=0o700)
        self.request=root/'request.json';self.request.write_bytes(s.canonical(self.fixture.request));self.request.chmod(0o600)
        self.policy=root/'trust.json';self.policy.write_bytes(s.canonical(self.fixture.policy));self.policy.chmod(0o600)
        shell=root/'shell';shell.write_bytes(b'FIXTURE_SHELL');shell.chmod(0o600)
        self.fixture.request['shell_tar_sha256']=s.sha(shell.read_bytes());self.request.write_bytes(s.canonical(self.fixture.request))
        for target,name,value in [(b,'BASE',self.base),(b,'REQUEST',self.request),(b,'SHELL',shell),(trust,'TRUST',self.policy),(b,'fetch',self.fixture.api)]:
            patch=mock.patch.object(target,name,value);patch.start();self.addCleanup(patch.stop)
        for target,name,value in [(b,'verified_code',None),(b.site,'official_shell',None)]:
            patch=mock.patch.object(target,name,return_value=value);patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(b.os,'uname',return_value=SimpleNamespace(nodename='iZvt5t8tlrm8oiZ'));patch.start();self.addCleanup(patch.stop)
        self.original=b.construct
        patch=mock.patch.object(b,'construct',side_effect=lambda req,stage,shell:self.original(req,stage,shell,self.fixture.api));patch.start();self.addCleanup(patch.stop)
        old=os.umask(0o077);os.umask(old);self.addCleanup(os.umask,old)
        patch=mock.patch('builtins.print');patch.start();self.addCleanup(patch.stop)
    def test_full_synthetic_pipeline_seals_and_duplicate_request_is_not_retried(self):
        b.main();folder=next(self.base.iterdir())
        self.assertTrue((folder/'SHOWCASE_RELEASE.tar.gz').is_file())
        self.assertFalse((folder/'SHOWCASE_RELEASE.pending').exists())
        receipt=json.loads((folder/'BUILD_RECEIPT.json').read_bytes())
        self.assertEqual(receipt['trust_snapshot_sha256'],s.sha(self.policy.read_bytes()))
        self.assertEqual(receipt['production_changes'],0)
        with self.assertRaises(FileExistsError):b.main()
    def test_trust_drift_preserves_hold_without_sealing(self):
        def drift(req,stage,shell):
            result=self.original(req,stage,shell,self.fixture.api)
            self.policy.write_bytes(b'{}');return result
        with mock.patch.object(b,'construct',side_effect=drift):
            with self.assertRaisesRegex(ValueError,'BUILDER_REQUEST_OR_TRUST_DRIFT'):b.main()
        folder=next(self.base.iterdir());self.assertTrue((folder/'BUILD_HOLD.json').exists())
        self.assertFalse((folder/'SHOWCASE_RELEASE.tar.gz').exists())
    def test_final_review_recheck_failure_cannot_seal(self):
        def denied(*args,**kwargs):raise ValueError('FIXTURE_REVOKED_AT_FINAL_CHECK')
        with mock.patch.object(b,'verify_review',side_effect=denied):
            with self.assertRaisesRegex(ValueError,'FIXTURE_REVOKED_AT_FINAL_CHECK'):b.main()
        folder=next(self.base.iterdir());self.assertTrue((folder/'BUILD_HOLD.json').exists())
        self.assertFalse((folder/'SHOWCASE_RELEASE.tar.gz').exists())

if __name__=='__main__':unittest.main()
