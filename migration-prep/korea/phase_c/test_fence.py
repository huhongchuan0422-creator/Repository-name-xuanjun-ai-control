"""Synthetic nft/systemd/UID-counter model, never a real kernel PASS claim."""
import copy
import json
import os
import subprocess
import unittest

from gate_common import GateError,canonical_bytes
from korea.phase_c import artifact,fence,security
from korea.phase_c import lifecycle as live
from korea.phase_c import test_lifecycle as fixtures


class FenceModel(fixtures.LiveModel,fence.Context):
    def __init__(self, root):
        super().__init__(root);self.applied=False;self.existing=False;self.counter={986:0,1986:0}
        self.no_delta=False;self.bad_probe=False;self.apply_unknown=False;self.check_fail=False
        self.extra_changed=False;self.table_changed=False;self.expire_after_claim=False
    def global_rules(self):
        rows=[{'metainfo':{'version':'MODEL_NOT_HOST'}},{'table':{'family':'ip','name':'shared-fixture'}}]
        if self.extra_changed and self.applied:rows[1]['table']['name']='drift'
        if self.applied or self.existing:rows.append({'table':{'family':'inet','name':self.table_name}})
        return {'nftables':rows}
    def nft(self,args,data=None):
        self.calls.append(('nft',tuple(args),data))
        if args==['-c','-f','-']:return subprocess.CompletedProcess(args,1 if self.check_fail else 0,'','')
        if args==['-f','-']:
            self.applied=True
            return subprocess.CompletedProcess(args,1 if self.apply_unknown else 0,'','')
        raise AssertionError(args)
    def table(self,name):
        rows=[{'table':{'family':'inet','name':name}},{'chain':{'family':'inet','table':name,
            'name':'output','type':'filter','hook':'output','prio':0,'policy':'accept'}}]
        for uid,packets in self.counter.items():
            rows.append({'rule':{'family':'inet','table':name,'chain':'output','expr':[
                {'match':{'op':'==','left':{'meta':{'key':'skuid'}},'right':uid}},
                {'counter':{'packets':packets,'bytes':packets*60}},{'drop':None}]}})
        if self.table_changed and sum(self.counter.values()):rows[-1]['rule']['expr'][-1]={'accept':None}
        return {'nftables':rows}
    def probe(self,uid,family):
        self.calls.append(('MODELED_LOOPBACK_PROBE',uid,family))
        if self.bad_probe:raise GateError('MODEL_CONNECTED')
        if not self.no_delta:self.counter[uid]+=1


