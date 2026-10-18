"""Ordinary temporary-journal tests; not M99, live fencing or production trust."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import catalogue_binding as c
import existing_fd_controller as f
import source_fence as s
import migration_transaction as original
import stage_history
import held_proof


def catalogue():
    conf = {role:{'unit':role+'.service','source_sha256':'a'*64,'effective_configuration_sha256':'b'*64,
                  'runtime_identity_proof':'c'*64,'data_objects':['main'],'writer_origins':['portal'] if role=='portal' else []} for role in c.ROLES}
    obj = {'id':'main','path':'/opt/trading-system/data/project.db','kind':'FILE','classification':'COPY_FENCED',
           'device':1,'inode':2,'uid':1000,'nlink':1,'original_flags':0,'children':[],'writers':['portal']}
    conf['portal']['unit']='secure-secrets-portal.service'
    origin = {'id':'portal','kind':'SERVICE','unit':'secure-secrets-portal.service','retained':False,
              'objects':['main'],'proof_sha256':'d'*64}
    return {'schema':1,'host':c.SOURCE_HOST,'configurations':conf,'objects':[obj],'origins':[origin],
            'coverage_proofs':{'data_membership':'e'*64,'writers_and_activators':'f'*64,'protected_objects':'1'*64}}


def approved_records(value):
    """Fixture record registry keyed by exact digest; not an authority issuer."""
    approved = {('effective_configuration:'+role,c.digest(record)) for role,record in value['configurations'].items()}
    approved.update(value['coverage_proofs'].items())
    approved.update(('writer_origin:'+o['id'],c.digest(o)) for o in value['origins'])
    return lambda kind,digest:(kind,digest) in approved


class CatalogueTests(unittest.TestCase):
    def valid(self,value):
        return c.bind_catalogue(value,c.digest(value),approved_records(value))

    def test_exact_effective_catalogue(self):
        value=catalogue();self.assertEqual(self.valid(value),value)

    def test_unknown_runtime_is_not_source_default(self):
        value=catalogue();value['configurations']['portal']['effective_configuration_sha256']='UNKNOWN'
        with self.assertRaises(c.CatalogueHold):self.valid(value)

    def test_rehashed_unverified_record_rejected(self):
        value=catalogue();check=approved_records(value);value['configurations']['portal']['unit']='other.service'
        with self.assertRaises(c.CatalogueHold):c.bind_catalogue(value,c.digest(value),check)

    def test_missing_idle_scheduler_coverage(self):
        value=catalogue();check=approved_records(value);value['coverage_proofs']['writers_and_activators']='0'*64
        with self.assertRaises(c.CatalogueHold):c.bind_catalogue(value,c.digest(value),check)

    def test_shared_retained_writer_refused(self):
        value=catalogue();value['origins'][0]['retained']=True
        with self.assertRaises(c.CatalogueHold):self.valid(value)

    def test_hardlink_alias_refused(self):
        value=catalogue();other=copy.deepcopy(value['objects'][0]);other.update(id='copy',path='/opt/trading-system/data/copy.db')
        value['objects'].append(other);value['origins'][0]['objects'].append('copy')
        with self.assertRaises(c.CatalogueHold):self.valid(value)

    def test_child_directory_coverage_refused(self):
        value=catalogue();root=copy.deepcopy(value['objects'][0]);root.update(id='root',path='/opt/trading-system/data',kind='DIRECTORY',inode=3,children=[])
        value['objects'].append(root);value['origins'][0]['objects'].append('root')
        with self.assertRaises(c.CatalogueHold):self.valid(value)

    def test_scope_escape_refused(self):
        for path in ('/etc/passwd','/opt/trading-system/../etc/file','/opt/trading-system//bad'):
            value=catalogue();value['objects'][0]['path']=path
            with self.assertRaises(c.CatalogueHold):self.valid(value)

    def test_configuration_missing_object_edges_refused(self):
        value=catalogue();value['configurations']['portal']['data_objects']=[]
        with self.assertRaises(c.CatalogueHold):self.valid(value)

    def test_wrong_effective_unit_writer_edge_refused(self):
        value=catalogue();value['configurations']['portal']['unit']='other.service'
        with self.assertRaises(c.CatalogueHold):self.valid(value)

    def test_configuration_cannot_claim_unknown_writer(self):
        value=catalogue();value['configurations']['portal']['writer_origins']=['unknown']
        with self.assertRaises(c.CatalogueHold):self.valid(value)


class OriginalJournalFixture:
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.root.chmod(0o700)
        self.cat=catalogue();self.inventory=c.digest(self.cat);now=int(time.time())
        self.plan={'action':original.ACTION,'transaction_id':'fixture-original','head':'a'*40,'host':original.HOST,
                   'source_host':original.SOURCE_HOST,'release':original.RELEASE,'issued_at':now-1,'expires_at':now+1000,
                   'independent_review_comment_id':1,'source_hashes':{n:'a'*64 for n in ('migration_transaction.py','production_start.py','stopped_transaction.py','final_materials.py','production_transport.py')},
                   'bindings':{k:self.inventory if k=='writer_inventory' else 'b'*64 for k in ('writer_inventory','protected_inventory','final_manifest_contract','runtime_identity','unit_manifest','business_acceptance_contract','route_contract')},
                   'steps':list(original.STEPS)}
        self.plan_digest=original.digest(self.plan)
        self.journal=original.Journal(self.root,'fixture-original');self.journal.claim(self.plan,self.plan_digest)
        self.root_fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        self.txn_fd=os.open(self.journal.path,os.O_RDONLY|os.O_DIRECTORY)
        identity=lambda fd:[os.fstat(fd).st_dev,os.fstat(fd).st_ino]
        self.binding={'transaction_id':'fixture-original','plan_digest':self.plan_digest,'epoch':7,'writer_inventory_sha256':self.inventory,
                      'extension_manifest_sha256':original.digest(f.extension_manifest()),'root_identity':identity(self.root_fd),'transaction_identity':identity(self.txn_fd),'lock_identity':identity(self.journal.lock.fileno())}
        self.allowed=True;self.paths_valid=True;self.calls=[]
        self.controller=self.make_controller()
        self.req=original.request(self.plan,'inspect_protected',self.plan_digest)

    def tearDown(self):
        os.close(self.root_fd);os.close(self.txn_fd);self.journal.close();self.temp.cleanup()

    def history(self,plan,events):
        return stage_history.verify(original,plan,events)

    def make_controller(self):
        return f.ExistingFdController(self.journal,original,self.root_fd,self.txn_fd,self.binding,
            lambda mode,b:self.allowed and b==self.binding,lambda:self.paths_valid,self.history)

    def receipt(self,req):
        return {'request_digest':original.digest(req),'operation_id':req['operation_id'],'stage':req['stage'],'status':'SUCCEEDED','evidence':'c'*64}

    def dispatch(self,req):
        self.calls.append('dispatch');return self.receipt(req)

    def query(self,req):
        self.calls.append('query');return self.receipt(req)

    def perform(self):
        with patch.object(original,'source_manifest',return_value=self.plan['source_hashes']):
            return self.controller.perform(self.req,self.dispatch,self.query)

class ControllerTests(OriginalJournalFixture, unittest.TestCase):
    def test_extension_change_requires_renewed_exact_binding(self):
        with patch.object(f,'extension_manifest',return_value={}):
            with self.assertRaises(f.ControllerHold):self.perform()
        self.assertEqual(self.calls,[]);self.assertEqual(self.journal.load()[1],[])

    def test_complete_stage_order_and_hash_chain(self):
        previous=self.plan_digest
        with patch.object(original,'source_manifest',return_value=self.plan['source_hashes']):
            for stage in original.STEPS:
                req=original.request(self.plan,stage,previous)
                result=self.controller.perform(req,self.dispatch,self.query)
                previous=original.digest(result)
        self.assertEqual(len(self.calls),len(original.STEPS))
        self.assertEqual(len(self.controller.load()[1]),2*len(original.STEPS))
        self.assertFalse(stage_history.verify(original,self.plan,self.controller.load()[1]+[{'type':'TERMINAL','status':'PRODUCTION_COMPLETE'}]))

    def test_process_restart_pending_intent_is_query_only(self):
        self.journal.append({'type':'INTENT','request':self.req})
        self.journal.close()
        script = '''import os,sys,json
sys.path[:0]=json.loads(sys.argv[1])
import migration_transaction as m,existing_fd_controller as f,stage_history
b=json.loads(sys.argv[3]);j=m.Journal(__import__('pathlib').Path(sys.argv[2]),b['transaction_id'])
r=os.open(sys.argv[2],os.O_RDONLY|os.O_DIRECTORY);t=os.open(j.path,os.O_RDONLY|os.O_DIRECTORY)
c=f.ExistingFdController(j,m,r,t,b,lambda mode,v:v==b,lambda:True,lambda p,e:stage_history.verify(m,p,e))
claim,_,_=c.load();req=m.request(claim['plan'],'inspect_protected',b['plan_digest'])
def no_dispatch(req):raise AssertionError('REPLAY')
def query(req):return {'request_digest':m.digest(req),'operation_id':req['operation_id'],'stage':req['stage'],'status':'SUCCEEDED','evidence':'c'*64}
c.perform(req,no_dispatch,query)
assert len(c.load()[1])==2
j.close();os.close(r);os.close(t)
'''
        imports=[str(Path(__file__).resolve().parent),str(Path(original.__file__).resolve().parent)]
        result=subprocess.run([sys.executable,'-I','-B','-c',script,json.dumps(imports),str(self.root),json.dumps(self.binding)],capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        # Reacquire the SAME original named lock after the old process terminates.
        self.journal=original.Journal(self.root,'fixture-original')

    def test_skipping_first_stage_writes_no_intent(self):
        req=original.request(self.plan,'fence_source',self.plan_digest)
        with patch.object(original,'source_manifest',return_value=self.plan['source_hashes']):
            with self.assertRaises(f.ControllerHold):self.controller.perform(req,self.dispatch,self.query)
        self.assertEqual(self.calls,[]);self.assertEqual(self.journal.load()[1],[])

    def test_wrong_previous_receipt_writes_no_next_intent(self):
        self.perform()
        req=original.request(self.plan,'fence_source','0'*64)
        with patch.object(original,'source_manifest',return_value=self.plan['source_hashes']):
            with self.assertRaises(f.ControllerHold):self.controller.perform(req,self.dispatch,self.query)
        self.assertEqual(self.calls,['dispatch']);self.assertEqual(len(self.journal.load()[1]),2)

    def test_recovered_unknown_cannot_advance(self):
        self.journal.append({'type':'INTENT','request':self.req})
        self.journal.append({'type':'UNKNOWN','operation_id':self.req['operation_id']})
        result=self.perform()
        req=original.request(self.plan,'fence_source',original.digest(result))
        with self.assertRaises(f.ControllerHold):self.controller.perform(req,self.dispatch,self.query)
        self.assertEqual(self.calls,['query'])

    def test_real_original_journal_dispatch_once_then_cache(self):
        result=self.perform();self.assertEqual(self.perform(),result);self.assertEqual(self.calls,['dispatch'])
        self.assertEqual(self.journal.load()[1],self.controller.load()[1])

    def test_prior_intent_never_dispatches(self):
        self.journal.append({'type':'INTENT','request':self.req})
        self.perform();self.assertEqual(self.calls,['query'])

    def test_unknown_query_failure_preserves_no_replay(self):
        self.journal.append({'type':'INTENT','request':self.req})
        with self.assertRaises(f.ControllerHold):self.controller.perform(self.req,self.dispatch,lambda r:None)
        self.assertEqual(self.calls,[]);self.assertEqual(len(self.journal.load()[1]),1)

    def test_revoked_authority_reads_no_journal(self):
        self.allowed=False
        with patch.object(self.controller,'_read',side_effect=AssertionError('unauthorized read')):
            with self.assertRaises(f.ControllerHold):self.controller.load()
        self.assertEqual(self.calls,[])

    def test_revoked_ancestor_binding_writes_nothing(self):
        self.paths_valid=False
        with self.assertRaises(f.ControllerHold):self.perform()
        self.assertEqual(self.journal.load()[1],[])

    def test_replaced_lock_is_not_new_writer(self):
        (self.root/'lock').unlink();(self.root/'lock').write_bytes(b'');(self.root/'lock').chmod(0o600)
        with self.assertRaises(f.ControllerHold):self.perform()
        self.assertEqual(self.calls,[])

    def test_foreign_record_not_overwritten(self):
        (self.journal.path/'0000.json').write_bytes(b'PARTIAL');(self.journal.path/'0000.json').chmod(0o600)
        with self.assertRaises((ValueError,f.ControllerHold)):self.perform()
        self.assertEqual((self.journal.path/'0000.json').read_bytes(),b'PARTIAL')

    def test_dispatch_failure_unknown_and_only_query(self):
        def fail(req):self.calls.append('failed-dispatch');raise TimeoutError()
        with patch.object(original,'source_manifest',return_value=self.plan['source_hashes']):
            with self.assertRaises(f.ControllerHold):self.controller.perform(self.req,fail,self.query)
        self.perform();self.assertEqual(self.calls,['failed-dispatch','query'])

    def test_source_drift_before_intent(self):
        with patch.object(original,'source_manifest',return_value={}):
            with self.assertRaises(f.ControllerHold):self.controller.perform(self.req,self.dispatch,self.query)
        self.assertEqual(self.journal.load()[1],[])

    def test_second_process_cannot_take_original_lock(self):
        script='import fcntl,os,sys\nf=os.open(sys.argv[1],os.O_RDWR)\ntry:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nexcept BlockingIOError:sys.exit(0)\nsys.exit(1)'
        result=subprocess.run([sys.executable,'-I','-B','-c',script,str(self.root/'lock')],capture_output=True)
        self.assertEqual(result.returncode,0)

    def test_partial_event_not_reset(self):
        (self.journal.path/'0000.json').write_bytes(b'{');(self.journal.path/'0000.json').chmod(0o600)
        with self.assertRaises((ValueError,f.ControllerHold)):self.perform()
        self.assertEqual(self.calls,[])


class FixtureBackend:
    """State machine fixture. Does not claim actual systemd or kernel protection."""
    def __init__(self):self.calls=[];self.masked=set();self.stopped=set();self.flags={};self.partial=False
    def mask(self,u):self.calls.append(('mask',u));self.masked.add(u)
    def stop(self,u):self.calls.append(('stop',u));self.stopped.add(u)
    def stopped_and_masked(self,u):return u in self.masked and u in self.stopped
    def freeze(self,obj):
        self.calls.append(('freeze',obj['id']))
        if self.partial:raise OSError('fixture unavailable')
        self.flags[obj['id']]=obj['original_flags']|s.IMMUTABLE
    def get_flags(self,obj):return self.flags.get(obj['id'],obj['original_flags'])
    def exact_directory(self,obj,children):return True


class FenceTests(OriginalJournalFixture, unittest.TestCase):
    def setUp(self):
        super().setUp();self.backend=FixtureBackend();self.stored=None
        self.drain={'inventory_sha256':self.inventory,'epoch':7,'pending':0,'unknown':0,'proof_sha256':'d'*64}
        self.provider=s.SourceFence(self.controller,self.cat,self.inventory,approved_records(self.cat),self.backend,
            lambda inv,epoch:copy.deepcopy(self.drain),self.publish)
        self.fence_req=original.request(self.plan,'fence_source',self.plan_digest)

    def publish(self,proof,query_only=False):
        if self.stored is None and not query_only:self.stored=copy.deepcopy(proof)
        return copy.deepcopy(self.stored)

    def test_masks_and_kernel_checks_before_result(self):
        result=self.provider.dispatch(self.fence_req)
        self.assertEqual(self.backend.calls,[('mask','secure-secrets-portal.service'),('stop','secure-secrets-portal.service'),('freeze','main')])
        self.assertEqual(result['status'],'SUCCEEDED');self.assertIsNotNone(self.stored)

    def test_no_fd_scan_substitution_for_drain(self):
        self.drain['unknown']=1
        with self.assertRaises(s.FenceHold):self.provider.dispatch(self.fence_req)
        self.assertEqual(self.backend.calls,[])

    def test_partial_kernel_fence_query_does_not_reapply(self):
        self.backend.partial=True
        with self.assertRaises(OSError):self.provider.dispatch(self.fence_req)
        calls=list(self.backend.calls)
        with self.assertRaises(s.FenceHold):self.provider.query(self.fence_req)
        self.assertEqual(self.backend.calls,calls);self.assertIsNone(self.stored)

    def test_fence_result_without_durable_proof_rejected(self):
        self.provider.publish=lambda proof,query_only:None
        with self.assertRaises(s.FenceHold):self.provider.dispatch(self.fence_req)

    def test_query_returns_original_durable_evidence(self):
        first=self.provider.dispatch(self.fence_req);calls=list(self.backend.calls)
        second=self.provider.query(self.fence_req)
        self.assertEqual(first,second);self.assertEqual(calls,self.backend.calls)

    def test_retained_finance_writer_is_held(self):
        self.cat['origins'][0]['unit']='finance-collection-sync.service'
        self.cat['configurations']['portal']['unit']='finance-collection-sync.service'
        with self.assertRaises(s.FenceHold):s.SourceFence(self.controller,self.cat,c.digest(self.cat),approved_records(self.cat),self.backend,
            lambda i,e:self.drain,self.publish)


class ProofTests(OriginalJournalFixture,unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.output=os.open(self.root/'original-proof-output',os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
        self.proof=held_proof.HeldProof(self.output,self.controller,lambda:True)
        self.value={'action':'fixture','observed_at':10,'inventory':self.inventory}

    def tearDown(self):
        os.close(self.output);super().tearDown()

    def test_persistent_original_fd_reuse(self):
        first=self.proof(self.value)
        reopened=held_proof.HeldProof(self.output,self.controller,lambda:True)
        self.assertEqual(reopened(dict(self.value,observed_at=20),query_only=True),first)

    def test_query_never_creates_proof(self):
        with self.assertRaises(held_proof.ProofHold):self.proof(self.value,query_only=True)
        self.assertEqual(os.fstat(self.output).st_size,0)

    def test_partial_output_not_overwritten(self):
        os.write(self.output,b'{')
        with self.assertRaises(held_proof.ProofHold):self.proof(self.value)
        self.assertEqual(os.pread(self.output,100,0),b'{')

    def test_different_inventory_not_reused(self):
        self.proof(self.value)
        with self.assertRaises(held_proof.ProofHold):self.proof(dict(self.value,inventory='0'*64))
        self.assertEqual(json.loads(os.pread(self.output,10000,0)),self.value)

    def test_revoked_authority_cannot_write_proof(self):
        self.allowed=False
        with self.assertRaises(f.ControllerHold):self.proof(self.value)
        self.assertEqual(os.fstat(self.output).st_size,0)


class KernelInterfaceTests(unittest.TestCase):
    def setUp(self):
        from types import SimpleNamespace
        for target,value in (('geteuid',0),('uname',SimpleNamespace(nodename=c.SOURCE_HOST))):
            p=patch.object(s.os,target,return_value=value);p.start();self.addCleanup(p.stop)
        class GuardFixture:
            def check(self):return True
            def file_fd(self,path):raise AssertionError('no actual data fd')
            def directory_fd(self,path):raise AssertionError('no actual data directory')
        self.backend=s.LinuxFenceBackend(GuardFixture(),{},lambda:True)

    def test_wrong_host_cannot_reach_syscall(self):
        from types import SimpleNamespace
        with patch.object(s.os,'uname',return_value=SimpleNamespace(nodename='wrong-host')),patch.object(s.subprocess,'run',side_effect=AssertionError('host effect')):
            with self.assertRaises(s.FenceHold):self.backend.mask('secure-secrets-portal.service')

    def test_fixed_systemctl_arguments(self):
        with patch.object(s.subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'',b'')) as call:
            self.backend.mask('secure-secrets-portal.service')
        self.assertEqual(call.call_args.args[0],['/usr/bin/systemctl','mask','--runtime','--','secure-secrets-portal.service'])
        self.assertEqual(call.call_args.kwargs['timeout'],20)

    def test_retained_units_rejected_before_syscall(self):
        for unit in ('windows-interaction-http.service','provider-neutral-domestic-bridge.service','finance-sync.timer','../bad.service','--bad.service'):
            with patch.object(s.subprocess,'run',side_effect=AssertionError('host call')):
                with self.assertRaises(s.FenceHold):self.backend.stop(unit)

    def test_command_unknown_stops_no_fallback(self):
        with patch.object(s.subprocess,'run',side_effect=subprocess.TimeoutExpired('systemctl',20)) as call:
            with self.assertRaises(subprocess.TimeoutExpired):self.backend.stop('secure-secrets-portal.service')
        self.assertEqual(call.call_count,1)

    def test_missing_nonempty_cgroup_binding_held(self):
        text='ActiveState=inactive\nMainPID=0\nControlPID=0\nControlGroup=/system.slice/original\nUnitFileState=masked-runtime\n'
        self.backend.cgroups={'x.service':{'control_group':'/system.slice/original','fds':[]}}
        with patch.object(self.backend,'_ctl',return_value=text):
            with self.assertRaises(s.FenceHold):self.backend.stopped_and_masked('x.service')

    def test_ioctl_failure_not_success_or_retried(self):
        with tempfile.TemporaryFile() as file:
            with patch.object(self.backend,'object_fd',side_effect=lambda obj:os.dup(file.fileno())),patch.object(s.fcntl,'ioctl',side_effect=PermissionError()) as ioctl:
                with self.assertRaises(PermissionError):self.backend.freeze({'original_flags':0})
            self.assertEqual(ioctl.call_count,1)

    def test_ioctl_checks_original_and_observed_flags(self):
        calls=[]
        def ioctl(fd,command,flags,mutate):
            calls.append(command)
            if command==s.GETFLAGS:flags[0]=0 if len(calls)==1 else s.IMMUTABLE
            else:self.assertEqual(flags[0],s.IMMUTABLE)
        with tempfile.TemporaryFile() as file:
            with patch.object(self.backend,'object_fd',side_effect=lambda obj:os.dup(file.fileno())),patch.object(s.fcntl,'ioctl',side_effect=ioctl):
                self.backend.freeze({'original_flags':0})
        self.assertEqual(calls,[s.GETFLAGS,s.SETFLAGS,s.GETFLAGS])


if __name__=='__main__':unittest.main()
