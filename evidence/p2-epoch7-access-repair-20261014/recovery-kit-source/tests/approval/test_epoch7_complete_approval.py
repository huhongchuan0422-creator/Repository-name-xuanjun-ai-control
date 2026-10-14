import copy,hashlib,json,sys,unittest
from unittest import mock
import epoch7_approval as base
import epoch7_complete_approval as s
from test_epoch7_injected_recovery import prepared

class CompleteTests(unittest.TestCase):
    def setUp(self):
        unused,unused,self.ops,unused,self.gate,unused=prepared()
        self.wanted=s.expected_complete('a'*64,self.gate)
        self.body=base.MARKER+json.dumps(self.wanted,sort_keys=True)
        self.bodysha=hashlib.sha256(self.body.encode()).hexdigest()
        self.calls=[];self.reject=False
        def fetcher(review_id,wanted):
            self.calls.append(review_id)
            if self.reject:raise ValueError('fixture rejection')
            raw=json.dumps({'id':review_id,'user':{'id':332398908,'login':'huhongchuan0422-creator'},
                'issue_url':'https://api.github.com/repos/'+base.REPO+'/issues/58','body':self.body}).encode()
            return base.validate(raw,review_id,wanted)
        self.v=s.CompleteApprovalVerifier(self.gate.review_id,self.bodysha,self.ops.install_lock_held,fetcher)
        self.gate.verifier=self.v;self.v.bind(self.gate,'a'*64)
    def test_one_envelope_binds_both(self):
        result=self.v.verify_outer_review(self.v.context)
        self.assertEqual(result['operation'],'verify_outer_review')
        proof=self.gate.check();self.assertEqual(proof['body_sha256'],self.bodysha)
        self.assertEqual(len(self.calls),1)
    def test_no_self_comment_id_cycle(self):
        self.assertNotIn('review_id',self.wanted['sequence_contract'])
        self.assertNotIn('context_sha256',self.wanted['sequence_contract'])
        self.assertEqual(self.wanted['retained_authorization'],self.gate.expected)
    def test_inner_before_outer_denied(self):
        with self.assertRaises(ValueError):self.gate.check()
    def test_prelock_check_does_not_grant_inner(self):
        self.ops.lock=False;self.v.verify_outer_review(self.v.context);self.ops.lock=True
        with self.assertRaises(ValueError):self.gate.check()
        self.v.verify_outer_review(self.v.context);self.gate.check();self.assertEqual(len(self.calls),2)
    def test_wrong_body_hash_rejected(self):
        self.v.body_sha='b'*64
        with self.assertRaises(ValueError):self.v.verify_outer_review(self.v.context)
    def test_old_flat_approval_rejected(self):
        self.body=base.MARKER+json.dumps(base.expected('a'*64,'b'*64,'c'*64,'d'*64))
        with self.assertRaises(ValueError):self.v.verify_outer_review(self.v.context)
    def test_changed_phase_contract_rejected(self):
        c=copy.deepcopy(self.v.context);c['phase_order'].reverse()
        with self.assertRaises(ValueError):self.v.verify_outer_review(c)
    def test_wanted_mutation_rejected(self):
        self.v.wanted['retained_authorization']['authorized_attempts']=2
        with self.assertRaises(ValueError):self.v.verify_outer_review(self.v.context)
    def test_inner_scope_mutation_rejected(self):
        self.v.verify_outer_review(self.v.context);wanted=copy.deepcopy(self.gate.expected);wanted['automatic_retry']=True
        with self.assertRaises(ValueError):self.v.verify_exact(self.gate.review_id,wanted)
    def test_lost_lock_rejected(self):
        self.v.verify_outer_review(self.v.context);self.ops.lock=False
        with self.assertRaises(ValueError):self.v.verify_exact(self.gate.review_id,self.gate.expected)
    def test_bind_once(self):
        with self.assertRaises(ValueError):self.v.bind(self.gate,'a'*64)
    def test_fresh_read_failure_denies(self):
        self.reject=True
        with self.assertRaises(ValueError):self.v.verify_outer_review(self.v.context)
        self.assertIsNone(self.v.cached)
    def test_failed_recheck_invalidates_cached_admission(self):
        self.v.verify_outer_review(self.v.context);self.reject=True
        with self.assertRaises(ValueError):self.v.verify_outer_review(self.v.context)
        with self.assertRaises(ValueError):self.gate.check()
    def test_bounded_fetch_timeout_revokes_cached_admission(self):
        self.v.verify_outer_review(self.v.context)
        self.gate.check()
        # The production fetch remains injectable, and a genuine bounded child
        # timeout (without network) must invalidate the previous locked check.
        worker = base._run_worker
        command = [sys.executable, '-I', '-B', '-S', '-c', 'import time; time.sleep(5)']
        def time_out(unused):
            return worker(command, timeout=0.4, cleanup_seconds=0.15)
        self.v.fetcher = base.fetch
        with mock.patch.object(base, '_run_worker', side_effect=time_out):
            with self.assertRaisesRegex(ValueError, 'APPROVAL_FETCH_TIMEOUT'):
                self.v.verify_outer_review(self.v.context)
        self.assertFalse(self.v.checked_under_lock)
        with self.assertRaises(ValueError):self.gate.check()

    def test_preapproval_body_compiles_without_gate_or_review_id(self):
        with mock.patch.object(s, 'context_from_gate', side_effect=AssertionError('no gate')):
            neutral = s.preapproval_sequence_contract(self.gate.delta, self.gate.expected)
            body = s.expected_complete_from_inputs('a'*64, self.gate.delta, self.gate.expected)
        self.assertNotIn('review_id', neutral)
        self.assertNotIn('context_sha256', neutral)
        self.assertEqual(body, self.wanted)
        self.assertEqual(neutral, self.wanted['sequence_contract'])

    def test_preapproval_validates_controller_transition_even_with_rehashed_authorization(self):
        mutations = (
            lambda row:row['after'].update(binary_sha256='f'*64),
            lambda row:row['before'].update(binary_sha256=row['after']['binary_sha256']),
            lambda row:row['after'].update(release_sha256='f'*64),
            lambda row:row['after'].update(instance='cccccccc-cccc-4ccc-8ccc-cccccccccccc'),
            lambda row:row['preserved_identity'].update(instance='forged'),
            lambda row:row.update(operation='RETAIN'))
        for mutate in mutations:
            delta = copy.deepcopy(self.gate.delta)
            mutate(delta['controller_transition'])
            authorization = copy.deepcopy(self.gate.expected)
            authorization['delta_sha256'] = s.digest(delta)
            with self.assertRaises(ValueError):
                s.preapproval_sequence_contract(delta, authorization)

    def test_controller_transition_is_covered_by_delta_and_actual_body_binding(self):
        import epoch7_delta as d
        self.assertEqual(d.validate_controller_transition(self.gate.delta['controller_transition']),
                         self.gate.delta['controller_transition'])
        self.assertEqual(self.wanted['sequence_contract']['delta_sha256'], s.digest(self.gate.delta))
        self.v.verify_outer_review(self.v.context)
        self.gate.delta['controller_transition']['after']['binary_sha256'] = 'f'*64
        with self.assertRaises(ValueError): self.gate.check()

    def test_frozen_preapproval_plan_body_do_not_depend_on_future_id(self):
        neutral = s.preapproval_sequence_contract(self.gate.delta, self.gate.expected)
        frozen_plan = s.canonical({'sequence_contract_sha256':s.sequence_contract_sha256(neutral)})
        plan_hash = hashlib.sha256(frozen_plan).hexdigest()
        unsigned = s.expected_complete_from_inputs(plan_hash, self.gate.delta, self.gate.expected)
        body = base.MARKER + json.dumps(unsigned, sort_keys=True)
        bodysha = hashlib.sha256(body.encode()).hexdigest()
        contexts = []
        for future_id in (7000000000, 7000000001):
            # These are synthetic fixtures only. Production learns its ID from
            # the genuine newly created comment, after plan/body are frozen.
            unused,unused,ops,unused,gate,unused = prepared()
            gate.review_id = future_id
            def fetcher(review_id, wanted):
                raw = json.dumps({'id':review_id,
                    'user':{'id':332398908,'login':'huhongchuan0422-creator'},
                    'issue_url':'https://api.github.com/repos/'+base.REPO+'/issues/58',
                    'body':body}).encode()
                return base.validate(raw, review_id, wanted)
            verifier = s.CompleteApprovalVerifier(future_id, bodysha, ops.install_lock_held, fetcher)
            gate.verifier = verifier
            verifier.bind(gate, plan_hash)
            self.assertEqual(verifier.wanted, unsigned)
            self.assertEqual(s.canonical({'sequence_contract_sha256':
                s.sequence_contract_sha256(verifier.context)}), frozen_plan)
            verifier.verify_outer_review(verifier.context)
            proof = gate.check()
            self.assertEqual(proof['review_id'], future_id)
            self.assertEqual(proof['body_sha256'], bodysha)
            contexts.append(verifier.context)
        self.assertNotEqual(contexts[0]['context_sha256'], contexts[1]['context_sha256'])

    def test_identical_body_at_other_comment_id_cannot_admit(self):
        other_id = self.gate.review_id + 1
        raw = json.dumps({'id':other_id,
            'user':{'id':332398908,'login':'huhongchuan0422-creator'},
            'issue_url':'https://api.github.com/repos/'+base.REPO+'/issues/58',
            'body':self.body}).encode()
        self.v.fetcher = lambda review_id,wanted:base.validate(raw, review_id, wanted)
        with self.assertRaisesRegex(ValueError, 'APPROVAL_AUTHOR'):
            self.v.verify_outer_review(self.v.context)
        with self.assertRaises(ValueError):self.gate.check()

    def test_same_json_but_changed_raw_body_cannot_admit(self):
        self.body += '\n'
        with self.assertRaisesRegex(ValueError, 'COMPLETE_AUTHENTICATED_BODY'):
            self.v.verify_outer_review(self.v.context)
        with self.assertRaises(ValueError):self.gate.check()

    def test_neutral_normalizer_rejects_partial_or_stale_admission_fields(self):
        neutral = s.sequence_contract(self.v.context)
        for field,value in (('review_id', self.gate.review_id), ('context_sha256', 'a'*64),
                            ('unreviewed_extension', True)):
            with self.assertRaises(ValueError):s.sequence_contract(dict(neutral, **{field:value}))
        stale = dict(self.v.context, review_id=self.gate.review_id+1)
        with self.assertRaisesRegex(ValueError, 'COMPLETE_CONTEXT_MUTATED'):
            s.sequence_contract(stale)
        for review_id in (True, 6170703284):
            bad = dict(neutral, review_id=review_id)
            bad['context_sha256'] = s.digest(bad)
            with self.assertRaisesRegex(ValueError, 'COMPLETE_FRESH_REVIEW'):
                s.sequence_contract(bad)

    def test_neutral_normalizer_keeps_every_policy_pin(self):
        neutral = s.sequence_contract(self.v.context)
        before = s.sequence_contract_sha256(neutral)
        for key in ('authorization_sha256', 'snapshot_sha256', 'candidate_sha256',
                    'runtime_manifest_sha256', 'delta_sha256', 'kit_manifest_sha256',
                    'security_delta_sha256'):
            other = dict(neutral, **{key:'f'*64})
            self.assertNotEqual(before, s.sequence_contract_sha256(other))
        other = copy.deepcopy(neutral);other['phase_order'].reverse()
        with self.assertRaisesRegex(ValueError, 'COMPLETE_SEQUENCE_FIXED_POLICY'):
            s.sequence_contract_sha256(other)
        other = copy.deepcopy(neutral);other['tls_change']['certificate_sha256'] = 'f'*64
        self.assertNotEqual(before, s.sequence_contract_sha256(other))

    def test_preapproval_rejects_delta_authorization_mismatch(self):
        for key in ('delta_sha256', 'snapshot_sha256', 'candidate_sha256', 'runtime_manifest_sha256'):
            authorization = dict(self.gate.expected, **{key:'f'*64})
            with self.assertRaises(ValueError):
                s.preapproval_sequence_contract(self.gate.delta, authorization)
        authorization = dict(self.gate.expected, authorized_attempts=True)
        with self.assertRaisesRegex(ValueError, 'COMPLETE_PREAPPROVAL_POLICY'):
            s.preapproval_sequence_contract(self.gate.delta, authorization)

    def test_rehashed_changed_neutral_contract_cannot_replace_approved_context(self):
        self.v.context['security_delta_sha256'] = 'f'*64
        self.v.context.pop('context_sha256')
        self.v.context['context_sha256'] = s.digest(self.v.context)
        with self.assertRaisesRegex(ValueError, 'COMPLETE_ADMISSION_CONTRACT'):
            self.v.verify_outer_review(self.v.context)

    def test_preapproval_rejects_invented_id_fields_in_input_contracts(self):
        for field in ('review_id', 'context_sha256', 'approval_body_sha256'):
            with self.assertRaisesRegex(ValueError, 'COMPLETE_PREAPPROVAL_INPUT_FIELDS'):
                s.preapproval_sequence_contract(dict(self.gate.delta, **{field:'unreviewed'}),
                                                self.gate.expected)
            with self.assertRaisesRegex(ValueError, 'COMPLETE_PREAPPROVAL_INPUT_FIELDS'):
                s.preapproval_sequence_contract(self.gate.delta,
                                                dict(self.gate.expected, **{field:'unreviewed'}))

    def test_wrong_context_recheck_revokes_old_admission(self):
        self.v.verify_outer_review(self.v.context)
        self.gate.check()
        other = s.sequence_contract(self.v.context)
        other['review_id'] = self.gate.review_id + 1
        other['context_sha256'] = s.digest(other)
        with self.assertRaisesRegex(ValueError, 'COMPLETE_OUTER_CONTEXT'):
            self.v.verify_outer_review(other)
        self.assertFalse(self.v.checked_under_lock)
        with self.assertRaises(ValueError):self.gate.check()

    def test_known_consumed_id_denied(self):
        for review in base.CONSUMED:
            with self.assertRaises(ValueError):s.CompleteApprovalVerifier(review,'a'*64,lambda:True)

if __name__=='__main__':unittest.main()
