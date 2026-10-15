"""Synthetic tests only; no host, RPM, service, probe or permission operations."""
import ast,contextlib,copy,hashlib,io,json,pathlib,signal,sys,time,types,unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parent
d=types.ModuleType('writer_diagnostic_under_test');d.__file__=str(HERE/'diagnose_writer_pair.py')
exec(compile(pathlib.Path(d.__file__).read_bytes(),d.__file__,'exec'),d.__dict__)


def row():
    return {'manager':{'uids':[0]*4,'channels':{'/run/systemd/private':{'ino':3}}},
        'units':{'test.service':{'state':{'Id':'test.service','ActiveState':'inactive'},'cgroup_entries':{}}},
        'masks':{'/etc/systemd/system/test.service':{'mode':511,'kind':'MASK','link':'/dev/null'}},
        'scheduler_sha256':'a'*64,'control_files':{'/private/SECRET_PATH':{'sha256':'b'*64}},
        'processes':{'process_identity_sha256':'c'*64,'fd_count':12,'background_processes':[{'SECRET_ARGV':'SECRET_VALUE'}],'background_processes_sha256':'d'*64}}


def capture_pair(a=None,b=None):
    cap=d.Capture()
    for value in (row() if a is None else a,row() if b is None else b):cap.call(lambda:value,lambda unused:None)
    return cap


def project(cap):return d.project(cap,('test.service',),('/etc/systemd/system/test.service',))


class CaptureTests(unittest.TestCase):
    def test_original_object_returned(self):
        v=row();c=d.Capture();self.assertIs(c.call(lambda:v,lambda x:None),v)
    def test_copy_not_shared(self):
        v=row();c=d.Capture();c.call(lambda:v,lambda x:None);v['manager']['uids'][0]=77;self.assertEqual(c.samples[0]['manager']['uids'][0],0)
    def test_before_call_bound(self):
        c=capture_pair();operation=mock.Mock(return_value=row())
        with self.assertRaisesRegex(ValueError,'WRITER_CAPTURE_CALL_BOUND'):c.call(operation,lambda x:None)
        operation.assert_not_called();self.assertEqual(c.calls,2)
    def test_failed_call_counts(self):
        c=d.Capture();fail=ValueError('fixture')
        with self.assertRaises(ValueError) as got:c.call(lambda:(_ for _ in ()).throw(fail),lambda x:None)
        self.assertIs(got.exception,fail);self.assertEqual(c.calls,1);self.assertEqual(c.samples,[])
    def test_invalid_sample_stops(self):
        c=d.Capture();fail=ValueError('WRITER_NOT_STOPPED')
        with self.assertRaises(ValueError) as got:c.call(row,lambda x:(_ for _ in ()).throw(fail))
        self.assertIs(got.exception,fail);self.assertEqual(c.samples,[])
    def test_size_bound(self):
        with self.assertRaisesRegex(ValueError,'WRITER_CAPTURE_SIZE_BOUND'):d.canonical({'value':'x'*100},20)
    def test_nan_refused(self):
        with self.assertRaises(ValueError):d.canonical({'value':float('nan')})
    def test_ns_integer_exact(self):
        value={'ctime_ns':1777777777777777777};c=d.Capture();c.call(lambda:value,lambda x:None);self.assertEqual(c.samples,[value])
    def test_recording_subclass_unchanged_super(self):
        value=row();base_calls=[]
        class Base:
            def writers(self,p,paths):base_calls.append((p,paths));return value
        c=d.Capture();reader=d.recording_io(Base,lambda x:None,c)()
        self.assertIs(reader.writers('policy','paths'),value);self.assertEqual(base_calls,[('policy','paths')])


class ProjectionTests(unittest.TestCase):
    def test_equal(self):self.assertTrue(project(capture_pair())['exact_pair_equal'])
    def test_empty_not_equal(self):self.assertEqual(project(d.Capture())['pair_state'],'UNKNOWN_NOT_REACHED')
    def test_single_not_equal(self):
        c=d.Capture();c.call(row,lambda x:None);self.assertNotIn('exact_pair_equal',project(c))
    def test_process_difference_only(self):
        a=row();b=copy.deepcopy(a);b['processes']['fd_count']=13
        p=project(capture_pair(a,b));self.assertEqual(p['changed_sections'],['processes']);self.assertEqual(p['sections']['processes']['fd_count_after'],13);self.assertEqual(p['global_process_churn_cause'],'NOT_ATTRIBUTED')
    def test_no_private_strings(self):
        a=row();b=copy.deepcopy(a);b['control_files']['SECRET_NEW_PATH']={'content':'SECRET_CONFIG'};b['manager']['SECRET_FIELD']='SECRET_VALUE2'
        raw=json.dumps(project(capture_pair(a,b)))
        for text in ('SECRET_PATH','SECRET_NEW_PATH','SECRET_CONFIG','SECRET_FIELD','SECRET_VALUE','SECRET_ARGV'):self.assertNotIn(text,raw)
    def test_unit_field_names_only(self):
        a=row();b=copy.deepcopy(a);b['units']['test.service']['state']['FragmentPath']='/private/SECRET_UNIT'
        p=project(capture_pair(a,b));self.assertEqual(p['sections']['units']['rows']['test.service']['state']['changed_fields'],['FragmentPath']);self.assertNotIn('SECRET_UNIT',json.dumps(p))
    def test_manager_channel_metadata_names(self):
        a=row();b=copy.deepcopy(a);b['manager']['channels']['/run/systemd/private']['ino']=999
        p=project(capture_pair(a,b));self.assertEqual(p['sections']['manager']['channels']['/run/systemd/private']['changed_fields'],['ino']);self.assertNotIn('999',json.dumps(p))
    def test_masks_changed_field_names(self):
        a=row();b=copy.deepcopy(a);b['masks']['/etc/systemd/system/test.service']['ino']=777
        self.assertEqual(project(capture_pair(a,b))['sections']['masks']['rows']['/etc/systemd/system/test.service']['changed_fields'],['ino'])
    def test_cgroup_count_not_paths(self):
        a=row();b=copy.deepcopy(a);b['units']['test.service']['cgroup_entries']['SECRET_CGROUP']='e'*64
        p=project(capture_pair(a,b));self.assertEqual(p['sections']['units']['rows']['test.service']['cgroup_entries']['after_count'],1);self.assertNotIn('SECRET_CGROUP',json.dumps(p))
    def test_public_literal_error_only(self):
        codes=d.public_codes({'a.py':b"x='WRITER_OBSERVATION_CHANGED'; y='private arbitrary'"})
        self.assertEqual(d.error_info(ValueError('WRITER_OBSERVATION_CHANGED'),codes)['failure_code'],'WRITER_OBSERVATION_CHANGED')
        self.assertNotIn('SECRET_ERROR',json.dumps(d.error_info(ValueError('SECRET_ERROR'),codes)))
    def test_errno_only(self):self.assertEqual(d.error_info(OSError(13,'SECRET_PATH'),d.LOCAL_CODES)['errno'],13)


