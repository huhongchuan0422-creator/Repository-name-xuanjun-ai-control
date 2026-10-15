"""Portable, synthetic and harmless temporary-directory tests only."""
import copy
import contextlib
import hashlib
import errno
import os
import pathlib
import signal
import stat
import tempfile
import time
import types
import unittest
from unittest import mock
import epoch7_owner_prerequisite as p


class FakeDirectories(object):
    def __init__(self):self.modes={path:0o775 for path in p.TARGETS};self.calls=[];self.failure=None
    def check(self):
        return {path:dict(dev=1,ino=index+1,mode=mode,uid=1002,gid=1002,nlink=2,size=4096,
            mtime_ns=1,ctime_ns=2 if mode==0o755 else 1) for index,(path,mode) in enumerate(sorted(self.modes.items()))}
    def narrow(self,path):
        self.calls.append(path)
        if self.failure==path:raise OSError('PRIVATE_SECRET')
        self.modes[path]=0o755
        return {'mode':0o755}


class FakeBackend(object):
    def __init__(self):
        self.directories=FakeDirectories();self.events=[];self.guard_fail=None;self.node_fail=False;self.after_fail=False;self.exit_fail=False
    def __enter__(self):self.events.append('enter');return self
    def __exit__(self,*args):
        self.events.append('exit')
        if self.exit_fail:raise ValueError('PREREQUISITE_DESCRIPTOR_CLEANUP')
    def entry_evidence(self):return {'two_fixed_sources':'fixture'}
    def guard(self):
        self.events.append('guard')
        if self.guard_fail==self.events.count('guard'):raise ValueError('PREREQUISITE_ACTIVATION_CHANGED')
        return {'epoch':7,'state':'PREPARED'}
    def node_measurement(self):
        self.events.append('node')
        if self.node_fail:raise ValueError('NODE_REFERENCE_RETAINED_ELF_HASH')
        return {'kind':'FIXED_NODE_DIRECTORY_ALIAS_MEASUREMENT','admission':'NOT_GRANTED',
            'unsafe_ancestors':sorted(p.TARGETS[1:]),'reference_path':'fixed-alias',
            'link':{'path':'fixed-link','metadata':{'ino':99}},
            'ancestors':{path:row for path,row in self.directories.check().items() if path in p.TARGETS[1:]},
            'final':{'path':p.NODE,'sha256':p.NODE_SHA,'metadata':{'size':p.NODE_SIZE,'ino':77}}}
    def node_admission(self):
        self.events.append('strict_node')
        if self.after_fail:raise ValueError('NODE_REFERENCE_COMPLETE_ROUND_RACE')
        value=self.node_measurement();value['kind']='FIXED_NODE_DIRECTORY_ALIAS'
        value.pop('admission');value.pop('unsafe_ancestors');return value


