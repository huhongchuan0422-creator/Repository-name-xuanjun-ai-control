#!/usr/bin/env bash
set -euo pipefail

[[ ${EUID} -eq 0 ]] || { echo 'HOLD: root required' >&2; exit 2; }
[[ $(hostname) == iZmj7a5kwr75qc1tul4kf9Z ]] || { echo 'HOLD: wrong host' >&2; exit 2; }
[[ $# -eq 2 ]] || { echo 'usage: install-candidate.sh SOURCE_ROOT EXPECTED_MANIFEST_SHA256' >&2; exit 2; }
source_root=$(readlink -f -- "$1")
expected_manifest=$2
[[ -d ${source_root}/migration-prep ]] || { echo 'HOLD: source root invalid' >&2; exit 2; }
[[ ${expected_manifest} =~ ^[0-9a-f]{64}$ ]] || { echo 'HOLD: manifest hash invalid' >&2; exit 2; }
actual_manifest=$(sha256sum "${source_root}/migration-prep/korea/minimal-runtime-manifest.json" | awk '{print $1}')
[[ ${actual_manifest} == "${expected_manifest}" ]] || { echo 'HOLD: manifest hash mismatch' >&2; exit 2; }
SOURCE_ROOT=${source_root} python3.11 - <<'PY'
import hashlib, json, os
from pathlib import Path
root = Path(os.environ["SOURCE_ROOT"])
manifest = json.loads((root / "migration-prep/korea/minimal-runtime-manifest.json").read_text())
for item in manifest["files"]:
    raw = (root / item["path"]).read_bytes()
    if len(raw) != item["size"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
        raise SystemExit("HOLD: runtime file identity mismatch: " + item["path"])
print("SOURCE_MANIFEST_CONTENT_PASS")
PY

for protected in morelogin-socks5-permanent.service xuanjun-novel-factory.service postgresql.service redis.service yibi-api.service yibi-scheduler.service; do
  systemctl show "$protected" -p ActiveState -p SubState --no-pager || true
done

getent group xuanjun_binance >/dev/null || groupadd --system xuanjun_binance
getent passwd xuanjun_binance >/dev/null || useradd --system --gid xuanjun_binance --home-dir /var/lib/xuanjun-binance --shell /sbin/nologin xuanjun_binance
install -d -o root -g root -m 0755 /opt/xuanjun-binance/releases
[[ ! -e /opt/xuanjun-binance/current ]] || { echo 'HOLD: current release already exists' >&2; exit 2; }
[[ ! -e /opt/xuanjun-binance/venv ]] || { echo 'HOLD: candidate venv already exists' >&2; exit 2; }
[[ ! -e /etc/systemd/system/xuanjun-binance-shadow.service ]] || { echo 'HOLD: unit already exists' >&2; exit 2; }
install -d -o xuanjun_binance -g xuanjun_binance -m 0700 /var/lib/xuanjun-binance/input /var/lib/xuanjun-binance/evidence /var/log/xuanjun-binance
install -d -o root -g xuanjun_binance -m 0750 /etc/xuanjun-binance /etc/xuanjun-binance/secretref

release_id=$(sha256sum "${source_root}/migration-prep/korea/minimal-runtime-manifest.json" | awk '{print substr($1,1,16)}')
release="/opt/xuanjun-binance/releases/${release_id}"
[[ ! -e ${release} ]] || { echo 'HOLD: release already exists' >&2; exit 2; }
install -d -o root -g root -m 0755 "$release" "$release/korea"
for file in gate_common.py final_snapshot.py readonly_reconciliation_adapter.py; do
  install -o root -g root -m 0644 "${source_root}/migration-prep/${file}" "${release}/${file}"
done
for file in __init__.py get_only_policy.py migration_shadow_entry.py; do
  install -o root -g root -m 0644 "${source_root}/migration-prep/korea/${file}" "${release}/korea/${file}"
done
install -o root -g root -m 0644 "${source_root}/migration-prep/korea/minimal-runtime-manifest.json" "${release}/minimal-runtime-manifest.json"

python3.11 -m venv /opt/xuanjun-binance/venv
/opt/xuanjun-binance/venv/bin/python -m compileall -q "$release"
ln -sfn "$release" /opt/xuanjun-binance/current
install -o root -g root -m 0644 "${source_root}/migration-prep/korea/xuanjun-binance-shadow.service.in" /etc/systemd/system/xuanjun-binance-shadow.service
systemctl daemon-reload
systemctl disable xuanjun-binance-shadow.service >/dev/null 2>&1 || true
systemctl is-active --quiet xuanjun-binance-shadow.service && { echo 'HOLD: service unexpectedly active' >&2; exit 2; }
systemd-analyze verify /etc/systemd/system/xuanjun-binance-shadow.service
PYTHONPATH=/opt/xuanjun-binance/current /opt/xuanjun-binance/venv/bin/python -m korea.migration_shadow_entry --self-check
echo 'INSTALL_CANDIDATE_PASS_SERVICE_DISABLED_WRITER_LOCKED'
