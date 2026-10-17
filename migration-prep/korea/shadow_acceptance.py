"""Bounded, restart-resumable GET-only Shadow sampling and acceptance."""
from __future__ import print_function

import hashlib
import json
import math
import os
import stat
import threading
import time

from gate_common import canonical_bytes, require, sha256_value


ACCEPTANCE_FIELDS = frozenset((
    "schema_version", "feature_id", "window_id", "owner_approval_id",
    "owner_approved", "duration_seconds", "sample_interval_seconds",
    "minimum_samples", "max_failed_samples", "rss_peak_mib",
    "mem_available_floor_mib", "swap_growth_mib", "latency_p95_ms",
    "latency_p99_ms",
    "max_sample_gap_seconds", "max_restart_count",
))


def _secure_json(path):
    require(isinstance(path, str) and path.startswith("/"),
            "SHADOW_ACCEPTANCE_PATH_REQUIRED")
    require(os.path.isfile(path) and not os.path.islink(path),
            "SHADOW_ACCEPTANCE_REGULAR_FILE_REQUIRED")
    value = os.stat(path)
    require(stat.S_IMODE(value.st_mode) & 0o077 == 0,
            "SHADOW_ACCEPTANCE_MODE_TOO_BROAD")
    with open(path, "rb") as stream:
        raw = stream.read()
    require(raw and len(raw) <= 16384, "SHADOW_ACCEPTANCE_SIZE_INVALID")
    return json.loads(raw.decode("utf-8"))


def validate_acceptance_config(value):
    require(isinstance(value, dict) and frozenset(value) == ACCEPTANCE_FIELDS,
            "SHADOW_ACCEPTANCE_FIELDS_INVALID")
    require(value["schema_version"] == 1 and
            value["feature_id"] == "TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1",
            "SHADOW_ACCEPTANCE_SCHEMA_OR_FEATURE_INVALID")
    require(value["owner_approved"] is True and
            isinstance(value["owner_approval_id"], str) and value["owner_approval_id"],
            "SHADOW_ACCEPTANCE_OWNER_APPROVAL_REQUIRED")
    require(isinstance(value["window_id"], str) and value["window_id"] and
            all(character.isalnum() or character in "-_." for character in value["window_id"]),
            "SHADOW_ACCEPTANCE_WINDOW_ID_INVALID")
    integer_ranges = {
        "duration_seconds": (60, 7 * 24 * 3600),
        "sample_interval_seconds": (1, 3600),
        "minimum_samples": (2, 100000),
        "max_failed_samples": (0, 1000),
        "rss_peak_mib": (1, 65536),
        "mem_available_floor_mib": (1, 1048576),
        "swap_growth_mib": (0, 1048576),
        "latency_p95_ms": (1, 3600000),
        "latency_p99_ms": (1, 3600000),
        "max_sample_gap_seconds": (1, 7200),
        "max_restart_count": (0, 1000),
    }
    for name, bounds in integer_ranges.items():
        require(type(value[name]) is int and bounds[0] <= value[name] <= bounds[1],
                "SHADOW_ACCEPTANCE_THRESHOLD_INVALID:" + name)
    require(value["latency_p95_ms"] <= value["latency_p99_ms"],
            "SHADOW_ACCEPTANCE_LATENCY_ORDER_INVALID")
    possible = ((value["duration_seconds"] + value["sample_interval_seconds"] - 1) //
                value["sample_interval_seconds"])
    require(value["minimum_samples"] <= possible,
            "SHADOW_ACCEPTANCE_MINIMUM_SAMPLES_UNREACHABLE")
    require(value["max_failed_samples"] == 0,
            "SHADOW_FAILED_SAMPLES_CANNOT_BE_WAIVED")
    require(value["max_sample_gap_seconds"] <=
            value["sample_interval_seconds"] * 2,
            "SHADOW_MAX_GAP_TOO_BROAD")
    return value


def load_acceptance_config(path):
    return validate_acceptance_config(_secure_json(path))


def _read_integer(path):
    with open(path, "r", encoding="utf-8") as stream:
        return int(stream.read().strip())


def _bounded_cgroup_path(root, relative, controller=None):
    base = os.path.join(root, controller) if controller else root
    candidate = os.path.realpath(os.path.join(base, relative.lstrip("/")))
    real_base = os.path.realpath(base)
    require(candidate == real_base or candidate.startswith(real_base + os.sep),
            "SHADOW_CGROUP_PATH_INVALID")
    return candidate


