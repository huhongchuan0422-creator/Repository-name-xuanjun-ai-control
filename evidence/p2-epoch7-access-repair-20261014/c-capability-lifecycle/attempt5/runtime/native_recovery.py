"""Versioned native durable phase continuation. Never invokes old resume_once.

All effects use the actual InjectedDriver phase dispatch and its original
before/after guards, diagnostic bounds, CAS journal and failure containment.
Admission/recovery must come from the independent signed receipt provider.
There is deliberately no default production transport or key.
"""
import copy
from receipt_provider import ReceiptProvider, Hold, need, digest
import native_state

class NativeRecovery(object):
    def __init__(self, driver, ledger, provider, source_identity=None, fixture_mode=False, approval_review_id=None, cycle_policy=None):
        from permit_cycle import policy
        self.cycle_policy=policy(cycle_policy)
        self.approval_review_id=approval_review_id
        import epoch7_recovery_sequence as sequence
        from attempt_ledger import Ledger
        need(isinstance(driver, sequence.InjectedDriver) and isinstance(ledger, Ledger), 'NATIVE_DEPENDENCIES')
        need(isinstance(provider, ReceiptProvider), 'AUTHENTICATED_PROVIDER_REQUIRED')
        need(type(source_identity) is dict and all(source_identity.get(key) == ledger.grant[key]
             for key in ('source_commit','source_tree','manifest_sha256')), 'EXACT_VERSION_BINDING')
        if fixture_mode:
            need(ledger.grant['target_host']=='TEST_ONLY' and provider.issuer=='TEST_ONLY', 'FIXTURE_CANNOT_AUTHORIZE_HOST')
        else:
            from epoch7_live_controls import FiniteLiveControls
            from epoch7_host_containment import HostContainment
            need(isinstance(driver.controls,FiniteLiveControls) and
                 isinstance(driver.containment,HostContainment),'CONCRETE_NATIVE_COMPOSITION_REQUIRED')
            need(ledger.grant['recovery_entry']=='native_recovery.NativeRecovery','VERSIONED_RECOVERY_ENTRY_REQUIRED')
            from authorization import authenticate
            self.approval=authenticate(approval_review_id,ledger.grant,provider,self.cycle_policy)
        self.s, self.driver, self.ledger, self.provider = sequence, driver, ledger, provider
        self.journal = None

    def proof(self, attempt, operation, payload=None):
        result = self.provider.request(self.ledger.grant, attempt, operation, payload)
        need(result.get('grant_id') == self.ledger.grant['grant_id'] and
             result.get('attempt_id') == attempt, 'AUTHORITY_BINDING')
        return result

    def fence(self, attempt, step):
        self.ledger._fresh()
        proof = self.proof(attempt, 'verify_fence', {'step': step})
        need(proof.get('status') == 'HELD' and proof.get('exclusive') is True and
             type(proof.get('fence')) is int and proof['fence'] > 0 and
             type(proof.get('lease_epoch')) is int and proof['lease_epoch'] > 0,
             'WRITER_FENCE_UNKNOWN')
        token = (proof['writer'], proof['lease_epoch'], proof['fence'])
        if hasattr(self, 'token'):
            need(self.token == token, 'FENCE_CHANGED')
        self.token = token
        return proof

    def _guard_native_effects(self, attempt):
        # All concrete original effect IO/commands pass ClaimAuthority.receipt
        # through authority.phase/effect_check. Bind the *new* lease/grant at
        # that native guard as well as at phase boundaries. No long phase can
        # continue commands under an expired new five-attempt authorization.
        authority=getattr(self.driver.journal_io,'authority',None)
        if authority is None:
            return  # Explicit TEST_ONLY Rig has no concrete host authority.
        original=getattr(authority,'_attempt5_original_receipt',authority.receipt)
        authority._attempt5_original_receipt=original
        def guarded_receipt(*args,**kwargs):
            self.fence(attempt,'NATIVE_EFFECT')
            return original(*args,**kwargs)
        authority.receipt=guarded_receipt

    def begin(self, command_sha):
        # Global authority must atomically consume the same ordinal before any
        # native admission. An interrupted local claim remains consumed/HOLD.
        self.fence('CANDIDATE', 'CLAIM')
        attempt = self.ledger.claim()
        self.ledger.intent(attempt, command_sha)
        snapshot = self.ledger.snapshot()
        proof = self.proof(attempt, 'consume_attempt',
                           {'ordinal': len(snapshot['attempts']),
                            'command_sha256': command_sha,
                            'ledger_sha256': digest(snapshot)})
        need(proof.get('status') == 'CONSUMED' and
             proof.get('ordinal') == len(snapshot['attempts']) and
             proof.get('max_attempts') == 5, 'GLOBAL_QUOTA_UNKNOWN')
        return attempt

    def _initialize(self, attempt):
        driver, s = self.driver, self.s
        proof = self.proof(attempt, 'authorize_first_admission',
                           {'context_sha256': driver.context['context_sha256']})
        need(proof.get('status') == 'AUTHORIZED' and
             proof.get('policy') == 'P2_ATTEMPT5_V1' and
             proof.get('context_sha256') == driver.context['context_sha256'], 'FIRST_ADMISSION_UNKNOWN')
        prior=self.ledger.snapshot()['attempts'][:-1]
        need(all(row['state']=='FAILED_NO_WRITE' for row in prior), 'MISSING_NATIVE_HISTORY')
        need(driver.retained_io.journal_exists(driver.inner.name) is False,'PARTIAL_NATIVE_CLAIM')
        s.check_observation(driver.controls.verify_outer_review(copy.deepcopy(driver.context)),
                            driver.context, 'verify_outer_review')
        # The original native capability is prepared/claimed exactly once.
        # Subsequent attempts authenticate/adopt its persistent CAS records.
        prepared, evidence = s.successor.prepare_successor(driver, driver.context['claim_successor'])
        self.journal = s.OuterJournal(driver.journal_io, driver.context, driver.gate.journal_binding())
        state = {'schema': 1, 'stage': 'CLAIM_INTENT', 'completed': [],
                 'phase_evidence': {}, 'containment': [], 'containment_status': 'NOT_ATTEMPTED',
                 'secondary_errors': [], 'interruption': None, 'admission': 'UNKNOWN',
                 'receipt_status': 'UNKNOWN', 'automatic_retry': False,
                 'production_acceptance': 'PENDING', 'prepare_evidence': evidence}
        s.successor.commit_successor(driver, prepared, self.journal, state)
        state.update(stage='ADMITTED', admission='ADMITTED', receipt_status='OBSERVED')
        state['component_checkpoint']=native_state.capture(driver, [])
        self.journal.save(state)
        return state

    def _adopt(self, attempt):
        """Authenticate exact native records before setting in-memory CAS state.

        No old claim is deleted, rewritten as fresh, or re-consumed. An external
        five-attempt grant authorizes continuation of these exact records.
        """
        driver, s = self.driver, self.s
        record = driver.journal_io.read_journal(s.OUTER_NAME)
        value = s.retained.BoundJournal._validate_record(record)
        state = value['state']
        need(type(state) is dict and state.get('admission') == 'ADMITTED', 'NATIVE_ADMISSION')
        done = state.get('completed')
        need(type(done) is list and done == list(s.PHASES[:len(done)]), 'NATIVE_PHASE_ORDER')
        inner = driver.retained_io.read_journal(driver.inner.name)
        inner_value = s.retained.BoundJournal._validate_record(inner)
        need(inner_value.get('name') == driver.inner.name, 'INNER_BINDING')
        payload = {'outer_sha256': s.sha(record['data']), 'inner_sha256': s.sha(inner['data']),
                   'context_sha256': driver.context['context_sha256'], 'completed': done,
                   'ledger_sha256': digest(self.ledger.snapshot())}
        proof = self.proof(attempt, 'authenticate_native_recovery', payload)
        need(proof.get('status') == 'AUTHORIZED' and proof.get('binding') == payload and
             proof.get('policy') == 'P2_ATTEMPT5_V1' and proof.get('max_attempts') == 5,
             'NEW_VERSIONED_GRANT_REQUIRED')
        need(proof.get('safe_stage') == state.get('stage') and
             state.get('stage') in ('ADMITTED',) + tuple(p + '_COMPLETE' for p in s.PHASES),
             'PARTIAL_OR_UNKNOWN_REQUIRES_NATIVE_RECONCILIATION')
        # Before adoption, prove every completed native effect against actual
        # host readback and immutable checkpoint/backup/transaction receipts.
        pins = {row['name']: row['sha256'] for row in self.ledger.snapshot()['completed']}
        for phase in done:
            evidence = state['phase_evidence'][phase]
            s.check_observation(evidence, driver.context, phase)
            fingerprint = digest(evidence)
            need(phase not in pins or pins[phase] == fingerprint, 'CHECKPOINT_MISMATCH')
            readback = self.proof(attempt, 'verify_completed_phase',
                                 {'phase': phase, 'checkpoint_sha256': fingerprint})
            need(readback.get('status') == 'VERIFIED' and
                 readback.get('checkpoint_sha256') == fingerprint, 'EFFECT_UNVERIFIED')
            if phase not in pins:
                self.ledger.checkpoint(attempt, phase, fingerprint)
        native_state.restore(driver, state.get('component_checkpoint'), done)
        self.journal = s.OuterJournal(driver.journal_io, driver.context, driver.gate.journal_binding())
        need(self.journal._read()==record and inner_value.get('binding')==driver.gate.journal_binding(), 'RESTORED_NATIVE_BINDING')
        driver.gate.verifier._bound()
        self.journal.last = copy.deepcopy(record)
        driver.inner.last, driver.inner.state = copy.deepcopy(inner), copy.deepcopy(inner_value['state'])
        return copy.deepcopy(state)

    def reconcile_unadmitted(self, attempt):
        """Explicit no-write retry after a failed claim/admission, never reset."""
        driver,s=self.driver,self.s
        with driver.controls.install_lock():
            self.fence(attempt,'RECONCILE_UNADMITTED')
            need(driver.journal_io.journal_exists(s.OUTER_NAME) is False and
                 driver.retained_io.journal_exists(driver.inner.name) is False,'PARTIAL_NATIVE_CLAIM')
            binding={'outer_absent':True,'inner_absent':True,
                     'ledger_sha256':digest(self.ledger.snapshot())}
            response=self.proof(attempt,'reconcile_unadmitted',binding)
            need(response.get('status')=='RECONCILED' and response.get('binding')==binding and
                 type(response.get('proof')) is dict and response['proof'].get('outcome')=='NO_WRITE',
                 'NO_WRITE_UNPROVEN')
            return self.ledger.reconcile(attempt,response['proof'],lambda value:value==response['proof'])

    def reconcile(self, attempt):
        """Resolve exactly one durable uncertain phase through native CAS.

        A signed whole-phase COMMITTED proof advances the native state; a
        signed NO_WRITE proof restores its preceding safe stage. Partial or
        UNKNOWN host effects remain HOLD. Failed intent and proof are retained
        in the same journal; no phase is sent a SKIP instruction.
        """
        driver, s = self.driver, self.s
        with driver.controls.install_lock():
            self.fence(attempt, 'RECONCILE')
            self._guard_native_effects(attempt)
            record = driver.journal_io.read_journal(s.OUTER_NAME)
            state = s.retained.BoundJournal._validate_record(record)['state']
            done = state.get('completed')
            need(type(done) is list and done == list(s.PHASES[:len(done)]), 'NATIVE_PHASE_ORDER')
            need(len(done) < 16 and state.get('stage') == s.PHASES[len(done)] + '_INTENT', 'RECOVERY_INTENT')
            phase = s.PHASES[len(done)]
            binding = {'outer_sha256': s.sha(record['data']), 'phase': phase,
                       'ledger_sha256': digest(self.ledger.snapshot())}
            proof = self.proof(attempt, 'reconcile_native_intent', binding)
            need(proof.get('binding') == binding and proof.get('status') in ('NO_WRITE','COMMITTED') and
                 type(proof.get('proof')) is dict and
                 proof['proof'].get('outcome') == 'SAFE_CHECKPOINT', 'RECOVERY_UNVERIFIED')
            checkpoint=(state.get('pending_components') if proof['status']=='COMMITTED' else state.get('component_checkpoint'))
            restored_done=done+[phase] if proof['status']=='COMMITTED' else done
            native_state.restore(driver,checkpoint,restored_done)
            journal=s.OuterJournal(driver.journal_io,driver.context,driver.gate.journal_binding())
            need(journal._read()==record,'RECOVERY_NATIVE_BINDING')
            journal.last = copy.deepcopy(record)
            if proof['status'] == 'COMMITTED':
                evidence = s.check_observation(proof.get('observation'), driver.context, phase)
                need(state.get('pending_observation')==evidence,'NATIVE_PENDING_EFFECT_MISMATCH')
                self.fence(attempt, 'RECOVERY_COMMIT')
                state['phase_evidence'][phase] = evidence
                state['completed'].append(phase)
            state['component_checkpoint']=checkpoint
            state.pop('pending_components',None);state.pop('pending_observation',None)
            state['stage'] = state['completed'][-1] + '_COMPLETE' if state['completed'] else 'ADMITTED'
            state.setdefault('attempt5_recoveries', []).append(
                {'attempt': attempt, 'intent_sha256': binding['outer_sha256'],
                 'proof_sha256': digest(proof), 'outcome': proof['status']})
            journal.save(state)
            # Checkpoint insertion on next adoption follows independently
            # authenticated native readback, including an interrupted commit.
            terminal = self.proof(attempt, 'commit_safe_reconciliation',
                                  {'outer_sha256': s.sha(journal.last['data']), 'proof': proof['proof']})
            need(terminal.get('status') == 'RECONCILED' and
                 terminal.get('proof') == proof['proof'], 'GLOBAL_RECONCILIATION_UNKNOWN')
            return self.ledger.reconcile(attempt, proof['proof'], lambda value: value == terminal['proof'])

    def run(self, attempt):
        driver, s = self.driver, self.s
        snapshot = self.ledger.snapshot()
        need(snapshot['attempts'] and snapshot['attempts'][-1]['id'] == attempt and
             snapshot['attempts'][-1]['state'] == 'INTENT_RECORDED', 'DURABLE_INTENT_REQUIRED')
        need(not driver.started, 'DRIVER_ALREADY_USED')
        driver.started = True
        lock = driver.controls.install_lock()
        with lock:
            self.fence(attempt, 'START')
            self._guard_native_effects(attempt)
            driver.check_binding()
            state = (self._adopt(attempt) if driver.journal_io.journal_exists(s.OUTER_NAME)
                     else self._initialize(attempt))
            try:
                for phase in s.PHASES[len(state['completed']):]:
                    self.fence(attempt, 'BEFORE_' + phase)
                    driver.diagnostics.start_scope('phase:' + phase)
                    state['stage'] = phase + '_INTENT'
                    self.journal.save(state)
                    driver.check_binding()
                    s.check_observation(driver.controls.before_phase(copy.deepcopy(driver.context), phase),
                                        driver.context, 'before:' + phase)
                    evidence = s.check_observation(driver.phase(phase), driver.context, phase)
                    need(driver.diagnostics.scope_failure is None, 'BOUNDED_COMMAND_FAILED')
                    s.check_observation(driver.controls.after_phase(copy.deepcopy(driver.context), phase,
                                        copy.deepcopy(evidence)), driver.context, 'after:' + phase)
                    state['pending_components']=native_state.capture(driver,state['completed']+[phase])
                    state['pending_observation']=evidence
                    self.journal.save(state)
                    self.fence(attempt, 'AFTER_' + phase)
                    fingerprint = digest(evidence)
                    proof = self.proof(attempt, 'verify_phase_commit',
                                       {'phase': phase, 'checkpoint_sha256': fingerprint})
                    need(proof.get('status') == 'VERIFIED' and
                         proof.get('checkpoint_sha256') == fingerprint, 'COMMIT_UNKNOWN')
                    state['phase_evidence'][phase] = evidence
                    state['completed'].append(phase)
                    state['stage'] = phase + '_COMPLETE'
                    state['component_checkpoint']=state.pop('pending_components')
                    state.pop('pending_observation')
                    self.journal.save(state)
                    self.ledger.checkpoint(attempt, phase, fingerprint)
                self.fence(attempt, 'FINISH')
                proof = self.proof(attempt, 'verify_terminal', {'outer_sha256': s.sha(self.journal.last['data'])})
                need(proof.get('status') == 'SUCCESS' and type(proof.get('proof')) is dict and
                     proof['proof'].get('outcome') == 'SUCCESS',
                     'TERMINAL_UNKNOWN')
                return self.ledger.reconcile(attempt, proof['proof'], lambda value: value == proof['proof'])
            except BaseException:
                # Durable intent already blocks another claim. Native containment
                # is retained; unknown outcomes cannot be reclassified as safe.
                self.ledger.uncertain(attempt, partial=True)
                s._cleanup(driver, state)
                raise
