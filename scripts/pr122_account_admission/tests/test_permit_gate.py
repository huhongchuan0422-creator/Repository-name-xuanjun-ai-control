import base64, copy, datetime, hashlib, importlib.util, json, os, pathlib, tempfile, types, unittest
from unittest.mock import patch, Mock
HERE=pathlib.Path(__file__).resolve().parents[1]
def load(name,path):
    sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
g=load('permit_gate_test',HERE/'permit_gate.py')
t=load('permit_transport_test',HERE/'readonly_transport.py')

class PermitTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name);self.workflow=b'FIXTURE ONLY NOT DEPLOYABLE\n'
        self.p=dict(schema=1,kind=g.PERMIT_KIND,decision='APPROVED_EXACT_ONE_ATTEMPT',repository=g.PERMIT_REPO,pr_number=122,head_sha='a'*40,base_sha='b'*40,merge_sha='c'*40,workflow_ref=g.PERMIT_REPO+'/'+g.PERMIT_PATH+'@refs/pull/122/merge',workflow_blob_sha=hashlib.sha1(b'blob '+str(len(self.workflow)).encode()+b'\0'+self.workflow).hexdigest(),workflow_sha256=g.permit_hash(self.workflow),payload_sha256=g.PERMIT_BUNDLE,caller_sha256=g.PERMIT_CALLER,reviewer_principal='independent-task5',source_writer_principal='source-author',custody_evidence_sha256='e'*64,approval_nonce='f'*32,issued_unix=1000,expires_unix=1300,max_attempts=1,region='cn-shanghai',instance_id='3a22c458934142eea89ec6e3bf481a57',hostname='iZvt5t8tlrm8oiZ',role_arn='acs:ram::1384884686754410:role/xuanjun-automation',actions=g.PERMIT_ACTIONS.copy(),max_run_commands=1,query_same_invoke_only=True)
        self.pin=dict(schema=1,action=g.PERMIT_KIND,approval_comment_id=123,approval_body_sha256='',reviewer_principal='independent-task5',source_writer_principal='source-author',custody_evidence_sha256='e'*64,owner_attests_independent_review=True,runner_hostname=g.PERMIT_EXECUTOR_HOST,registry_persistent=True,revoked=False)
        self.comment=dict(id=123,issue_url='https://api.github.com/repos/'+g.PERMIT_REPO+'/issues/122',user={'id':332398908},performed_via_github_app={'id':1144995},created_at='1970-01-01T00:16:40Z')
        self.pr=dict(state='open',mergeable=True,head={'sha':'a'*40,'ref':g.PERMIT_BRANCH,'repo':{'full_name':g.PERMIT_REPO}},base={'sha':'b'*40,'ref':g.PERMIT_BASE},merge_commit_sha='c'*40)
        self.entry=dict(type='file',path=g.PERMIT_PATH,sha=self.p['workflow_blob_sha'],encoding='base64',content=base64.b64encode(self.workflow).decode())
        self.env={'GITHUB_WORKFLOW_REF':self.p['workflow_ref'],'GITHUB_WORKFLOW_SHA':'c'*40,'GITHUB_RUN_ATTEMPT':'1','GITHUB_RUN_ID':'555'}
        self.now=1100;self.gate=g.ReadonlyPermit(self.fetch,self.env,lambda:self.now);self.gate.anchor=self.root/'pin';self.gate.registry=self.root
        # Only fixtures bypass protected ownership/host. Production uses fixed paths.
        self.addCleanup(patch.stopall);patch.object(g,'permit_secure').start();patch.object(g.os,'geteuid',return_value=0).start();patch.object(g.os,'uname',return_value=types.SimpleNamespace(nodename=g.PERMIT_EXECUTOR_HOST)).start()
        self.enroll()
    def enroll(self):
        self.comment['body']=g.PERMIT_BEGIN+json.dumps(self.p,sort_keys=True)+g.PERMIT_END
        self.pin['approval_body_sha256']=g.permit_hash(self.comment['body'].encode());self.gate.anchor.write_text(json.dumps(self.pin))
    def fetch(self,path):
        if '/issues/comments/' in path:return copy.deepcopy(self.comment)
        if path.endswith('/pulls/122'):return copy.deepcopy(self.pr)
        if '/contents/' in path:return copy.deepcopy(self.entry)
        raise AssertionError(path)
    def reject(self):
        with self.assertRaises((g.PermitDenied,FileNotFoundError,FileExistsError,ValueError,KeyError)):self.gate.validate()
    def test_exact_final_permit(self):self.assertEqual(self.gate.validate()['head_sha'],'a'*40)
    def test_comment_id_and_provenance(self):
        for field,value in [('id',124),('issue_url','wrong'),('user',{'id':1}),('performed_via_github_app',None)]:
            with self.subTest(field=field):
                old=self.comment[field];self.comment[field]=value;self.reject();self.comment[field]=old
    def test_changed_body_rejected(self):self.comment['body']+=' ';self.reject()
    def test_duplicate_json_rejected(self):
        self.comment['body']=g.PERMIT_BEGIN+'{"schema":1,"schema":1}'+g.PERMIT_END;self.pin['approval_body_sha256']=g.permit_hash(self.comment['body'].encode());self.gate.anchor.write_text(json.dumps(self.pin));self.reject()
    def test_same_owner_is_not_independence(self):self.pin['reviewer_principal']=self.pin['source_writer_principal'];self.gate.anchor.write_text(json.dumps(self.pin));self.reject()
    def test_custody_unknown_rejected(self):self.pin['custody_evidence_sha256']='UNKNOWN';self.gate.anchor.write_text(json.dumps(self.pin));self.reject()
    def test_missing_protected_source_rejected(self):self.gate.anchor.unlink();self.reject()
    def test_hosted_executor_rejected(self):
        with patch.object(g.os,'uname',return_value=types.SimpleNamespace(nodename='github-hosted')):self.reject()
    def test_nonroot_executor_rejected(self):
        with patch.object(g.os,'geteuid',return_value=1001):self.reject()
    def test_unprotected_or_ephemeral_enrollment_rejected(self):
        for key in ('registry_persistent','owner_attests_independent_review'):
            self.pin[key]=False;self.gate.anchor.write_text(json.dumps(self.pin));self.reject();self.pin[key]=True
    def test_revoked_rejected(self):self.pin['revoked']=True;self.gate.anchor.write_text(json.dumps(self.pin));self.reject()
    def test_final_head_base_merge_drift(self):
        for section,key in [('head','sha'),('base','sha'),(None,'merge_commit_sha')]:
            target=self.pr[section] if section else self.pr;old=target[key];target[key]='d'*40;self.reject();target[key]=old
    def test_workflow_blob_and_bytes_drift(self):
        for k,v in [('sha','d'*40),('content',base64.b64encode(b'changed').decode())]:
            old=self.entry[k];self.entry[k]=v;self.reject();self.entry[k]=old
    def test_runtime_ref_and_rerun_rejected(self):
        for k,v in [('GITHUB_WORKFLOW_REF','wrong'),('GITHUB_WORKFLOW_SHA','d'*40),('GITHUB_RUN_ATTEMPT','2')]:
            old=self.env[k];self.env[k]=v;self.reject();self.env[k]=old
    def test_expired_future_overlong_permit(self):
        for start,end in [(1000,1099),(1101,1300),(1000,8201)]:
            self.p.update(issued_unix=start,expires_unix=end);self.enroll();self.reject()
    def test_wrong_effect_or_target_rejected(self):
        for k,v in [('actions',['ALL']),('max_run_commands',2),('query_same_invoke_only',False),('instance_id','other'),('payload_sha256','a'*64),('caller_sha256','a'*64),('hostname','other')]:
            old=self.p[k];self.p[k]=v;self.enroll();self.reject();self.p[k]=old
    def test_source_nonce_and_expiry_drift_after_validation(self):
        self.gate.validate();self.p['approval_nonce']='a'*32;self.enroll();self.reject()
    def test_expiry_between_validate_and_use(self):
        self.gate.reserve();self.now=1300
        with self.assertRaises(g.PermitDenied):self.gate.claim_dispatch()
    def test_durable_consumption_survives_new_object(self):
        self.gate.reserve();new=g.ReadonlyPermit(self.fetch,self.env,lambda:self.now);new.anchor=self.gate.anchor;new.registry=self.root
        with self.assertRaises(FileExistsError):new.reserve()
    def test_same_nonce_different_comment_rejected(self):
        self.gate.reserve();self.pin['approval_comment_id']=124;self.comment['id']=124;self.enroll();self.gate.proof=None;self.gate.pin_hash=None
        with self.assertRaises(FileExistsError):self.gate.reserve()
    def test_other_run_cannot_claim(self):
        self.gate.reserve();self.env['GITHUB_RUN_ID']='556'
        with self.assertRaises(g.PermitDenied):self.gate.claim_dispatch()
    def test_partial_reservation_consumes(self):
        self.gate.validate();g.permit_write_once(self.root/('readonly-nonce-'+self.p['approval_nonce']+'.consumed.json'),{'partial':True})
        with self.assertRaises(FileExistsError):self.gate.reserve()
    def test_dispatch_single_use_even_without_response(self):
        self.gate.reserve();self.gate.claim_dispatch()
        with self.assertRaises(FileExistsError):self.gate.claim_dispatch()
    def test_query_exact_invoke_scope(self):
        self.gate.reserve();self.gate.claim_dispatch();self.gate.bind_invoke('test-invoke');self.gate.query('test-invoke')
        with self.assertRaises(g.PermitDenied):self.gate.query('other-invoke')
    def test_query_after_revocation_denied(self):
        self.gate.reserve();self.gate.claim_dispatch();self.gate.bind_invoke('test-invoke');self.pin['revoked']=True;self.gate.anchor.write_text(json.dumps(self.pin))
        with self.assertRaises(g.PermitDenied):self.gate.query('test-invoke')
    def test_missing_invoke_never_query(self):
        self.gate.reserve();self.gate.claim_dispatch()
        with self.assertRaises(FileNotFoundError):self.gate.query('unknown')

    def test_cross_process_pin_byte_drift(self):
        self.gate.reserve()
        self.gate.anchor.write_text(json.dumps(self.pin,indent=2))
        other=g.ReadonlyPermit(self.fetch,self.env,lambda:self.now);other.anchor=self.gate.anchor;other.registry=self.root
        with self.assertRaises(g.PermitDenied):other.claim_dispatch()
    def test_partial_comment_marker_denied(self):
        self.gate.reserve();self.gate.marker().write_text('{')
        with self.assertRaises(ValueError):self.gate.claim_dispatch()
    def test_two_competing_reservations_one_winner(self):
        import concurrent.futures
        def attempt(_):
            other=g.ReadonlyPermit(self.fetch,self.env,lambda:self.now);other.anchor=self.gate.anchor;other.registry=self.root
            try:other.reserve();return 'WON'
            except FileExistsError:return 'CONSUMED'
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
        self.assertEqual(sorted(results),['CONSUMED','WON'])

