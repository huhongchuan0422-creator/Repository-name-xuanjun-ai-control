"""Containment/legacy wrapper boundary tests, no host effects."""
import copy
import os
import subprocess
import types
import unittest
from unittest import mock

import epoch7_delta as d
import epoch7_host_containment as c
import epoch7_host_phases as h
from epoch7_recovery_sequence import observation
from test_epoch7_delta import fixture


class ContainmentTests(unittest.TestCase):
    def setUp(self):
        self.context={'context_sha256':d.digest('context')}
        self.handler=c.HostContainment.__new__(c.HostContainment)
        self.handler.context=self.context
        self.handler.attempted=set()
        self.handler.guard=lambda *args:True
        authority=mock.Mock()
        authority.receipt.return_value=None
        authority.validate_outer.return_value={'state':{'admission':'ADMITTED'}}
        self.handler.io=mock.Mock(authority=authority)
        self.handler.io.read_journal.return_value={'data':b'claim'}
        snap,candidate=fixture()
        candidate['activation']['release_sha256']=h.MANIFEST
        self.handler.core=types.SimpleNamespace(snapshot=snap,candidate=candidate,
            store=mock.Mock())
        self.handler.runtime=mock.Mock()
        self.handler.legacy=mock.Mock()
        self.handler.observer=mock.Mock()
    def perform(self,op,unit=None):return self.handler.run(self.context,op,unit,None)
    def test_fence_reuses_actual_next_epoch_prepared_semantics(self):
        actual=dict(self.handler.core.candidate['activation'],state='ACTIVE')
        self.handler.core.store.read.return_value=actual
        fenced=dict(actual,state='PREPARED',epoch=9)
        self.handler.core.store.fence.return_value=fenced
        result=self.perform('fence')
        self.assertEqual(result['status'],'OBSERVED')
        self.assertEqual(self.handler.core.current,fenced)
        self.handler.core.store.fence.assert_called_once_with(8,actual['instance'])
    def test_prerebind_fence_preserves_old_release_and_advances_only_epoch(self):
        actual=self.handler.core.snapshot['activation']
        self.handler.core.store.read.return_value=actual
        self.handler.core.store.fence.return_value=dict(actual,epoch=8)
        self.perform('fence')
        self.assertEqual(self.handler.core.current['release_sha256'],d.OLD_MANIFEST)
    def test_fence_canonical_drift_does_not_stop_other_cleanup(self):
        actual=dict(self.handler.core.candidate['activation'],db_path='/tmp/wrong')
        self.handler.core.store.read.return_value=actual
        with self.assertRaisesRegex(ValueError,'FENCE_IDENTITY'):self.perform('fence')
        unit=c.STOP_UNITS[0]
        self.handler.runtime.stop_unit.return_value=observation(self.context,'stop_unit:'+unit,d.digest('stopped'))
        self.assertEqual(self.perform('stop_unit',unit)['operation'],'stop_unit:'+unit)
        self.handler.core.store.fence.assert_not_called()
    def test_wrong_unit_envelope_refused(self):
        unit=c.STOP_UNITS[0]
        self.handler.runtime.stop_unit.return_value=observation(self.context,'stop_unit',d.digest('wrong'))
        with self.assertRaises(ValueError):self.perform('stop_unit',unit)
    def test_no_cleanup_retry(self):
        self.handler.observer.legacy_exclusion.return_value={'checked':True}
        self.perform('verify_legacy_exclusion')
        with self.assertRaisesRegex(ValueError,'FIXED_ONCE'):self.perform('verify_legacy_exclusion')
    def test_claim_not_admitted_refuses_cleanup_mutations(self):
        self.handler.io.authority.validate_outer.return_value={'state':{'admission':'UNKNOWN'}}
        with self.assertRaisesRegex(ValueError,'ADMITTED_CLAIM'):self.perform('stop_unit',c.STOP_UNITS[0])
        self.handler.runtime.stop_unit.assert_not_called()
    def test_gateway_restore_precedes_services_and_failure_prevents_start(self):
        order=[]
        legacy=mock.Mock();runtime=mock.Mock()
        legacy.restore_gateway.side_effect=lambda *args:order.append('restore')
        runtime.activate_new_services.side_effect=lambda *args:order.append('start') or 'result'
        self.assertEqual(c.services_with_gateway(legacy,runtime)(self.context,None),'result')
        self.assertEqual(order,['restore','start'])
        legacy.restore_gateway.side_effect=OSError('uncertain')
        with self.assertRaises(OSError):c.services_with_gateway(legacy,runtime)(self.context,None)
        self.assertEqual(runtime.activate_new_services.call_count,1)
    def test_tls_content_drift_produces_unknown_not_success(self):
        self.handler.observer.tls_contents.return_value={'certificate_sha256':d.digest('wrong'),'tree_fingerprint_sha256':d.digest('wrong')}
        with self.assertRaisesRegex(ValueError,'RETAINED_TLS'):self.perform('verify_retained_tls')
    def test_legacy_inherited_mutators_are_unreachable(self):
        obj=c.BoundLegacyFiles.__new__(c.BoundLegacyFiles)
        for name in ('preflight','stop_and_inhibit','measure_quiescence'):
            with self.assertRaises(ValueError):getattr(obj,name)({})
    def test_legacy_proxy_refuses_unexpected_commands_before_runner(self):
        obj=c.BoundLegacyFiles.__new__(c.BoundLegacyFiles)
        with self.assertRaisesRegex(ValueError,'ONLY_DAEMON_RELOAD'):
            obj._bounded_run(['/usr/bin/systemctl','start','legacy.service'])

