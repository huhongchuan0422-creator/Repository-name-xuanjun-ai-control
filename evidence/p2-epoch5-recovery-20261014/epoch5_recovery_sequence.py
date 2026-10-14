"""Single-attempt epoch5 recovery sequencing; no default production driver.

This reuses the original installation transaction's protected journal directory.
The injected driver must implement the existing install lock, exact independent
approval checks, bounded live preflight, publication and containment operations.
No CLI or fallback driver is supplied: wiring is not production-ready yet.
"""

PHASES = (
    'stage_exact_release',
    'preserve_prior_receipts',
    'rebind_prepared_epoch',
    'quiesce_exact_epoch',
    'provision_from_retained_resources',
    'reopen_existing_database',
    'activate_exact_epoch',
    'activate_new_services',
    'post_install_checks',
)


class RecoveryHold(RuntimeError):
    pass


class ContainmentIncomplete(RuntimeError):
    """Bounded operation evidence to preserve with an UNKNOWN durable result."""
    def __init__(self, evidence):
        super(ContainmentIncomplete, self).__init__('FAILURE_CONTAINMENT_INCOMPLETE')
        self.evidence = evidence


def resume_once(driver, plan, approval):
    """Run one admitted attempt; failures retain resources and never retry.

    Required journal methods: create_attempt must be O_EXCL + fsync, save_attempt
    must atomically replace + fsync in the same existing transaction directory.
    The driver must reject any existing attempt before mutation. Approval is
    checked before and inside the install lock, around a fresh live snapshot.
    Each effect method must return a JSON-serializable evidence dict, not True.
    """
    driver.verify_approval(plan, approval)
    with driver.install_lock():
        snapshot = driver.preflight(plan)
        driver.verify_approval(plan, approval)
        driver.verify_snapshot_binding(snapshot, approval)
        state = {'schema': 1, 'stage': 'ADMITTED', 'automatic_retry': False,
                 'completed': [], 'phase_evidence': {}, 'containment': {},
                 'retained_prerequisites': True, 'historical_replay': False,
                 'legacy_restart': False, 'production_acceptance': 'PENDING'}
        # Never catch/create over an existing attempt. No effects before this.
        driver.create_attempt(state, plan, approval, snapshot)
        try:
            for phase in PHASES:
                state['stage'] = phase + '_INTENT'
                driver.save_attempt(state)
                evidence = getattr(driver, phase)(plan)
                if not isinstance(evidence, dict) or not evidence:
                    raise RecoveryHold('MISSING_PHASE_EVIDENCE:' + phase)
                state['phase_evidence'][phase] = evidence
                state['completed'].append(phase)
                state['stage'] = phase + '_COMPLETE'
                driver.save_attempt(state)
            state['stage'] = 'COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE'
            driver.save_attempt(state)
            return state
        except BaseException as error:
            # A phase may have had effects even if it returned no evidence.
            # Fence first, then stop exact new services regardless of fence result.
            # No generic runtime.restore: it could erase retained bootstrap/NSS.
            state['stage'] = 'HOLD'
            state['error_type'] = type(error).__name__
            for operation in ('fence_uncertain_activation', 'stop_exact_new_services',
                              'verify_stopped_and_preserve_legacy_masks'):
                try:
                    result = getattr(driver, operation)(plan)
                    if not isinstance(result, dict) or not result:
                        raise RecoveryHold('MISSING_CONTAINMENT_EVIDENCE')
                    state['containment'][operation] = {'status': 'OBSERVED', 'evidence': result}
                except BaseException as containment_error:
                    state['containment'][operation] = {'status': 'UNKNOWN',
                                                       'error_type': type(containment_error).__name__}
                    if isinstance(containment_error, ContainmentIncomplete):
                        state['containment'][operation]['evidence'] = containment_error.evidence
            state['recovery'] = 'MANUAL_RECONCILIATION_REQUIRED_NO_RESTART'
            try:
                driver.save_attempt(state)
            except BaseException:
                # Durable phase INTENT remains; caller must report journal unknown.
                raise RecoveryHold('RECOVERY_HOLD_FINAL_RECEIPT_UNAVAILABLE') from error
            raise RecoveryHold('RECOVERY_HOLD_RETAINED_RESOURCES_NO_RETRY') from error
