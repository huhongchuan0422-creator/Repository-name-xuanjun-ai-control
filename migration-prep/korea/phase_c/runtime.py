"""Wire existing reconciliation and window ledger to authenticated generations/GET.

No default production configuration or implicit approval. Tests inject synthetic
collectors/resources; live entry additionally requires an independent, expiring
execution admission and the exact account/network/custody/runtime bindings.
"""
import os
from pathlib import Path
import time

from final_snapshot import REQUIRED_SURFACES
from gate_common import require
from korea.migration_shadow_entry import _hard_deadline
from korea.phase_c.network import validate_policy
from korea.phase_c.security import fsync_dir, hash_value, identifier
from korea.phase_c.snapshots import pin_current
from korea.shadow_acceptance import run_continuous, validate_acceptance_config
from readonly_reconciliation_adapter import (AuthenticatedGetOnlyPager, EvidenceDirectory,
    ReadOnlyBusinessDatabase, SYMBOLS, evaluate_reconciliation)


def verify_admission(admission, signature, public_verifier, config, acceptance, now_ms, host):
    expected = {"schema_version", "action", "host", "window_id", "config_sha256",
                "acceptance_sha256", "issued_at_ms", "expires_at_ms", "approval_comment_id",
                "network_enforcement_verified", "credential_readonly_verified",
                "source_identity_verified", "max_attempts"}
    require(isinstance(admission, dict) and set(admission) == expected, "C_ADMISSION_FIELDS")
    require(admission["schema_version"] == 1 and
            admission["action"] == "PR99_PHASE_C_READONLY_SHADOW_V1" and
            admission["host"] == host == "iZmj7a5kwr75qc1tul4kf9Z" and
            admission["window_id"] == acceptance["window_id"] and
            admission["config_sha256"] == hash_value(config) and
            admission["acceptance_sha256"] == hash_value(acceptance) and
            type(admission["approval_comment_id"]) is int and admission["approval_comment_id"] > 0 and
            admission["max_attempts"] == 1 and
            all(admission[k] is True for k in ("network_enforcement_verified",
                "credential_readonly_verified", "source_identity_verified")), "C_ADMISSION_BINDING")
    require(type(admission["issued_at_ms"]) is int and type(admission["expires_at_ms"]) is int and
            admission["issued_at_ms"] <= now_ms < admission["expires_at_ms"] and
            admission["expires_at_ms"] - admission["issued_at_ms"] <= 7 * 86400000 and
            now_ms + acceptance["duration_seconds"] * 1000 <= admission["expires_at_ms"],
            "C_ADMISSION_WINDOW_EXPIRED")
    require(public_verifier.verify(admission, signature), "C_ADMISSION_SIGNATURE")
    validate_policy(config["network_policy"], now_ms)
    require(config["network_policy"]["expires_at_ms"] >= admission["expires_at_ms"],
            "C_NETWORK_WINDOW_TOO_SHORT")
    validate_acceptance_config(acceptance)
    require(config["writer_enabled"] is False and config["scheduler_enabled"] is False and
            config["credential_role"] == "BINANCE_ACCOUNT_READONLY" and
            config["snapshot_reader_uid"] == config["network_policy"]["worker_uid"],
            "C_WORKER_ROLE_BINDING")


