"""Model PID1 stop-post; real private files, model service/cgroup lifecycle."""
import copy
import json
import os
import unittest

from gate_common import GateError,canonical_bytes
from korea.phase_c import lifecycle as live,security,stop_guard
from korea.phase_c import test_lifecycle as fixtures


@unittest.skipUnless(os.geteuid()==0,'Root-owned fixtures')
class StopGuardTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.LifecycleTests.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.LifecycleTests.tearDownClass.__func__)
    make_plan=fixtures.LifecycleTests.make_plan
    baseline=fixtures.LifecycleTests.baseline
    set_pin=fixtures.LifecycleTests.set_pin
    setUp=fixtures.LifecycleTests.setUp
    run_live=fixtures.LifecycleTests.run_live
    receipt=fixtures.LifecycleTests.receipt
    def simulate_loss(self):
        # Model a crash after the durable start flag; NOT a real PID1 invocation.
        work=self.ctx.path(live.WORK);work.mkdir(mode=0o700)
        for name,data in (('consumed-approval.json',self.ctx.path(live.PIN).read_bytes()),
                          ('plan.json',self.path.read_bytes()),
                          ('temporary-identities.json',canonical_bytes({n:list(v) for n,v in self.ctx.temporary_objects(self.cfg).items()}))):
            security.write_once(work/name,data)
        receipt=dict(action=live.ACTION,approval_comment_id=1234567,status='OBSERVING',start_attempted=True,
                     temporary_quarantined=False,retry_allowed=False,writer_enabled=False)
        security.write_once(work/'receipt.json',canonical_bytes(receipt))
        security.write_once(self.ctx.path(self.cfg['admission_path']),canonical_bytes(self.liveplan['signed_admission']),mode=0o444)
        self.ctx.started=True
        return work
    def test_missing_attempt_has_no_stop_or_credential_action(self):
        result=stop_guard.finalize(self.ctx)
        self.assertEqual(result['status'],'NO_CONSUMED_ATTEMPT_NO_ACTION')
        self.assertFalse(self.ctx.stopped)
    def test_expired_consumed_start_permit_can_stop_only_not_restart(self):
        work=self.simulate_loss();self.ctx.time+=7200
        result=stop_guard.finalize(self.ctx)
        self.assertEqual(result['status'],'STOP_GUARD_STOPPED_AND_QUARANTINED')
        self.assertTrue(self.ctx.stopped);self.assertTrue((work/'receipt.before-stop-guard.json').exists())
        self.assertEqual(self.receipt()['status'],'HOLD_PRESERVE_EVIDENCE')
        self.assertFalse(any('start' in c for c in self.ctx.calls if isinstance(c,tuple)))
    def test_unknown_stop_preserves_material_and_guard_attempt(self):
        work=self.simulate_loss();self.ctx.stop_exit=1
        with self.assertRaises(GateError):stop_guard.finalize(self.ctx)
        self.assertTrue(self.ctx.path(self.cfg['credential_generation']).exists())
        self.assertTrue((work/'stop-guard-attempt.json').exists())
        with self.assertRaises(GateError):stop_guard.finalize(self.ctx)
        self.assertEqual(sum('stop' in c for c in self.ctx.calls if isinstance(c,tuple)),1)
    def test_tampered_consumed_approval_does_not_issue_stop(self):
        work=self.simulate_loss();pin=json.loads((work/'consumed-approval.json').read_bytes())
        pin['approval_body']+='tamper';(work/'consumed-approval.json').write_bytes(canonical_bytes(pin))
        with self.assertRaises(GateError):stop_guard.finalize(self.ctx)
        self.assertFalse(self.ctx.stopped)
    def test_wrong_temporary_inode_does_not_move_objects(self):
        work=self.simulate_loss();self.ctx.key_drift=True
        with self.assertRaises(GateError):stop_guard.finalize(self.ctx)
        self.assertTrue(self.ctx.stopped);self.assertTrue(self.ctx.path(self.cfg['broker_private_key']).exists())
    def test_normal_completed_window_no_duplicate_stop(self):
        self.run_live();before=sum('stop' in c for c in self.ctx.calls if isinstance(c,tuple))
        result=stop_guard.finalize(self.ctx)
        self.assertEqual(result['status'],'PRIOR_STOP_AND_QUARANTINE_CONFIRMED_NO_EXTRA_ACTION')
        self.assertEqual(sum('stop' in c for c in self.ctx.calls if isinstance(c,tuple)),before)
