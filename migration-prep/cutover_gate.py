"""G5 candidate: isolated Korea deployment, shadow/canary and rollback gates."""
from __future__ import print_function

from gate_common import next_phase_action, require, validate_phase_history


FORWARD_PHASES = (
    "KOREA_ISOLATED_DEPLOYED", "RUNTIME_VERIFIED", "SHADOW_PASS",
    "TOKYO_FENCED", "FINAL_CHECKPOINT_VERIFIED", "KOREA_AUTHORITY_GRANTED",
    "BOUNDED_CANARY_PASS", "OBSERVATION_PASS"
)

ROLLBACK_PHASES = (
    "KOREA_WRITER_LOCKED", "KOREA_CREDENTIAL_REVOKED", "KOREA_IP_REMOVED",
    "UNKNOWN_OUTCOMES_RECONCILED", "TOKYO_CHECKPOINT_RESTORED",
    "TOKYO_GET_ONLY_RECONCILED", "TOKYO_NEW_EPOCH_GRANTED"
)


def evaluate_isolation(observation):
    required = (
        "dedicated_user", "dedicated_directories", "dedicated_secret_namespace",
        "ports_non_overlapping", "runtime_versions_match", "dependencies_verified",
        "permissions_verified", "network_get_only_verified", "novel_unchanged",
        "postgres_unchanged", "redis_unchanged", "writer_enabled", "scheduler_enabled",
        "trade_credentials_present"
    )
    for key in required:
        require(key in observation, "G5_ISOLATION_MISSING:" + key)
    protected_and_required = (
        "dedicated_user", "dedicated_directories", "dedicated_secret_namespace",
        "ports_non_overlapping", "runtime_versions_match", "dependencies_verified",
        "permissions_verified", "network_get_only_verified", "novel_unchanged",
        "postgres_unchanged", "redis_unchanged"
    )
    for key in protected_and_required:
        require(observation[key] is True, "G5_ISOLATION_REQUIREMENT_FAILED:" + key)
    require(observation["writer_enabled"] is False, "G5_WRITER_MUST_BE_DISABLED")
    require(observation["scheduler_enabled"] is False, "G5_SCHEDULER_MUST_BE_DISABLED")
    require(observation["trade_credentials_present"] is False,
            "G5_TRADE_CREDENTIALS_FORBIDDEN")
    return {"status": "PASS_ISOLATED_CANDIDATE", "production_write": False}


def evaluate_shadow(observation):
    required = (
        "no_order_write", "same_inputs", "decision_match", "position_match", "order_match",
        "protective_match", "unknown_count", "inflight_count", "restart_recovered",
        "duration_met", "timed_out", "partial_success"
    )
    for key in required:
        require(key in observation, "G5_SHADOW_MISSING:" + key)
    boolean_fields = (
        "no_order_write", "same_inputs", "decision_match", "position_match",
        "order_match", "protective_match", "restart_recovered", "duration_met",
        "timed_out", "partial_success"
    )
    for key in boolean_fields:
        require(type(observation[key]) is bool, "G5_SHADOW_BOOLEAN_REQUIRED:" + key)
    for key in ("unknown_count", "inflight_count"):
        require(type(observation[key]) is int and observation[key] >= 0,
                "G5_SHADOW_COUNT_INVALID:" + key)
    if observation["timed_out"] is True or observation["partial_success"] is True:
        return {"status": "HOLD", "reason": "G5_SHADOW_UNCERTAIN_OR_PARTIAL"}
    require(observation["no_order_write"] is True, "G5_SHADOW_WRITE_DETECTED")
    require(all(observation[key] is True for key in
                ("same_inputs", "decision_match", "position_match", "order_match",
                 "protective_match", "restart_recovered", "duration_met")),
            "G5_SHADOW_MISMATCH")
    require(observation["unknown_count"] == 0 and observation["inflight_count"] == 0, "G5_SHADOW_UNRESOLVED")
    return {"status": "PASS_SHADOW_CANDIDATE", "production_write": False}


def advance(history, requested, rollback=False):
    phases = ROLLBACK_PHASES if rollback else FORWARD_PHASES
    return next_phase_action(phases, history, requested, "G5")


def rollback_verdict(history):
    assessment = validate_phase_history(ROLLBACK_PHASES, history, "G5_ROLLBACK")
    completed = assessment["completed"]
    if "TOKYO_NEW_EPOCH_GRANTED" in completed:
        required = set(ROLLBACK_PHASES[:-1])
        require(required.issubset(set(completed)), "G5_TOKYO_REGRANT_BEFORE_KOREA_FENCE")
    korea_fenced = all(phase in completed for phase in ROLLBACK_PHASES[:3])
    return {"status": "CANDIDATE_READY_TO_RESTORE_TOKYO_NOT_AUTHORIZED" if korea_fenced else "HOLD",
            "korea_fenced_first": korea_fenced, "history_status": assessment["status"],
            "production_authorized": False}


def uncertain_outcome(reason):
    return {
        "status": "HOLD",
        "reason": reason,
        "required_order": ["LOCK_KOREA", "REVOKE_KOREA_CREDENTIAL", "REMOVE_KOREA_IP",
                           "GET_ONLY_RECONCILE_UNKNOWN", "ONLY_THEN_CONSIDER_TOKYO_RESTORE"],
        "double_writer_allowed": False
    }