def sample_resources(proc_root="/proc", cgroup_root="/sys/fs/cgroup"):
    values = {}
    with open(os.path.join(proc_root, "self/status"), "r", encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("VmRSS:"):
                values["rss_mib"] = int(line.split()[1]) / 1024.0
                break
    memory = {}
    with open(os.path.join(proc_root, "meminfo"), "r", encoding="utf-8") as stream:
        for line in stream:
            name, raw = line.split(":", 1)
            if name in ("MemAvailable", "SwapTotal", "SwapFree"):
                memory[name] = int(raw.split()[0]) / 1024.0
    require("rss_mib" in values and set(memory) == {"MemAvailable", "SwapTotal", "SwapFree"},
            "SHADOW_RESOURCE_SAMPLE_INCOMPLETE")
    values["mem_available_mib"] = memory["MemAvailable"]
    values["swap_used_mib"] = memory["SwapTotal"] - memory["SwapFree"]
    with open(os.path.join(proc_root, "self/cgroup"), "r", encoding="utf-8") as stream:
        entries = [line.strip().split(":", 2) for line in stream if line.strip()]
    require(entries and all(len(item) == 3 for item in entries),
            "SHADOW_CGROUP_MEMBERSHIP_UNAVAILABLE")
    unified = [item[2] for item in entries if item[0] == "0" and item[1] == ""]
    if len(unified) == 1:
        location = _bounded_cgroup_path(cgroup_root, unified[0])
        peak = _read_integer(os.path.join(location, "memory.peak"))
        with open(os.path.join(location, "memory.events"), "r", encoding="utf-8") as stream:
            events = dict(line.split() for line in stream if line.strip())
        require("oom" in events and "oom_kill" in events,
                "SHADOW_CGROUP_V2_OOM_FIELDS_MISSING")
        values["cgroup_version"] = "v2"
        values["cgroup_memory_peak_mib"] = peak / 1048576.0
        values["cgroup_oom"] = int(events["oom"]) + int(events["oom_kill"])
        values["cgroup_oom_semantics"] = "memory.events:oom+oom_kill"
    else:
        memory_entries = [item for item in entries if "memory" in item[1].split(",")]
        require(len(memory_entries) == 1, "SHADOW_CGROUP_MEMORY_CONTROLLER_UNAVAILABLE")
        location = _bounded_cgroup_path(cgroup_root, memory_entries[0][2], "memory")
        peak = _read_integer(os.path.join(location, "memory.max_usage_in_bytes"))
        failcnt = _read_integer(os.path.join(location, "memory.failcnt"))
        with open(os.path.join(location, "memory.oom_control"), "r", encoding="utf-8") as stream:
            oom_control = dict(line.split() for line in stream if line.strip())
        require("under_oom" in oom_control, "SHADOW_CGROUP_V1_OOM_FIELDS_MISSING")
        values["cgroup_version"] = "v1"
        values["cgroup_memory_peak_mib"] = peak / 1048576.0
        values["cgroup_oom"] = failcnt + int(oom_control["under_oom"])
        values["cgroup_oom_semantics"] = "memory.failcnt+memory.oom_control:under_oom"
    require(values["cgroup_memory_peak_mib"] >= 0 and values["cgroup_oom"] >= 0,
            "SHADOW_CGROUP_RESOURCE_VALUES_INVALID")
    values["cgroup_evidence_complete"] = True
    return values


def _validated_resource_sample(value):
    required = ("rss_mib", "mem_available_mib", "swap_used_mib",
                "cgroup_memory_peak_mib", "cgroup_oom", "cgroup_version",
                "cgroup_oom_semantics", "cgroup_evidence_complete")
    require(isinstance(value, dict) and all(name in value for name in required),
            "SHADOW_CGROUP_RESOURCE_EVIDENCE_UNAVAILABLE")
    require(value["cgroup_evidence_complete"] is True and
            value["cgroup_version"] in ("v1", "v2") and
            isinstance(value["cgroup_oom_semantics"], str) and value["cgroup_oom_semantics"],
            "SHADOW_CGROUP_RESOURCE_EVIDENCE_UNAVAILABLE")
    return value


def _percentile(values, percentile):
    require(values, "SHADOW_LATENCY_SAMPLES_REQUIRED")
    ordered = sorted(values)
    index = max(0, int(math.ceil((percentile / 100.0) * len(ordered))) - 1)
    return ordered[index]


def _state_path(config, acceptance):
    root = os.path.realpath(config["evidence_root"])
    require(os.path.isdir(root) and not os.path.islink(config["evidence_root"]),
            "SHADOW_EVIDENCE_ROOT_REQUIRED")
    return os.path.join(root, "shadow-window-" + acceptance["window_id"] + ".json")


def _tested_object(config):
    return {
        "runtime_config_sha256": sha256_value(config),
        "runtime_manifest_sha256": config["runtime_manifest_sha256"],
        "account_id": config["account_id"],
        "business_database": os.path.realpath(config["business_database"]),
        "verifier_sha256": config["verifier_sha256"],
        "snapshot_refresh_protocol": config["snapshot_refresh_protocol"],
        "snapshot_publisher_identity_sha256": config["snapshot_publisher_identity_sha256"],
    }


def _write_state(path, value, create=False):
    temporary = path + ".tmp-" + str(os.getpid())
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical_bytes(value) + b"\n")
            stream.flush(); os.fsync(stream.fileno())
        if create:
            require(not os.path.lexists(path), "SHADOW_WINDOW_STATE_ALREADY_EXISTS")
        os.replace(temporary, path)
        directory_fd = os.open(os.path.dirname(path), os.O_RDONLY)
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def _load_or_create_state(config, acceptance, now_ms, resources):
    path = _state_path(config, acceptance)
    config_sha = sha256_value(acceptance)
    tested_object = _tested_object(config)
    tested_object_sha = sha256_value(tested_object)
    if os.path.lexists(path):
        require(os.path.isfile(path) and not os.path.islink(path),
                "SHADOW_WINDOW_STATE_INVALID")
        with open(path, "rb") as stream:
            state = json.loads(stream.read().decode("utf-8"))
        require(state.get("acceptance_config_sha256") == config_sha and
                state.get("window_id") == acceptance["window_id"] and
                state.get("tested_object_sha256") == tested_object_sha and
                state.get("tested_object") == tested_object,
                "SHADOW_WINDOW_RESTART_CONFIG_MISMATCH")
        require(state.get("status") in ("RUNNING", "HOLD_INTERRUPTED"),
                "SHADOW_WINDOW_ALREADY_FINAL")
        state["restart_count"] += 1
        max_gap_ms = acceptance["max_sample_gap_seconds"] * 1000
        last = (state["samples"][-1]["sample_finished_ms"]
                if state["samples"] else state["started_at_ms"])
        blockers = []
        if now_ms > state["deadline_ms"]:
            blockers.append("SHADOW_WINDOW_EXPIRED_BEFORE_RESUME")
        if now_ms - last > max_gap_ms:
            blockers.append("SHADOW_CONTINUITY_GAP_EXCEEDED")
        if state["restart_count"] > acceptance["max_restart_count"]:
            blockers.append("SHADOW_RESTART_LIMIT_EXCEEDED")
        if blockers:
            state["status"] = "HOLD"; state["blockers"] = blockers
            state["resume_rejected_at_ms"] = now_ms
            state["evidence_sha256"] = sha256_value(state)
            _write_state(path, state)
            return path, state
        state["status"] = "RUNNING"
        return path, state
    state = {
        "schema_version": 1, "window_id": acceptance["window_id"],
        "owner_approval_id": acceptance["owner_approval_id"],
        "acceptance_config_sha256": config_sha,
        "tested_object": tested_object,
        "tested_object_sha256": tested_object_sha,
        "started_at_ms": now_ms,
        "deadline_ms": now_ms + acceptance["duration_seconds"] * 1000,
        "initial_swap_used_mib": resources["swap_used_mib"],
        "initial_cgroup_oom": resources.get("cgroup_oom", 0),
        "restart_count": 0, "samples": [], "status": "RUNNING",
        "production_authorized": False, "writer_enabled": False,
    }
    _write_state(path, state, create=True)
    return path, state


