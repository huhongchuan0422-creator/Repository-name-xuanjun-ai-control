"""Read-only diagnostic regressions; public byte fixtures and temporary files."""
import contextlib,errno,hashlib,importlib.util,json,os,pathlib,signal,stat,tempfile,time,types,unittest
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('diagnose_preparation',str(ROOT/'diagnose_preparation.py'))
x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
RAW=(ROOT.parent/'r6-delivery-bound-candidate/epoch7_prepare_delivery.py').read_bytes()
CACHE={name:(ROOT.parent/'r6-preparation-candidate'/name).read_bytes() for name in ('epoch7_prepare.py','epoch7_prepare_data.py','epoch7_topology_projection.py')}

def mapped(info):
    values={n:getattr(info,n) for n in dir(info) if n.startswith('st_')};values.update(st_uid=0,st_gid=0)
    return types.SimpleNamespace(**values)
def proxy():
    p=types.SimpleNamespace(**{n:getattr(os,n) for n in dir(os) if not n.startswith('__')})
    p.fstat=lambda fd:mapped(os.fstat(fd));p.stat=lambda *a,**k:mapped(os.stat(*a,**k));p.geteuid=lambda:0;p.getegid=lambda:0
    return p
@contextlib.contextmanager
def scope(*args):yield time.monotonic()+30

class BindingTests(unittest.TestCase):
    def test_exact_frozen_publications_and_observation(self):
        d=x.delivery_module(RAW);self.assertEqual((len(RAW),x.sha(RAW)),(14950,x.DELIVERY_SHA256))
        self.assertEqual(d.validate_sources(CACHE),CACHE);self.assertEqual(d.OBSERVATION_PATH,x.OBSERVATION_PATH)
        self.assertEqual(d.OBSERVATION_SHA256,x.OBSERVATION_SHA256);self.assertEqual(d.PUBLICATION_COMMIT,x.PREPARATION_COMMIT)
    def test_changed_delivery_never_executes(self):
        with mock.patch('builtins.compile',side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(x.DiagnosticHold,'DELIVERY_PIN'):x.delivery_module(b'X'+RAW[1:])
    def test_code_paths_are_exact_authenticated_runtime_module_inventory(self):
        kit=ROOT.parent/'r6-integration-candidate/build-0c8a0f2a-python312-v2-a/epoch7-recovery-candidate-r6'
        raw=(kit/'recovery-kit-manifest.json').read_bytes()
        self.assertEqual(x.sha(raw),'70c76e30ae8390963f345813f87267bf1d2f024bc01031c8023733c84aa571cc')
        manifest=json.loads(raw.decode());self.assertEqual(x.PUBLIC_CODE_PATHS,set(manifest['modules'].values())|{'epoch7_recovery_entry.py'})
    def test_public_literal_labels_include_native_guard_and_not_private_values(self):
        labels=x.public_labels(CACHE)
        self.assertIn('EPOCH7_PREP_NATIVE_EXPECTED_AUTHORITY',labels)
        self.assertIn('TOPOLOGY_KERNEL_PEER_IDENTITY',labels)
        self.assertNotIn('secret runtime configuration',labels)
    def test_argument_and_root_scope_refuse_before_download(self):
        for args,uid in ((['--prepare'],0),([],1000)):
            with mock.patch.object(x.os,'geteuid',return_value=uid),mock.patch.object(x.os,'getegid',return_value=0),\
                 mock.patch.object(x,'download_delivery') as download,mock.patch.object(x,'output') as output:
                self.assertEqual(x.main(args),2);download.assert_not_called()
                self.assertEqual(output.call_args[0][0]['outer_phase'],'INPUT_VALIDATION')

class ReadonlyFilesystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='readonly-diagnostic-',dir=str(ROOT));self.addCleanup(self.tmp.cleanup)
        self.root=self.tmp.name;self.dest=self.root+'/epoch7-preparation-candidate-r6';self.d=x.delivery_module(RAW);self.os=proxy()
        self.d.CAND=self.root;self.d.PREP_ROOT=self.dest;self.d.os=self.os
    def fixture(self):
        os.mkdir(self.dest,0o700)
        for name,raw in CACHE.items():pathlib.Path(self.dest+'/'+name).write_bytes(raw);os.chmod(self.dest+'/'+name,0o600)
    def verify(self):
        with mock.patch.object(self.os,'mkdir',side_effect=AssertionError('mkdir forbidden')) as mkdir,\
             mock.patch.object(self.os,'write',side_effect=AssertionError('write forbidden')) as write,\
             mock.patch.object(self.os,'chmod',side_effect=AssertionError('chmod forbidden')) as chmod:
            try:return self.d.stage(CACHE,time.monotonic()+20,allow_create=False)
            finally:mkdir.assert_not_called();write.assert_not_called();chmod.assert_not_called()
    def test_exact_existing_inventory_is_read_only(self):
        self.fixture();before={n:os.stat(self.dest+'/'+n) for n in CACHE};row=self.verify()
        self.assertEqual(row['state'],'REUSED_EXACT');self.assertEqual(row['created_paths'],[])
        self.assertEqual(before,{n:os.stat(self.dest+'/'+n) for n in CACHE})
    def test_missing_directory_never_created(self):
        with self.assertRaisesRegex(self.d.Hold,'DIRECTORY'):self.verify()
        self.assertEqual(os.listdir(self.root),[])
    def test_partial_inventory_never_repaired(self):
        os.mkdir(self.dest,0o700);pathlib.Path(self.dest+'/epoch7_prepare.py').write_bytes(CACHE['epoch7_prepare.py']);os.chmod(self.dest+'/epoch7_prepare.py',0o600)
        with self.assertRaisesRegex(self.d.Hold,'INVENTORY'):self.verify()
        self.assertEqual(os.listdir(self.dest),['epoch7_prepare.py'])
    def test_mismatched_bytes_never_overwritten(self):
        self.fixture();f=pathlib.Path(self.dest+'/epoch7_prepare.py');f.write_bytes(b'X'+f.read_bytes()[1:]);before=f.read_bytes()
        with self.assertRaisesRegex(self.d.Hold,'FILE_BYTES'):self.verify()
        self.assertEqual(f.read_bytes(),before)
    def test_extra_inventory_and_symlink_refuse(self):
        self.fixture();extra=pathlib.Path(self.dest+'/extra');extra.write_bytes(b'fixture')
        with self.assertRaises(self.d.Hold):self.verify()
        extra.unlink();f=pathlib.Path(self.dest+'/epoch7_prepare.py');f.rename(self.root+'/old');os.symlink(self.root+'/old',str(f))
        with self.assertRaises(OSError):self.verify()
    def test_wrong_mode_refuses_without_chmod(self):
        self.fixture();os.chmod(self.dest+'/epoch7_prepare.py',0o644)
        with self.assertRaisesRegex(self.d.Hold,'FILE_AUTHORITY'):self.verify()
        self.assertEqual(stat.S_IMODE(os.stat(self.dest+'/epoch7_prepare.py').st_mode),0o644)

