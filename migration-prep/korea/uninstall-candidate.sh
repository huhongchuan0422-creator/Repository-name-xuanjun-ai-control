#!/usr/bin/env bash
set -euo pipefail

[[ ${EUID} -eq 0 ]] || { echo 'HOLD: root required' >&2; exit 2; }
[[ $(hostname) == iZmj7a5kwr75qc1tul4kf9Z ]] || { echo 'HOLD: wrong host' >&2; exit 2; }
[[ ${1:-} == --confirm-disabled-candidate-only ]] || { echo 'HOLD: explicit confirmation required' >&2; exit 2; }
systemctl is-active --quiet xuanjun-binance-shadow.service && { echo 'HOLD: refuse active service removal' >&2; exit 2; }
systemctl disable xuanjun-binance-shadow.service >/dev/null 2>&1 || true
rm -f -- /etc/systemd/system/xuanjun-binance-shadow.service
systemctl daemon-reload
if [[ -L /opt/xuanjun-binance/current ]]; then rm -f -- /opt/xuanjun-binance/current; fi
echo 'UNINSTALL_CODE_UNIT_PASS_STATE_CREDENTIALS_AND_IDENTITY_PRESERVED'