class GatewayRestorationTests(unittest.TestCase):
    def make(self):
        obj=object.__new__(c.BoundLegacyFiles)
        obj.context={'context_sha256':'a'*64};obj.restored=True;obj.cleaning=False;obj.restoration=None
        obj.io=mock.Mock();obj.diagnostics=types.SimpleNamespace(sequence=71)
        obj.forward=mock.Mock(return_value=True);obj.executable=mock.Mock(return_value=True)
        obj.cleanup=mock.Mock(return_value=True)
        path='/etc/systemd/system/'+c.GATEWAY;backup=c.fs.TRANSACTION+'/'+c.GATEWAY+'.backup'
        wanted={'path':path,'backup':backup,'sha256':h.sha(b'unit'),'mode':0o644,'uid':0,'gid':0,'was_active':True}
        state={'schema':1,'units':{c.GATEWAY:wanted,c.COORDINATOR:{}},'source_before':{}}
        raw=d.canonical(state)+b'\n';obj.receipt_sha=h.sha(raw)
        obj.io.read_exact.return_value=(raw,{'uid':0,'gid':0,'mode':0o600,'nlink':1})
        actual={'kind':'FILE','sha256':wanted['sha256'],'mode':0o644,'uid':0,'gid':0,'nlink':1,
                'dev':1,'ino':2,'size':4,'mtime_ns':3,'ctime_ns':4}
        rows={path:actual,backup:dict(actual,mode=0o600,ino=3),
              '/etc/systemd/system/'+c.COORDINATOR:{'kind':'MASK','link':'/dev/null'}}
        obj.io._parent.side_effect=lambda path:(os.open('/tmp',os.O_RDONLY|os.O_DIRECTORY),path)
        obj.io._read_at.side_effect=lambda parent,path,**kwargs:(copy.deepcopy(rows[path]),None)
        return obj,rows,actual
    def run_reload(self,obj,action):
        def factory(contract,guard,diagnostics):
            def run(key):
                self.assertIsNotNone(obj.restoration)
                self.assertIsNone(obj.restoration['reload'])
                guard()
                return action()
            return types.SimpleNamespace(run=run)
        with mock.patch.object(c,'ExactCommandRunner',side_effect=factory):
            return obj._bounded_run(['/usr/bin/systemctl','daemon-reload'],stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,timeout=45,check=False)
    def test_owned_file_proof_precedes_reload_guard_and_success_is_captured(self):
        obj,rows,actual=self.make()
        self.run_reload(obj,lambda:subprocess.CompletedProcess(None,0,b'',b''))
        self.assertEqual(obj.restoration_evidence()['observed_after'],actual)
        self.assertEqual(obj.restoration['reload']['sequence'],71)
        self.assertEqual(obj.restoration['reload']['operation'],'daemon_reload')
    def test_failed_reload_keeps_owned_file_proof_without_success(self):
        obj,rows,actual=self.make()
        def fail():raise OSError('uncertain reload')
        with self.assertRaises(OSError):self.run_reload(obj,fail)
        self.assertEqual(obj.restoration['observed_after'],actual)
        self.assertIsNone(obj.restoration['reload'])
    def test_same_bytes_new_inode_and_backup_drift_are_refused(self):
        for target in ('file','backup'):
            obj,rows,actual=self.make();self.run_reload(obj,lambda:subprocess.CompletedProcess(None,0,b'',b''))
            if target=='file':actual['ino']+=1
            else:rows[c.fs.TRANSACTION+'/'+c.GATEWAY+'.backup']['sha256']='b'*64
            with self.assertRaises(ValueError):obj.restoration_evidence()
    def test_coordinator_unmask_and_unowned_reload_refused(self):
        obj,rows,actual=self.make();rows['/etc/systemd/system/'+c.COORDINATOR]['kind']='FILE'
        with self.assertRaisesRegex(ValueError,'COORDINATOR_MASK'):
            self.run_reload(obj,lambda:subprocess.CompletedProcess(None,0,b'',b''))
        obj,rows,actual=self.make();obj.restored=False
        with self.assertRaisesRegex(ValueError,'OWN_RESTORE_ONCE'):
            self.run_reload(obj,lambda:subprocess.CompletedProcess(None,0,b'',b''))


if __name__=='__main__':unittest.main()
