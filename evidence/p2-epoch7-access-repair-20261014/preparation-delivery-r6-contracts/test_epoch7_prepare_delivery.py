"""Public local delivery boundaries. Synthetic identities; no external requests."""
import contextlib,errno,hashlib,importlib.util,io,json,os,pathlib,signal,stat,tempfile,time,types,unittest
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('epoch7_prepare_delivery',str(ROOT/'epoch7_prepare_delivery.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

PREPARATION_ROOT=ROOT/'fixtures/preparation-source'
def sources():return {name:(PREPARATION_ROOT/name).read_bytes() for name in m.SOURCES}
def mapped(info):
    row={name:getattr(info,name) for name in dir(info) if name.startswith('st_')};row.update(st_uid=0,st_gid=0)
    return types.SimpleNamespace(**row)
def proxy():
    p=types.SimpleNamespace(**{name:getattr(os,name) for name in dir(os) if not name.startswith('__')})
    p.fstat=lambda fd:mapped(os.fstat(fd));p.stat=lambda *args,**kw:mapped(os.stat(*args,**kw));p.geteuid=lambda:0;p.getegid=lambda:0
    return p

class ContractTests(unittest.TestCase):
    def test_r6_contracts_publication_and_genuine_observation_bound(self):
        self.assertIs(m.PINS_BOUND,True)
        self.assertEqual(m.PUBLICATION_COMMIT,'8ab751a84922b76b80c8e8641cbe96e82fa5d391')
        self.assertEqual(m.PUBLIC_PREFIX,'evidence/p2-epoch7-access-repair-20261014/preparation-source-r6-contracts/')
        self.assertEqual(m.PREP_ROOT,m.CAND+'/epoch7-preparation-candidate-r6-contracts')
        self.assertEqual(m.OBSERVATION_PATH,m.CAND+'/epoch7-observation-1311b9e9fa97cfd4.private.json')
        self.assertEqual(m.OBSERVATION_SHA256,'b961df049e2861e4706f28f29fcf994a14fe28e153263a23ec82d4e822b9b246')
        m.bound()

    def test_different_valid_observation_binding_refuses_before_host_or_download(self):
        rows=((m.CAND+'/epoch7-observation-'+'1'*16+'.private.json',m.OBSERVATION_SHA256),
              (m.OBSERVATION_PATH,'1'*64))
        for path,pin in rows:
            with self.subTest(path=path),mock.patch.object(m,'PINS_BOUND',True),mock.patch.object(m,'PUBLICATION_COMMIT','a'*40),\
                 mock.patch.object(m.os,'geteuid') as uid,\
                 mock.patch.object(m,'fetch_sources') as fetch,mock.patch.object(m,'stage') as stage:
                with self.assertRaisesRegex(m.Hold,'OBSERVATION_BINDING'):
                    m.run(['--observation',path,'--observation-sha256',pin])
                uid.assert_not_called();fetch.assert_not_called();stage.assert_not_called()
    def test_prepare_or_resume_arguments_refuse_without_effects(self):
        for operation in ('prepare','resume'):
            with mock.patch.object(m,'fetch_sources') as fetch,mock.patch.object(m,'stage') as stage:
                with self.assertRaisesRegex(m.Hold,'ARGUMENTS'):
                    m.run(['--observation',m.OBSERVATION_PATH,'--observation-sha256',m.OBSERVATION_SHA256,
                           '--operation',operation])
                fetch.assert_not_called();stage.assert_not_called()
    def test_unbound_refuses_before_network_or_filesystem(self):
        with mock.patch.object(m,'PINS_BOUND',False),mock.patch.object(m,'fetch_sources') as fetch,\
             mock.patch.object(m,'stage') as stage,mock.patch.object(m,'deliver_status') as status:
            self.assertEqual(m.entrypoint(['--observation','/not-authority','--observation-sha256','1'*64]),2)
        fetch.assert_not_called();stage.assert_not_called();self.assertEqual(status.call_args[0][0]['failure_label'],'UNBOUND')
    def test_all_three_pins_are_real_frozen_bytes(self):self.assertEqual(m.validate_sources(sources()),sources())
    def test_missing_extra_changed_wrongtype_sources_reject(self):
        for mode in ('missing','extra','changed','type'):
            cache=sources()
            if mode=='missing':cache.pop('epoch7_prepare.py')
            elif mode=='extra':cache['arbitrary.py']=b'x'
            elif mode=='changed':cache['epoch7_prepare.py']+=b'x'
            else:cache['epoch7_prepare.py']='not bytes'
            with self.subTest(mode=mode),self.assertRaises(m.Hold):m.validate_sources(cache)
    def test_preparer_loads_only_actual_pinned_wrapper(self):
        p=m.preparer(sources());self.assertEqual(p.PREP_ROOT,m.PREP_ROOT);self.assertEqual(p.__file__,m.PREP_ROOT+'/epoch7_prepare.py')
    def test_bad_observation_path_or_hash_refuses_before_download(self):
        for path,pin in (('/tmp/unknown','1'*64),(m.CAND+'/epoch7-observation-'+'1'*16+'.private.json','not a hash')):
            with mock.patch.object(m,'PINS_BOUND',True),mock.patch.object(m,'PUBLICATION_COMMIT','a'*40),\
                 mock.patch.object(m,'fetch_sources') as fetch,self.assertRaisesRegex(m.Hold,'ARGUMENTS'):
                m.run(['--observation',path,'--observation-sha256',pin])
            fetch.assert_not_called()
    def test_root_and_host_checks_precede_download(self):
        for uid,gid,host in ((1000,0,m.HOST),(0,1000,m.HOST),(0,0,'unknown')):
            with mock.patch.object(m,'PINS_BOUND',True),mock.patch.object(m,'PUBLICATION_COMMIT','a'*40),\
                 mock.patch.object(m.os,'geteuid',return_value=uid),mock.patch.object(m.os,'getegid',return_value=gid),\
                 mock.patch.object(m.socket,'gethostname',return_value=host),mock.patch.object(m,'fetch_sources') as fetch:
                with self.assertRaisesRegex(m.Hold,'ROOT_HOST'):m.run(['--observation',m.OBSERVATION_PATH,'--observation-sha256',m.OBSERVATION_SHA256])
                fetch.assert_not_called()

class DownloadTests(unittest.TestCase):
    def response(self,name,raw=None):
        body=sources()[name] if raw is None else raw
        return types.SimpleNamespace(status=200,geturl=lambda:m.RAW_PREFIX+'a'*40+'/'+m.PUBLIC_PREFIX+name,
            headers={'Content-Length':str(m.SOURCES[name][1])},read=mock.Mock(return_value=body),close=mock.Mock())
    def call(self,responses):
        opener=types.SimpleNamespace(open=mock.Mock(side_effect=responses))
        with mock.patch.object(m,'PINS_BOUND',True),mock.patch.object(m,'PUBLICATION_COMMIT','a'*40),\
             mock.patch.object(m.urllib.request,'build_opener',return_value=opener):result=m.fetch_sources(time.monotonic()+10)
        return result,opener
    def test_exact_three_https_requests_bounded_identity_no_redirect(self):
        rows=[self.response(name) for name in sorted(m.SOURCES)];result,opener=self.call(rows)
        self.assertEqual(result,sources());self.assertEqual(opener.open.call_count,3)
        for call,name,row in zip(opener.open.call_args_list,sorted(m.SOURCES),rows):
            request=call[0][0];self.assertEqual(request.full_url,m.RAW_PREFIX+'a'*40+'/'+m.PUBLIC_PREFIX+name)
            self.assertEqual(request.get_header('Accept-encoding'),'identity');self.assertLessEqual(call[1]['timeout'],10)
            row.read.assert_called_once_with(m.SOURCES[name][1]+1);row.close.assert_called_once_with()
        with self.assertRaisesRegex(m.Hold,'REDIRECT'):m.NoRedirect().redirect_request(None)
    def test_hash_encoding_length_status_url_and_oversize_refuse(self):
        for field in ('bytes','encoding','length','status','url','oversize'):
            name=sorted(m.SOURCES)[0];row=self.response(name)
            if field=='bytes':row.read.return_value=b'unknown'
            elif field=='oversize':row.read.return_value=sources()[name]+b'x'
            elif field=='encoding':row.headers['Content-Encoding']='gzip'
            elif field=='length':row.headers['Content-Length']='1'
            elif field=='status':row.status=302
            else:row.geturl=lambda:'https://unapproved.invalid/'
            with self.subTest(field=field),self.assertRaises(m.Hold):self.call([row])
            row.close.assert_called_once_with()
    def test_primary_download_error_survives_close_error(self):
        row=self.response(sorted(m.SOURCES)[0]);primary=OSError(errno.EIO,'private');row.read.side_effect=primary;row.close.side_effect=OSError(errno.EIO,'cleanup')
        with self.assertRaises(OSError) as caught:self.call([row])
        self.assertIs(caught.exception,primary);self.assertTrue(primary.delivery_cleanup_failed)
    def test_close_error_without_primary_refuses(self):
        row=self.response(sorted(m.SOURCES)[0]);row.close.side_effect=OSError(errno.EIO,'private')
        with self.assertRaises(m.CleanupError):self.call([row])

class FilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='delivery-',dir=str(ROOT));self.addCleanup(self.temp.cleanup)
        self.parent=self.temp.name;self.dest=self.parent+'/epoch7-preparation-candidate-r6-contracts';self.os=proxy()
        for name,value in (('CAND',self.parent),('PREP_ROOT',self.dest),('os',self.os)):
            patch=mock.patch.object(m,name,value);patch.start();self.addCleanup(patch.stop)
    def stage(self):return m.stage(sources(),time.monotonic()+20)
    def test_new_exact_files_modes_and_exact_reuse(self):
        first=self.stage();self.assertEqual(first['state'],'STAGED_EXACT');self.assertEqual(len(first['created_paths']),4)
        self.assertEqual(stat.S_IMODE(os.stat(self.dest).st_mode),0o700)
        before={}
        for name,raw in sources().items():
            path=self.dest+'/'+name;self.assertEqual(pathlib.Path(path).read_bytes(),raw)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode),0o600);before[name]=os.stat(path)
        with mock.patch.object(self.os,'mkdir',side_effect=AssertionError('no write')),mock.patch.object(self.os,'write',side_effect=AssertionError('no write')):
            second=self.stage()
        self.assertEqual(second['state'],'REUSED_EXACT');self.assertEqual(second['created_paths'],[])
        self.assertEqual({name:os.stat(self.dest+'/'+name) for name in sources()},before)
    def test_historical_r5_and_r6_directories_are_untouched(self):
        before={}
        for leaf in ('epoch7-preparation-candidate','epoch7-preparation-candidate-r6'):
            prior=self.parent+'/'+leaf;os.mkdir(prior,0o700)
            marker=pathlib.Path(prior)/'retained';marker.write_bytes(b'public test fixture');os.chmod(str(marker),0o600)
            before[prior]=(os.stat(prior),os.stat(str(marker)),marker.read_bytes())
        result=self.stage();self.assertEqual(result['path'],self.dest)
        for prior,wanted in before.items():
            marker=pathlib.Path(prior)/'retained'
            self.assertEqual((os.stat(prior),os.stat(str(marker)),marker.read_bytes()),wanted)
            self.assertNotIn(prior,result['created_paths'])
    def test_wrong_root_refuses_before_descriptor_open(self):
        with mock.patch.object(self.os,'geteuid',return_value=1000),mock.patch.object(self.os,'open') as opened:
            with self.assertRaisesRegex(m.Hold,'ROOT_HOST'):self.stage()
        opened.assert_not_called()
    def test_invalid_cache_refuses_before_any_directory_read(self):
        with mock.patch.object(self.os,'open') as opened:
            with self.assertRaisesRegex(m.Hold,'SOURCE_SET'):m.stage({},time.monotonic()+1)
        opened.assert_not_called()
    def test_destination_symlink_and_regular_file_reject(self):
        for kind in ('symlink','file'):
            if kind=='symlink':os.symlink(self.parent,self.dest)
            else:pathlib.Path(self.dest).write_bytes(b'fixed')
            try:
                with self.assertRaisesRegex(m.Hold,'DIRECTORY'):self.stage()
            finally:os.unlink(self.dest)
    def test_partial_or_extra_existing_inventory_reject_without_writes(self):
        os.mkdir(self.dest,0o700)
        with self.assertRaisesRegex(m.Hold,'INVENTORY'):self.stage()
        for name,raw in sources().items():pathlib.Path(self.dest+'/'+name).write_bytes(raw);os.chmod(self.dest+'/'+name,0o600)
        pathlib.Path(self.dest+'/unknown').write_bytes(b'x')
        with self.assertRaises(m.Hold):self.stage()
    def test_wrong_directory_mode_and_wrong_file_mode_reject(self):
        self.stage();os.chmod(self.dest,0o755)
        with self.assertRaisesRegex(m.Hold,'ANCESTRY'):self.stage()
        os.chmod(self.dest,0o700);os.chmod(self.dest+'/epoch7_prepare.py',0o644)
        with self.assertRaisesRegex(m.Hold,'FILE_AUTHORITY'):self.stage()
    def test_hardlink_and_leaf_symlink_refuse(self):
        self.stage();name='epoch7_prepare.py';target=self.dest+'/'+name
        os.link(target,self.parent+'/linked')
        with self.assertRaisesRegex(m.Hold,'FILE_AUTHORITY'):self.stage()
        os.unlink(self.parent+'/linked');os.rename(target,self.parent+'/actual');os.symlink(self.parent+'/actual',target)
        with self.assertRaises(OSError):self.stage()
    def test_wrong_existing_bytes_never_overwritten(self):
        self.stage();path=self.dest+'/epoch7_prepare.py';raw=pathlib.Path(path).read_bytes();pathlib.Path(path).write_bytes(b'X'+raw[1:])
        with self.assertRaisesRegex(m.Hold,'FILE_BYTES'):self.stage()
        self.assertEqual(pathlib.Path(path).read_bytes(),b'X'+raw[1:])
    def test_partial_write_reports_directory_and_partial_file(self):
        original=self.os.write;calls=[0]
        def write(fd,raw):
            calls[0]+=1
            if calls[0]==2:raise OSError(errno.ENOSPC,'secret')
            return original(fd,raw)
        with mock.patch.object(self.os,'write',side_effect=write):
            with self.assertRaises(OSError) as caught:self.stage()
        paths=caught.exception.delivery_created_paths;self.assertEqual(paths,[self.dest,self.dest+'/epoch7_prepare.py'])
        self.assertEqual(os.stat(paths[1]).st_size,16384)
        self.assertEqual(stat.S_IMODE(os.stat(paths[1]).st_mode),0o600)
    def test_unrelated_parent_entry_during_creation_refuses(self):
        original=self.os.mkdir
        def mkdir(*args,**kwargs):
            original(*args,**kwargs);pathlib.Path(self.parent+'/unrelated').write_bytes(b'x')
        with mock.patch.object(self.os,'mkdir',side_effect=mkdir):
            with self.assertRaisesRegex(m.Hold,'OWNED_PARENT') as caught:self.stage()
        self.assertEqual(len(caught.exception.delivery_created_paths),4)
    def test_leaf_replacement_between_open_and_read_refuses(self):
        self.stage();original=self.os.open;done=[False]
        def opened(path,*args,**kwargs):
            fd=original(path,*args,**kwargs)
            if path=='epoch7_prepare.py' and not done[0]:
                done[0]=True;target=self.dest+'/'+path;os.rename(target,target+'.old');pathlib.Path(target).write_bytes(sources()[path]);os.chmod(target,0o600)
            return fd
        with mock.patch.object(self.os,'open',side_effect=opened):
            with self.assertRaisesRegex(m.Hold,'FILE_RACE'):self.stage()
    def test_cleanup_attempts_all_owned_descriptors_preserving_primary(self):
        primary=ValueError('fixed')
        with mock.patch.object(self.os,'close',side_effect=OSError(errno.EIO,'private')) as close:m.close_all([1,2,3],primary)
        self.assertEqual(close.call_args_list,[mock.call(3),mock.call(2),mock.call(1)]);self.assertTrue(primary.delivery_cleanup_failed)
    def test_first_ancestor_failure_closes_open_fd(self):
        original=self.os.close
        with mock.patch.object(self.os,'getxattr',side_effect=OSError(errno.EIO,'private')),mock.patch.object(self.os,'close',side_effect=original) as close:
            with self.assertRaisesRegex(m.Hold,'XATTR'):self.stage()
        self.assertEqual(close.call_count,1)