def _finalize(state, acceptance):
    samples = state["samples"]
    latencies = [sample["latency_ms"] for sample in samples]
    failures = [sample for sample in samples if not str(sample["cycle_status"]).startswith("PASS")]
    blockers = []
    max_gap_ms = acceptance["max_sample_gap_seconds"] * 1000
    if len(samples) < acceptance["minimum_samples"]:
        blockers.append("SHADOW_MINIMUM_SAMPLES_NOT_MET")
    if len(failures) > acceptance["max_failed_samples"]:
        blockers.append("SHADOW_FAILED_SAMPLE_LIMIT_EXCEEDED")
    if samples:
        gaps = [samples[0]["sample_started_ms"] - state["started_at_ms"]]
        gaps.extend(samples[index]["sample_started_ms"] - samples[index - 1]["sample_finished_ms"]
                    for index in range(1, len(samples)))
        gaps.append(state["deadline_ms"] - samples[-1]["sample_finished_ms"])
        state["maximum_observed_gap_ms"] = max(gaps)
        if max(gaps) > max_gap_ms:
            blockers.append("SHADOW_CONTINUITY_GAP_EXCEEDED")
        generations = [sample.get("snapshot_generation_id") for sample in samples]
        if any(not value for value in generations):
            blockers.append("SHADOW_SNAPSHOT_GENERATION_EVIDENCE_MISSING")
    if samples:
        if max(max(sample["resources"]["rss_mib"], sample["resources"].get("cgroup_memory_peak_mib", 0)) for sample in samples) > acceptance["rss_peak_mib"]:
            blockers.append("SHADOW_RSS_THRESHOLD_EXCEEDED")
        if any(sample["resources"].get("cgroup_oom", 0) > state.get("initial_cgroup_oom", 0)
               for sample in samples):
            blockers.append("SHADOW_CGROUP_OOM_OBSERVED")
        if min(sample["resources"]["mem_available_mib"] for sample in samples) < acceptance["mem_available_floor_mib"]:
            blockers.append("SHADOW_MEM_AVAILABLE_THRESHOLD_BREACHED")
        growth = max(sample["resources"]["swap_used_mib"] for sample in samples) - state["initial_swap_used_mib"]
        if growth > acceptance["swap_growth_mib"]:
            blockers.append("SHADOW_SWAP_GROWTH_THRESHOLD_EXCEEDED")
        if _percentile(latencies, 95) > acceptance["latency_p95_ms"]:
            blockers.append("SHADOW_LATENCY_P95_THRESHOLD_EXCEEDED")
        if _percentile(latencies, 99) > acceptance["latency_p99_ms"]:
            blockers.append("SHADOW_LATENCY_P99_THRESHOLD_EXCEEDED")
    state["blockers"] = blockers
    state["latency_p95_ms"] = _percentile(latencies, 95) if latencies else None
    state["latency_p99_ms"] = _percentile(latencies, 99) if latencies else None
    state["status"] = "PASS_SHADOW_WINDOW" if not blockers else "HOLD"
    state["completed_at_ms"] = state.get("last_sample_at_ms", state["deadline_ms"])
    state["evidence_sha256"] = sha256_value(state)
    return state