class SequenceTests(unittest.TestCase):
    def test_ack_required_before_backend_entry(self):
        backend=FakeBackend();r=p.execute(backend,False)
        self.assertEqual(r['stage'],'HOLD');self.assertEqual(backend.events,[])
    def test_no_truthy_ack(self):
        for value in (1,'yes',[],None):self.assertEqual(p.execute(FakeBackend(),value)['stage'],'HOLD')
    def test_exact_complete_once(self):
        b=FakeBackend();r=p.execute(b,True)
        self.assertEqual(r['stage'],'COMPLETE_PREREQUISITES_ONLY');self.assertEqual(r['completed'],list(p.TARGETS))
        self.assertEqual(b.directories.calls,list(p.TARGETS));self.assertFalse(r['automatic_retry'])
        self.assertEqual(r['production_admission'],'NOT_GRANTED');self.assertEqual(r['service_actions'],0)
        self.assertLess(b.events.index('node'),b.events.index('strict_node'));self.assertEqual(b.events[-1],'exit')
    def test_node_failure_before_changes(self):
        b=FakeBackend();b.node_fail=True;r=p.execute(b,True)
        self.assertEqual(r['attempted'],[]);self.assertEqual(b.directories.calls,[])
    def test_first_state_failure_before_node(self):
        b=FakeBackend();b.guard_fail=1;r=p.execute(b,True)
        self.assertEqual(r['stage'],'HOLD');self.assertNotIn('node',b.events)
    def test_second_state_failure_before_any_change(self):
        b=FakeBackend();b.guard_fail=2;r=p.execute(b,True);self.assertEqual(r['attempted'],[])
    def test_state_change_between_targets_stops(self):
        b=FakeBackend();b.guard_fail=4;r=p.execute(b,True)
        self.assertEqual(r['completed'],[p.TARGETS[0]]);self.assertEqual(r['stage'],'PARTIAL_HOLD')
    def test_each_chmod_failure_retains_partial(self):
        for index,path in enumerate(p.TARGETS):
            b=FakeBackend();b.directories.failure=path;r=p.execute(b,True)
            self.assertEqual(r['completed'],list(p.TARGETS[:index]));self.assertEqual(r['attempted'],list(p.TARGETS[:index+1]))
            self.assertEqual(r['stage'],'PARTIAL_HOLD');self.assertNotIn('PRIVATE_SECRET',str(r));self.assertFalse(r['permission_widening_rollback'])
    def test_post_node_failure_retains_all_narrowed(self):
        b=FakeBackend();b.after_fail=True;r=p.execute(b,True)
        self.assertEqual(r['stage'],'PARTIAL_HOLD');self.assertEqual(r['completed'],list(p.TARGETS));self.assertEqual(set(b.directories.modes.values()),{0o755})
    def test_cleanup_failure_cannot_claim_complete(self):
        b=FakeBackend();b.exit_fail=True;r=p.execute(b,True);self.assertEqual(r['stage'],'PARTIAL_HOLD')
    def test_interrupt_records_attempt_not_success(self):
        b=FakeBackend()
        def interrupted(path):raise KeyboardInterrupt()
        b.directories.narrow=interrupted;r=p.execute(b,True)
        self.assertEqual(r['failure_code'],'PREREQUISITE_INTERRUPTED');self.assertEqual(r['completed'],[]);self.assertEqual(r['attempted'],[p.TARGETS[0]])
    def test_same_bytes_replaced_node_inode_stays_partial_hold(self):
        b=FakeBackend();original=b.node_admission
        def replaced():
            value=original();value['final']['metadata']['ino']=78;return value
        b.node_admission=replaced;r=p.execute(b,True)
        self.assertEqual(r['stage'],'PARTIAL_HOLD');self.assertEqual(r['failure_code'],'PREREQUISITE_NODE_IDENTITY_CHANGED')

    def test_link_replaced_between_proofs_stays_partial_hold(self):
        b=FakeBackend();original=b.node_admission
        def replaced():
            value=original();value['link']['metadata']['ino']=100;return value
        b.node_admission=replaced;r=p.execute(b,True)
        self.assertEqual(r['stage'],'PARTIAL_HOLD')

    def test_static_shared_cleanup_cause_preserves_primary_and_flags_uncertainty(self):
        for code in ('EXISTING_LOCKS_CLEANUP_UNKNOWN','NODE_REFERENCE_CLEANUP_UNKNOWN'):
            b=FakeBackend()
            def interrupted():raise KeyboardInterrupt() from ValueError(code)
            b.node_measurement=interrupted;result=p.execute(b,True)
            self.assertEqual(result['failure_code'],'PREREQUISITE_INTERRUPTED')
            self.assertTrue(result['cleanup_failed']);self.assertEqual(result['attempted'],[])

    def test_measurement_kind_not_admission(self):
        b=FakeBackend();original=b.node_measurement
        def wrong():
            value=original();value['kind']='FIXED_NODE_DIRECTORY_ALIAS';return value
        b.node_measurement=wrong;r=p.execute(b,True);self.assertEqual(r['attempted'],[])
    def test_wrong_node_size_refuses_before_effects(self):
        b=FakeBackend();original=b.node_measurement
        def wrong():
            value=original();value['final']['metadata']['size']-=1;return value
        b.node_measurement=wrong;self.assertEqual(p.execute(b,True)['attempted'],[])


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='p2-prerequisite-fixture-');self.root=self.tmp.name
        paths=[('/home',0o755),(p.HOME,0o700),(p.OPENCLAW,0o700)]+[(path,0o775) for path in p.TARGETS]
        for path,mode in paths:
            name=self.root+path;os.mkdir(name);os.chmod(name,mode)
        self.owner=(os.getuid(),os.getgid())
    def tearDown(self):self.tmp.cleanup()
    def held(self):return p.HeldDirectories(self.root,self.owner,self.owner,0o700)
    def test_genuine_three_fd_changes_preserve_bytes_owner_and_group(self):
        files={}
        for index,path in enumerate(p.TARGETS):
            name=self.root+path+'/fixture'+str(index);raw=('harmless'+str(index)).encode()
            with open(name,'wb') as stream:stream.write(raw)
            files[name]=raw
        with self.held() as held:
            before=held.check()
            for path in p.TARGETS:held.narrow(path)
            after=held.check()
        for path in p.TARGETS:
            self.assertEqual(after[path]['mode'],0o755)
            for key in p.FIELDS:
                if key not in ('mode','ctime_ns'):self.assertEqual(before[path][key],after[path][key])
        for name,raw in files.items():
            with open(name,'rb') as stream:self.assertEqual(stream.read(),raw)
    def test_already_755_is_hold(self):
        os.chmod(self.root+p.TARGETS[0],0o755)
        with self.assertRaisesRegex(ValueError,'DIRECTORY_AUTHORITY'):
            with self.held():pass
    def test_symlink_target_refused(self):
        os.rmdir(self.root+p.TARGETS[0]);os.symlink('tools',self.root+p.TARGETS[0])
        with self.assertRaises(OSError):
            with self.held():pass
    def test_wrong_mode_refused(self):
        os.chmod(self.root+p.TARGETS[1],0o777)
        with self.assertRaisesRegex(ValueError,'DIRECTORY_AUTHORITY'):
            with self.held():pass
    def test_parent_775_refused(self):
        os.chmod(self.root+p.OPENCLAW,0o775)
        with self.assertRaisesRegex(ValueError,'DIRECTORY_AUTHORITY'):
            with self.held():pass
    def test_acl_refused(self):
        with mock.patch.object(p.os,'getxattr',return_value=b'present'):
            with self.assertRaisesRegex(ValueError,'ACL_OR_CAPABILITY'):
                with self.held():pass
    def test_unknown_xattr_failure_refused(self):
        with mock.patch.object(p.os,'getxattr',side_effect=OSError(errno.EPERM,'private')):
            with self.assertRaisesRegex(ValueError,'XATTR_UNKNOWN'):
                with self.held():pass
    def test_directory_replaced_after_open(self):
        with self.held() as held:
            path=self.root+p.TARGETS[0];os.rename(path,path+'.old');os.mkdir(path);os.chmod(path,0o775)
            with self.assertRaisesRegex(ValueError,'DIRECTORY_CHANGED'):held.narrow(p.TARGETS[0])
        self.assertEqual(stat.S_IMODE(os.stat(path+'.old').st_mode),0o775)
    def test_new_child_aborts_before_chmod(self):
        with self.held() as held:
            open(self.root+p.TARGETS[0]+'/new','wb').close()
            with self.assertRaisesRegex(ValueError,'DIRECTORY_CHANGED|CONTENTS_CHANGED'):held.narrow(p.TARGETS[0])
    def test_permission_drift_aborts(self):
        with self.held() as held:
            os.chmod(self.root+p.TARGETS[2],0o755)
            with self.assertRaisesRegex(ValueError,'DIRECTORY_CHANGED'):held.narrow(p.TARGETS[0])
    def test_second_narrow_same_fd_refused(self):
        with self.held() as held:
            held.narrow(p.TARGETS[0])
            with self.assertRaisesRegex(ValueError,'ALREADY_CHANGED'):held.narrow(p.TARGETS[0])
    def test_out_of_scope_path_refused(self):
        with self.held() as held:
            with self.assertRaisesRegex(ValueError,'TARGET_SCOPE'):held.narrow(p.OPENCLAW)
    def test_fchmod_does_not_widen_after_partial_failure(self):
        with self.held() as held:
            held.narrow(p.TARGETS[0])
            with mock.patch.object(p.os,'fchmod',side_effect=OSError(errno.EPERM,'denied')):
                with self.assertRaises(OSError):held.narrow(p.TARGETS[1])
        self.assertEqual(stat.S_IMODE(os.stat(self.root+p.TARGETS[0]).st_mode),0o755)
        self.assertEqual(stat.S_IMODE(os.stat(self.root+p.TARGETS[1]).st_mode),0o775)
    def test_real_target_reverted_during_node_admission_is_detected(self):
        fixture=self
        class Backend(FakeBackend):
            def __enter__(inner):inner.directories=fixture.held().__enter__();return inner
            def __exit__(inner,*args):return inner.directories.__exit__(*args)
            def node_admission(inner):
                result=super(Backend,inner).node_admission()
                os.chmod(fixture.root+p.TARGETS[0],0o775)
                return result
        result=p.execute(Backend(),True)
        self.assertEqual(result['stage'],'PARTIAL_HOLD');self.assertEqual(result['failure_code'],'PREREQUISITE_DIRECTORY_CHANGED')

    def test_real_target_reverted_during_final_guard_is_detected(self):
        fixture=self
        class Backend(FakeBackend):
            def __enter__(inner):inner.directories=fixture.held().__enter__();return inner
            def __exit__(inner,*args):return inner.directories.__exit__(*args)
            def guard(inner):
                result=super(Backend,inner).guard()
                if inner.events.count('guard')==7:os.chmod(fixture.root+p.TARGETS[0],0o775)
                return result
        result=p.execute(Backend(),True)
        self.assertEqual(result['stage'],'PARTIAL_HOLD');self.assertEqual(result['failure_code'],'PREREQUISITE_DIRECTORY_CHANGED')

    def test_enumeration_bound_prevents_mutation(self):
        class Entry:
            name='fixture'
        class Entries:
            def __enter__(self):return iter([Entry()]*4097)
            def __exit__(self,*args):pass
        with mock.patch.object(p.os,'scandir',return_value=Entries()):
            with self.assertRaisesRegex(ValueError,'ENTRY_BOUND'):
                with self.held():pass
    def test_fd_cleanup_when_open_fails(self):
        before=len(os.listdir('/proc/self/fd'));os.chmod(self.root+p.TARGETS[2],0o777)
        with self.assertRaises(ValueError):
            with self.held():pass
        self.assertEqual(len(os.listdir('/proc/self/fd')),before)


