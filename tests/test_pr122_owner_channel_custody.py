import io,json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
from scripts import pr122_owner_channel_custody as c

class TTY(io.StringIO):
    def __init__(self,answers):super().__init__(answers);self.prompts=[]
    def isatty(self):return True
    def write(self,s):self.prompts.append(s);return len(s)

class CustodyTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.getuid(),0)
        self.tmp=tempfile.TemporaryDirectory(dir='/root',prefix='pr122-owner-custody-test-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(c,'HOST',os.uname().nodename))
        self.stack.enter_context(patch.object(c,'OUT',self.root/'new-custody'))
        launcher=self.root/'launcher.py';launcher.write_bytes(Path(c.__file__).read_bytes());launcher.chmod(0o400)
        self.stack.enter_context(patch.object(c,'__file__',str(launcher)))
        self.input=self.root/'staged.zip';self.input.write_bytes(b'fake-test-input');self.input.chmod(0o400);os.chown(self.input,1002,1002)
        self.stack.enter_context(patch.object(c,'STAGE',self.input))
        self.dec=self.stack.enter_context(patch.object(c,'decode',return_value=(b'# inert fixture',b'fixture bytes')))
        self.audit='real fetched audit fixture';self.stack.enter_context(patch.object(c,'AUDIT_SHA',c.sha(self.audit.encode())))
        self.ident=678
        p={'decision':'OWNER_CUSTODY_PREPARE_APPROVED','attempt_id':c.ATTEMPT,'host':c.HOST,
           'launcher_sha256':c.sha(Path(c.__file__).read_bytes()),'review_zip_sha256':c.ZIP_SHA,
           'helper_sha256':c.HELPER_SHA,'audit_comment_id':c.AUDIT_ID,'audit_body_sha256':c.AUDIT_SHA,
           'max_attempts':1,'channel_write_allowed':False,'apply_allowed':False,
           'issued_unix':int(time.time())-1,'expires_unix':int(time.time())+300}
        self.body='XUANJUN_PR122_OWNER_CUSTODY_PREPARE\n'+json.dumps(p);self.digest=c.sha(self.body.encode())
        self.comments={self.ident:self.comment(self.ident,self.body),c.AUDIT_ID:self.comment(c.AUDIT_ID,self.audit)}
    def comment(self,n,b):return {'id':n,'user':{'login':'huhongchuan0422-creator'},'issue_url':'https://api.github.com/repos/'+c.REPO+'/issues/122','body':b}
    def tty(self,writer='writer',reviewer='reviewer',proof='e'*64,confirm=None):return TTY('Owner\n'+writer+'\n'+reviewer+'\n'+proof+'\n'+(confirm or c.CONFIRM)+'\n')
    def prepare(self,tty=None,get=None):return c.prepare(self.ident,self.digest,get=get or self.comments.__getitem__,tty=tty or self.tty())
    def test_real_nonseekable_pseudoterminal_roundtrip(self):
        master,slave=os.openpty()
        try:
            path=os.ttyname(slave)
            with self.assertRaises(io.UnsupportedOperation):
                open(path,'r+',encoding='utf-8')
            with c.open_terminal(path) as tty:
                self.assertTrue(tty.isatty())
                os.write(master,b'owner-confirmation\n')
                self.assertEqual(tty.readline(),'owner-confirmation\n')
                tty.write('prompt-ok\n');tty.flush()
                received=os.read(master,4096)
                self.assertTrue(received)
        finally:os.close(master);os.close(slave)

    def test_owner_attestation_saves_exact_inputs_without_channel_install(self):
        r=self.prepare();self.assertEqual(r['state'],'CUSTODY_PREPARED_AWAIT_INDEPENDENT_ACCEPTANCE')
        self.assertFalse(r['trust_installed']);self.assertFalse(r['helper_executed']);self.assertEqual(r['channel_changes'],0)
        for p in c.OUT.iterdir():self.assertEqual(p.stat().st_mode&0o777,0o400)
        att=json.loads((c.OUT/'OWNER_CUSTODY.json').read_bytes());self.assertIn('NOT_CRYPTOGRAPHIC',att['attestation_kind'])
        self.assertEqual(att['reviewer_principal'],'reviewer')
    def test_repeated_preparation_is_refused_and_first_evidence_retained(self):
        self.prepare();b=(c.OUT/'receipt.json').read_bytes()
        with self.assertRaises(RuntimeError):self.prepare()
        self.assertEqual((c.OUT/'receipt.json').read_bytes(),b)
    def test_ordinary_pipe_cannot_attest_owner(self):
        with self.assertRaises(RuntimeError):self.prepare(tty=io.StringIO('values'))
        self.assertTrue((c.OUT/'failure.json').exists())
    def test_same_writer_reviewer_refused(self):
        with self.assertRaises(RuntimeError):self.prepare(tty=self.tty(reviewer='writer'))
        self.assertFalse((c.OUT/'OWNER_CUSTODY.json').exists())
    def test_missing_external_proof_or_explicit_confirmation_refused(self):
        with self.assertRaises(RuntimeError):self.prepare(tty=self.tty(proof='unknown',confirm='yes'))
    def test_expired_or_edited_approval_refused_before_consumption(self):
        with patch.object(c.time,'time',return_value=time.time()+10000),self.assertRaises(RuntimeError):self.prepare()
        self.assertFalse(c.OUT.exists())
        self.comments[self.ident]['body']+=' '
        with self.assertRaises(RuntimeError):self.prepare()
        self.assertFalse(c.OUT.exists())
    def test_approval_changed_after_operator_confirmation_stops(self):
        count=[0]
        def get(n):
            if n==self.ident:
                count[0]+=1
                if count[0]>1:return self.comment(n,self.body+' ')
            return self.comments[n]
        with self.assertRaises(RuntimeError):self.prepare(get=get)
        self.assertFalse((c.OUT/'approved-upgrade.py').exists())
    def test_wrong_launcher_or_expanded_scope_refused(self):
        p=json.loads(self.body.split('\n',1)[1]);p['apply_allowed']=True
        self.body='XUANJUN_PR122_OWNER_CUSTODY_PREPARE\n'+json.dumps(p);self.digest=c.sha(self.body.encode());self.comments[self.ident]=self.comment(self.ident,self.body)
        with self.assertRaises(RuntimeError):self.prepare()
        self.assertFalse(c.OUT.exists())
    def test_runner_sudo_identity_refused(self):
        with patch.dict(os.environ,{'SUDO_UID':'1002'}),self.assertRaises(RuntimeError):self.prepare()
        self.assertFalse(c.OUT.exists())
    def test_staging_symlink_or_writable_parent_refused(self):
        link=self.root/'link';link.symlink_to(self.input)
        with patch.object(c,'STAGE',link),self.assertRaises(RuntimeError):self.prepare()
        self.assertTrue((c.OUT/'failure.json').exists())
    def test_persistence_failure_never_overwrites_or_calls_helper(self):
        original=c.write
        def fail(p,b):
            if p.name=='OWNER_CUSTODY.json':raise OSError('fsync unavailable')
            return original(p,b)
        with patch.object(c,'write',side_effect=fail),self.assertRaises(OSError):self.prepare()
        with self.assertRaises(RuntimeError):self.prepare()
        self.assertFalse((c.OUT/'approved-upgrade.py').exists())
    def test_exact_real_review_artifact_decodes_without_executing(self):
        raw=Path(os.environ['PR122_CUSTODY_REVIEW_ZIP']).read_bytes()
        # The actual function is retained outside fixture mocking.
        helper,runtime=REAL_DECODE(raw)
        self.assertEqual(c.sha(helper),c.HELPER_SHA);self.assertEqual(c.sha(runtime),c.RUNTIME_SHA)
        with self.assertRaises(RuntimeError):REAL_DECODE(raw+b'bad')

REAL_DECODE=c.decode
if __name__=='__main__':unittest.main()