class FlowTests(unittest.TestCase):
    def invoke(self,where=None,error=None,native=False):
        d=x.delivery_module(RAW);p=d.preparer(CACHE);events=[]
        p.budget=scope;d.budget=scope
        def fetch(end):
            events.append('fetch')
            if where=='fetch':raise error
            return CACHE
        def stage(cache,end,allow_create=True):
            self.assertIs(allow_create,False);events.append('verify')
            if where=='delivery_cleanup':raise d.CleanupError()
            if where=='stage':raise error
            return {'state':'REUSED_EXACT','created_paths':[]}
        def load(cache):
            events.append('load')
            if where=='load':raise error
            return p
        def propose(args,end):
            events.append('propose');self.assertEqual(vars(args),{'operation':'propose-topology','observation':x.OBSERVATION_PATH,
                'observation_sha256':x.OBSERVATION_SHA256,'topology_review_id':None,'retained_renewal_timer':None})
            p.phase('COLLECT_INPUTS')
            if native:
                g=p.Gatherer(None,end);tree=types.SimpleNamespace(parent=lambda name:(7,'p2-native-binding.json'))
                with mock.patch.object(g,'tree',return_value=tree),mock.patch.object(p.os,'stat'),mock.patch.object(p.os,'open',return_value=9),\
                     mock.patch.object(p.os,'fstat'),mock.patch.object(p.os,'close') as close:
                    try:g.read('/etc/xuanjun-development/p2-native-binding.json',2048,expected={'uid':0,'gid':0,'mode':0o644})
                    finally:close.assert_called_once_with(9)
            if where=='preparer_cleanup':raise p.CleanupError()
            if where=='propose':raise error
            return {'state':'TOPOLOGY_REVIEW_REQUIRED','expected_review_body':{'synthetic':True}}
        d.fetch_sources=fetch;d.stage=stage;d.preparer=load;p.run_preparation=propose
        with mock.patch.object(x.os,'geteuid',return_value=0),mock.patch.object(x.os,'getegid',return_value=0),\
             mock.patch.object(x.socket,'gethostname',return_value=x.HOST),\
             mock.patch.object(x.sys,'flags',types.SimpleNamespace(isolated=1,no_site=1)),mock.patch.object(x.sys,'dont_write_bytecode',True),\
             mock.patch.object(x,'budget',scope),mock.patch.object(x,'download_delivery',return_value=RAW),\
             mock.patch.object(x,'delivery_module',return_value=d),mock.patch.object(x,'output') as output:
            code=x.main([])
        return code,events,output.call_args[0][0],p,d
    def test_only_existing_verification_then_fixed_proposal_then_reverification(self):
        code,events,row,p,d=self.invoke();self.assertEqual(code,0)
        self.assertEqual(events,['fetch','verify','load','propose','verify']);self.assertEqual(row['created_paths'],[])
        self.assertEqual(row['output_scope'],'UNSIGNED_PROPOSAL_AND_HOST_VALIDATED_EVIDENCE_BINDINGS')
    def test_actual_frozen_native_guard_has_exact_inner_phase_label_and_location(self):
        code,events,row,p,d=self.invoke(native=True)
        self.assertEqual(code,2);self.assertEqual(row['preparation_phase'],'COLLECT_INPUTS')
        self.assertEqual(row['failure_label'],'EPOCH7_PREP_NATIVE_EXPECTED_AUTHORITY')
        self.assertTrue(any(r['source']=='preparation/epoch7_prepare.py' and 215<=r['line']<=223 for r in row['code_locations']))
        self.assertFalse(row['cleanup_unknown']);self.assertNotIn('proposal',row)
    def test_unknown_empty_and_sensitive_errors_remain_safe(self):
        for error in (ValueError('secret runtime configuration'),ValueError(),ValueError('safe','private text'),KeyError('private path')):
            code,events,row,p,d=self.invoke(where='propose',error=error)
            self.assertEqual(code,2);self.assertIsNone(row['failure_label']);self.assertEqual(row['preparation_phase'],'COLLECT_INPUTS')
            self.assertNotIn('secret',repr(row));self.assertNotIn('private path',repr(row))
    def test_failure_before_preparer_load_is_not_opaque(self):
        for where in ('fetch','stage','load'):
            code,events,row,p,d=self.invoke(where=where,error=ValueError('secret'))
            self.assertEqual(code,2);self.assertEqual(row['preparation_phase'],'UNAVAILABLE')
            self.assertEqual(row['outer_phase'],{'fetch':'AUTHENTICATE_PREPARATION_SOURCES','stage':'VERIFY_EXISTING_STAGING','load':'LOAD_FROZEN_PREPARER'}[where])
            self.assertTrue(row['code_locations']);self.assertNotIn('propose',events)
    def test_timeout_before_moduleload_retains_safe_phase(self):
        code,events,row,p,d=self.invoke(where='load',error=x.DiagnosticHold('DEADLINE'))
        self.assertEqual(row['failure_label'],'DEADLINE');self.assertEqual(row['preparation_phase'],'UNAVAILABLE')
    def test_cleanup_flag_survives_primary_failure(self):
        error=ValueError('secret');error.preparation_cleanup_failed=True
        code,events,row,p,d=self.invoke(where='propose',error=error)
        self.assertTrue(row['cleanup_unknown']);self.assertEqual(row['failure_code'],'ValueError')
    def test_each_verified_dependency_cleanup_class_is_reported(self):
        for where in ('delivery_cleanup','preparer_cleanup'):
            code,events,row,p,d=self.invoke(where=where)
            self.assertEqual(code,2);self.assertTrue(row['cleanup_unknown']);self.assertEqual(row['failure_code'],'CleanupError')
    def test_unknown_exception_class_name_is_not_echoed(self):
        error=type('PrivateRuntimeValue',(Exception,),{})('private text')
        code,events,row,p,d=self.invoke(where='propose',error=error)
        self.assertEqual(row['failure_code'],'DEPENDENCY_ERROR');self.assertNotIn('PrivateRuntimeValue',repr(row))
    def test_unknown_phase_and_unknown_code_filename_never_echo(self):
        p=types.SimpleNamespace(CURRENT_PHASE=['private'],PHASES={'COLLECT_INPUTS'},CleanupError=type('C', (Exception,),{}))
        namespace={};exec(compile("def f(): raise ValueError('secret')",'/private/configuration','exec'),namespace)
        try:namespace['f']()
        except ValueError as error:row=x.failure(error,'private',p,None,frozenset())
        self.assertEqual(row['preparation_phase'],'UNAVAILABLE');self.assertEqual(row['outer_phase'],'INPUT_VALIDATION')
        self.assertNotIn('private',repr(row));self.assertEqual(row['code_locations'],[])

