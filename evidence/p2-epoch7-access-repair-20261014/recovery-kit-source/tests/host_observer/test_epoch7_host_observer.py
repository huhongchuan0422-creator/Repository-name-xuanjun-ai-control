"""Local actual /proc helper tests and synthetic unit-boundary failures."""
import os
import pathlib
import tempfile
import time
import unittest
import copy
import types
from unittest import mock

import epoch7_host_observer as o
import epoch7_delta as d
from epoch7_recovery_sequence import BoundedDiagnostics


class ProcTests(unittest.TestCase):
    def setUp(self):
        self.c=o.LinuxProcessCensus({'context_sha256':d.digest('context')},mock.Mock(),
            BoundedDiagnostics(lambda e:None),lambda exe:True,
            {path:{'dev':1,'ino':i+1} for i,path in enumerate(o.snap.DATABASES)}, {},
            {p+s:None for p in o.snap.DATABASES if p!=d.DB for s in ('-wal','-shm','-journal')})
        self.c.deadline=time.monotonic()+30;self.c.phase='post_install_checks'
    def test_stable_own_fd_directory_has_no_phantom_enumeration_descriptor(self):
        stream=o.StableDirectory(os.open('/proc/self/fd',o.D_FLAGS))
        try:
            names=stream.names(1024)
            for name in names:os.stat(name,dir_fd=stream.fd,follow_symlinks=True)
            self.assertEqual(names,stream.names(1024))
            self.assertIn(str(stream.fd),names)
        finally:stream.close()
    def test_actual_self_identity_and_read_only_fd_report(self):
        pid=os.getpid();identity=self.c._identity(pid,None)
        self.assertEqual(identity['pid'],pid)
        self.assertFalse(identity['kernel_thread'])
        self.assertEqual(identity['uids'],[os.geteuid()]*4)
        base=str(pathlib.Path(__import__('epoch7_protected_fs').__file__).resolve().parent/'fixtures')
        fd,path=tempfile.mkstemp(dir=base)
        try:
            info=os.fstat(fd);rows,count=self.c._fds(pid,{(info.st_dev,info.st_ino):(o.d.DB,o.d.DB)})
            selected=[row for row in rows if row['fd']==fd]
            self.assertEqual(len(selected),1)
            self.assertEqual(selected[0]['flags']&os.O_ACCMODE,os.O_RDWR)
            self.assertGreater(count,0)
        finally:os.close(fd);os.unlink(path)
    def test_confirmed_database_fd_disappearance_is_never_benign_retry(self):
        base=str(pathlib.Path(__import__('epoch7_protected_fs').__file__).resolve().parent/'fixtures')
        fd,path=tempfile.mkstemp(dir=base);pid=os.getpid();info=os.fstat(fd)
        original=self.c._read
        def read(name,maximum):
            if name=='/proc/%d/fdinfo/%d'%(pid,fd):raise FileNotFoundError('closed after watched inode')
            return original(name,maximum)
        try:
            with mock.patch.object(self.c,'_read',side_effect=read):
                with self.assertRaisesRegex(ValueError,'WATCHED_FD_DISAPPEARED'):
                    self.c._fds(pid,{(info.st_dev,info.st_ino):(o.d.DB,o.d.DB)})
        finally:os.close(fd);os.unlink(path)
    def test_expired_deadline_stops_before_proc_read(self):
        self.c.deadline=time.monotonic()-1
        with self.assertRaisesRegex(ValueError,'TOTAL_DEADLINE'):self.c._identity(os.getpid(),None)
    def test_unknown_or_deleted_executable_fails_closed(self):
        with mock.patch.object(o.os,'readlink',return_value='/bin/unknown (deleted)'):
            with self.assertRaisesRegex(ValueError,'EXECUTABLE_PATH'):self.c._executable(os.getpid())
    def test_database_inode_drift_fails_before_any_fd_exception(self):
        with mock.patch.object(o.os,'lstat',return_value=type('S',(),{'st_mode':0o100600,'st_dev':9,'st_ino':9,'st_nlink':1,'st_uid':0,'st_gid':0})()):
            with self.assertRaisesRegex(ValueError,'DATABASE_IDENTITY_CHANGED'):self.c._database_paths()
    def test_scoped_identity_measures_actual_parent_start_and_executable_inode(self):
        pid=os.getpid();self.c.scoped_units={'synthetic'}
        value=self.c._identity(pid,'synthetic');meta=self.c.process_meta[pid]
        self.assertEqual(meta['ppid'],os.getppid());self.assertGreater(meta['parent_starttime'],0)
        info=os.stat('/proc/self/exe')
        self.assertEqual((meta['executable_dev'],meta['executable_ino']),(info.st_dev,info.st_ino))
        self.assertGreater(meta['cmdline_size'],0)
        self.assertEqual(value['argv_sha256'],o.sha(pathlib.Path('/proc/self/cmdline').read_bytes()))
    def test_no_process_or_unit_mutation_commands(self):
        raw=pathlib.Path(o.__file__).read_text()
        for value in ('subprocess.run(','.communicate(',"'service_start'","'service_stop'",'sqlite3.connect'):
            self.assertNotIn(value,raw)