class DeadlineTests(unittest.TestCase):
    def test_initial_arm_failure_restores_handler(self):
        primary=OSError(errno.EIO,'private');old=object()
        with mock.patch.object(m.signal,'getitimer',return_value=(0.,0.)),mock.patch.object(m.signal,'getsignal',return_value=old),\
             mock.patch.object(m.signal,'signal') as handler,mock.patch.object(m.signal,'setitimer',side_effect=[primary,None]):
            with self.assertRaises(OSError) as caught:
                with m.budget(1):self.fail('must not yield')
        self.assertIs(caught.exception,primary);self.assertEqual(handler.call_args_list[-1],mock.call(signal.SIGALRM,old))
    def test_final_deadline_check_catches_late_success(self):
        with mock.patch.object(m.signal,'getitimer',return_value=(0.,0.)),mock.patch.object(m.signal,'getsignal',return_value=None),\
             mock.patch.object(m.signal,'signal'),mock.patch.object(m.signal,'setitimer'),mock.patch.object(m.time,'monotonic',side_effect=[0,2]):
            with self.assertRaisesRegex(m.Hold,'DEADLINE'):
                with m.budget(1):pass
    def test_status_uses_exact_direct_bytes_and_no_retry_after_failure(self):
        values=[]
        with mock.patch.object(m.os,'write',side_effect=lambda fd,raw:(values.append((fd,raw)) or len(raw))):m.deliver_status({'state':'HOLD'})
        self.assertEqual(values,[(1,b'{"state":"HOLD"}\n')])
        with mock.patch.object(m,'run',side_effect=m.StatusDeliveryError()),mock.patch.object(m,'deliver_status') as deliver:self.assertEqual(m.entrypoint([]),2)
        deliver.assert_not_called()
    def test_bounded_status_blocked_pipe_and_handler_restore(self):
        import fcntl
        read,write=os.pipe();actual=os.write;old=signal.getsignal(signal.SIGALRM)
        try:
            flags=fcntl.fcntl(write,fcntl.F_GETFL);fcntl.fcntl(write,fcntl.F_SETFL,flags|os.O_NONBLOCK)
            while True:
                try:actual(write,b'x'*4096)
                except BlockingIOError:break
            fcntl.fcntl(write,fcntl.F_SETFL,flags)
            start=time.monotonic()
            with mock.patch.object(m,'STATUS_SECONDS',.05),mock.patch.object(m.os,'write',side_effect=lambda fd,raw:actual(write,raw)):
                with self.assertRaises(m.StatusDeliveryError):m.deliver_status({'state':'HOLD'})
            self.assertLess(time.monotonic()-start,1);self.assertEqual(signal.getsignal(signal.SIGALRM),old)
        finally:os.close(write);os.close(read)

