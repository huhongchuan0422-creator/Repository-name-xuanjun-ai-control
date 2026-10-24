"""Real file journal and original transport with isolated Docker observations.

Only original Docker subprocess/host name/remote health are synthetic; no site
execution. The journal, fsync/locks/checkpoints and coordinator run for real.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
import test_community_preview_release_plan as fixtures
import test_community_preview_upgrade as oldfixture
from scripts import community_preview_release_plan as plan
from scripts import community_preview_update_checkpoint as u


class Checkpoints(unittest.TestCase):
    def setUp(self):
        self.owner_patch=patch.object(u,'OWNER_UID',os.getuid());self.owner_patch.start();self.addCleanup(self.owner_patch.stop)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.parent_patch=patch.object(u,'JOURNAL_PARENT',self.tmp.name);self.parent_patch.start();self.addCleanup(self.parent_patch.stop)
        self.parent=os.open(self.tmp.name,os.O_RDONLY|os.O_DIRECTORY);self.addCleanup(os.close,self.parent)
        self.p=plan.prepare(fixtures.source(),fixtures.current(),fixtures.image())
        self.j=u.Journal(self.parent,self.p);self.addCleanup(self.j.close)
        self.old=True;self.new=None;self.calls=[];self.now=1000.25
        def inspect(cid):
            if cid==self.p['current']['container_id']:return oldfixture.info(self.p['current']['image_id'],cid,self.old)
            if cid=='9'*64 and self.new is not None:return oldfixture.info(self.p['image']['image_id'],cid,self.new)
            raise u.Hold('UNKNOWN_SYNTHETIC_CONTAINER')
        def mutate(argv,timeout):
            self.calls.append(list(argv));action=argv[3]
            if action=='stop':
                if argv[-1]==self.p['current']['container_id']:self.old=False
                else:self.new=False
            elif action=='start':self.old=True
            elif action=='run':self.new=True;return '9'*64
            return ''
        self.addCleanup(patch.stopall)
        patch.object(u.original,'inspect',side_effect=inspect).start()
        patch.object(u.original,'mutate',side_effect=mutate).start()
        def command(argv):
            if argv[3:5]==['image','inspect']:
                return '\n'.join(json.dumps(v) for v in (self.p['image']['image_id'],self.p['source']['source_sha'],'10001:1008'))
            return plan.NAME+'\n'
        patch.object(u.original,'command',side_effect=command).start()
        patch.object(u.os,'uname',return_value=Mock(nodename=plan.HOST)).start()
        patch.object(u.os,'getuid',return_value=0).start();patch.object(u.os,'geteuid',return_value=0).start()
        self.t=u.OriginalTransport(self.bindings,self.health)
    def bindings(self):return dict(self.p['current'],running=self.old)
    def health(self):
        return dict(http_status=200,url=plan.URL,status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
            runtime_source_sha=self.p['source']['source_sha'],version_source='IMAGE_BUILD_STAMP',observed_at=1000)
    def update(self,enabled=True,clock=None):return u.Update(self.j,self.t,execution_enabled=enabled,clock=clock or (lambda:self.now))
    def test_default_disabled_zero_transport_actions(self):
        with self.assertRaisesRegex(u.Hold,'DISABLED'):u.Update(self.j,self.t).run()
        self.assertEqual(self.calls,[])
    def test_real_fsync_journal_serial_success_reopen_and_no_replay(self):
        r=self.update().run();self.assertEqual(r['phase'],'COMMITTED');self.assertFalse(self.old);self.assertTrue(self.new)
        self.j.close();self.j=u.Journal(self.parent,self.p);self.addCleanup(self.j.close)
        before=len(self.calls)
        with self.assertRaises(u.Hold):self.update().run()
        self.assertEqual(len(self.calls),before)
    def test_known_health_failure_then_restart_and_safe_serial_recovery(self):
        self.t.health=lambda:dict(self.health(),status='NOT_READY')
        with self.assertRaisesRegex(u.Hold,'RECOVERY_REQUIRED'):self.update().run()
        self.j.close();self.j=u.Journal(self.parent,self.p);self.addCleanup(self.j.close)
        self.t.health=self.health;self.assertEqual(self.update().recover()['phase'],'ROLLED_BACK_PREVIEW_HOLD')
        self.assertFalse(self.new);self.assertTrue(self.old)
        stops=[i for i,a in enumerate(self.calls) if a[3]=='stop' and a[-1]=='9'*64]
        starts=[i for i,a in enumerate(self.calls) if a[3]=='start']
        self.assertLess(stops[-1],starts[-1])
    def test_timeout_after_run_intent_persists_unknown_and_never_restores_old(self):
        original=u.original.mutate.side_effect
        def timeout(argv,seconds):
            if argv[3]=='run':raise u.original.Unknown('TIMEOUT')
            return original(argv,seconds)
        u.original.mutate.side_effect=timeout
        with self.assertRaises(u.Hold):self.update().run()
        self.assertEqual(self.j.state['phase'],'HOLD_UNKNOWN_INSPECT_SAME_ATTEMPT')
        before=len(self.calls)
        with self.assertRaises(u.Hold):self.update().recover()
        self.assertEqual(len(self.calls),before)
    def test_unknown_health_transport_not_reclassified_known_failure(self):
        self.t.health=lambda:(_ for _ in ()).throw(TimeoutError())
        with self.assertRaises(u.Hold):self.update().run()
        self.assertEqual(self.j.state['phase'],'HOLD_UNKNOWN_INSPECT_SAME_ATTEMPT')
        with self.assertRaises(u.Hold):self.update().recover()
    def test_binding_and_time_rechecked_after_checkpoint_before_action(self):
        write=self.j.write
        for change in ('expiry','binding'):
            def publish(*args,**kwargs):
                write(*args,**kwargs)
                if change=='expiry':self.now=1601
                else:self.t.bindings=lambda:dict(self.bindings(),routing_sha256='0'*64)
            with patch.object(self.j,'write',side_effect=publish):
                with self.assertRaises(u.Hold):self.update().run()
            self.assertEqual(self.calls,[])
            # The same test attempt is reset only inside this isolated fixture.
            self.now=1000.25;self.t.bindings=self.bindings;write('PREPARED')
    def test_real_default_float_clock_valid_bool_nonfinite_and_backwards_denied(self):
        live=int(time.time());self.t.bindings=lambda:dict(self.bindings(),observed_at=live)
        self.assertIsInstance(u.Update(self.j,self.t,execution_enabled=True).guard(),int)
        for value in (True,float('nan'),float('inf')):
            with self.assertRaises(u.Hold):self.update(clock=lambda:value).guard()
        values=iter([live+.5,live+.25]);v=self.update(clock=lambda:next(values));v.guard()
        with self.assertRaises(u.Hold):v.guard()
    def test_new_stop_unknown_cannot_start_old(self):
        self.t.health=lambda:dict(self.health(),status='NOT_READY')
        with self.assertRaises(u.Hold):self.update().run()
        u.original.mutate.side_effect=u.original.Unknown('STOP_UNKNOWN')
        with self.assertRaises(u.Hold):self.update().recover()
        self.assertFalse(any(a[3]=='start' for a in self.calls))
        self.assertEqual(self.j.state['phase'],'HOLD_UNKNOWN_INSPECT_SAME_ATTEMPT')
    def test_global_real_lock_excludes_independent_process(self):
        code="from scripts import community_preview_update_checkpoint as u;import json,os,sys;u.OWNER_UID=os.getuid();u.JOURNAL_PARENT=os.readlink('/proc/self/fd/'+sys.argv[1]);u.Journal(int(sys.argv[1]),json.loads(sys.argv[2]))"
        r=subprocess.run([sys.executable,'-B','-c',code,str(self.parent),json.dumps(self.p)],pass_fds=(self.parent,),capture_output=True,timeout=5)
        self.assertNotEqual(r.returncode,0)
        self.assertIn(b'BlockingIOError',r.stderr)
    def test_partial_atomic_file_and_foreign_attempt_remain_hold(self):
        self.j.close();d=Path(self.tmp.name)/self.p['attempt'];(d/'checkpoint.tmp').write_text('partial')
        with self.assertRaises(u.Hold):u.Journal(self.parent,self.p)
        (d/'checkpoint.tmp').unlink()
        c=fixtures.current();c['container_id']='8'*64;other=plan.prepare(fixtures.source(),c,fixtures.image())
        with self.assertRaisesRegex(u.Hold,'OTHER_ATTEMPT'):u.Journal(self.parent,other)
    def test_symlink_and_world_readable_checkpoint_denied(self):
        self.j.close();f=Path(self.tmp.name)/self.p['attempt']/'checkpoint.json';f.chmod(0o644)
        with self.assertRaises(u.Hold):u.Journal(self.parent,self.p)
        f.unlink();f.symlink_to('/etc/passwd')
        with self.assertRaises(OSError):u.Journal(self.parent,self.p)
    def test_actual_dispatch_source_and_push_evidence_are_separate(self):
        source=fixtures.source();source['run_id']=40059478387;source['push_evidence_run_id']=40058542631
        image=fixtures.image();image['run_id']=40059478387
        p=plan.prepare(source,fixtures.current(),image)
        self.assertEqual(p['manual_preview']['preview_evidence_run_id'],'40058542631')
        self.assertEqual(p['image']['run_id'],40059478387)
    def test_partial_fsync_poison_stops_same_object_and_reopen(self):
        with patch.object(u.os,'fsync',side_effect=OSError('SYNTHETIC FSYNC')):
            with self.assertRaises(OSError):self.update().run()
        with self.assertRaises(u.Hold):self.update().run()
        self.assertEqual(self.calls,[])
        self.j.close()
        with self.assertRaises(u.Hold):u.Journal(self.parent,self.p)
    def test_wrong_thread_or_nonroot_never_calls_transport(self):
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            with self.assertRaises(u.Hold):pool.submit(self.update().run).result()
        with patch.object(u.os,'geteuid',return_value=1000):
            with self.assertRaises(u.Hold):self.update().run()
        self.assertEqual(self.calls,[])
    def test_checkpoint_history_is_append_only_and_preserved(self):
        self.update().run();directory=Path(self.tmp.name)/self.p['attempt']
        records=sorted(directory.glob('event-*.json'))
        self.assertEqual(len(records),self.j.state['sequence'])
        self.assertEqual(json.loads(records[0].read_text())['phase'],'PREPARED')
        self.assertEqual(json.loads(records[-1].read_text())['phase'],'COMMITTED')
    def test_absent_wrong_loaded_image_or_colliding_recovery_name_zero_mutation(self):
        for result in ('UNKNOWN',json.dumps(self.p['image']['image_id'])+'\n'+json.dumps('WRONG')+'\n'+json.dumps('10001:1008')):
            with patch.object(u.original,'command',return_value=result):
                with self.assertRaises(u.Hold):self.update().run()
            self.assertEqual(self.calls,[])
        original=u.original.command.side_effect
        def collide(argv):
            return original(argv) if argv[3:5]==['image','inspect'] else self.p['rollback_name']+'\n'
        with patch.object(u.original,'command',side_effect=collide):
            with self.assertRaises(u.Hold):self.update().run()
        self.assertEqual(self.calls,[])
    def test_missing_or_stale_runtime_health_cannot_become_recovery_permission(self):
        self.t.health=lambda:dict(self.health(),runtime_source_sha=None)
        with self.assertRaisesRegex(u.Hold,'HEALTH_EVIDENCE_UNKNOWN'):self.update().run()
        self.assertEqual(self.j.state['phase'],'HOLD_UNKNOWN_INSPECT_SAME_ATTEMPT')
        before=len(self.calls)
        with self.assertRaises(u.Hold):self.update().recover()
        self.assertEqual(len(self.calls),before)
