"""Owner authorization and real signed service/SQLite integration, isolated only.

GitHub HTTPS acquisition is mocked at its existing worker boundary. No fixture
comment, Grant, key or host receipt is production authority or UK evidence.
"""
import base64
import copy
import hashlib
import importlib.util
import io
import tarfile
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
CORE=ROOT/'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/attempt5'
sys.path[:0]=[str(CORE/'runtime'),str(CORE/'original'),str(CORE),
 str(CORE.parent/'kit-overlay/helpers'),
 str(ROOT/'evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers')]
import authorization as a
import epoch7_approval as old
from receipt_provider import ReceiptProvider,Hold,canonical,digest
from authority_store import AuthorityStore
from issuer_service import IssuerService
from permit_cycle import policy
from test_authority_store import grant
import test_receipt_provider as provider_fixtures


def owner_body(g,p,approved=None):
    wanted=a.expected(g,p,approved,owner=True)
    body=a.OWNER_MARKER+canonical(wanted).decode('utf-8')
    g['approval_body_sha256']=hashlib.sha256(body.encode('utf-8')).hexdigest()
    return {'id':9000000099,'user':{'id':a.OWNER_ID,'login':a.OWNER_LOGIN},
        'issue_url':'https://api.github.com/repos/'+a.REPO+'/issues/17','body':body}


class OwnerAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.g=grant()
        self.p=types.SimpleNamespace(modulus=(1<<2047)+1,exponent=65537,issuer='TEST_ONLY')
        self.value=owner_body(self.g,self.p)
    def validate(self):
        return a.validate(json.dumps(self.value).encode(),9000000099,self.g,self.p)
    def test_owner_exact_identity_and_scope(self):
        self.assertEqual(self.validate()['grant_sha256'],digest(self.g))
    def test_owner_numeric_id_mismatch_rejected(self):
        self.value['user']['id']=95597695
        with self.assertRaises(Hold):self.validate()
    def test_owner_login_mismatch_rejected(self):
        self.value['user']['login']='impostor'
        with self.assertRaises(Hold):self.validate()
    def test_independent_account_cannot_issue_owner_mode(self):
        self.value['user']={'id':95597695,'login':'18598789888'}
        with self.assertRaises(Hold):self.validate()
    def test_owner_wrong_pr_rejected(self):
        self.value['issue_url']='https://api.github.com/repos/'+a.REPO+'/issues/58'
        with self.assertRaises(Hold):self.validate()
    def test_wrong_repository_rejected(self):
        self.value['issue_url']='https://api.github.com/repos/other/repo/issues/17'
        with self.assertRaises(Hold):self.validate()
    def test_owner_changed_body_hash_rejected(self):
        self.value['body']+=' '
        with self.assertRaises(Hold):self.validate()
    def test_owner_changed_source_rejected(self):
        self.g['source_commit']='f'*40
        with self.assertRaises(Hold):self.validate()
    def test_owner_changed_manifest_rejected(self):
        self.g['manifest_sha256']='f'*64
        with self.assertRaises(Hold):self.validate()
    def test_owner_changed_provider_key_rejected(self):
        self.p.modulus+=2
        with self.assertRaises(Hold):self.validate()
    def test_owner_changed_policy_rejected(self):
        approved=policy();approved['max_attempts']=6
        with self.assertRaises(Hold):
            a.validate(json.dumps(self.value).encode(),9000000099,self.g,self.p,approved)
    def test_owner_old_marker_cannot_downgrade_to_independent(self):
        self.value['body']=self.value['body'].replace(a.OWNER_MARKER,a.MARKER,1)
        self.g['approval_body_sha256']=hashlib.sha256(self.value['body'].encode()).hexdigest()
        with self.assertRaises(Hold):self.validate()
    def test_general_flow_comment_is_not_exact_authority(self):
        self.value['body']='Owner authorizes continuous development'
        self.g['approval_body_sha256']=hashlib.sha256(self.value['body'].encode()).hexdigest()
        with self.assertRaises(Hold):self.validate()
    def test_authenticate_uses_original_worker_and_owner_comment(self):
        with mock.patch.object(old,'_run_worker',return_value=json.dumps(self.value).encode()) as fetch:
            result=a.authenticate(9000000099,self.g,self.p)
        self.assertEqual(result,self.validate())
        self.assertEqual(fetch.call_args[0][0][-1],
            'https://api.github.com/repos/'+a.REPO+'/issues/comments/9000000099')
    def test_forged_worker_response_identity_still_rejected(self):
        self.value['user']['id']=1
        with mock.patch.object(old,'_run_worker',return_value=json.dumps(self.value).encode()):
            with self.assertRaises(Hold):a.authenticate(9000000099,self.g,self.p)
    def test_owner_duplicate_json_rejected(self):
        raw=json.dumps(self.value).replace('"id": 9000000099','"id": 1, "id": 9000000099',1).encode()
        with self.assertRaises((Hold,ValueError)):a.validate(raw,9000000099,self.g,self.p)
    def test_same_review_and_body_for_five_attempts(self):
        approvals=[self.validate() for unused in range(5)]
        self.assertTrue(all(x==approvals[0] for x in approvals))
        self.assertEqual(approvals[0]['review_id'],9000000099)


class OwnerServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):provider_fixtures.ProviderTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(dir='/root');os.chmod(self.folder.name,0o700)
        self.addCleanup(self.folder.cleanup)
        self.g=grant()
        self.principal={'actor_id':self.g['actor_id'],'host':self.g['target_host'],'writer_id':'owner-fixture'}
        self.store=AuthorityStore(str(Path(self.folder.name)/'authority.db'),initialize=True,clock=lambda:100)
        self.addCleanup(lambda:self.store.close())
        self.unknown=False
        self.service=IssuerService(self.store,self.host,self.sign,'TEST_ONLY')
        self.provider=ReceiptProvider(lambda req:self.service.handle(req,self.principal),
            self.modulus,65537,'TEST_ONLY',clock=lambda:101)
        self.comment=owner_body(self.g,self.provider)
        with mock.patch.object(old,'_run_worker',return_value=json.dumps(self.comment).encode()):
            self.approval=a.authenticate(9000000099,self.g,self.provider)
        self.store.register(self.g)
        self.store.register_cycle(self.g,policy(),self.approval)
    def sign(self,raw):
        return subprocess.check_output(['openssl','dgst','-sha256','-sign',self.key],input=raw)
    def host(self,g,attempt,operation,payload):
        proof={'outcome':'SUCCESS' if operation=='verify_terminal' else 'NO_WRITE',
            'evidence_sha256':'a'*64,'checkpoint_sha256':'b'*64,'log_sha256':'c'*64}
        result={'binding':payload,'status':'UNKNOWN' if self.unknown else
            ('SUCCESS' if operation=='verify_terminal' else 'RECONCILED'),'proof':proof}
        return {'grant_sha256':digest(g),'attempt_id':attempt,'operation':operation,
            'payload_sha256':digest(payload),'run_id':'SYNTHETIC_RUN','job_id':'SYNTHETIC_JOB',
            'invoke_id':'SYNTHETIC_INVOKE','backup_sha256':'a'*64,
            'checkpoint_sha256':'b'*64,'log_sha256':'c'*64,'result':result}
    def consume(self,n):
        return self.provider.request(self.g,'owner-attempt-'+str(n),'consume_attempt',
            {'ordinal':n,'command_sha256':'a'*64,'ledger_sha256':str(n)*64})
    def finish(self,n,success=False):
        return self.provider.request(self.g,'owner-attempt-'+str(n),
            'verify_terminal' if success else 'reconcile_unadmitted',{})
    def test_owner_grant_five_safe_attempts_one_authority(self):
        for n in range(1,6):
            self.assertEqual(self.consume(n)['status'],'CONSUMED')
            self.finish(n,success=(n==5))
        self.assertEqual(self.store.db.execute('SELECT consumed,terminal FROM grants').fetchone(),(5,1))
        with self.assertRaises(Hold):self.consume(6)
    def test_owner_success_stops_remaining_quota(self):
        self.consume(1);self.finish(1,True)
        with self.assertRaises(Hold):self.consume(2)
        self.assertEqual(self.store.db.execute('SELECT consumed FROM grants').fetchone()[0],1)
    def test_owner_unknown_holds_then_same_attempt_reconciles(self):
        self.consume(1);self.unknown=True
        with self.assertRaises(Hold):self.finish(1)
        with self.assertRaises(Hold):self.consume(2)
        self.assertEqual(self.store.db.execute('SELECT state FROM attempts').fetchone()[0],'UNKNOWN')
        self.unknown=False;self.finish(1);self.consume(2)
        self.assertEqual(self.store.db.execute('SELECT consumed FROM grants').fetchone()[0],2)
    def test_owner_conflicting_writer_rejected(self):
        self.consume(1);self.principal=dict(self.principal,writer_id='CONFLICTING')
        with self.assertRaises(Hold):self.finish(1)
        self.assertEqual(self.store.db.execute('SELECT consumed FROM grants').fetchone()[0],1)
    def test_owner_restart_preserves_quota_and_unknown(self):
        self.consume(1)
        self.store.close()
        self.store=AuthorityStore(str(Path(self.folder.name)/'authority.db'),initialize=False,clock=lambda:100)
        self.service=IssuerService(self.store,self.host,self.sign,'TEST_ONLY')
        self.consume(1)
        self.assertEqual(self.store.db.execute('SELECT consumed FROM grants').fetchone()[0],1)
        with self.assertRaises(Hold):self.consume(2)
        self.finish(1);self.consume(2)
    def test_owner_signature_verification_not_bypassed(self):
        self.service.signer=lambda raw:b'x'*256
        with self.assertRaises(Hold):self.consume(1)
        self.assertEqual(self.store.db.execute('SELECT consumed FROM grants').fetchone()[0],1)
        # Unknown reply doesn't justify new consumption; exact request can query.
        result=self.provider
        self.service.signer=self.sign
        self.assertEqual(self.consume(1)['status'],'CONSUMED')
        self.assertIs(result,self.provider)
    def test_owner_mode_through_exact_kit_import_scope(self):
        builder_spec=importlib.util.spec_from_file_location('owner_fixture_builder',str(CORE/'build_kit.py'))
        builder=importlib.util.module_from_spec(builder_spec);builder_spec.loader.exec_module(builder)
        git=lambda ref:subprocess.check_output(['git','-c','safe.directory=*','rev-parse',ref],cwd=str(ROOT)).decode().strip()
        raw,manifest=builder.build(git('HEAD'),git('HEAD^{tree}'))
        root=Path(self.folder.name)/'kit'
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
            for item in archive.getmembers():
                assert item.isfile()
                relative=item.name.split('/',1)[1]
                assert '..' not in relative.split('/')
                target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(archive.extractfile(item).read());os.chmod(str(target),0o600)
        payload=Path(self.folder.name)/'fixture.json'
        payload.write_text(json.dumps({'comment':self.comment,'grant':self.g,
            'modulus':self.modulus,'issuer':'TEST_ONLY'}))
        os.chmod(str(payload),0o600)
        script=('import sys,types,json,importlib.util;'
            's=importlib.util.spec_from_file_location("loader",sys.argv[1]);'
            'm=importlib.util.module_from_spec(s);s.loader.exec_module(m);'
            'v=json.load(open(sys.argv[4]));'
            'scope=m.imports(sys.argv[2],sys.argv[3]);scope.__enter__();'
            'import authorization;'
            'p=types.SimpleNamespace(modulus=v["modulus"],exponent=65537,issuer=v["issuer"]);'
            'r=authorization.validate(json.dumps(v["comment"]).encode(),9000000099,v["grant"],p);'
            'assert r["grant_sha256"]==authorization.digest(v["grant"]);scope.__exit__(None,None,None)')
        result=subprocess.run([sys.executable,'-I','-B','-S','-c',script,
            str(root/'attempt5/runtime/versioned_entry.py'),str(root),
            hashlib.sha256((root/'attempt5-manifest.json').read_bytes()).hexdigest(),str(payload)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr.decode())
    def test_owner_fifth_failure_exhausts(self):
        for n in range(1,6):self.consume(n);self.finish(n)
        with self.assertRaises(Hold):self.consume(6)
        self.assertEqual(self.store.db.execute('SELECT consumed,terminal FROM grants').fetchone(),(5,0))

if __name__=='__main__':unittest.main()
