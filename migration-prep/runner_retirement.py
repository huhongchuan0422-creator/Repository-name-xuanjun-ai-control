"""G1 candidate: fail-safe production Runner retirement plan and verifier.

The module never obtains GitHub tokens and never runs commands by itself.  A
separately authorized root wrapper may consume the generated command plan.
"""
from __future__ import print_function

from gate_common import GateError, require


PHASES = ("BASELINED", "STOPPED", "UNINSTALLED", "DEREGISTERED", "SUDO_CLEANED", "VERIFIED")


def command_plan(host, runner, residue):
    work = runner["working_directory"]
    unit = runner["service"]
    return [
        {"phase": "BASELINED", "command": ["systemctl", "show", unit], "mutating": False},
        {"phase": "STOPPED", "command": [work + "/svc.sh", "stop"], "mutating": True},
        {"phase": "UNINSTALLED", "command": [work + "/svc.sh", "uninstall"], "mutating": True},
        {"phase": "DEREGISTERED", "run_as": runner["user"],
         "command": [work + "/config.sh", "remove", "--token", "<PROTECTED_SHORT_LIVED_REMOVE_TOKEN>"],
         "mutating": True},
        {"phase": "SUDO_CLEANED", "command": ["unlink", residue["sudoers_dropin"]], "mutating": True},
        {"phase": "SUDO_CLEANED", "command": ["unlink", residue["helper"]], "mutating": True},
        {"phase": "SUDO_CLEANED", "command": ["visudo", "-c"], "mutating": False},
        {"phase": "VERIFIED", "command": ["systemctl", "is-enabled", unit], "expect": "not-found", "mutating": False},
        {"phase": "VERIFIED", "command": ["systemctl", "is-active", unit], "expect": "inactive-or-not-found", "mutating": False},
        {"phase": "VERIFIED", "command": ["test", "!", "-e", runner["service_path"]], "mutating": False},
        {"phase": "VERIFIED", "command": ["test", "!", "-e", residue["sudoers_dropin"]], "mutating": False},
        {"phase": "VERIFIED", "command": ["test", "!", "-e", residue["helper"]], "mutating": False},
        {"phase": "VERIFIED", "check": "github_admin_runner_agent_absent", "agent_id": runner["agent_id"]},
        {"phase": "VERIFIED", "check": "ssh_openclaw_canary_preserved", "host": host["hostname"]}
    ]


def evaluate(host, observation):
    required = (
        "hostname", "runner_agent_id", "runner_name", "runner_pool", "phase",
        "unit_active", "unit_enabled", "listener_processes", "autostart_entries",
        "github_registration_present", "helper_present", "sudoers_dropin_present",
        "ssh_openclaw_canary", "production_services_unchanged", "timed_out",
        "partial_success"
    )
    for key in required:
        require(key in observation, "G1_MISSING:" + key)
    runner = host["runner"]
    require(observation["hostname"] == host["hostname"], "G1_HOST_MISMATCH")
    require(observation["runner_agent_id"] == runner["agent_id"], "G1_AGENT_ID_MISMATCH")
    require(observation["runner_name"] == runner["name"], "G1_RUNNER_NAME_MISMATCH")
    require(observation["runner_pool"] == "Default", "G1_POOL_DRIFT")
    require(observation["phase"] in PHASES, "G1_PHASE_INVALID")
    if observation["timed_out"] or observation["partial_success"]:
        return {"status": "HOLD", "reason": "G1_UNCERTAIN_OR_PARTIAL", "next": "INSPECT_ONLY_NO_BLIND_RETRY"}
    if observation["phase"] != "VERIFIED":
        return {"status": "HOLD", "reason": "G1_NOT_COMPLETE", "next": PHASES[PHASES.index(observation["phase"]) + 1]}
    checks = [
        not observation["unit_active"], not observation["unit_enabled"],
        observation["listener_processes"] == 0, observation["autostart_entries"] == 0,
        not observation["github_registration_present"], not observation["helper_present"],
        not observation["sudoers_dropin_present"], observation["ssh_openclaw_canary"],
        observation["production_services_unchanged"]
    ]
    require(all(checks), "G1_RESIDUE_OR_CHANNEL_FAILURE")
    return {"status": "PASS_CANDIDATE_EVIDENCE", "production_authority": False}


def enforce_order(completed, requested):
    require(requested in PHASES, "G1_PHASE_INVALID")
    completed = list(completed)
    if requested in completed:
        return "REPLAY_NOOP"
    expected = PHASES[len(completed)] if len(completed) < len(PHASES) else None
    require(requested == expected, "G1_PHASE_ORDER_VIOLATION")
    return "EXECUTE_ONCE"