@unittest.skipUnless(os.geteuid()==0,'Root-owned synthetic filesystem')
class FenceTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.LifecycleTests.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.LifecycleTests.tearDownClass.__func__)
    make_plan=fixtures.LifecycleTests.make_plan
    baseline=fixtures.LifecycleTests.baseline
    set_pin=fixtures.LifecycleTests.set_pin
    def setUp(self):
        fixtures.LifecycleTests.setUp(self)
        old=self.ctx
        self.ctx=FenceModel(old.root)
        for name in ('b_unit_sha','b_transaction_sha','b_manifest_sha'):setattr(self.ctx,name,getattr(old,name))
        self.ctx.table_name=self.cfg['network_policy']['table']
        self.ctx.path(live.NETWORK_PROOF).unlink() # Synthetic old proof only, not production cleanup.
        self.grant=dict(schema_version=1,decision='APPROVED_WITH_EXACT_PRECONDITIONS',host=live.HOST,
            action=fence.ACTION,max_attempts=1,network_changes_allowed=True,loopback_negative_probes_allowed=True,
            service_start_allowed=False,credentials_allowed=False,database_export_allowed=False,writer_allowed=False,
            runtime_manifest_sha256=self.cfg['runtime_manifest_sha256'],config_sha256=security.hash_value(self.cfg),
            policy_sha256=security.hash_value(self.cfg['network_policy']),
            controller_sha256=security.digest((self.origin/(artifact.PREFIX+'fence.py')).read_bytes()),
            approval_comment_id=222222,issued_at=fixtures.NOW-1,expires_at=fixtures.NOW+3600)
        self.replace_fence_pin()
    def replace_fence_pin(self,**changes):
        self.grant.update(changes)
        body='SYNTHETIC FENCE ONLY\n<!-- '+fence.MARKER+'\n'+json.dumps(self.grant)+'\n'+fence.MARKER+' -->'
        self.ctx.current_body=body
        pin=dict(approval_comment_id=222222,approval_body_sha256=security.digest(body.encode()),approval_body=body)
        p=self.ctx.path(fence.PIN)
        if p.exists():p.write_bytes(canonical_bytes(pin))
        else:security.write_once(p,canonical_bytes(pin))
    def run_fence(self):return fence.apply_once(self.ctx)
    def receipt(self):return json.loads((self.ctx.path(fence.WORK)/'receipt.json').read_bytes())
    def test_single_table_four_counter_deltas_no_service_or_credential_action(self):
        result=self.run_fence();self.assertEqual(result['status'],'DEDICATED_FENCE_KERNEL_NEGATIVE_PROBES_PASS')
        proof=json.loads(self.ctx.path(live.NETWORK_PROOF).read_bytes());live.network_proof(proof,self.cfg,self.ctx.now_ms())
        self.assertEqual(len(proof['negative_probes']),4);self.assertFalse(self.ctx.readonly_checked)
        self.assertEqual(sum(c[:2]==('nft',('-f','-')) for c in self.ctx.calls if isinstance(c,tuple)),1)
        self.assertFalse(self.ctx.path(fence.LOCK).exists())
        self.assertFalse(any(c[0]=='/usr/bin/systemctl' and 'start' in c for c in self.ctx.calls if isinstance(c,tuple)))
        with self.assertRaises(GateError):self.run_fence()
    def test_edited_approval_has_no_attempt(self):
        self.ctx.current_body='revoked'
        with self.assertRaises(GateError):self.run_fence()
        self.assertFalse(self.ctx.path(fence.WORK).exists());self.assertFalse(self.ctx.applied)
    def test_old_wrong_scope_expired_and_wrong_runtime_rejected(self):
        for change in ({'action':live.ACTION},{'credentials_allowed':True},{'expires_at':fixtures.NOW},
                       {'runtime_manifest_sha256':'0'*64}):
            old=copy.deepcopy(self.grant);self.replace_fence_pin(**change)
            with self.subTest(change=change),self.assertRaises(GateError):self.run_fence()
            self.assertFalse(self.ctx.applied);self.grant=old
        self.replace_fence_pin()
    def test_existing_table_is_not_replaced(self):
        self.ctx.existing=True
        with self.assertRaises(GateError):self.run_fence()
        self.assertFalse(self.ctx.path(fence.WORK).exists());self.assertFalse(self.ctx.applied)
    def test_syntax_failure_before_claim_and_apply(self):
        self.ctx.check_fail=True
        with self.assertRaises(GateError):self.run_fence()
        self.assertFalse(self.ctx.path(fence.WORK).exists());self.assertFalse(self.ctx.applied)
    def test_apply_unknown_preserves_attempt_and_no_proof(self):
        self.ctx.apply_unknown=True
        with self.assertRaises(GateError):self.run_fence()
        self.assertTrue(self.ctx.path(fence.LOCK).exists());self.assertFalse(self.ctx.path(live.NETWORK_PROOF).exists())
        self.assertTrue(self.receipt()['network_apply_attempted'])
    def test_timeout_without_drop_counter_never_proves_firewall(self):
        self.ctx.no_delta=True
        with self.assertRaisesRegex(GateError,'C_FENCE_NO_KERNEL_DROP_EVIDENCE'):self.run_fence()
        self.assertFalse(self.ctx.path(live.NETWORK_PROOF).exists());self.assertTrue(self.ctx.applied)
    def test_connected_or_wrong_probe_result_holds(self):
        self.ctx.bad_probe=True
        with self.assertRaises(GateError):self.run_fence()
        self.assertFalse(self.ctx.path(live.NETWORK_PROOF).exists())
    def test_table_drift_stops_before_proof(self):
        self.ctx.table_changed=True
        with self.assertRaises(GateError):self.run_fence()
        self.assertFalse(self.ctx.path(live.NETWORK_PROOF).exists())
    def test_shared_global_drift_is_preserved_not_restored(self):
        self.ctx.extra_changed=True
        with self.assertRaises(GateError):self.run_fence()
        self.assertTrue(self.ctx.applied);self.assertFalse(self.ctx.path(live.NETWORK_PROOF).exists())
        self.assertEqual(self.receipt()['status'],'HOLD_PRESERVE_EVIDENCE')
    def test_drop_counter_exact_uid_and_drop_semantics(self):
        table=self.ctx.table(self.ctx.table_name)
        self.assertEqual(fence.drop_counter(table,self.ctx.table_name,986),0)
        table['nftables'][2]['rule']['expr'][-1]={'accept':None}
        with self.assertRaises(GateError):fence.drop_counter(table,self.ctx.table_name,986)
    def test_only_loopback_and_no_payload_in_production_probe(self):
        self.assertIn('127.0.0.1',fence.PROBE_CODE);self.assertIn('::1',fence.PROBE_CODE)
        self.assertIn('os.setgroups([]);os.setgid(uid);os.setuid(uid)',fence.PROBE_CODE)
        self.assertNotIn('.send(',fence.PROBE_CODE);self.assertNotIn('.sendall(',fence.PROBE_CODE)
        compile(fence.PROBE_CODE,'probe','exec')