class BoundaryTests(unittest.TestCase):
    def test_cleanup_causes(self):
        for code in d.CLEANUP:
            primary=KeyboardInterrupt();primary.__cause__=ValueError(code)
            result=d.error_info(primary,d.LOCAL_CODES);self.assertEqual(result['failure_code'],'INTERRUPTED');self.assertTrue(result['cleanup_unknown'])
    def test_cycle_bounded(self):
        error=ValueError('fixture');error.__cause__=error;self.assertFalse(d.error_info(error,d.LOCAL_CODES)['cleanup_unknown'])
    def test_real_alarm_recurs_through_unwind(self):
        count=[]
        with self.assertRaises(d.Deadline):
            with d.bounded(.02):
                try:time.sleep(.1)
                except d.Deadline:count.append(1);time.sleep(1.1)
        self.assertEqual(count,[1]);self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
    def test_existing_alarm_refused(self):
        with mock.patch.object(d.signal,'getitimer',return_value=(1.,0.)),mock.patch.object(d.signal,'signal') as setter:
            with self.assertRaises(ValueError):
                with d.bounded():pass
            setter.assert_not_called()
    def test_timer_cleanup_without_primary(self):
        real=d.signal.setitimer
        def setter(kind,value,*args):
            if value==0:raise OSError(5,'SECRET_TIMER')
            return real(kind,value,*args)
        try:
            with mock.patch.object(d.signal,'setitimer',side_effect=setter):
                with self.assertRaises(ValueError) as got:
                    with d.bounded(.1):pass
            self.assertTrue(got.exception.diagnostic_cleanup_failed)
        finally:real(signal.ITIMER_REAL,0)
    def test_timer_cleanup_preserves_primary(self):
        error=KeyboardInterrupt();real=d.signal.setitimer
        def setter(kind,value,*args):
            if value==0:raise OSError(5,'SECRET_TIMER')
            return real(kind,value,*args)
        try:
            with mock.patch.object(d.signal,'setitimer',side_effect=setter):
                with self.assertRaises(KeyboardInterrupt) as got:
                    with d.bounded(.1):raise error
            self.assertIs(got.exception,error);self.assertTrue(error.diagnostic_cleanup_failed)
        finally:real(signal.ITIMER_REAL,0)
    def test_holds_and_tail_boundary_preserved(self):
        result=d.new_result();result['final_authentication']='VERIFIED'
        text,code=d.finish(result,capture_pair(),{'units':('test.service',),'masks':('/etc/systemd/system/test.service',)},ValueError('WRITER_OBSERVATION_CHANGED'),d.LOCAL_CODES)
        value=json.loads(text);self.assertEqual(code,2);self.assertEqual(value['tail_checks'],'NOT_REACHED_AFTER_WRITER_MISMATCH');self.assertFalse(value['success']);self.assertEqual(value['install_admission'],'NOT_GRANTED')
    def test_final_auth_failure_nonzero(self):
        result=d.new_result();result['final_authentication']='FAILED';result['final_authentication_failure']=d.error_info(ValueError('secret'),d.LOCAL_CODES)
        text,code=d.finish(result,d.Capture(),{},None,d.LOCAL_CODES);self.assertEqual(code,2);self.assertFalse(json.loads(text)['success'])
    def test_pair_retained_after_cleanup(self):
        result=d.new_result();result['final_authentication']='VERIFIED';error=KeyboardInterrupt();error.__cause__=ValueError('EXISTING_LOCKS_CLEANUP_UNKNOWN')
        text,code=d.finish(result,capture_pair(),{'units':('test.service',),'masks':('/etc/systemd/system/test.service',)},error,d.LOCAL_CODES)
        value=json.loads(text);self.assertEqual(code,2);self.assertTrue(value['cleanup_unknown']);self.assertEqual(value['writer_pair']['successful_validated_samples'],2)
    def test_output_bound_nonzero(self):
        result=d.new_result();result['SECRET_EXTRA']='x'*70000
        text,code=d.finish(result,d.Capture(),{},None,d.LOCAL_CODES);self.assertEqual(code,2);self.assertLess(len(text),1000);self.assertEqual(json.loads(text)['failure_code'],'OUTPUT_BOUND_OR_ENCODING')
    def test_reviewed_reader_functions_unchanged(self):
        pins={'authority': 'adc3c9da1d9a701b83f214764f98e0e4c5147801c421043041043e2835281945', 'entry_bytes': '386063c00971dd920fe39318646c690915d408424d4662a15808dba3e606d033', 'read_pair': 'b679e36f76a4ee214e3c55f73be5ba139b08b1134f5c1d67c3f6504c769486ae', 'stamp': 'f39ae51cd6b276074adb26e8af523362dda82b46f74c70d4056e3070dc2ca669'}
        raw=pathlib.Path(d.__file__).read_text();new=ast.parse(raw)
        for name,expected in pins.items():
            n=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name==name)
            end=max(x.lineno for x in ast.walk(n) if hasattr(x,'lineno'))
            self.assertEqual(d.sha(''.join(raw.splitlines(True)[n.lineno-1:end]).encode()),expected)


class FrozenCollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ex=types.ModuleType('frozen_extract');path=ROOT/'extract_epoch7_kit.py'
        if not path.exists():path=ROOT/'recovery-kit-source/tools/extract_epoch7_kit.py'
        ex.__file__=str(path);raw=path.read_bytes()
        assert d.sha(raw)=='a5c283dfa297983617d5fca20c8453cd4766d765ba53ec9326e6c5645493202c'
        exec(compile(raw,ex.__file__,'exec'),ex.__dict__)
        archive_path=ROOT/'build-9c40fc81-python312-a/epoch7-recovery-kit.tar.gz'
        if not archive_path.exists():archive_path=ROOT/'artifacts/epoch7-kit-9c40fc81.tar.gz'
        archive=archive_path.read_bytes()
        files,unused=ex.inspect_archive(archive,'e0fbc766d53a961f180a9ddfcdd1a40bdc6f8d809236f1b9bfb9cf4d3a929776',d.ENTRY_SHA,d.MANIFEST_SHA)
        assert len(files)==250
        entry=types.ModuleType('frozen_entry');entry.__file__='/cache-only/epoch7_recovery_entry.py'
        exec(compile(files['epoch7_recovery_entry.py'],entry.__file__,'exec'),entry.__dict__)
        manifest=entry.validate_manifest(entry.decode(files[entry.MANIFEST]));cache={k:v for k,v in files.items() if k!=entry.MANIFEST};entry.validate_runtime(manifest,cache)
        cls.kit=entry.VerifiedKit('/cache-only',manifest,cache,d.MANIFEST_SHA,raw_manifest=files[entry.MANIFEST])
    def actual(self,change=None,invalid=False,tail=False):
        with self.kit.imports({'test_snapshot':'tests/snapshot/test_snapshot.py'}):
            import epoch7_snapshot as core
            import test_snapshot as fixtures
            policy,original=fixtures.fixture();capture=d.Capture()
            class Base(fixtures.FakeIO):
                def writers(self,p,paths):
                    value=super(Base,self).writers(p,paths)
                    if invalid:return {}
                    if change is not None and capture.calls==2:
                        if change=='fd_count':value['processes'][change]+=1
                        else:value['processes'][change]='0'*64
                    return value
            wrapped=d.recording_io(Base,core.validate_writers,capture)();wrapped.__dict__.update(original.__dict__)
            if tail:
                read=wrapped.read
                def reread(name,maximum=16777216):
                    raw,meta=read(name,maximum)
                    if name==core.ACTIVE and wrapped.calls[name]>1:meta['ino']+=1
                    return raw,meta
                wrapped.read=reread
            primary=None
            with fixtures.native_pin_context(fixtures.native_raws(wrapped)):
                try:core.collect(policy,wrapped)
                except Exception as error:primary=error
            result=d.project(capture,tuple(sorted(core.WRITER_UNITS)),tuple(sorted(core.LEGACY_MASKS)))
            return primary,result,wrapped,capture
    def test_actual_r5_typed_comparison_and_projection_agree(self):
        with self.kit.imports({'test_snapshot':'tests/snapshot/test_snapshot.py'}):
            import epoch7_snapshot as core
            import test_snapshot as fixtures
            policy,backend=fixtures.fixture();before=backend.writers(policy,[]);after=copy.deepcopy(before)
            before['manager']['fixture']=True;after['manager']['fixture']=1
            capture=d.Capture();capture.call(lambda:before,core.validate_writers);capture.call(lambda:after,core.validate_writers)
            with self.assertRaisesRegex(ValueError,'WRITER_OBSERVATION_CHANGED'):core.validate_writer_transition(before,after)
            value=d.project(capture,tuple(sorted(core.WRITER_UNITS)),tuple(sorted(core.LEGACY_MASKS)))
            self.assertFalse(value['exact_pair_equal']);self.assertEqual(value['changed_sections'],['manager']);self.assertTrue(value['sections']['manager']['unlisted_fields']['changed'])
    def test_real_frozen_collector_equal(self):
        error,result,unused,capture=self.actual();self.assertIsNone(error);self.assertEqual(capture.calls,2);self.assertTrue(result['exact_pair_equal'])
    def test_real_original_mismatch_still_raises(self):
        error,result,wrapped,capture=self.actual(change='process_identity_sha256');self.assertEqual(str(error),'WRITER_OBSERVATION_CHANGED');self.assertEqual(result['changed_sections'],['processes']);self.assertEqual(capture.calls,2)
    def test_r5_original_count_only_drift_is_telemetry(self):
        error,result,wrapped,capture=self.actual(change='fd_count');self.assertIsNone(error);self.assertFalse(result['exact_pair_equal']);self.assertEqual(capture.calls,2)
    def test_real_invalid_row_stops_first(self):
        error,result,wrapped,capture=self.actual(invalid=True);self.assertEqual(str(error),'WRITER_EVIDENCE_KEYS');self.assertEqual(capture.calls,1);self.assertEqual(capture.samples,[])
    def test_real_tail_failure_after_equal_pair(self):
        error,result,wrapped,capture=self.actual(tail=True);self.assertEqual(str(error),'RETAINED_FILE_RACE');self.assertTrue(result['exact_pair_equal']);self.assertEqual(capture.calls,2)


    def observe_without_prepasses(self,changed=False):
        with self.kit.imports({'test_snapshot':'tests/snapshot/test_snapshot.py'}):
            import epoch7_snapshot as core
            import observe_epoch7 as observer
            import test_snapshot as fixtures
            case=fixtures.ObservationTests('test_missing_hashes_are_measured_in_one_observation');case.setUp()
            try:
                capture=d.Capture()
                class Base(fixtures.FakeIO):
                    def writers(self,p,paths):
                        value=super(Base,self).writers(p,paths)
                        if changed and capture.calls==2:value['processes']['process_identity_sha256']='0'*64
                        return value
                wrapped=d.recording_io(Base,core.validate_writers,capture)();wrapped.__dict__.update(case.f.__dict__)
                primary=None;value=None
                try:value=observer.observe_with_io(wrapped)
                except Exception as error:primary=error
                return primary,value,capture
            finally:case.tearDown()
    def test_real_measured_policy_and_collect_without_prepasses(self):
        error,value,capture=self.observe_without_prepasses();self.assertIsNone(error);self.assertEqual(value['kind'],'EPOCH7_OBSERVATION_ONLY_UNREVIEWED');self.assertEqual(value['install_admission'],'NOT_GRANTED');self.assertEqual(capture.calls,2)
    def test_real_whole_observer_preserves_mismatch_without_prepasses(self):
        error,value,capture=self.observe_without_prepasses(True);self.assertEqual(str(error),'WRITER_OBSERVATION_CHANGED');self.assertIsNone(value);self.assertEqual(capture.calls,2)