class BoundaryTests(unittest.TestCase):
    def test_production_refuses_non_root_before_backend(self):
        with mock.patch.object(p.os,'geteuid',return_value=1000):
            with self.assertRaisesRegex(ValueError,'FIXED_ROOT_HOST'):p.apply_reviewed_prerequisites(True)
    def test_timer_refuses_preexisting_alarm(self):
        with mock.patch.object(p.signal,'getitimer',return_value=(1.0,0.0)):
            with self.assertRaisesRegex(ValueError,'EXISTING_TIMER'):
                with p.bounded():pass
    def test_actual_timer_interrupt_and_restore(self):
        previous=signal.getsignal(signal.SIGALRM)
        with mock.patch.object(p,'MAX_SECONDS',0.02):
            with self.assertRaises(p.PrerequisiteTimeout):
                with p.bounded():time.sleep(0.2)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0));self.assertEqual(signal.getsignal(signal.SIGALRM),previous)
    def test_interrupted_close_attempts_each_owned_fd_once(self):
        held=p.HeldDirectories();held.held=[10,11,12]
        with mock.patch.object(p.os,'close',side_effect=[KeyboardInterrupt(),None,None]) as close:
            with self.assertRaises(KeyboardInterrupt):held.close()
        self.assertEqual(close.call_args_list,[mock.call(12),mock.call(11),mock.call(10)])
        self.assertEqual(held.held,[])

    def test_setup_primary_survives_stack_cleanup_error(self):
        primary=KeyboardInterrupt()
        reader=mock.Mock();reader.read.side_effect=primary
        observed=types.SimpleNamespace(ObservationReader=mock.Mock(return_value=reader))
        stack=mock.Mock();stack.__exit__=mock.Mock(side_effect=ValueError('SECONDARY'))
        with mock.patch.dict('sys.modules',{'snapshot_io':types.SimpleNamespace(),'observe_epoch7':observed}),mock.patch.object(p.contextlib,'ExitStack',return_value=stack):
            with self.assertRaises(KeyboardInterrupt) as raised:p.FixedBackend().__enter__()
        self.assertIs(raised.exception,primary);self.assertTrue(primary.prerequisite_cleanup_failed)

    def test_primary_interruption_preserved_on_directory_cleanup_failure(self):
        held=p.HeldDirectories();held.held=[999999]
        error=KeyboardInterrupt()
        self.assertFalse(held.__exit__(KeyboardInterrupt,error,None));self.assertTrue(error.prerequisite_cleanup_failed)





