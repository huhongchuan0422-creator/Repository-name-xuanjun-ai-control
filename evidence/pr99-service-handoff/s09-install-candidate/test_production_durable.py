"""Exercise the actual production start implementation with host boundaries mocked.
Filesystem intent/unit/receipt bytes are real temporary files; systemd/network are fake.
"""
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import production_start as m


class DurableTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.state=self.root/'state';self.units=self.root/'units';self.units.mkdir()
  self.permit=self.root/'permit';self.permit.write_bytes(b'fixture-permit')
  self.payload=m.units('xuanjun-s07');self.active={n:False for n in self.payload};self.calls=[]
  self.p={'unit_hashes':{n:m.sha(b) for n,b in self.payload.items()},'source_writer_fence_receipt_sha256':'a'*64,'expires_at':9999999999}
  self.stack=ExitStack();self.addCleanup(self.stack.close)
  for name,value in [('STATE',self.state),('SYSTEMD',self.units),('PERMIT',self.permit),
                     ('admit',lambda:(self.p,self.payload)),('read',lambda p,*a,**k:Path(p).read_bytes()),
                     ('ports_available',lambda:True),('verify_units',lambda p:None),
                     ('ctl',self.ctl),('health',self.health)]:
   self.stack.enter_context(patch.object(m,name,value))
 def ctl(self,*args):
  self.calls.append(args)
  if args[0]=='show':return 'ActiveState='+('active' if self.active[args[1]] else 'inactive')+'\nMainPID='+('123' if self.active[args[1]] else '0')+'\n'
  if args[0]=='start':self.active[args[1]]=True
  if args[0]=='stop':self.active[args[1]]=False
  return ''
 def health(self,port):return 200 if all(self.active.values()) else None
 def effects(self):
  return [json.loads(p.read_text()) for p in sorted(self.state.glob('effect-*.intent.json'))]
 def test_actual_start_files_and_durable_effects(self):
  result=m.start()
  self.assertEqual(result['status'],'THREE_APPS_STARTED_NO_TRAFFIC_CUTOVER')
  self.assertTrue(all(self.active.values()));self.assertFalse(result['production_cutover'])
  self.assertEqual(len(self.effects()),7)
  self.assertEqual(len(list(self.state.glob('effect-*.result.json'))),7)
  for n,b in self.payload.items():self.assertEqual((self.units/n).read_bytes(),b)
  self.assertTrue((self.state/'intent.json').exists());self.assertTrue((self.state/'receipt.json').exists())
 def query(self):
  from types import SimpleNamespace
  real=Path.lstat
  def lstat(path,*args,**kwargs):
   value=real(path,*args,**kwargs)
   if path==self.state:
    fields={n:getattr(value,n) for n in dir(value) if n.startswith('st_')};fields['st_uid']=0
    return SimpleNamespace(**fields)
   return value
  with patch.object(m.os,'geteuid',lambda:0),patch.object(m.os,'uname',lambda:SimpleNamespace(nodename=m.HOST)),patch.object(Path,'lstat',lstat):
   return m.query_only()
 def test_query_actual_records_never_mutates_services(self):
  m.start();before=len(self.calls);result=self.query()
  self.assertEqual(result['status'],'OBSERVED_ONLY_NO_RESUME')
  self.assertEqual(len(result['operations']),7)
  self.assertTrue(all(c[0]=='show' for c in self.calls[before:]))
 def test_query_pending_intent_is_unknown(self):
  real=self.ctl
  def ctl(*args):
   if args[0]=='start':raise subprocess.TimeoutExpired('systemctl',20)
   return real(*args)
  with patch.object(m,'ctl',ctl),self.assertRaises(m.EffectUnknown):m.start()
  before=len(self.calls);result=self.query()
  self.assertEqual(result['status'],'UNKNOWN_QUERY_ONLY_NO_REPLAY')
  self.assertTrue(all(c[0]=='show' for c in self.calls[before:]))
 def test_query_foreign_unit_refuses_observation_success(self):
  m.start();(self.units/next(iter(self.payload))).write_bytes(b'foreign')
  with self.assertRaisesRegex(RuntimeError,'QUERY_FOREIGN_UNIT'):self.query()
 def test_query_source_drift_rejected(self):
  m.start();p=self.state/'intent.json';v=json.loads(p.read_text());v['source_sha256']='f'*64;p.write_bytes(m.canonical(v))
  with self.assertRaisesRegex(RuntimeError,'QUERY_SOURCE_DRIFT'):self.query()
 def test_query_unknown_effect_name_rejected_before_systemctl(self):
  m.start();before=len(self.calls);p=self.state/'effect-0000.intent.json'
  p.write_bytes(m.canonical({'operation':'start:foreign.service'}))
  with self.assertRaisesRegex(RuntimeError,'OPERATION_SEMANTIC_SEQUENCE'):self.query()
  self.assertEqual(len(self.calls),before)
 def test_query_orphan_result_rejected(self):
  m.start();(self.state/'effect-9999.result.json').write_bytes(m.canonical({'status':'SUCCEEDED'}))
  with self.assertRaisesRegex(RuntimeError,'ORPHAN_OPERATION_RESULT'):self.query()
 def test_query_extra_intent_fields_rejected(self):
  m.start();p=self.state/'effect-0000.intent.json';r=json.loads(p.read_text());r['private']='do not return';p.write_bytes(m.canonical(r))
  with self.assertRaisesRegex(RuntimeError,'OPERATION_INTENT_SCHEMA'):self.query()
 def test_query_forward_after_failed_result_rejected(self):
  m.start();p=self.state/'effect-0000.result.json';p.write_bytes(m.canonical({'status':'FAILED'}))
  with self.assertRaisesRegex(RuntimeError,'OPERATION_AFTER_UNRESOLVED'):self.query()
 def test_query_complete_known_rollback_is_valid(self):
  real=self.ctl
  def ctl(*args):
   if args[0]=='start':raise m.KnownEffectFailure('SYSTEMCTL_FAILED')
   return real(*args)
  with patch.object(m,'ctl',ctl),self.assertRaises(m.KnownEffectFailure):m.start()
  result=self.query();self.assertEqual(result['status'],'OBSERVED_ONLY_NO_RESUME')
  self.assertEqual(sum(r['operation'].startswith('stop:') for r in result['operations']),3)
 def test_rollback_after_unknown_forward_rejected(self):
  rows=[{'operation':'create:'+next(iter(self.payload)),'status':'UNKNOWN'},
        {'operation':'rollback-owned','status':'UNKNOWN'}]
  with self.assertRaisesRegex(RuntimeError,'ROLLBACK_AFTER_UNKNOWN'):m.validate_effect_sequence(rows,self.payload)
 def test_rollback_child_order_and_claimed_success_rejected(self):
  names=list(self.payload);prefix=[{'operation':'create:'+n,'status':'SUCCEEDED'} for n in names]
  rows=prefix+[{'operation':'rollback-owned','status':'SUCCEEDED'},{'operation':'stop:'+names[1],'status':'SUCCEEDED'}]
  with self.assertRaisesRegex(RuntimeError,'ROLLBACK_OPERATION_SEQUENCE'):m.validate_effect_sequence(rows,self.payload)
  rows=prefix+[{'operation':'rollback-owned','status':'SUCCEEDED'}]
  with self.assertRaisesRegex(RuntimeError,'ROLLBACK_RESULT_CONFLICT'):m.validate_effect_sequence(rows,self.payload)
 def test_actual_state_replay_rejected(self):
  m.start();before=len(self.calls)
  with self.assertRaises(FileExistsError):m.start()
  self.assertEqual(len(self.calls),before)
 def test_start_timeout_keeps_unknown_without_compensating_stop(self):
  real=self.ctl
  def ctl(*args):
   if args[0]=='start':raise subprocess.TimeoutExpired('systemctl',20)
   return real(*args)
  with patch.object(m,'ctl',ctl),self.assertRaises(m.EffectUnknown):m.start()
  self.assertFalse(any(c[0]=='stop' for c in self.calls))
  self.assertEqual(self.effects()[-1]['operation'],'start:'+next(iter(self.payload)))
  self.assertFalse((self.state/'effect-0004.result.json').exists())
  self.assertEqual(json.loads((self.state/'failure.json').read_text())['status'],'EFFECT_UNKNOWN_QUERY_ONLY_NO_REPLAY')
 def test_known_start_failure_journals_owned_stop_actions(self):
  real=self.ctl
  def ctl(*args):
   if args[0]=='start':raise m.KnownEffectFailure('SYSTEMCTL_FAILED')
   return real(*args)
  with patch.object(m,'ctl',ctl),self.assertRaises(m.KnownEffectFailure):m.start()
  self.assertEqual(sum(c[0]=='stop' for c in self.calls),3)
  ops=[e['operation'] for e in self.effects()]
  self.assertEqual(sum(x.startswith('stop:') for x in ops),3)
  self.assertEqual(json.loads((self.state/'failure.json').read_text())['status'],'OWNED_APPS_STOPPED_DATA_PRESERVED')
 def test_partial_unit_write_is_unknown_preserves_bytes(self):
  real=m.create;target=self.units/next(iter(self.payload))
  def create(path,data,*args):
   real(path,data,*args)
   if Path(path)==target:raise OSError('fsync uncertain')
  with patch.object(m,'create',create),self.assertRaises(m.EffectUnknown):m.start()
  self.assertTrue(target.exists());self.assertFalse(any(c[0]=='stop' for c in self.calls))
  self.assertFalse((self.state/'effect-0000.result.json').exists())
 def test_result_write_failure_after_start_is_unknown(self):
  real=m.create
  def create(path,data,*args):
   if Path(path)==self.state/'effect-0004.result.json':raise OSError('disk full')
   return real(path,data,*args)
  with patch.object(m,'create',create),self.assertRaises(m.EffectUnknown):m.start()
  self.assertTrue(self.active[next(iter(self.payload))]);self.assertFalse(any(c[0]=='stop' for c in self.calls))
 def test_non_http_occupied_port_blocks_before_unit_write(self):
  with patch.object(m,'ports_available',return_value=False),self.assertRaisesRegex(RuntimeError,'PORT_ALREADY_OCCUPIED'):m.start()
  self.assertEqual(list(self.units.iterdir()),[])
 def test_supervision_failure_rolls_back_without_business_acceptance(self):
  ticks=iter([0,31])
  with patch.object(m.time,'monotonic',lambda:next(ticks)),self.assertRaisesRegex(RuntimeError,'SUPERVISION_FAILED'):m.start()
  self.assertFalse(any(self.active.values()));self.assertEqual(sum(c[0]=='stop' for c in self.calls),3)
 def test_foreign_unit_during_rollback_not_stopped(self):
  real=self.ctl
  def ctl(*args):
   if args[0]=='start':
    (self.units/next(iter(self.payload))).write_bytes(b'foreign')
    raise m.KnownEffectFailure('SYSTEMCTL_FAILED')
   return real(*args)
  with patch.object(m,'ctl',ctl),self.assertRaises(m.KnownEffectFailure):m.start()
  self.assertFalse(any(c[0]=='stop' for c in self.calls))
  self.assertEqual(json.loads((self.state/'failure.json').read_text())['status'],'ROLLBACK_UNKNOWN_PRESERVE_NO_RETRY')

if __name__=='__main__':unittest.main()
