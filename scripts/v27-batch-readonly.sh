#!/usr/bin/env bash
set -euo pipefail
ROLE="${1:?expected role}"
HOST="$(hostname -s)"
case "$ROLE:$HOST" in
 uk:iZd7oeikknn1z21sq6ji6zZ|tokyo:iZ6wee8q9z4t03hvqumwfhZ|korea:iZmj7a5kwr75qc1tul4kf9Z|domestic:iZvt5t8tlrm8oiZ) ;;
 *) echo "STOP=HOST_ROLE_MISMATCH"; exit 2 ;;
esac
test "$(id -un)" = githubrunner || { echo 'STOP=WRONG_USER'; exit 2; }
echo "ROLE=$ROLE"
echo "HOST=$HOST"
echo "RUNNER_USER=$(id -un)"
date -u '+UTC=%Y-%m-%dT%H:%M:%SZ'
echo "== CAPACITY =="
nproc
awk '/MemTotal|MemAvailable/{print $1,$2,$3}' /proc/meminfo
df -hP / | tail -1
echo "== TOOLS (NAMES/VERSIONS) =="
for tool in git python3 node npm docker openclaw; do
 if command -v "$tool" >/dev/null 2>&1; then
  case "$tool" in
    openclaw) echo "openclaw=FOUND";;
    *) echo "$tool=FOUND";;
  esac
 else echo "$tool=MISSING"; fi
done
echo "== RUNNER SANDBOX CHECK =="
id
for d in /opt/trading-system /home/openclaw_ops /home/githubrunner; do
 if [ -d "$d" ]; then
  if [ -r "$d" ]; then r=YES; else r=NO; fi
  if [ -w "$d" ]; then w=YES; else w=NO; fi
  printf 'DIR=%s READ=%s WRITE=%s\n' "$d" "$r" "$w"
 fi
done
echo "== SERVICE NAMES ONLY =="
systemctl list-units --type=service --all --no-legend --no-pager 2>/dev/null |
  awk '{print $1}' | grep -Ei '^(actions.runner|xuanjun|yibi|finance|provider-neutral|tokyo-restricted|openclaw)' |
  head -60 || true
echo "== FIXED SERVICE STATE AND RESOURCE LIMITS =="
case "$ROLE" in
 uk) UNITS=(xuanjun-uk-openclaw.service xuanjun-uk-stage1-minimal.service xuanjun-uk-owner-dashboard.service xuanjun-uk-owner-callback.service nginx.service docker.service containerd.service) ;;
 tokyo) UNITS=(tokyo-restricted-model-executor.service provider-neutral-tokyo-tunnel.service finance-collection-sync.service xuanjun-wecom-novel-ingress.service nginx.service docker.service) ;;
 korea) UNITS=(xuanjun-novel-factory.service xuanjun-ts-exit.service yibi-api.service yibi-scheduler.service yibi-health-check.service docker.service containerd.service nginx.service) ;;
 domestic) UNITS=(provider-neutral-domestic-bridge.service docker.service containerd.service nginx.service) ;;
esac
for unit in "${UNITS[@]}"; do
 printf 'UNIT=%s\n' "$unit"
 systemctl show "$unit" --no-pager \
   -p LoadState -p ActiveState -p SubState \
   -p CPUQuotaPerSecUSec -p MemoryMax -p TasksMax \
   -p NoNewPrivileges -p ProtectSystem -p ProtectHome -p PrivateTmp \
   2>/dev/null || echo "UNIT_EVIDENCE=NOT_VERIFIED"
done
echo "== LISTENER SCOPE AND PORT ONLY =="
if command -v ss >/dev/null 2>&1; then
 ss -H -ltn 2>/dev/null | awk '
   { addr=$4; n=split(addr,parts,":"); port=parts[n];
     if (port ~ /^[0-9]+$/) {
       scope=(addr ~ /^(127\.|\[?::1\]?:)/) ? "LOOPBACK" : "NON_LOOPBACK";
       print "LISTEN_SCOPE="scope" PORT="port
     }
   }' || echo "LISTENER_EVIDENCE=NOT_VERIFIED"
else
 echo "LISTENER_EVIDENCE=NOT_VERIFIED"
fi
echo "== SUDO CAPABILITY =="
if sudo -n true >/dev/null 2>&1; then echo 'SUDO_NONINTERACTIVE=YES_RISK_REVIEW'; else echo 'SUDO_NONINTERACTIVE=NO'; fi
echo "PRODUCTION_MUTATION=NO"
echo "BATCH_READONLY=PASS"