class ConcreteGuardTests(unittest.TestCase):
    def setUp(self):
        import epoch7_snapshot as c
        import epoch7_delta as d
        self.c,self.d=c,d
        def packed(value):return d.canonical(value)+b'\n'
        self.active=dict(schema=1,state='PREPARED',epoch=7,generation=1,release_sha256=d.OLD_MANIFEST,
            config_sha256='c'*64,binary_sha256=d.OLD_BINARY,ledger_uuid='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
            instance='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',db_path=d.DB,ledger_socket=d.SOCKET)
        last='0'*64;journal=b''
        for epoch in range(1,8):
            value=dict(self.active,epoch=epoch)
            line=packed(dict(schema=1,seq=epoch,epoch=epoch,state='PREPARED',previous_sha256=last,
                descriptor_sha256=c.sha(packed(value)),descriptor=value,proof={}))
            journal+=line;last=c.sha(line)
        self.raw={c.ACTIVE:packed(self.active),c.EPOCHS:journal}
        units={}
        for unit in c.WRITER_UNITS:
            masked='/etc/systemd/system/'+unit in c.LEGACY_MASKS
            state=dict(Id=unit,LoadState='masked' if masked else 'loaded',ActiveState='inactive',MainPID='0',
                ControlPID='0',ControlGroup='',NeedDaemonReload='no',UnitFileState='masked' if masked else 'disabled',ConditionResult='no')
            units[unit]={'state':state,'cgroup_entries':{}}
        background=[]
        self.writers={'units':units,'masks':{path:dict(kind='MASK',link='/dev/null',uid=0,gid=0,nlink=1,mode=0o777) for path in c.LEGACY_MASKS},
            'scheduler_sha256':'d'*64,'control_files':{'fixed':'pin'},'manager':{'fixed':'manager'},
            'processes':dict(process_identity_sha256='e'*64,fd_count=7,background_processes=background,background_processes_sha256=d.digest(background))}
        fixture=self
        class IO:
            def check_locks(self):pass
            def read(self,path):
                raw=fixture.raw[path];return raw,{'sha256':c.sha(raw),'mode':0o644,'uid':0,'gid':0,'nlink':1}
            def writers(self,*args):return copy.deepcopy(fixture.writers)
        self.backend=p.FixedBackend();self.backend.c=c;self.backend.d=d;self.backend.io=IO();self.backend.policy={}
        self.backend.state=None;self.backend.stable_writer=None
    def test_actual_activation_chain_and_writer_validator_pass(self):
        result=self.backend.guard();self.assertEqual(result['epoch'],7);self.assertEqual(result['state'],'PREPARED')
        self.assertEqual(self.backend.guard(),result)
    def test_activation_file_authority_required(self):
        original=self.backend.io.read
        for key,bad in (('uid',1002),('gid',1002),('mode',0o600),('nlink',2)):
            def changed(path):
                raw,row=original(path);row[key]=bad;return raw,row
            self.backend.io.read=changed
            with self.assertRaisesRegex(ValueError,'ACTIVATION_AUTHORITY'):self.backend.guard()
        self.backend.io.read=original

    def test_active_epoch_refused(self):
        self.active['state']='ACTIVE';self.raw[self.c.ACTIVE]=self.d.canonical(self.active)+b'\n'
        with self.assertRaisesRegex(ValueError,'EXACT_PREPARED_ACTIVATION'):self.backend.guard()
    def test_epoch8_refused(self):
        self.active['epoch']=8;self.raw[self.c.ACTIVE]=self.d.canonical(self.active)+b'\n'
        with self.assertRaisesRegex(ValueError,'EXACT_PREPARED_ACTIVATION'):self.backend.guard()
    def test_wrong_binary_refused(self):
        self.active['binary_sha256']='f'*64;self.raw[self.c.ACTIVE]=self.d.canonical(self.active)+b'\n'
        with self.assertRaisesRegex(ValueError,'ACTIVATION_IDENTITY'):self.backend.guard()
    def test_chain_corruption_refused(self):
        self.raw[self.c.EPOCHS]=self.raw[self.c.EPOCHS].replace(b'"seq":1',b'"seq":9')
        with self.assertRaisesRegex(ValueError,'EPOCH_JOURNAL_RECORD'):self.backend.guard()
    def test_activation_raw_drift_refused(self):
        self.backend.guard();self.raw[self.c.ACTIVE]=b' '+self.raw[self.c.ACTIVE]
        with self.assertRaisesRegex(ValueError,'ACTIVATION_CHANGED'):self.backend.guard()
    def test_active_writer_refused(self):
        self.writers['units']['xuanjun-uk-openclaw.service']['state']['ActiveState']='active'
        with self.assertRaisesRegex(ValueError,'WRITER_NOT_STOPPED'):self.backend.guard()
    def test_writer_pid_refused(self):
        self.writers['units']['nginx.service']['state']['MainPID']='42'
        with self.assertRaisesRegex(ValueError,'WRITER_NOT_STOPPED'):self.backend.guard()
    def test_nonempty_cgroup_refused(self):
        unit='nginx.service';self.writers['units'][unit]['cgroup_entries']={'/sys/fs/cgroup/systemd/system.slice/'+unit+'/cgroup.procs':'f'*64}
        with self.assertRaisesRegex(ValueError,'CGROUP_NOT_EMPTY'):self.backend.guard()
    def test_runner_condition_refused(self):
        self.writers['units'][self.c.RUNNER]['state']['ConditionResult']='yes'
        with self.assertRaisesRegex(ValueError,'RUNNER_NOT_EXCLUDED'):self.backend.guard()
    def test_mask_changed_refused(self):
        self.writers['masks'][next(iter(self.c.LEGACY_MASKS))]['link']='/elsewhere'
        with self.assertRaisesRegex(ValueError,'MASK_NOT_PRESERVED'):self.backend.guard()
    def test_scheduler_drift_refused(self):
        self.backend.guard();self.writers['scheduler_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'WRITER_BASELINE_CHANGED'):self.backend.guard()
    def test_control_bytes_drift_refused(self):
        self.backend.guard();self.writers['control_files']['fixed']='changed'
        with self.assertRaisesRegex(ValueError,'WRITER_BASELINE_CHANGED'):self.backend.guard()
    def test_unrelated_process_churn_does_not_change_stable_gate(self):
        self.backend.guard();self.writers['processes']['process_identity_sha256']='f'*64
        self.assertEqual(self.backend.guard()['state'],'PREPARED')
    def test_unsafe_background_even_if_digest_consistent_refused(self):
        row={'before':{},'after':{}};self.writers['processes']['background_processes']=[row]
        self.writers['processes']['background_processes_sha256']=self.d.digest([row])
        with self.assertRaises(ValueError):self.backend.guard()


class PublicFileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='p2-prerequisite-public-');self.addCleanup(self.temp.cleanup)
        root=self.temp.name;self.owner=(os.getuid(),os.getgid());self.files={};self.spec={}
        for index,(path,(size,unused,mode)) in enumerate(p.PUBLIC_FILES.items()):
            name=root+'/file'+str(index);raw=b'x'*size
            with open(name,'wb') as stream:stream.write(raw)
            os.chmod(name,mode or 0o644);self.files[path]=name
            self.spec[path]=(size,hashlib.sha256(raw).hexdigest(),mode)
        fixture=self
        class Reader:
            @contextlib.contextmanager
            def parent(self,path):
                fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
                try:yield fd,os.path.basename(fixture.files[path])
                finally:os.close(fd)
            def read(self,path,maximum):
                name=fixture.files[path]
                fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW)
                try:
                    before=os.fstat(fd);raw=os.read(fd,maximum+1)
                    return raw,dict(p.metadata(before),sha256=hashlib.sha256(raw).hexdigest())
                finally:os.close(fd)
        self.reader=Reader();self.patcher=mock.patch.object(p,'PUBLIC_FILES',self.spec);self.patcher.start();self.addCleanup(self.patcher.stop)
    def held(self):return p.HeldPublicFiles(self.reader,self.owner)
    def test_two_exact_small_sources_are_held_and_checked(self):
        with self.held() as held:self.assertEqual(set(held.check()),set(self.files))
    def test_hash_change_before_entry_refused(self):
        name=next(iter(self.files.values()))
        with open(name,'r+b') as stream:stream.write(b'z')
        with self.assertRaisesRegex(ValueError,'SOURCE_HASH'):
            with self.held():pass
    def test_leaf_symlink_refused(self):
        names=list(self.files.values());os.unlink(names[0]);os.symlink(names[1],names[0])
        with self.assertRaisesRegex(ValueError,'SOURCE_AUTHORITY'):
            with self.held():pass
    def test_source_modified_in_place_after_open_refused(self):
        with self.held() as held:
            with open(next(iter(self.files.values())),'r+b') as stream:stream.write(b'z')
            with self.assertRaisesRegex(ValueError,'HELD_FILE_CHANGED'):held.check()
    def test_same_bytes_new_inode_refused(self):
        with self.held() as held:
            name=next(iter(self.files.values()))
            with open(name,'rb') as stream:raw=stream.read()
            mode=stat.S_IMODE(os.stat(name).st_mode);os.rename(name,name+'.old')
            with open(name,'wb') as stream:stream.write(raw)
            os.chmod(name,mode)
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED|HELD_FILE_CHANGED'):held.check()
    def test_source_group_write_refused(self):
        os.chmod(next(iter(self.files.values())),0o775)
        with self.assertRaisesRegex(ValueError,'SOURCE_AUTHORITY'):
            with self.held():pass
    def test_source_size_drift_refused(self):
        with open(next(iter(self.files.values())),'ab') as stream:stream.write(b'x')
        with self.assertRaisesRegex(ValueError,'SOURCE_AUTHORITY'):
            with self.held():pass
    def test_close_interruption_attempts_each_owned_leaf_once(self):
        holder=p.HeldPublicFiles(self.reader);holder.held=[71,72]
        with mock.patch.object(p.os,'close',side_effect=[KeyboardInterrupt(),None]) as close:
            with self.assertRaises(KeyboardInterrupt):holder.close()
        self.assertEqual(close.call_args_list,[mock.call(72),mock.call(71)]);self.assertEqual(holder.held,[])



if __name__=='__main__':unittest.main()