def run_continuous(config, acceptance, cycle_runner=None, clock_ms=None,
                   sleep_fn=None, resource_sampler=None):
    """Run bounded samples; restart reuses the same hash-bound window ledger."""
    validate_acceptance_config(acceptance)
    clock = clock_ms or (lambda: int(time.time() * 1000))
    sleeper = sleep_fn or time.sleep
    resources_fn = resource_sampler or sample_resources
    if cycle_runner is None:
        from korea.migration_shadow_entry import run_once
        cycle_runner = run_once
    initial_resources = _validated_resource_sample(resources_fn())
    path, state = _load_or_create_state(config, acceptance, clock(), initial_resources)
    if state["status"] == "HOLD":
        return state
    interval_ms = acceptance["sample_interval_seconds"] * 1000
    next_due = (state["samples"][-1]["sample_started_ms"] + interval_ms
                if state["samples"] else state["started_at_ms"])
    try:
        while clock() < state["deadline_ms"]:
            current = clock()
            if current < next_due:
                sleeper(min((next_due - current) / 1000.0, 1.0))
                continue
            before = clock()
            observations = [_validated_resource_sample(resources_fn())]; monitor_errors = []
            stop_monitor = threading.Event()
            def monitor():
                while not stop_monitor.wait(0.05):
                    try:
                        observations.append(_validated_resource_sample(resources_fn()))
                    except BaseException as error:
                        monitor_errors.append(type(error).__name__)
                        return
            monitor_thread = threading.Thread(target=monitor, name="shadow-resource-monitor")
            monitor_thread.daemon = True; monitor_thread.start()
            try:
                result = cycle_runner(config, now_ms=before)
            finally:
                stop_monitor.set(); monitor_thread.join(timeout=1.0)
                observations.append(_validated_resource_sample(resources_fn()))
            require(not monitor_errors, "SHADOW_RESOURCE_MONITOR_FAILED")
            require(len(set(value["cgroup_version"] for value in observations)) == 1 and
                    len(set(value["cgroup_oom_semantics"] for value in observations)) == 1,
                    "SHADOW_CGROUP_RESOURCE_EVIDENCE_CHANGED")
            after = clock()
            resources = {
                "rss_mib": max(value["rss_mib"] for value in observations),
                "cgroup_memory_peak_mib": max(value.get("cgroup_memory_peak_mib", value["rss_mib"]) for value in observations),
                "mem_available_mib": min(value["mem_available_mib"] for value in observations),
                "swap_used_mib": max(value["swap_used_mib"] for value in observations),
                "cgroup_oom": max(value.get("cgroup_oom", 0) for value in observations),
                "cgroup_version": observations[0]["cgroup_version"],
                "cgroup_oom_semantics": observations[0]["cgroup_oom_semantics"],
                "cgroup_evidence_complete": True,
                "sample_count": len(observations),
            }
            sample = {
                "sequence": len(state["samples"]) + 1,
                "sample_started_ms": before, "sample_finished_ms": after,
                "latency_ms": max(0, after - before),
                "cycle_status": result.get("status", "UNKNOWN"),
                "observation_run_id": result.get("observation_run_id"),
                "authoritative_business_snapshot_id":
                    result.get("authoritative_business_snapshot_id"),
                "snapshot_generation_id": result.get("snapshot_generation_id"),
                "resources": resources,
            }
            state["samples"].append(sample)
            state["last_sample_at_ms"] = after
            _write_state(path, state)
            hard_blockers = []
            if sample["cycle_status"] != "PASS_READONLY_SHADOW_CYCLE":
                hard_blockers.append("SHADOW_NONPASS_SAMPLE_FAIL_CLOSED:" + str(sample["cycle_status"]))
            if max(resources["rss_mib"], resources["cgroup_memory_peak_mib"]) > acceptance["rss_peak_mib"]:
                hard_blockers.append("SHADOW_RSS_THRESHOLD_EXCEEDED")
            if resources["mem_available_mib"] < acceptance["mem_available_floor_mib"]:
                hard_blockers.append("SHADOW_MEM_AVAILABLE_THRESHOLD_BREACHED")
            if resources["cgroup_oom"] > state.get("initial_cgroup_oom", 0):
                hard_blockers.append("SHADOW_CGROUP_OOM_OBSERVED")
            if after - before > acceptance["latency_p99_ms"]:
                hard_blockers.append("SHADOW_CYCLE_HARD_LATENCY_EXCEEDED")
            previous_generation = (state["samples"][-2].get("snapshot_generation_id")
                                   if len(state["samples"]) > 1 else None)
            if not sample["snapshot_generation_id"]:
                hard_blockers.append("SHADOW_SNAPSHOT_GENERATION_EVIDENCE_MISSING")
            elif previous_generation == sample["snapshot_generation_id"] and \
                    after - state["samples"][-2]["sample_finished_ms"] > config["snapshot_max_age_ms"]:
                hard_blockers.append("SHADOW_STATIC_SNAPSHOT_EXPIRED")
            if hard_blockers:
                state["status"] = "HOLD"
                state["blockers"] = hard_blockers
                state["hard_stopped_at_sequence"] = sample["sequence"]
                state["evidence_sha256"] = sha256_value(state)
                _write_state(path, state)
                return state
            next_due = before + interval_ms
        state = _finalize(state, acceptance)
        _write_state(path, state)
        return state
    except BaseException:
        state["status"] = "HOLD_INTERRUPTED"
        state["interrupted_at_ms"] = clock()
        _write_state(path, state)
        raise