def run_cycle(config, source_verifier, client_factory, now_ms=None, clock_ms=None,
              generation_pin=None):
    clock = clock_ms or (lambda: int(time.time() * 1000))
    started = clock() if now_ms is None else now_ms
    directory = EvidenceDirectory(config["evidence_root"], config["business_database"])
    run_id = "shadow-observation-" + str(started)
    run_dir = directory.create_run(run_id)
    admitted = database = None
    try:
        with _hard_deadline(config["capture_timeout_ms"] / 1000.0):
            _, receipt, admitted = (generation_pin or pin_current)(
                config["snapshot_root"], config, source_verifier, started)
            authenticated = admitted.materialize(run_dir)
            database = ReadOnlyBusinessDatabase(authenticated["path"], run_dir, config["account_id"],
                                                None, started, config["snapshot_max_age_ms"])
            local = database.snapshot()
            client = client_factory(run_id)
            pager = AuthenticatedGetOnlyPager(client, client.verify_receipt, clock,
                                             started + config["capture_timeout_ms"])
            surfaces = {surface: pager.collect(surface, SYMBOLS, config["account_id"], local["snapshot_id"])
                        for surface in REQUIRED_SURFACES}
            finished = clock()
            blockers = evaluate_reconciliation(local, surfaces, pager.calls, started, started,
                                               finished, max_capture_ms=config["capture_timeout_ms"],
                                               require_authenticated=True)
            stable = database.close_and_verify()
            require(stable["source_stable_through_read"], "C_MATERIALIZED_SNAPSHOT_CHANGED")
            result = {"status": "HOLD" if blockers else "PASS_READONLY_SHADOW_CYCLE",
                      "blockers": blockers, "observation_run_id": run_id,
                      "authoritative_business_snapshot_id": local["snapshot_id"],
                      "snapshot_generation_id": receipt["snapshot_generation_id"],
                      "production_authorized": False, "writer_enabled": False}
            directory.write_once(run_dir, "exchange-pages.json", surfaces)
            directory.write_once(run_dir, "local-state.json", local)
            directory.write_once(run_dir, "reconciliation.json", result)
            return result
    except Exception as error:
        failure = {"status": "HOLD", "error_type": type(error).__name__,
                   "observation_run_id": run_id, "production_authorized": False}
        try:
            directory.write_once(run_dir, "reconciliation.json", failure)
        except Exception:
            pass
        return failure
    finally:
        if database is not None:
            database.connection.close()
        if admitted is not None:
            admitted.close()


def run_window(config, acceptance, admission, signature, authority, source_verifier,
               client_factory, clock_ms=None, sleep_fn=None, resource_sampler=None,
               host=None):
    clock = clock_ms or (lambda: int(time.time() * 1000))
    verify_admission(admission, signature, authority, config, acceptance, clock(),
                     host or os.uname().nodename)
    require(os.geteuid() == config["network_policy"]["worker_uid"], "C_WORKER_PROCESS_UID")
    evidence = Path(config["evidence_root"])
    require(evidence.is_dir() and not evidence.is_symlink(), "C_EVIDENCE_DIRECTORY")
    # A permanent O_EXCL attempt blocks a second process even after an interrupted
    # first invocation. Future recovery needs another exact reviewed authorization.
    attempt = evidence / ("phase-c-attempt-" + identifier(acceptance["window_id"]))
    fd = os.open(attempt, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.fsync(fd)
    os.close(fd)
    fsync_dir(evidence)
    generations = set()
    def cycle(base, now_ms):
        require(now_ms < admission["expires_at_ms"], "C_ADMISSION_EXPIRED_DURING_WINDOW")
        validate_policy(base["network_policy"], now_ms)
        # Claim generation before any network request; never turn duplicate or
        # unknown ACK into another capture/GET attempt.
        pinned, receipt, held = pin_current(base["snapshot_root"], base, source_verifier, now_ms)
        held.close()
        require(receipt["snapshot_generation_id"] not in generations, "C_FRESH_GENERATION_REQUIRED")
        generations.add(receipt["snapshot_generation_id"])
        # Fix this generation for the complete cycle, even if current changes.
        from korea.phase_c.snapshots import verify_generation
        def fixed_pin(root, cfg, verifier, observed):
            return verify_generation(root, receipt["snapshot_generation_id"], cfg, verifier, observed)
        return run_cycle(base, source_verifier, client_factory, now_ms=now_ms, clock_ms=clock,
                         generation_pin=fixed_pin)
    return run_continuous(config, acceptance, cycle_runner=cycle, clock_ms=clock,
                          sleep_fn=sleep_fn, resource_sampler=resource_sampler)
