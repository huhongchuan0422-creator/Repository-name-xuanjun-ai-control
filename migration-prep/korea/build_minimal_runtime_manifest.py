"""Build the deterministic Korea minimal-runtime manifest."""
from __future__ import print_function

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FILES = (
    "migration-prep/gate_common.py",
    "migration-prep/final_snapshot.py",
    "migration-prep/readonly_reconciliation_adapter.py",
    "migration-prep/korea/__init__.py",
    "migration-prep/korea/get_only_policy.py",
    "migration-prep/korea/migration_shadow_entry.py",
    "migration-prep/korea/shadow_acceptance.py",
    "migration-prep/korea/shadow-acceptance.template.json",
    "migration-prep/korea/validate_runtime_candidate.py",
    "migration-prep/korea/build_runtime_candidate.py",
    "migration-prep/korea/shadow-config.template.json",
    "migration-prep/korea/xuanjun-binance-shadow.service.in",
    "migration-prep/korea/install-candidate.sh",
    "migration-prep/korea/check-candidate.sh",
    "migration-prep/korea/uninstall-candidate.sh",
    "migration-prep/korea/requirements.lock",
)


def build():
    records = []
    for name in FILES:
        raw = (ROOT / name).read_bytes()
        records.append({"path": name, "size": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest()})
    content = "\n".join(item["path"] + "\0" + item["sha256"] for item in records)
    return {
        "schema_version": 2,
        "feature_id": "TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1",
        "artifact_role": "KOREA_GET_ONLY_SHADOW_RUNTIME_CANDIDATE",
        "entrypoint": "python -m korea.migration_shadow_entry --continuous",
        "python": "/usr/bin/python3.11",
        "requirements": "stdlib-only",
        "files": records,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "writer_enabled": False,
        "scheduler_enabled": False,
        "allowed_exchange_methods": ["GET"],
        "allowed_credential_role": "BINANCE_ACCOUNT_READONLY",
        "forbidden_credential_references": [
            "BINANCE_TRADING", "TRADING_CREDENTIAL_MASTER_KEY", "PLAINTEXT_ENV_SECRET"
        ],
        "persistent_production_launcher": "NOT_PROVEN_NOT_INCLUDED",
        "install_executed": False,
        "binance_called": False,
        "production_authorized": False,
    }


def main():
    output = Path(__file__).with_name("minimal-runtime-manifest.json")
    output.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
