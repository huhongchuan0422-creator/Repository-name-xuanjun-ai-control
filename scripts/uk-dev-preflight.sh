#!/usr/bin/env bash
set -euo pipefail

echo "MODE=UK_DEV_CONTROL_PLANE_PREFLIGHT"
echo "HOST=$(hostname)"
echo "USER=$(id -un)"
date -u +UTC=%FT%TZ

echo "CPU=$(nproc)"
awk '/MemTotal/{print "MEM_KB="$2}' /proc/meminfo
df -P / | awk 'NR==2{print "ROOT_FS_KB="$2" ROOT_FREE_KB="$4}'
uname -srmo
timedatectl show -p NTPSynchronized -p Timezone 2>/dev/null || true

for c in git python3 node docker systemctl; do
  if command -v "$c" >/dev/null 2>&1; then
    printf '%s=' "$c"; "$c" --version 2>&1 | head -1 || true
  else
    echo "$c=MISSING"
  fi
done

echo "TRADING_PRODUCTION_WRITE=DENY"
echo "PRODUCTION_MUTATION=NO"
echo "PREFLIGHT=PASS"
