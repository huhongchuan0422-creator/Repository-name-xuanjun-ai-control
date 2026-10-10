#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/trading-system
echo "MODE=TOKYO_READONLY_DISCOVERY"
echo "HOST=$(hostname)"
echo "USER=$(id -un)"
date -u +UTC=%FT%TZ

test -d "$ROOT" || { echo "TRADING_ROOT=NOT_FOUND"; exit 2; }
echo "TRADING_ROOT=FOUND"
git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null || true
git -C "$ROOT" rev-parse HEAD 2>/dev/null || true
git -C "$ROOT" status --short 2>/dev/null | head -100 || true

echo "== TOP LEVEL =="
find "$ROOT" -mindepth 1 -maxdepth 2 -type d -print 2>/dev/null | sort | head -300

echo "== SERVICES (names/states only) =="
systemctl list-unit-files --type=service --no-pager 2>/dev/null  | grep -Ei 'xuanjun|binance|trading|finance|billing|openclaw|model|telegram|wecom|korea'  | head -200 || true

echo "== RUNTIMES =="
for c in git python3 node docker openclaw; do
  if command -v "$c" >/dev/null 2>&1; then
    printf '%s=' "$c"; "$c" --version 2>&1 | head -1 || true
  else
    echo "$c=MISSING"
  fi
done

echo "TOKYO_PRODUCTION_MUTATION=NO"
echo "DISCOVERY=PASS"
