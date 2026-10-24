import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import migration_transaction as m


def plan():
    return dict(action=m.ACTION, transaction_id='fixture-001', head='a'*40,
                host=m.HOST, source_host=m.SOURCE_HOST, release=m.RELEASE,
                issued_at=100, expires_at=200, independent_review_comment_id=123,
                source_hashes=m.source_manifest(),
                bindings={k:'c'*64 for k in ('writer_inventory', 'protected_inventory', 'final_manifest_contract',
                          'runtime_identity', 'unit_manifest', 'business_acceptance_contract', 'route_contract')},
                steps=list(m.STEPS))


def event():
    return dict(repository=m.REPOSITORY, action='labeled', pr=99, head_repository=m.REPOSITORY,
                branch=m.BRANCH, actor_id='332398908', label='pr99-s09-production-'+'a'*12,
                head='a'*40, run_attempt='1')


class FixtureAdapter:
    def __init__(self, fail=None, unknown=None, invalid=None):
        self.fail, self.unknown, self.invalid = fail, unknown, invalid
        self.executed, self.queried = [], []
    def receipt(self, request):
        return dict(request_digest=m.digest(request), operation_id=request['operation_id'],
                    stage=request['stage'], status='FAILED' if request['stage'] == self.fail else 'SUCCEEDED',
                    evidence='d'*64)
    def execute(self, request):
        self.executed.append(request['stage'])
        if request['stage'] == self.unknown:
            raise TimeoutError('private data MUST NOT be logged')
        r = self.receipt(request)
        if request['stage'] == self.invalid:
            r['operation_id'] = 'wrong'
        return r
    def query(self, request):
        self.queried.append(request['stage'])
        return self.receipt(request)


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.root.chmod(0o700)
        self.p = plan(); self.hash = m.digest(self.p)
    def run_tx(self, adapter):
        return m.Transaction(self.root, adapter, lambda:150).run_fixture(self.p, self.hash)
    def test_complete_order_and_chain(self):
        a = FixtureAdapter()
        self.assertEqual(self.run_tx(a), 'FIXTURE_TRANSACTION_SUCCEEDED')
        self.assertEqual(a.executed, list(m.STEPS))
        j = m.Journal(self.root, self.p['transaction_id'])
        try:
            claim, events, _ = j.load()
            self.assertEqual(len(events), 25)
            self.assertEqual(claim['plan_digest'], self.hash)
        finally: j.close()
    def test_replay_and_new_attempt_both_blocked(self):
        a = FixtureAdapter(); self.run_tx(a)
        for txid in ('fixture-001', 'fixture-002'):
            self.p['transaction_id'] = txid; self.hash = m.digest(self.p)
            with self.assertRaisesRegex(m.Hold, 'EXISTING_TRANSACTION'):
                self.run_tx(a)
        self.assertEqual(len(a.executed), 12)
    def test_failure_at_every_stage_and_containment_order(self):
        for stage in m.STEPS:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as d:
                a = FixtureAdapter(fail=stage)
                result = m.Transaction(d, a, lambda:150).run_fixture(self.p, self.hash)
                expected = list(m.STEPS[:m.STEPS.index(stage)+1])
                if 'cutover_route' in expected: expected += ['restore_route']
                if 'install_stopped' in expected: expected += ['stop_owned']
                self.assertEqual(a.executed, expected)
                self.assertEqual(result, 'FAILED_PRESERVED_NO_SOURCE_RESUME')
    def test_unknown_at_every_stage_never_rolls_back_or_replays(self):
        for stage in m.STEPS:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as d:
                a = FixtureAdapter(unknown=stage); tx = m.Transaction(d, a, lambda:150)
                with self.assertRaisesRegex(m.Hold, 'OPERATION_UNKNOWN'):
                    tx.run_fixture(self.p, self.hash)
                before = list(a.executed)
                self.assertEqual(tx.query_only(self.p['transaction_id'], self.hash),
                                 'RESOLVED_SUCCEEDED_HOLD_NO_CONTINUATION')
                self.assertEqual(tx.query_only(self.p['transaction_id'], self.hash),
                                 'RECORDED_RESULT_HOLD_NO_CONTINUATION')
                self.assertEqual(a.executed, before)
                self.assertEqual(a.queried, [stage])
                self.assertNotIn('private data', ''.join(p.read_text() for p in Path(d).rglob('*.json')))
    def test_crash_saving_result_queries_without_redispatch(self):
        a=FixtureAdapter();real=m.exclusive
        def write(path,payload):
            if Path(path).name=='0001.json':raise OSError('disk')
            return real(path,payload)
        with patch.object(m,'exclusive',write):
            with self.assertRaises(OSError):self.run_tx(a)
        self.assertEqual(a.executed,['inspect_protected'])
        self.assertEqual(m.Transaction(self.root,a).query_only(self.p['transaction_id'],self.hash),
                         'RESOLVED_SUCCEEDED_HOLD_NO_CONTINUATION')
        self.assertEqual(a.executed,['inspect_protected'])
    def test_foreign_query_receipt_remains_unknown(self):
        a=FixtureAdapter(unknown='cutover_route');tx=m.Transaction(self.root,a,lambda:150)
        with self.assertRaises(m.Hold):tx.run_fixture(self.p,self.hash)
        with patch.object(a,'query',return_value={'status':'SUCCEEDED'}):
            self.assertEqual(tx.query_only(self.p['transaction_id'],self.hash),'UNKNOWN_QUERY_ONLY_NO_REPLAY')
        self.assertNotIn('restore_route',a.executed)
    def test_bad_receipt_is_unknown(self):
        a=FixtureAdapter(invalid='start_owned')
        with self.assertRaisesRegex(m.Hold, 'OPERATION_UNKNOWN'): self.run_tx(a)
        self.assertNotIn('stop_owned', a.executed)
    def test_rollback_failure_remains_hold(self):
        a=FixtureAdapter(fail='accept_https')
        original=a.execute
        def execute(req):
            r=original(req)
            if req['stage']=='restore_route': r['status']='FAILED'
            return r
        a.execute=execute
        self.assertEqual(self.run_tx(a), 'CONTAINMENT_FAILED_HOLD')
        self.assertNotIn('stop_owned', a.executed)
    def test_expiry_checked_before_each_effect(self):
        a=FixtureAdapter(); tick=iter([150,150,201])
        with self.assertRaisesRegex(m.Hold,'EXPIRED_BEFORE_OPERATION'):
            m.Transaction(self.root,a,lambda:next(tick)).run_fixture(self.p,self.hash)
        self.assertEqual(a.executed,['inspect_protected'])
    def test_corrupt_partial_record_preserved(self):
        a=FixtureAdapter(); self.run_tx(a)
        path=self.root/self.p['transaction_id']/'0001.json'; path.write_bytes(b'{')
        with self.assertRaisesRegex(m.Hold, 'CORRUPT_JOURNAL'):
            m.Transaction(self.root,a).query_only(self.p['transaction_id'],self.hash)
        self.assertEqual(path.read_bytes(),b'{')
    def test_wrong_recovery_digest_no_query(self):
        a=FixtureAdapter(unknown='fence_source')
        with self.assertRaises(m.Hold): self.run_tx(a)
        with self.assertRaisesRegex(m.Hold,'RECOVERY_PLAN_DIGEST'):
            m.Transaction(self.root,a).query_only(self.p['transaction_id'],'e'*64)
        self.assertEqual(a.queried,[])
    def test_concurrency_lock(self):
        first=m.Journal(self.root,self.p['transaction_id'])
        try:
            with self.assertRaises(BlockingIOError):m.Journal(self.root,self.p['transaction_id'])
        finally:first.close()
    def test_claim_crash_consumes_without_dispatch(self):
        a=FixtureAdapter()
        with patch.object(m,'exclusive',side_effect=OSError('disk')):
            with self.assertRaises(OSError):self.run_tx(a)
        with self.assertRaisesRegex(m.Hold,'EXISTING_TRANSACTION'):self.run_tx(a)
        self.assertEqual(a.executed,[])
    def test_intent_durable_before_effect(self):
        a=FixtureAdapter(); original=a.execute
        def execute(req):
            files=sorted((self.root/self.p['transaction_id']).glob('[0-9]*.json'))
            last=json.loads(files[-1].read_text())['body']
            self.assertEqual(last,{'type':'INTENT','request':req})
            return original(req)
        a.execute=execute;self.run_tx(a)
    def test_journal_symlink_rejected(self):
        target=self.root/'target';target.mkdir(mode=0o700)
        link=self.root/'link';link.symlink_to(target)
        with self.assertRaisesRegex(m.Hold,'JOURNAL_SYMLINK'):m.Journal(link,'fixture')
    def test_private_mode_required(self):
        self.root.chmod(0o755)
        with self.assertRaisesRegex(m.Hold,'JOURNAL_DIRECTORY_IDENTITY'):self.run_tx(FixtureAdapter())
    def test_plan_negative_fields(self):
        cases={'action':'wrong','host':'other','source_host':'other','release':'/domestic-r2',
               'head':'a'*39,'issued_at':True,'expires_at':150,'independent_review_comment_id':True,
               'transaction_id':'../escape','steps':list(reversed(m.STEPS)), 'bindings':{}}
        for key,value in cases.items():
            p=copy.deepcopy(self.p);p[key]=value
            with self.subTest(key=key),self.assertRaises(m.Hold):m.validate_plan(p,m.digest(p),150)
    def test_source_drift_no_claim_or_dispatch(self):
        self.p['source_hashes']['production_start.py']='e'*64;self.hash=m.digest(self.p)
        a=FixtureAdapter()
        with self.assertRaisesRegex(m.Hold,'SOURCE_DRIFT'):self.run_tx(a)
        self.assertEqual(a.executed,[])
        self.assertFalse((self.root/self.p['transaction_id']).exists())
    def test_existing_state_and_host_constants_reused(self):
        import production_start
        self.assertEqual(m.HOST,production_start.HOST)
        self.assertEqual(m.RELEASE,str(production_start.RELEASE))
        self.assertEqual(m.HOST_OPERATION_STORE,str(production_start.STATE/'operations'))
    def test_plan_digest_required(self):
        with self.assertRaisesRegex(m.Hold,'PLAN_DIGEST'):m.validate_plan(self.p,'f'*64,150)
    def test_event_negative_fields(self):
        for key in event():
            e=event();e[key]='invalid'
            with self.subTest(key=key),self.assertRaises(m.Hold):m.validate_event(e,'a'*40)
    def test_even_exact_production_entry_unconditionally_disabled(self):
        with patch.object(m.time,'time',lambda:150):
            with self.assertRaisesRegex(m.Hold,'REVIEW_ONLY_NO_PRODUCTION_ADAPTER_NO_CLOUD_CALL'):
                m.production_entry(event(),self.p,self.hash)
    def test_unknown_query_timeout_no_dispatch(self):
        a=FixtureAdapter(unknown='cutover_route');tx=m.Transaction(self.root,a,lambda:150)
        with self.assertRaises(m.Hold):tx.run_fixture(self.p,self.hash)
        with patch.object(a,'query',side_effect=TimeoutError):
            self.assertEqual(tx.query_only(self.p['transaction_id'],self.hash),'UNKNOWN_QUERY_ONLY_NO_REPLAY')
        self.assertEqual(a.executed,list(m.STEPS[:-1]))

if __name__=='__main__': unittest.main()