class BatchedUnitTests(unittest.TestCase):
    def raw(self,units):
        rows=[]
        for unit in units:
            value={key:'' for key in o.UNIT_FIELDS};value.update(Id=unit,MainPID='0',ControlPID='0')
            rows.append('\n'.join(key+'='+value[key] for key in sorted(value)))
        return ('\n\n'.join(rows)+'\n').encode()
    def test_exact19_identity_blocks_parse_without_order_assumption(self):
        units=sorted(o.snap.WRITER_UNITS);result=o.LinuxProcessCensus._parse_unit_blocks(self.raw(list(reversed(units))),units)
        self.assertEqual(set(result),set(units));self.assertTrue(all(row['MainPID']==0 for row in result.values()))
    def test_missing_duplicate_unknown_and_truncated_blocks_hold(self):
        units=sorted(o.snap.WRITER_UNITS)
        for raw in (self.raw(units[:-1]),self.raw(units[:-1]+[units[0]]),self.raw(units).replace(b'Id=',b'Unknown='),self.raw(units)[:-20]):
            with self.assertRaises(ValueError):o.LinuxProcessCensus._parse_unit_blocks(raw,units)
    def test_output_cap_and_malformed_separators_cannot_merge_units(self):
        units=sorted(o.snap.WRITER_UNITS);raw=self.raw(units)
        for malformed in (b'x'*65537,raw.replace(b'\n\n',b'\n',1),raw.replace(b'\n\n',b'\n\n\n',1),
                          raw.replace(units[0].encode(),b'unknown.service',1)):
            with self.assertRaises(ValueError):o.LinuxProcessCensus._parse_unit_blocks(malformed,units)

    def test_two_batch_commands_keep_four_full_cgroup_scans_per_census(self):
        value=object.__new__(o.LinuxProcessCensus);units=sorted(o.snap.WRITER_UNITS)
        states=o.LinuxProcessCensus._parse_unit_blocks(self.raw(units),units)
        value._show_units=mock.Mock(return_value=states);value._cgroups=mock.Mock(return_value=(False,{}))
        before=value._all_units();after=value._all_units()
        self.assertEqual(before,after);self.assertEqual(value._show_units.call_count,4)
        self.assertEqual(value._cgroups.call_count,4*len(units))
    def test_batch_reobservation_still_refuses_unit_drift(self):
        value=object.__new__(o.LinuxProcessCensus);units=sorted(o.snap.WRITER_UNITS)
        states=o.LinuxProcessCensus._parse_unit_blocks(self.raw(units),units);changed=copy.deepcopy(states)
        changed[units[0]]['NeedDaemonReload']='yes'
        value._show_units=mock.Mock(side_effect=[states,changed]);value._cgroups=mock.Mock(return_value=(False,{}))
        with self.assertRaisesRegex(ValueError,'BATCH_UNIT_CGROUP_RACE'):value._all_units()