class OrchestrationTests(unittest.TestCase):
    def invoke(self,run=None,final_error=None,bound_error=None):
        entry=types.ModuleType('fixture_entry');kit=types.SimpleNamespace(cache={'x.py':b"'WRITER_OBSERVATION_CHANGED'"})
        entry.verify_kit=mock.Mock(side_effect=[kit,final_error] if final_error is not None else [kit,kit])
        stages=[]
        @contextlib.contextmanager
        def timer(seconds=600):
            stages.append(seconds)
            yield
            if bound_error is not None and seconds==10:raise bound_error
        output=io.StringIO()
        def success(entry,kit,result,capture,scope):result['collector_started']=result['collector_returned']=True
        with mock.patch.object(d.os,'geteuid',return_value=0),mock.patch.object(d.os,'getegid',return_value=0),mock.patch.object(d.socket,'gethostname',return_value=d.HOST),mock.patch.object(d,'bounded',side_effect=timer),mock.patch.object(d,'entry_bytes',return_value=b'pass'),mock.patch.object(d.types,'ModuleType',return_value=entry),mock.patch.object(d,'read_pair',return_value=({'kind':'EPOCH7_OBSERVATION_ONLY_HOLD','failure_code':'WRITER_OBSERVATION_CHANGED'},{})),mock.patch.object(d,'run',side_effect=run or success) as called,mock.patch.object(d.sys,'stdout',output):
            status=d.main()
        return status,json.loads(output.getvalue()),stages,called,entry
    def test_once_and_separate_bounds(self):
        status,value,stages,called,entry=self.invoke();self.assertEqual(status,0);called.assert_called_once();self.assertEqual(stages,[600,60,10]);self.assertEqual(entry.verify_kit.call_count,2);self.assertEqual(value['collector_attempts'],1)
    def test_mismatch_remains_nonzero(self):
        def fail(*args):raise ValueError('WRITER_OBSERVATION_CHANGED')
        status,value,*unused=self.invoke(run=fail);self.assertEqual(status,2);self.assertEqual(value['primary_failure']['failure_code'],'WRITER_OBSERVATION_CHANGED');self.assertEqual(value['tail_checks'],'NOT_REACHED_AFTER_WRITER_MISMATCH')
    def test_primary_interrupt_not_replaced_by_reverify(self):
        def fail(*args):raise KeyboardInterrupt()
        status,value,*unused=self.invoke(run=fail,final_error=ValueError('SECRET_HASH_FAILURE'));self.assertEqual(status,2);self.assertEqual(value['primary_failure']['failure_code'],'INTERRUPTED');self.assertEqual(value['final_authentication'],'FAILED');self.assertNotIn('SECRET_HASH_FAILURE',json.dumps(value))
    def test_capture_survives_post_return_cleanup(self):
        def fail(entry,kit,result,capture,scope):
            for sample in (row(),row()):capture.call(lambda:sample,lambda x:None)
            scope.update(units=('test.service',),masks=('/etc/systemd/system/test.service',));result['collector_returned']=True
            error=ValueError('original');error.__cause__=ValueError('EXISTING_LOCKS_CLEANUP_UNKNOWN');raise error
        status,value,*unused=self.invoke(run=fail);self.assertEqual(status,2);self.assertEqual(value['writer_pair']['successful_validated_samples'],2);self.assertTrue(value['cleanup_unknown']);self.assertFalse(value['diagnostic_complete'])
    def test_finalization_deadline_is_structured(self):
        status,value,*unused=self.invoke(bound_error=d.Deadline());self.assertEqual(status,2);self.assertEqual(value['failure_code'],'OUTPUT_FINALIZATION_FAILED');self.assertEqual(value['output_failure']['failure_code'],'DIAGNOSTIC_DEADLINE')
    def test_finalization_cleanup_flag(self):
        error=ValueError('timer cleanup');error.diagnostic_cleanup_failed=True
        status,value,*unused=self.invoke(bound_error=error);self.assertEqual(status,2);self.assertTrue(value['cleanup_unknown']);self.assertEqual(value['failure_code'],'OUTPUT_FINALIZATION_FAILED')
    def test_finalization_preserves_primary(self):
        def fail(*args):raise KeyboardInterrupt()
        status,value,*unused=self.invoke(run=fail,bound_error=d.Deadline());self.assertEqual(value['primary_failure']['failure_code'],'INTERRUPTED')
    def test_output_deadline_preserves_prior_final_cleanup_unknown(self):
        error=ValueError('cleanup');error.diagnostic_cleanup_failed=True
        status,value,*unused=self.invoke(final_error=error,bound_error=d.Deadline())
        self.assertEqual(status,2);self.assertTrue(value['cleanup_unknown']);self.assertEqual(value['final_authentication'],'FAILED');self.assertTrue(value['final_authentication_failure']['cleanup_unknown'])
    def test_reverify_failure_after_success_is_not_success(self):
        status,value,*unused=self.invoke(final_error=OSError(5,'private'));self.assertEqual(status,2);self.assertFalse(value['success']);self.assertEqual(value['final_authentication_failure']['errno'],5)


