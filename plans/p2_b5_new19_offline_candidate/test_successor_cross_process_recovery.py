"""Offline two-process recovery of original protected intent records."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).parent / 'reused-6825'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).parent / 'successor_controller'))
SOURCE = pathlib.Path(__file__).parent / 'new19-source'
sys.path.insert(0, str(SOURCE))
import pr17_b5_successor_review as c53

CHILD = r'''
import json, os, pathlib, sys
sys.path.insert(0, sys.argv[1]);sys.path.insert(0, sys.argv[3]);sys.path.insert(0, sys.argv[4]);sys.path.insert(0, sys.argv[5])
from pr17_b5_successor_backend import R2HostBackend
from pr17_b5_successor_review import Hold, Transaction
from test_successor_release_gate import fixture_gate, ROOT as fixture_root
import pr17_b5_successor_binder as binder
root=pathlib.Path(sys.argv[2]); bundle=json.loads((root/'bundle.json').read_text())
class Legacy:
 def read(self,path):
  with open(path,'rb') as f:return f.read(),None
class Authority:
 def observe_original_intake_ready(self,request):
  rid=request['request_id']
  if (root/('ready-'+rid)).exists():return {'request_id':rid,'state':'ACCEPTED'}
  raise Hold('INTAKE_READY_NOT_PROVEN')
 def observe_original_success_progress(self,ids,catalog):
  assert catalog==bundle['catalog_sha'] and tuple(ids)==tuple(r['request_id'] for r in bundle['requests'])
  return int((root/'progress').read_text())
spec=binder.verify_spec_bytes((fixture_root/'SUCCESSOR_SPEC.json').read_bytes())
b=R2HostBackend(legacy_io=Legacy(),spec=spec,source_blobs={},observed_bytes={},
                authority=Authority())
b.job=str(root);b.expected_ids=tuple(r['request_id'] for r in bundle['requests'])
b.release_gate=fixture_gate(b.spec,'recover')
try:
 observed=Transaction.recover_intake_readonly(b,bundle)
 if observed['state']=='B5_HTTP_AWAITING_PROVENANCE_NO_REPLAY':
  # Fixture facts model the separately checked activation marker; this child
  # tests the phase transition, not the UK protected activation reader.
  b.recovered_from_protected=True;b.activation_committed=True;b.bundle=bundle
  bundle['files']={name:b'' for name in __import__('pr17_b5_successor_review').CONFIGS+
                   __import__('pr17_b5_successor_review').SLOTS}
  tx=Transaction(spec,bundle,b);tx.stage='UNKNOWN'
  observed['resume']=tx.resume_recovered_b5_http_wait()
  observed['stage']=tx.stage
 print(json.dumps(observed,sort_keys=True))
except BaseException as exc:
 print(json.dumps({'state':'HOLD','code':str(exc)},sort_keys=True));sys.exit(2)
'''

class CrossProcessRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)
        self.bundle={'batch_id':'batch-20261024-fixed','catalog_sha':'a'*64,
                     'generation_seal':'b'*64,
                     'window_start':1792800000,'window_end':1792803600,
                     'requests':[{'request_id':'l2-b5-batch-20261024-fixed-%02d'%i,
                                  'arguments':{'object_ref':'b5-material-%02d'%i}}
                                 for i in range(1,20)]}
        self.write('bundle.json',json.dumps(self.bundle).encode())
        self.write('reservation.json',c53.canon({'batch':self.bundle['batch_id'],
            'ids':[r['request_id'] for r in self.bundle['requests']],
            'catalog_sha256':self.bundle['catalog_sha'],'release':c53.COMMIT,
            'request_set_sha256':c53.sha(c53.canon(self.bundle['requests'])),
            'generation_seal':self.bundle['generation_seal'],
            'window_start':self.bundle['window_start'],
            'window_end':self.bundle['window_end'],
            'state':'RESERVED_NOT_SUBMITTED'})+b'\n')
        self.write('window-open.json',c53.canon({'catalog_sha256':self.bundle['catalog_sha'],
            'window_start':self.bundle['window_start'],'window_end':self.bundle['window_end'],
            'state':'ACTIVE_NOT_DELIVERED'})+b'\n')
        self.write('progress',b'0')
        self.write('checkpoint-001.json',c53.canon({'schema':1,'sequence':1,
            'phase':'INTAKE_19','release_commit':c53.COMMIT,'project':c53.PROJ})+b'\n')

    def write(self,name,data):
        with (self.root/name).open('xb') as f:
            f.write(data);f.flush();os.fsync(f.fileno())

    def intent(self,r,sent=True):
        from production.cloud_connection.queue import canonical
        rid=r['request_id'];digest=c53.sha(canonical(r).encode())
        self.write('intake-'+rid+'.intent.json',c53.canon({'request_id':rid,
            'request_sha256':digest,'catalog_sha256':self.bundle['catalog_sha'],
            'actor_id':332398908,'state':'POST_MAY_HAVE_OCCURRED_NO_REPOST'}))
        if sent:self.write('intake-'+rid+'.sent.json',c53.canon({'request_id':rid,
            'request_sha256':digest,'comment_id':101,'state':'SENT_NOT_ACCEPTED'}))
        return rid

    def child(self):
        proc=subprocess.run([sys.executable,'-B','-c',CHILD,str(ROOT),str(self.root),str(SOURCE),str(pathlib.Path(__file__).parent / 'successor_controller'),str(pathlib.Path(__file__).parent)],
            capture_output=True,text=True,timeout=15)
        return proc,json.loads(proc.stdout)

    def test_two_fresh_processes_reconcile_without_post(self):
        ids=[]
        for r in self.bundle['requests']:
            ids.append(self.intent(r))
            self.write('ready-'+ids[-1],b'1')
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()}
        first,a=self.child();second,b=self.child()
        self.assertEqual((first.returncode,second.returncode),(0,0))
        self.assertEqual(a,b)
        self.assertEqual((a['state'],a['ready_count'],a['mutation_allowed']),
                         ('WAIT_ORIGINAL_SUCCESS_NO_REPOST',19,False))
        self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in self.root.iterdir()})

    def test_crash_after_intent_reopens_unknown_without_repost(self):
        r=self.bundle['requests'][0];rid=r['request_id']
        writer_code='''import hashlib,json,os,pathlib,signal,sys
root=pathlib.Path(sys.argv[1]);r=json.loads(sys.argv[2]);catalog=sys.argv[3]
canonical=json.dumps(r,sort_keys=True,separators=(',',':'),allow_nan=False)
digest=hashlib.sha256(canonical.encode()).hexdigest()
data={'request_id':r['request_id'],'request_sha256':digest,
 'catalog_sha256':catalog,'actor_id':332398908,
 'state':'POST_MAY_HAVE_OCCURRED_NO_REPOST'}
with (root/('intake-'+r['request_id']+'.intent.json')).open('xb') as f:
 f.write(json.dumps(data,sort_keys=True,separators=(',',':')).encode());f.flush();os.fsync(f.fileno())
os.kill(os.getpid(),signal.SIGKILL)
'''
        writer=subprocess.Popen([sys.executable,'-B','-c',writer_code,str(self.root),
            json.dumps(r),self.bundle['catalog_sha']])
        self.assertNotEqual(writer.wait(timeout=10),0)
        proc,result=self.child()
        self.assertEqual(proc.returncode,0)
        self.assertEqual(result['state'],'UNKNOWN_OR_PENDING_NO_REPOST')
        self.assertFalse(result['mutation_allowed'])
        self.assertFalse((self.root/('intake-'+rid+'.sent.json')).exists())

    def test_tampered_intent_holds(self):
        r=self.bundle['requests'][0];rid=self.intent(r)
        p=self.root/('intake-'+rid+'.intent.json')
        data=json.loads(p.read_text());data['actor_id']=1;p.write_text(json.dumps(data))
        proc,result=self.child()
        self.assertEqual(proc.returncode,2)
        self.assertEqual(result['code'],'RECOVERY_INTENT_BINDING')

    def test_checkpoint_gap_rejected_without_post(self):
        self.write('checkpoint-003.json',c53.canon({'schema':1,'sequence':3,
            'phase':'WAIT_19_SUCCESS','release_commit':c53.COMMIT,'project':c53.PROJ}))
        proc,result=self.child()
        self.assertEqual(proc.returncode,2)
        self.assertEqual(result['code'],'RECOVERY_CHECKPOINT_GAP')

    def test_all_success_observation_still_forbids_mutation(self):
        for r in self.bundle['requests']:
            rid=self.intent(r);self.write('ready-'+rid,b'1')
        (self.root/'progress').write_text('19')
        proc,result=self.child()
        self.assertEqual(proc.returncode,0)
        self.assertEqual((result['state'],result['success_count'],result['mutation_allowed']),
                         ('SUCCESS_OBSERVED_READONLY',19,False))

    def test_two_processes_wait_for_b5_http_after_custody_without_replay(self):
        for r in self.bundle['requests']:
            rid=self.intent(r);self.write('ready-'+rid,b'1')
        (self.root/'progress').write_text('19')
        for number,phase in enumerate(('WAIT_19_SUCCESS','CHECK_19_SUCCESS',
                         'ONE_CUSTODY','READY_FOR_B5_HTTP_NOT_RECEIVED'),2):
            self.write('checkpoint-%03d.json'%number,c53.canon({
                'schema':1,'sequence':number,'phase':phase,
                'release_commit':c53.COMMIT,'project':c53.PROJ})+b'\n')
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.iterdir()}
        first,a=self.child();second,b=self.child()
        self.assertEqual((first.returncode,second.returncode),(0,0))
        self.assertEqual(a,b)
        self.assertEqual((a['state'],a['stage'],a['resume']['mutation_allowed']),
            ('B5_HTTP_AWAITING_PROVENANCE_NO_REPLAY',
             'READY_FOR_B5_HTTP_NOT_RECEIVED',False))
        self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in self.root.iterdir()})
        (self.root/'progress').write_text('18')
        failed,result=self.child()
        self.assertEqual((failed.returncode,result['code']),
                         (2,'RECOVERY_CUSTODY_SUCCESS_CHANGED'))

    def test_close_attempt_checkpoint_holds_across_fresh_process(self):
        for r in self.bundle['requests']:
            rid=self.intent(r);self.write('ready-'+rid,b'1')
        (self.root/'progress').write_text('19')
        for number,phase in enumerate(('WAIT_19_SUCCESS','CHECK_19_SUCCESS',
                         'ONE_CUSTODY','READY_FOR_B5_HTTP_NOT_RECEIVED',
                         'CLOSE_ATTEMPT'),2):
            self.write('checkpoint-%03d.json'%number,c53.canon({
                'schema':1,'sequence':number,'phase':phase,
                'release_commit':c53.COMMIT,'project':c53.PROJ})+b'\n')
        first,a=self.child();second,b=self.child()
        self.assertEqual((first.returncode,second.returncode),(2,2))
        self.assertEqual((a['code'],b['code']),
                         ('RECOVERY_CHECKPOINT_PHASE',
                          'RECOVERY_CHECKPOINT_PHASE'))

    def test_failure_checkpoint_persists_hold_across_fresh_process(self):
        for r in self.bundle['requests']:
            rid=self.intent(r);self.write('ready-'+rid,b'1')
        (self.root/'progress').write_text('19')
        for number,phase in enumerate(('WAIT_19_SUCCESS','CHECK_19_SUCCESS',
                         'ONE_CUSTODY','READY_FOR_B5_HTTP_NOT_RECEIVED',
                         'FAILURE_READY_FOR_B5_HTTP_NOT_RECEIVED'),2):
            self.write('checkpoint-%03d.json'%number,c53.canon({
                'schema':1,'sequence':number,'phase':phase,
                'release_commit':c53.COMMIT,'project':c53.PROJ})+b'\n')
        first,a=self.child();second,b=self.child()
        self.assertEqual((first.returncode,second.returncode),(2,2))
        self.assertEqual((a['code'],b['code']),
                         ('RECOVERY_CHECKPOINT_PHASE',
                          'RECOVERY_CHECKPOINT_PHASE'))

    def test_same_ids_changed_request_rejected(self):
        self.bundle['requests'][0]['arguments']['object_ref']='other'
        (self.root/'bundle.json').write_text(json.dumps(self.bundle))
        proc,result=self.child()
        self.assertEqual(proc.returncode,2)
        self.assertEqual(result['code'],'RECOVERY_RESERVATION_BINDING')

    def test_unknown_never_enters_custody_continuation(self):
        class Backend:
            recovered_from_protected=True
            activation_committed=True
            def recover_intake_readonly(self,bundle):
                return {'state':'UNKNOWN_OR_PENDING_NO_REPOST',
                        'ready_count':18,'mutation_allowed':False}
        tx=c53.Transaction.__new__(c53.Transaction)
        tx.b=Backend();tx.bundle=self.bundle;tx.stage='NEW'
        tx.continue_after_original_ready=lambda: (_ for _ in ()).throw(
            AssertionError('CUSTODY_WAS_ENTERED'))
        with self.assertRaisesRegex(c53.Hold,'RECOVERY_CUSTODY_NOT_PROVEN_NO_RETRY'):
            tx.resume_recovered_custody()

if __name__=='__main__':
    unittest.main(verbosity=2)