class OwnedReceiptTests(unittest.TestCase):
    """Protected read boundaries mocked; actual canonical schemas and CAS logic."""
    def make(self):
        from epoch7_injected_recovery import PROVISION
        value=object.__new__(o.Epoch7HostObserver)
        value.context={'context_sha256':'a'*64}
        value.authority=types.SimpleNamespace(binding={'review_id':7000000001},receipt=mock.Mock())
        path='/etc/systemd/system/xuanjun-development-dispatcher.service'
        observed={'kind':'FILE','sha256':o.sha(b'unit'),'uid':0,'gid':0,'mode':0o644,
                  'dev':1,'ino':2,'nlink':1,'size':4,'mtime_ns':3,'ctime_ns':4}
        after={k:observed[k] for k in ('kind','sha256','uid','gid','mode')}
        change={'path':path,'operation':'REPLACE','before':{'kind':'FILE'},'after':after}
        row=dict(change,state='DONE',backup={'name':'private'},observed_after=copy.deepcopy(observed))
        journal={'schema':1,'name':PROVISION,'transaction_id':d.TX,'binding':value.authority.binding,
                 'state':{'stage':'TARGET_DELTA_COMPLETE','targets':[row]}}
        value.driver_gate=types.SimpleNamespace(delta={'changes':[copy.deepcopy(change)]},
            current_targets={path:copy.deepcopy(observed)},journal_binding=lambda:value.authority.binding)
        value.live_contract={'unit_transition_contract':{'targets':{path:{k:after[k] for k in ('sha256','uid','gid','mode')}}}}
        value.runtime=types.SimpleNamespace(successful_commands={})
        value.outer_io=mock.Mock()
        value.runtime.legacy=types.SimpleNamespace(io=value.outer_io,restoration_evidence=mock.Mock(return_value=None))
        # An actual harmless directory descriptor keeps the real finally-close.
        value.outer_io._parent.side_effect=lambda path:(os.open('/tmp',o.D_FLAGS),'fixture')
        value.outer_io._read_at.side_effect=lambda parent,leaf:({'uid':0,'gid':0,'mode':0o600,'nlink':1},d.canonical(journal)+b'\n')
        value.outer_io.read_target.side_effect=lambda path:copy.deepcopy(observed)
        return value,path,observed,journal
    def test_complete_own_receipt_is_bound_to_exact_published_inode(self):
        from epoch7_injected_recovery import PROVISION
        value,path,observed,journal=self.make()
        actual=value._target_transition('replace_retained_targets','after')
        self.assertEqual(actual['target_receipt']['path'],PROVISION)
        self.assertEqual(actual['target_receipt']['targets'],{path:observed})
        self.assertEqual(actual['target_receipt']['sha256'],o.sha(d.canonical(journal)+b'\n'))
        self.assertIsNone(actual['reload'])
        value.outer_io.read_target.assert_called_once_with(path)
    def test_partial_write_and_cleanup_do_not_claim_future_complete_receipt(self):
        value,path,observed,journal=self.make()
        for phase,boundary in (('stage_exact_release','preflight'),('replace_retained_targets','effect'),('replace_retained_targets','before'),('activate_new_services','cleanup'),('replace_retained_targets','inner')):
            self.assertIsNone(value._target_transition(phase,boundary))
        value.outer_io._parent.assert_not_called()
    def test_same_bytes_replaced_inode_is_not_accepted(self):
        value,path,observed,journal=self.make();observed['ino']=8
        with self.assertRaisesRegex(ValueError,'PUBLISHED_INODE_DRIFT'):
            value._target_transition('replace_retained_targets','after')
    def test_consumed_or_unbound_journal_refused(self):
        value,path,observed,journal=self.make();journal['binding']={'review_id':6170703284}
        with self.assertRaisesRegex(ValueError,'RECEIPT_BINDING'):
            value._target_transition('replace_retained_targets','after')
    def test_pending_or_changed_gate_metadata_refused(self):
        for drift in ('state','gate'):
            value,path,observed,journal=self.make()
            if drift=='state':journal['state']['targets'][0]['state']='REPLACE_INTENT'
            else:value.driver_gate.current_targets[path]['ino']=55
            with self.assertRaisesRegex(ValueError,'OWN_CAS_BINDING'):
                value._target_transition('replace_retained_targets','after')
    def test_retained_target_cannot_be_fabricated_as_an_own_replacement(self):
        value,path,observed,journal=self.make();journal['state']['targets']=[];value.driver_gate.delta['changes']=[]
        with self.assertRaisesRegex(ValueError,'NO_UNOWNED_REPLACEMENT'):
            value._target_transition('replace_retained_targets','after')
    def test_reload_receipt_is_actual_success_map_only(self):
        value,path,observed,journal=self.make();receipt={'fixture':'real capture map'}
        value.runtime.successful_commands['daemon_reload']=receipt
        actual=value._target_transition('activate_new_services','effect')
        self.assertEqual(actual['reload'],receipt);self.assertIsNot(actual['reload'],receipt)
    def test_service_capture_pending_and_persisted_are_distinguished(self):
        value,path,observed,journal=self.make()
        captured={'daemon_reload':{'sequence':1},'nginx.service':{'sequence':2}}
        value.runtime.successful_commands=captured
        journal.clear();journal.update(context_sha256='a'*64,successful_commands={'daemon_reload':captured['daemon_reload']})
        self.assertEqual(value._service_receipts('nginx.service')['persistence'],'OWN_CAPTURE_PENDING_PUBLICATION')
        journal['successful_commands']=copy.deepcopy(captured)
        self.assertEqual(value._service_receipts('nginx.service')['persistence'],'PERSISTED')
        journal['successful_commands']['nginx.service']['sequence']=99
        with self.assertRaisesRegex(ValueError,'RECEIPT_DRIFT'):value._service_receipts('nginx.service')

    def test_restore_only_scope_has_no_invented_target_cas(self):
        value,path,observed,journal=self.make()
        value.live_contract['unit_transition_contract']={'targets':{},'gateway_restoration':{'fixture':'reviewed policy'}}
        actual=value._target_transition('activate_new_services','effect')
        self.assertEqual(set(actual),{'context_sha256','target_receipt','reload','gateway_restoration'})
        self.assertIsNone(actual['target_receipt']);self.assertIsNone(actual['gateway_restoration'])
        value.outer_io._parent.assert_not_called()

    def test_gateway_pending_only_until_exact_owned_boot_publication(self):
        value,path,observed,journal=self.make()
        captured={'context_sha256':'a'*64,'legacy_receipt_sha256':'b'*64,
                  'observed_after':observed,'reload':{'sequence':1}}
        value.runtime.legacy.restoration_evidence.return_value=captured
        value.outer_io._read_at.side_effect=FileNotFoundError()
        self.assertEqual(value._gateway_restoration()['persistence'],'OWN_CAPTURE_PENDING_PUBLICATION')
        journal={'context_sha256':'a'*64,'gateway_restoration':copy.deepcopy(captured)}
        value.outer_io._read_at.side_effect=lambda *args:({'uid':0,'gid':0,'mode':0o600,'nlink':1},d.canonical(journal))
        self.assertEqual(value._gateway_restoration()['persistence'],'PERSISTED')
        journal['gateway_restoration']['observed_after']['ino']+=1
        with self.assertRaisesRegex(ValueError,'PERSISTED_RESTORATION_CHANGED'):value._gateway_restoration()

if __name__=='__main__':unittest.main()