class FixedSeamTests(unittest.TestCase):
    def test_two_existing_locks_and_one_original_call(self):
        calls=[];capture=d.Capture();result=d.new_result();locks=object()
        reader=types.SimpleNamespace(pins={},read=lambda name:(b'',dict(uid=0,gid=0,mode=384 if name=='install' else 420,sha256='a'*64)))
        class Base:
            def __init__(self,pins,given):calls.append(('init',pins,given))
            def _process_scan(self,paths):return {}
            def writers(self,p,paths):return row()
        observer=types.SimpleNamespace(ObservationReader=mock.Mock(return_value=reader),ObservationIO=Base,observe_with_io=mock.Mock(return_value={'policy_sha256':'a'*64,'snapshot_sha256':'b'*64,'evidence_sha256':'c'*64}))
        @contextlib.contextmanager
        def held(r,p):calls.append(('locks',r,p));yield locks;calls.append(('closed',))
        concrete=types.SimpleNamespace(existing_locks=held);core=types.SimpleNamespace(INSTALL_LOCK='install',ACTIVATION_LOCK='activation',need=lambda x,c:d.need(x),validate_writers=lambda x:x,d=types.SimpleNamespace(digest=d.digest))
        d.collect_once(observer,concrete,core,capture,result)
        observer.observe_with_io.assert_called_once();self.assertEqual([x[0] for x in calls],['locks','init','closed']);self.assertTrue(result['collector_returned'])
        self.assertEqual(set(calls[0][2]['files']),{'install','activation'})
    def test_no_other_effect_entrypoints(self):
        tree=ast.parse(pathlib.Path(d.__file__).read_text());attrs={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
        self.assertFalse(attrs & {'observe_host','observe','persist_private','narrow','chmod','fchmod','resume_once','execute_reviewed_probe','apply_reviewed_prerequisites'})

def proc_stat(pid,start,kernel=False):
    fields=[b'S']+[b'0']*19;fields[6]=str(0x00200000 if kernel else 0).encode();fields[19]=str(start).encode()
    return str(pid).encode()+b' (SECRET_STAT_COMM) '+b' '.join(fields)+b'\n'

class SyntheticScan(object):
    def __init__(self,rows=None):
        self.rows=rows or {'10':{'starttime':100,'uids':[0]*4,'fd_count':3,'kernel':False,'comm':b'systemd\n'}}
        self.error=None;self.bad_digest=False;self.bad_count=False;self.extra_stat=False;self.indirect=False;self.foreign=None
    def _process_scan(self,paths):
        result={};fd_count=0
        for pid,row in sorted(self.rows.items()):
            counts={}
            def procfile(name,limit):
                counts[name]=counts.get(name,0)+1
                if name=='stat':return row.get('stat'+str(counts[name]),proc_stat(int(pid),row['starttime'],row['kernel']))
                if name=='comm':return row['comm']
                return b'SECRET_UNCAPTURED_ARGUMENT'
            procfile('stat',65536);procfile('comm',256);procfile('cmdline',65536)
            if self.indirect:
                def ssh_indirect():return procfile('stat',65536)
                ssh_indirect()
            if self.foreign:self.foreign._process_scan(paths)
            fd_names=['SECRET_FD_NAME']*row['fd_count'];fd_count+=len(fd_names)
            procfile('stat',65536)
            if self.extra_stat:procfile('stat',65536)
            result[pid]={'starttime':row['starttime'],'uids':row['uids'][:]}
        self.last_result=result
        if self.error is not None:raise self.error
        return {'process_identity_sha256':'0'*64 if self.bad_digest else d.digest(result),
            'fd_count':fd_count+(1 if self.bad_count else 0),'background_processes':[],'background_processes_sha256':d.digest([])}

class ProcessCaptureTests(unittest.TestCase):
    def call(self,scan=None,capture=None,owner=None):
        scan=scan or SyntheticScan();capture=capture or d.ProcessCapture()
        value=capture.call(scan if owner is None else owner,SyntheticScan._process_scan.__code__,lambda:scan._process_scan([]),d.digest)
        return capture,value,scan
    def test_exact_same_call_return_and_details(self):
        capture,value,scan=self.call();r=capture.records[0]
        self.assertEqual(r['state'],'CAPTURED_FROM_ORIGINAL_RETURN');self.assertEqual(r['details_state'],'EXACT_ORIGINAL_STAT_COMM_FD_BOUND')
        self.assertEqual(r['fd_count'],3);self.assertFalse(r['details']['10']['kernel_thread']);self.assertEqual(r['details']['10']['comm_label'],'SYSTEMD_COMM');self.assertEqual(r['details']['10']['fd_count'],3)
        self.assertIsNone(sys.getprofile());self.assertIsNone(sys.gettrace())
    def test_original_object_identity(self):
        scan=SyntheticScan();returned=[]
        def operation():value=scan._process_scan([]);returned.append(value);return value
        value=d.ProcessCapture().call(scan,SyntheticScan._process_scan.__code__,operation,d.digest);self.assertIs(value,returned[0])
    def test_no_mutable_map_escape(self):
        capture,value,scan=self.call();scan.last_result['10']['uids'][0]=999;self.assertEqual(capture.records[0]['sample']['10']['uids'],[0]*4)
    def test_zero_boot_tick_starttime_remains_numeric_telemetry(self):
        scan=SyntheticScan();scan.rows['10']['starttime']=0;scan.rows['10']['kernel']=True
        capture,unused,unused=self.call(scan);self.assertEqual(capture.records[0]['details_state'],'EXACT_ORIGINAL_STAT_COMM_FD_BOUND');self.assertEqual(capture.records[0]['sample']['10']['starttime'],0)
    def test_hook_exception_preserves_primary_and_clears_profile(self):
        actual=sys.setprofile;error=RuntimeError('PRIVATE_HOOK_FAILURE')
        def install(hook):
            if hook is None:return actual(None)
            def broken(frame,event,value):
                hook(frame,event,value)
                if event=='return' and frame.f_code is SyntheticScan._process_scan.__code__:raise error
            return actual(broken)
        with mock.patch.object(d.sys,'setprofile',side_effect=install):
            with self.assertRaises(RuntimeError) as got:self.call()
        self.assertIs(got.exception,error);self.assertIsNone(sys.getprofile())
    def test_kernel_flags_from_both_original_stats(self):
        scan=SyntheticScan();scan.rows['10']['kernel']=True
        capture,unused,unused=self.call(scan);self.assertTrue(capture.records[0]['details']['10']['kernel_thread'])
    def test_indirect_ssh_stat_is_ignored(self):
        scan=SyntheticScan();scan.indirect=True
        capture,unused,unused=self.call(scan);self.assertEqual(capture.records[0]['details_state'],'EXACT_ORIGINAL_STAT_COMM_FD_BOUND')
    def test_same_code_other_self_is_ignored(self):
        scan=SyntheticScan();scan.foreign=SyntheticScan()
        capture,unused,unused=self.call(scan);self.assertEqual(capture.records[0]['details_state'],'EXACT_ORIGINAL_STAT_COMM_FD_BOUND')
    def test_wrong_self_cannot_supply_capture(self):
        capture,unused,unused=self.call(owner=object());self.assertEqual(capture.records[0]['state'],'UNKNOWN');self.assertEqual(capture.records[0]['reason'],'PROCESS_CAPTURE_RETURN_BINDING')
    def test_missing_scan_return_is_unknown(self):
        scan=SyntheticScan();c=d.ProcessCapture();v={'fd_count':0}
        self.assertIs(c.call(scan,SyntheticScan._process_scan.__code__,lambda:v,d.digest),v);self.assertEqual(c.records[0]['state'],'UNKNOWN')
    def test_duplicate_scan_returns_are_unknown(self):
        scan=SyntheticScan();c=d.ProcessCapture()
        def operation():scan._process_scan([]);return scan._process_scan([])
        c.call(scan,SyntheticScan._process_scan.__code__,operation,d.digest);self.assertEqual(c.records[0]['reason'],'PROCESS_CAPTURE_RETURN_BINDING')
    def test_digest_mismatch_never_attributes(self):
        scan=SyntheticScan();scan.bad_digest=True;c,unused,unused=self.call(scan);self.assertEqual(c.records[0]['state'],'UNKNOWN');self.assertEqual(c.records[0]['reason'],'PROCESS_CAPTURE_DIGEST_BINDING')
    def test_total_fd_mismatch_never_attributes(self):
        scan=SyntheticScan();scan.bad_count=True;c,unused,unused=self.call(scan);self.assertEqual(c.records[0]['reason'],'PROCESS_CAPTURE_FD_BINDING')
    def test_changed_starttime_is_unknown_detail(self):
        scan=SyntheticScan();scan.rows['10']['stat2']=proc_stat(10,101);c,unused,unused=self.call(scan);self.assertEqual(c.records[0]['details_state'],'UNKNOWN');self.assertEqual(c.records[0]['details_reason'],'PROCESS_CAPTURE_STAT_BINDING')
    def test_changed_kernel_flag_is_unknown_detail(self):
        scan=SyntheticScan();scan.rows['10']['stat2']=proc_stat(10,100,True);c,unused,unused=self.call(scan);self.assertEqual(c.records[0]['details_reason'],'PROCESS_CAPTURE_STAT_BINDING')
    def test_wrong_stat_pid_is_unknown_detail(self):
        scan=SyntheticScan();scan.rows['10']['stat2']=proc_stat(11,100);c,unused,unused=self.call(scan);self.assertEqual(c.records[0]['details_state'],'UNKNOWN')
    def test_duplicate_stat_is_unknown_detail(self):
        scan=SyntheticScan();scan.extra_stat=True;c,unused,unused=self.call(scan);self.assertEqual(c.records[0]['details_reason'],'PROCESS_CAPTURE_DETAIL_SCHEMA')
    def test_raw_detail_aggregate_cap(self):
        with mock.patch.object(d,'MAX_PROC_CAPTURE',1):c,unused,unused=self.call()
        self.assertEqual(c.records[0]['details_reason'],'PROCESS_CAPTURE_DETAIL_BOUND')
    def test_map_size_cap(self):
        with mock.patch.object(d,'MAX_CENSUS',1):c,unused,unused=self.call()
        self.assertEqual(c.records[0]['state'],'UNKNOWN')
    def test_oversize_comm_is_unknown_without_raw_output(self):
        scan=SyntheticScan();scan.rows['10']['comm']=b'SECRET'*100;c,unused,unused=self.call(scan);self.assertEqual(c.records[0]['details_state'],'UNKNOWN');self.assertNotIn('SECRET',json.dumps(c.records))
    def test_unknown_comm_hash_only_and_no_executable_trust(self):
        scan=SyntheticScan();scan.rows['10']['comm']=b'SECRET_COMM\n';c,unused,unused=self.call(scan);r=c.records[0]['details']['10'];self.assertEqual(r['comm_label'],'UNLISTED_COMM_HASH_ONLY');self.assertEqual(r['comm_sha256'],d.sha(b'SECRET_COMM'));self.assertNotIn('SECRET',json.dumps(c.records))
    def test_prior_profile_refused_without_call(self):
        op=mock.Mock()
        with mock.patch.object(d.sys,'getprofile',return_value=object()):
            with self.assertRaisesRegex(ValueError,'PROCESS_CAPTURE_PROFILE_PRESENT'):d.ProcessCapture().call(object(),SyntheticScan._process_scan.__code__,op,d.digest)
        op.assert_not_called()
    def test_prior_trace_refused_without_call(self):
        op=mock.Mock()
        with mock.patch.object(d.sys,'gettrace',return_value=object()):
            with self.assertRaisesRegex(ValueError,'PROCESS_CAPTURE_PROFILE_PRESENT'):d.ProcessCapture().call(object(),SyntheticScan._process_scan.__code__,op,d.digest)
        op.assert_not_called()
    def test_max_two_attempts_checked_before_scan(self):
        c=d.ProcessCapture();self.call(capture=c);self.call(capture=c);op=mock.Mock()
        with self.assertRaisesRegex(ValueError,'PROCESS_CAPTURE_CALL_BOUND'):c.call(object(),SyntheticScan._process_scan.__code__,op,d.digest)
        op.assert_not_called()
    def test_original_nested_exception_preserved_profile_restored(self):
        scan=SyntheticScan();error=ValueError('PRIVATE_FAILURE');scan.error=error
        with self.assertRaises(ValueError) as got:self.call(scan)
        self.assertIs(got.exception,error);self.assertIsNone(sys.getprofile())
    def test_interruption_preserved_profile_restored(self):
        scan=SyntheticScan();error=d.Deadline();scan.error=error
        with self.assertRaises(d.Deadline) as got:self.call(scan)
        self.assertIs(got.exception,error);self.assertIsNone(sys.getprofile())
    def test_profile_cleanup_failure_is_fatal(self):
        actual=sys.setprofile
        def set_profile(value):
            if value is None:raise OSError('PRIVATE_CLEANUP')
            actual(value)
        try:
            with mock.patch.object(d.sys,'setprofile',side_effect=set_profile):
                with self.assertRaisesRegex(ValueError,'PROCESS_CAPTURE_PROFILE_CLEANUP_UNKNOWN') as got:self.call()
            self.assertTrue(got.exception.diagnostic_cleanup_failed)
        finally:actual(None)
    def test_cleanup_failure_preserves_primary(self):
        actual=sys.setprofile;scan=SyntheticScan();error=KeyboardInterrupt();scan.error=error
        def set_profile(value):
            if value is None:raise OSError('PRIVATE_CLEANUP')
            actual(value)
        try:
            with mock.patch.object(d.sys,'setprofile',side_effect=set_profile):
                with self.assertRaises(KeyboardInterrupt) as got:self.call(scan)
            self.assertIs(got.exception,error);self.assertTrue(error.diagnostic_cleanup_failed)
        finally:actual(None)
    def test_profile_replacement_refused_and_cleared(self):
        scan=SyntheticScan();c=d.ProcessCapture()
        def operation():value=scan._process_scan([]);sys.setprofile(None);return value
        with self.assertRaisesRegex(ValueError,'PROCESS_CAPTURE_PROFILE_CHANGED'):c.call(scan,SyntheticScan._process_scan.__code__,operation,d.digest)
        self.assertIsNone(sys.getprofile())
    def test_no_frame_or_raw_bytes_retained(self):
        c,unused,unused=self.call()
        def check(value):
            self.assertNotIsInstance(value,(types.FrameType,bytes))
            if isinstance(value,dict):
                for k,v in value.items():check(k);check(v)
            elif isinstance(value,list):
                for v in value:check(v)
        check(c.records)
    def test_added_removed_changed_rows_bind_original_writer_samples(self):
        c=d.Capture();one=SyntheticScan();two=SyntheticScan({'11':dict(starttime=101,uids=[0]*4,fd_count=1,kernel=True,comm=b'kworker/SECRET\n')})
        for scan in (one,two):
            unused,processes,unused=self.call(scan,c.processes);value=row();value['processes']=processes;c.call(lambda:value,lambda v:None)
        result=d.project_process_capture(c);self.assertEqual(result['state'],'EXACT_ORIGINAL_SAMPLES_BOUND');self.assertEqual(result['added_count'],1);self.assertEqual(result['removed_count'],1);self.assertEqual(result['class_metadata_state'],'EXACT_ORIGINAL_SAMPLES_BOUND');self.assertNotIn('SECRET',json.dumps(result))
        self.assertTrue(result['changed_pid_rows'][1]['after']['class_metadata']['kernel_thread']);self.assertEqual(result['security_classification'],'NOT_GRANTED')
    def test_writer_sample_mismatch_prevents_attribution(self):
        c=d.Capture()
        for unused in range(2):
            pc,processes,unused=self.call(capture=c.processes);value=row();value['processes']=processes;c.call(lambda:value,lambda v:None)
        c.samples[1]['processes']['fd_count']+=1;self.assertEqual(d.project_process_capture(c)['state'],'UNKNOWN_WRITER_SAMPLE_BINDING')
    def test_worst_case_changed_rows_bounded_and_truncated(self):
        c=d.Capture()
        for step in (0,1):
            rows={str(pid):dict(starttime=2**64-2+step,uids=[2**32-1]*4,fd_count=999,kernel=bool(step),comm=b'UNKNOWN_SECRET') for pid in range(100,170)}
            pc,processes,unused=self.call(SyntheticScan(rows),c.processes);value=row();value['processes']=processes;c.call(lambda:value,lambda v:None)
        output=project(c);self.assertEqual(len(output['process_attribution']['changed_pid_rows']),64);self.assertEqual(output['process_attribution']['omitted_changed_pid_count'],6);self.assertTrue(output['process_attribution']['truncated']);self.assertLess(len(d.canonical(output,d.MAX_OUTPUT)),d.MAX_OUTPUT);self.assertNotIn('UNKNOWN_SECRET',json.dumps(output))

class ActualFrozenProcessCaptureTests(FrozenCollectorTests):
    # Inherit the exact authenticated archive fixture but execute only new tests.
    test_actual_r5_typed_comparison_and_projection_agree=None
    test_real_frozen_collector_equal=None
    test_real_original_mismatch_still_raises=None
    test_real_invalid_row_stops_first=None
    test_real_tail_failure_after_equal_pair=None
    test_real_measured_policy_and_collect_without_prepasses=None
    test_real_whole_observer_preserves_mismatch_without_prepasses=None
    test_r5_original_count_only_drift_is_telemetry=None
    def test_full_frozen_writer_scope_worst_case_output_bound(self):
        with self.kit.imports({'test_snapshot':'tests/snapshot/test_snapshot.py'}):
            import epoch7_snapshot as core
            import test_snapshot as fixtures
            policy,backend=fixtures.fixture();capture=d.Capture()
            for step in (0,1):
                rows={str(pid):dict(starttime=2**64-2+step,uids=[2**32-1]*4,fd_count=999,kernel=bool(step),comm=b'UNKNOWN_SECRET') for pid in range(100,170)}
                scan=SyntheticScan(rows);processes=capture.processes.call(scan,SyntheticScan._process_scan.__code__,lambda:scan._process_scan([]),core.d.digest)
                value=backend.writers(policy,[]);value['processes']=processes;capture.call(lambda:value,core.validate_writers)
            result=d.project(capture,tuple(sorted(core.WRITER_UNITS)),tuple(sorted(core.LEGACY_MASKS)))
            self.assertEqual(len(result['sections']['units']['rows']),19);self.assertTrue(result['process_attribution']['truncated']);self.assertLess(len(d.canonical(result,d.MAX_OUTPUT)),d.MAX_OUTPUT)
    def test_actual_frozen_process_scan_with_no_extra_proc_reads(self):
        with self.kit.imports():
            import snapshot_io as concrete
            import epoch7_snapshot as core
            scan=object.__new__(concrete.LocalReadOnlyIO);capture=d.ProcessCapture();reads=[]
            statraw=proc_stat(10,100,True)
            def opened(path,mode):
                reads.append(path);name=path.rsplit('/',1)[-1]
                return io.BytesIO({'stat':statraw,'status':b'Uid:\t0\t0\t0\t0\n','comm':b'UNKNOWN_KERNEL_SECRET\n'}[name])
            def listed(path):return ['10'] if path=='/proc' else ['0','1']
            with mock.patch('builtins.open',side_effect=opened),mock.patch.object(concrete.os,'listdir',side_effect=listed),mock.patch.object(concrete.os,'getpid',return_value=999),mock.patch.object(concrete.os,'stat',return_value=types.SimpleNamespace(st_dev=1,st_ino=2)):
                value=capture.call(scan,concrete.LocalReadOnlyIO._process_scan.__code__,lambda:scan._process_scan([]),core.d.digest)
            self.assertEqual(reads,['/proc/10/stat','/proc/10/status','/proc/10/comm','/proc/10/status','/proc/10/stat'])
            self.assertEqual(value['fd_count'],2);record=capture.records[0];self.assertEqual(record['details_state'],'EXACT_ORIGINAL_STAT_COMM_FD_BOUND');self.assertTrue(record['details']['10']['kernel_thread']);self.assertNotIn('SECRET',json.dumps(record))


if __name__=='__main__':unittest.main()