class FlowTests(unittest.TestCase):
    def invoke(self,stage_error=None,proposal_error=None,load_error=None):
        @contextlib.contextmanager
        def scope(*args):yield time.monotonic()+10
        staged={'state':'STAGED_EXACT','created_paths':[m.PREP_ROOT,m.PREP_ROOT+'/epoch7_prepare.py']}
        actual=m.preparer(sources())
        module=types.SimpleNamespace(CleanupError=actual.CleanupError,budget=scope,run_preparation=mock.Mock(side_effect=proposal_error,return_value={'state':'TOPOLOGY_REVIEW_REQUIRED'}))
        events=[]
        def fetch(end):events.append('download_all');return sources()
        def load(cache):
            events.append('load')
            if load_error is not None:raise load_error
            self.assertTrue(time.monotonic()<deadline[0])
            return module
        deadline=[0]
        @contextlib.contextmanager
        def outer_scope(*args):
            deadline[0]=time.monotonic()+10
            try:yield deadline[0]
            finally:deadline[0]=0
        def stage(cache,end,allow_create=True):
            events.append('create' if allow_create else 'verify_only')
            if stage_error is not None and not allow_create:raise stage_error
            return staged
        with mock.patch.object(m,'PINS_BOUND',True),mock.patch.object(m,'PUBLICATION_COMMIT','a'*40),\
             mock.patch.object(m.os,'geteuid',return_value=0),mock.patch.object(m.os,'getegid',return_value=0),\
             mock.patch.object(m.socket,'gethostname',return_value=m.HOST),mock.patch.object(m,'fetch_sources',fetch),\
             mock.patch.object(m,'stage',stage),mock.patch.object(m,'preparer',side_effect=load),\
             mock.patch.object(m,'budget',outer_scope),mock.patch.object(m,'deliver_status') as deliver,\
             mock.patch.object(m.sys,'flags',types.SimpleNamespace(isolated=1,no_site=1)),mock.patch.object(m.sys,'dont_write_bytecode',True):
            code=m.entrypoint(['--observation',m.OBSERVATION_PATH,'--observation-sha256',m.OBSERVATION_SHA256])
        return code,events,module,deliver.call_args[0][0],staged
    def test_download_before_create_and_only_proposal_then_verify(self):
        code,events,module,row,staged=self.invoke();self.assertEqual(code,0)
        self.assertEqual(events,['download_all','load','create','verify_only'])
        args=module.run_preparation.call_args[0][0]
        self.assertEqual(args.operation,'propose-topology');self.assertIsNone(args.topology_review_id);self.assertIsNone(args.retained_renewal_timer)
        self.assertEqual(row['staging'],staged);self.assertEqual(row['install_admission'],'NOT_GRANTED')
    def test_proposal_failure_reports_every_staged_path(self):
        primary=ValueError('untrusted private text')
        code,events,module,row,staged=self.invoke(proposal_error=primary)
        self.assertEqual(code,2);self.assertEqual(events,['download_all','load','create'])
        self.assertEqual(row['created_paths'],staged['created_paths']);self.assertNotIn('untrusted',repr(row))
    def test_post_proposal_source_or_inventory_drift_refuses_output(self):
        code,events,module,row,staged=self.invoke(stage_error=m.Hold('FILE_BYTES'))
        self.assertEqual(code,2);self.assertEqual(row['failure_label'],'FILE_BYTES')
        self.assertEqual(row['created_paths'],staged['created_paths']);self.assertNotIn('proposal',row)
    def test_verified_load_interrupt_is_bounded_before_creation(self):
        code,events,module,row,staged=self.invoke(load_error=m.DeadlineError())
        self.assertEqual(code,2);self.assertEqual(events,['download_all','load'])
        self.assertEqual(row['created_paths'],[]);self.assertEqual(row['phase'],'LOAD_VERIFIED_PREPARER')
    def test_distinct_preparer_cleanup_class_marks_uncertainty(self):
        actual=m.preparer(sources());primary=actual.CleanupError()
        self.assertIsNot(actual.CleanupError,m.CleanupError)
        # Use that same exact verified class for this invocation's module.
        with mock.patch.object(m,'preparer',return_value=actual):
            code,events,module,row,staged=self.invoke(proposal_error=primary)
        self.assertEqual(code,2);self.assertTrue(row['cleanup_unknown'])
        self.assertEqual(row['created_paths'],staged['created_paths'])
    def test_verification_only_cannot_create_missing_directory(self):
        with tempfile.TemporaryDirectory(prefix='delivery-verify-',dir=str(ROOT)) as root:
            with mock.patch.object(m,'CAND',root),mock.patch.object(m,'PREP_ROOT',root+'/epoch7-preparation-candidate-r6-contracts'),mock.patch.object(m,'os',proxy()):
                with self.assertRaisesRegex(m.Hold,'DIRECTORY'):m.stage(sources(),time.monotonic()+10,allow_create=False)
            self.assertEqual(os.listdir(root),[])


