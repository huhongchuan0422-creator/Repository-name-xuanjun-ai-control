#!/usr/bin/env bash
set -euo pipefail

[[ $(hostname) == iZmj7a5kwr75qc1tul4kf9Z ]] || { echo 'HOLD: wrong host' >&2; exit 2; }
for path in /opt/xuanjun-binance/current /opt/xuanjun-binance/venv/bin/python /etc/systemd/system/xuanjun-binance-shadow.service; do
  [[ -e $path ]] || { echo "HOLD: missing $path" >&2; exit 2; }
done
enabled_state=$(systemctl is-enabled xuanjun-binance-shadow.service 2>/dev/null || true)
[[ ${enabled_state} == disabled ]] || { echo "HOLD: unit state is ${enabled_state}" >&2; exit 2; }
! systemctl is-active --quiet xuanjun-binance-shadow.service
systemd-analyze verify /etc/systemd/system/xuanjun-binance-shadow.service
grep -Fx 'IPAddressDeny=any' /etc/systemd/system/xuanjun-binance-shadow.service >/dev/null
! grep -Eq '^IPAddressAllow=' /etc/systemd/system/xuanjun-binance-shadow.service
PYTHONPATH=/opt/xuanjun-binance/current /opt/xuanjun-binance/venv/bin/python -m korea.migration_shadow_entry --self-check
ss -lntp | grep -E ':(443|8000|18760|18765)\b' || true
echo 'CHECK_CANDIDATE_PASS_NO_NETWORK_NO_SERVICE_START'