class NetworkAndBudgetTests(unittest.TestCase):
    def response(self):return types.SimpleNamespace(status=200,geturl=lambda:x.DELIVERY_URL,headers={'Content-Length':str(len(RAW))},read=mock.Mock(return_value=RAW),close=mock.Mock())
    def test_exact_bounded_download_and_close(self):
        r=self.response();opener=types.SimpleNamespace(open=mock.Mock(return_value=r))
        with mock.patch.object(x.urllib.request,'build_opener',return_value=opener):self.assertEqual(x.download_delivery(time.monotonic()+10),RAW)
        self.assertEqual(opener.open.call_args[0][0].full_url,x.DELIVERY_URL);r.read.assert_called_once_with(14951);r.close.assert_called_once_with()
    def test_bad_response_encoding_length_url_and_bytes_refuse(self):
        for field in ('status','encoding','length','url','bytes'):
            r=self.response()
            if field=='status':r.status=302
            elif field=='encoding':r.headers['Content-Encoding']='gzip'
            elif field=='length':r.headers['Content-Length']='1'
            elif field=='url':r.geturl=lambda:'https://unapproved.invalid/'
            else:r.read.return_value=b'X'+RAW[1:]
            with mock.patch.object(x.urllib.request,'build_opener',return_value=types.SimpleNamespace(open=lambda *a,**k:r)):
                with self.assertRaises(x.DiagnosticHold):x.download_delivery(time.monotonic()+10)
            r.close.assert_called_once_with()
    def test_primary_network_failure_preserves_cleanup_uncertainty(self):
        r=self.response();primary=OSError(errno.EIO,'secret');r.read.side_effect=primary;r.close.side_effect=OSError('secret')
        with mock.patch.object(x.urllib.request,'build_opener',return_value=types.SimpleNamespace(open=lambda *a,**k:r)):
            with self.assertRaises(OSError) as caught:x.download_delivery(time.monotonic()+10)
        self.assertIs(caught.exception,primary);self.assertTrue(primary.diagnostic_cleanup_failed)
    def test_initial_alarm_failure_restores_handler(self):
        old=object();primary=OSError('secret')
        with mock.patch.object(x.signal,'getitimer',return_value=(0.,0.)),mock.patch.object(x.signal,'getsignal',return_value=old),\
             mock.patch.object(x.signal,'signal') as handler,mock.patch.object(x.signal,'setitimer',side_effect=[primary,None]):
            with self.assertRaises(OSError):
                with x.budget(1):self.fail('must not yield')
        self.assertEqual(handler.call_args_list[-1],mock.call(signal.SIGALRM,old))
    def test_status_unavailable_is_attempted_once(self):
        with mock.patch.object(x,'output',side_effect=x.StatusDeliveryError()) as output:
            self.assertEqual(x.main(['forbidden']),2)
        self.assertEqual(output.call_count,1)
    def test_projection_failure_has_one_static_fallback_without_traceback(self):
        with mock.patch.object(x,'failure',side_effect=ValueError('private text')),mock.patch.object(x,'output') as output:
            self.assertEqual(x.main(['forbidden']),2)
        self.assertEqual(output.call_count,1);row=output.call_args[0][0]
        self.assertEqual(row['failure_code'],'DIAGNOSTIC_PROJECTION_FAILED');self.assertNotIn('private',repr(row))
        self.assertTrue(row['cleanup_unknown'])
    def test_blocked_status_sink_is_bounded_without_retry(self):
        import fcntl
        read,write=os.pipe();actual=os.write;old=signal.getsignal(signal.SIGALRM);original_budget=x.budget
        try:
            flags=fcntl.fcntl(write,fcntl.F_GETFL);fcntl.fcntl(write,fcntl.F_SETFL,flags|os.O_NONBLOCK)
            while True:
                try:actual(write,b'x'*4096)
                except BlockingIOError:break
            fcntl.fcntl(write,fcntl.F_SETFL,flags);start=time.monotonic()
            with mock.patch.object(x,'budget',side_effect=lambda seconds:original_budget(.05)),\
                 mock.patch.object(x.os,'write',side_effect=lambda fd,raw:actual(write,raw)):
                with self.assertRaises(x.StatusDeliveryError):x.output({'state':'HOLD'})
            self.assertLess(time.monotonic()-start,1);self.assertEqual(signal.getsignal(signal.SIGALRM),old)
        finally:os.close(write);os.close(read)
    def test_oversize_status_refuses_before_write(self):
        with mock.patch.object(x.os,'write') as write:
            with self.assertRaises(x.StatusDeliveryError):x.output({'data':'x'*131072})
        write.assert_not_called()
    def test_status_is_direct_bounded_json(self):
        writes=[]
        with mock.patch.object(x.os,'write',side_effect=lambda fd,raw:(writes.append((fd,raw)) or len(raw))):x.output({'state':'HOLD'})
        self.assertEqual(writes,[(1,b'{"state":"HOLD"}\n')])

if __name__=='__main__':unittest.main(verbosity=2)