class BootstrapTemplateTests(unittest.TestCase):
    def load(self):
        raw=(ROOT/'OWNER_PREPARATION_UNBOUND.txt').read_text()
        body=raw.split("<<'PY'\n",1)[1].rsplit('\nPY',1)[0]
        module=types.ModuleType('test_verified_delivery_template')
        exec(compile(body,'<unbound-owner-template>','exec'),module.__dict__)
        return module
    def test_template_binds_observation_but_has_no_delivery_publication(self):
        module=self.load()
        for name in ('DELIVERY_COMMIT','DELIVERY_SHA256','DELIVERY_BYTES'):
            self.assertIsNone(getattr(module,name))
        self.assertEqual(module.OBSERVATION_PATH,m.OBSERVATION_PATH)
        self.assertEqual(module.OBSERVATION_SHA256,m.OBSERVATION_SHA256)
        self.assertEqual(module.SOURCE_PATH,'evidence/p2-epoch7-access-repair-20261014/preparation-delivery-r6-contracts/epoch7_prepare_delivery.py')
    def test_default_template_is_unbound_and_performs_no_download(self):
        module=self.load()
        with mock.patch.object(module,'output') as output,mock.patch.object(module.urllib.request,'build_opener') as opener:
            self.assertEqual(module.main(),2)
        opener.assert_not_called();self.assertEqual(output.call_args[0][0]['phase'],'BINDING_CHECK')
    def test_template_arm_failure_restores_prior_handler(self):
        module=self.load();primary=OSError(errno.EIO,'secret');old=object()
        with mock.patch.object(module.signal,'getitimer',return_value=(0.,0.)),mock.patch.object(module.signal,'getsignal',return_value=old),\
             mock.patch.object(module.signal,'signal') as handler,mock.patch.object(module.signal,'setitimer',side_effect=[primary,None]):
            with self.assertRaises(OSError) as caught:
                with module.budget(1):self.fail('must not yield')
        self.assertIs(caught.exception,primary);self.assertEqual(handler.call_args_list[-1],mock.call(signal.SIGALRM,old))
    def test_template_static_failure_does_not_echo_sensitive_text(self):
        module=self.load()
        with mock.patch.object(module,'need',side_effect=ValueError('private-text')),mock.patch.object(module,'output') as output:
            self.assertEqual(module.main(),2)
        self.assertNotIn('private-text',repr(output.call_args[0][0]))


if __name__=='__main__':unittest.main(verbosity=2)