class IntegrationTests(unittest.TestCase):
    def test_failed_permit_before_cloud_access(self):
        class Env(dict):
            def get(self,k,*args):
                if k.startswith('ALIYUN_'):raise AssertionError('CLOUD_SECRET_ACCESSED')
                return super().get(k,*args)
        with patch.object(t,'ARMED',True),patch.object(t,'EXECUTION_ADMISSION',True),patch.object(t,'ReadonlyPermit') as P,patch.object(t.os,'environ',Env()),patch.object(t,'persist'),patch('builtins.print'),patch.object(t,'rpc') as rpc:
            P.return_value.validate.side_effect=t.PermitDenied('NO_TRUST');self.assertEqual(t.main(),2);rpc.assert_not_called()
    def test_workflow_admission_step_has_no_cloud_secrets(self):
        import yaml
        workflow=yaml.safe_load((HERE/'readonly-transport-candidate.yml').read_text());steps=workflow['jobs']['readonly-admission-once']['steps']
        self.assertEqual(steps[0]['env']['ADMISSION_PHASE'],'ADMIT');self.assertNotIn('ALIYUN_ACCESS_KEY_ID',steps[0]['env']);self.assertNotIn('ALIYUN_ACCESS_KEY_SECRET',steps[0]['env'])
        self.assertEqual(steps[1]['if'],"${{ steps.admission.outputs.ready == 'true' }}");self.assertEqual(steps[1]['env']['ADMISSION_PHASE'],'EXECUTE')
        self.assertIn('${{ false &&',workflow['jobs']['readonly-admission-once']['if'])
    def test_both_inline_transports_are_exact(self):
        import yaml
        workflow=yaml.safe_load((HERE/'readonly-transport-candidate.yml').read_text());steps=workflow['jobs']['readonly-admission-once']['steps'];source=(HERE/'readonly_transport.py').read_text()
        for step in steps[:2]:self.assertEqual(step['run'].split("python3 - <<'PY'\n",1)[1].rsplit('PY\n',1)[0],source)
    def test_no_registry_or_pin_provisioning(self):
        source=(HERE/'permit_gate.py').read_text();self.assertNotIn('.mkdir(',source);self.assertNotIn('os.mkdir(',source);self.assertNotIn('write_text(',source)

if __name__=='__main__':unittest.main()
