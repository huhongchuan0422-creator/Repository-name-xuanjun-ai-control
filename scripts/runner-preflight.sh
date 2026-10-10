#!/usr/bin/env bash
set -euo pipefail

echo "HOST=$(hostname)"
echo "USER=$(id -un)"
echo "UTC=$(date -u +%FT%TZ)"
echo "KERNEL=$(uname -srmo)"
echo "CPU=$(nproc)"
echo "MEM_KB=$(awk '/MemTotal/{print $2}' /proc/meminfo)"
echo "DISK_ROOT=$(df -P / | tail -1 | awk '{print $2":"$4}')"
command -v git >/dev/null && git --version || echo "GIT=MISSING"
command -v docker >/dev/null && docker --version || echo "DOCKER=MISSING"
command -v python3 >/dev/null && python3 --version || echo "PYTHON3=MISSING"
command -v node >/dev/null && node --version || echo "NODE=MISSING"
command -v systemctl >/dev/null && systemctl --version | head -1 || true
echo "PREFLIGHT=PASS"
