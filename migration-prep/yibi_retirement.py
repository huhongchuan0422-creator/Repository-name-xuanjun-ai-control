"""G2 candidate: permanent Yibi retirement without touching shared services."""
from __future__ import print_function

from gate_common import require


PHASES = ("ARCHIVE_VERIFIED", "TRIGGERS_FROZEN", "SERVICES_STOPPED", "UNITS_DISABLED", "UNITS_MASKED", "VERIFIED")


def retirement_plan(yibi):
    units = list(yibi["timers"]) + list(yibi["services"])
    commands = []
    for unit in yibi["timers"]:
        commands.append({"phase": "TRIGGERS_FROZEN", "command": ["systemctl", "stop", unit]})
    for unit in yibi["services"]:
        commands.append({"phase": "SERVICES_STOPPED", "command": ["systemctl", "stop", unit]})
    for unit in units:
        commands.append({"phase": "UNITS_DISABLED", "command": ["systemctl", "disable", unit]})
    for unit in units:
        commands.append({"phase": "UNITS_MASKED", "command": ["systemctl", "mask", unit]})
    commands.append({"phase": "VERIFIED", "check": "no_yibi_process_listener_timer_cron_openclaw_trigger"})
    commands.append({"phase": "VERIFIED", "check": "protected_units_pre_post_equal",
                     "protected_units": yibi["protected_units"]})
    return commands


def evaluate(yibi, observation):
    require(yibi["policy"] == "ARCHIVE_ONLY_NEVER_REENABLE", "G2_POLICY_MISMATCH")
    required = (
        "phase", "archive_identity_verified", "active_units", "enabled_units", "masked_units",
        "processes", "listeners", "timer_triggers", "cron_triggers", "openclaw_triggers",
        "openclaw_inventory_complete", "protected_units_pre", "protected_units_post",
        "postgres_data_identity_unchanged", "redis_identity_unchanged", "novel_identity_unchanged",
        "timed_out", "partial_success"
    )
    for key in required:
        require(key in observation, "G2_MISSING:" + key)
    if observation["timed_out"] or observation["partial_success"]:
        return {"status": "HOLD", "reason": "G2_UNCERTAIN_OR_PARTIAL", "re_enable_yibi": False}
    if not observation["openclaw_inventory_complete"]:
        return {"status": "HOLD", "reason": "G2_OPENCLAW_TRIGGER_INVENTORY_INCOMPLETE", "re_enable_yibi": False}
    require(observation["phase"] == "VERIFIED", "G2_NOT_COMPLETE")
    require(observation["archive_identity_verified"], "G2_ARCHIVE_IDENTITY_UNVERIFIED")
    require(observation["active_units"] == [], "G2_ACTIVE_UNITS_REMAIN")
    require(observation["enabled_units"] == [], "G2_ENABLED_UNITS_REMAIN")
    require(sorted(observation["masked_units"]) == sorted(yibi["services"] + yibi["timers"]), "G2_MASK_INCOMPLETE")
    require(all(observation[name] == 0 for name in ("processes", "listeners", "timer_triggers", "cron_triggers", "openclaw_triggers")), "G2_TRIGGER_REMAINS")
    require(observation["protected_units_pre"] == observation["protected_units_post"], "G2_SHARED_SERVICE_CHANGED")
    require(observation["postgres_data_identity_unchanged"], "G2_POSTGRES_CHANGED")
    require(observation["redis_identity_unchanged"], "G2_REDIS_CHANGED")
    require(observation["novel_identity_unchanged"], "G2_NOVEL_CHANGED")
    return {"status": "PASS_CANDIDATE_EVIDENCE", "archive_only": True, "re_enable_yibi": False}


def enforce_order(completed, requested):
    require(requested in PHASES, "G2_PHASE_INVALID")
    completed = list(completed)
    if requested in completed:
        return "REPLAY_NOOP"
    require(len(completed) < len(PHASES) and requested == PHASES[len(completed)], "G2_PHASE_ORDER_VIOLATION")
    return "EXECUTE_ONCE"


def failure_recovery():
    return {
        "rule": "DO_NOT_REENABLE_YIBI",
        "actions": ["inspect_failed_unit", "restore_only_novel_or_shared_dependency_if_changed", "keep_all_completed_yibi_masks"],
        "forbidden": ["start_yibi", "enable_yibi", "unmask_yibi", "restore_yibi_to_production"]
    }
