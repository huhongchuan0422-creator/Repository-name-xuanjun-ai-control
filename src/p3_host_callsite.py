"""Bounded P3 callsite for the one already-admitted original host.

This module does not create a ledger, runner, provider, service, or task.  The
default configuration is inert.  A host may compose the reviewed boundaries
only after the exact loaded source bytes are verified and the existing host's
admission reader proves both P2 acceptance and an explicit P3 release.
"""
from __future__ import absolute_import

import hashlib
import importlib
import os

try:
    from p3_host_boundaries import (
        AdmissionGate, EvidenceReaders, OutboxController, ReceiptVerifier,
        RunnerController,
    )
except ImportError:  # package-form local tests; installed host uses flat modules
    from .p3_host_boundaries import (
        AdmissionGate, EvidenceReaders, OutboxController, ReceiptVerifier,
        RunnerController,
    )


EXPECTED_MODULE_SHA256 = {
    "p3_host_boundaries": "aa06589ab51298cd64ecd4ac8bb9af8746c692e6db7205da191ce7c718dfb17f",
    "p3_host_wiring": "e5b062ae99cbf2c5d8084c268de7da3dd72fa01de60e0200821892aa84ac49af",
    "p3_lifecycle": "d330b85d453d0d293cb62bbc931b1670d22f2112815ac84bf09d229021d02e30",
    "p3_owner_reminders": "ef52c2727978e6578d8875d2ff6212b5539fe3f42777bd4be0179cbb17094499",
    "activation_control": "169a30ee858ef0e1ecb0b366702f35463993db34042410a43bc98018a9471eb4",
}

DEFAULT_OFF_CONFIG = {
    "execution_enabled": False,
    "notifications_enabled": False,
}


def _sha256(path):
    value = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if not os.path.isfile(path) or info.st_size > 4 * 1024 * 1024:
            raise ValueError("INVALID_LOADED_MODULE")
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            value.update(chunk)
    finally:
        os.close(descriptor)
    return value.hexdigest()


def verify_loaded_sources(modules=None):
    """Verify the actual imported modules, not delivery-side dictionaries."""
    if modules is None:
        modules = {}
    observed = {}
    for name, expected in EXPECTED_MODULE_SHA256.items():
        module = modules.get(name) or importlib.import_module(name)
        raw_path = getattr(module, "__file__", "")
        path = os.path.realpath(raw_path)
        if (not raw_path or not os.path.isabs(raw_path)
                or raw_path != path or os.path.islink(raw_path)):
            raise ValueError("LOADED_MODULE_PATH_INVALID:%s" % name)
        digest = _sha256(path)
        if digest != expected:
            raise ValueError("LOADED_MODULE_SHA256_MISMATCH:%s" % name)
        observed[name] = {"path": path, "sha256": digest}
    return observed


def _config(value):
    keys = {
        "execution_enabled", "notifications_enabled", "task_to_blocker",
        "ratio_bands", "worker_prefix",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("EXACT_P3_HOST_CONFIG_REQUIRED")
    if (type(value["execution_enabled"]) is not bool
            or type(value["notifications_enabled"]) is not bool):
        raise ValueError("BOOLEAN_ENABLE_REQUIRED")
    if value["notifications_enabled"] and not value["execution_enabled"]:
        raise ValueError("EXECUTION_ADMISSION_REQUIRED")
    return value


def compose_existing_p3_host(
        existing_p3_ledger, pipeline_factory, config, admission_reader, clock,
        progress_subject=None, stop_subject=None, acceptance_index=None,
        completion_index=None, receipt_provider=None, runner_adapter=None,
        outbox_transport=None, executor=None, event_reader=None,
        eligibility_reader=None, notification_adapter=None, subject=None,
        modules=None):
    """Compose the frozen callsite, or return an inert readback while disabled.

    ``existing_p3_ledger`` is mandatory even while disabled so callers cannot
    use this entry to bootstrap a parallel ledger.  Enabling is host-only: the
    exact current run subject and an admission reader are rechecked before the
    original composition entry can run.
    """
    config = _config(config)
    if existing_p3_ledger is None:
        raise TypeError("EXISTING_P3_LEDGER_REQUIRED")
    loaded = verify_loaded_sources(modules)
    if not config["execution_enabled"]:
        return {
            "state": "PREPARED_DEFAULT_OFF",
            "execution_enabled": False,
            "notifications_enabled": False,
            "loop": None,
            "loaded_sources": loaded,
        }

    if subject is None:
        raise PermissionError("CURRENT_RUN_SUBJECT_REQUIRED")
    gate = AdmissionGate(
        admission_reader, clock, execution_enabled=True,
        notifications_enabled=config["notifications_enabled"])
    # This is the hard P2-acceptance + explicit-P3-release boundary.  The
    # original host-wiring entry independently checks the same authority.
    gate.check(subject, notifications=config["notifications_enabled"])
    if receipt_provider is None:
        raise TypeError("TRUSTED_RECEIPT_PROVIDER_REQUIRED")
    verifier = ReceiptVerifier(receipt_provider)
    readers = EvidenceReaders(
        verifier, progress_subject, stop_subject, acceptance_index,
        completion_index=completion_index)
    runner = None
    if runner_adapter is not None:
        runner = RunnerController(gate, verifier, runner_adapter)
    outbox = None
    if outbox_transport is not None:
        outbox = OutboxController(gate, verifier, outbox_transport)

    wiring = (modules or {}).get("p3_host_wiring")
    if wiring is None:
        wiring = importlib.import_module("p3_host_wiring")
    loop = wiring.compose_existing_host(
        existing_p3_ledger, pipeline_factory, config, admission_reader,
        executor=executor, event_reader=event_reader,
        eligibility_reader=eligibility_reader, adapter=notification_adapter)
    return {
        "state": "COMPOSED_ADMISSION_RECHECKED",
        "execution_enabled": True,
        "notifications_enabled": config["notifications_enabled"],
        "loop": loop,
        "evidence_readers": readers,
        "runner_controller": runner,
        "outbox_controller": outbox,
        "loaded_sources": loaded,
    }
