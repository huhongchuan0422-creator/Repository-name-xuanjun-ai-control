"""Bounded, restart-resumable GET-only Shadow sampling and acceptance."""
from __future__ import print_function

import hashlib
import json
import math
import os
import stat
import time

from gate_common import canonical_bytes, require, sha256_value


ACCEPTANCE_FIELDS = frozenset((
    "schema_version", "feature_id", "window_id", "owner_approval_id",
    "owner_approved", "duration_seconds", "sample_interval_seconds",
    "minimum_samples", "max_failed_samples", "rss_peak_mib",
    "mem_available_floor_mib", "swap_growth_mib", "latency_p95_ms",
    "latency_p99_ms",
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
    return value


def load_acceptance_config(path):
    return validate_acceptance_config(_secure_json(path))


def sample_resources():
    values = {}
    with open("/proc/self/status", "r", encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("VmRSS:"):
                values["rss_mib"] = int(line.split()[1]) / 1024.0
                break
    memory = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as stream:
        for line in stream:
            name, raw = line.split(":", 1)
            if name in ("MemAvailable", "SwapTotal", "SwapFree"):
                memory[name] = int(raw.split()[0]) / 1024.0
    require("rss_mib" in values and set(memory) == {"MemAvailable", "SwapTotal", "SwapFree"},
            "SHADOW_RESOURCE_SAMPLE_INCOMPLETE")
    values["mem_available_mib"] = memory["MemAvailable"]
    values["swap_used_mib"] = memory["SwapTotal"] - memory["SwapFree"]
    return values


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
    if os.path.lexists(path):
        require(os.path.isfile(path) and not os.path.islink(path),
                "SHADOW_WINDOW_STATE_INVALID")
        with open(path, "rb") as stream:
            state = json.loads(stream.read().decode("utf-8"))
        require(state.get("acceptance_config_sha256") == config_sha and
                state.get("window_id") == acceptance["window_id"],
                "SHADOW_WINDOW_RESTART_CONFIG_MISMATCH")
        require(state.get("status") in ("RUNNING", "HOLD_INTERRUPTED"),
                "SHADOW_WINDOW_ALREADY_FINAL")
        state["restart_count"] += 1
        state["status"] = "RUNNING"
        return path, state
    state = {
        "schema_version": 1, "window_id": acceptance["window_id"],
        "owner_approval_id": acceptance["owner_approval_id"],
        "acceptance_config_sha256": config_sha,
        "started_at_ms": now_ms,
        "deadline_ms": now_ms + acceptance["duration_seconds"] * 1000,
        "initial_swap_used_mib": resources["swap_used_mib"],
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
    if len(samples) < acceptance["minimum_samples"]:
        blockers.append("SHADOW_MINIMUM_SAMPLES_NOT_MET")
    if len(failures) > acceptance["max_failed_samples"]:
        blockers.append("SHADOW_FAILED_SAMPLE_LIMIT_EXCEEDED")
    if samples:
        if max(sample["resources"]["rss_mib"] for sample in samples) > acceptance["rss_peak_mib"]:
            blockers.append("SHADOW_RSS_THRESHOLD_EXCEEDED")
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
    initial_resources = resources_fn()
    path, state = _load_or_create_state(config, acceptance, clock(), initial_resources)
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
            result = cycle_runner(config, now_ms=before)
            after = clock()
            sample = {
                "sequence": len(state["samples"]) + 1,
                "sample_started_ms": before, "sample_finished_ms": after,
                "latency_ms": max(0, after - before),
                "cycle_status": result.get("status", "UNKNOWN"),
                "observation_run_id": result.get("observation_run_id"),
                "authoritative_business_snapshot_id":
                    result.get("authoritative_business_snapshot_id"),
                "resources": resources_fn(),
            }
            state["samples"].append(sample)
            state["last_sample_at_ms"] = after
            _write_state(path, state)
            if sample["cycle_status"] == "UNKNOWN":
                state["status"] = "HOLD"
                state["blockers"] = ["SHADOW_UNKNOWN_SAMPLE_FAIL_CLOSED"]
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
