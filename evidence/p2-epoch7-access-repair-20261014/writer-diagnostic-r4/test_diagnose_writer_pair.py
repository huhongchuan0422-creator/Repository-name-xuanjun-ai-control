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
        pins={'authority': 'adc3c9da1d9a701b83f214764f98e0e4c5147801c421043041043e2835281945', 'entry_bytes': '386063c00971dd920fe39318646c690915d408424d4662a15808dba3e606d033', 'read_pair': '75acf8690233c96bf7a825f34c7f44131eb0ad920b0938aeaa801410c0f3fbbc', 'stamp': 'f39ae51cd6b276074adb26e8af523362dda82b46f74c70d4056e3070dc2ca669'}
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
        assert d.sha(raw)=='486400644780ecef13fb65956f4a834518cdb155e705c2ccd2fe59e218e80bb7'
        exec(compile(raw,ex.__file__,'exec'),ex.__dict__)
        archive_path=ROOT/'build-c86a4d64-python312-a/epoch7-recovery-kit.tar.gz'
        if not archive_path.exists():archive_path=ROOT/'artifacts/epoch7-kit-c86a4d64.tar.gz'
        archive=archive_path.read_bytes()
        files,unused=ex.inspect_archive(archive,'2b1885a9b1cec024abf657a82c790d420f1e5b4fe8ce1776d9cba4616b4b97b9',d.ENTRY_SHA,d.MANIFEST_SHA)
        assert len(files)==249
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
                    if change is not None and capture.calls==2:value['processes'][change]+=1
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
    def test_real_frozen_collector_equal(self):
        error,result,unused,capture=self.actual();self.assertIsNone(error);self.assertEqual(capture.calls,2);self.assertTrue(result['exact_pair_equal'])
    def test_real_original_mismatch_still_raises(self):
        error,result,wrapped,capture=self.actual(change='fd_count');self.assertEqual(str(error),'WRITER_OBSERVATION_CHANGED');self.assertEqual(result['changed_sections'],['processes']);self.assertEqual(capture.calls,2)
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
                        if changed and capture.calls==2:value['processes']['fd_count']+=1
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
            def writers(self,p,paths):return row()
        observer=types.SimpleNamespace(ObservationReader=mock.Mock(return_value=reader),ObservationIO=Base,observe_with_io=mock.Mock(return_value={'policy_sha256':'a'*64,'snapshot_sha256':'b'*64,'evidence_sha256':'c'*64}))
        @contextlib.contextmanager
        def held(r,p):calls.append(('locks',r,p));yield locks;calls.append(('closed',))
        concrete=types.SimpleNamespace(existing_locks=held);core=types.SimpleNamespace(INSTALL_LOCK='install',ACTIVATION_LOCK='activation',need=lambda x,c:d.need(x),validate_writers=lambda x:x)
        d.collect_once(observer,concrete,core,capture,result)
        observer.observe_with_io.assert_called_once();self.assertEqual([x[0] for x in calls],['locks','init','closed']);self.assertTrue(result['collector_returned'])
        self.assertEqual(set(calls[0][2]['files']),{'install','activation'})
    def test_no_other_effect_entrypoints(self):
        tree=ast.parse(pathlib.Path(d.__file__).read_text());attrs={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
        self.assertFalse(attrs & {'observe_host','observe','persist_private','narrow','chmod','fchmod','resume_once','execute_reviewed_probe','apply_reviewed_prerequisites'})

if __name__=='__main__':unittest.main()
