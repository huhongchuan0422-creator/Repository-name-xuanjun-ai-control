"""Explicit Phase-C CLI. prepare renders only; broker/worker require signed admission."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys
import time

from gate_common import require
from korea.phase_c.broker import ReadonlyBroker, VerifiedBrokerClient
from korea.phase_c.artifact import verify_runtime
from korea.phase_c.credentials import load_pair
from korea.phase_c.network import compile_rules
from korea.phase_c.runtime import run_window, verify_admission
from korea.phase_c.security import DetachedRSA, digest, hash_value, read_file, strict_json


def load_config(path):
    # Public configuration contains references, never key material. Root owns it.
    config = strict_json(read_file(path, modes=(0o444, 0o644), limit=32768))
    return validate_config(config)


def validate_config(config):
    fields = {"schema_version", "feature_id", "account_id", "symbols", "business_database",
        "evidence_root", "credential_role", "snapshot_max_age_ms", "capture_timeout_ms",
        "runtime_manifest_sha256", "snapshot_refresh_protocol", "snapshot_publisher_identity_sha256",
        "verifier_sha256", "writer_enabled", "scheduler_enabled", "snapshot_reader_uid",
        "network_policy", "snapshot_root", "socket_path", "credential_generation", "secret_ref",
        "custody_attestation_sha256", "broker_public_key", "broker_public_key_sha256",
        "broker_private_key", "source_public_key", "source_public_key_sha256",
        "authority_public_key", "authority_public_key_sha256", "admission_path", "acceptance_path"}
    require(isinstance(config, dict) and set(config) == fields and config["schema_version"] == 1,
            "C_CONFIG_FIELDS")
    require(config["feature_id"] == "TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1" and
            config["symbols"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"] and
            config["credential_role"] == "BINANCE_ACCOUNT_READONLY" and
            config["writer_enabled"] is False and config["scheduler_enabled"] is False,
            "C_CONFIG_SCOPE")
    require(type(config["snapshot_max_age_ms"]) is int and 0 < config["snapshot_max_age_ms"] <= 300000 and
            type(config["capture_timeout_ms"]) is int and 0 < config["capture_timeout_ms"] <= 300000,
            "C_CONFIG_TIMEOUT")
    require(config["snapshot_refresh_protocol"] == "XUANJUN_SQLITE_WAL_BACKUP_ATOMIC_HANDOFF_V1" and
            config["source_public_key_sha256"] == config["snapshot_publisher_identity_sha256"],
            "C_SOURCE_IDENTITY_CONFIG")
    for name in ("runtime_manifest_sha256", "verifier_sha256", "custody_attestation_sha256",
                 "broker_public_key_sha256", "source_public_key_sha256", "authority_public_key_sha256"):
        require(isinstance(config[name], str) and len(config[name]) == 64 and
                all(c in "0123456789abcdef" for c in config[name]), "C_CONFIG_HASH")
    for name in ("business_database", "evidence_root", "snapshot_root", "socket_path",
                 "credential_generation", "broker_public_key", "broker_private_key", "source_public_key",
                 "authority_public_key", "admission_path", "acceptance_path"):
        require(isinstance(config[name], str) and Path(config[name]).is_absolute() and
                ".." not in Path(config[name]).parts and
                not config[name].startswith(("/opt/xuanjun-binance/current", "/etc/xuanjun-binance/")),
                "C_PATH_FROZEN_B_OR_INVALID")
    require("REPLACE" not in json.dumps(config).upper() and
            "TRADING_CREDENTIAL_MASTER_KEY" not in json.dumps(config).upper(), "C_PLACEHOLDER_CONFIG")
    return config


def notify_ready():
    # systemd239 supports Type=notify. Worker must not race socket.bind/listen.
    target = os.environ.get("NOTIFY_SOCKET")
    require(type(target) is str and target and (target.startswith("/") or target.startswith("@")) and
            len(target) <= 107, "C_NOTIFY_SOCKET_REQUIRED")
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notification:
        notification.connect("\x00" + target[1:] if target.startswith("@") else target)
        require(notification.send(b"READY=1") == 7, "C_NOTIFY_READY_FAILED")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "broker", "worker"))
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    root = Path(__file__).resolve().parents[3]
    verify_runtime(root, config["runtime_manifest_sha256"])
    require(digest((Path(__file__).parent / "security.py").read_bytes()) == config["verifier_sha256"],
            "C_VERIFIER_CODE_PIN")
    if args.action == "prepare":
        print(compile_rules(config["network_policy"]), end="")
        print("# PREPARED_ONLY; NO_NFT_INVOCATION; NO_INSTALL; NO_SERVICE_ACTION")
        return 0
    now = lambda: int(time.time() * 1000)
    acceptance = strict_json(read_file(config["acceptance_path"], modes=(0o444, 0o644)))
    packet = strict_json(read_file(config["admission_path"], modes=(0o444, 0o644)))
    require(set(packet) == {"admission", "signature"}, "C_ADMISSION_PACKET")
    authority = DetachedRSA(config["authority_public_key"], config["authority_public_key_sha256"])
    verify_admission(packet["admission"], packet["signature"], authority, config, acceptance,
                     now(), os.uname().nodename)
    if args.action == "worker":
        source = DetachedRSA(config["source_public_key"], config["source_public_key_sha256"])
        public = DetachedRSA(config["broker_public_key"], config["broker_public_key_sha256"])
        def factory(run_id):
            return VerifiedBrokerClient(config["socket_path"], 986, public, config["network_policy"],
                                        config["account_id"], acceptance["window_id"], run_id)
        from korea.phase_c.resources import live_sampler
        result = run_window(config, acceptance, packet["admission"], packet["signature"], authority,
                            source, factory, resource_sampler=live_sampler())
        # Full reconciliation/account data stays private in evidence_root.
        print(json.dumps({"status": result["status"], "writer_enabled": False,
                          "production_authorized": False}, sort_keys=True))
        return 0 if result["status"] == "PASS_SHADOW_WINDOW" else 2
    require(os.geteuid() == 986, "C_BROKER_PROCESS_UID")
    signer = DetachedRSA(config["broker_public_key"], config["broker_public_key_sha256"],
                         private_key=config["broker_private_key"], key_owner=986)
    expected = {"role": config["credential_role"], "account_id": config["account_id"],
                "secret_ref": config["secret_ref"]}
    key, secret = load_pair(config["credential_generation"], expected,
                           lambda record: hash_value(record) == config["custody_attestation_sha256"], now())
    custody = strict_json(read_file(Path(config["credential_generation"]) / "custody.json", modes=(0o444,)))
    require(custody["expires_at_ms"] >= packet["admission"]["expires_at_ms"],
            "C_CUSTODY_WINDOW_TOO_SHORT")
    broker = ReadonlyBroker(config["network_policy"], config["account_id"], key, secret, signer,
                            acceptance["window_id"], custody["expires_at_ms"])
    # New RuntimeDirectory belongs to broker UID/group of worker, supplied by unit.
    socket_path = Path(config["socket_path"])
    require(socket_path.parent.stat().st_uid == 986 and not socket_path.parent.is_symlink(),
            "C_BROKER_SOCKET_DIRECTORY")
    attempt = socket_path.parent / ("attempt-" + acceptance["window_id"])
    fd = os.open(attempt, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.fsync(fd); os.close(fd)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        require(not os.path.lexists(socket_path), "C_BROKER_SOCKET_EXISTS")
        listener.bind(str(socket_path))
        os.chmod(socket_path, 0o660)
        listener.listen(1)
        listener.settimeout(1)
        notify_ready()
        while now() < min(packet["admission"]["expires_at_ms"], config["network_policy"]["expires_at_ms"]):
            try:
                broker.serve_one(listener)
            except socket.timeout:
                pass
    return 0


if __name__ == "__main__":
    try:
        status = main()
    except BaseException as error:
        print(json.dumps({"status": "HOLD_PHASE_C", "error_type": type(error).__name__,
                          "retry_allowed": False}), file=sys.stderr)
        sys.exit(2)
    else:
        sys.exit(status)
