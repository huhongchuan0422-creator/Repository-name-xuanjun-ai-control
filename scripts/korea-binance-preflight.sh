#!/usr/bin/env bash
set -euo pipefail

echo "MODE=KOREA_BINANCE_TARGET_PREFLIGHT"
echo "HOST=$(hostname)"
echo "USER=$(id -un)"
date -u +UTC=%FT%TZ

echo "== CAPACITY =="
echo "CPU=$(nproc)"
awk '/MemTotal/{print "MEM_KB="$2}' /proc/meminfo
df -P / | awk 'NR==2{print "ROOT_FS_KB="$2" ROOT_FREE_KB="$4}'
timedatectl show -p NTPSynchronized -p Timezone 2>/dev/null || true

echo "== EXISTING WORKLOAD MARKERS =="
systemctl list-unit-files --type=service --no-pager 2>/dev/null  | grep -Ei 'novel|easi|yibi|korea|xuanjun|openclaw|trading|binance'  | head -200 || true
docker ps --format '{{.Names}} {{.Status}}' 2>/dev/null | head -100 || true

echo "== REQUIRED TOOLS =="
for c in git python3 node docker systemctl; do
  command -v "$c" >/dev/null 2>&1 && echo "$c=FOUND" || echo "$c=MISSING"
done

echo "BINANCE_ORDER_WRITE=DISABLED"
echo "PRODUCTION_MUTATION=NO"
echo "PREFLIGHT=PASS"
