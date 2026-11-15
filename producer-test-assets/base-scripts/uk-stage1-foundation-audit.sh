#!/usr/bin/env bash
set -euo pipefail
echo "TASK_ID=XUANJUN_UK_AI_DEVELOPMENT_CONTROL_PLANE_V1_STAGE1_AUDIT"
echo "HOST=$(hostname)"
echo "USER=$(id -un)"
date -u +UTC=%FT%TZ

echo "== PRIVILEGE =="
if sudo -n true 2>/dev/null; then echo "SUDO_NONINTERACTIVE=PASS"; else echo "SUDO_NONINTERACTIVE=NO"; fi

echo "== OS =="
cat /etc/os-release || true
uname -srmo

echo "== CAPACITY =="
nproc
awk '/MemTotal|MemAvailable/{print}' /proc/meminfo
df -hT / /home 2>/dev/null || true

echo "== TIME =="
timedatectl status 2>/dev/null || true

echo "== NETWORK/FIREWALL READONLY =="
ip -brief addr 2>/dev/null || true
ip route 2>/dev/null || true
sudo -n firewall-cmd --state 2>/dev/null || true
sudo -n firewall-cmd --list-all 2>/dev/null || true
sudo -n nft list ruleset 2>/dev/null | head -250 || true

echo "== USERS/SSH READONLY =="
getent passwd githubrunner || true
sudo -n sshd -T 2>/dev/null | grep -E '^(permitrootlogin|passwordauthentication|pubkeyauthentication|maxauthtries|clientaliveinterval|clientalivecountmax)' || true

echo "== RUNTIMES =="
for c in git python3 python node npm docker podman gcc make ffmpeg sqlite3 psql nginx; do
  if command -v "$c" >/dev/null 2>&1; then
    printf '%s=' "$c"; "$c" --version 2>&1 | head -1 || true
  else
    echo "$c=MISSING"
  fi
done

echo "== SERVICES READONLY =="
systemctl --no-pager --type=service --state=running 2>/dev/null | head -120 || true

echo "== LISTENERS READONLY =="
ss -lntup 2>/dev/null | head -150 || true

echo "== GITHUB RUNNER =="
systemctl --no-pager --type=service 2>/dev/null | grep 'actions.runner' || true

echo "PRODUCTION_MUTATION=NO"
echo "AUDIT=PASS"
