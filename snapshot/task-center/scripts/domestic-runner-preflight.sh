#!/usr/bin/env bash
set -euo pipefail
echo "MODE=DOMESTIC_RUNNER_READONLY_PREFLIGHT"
echo "HOST=$(hostname -s)"
echo "USER=$(id -un)"
if [[ "$(hostname -s)" != "iZvt5t8tlrm8oiZ" ]]; then
  echo "STOP=WRONG_HOST"; exit 2
fi
if [[ "$(id -un)" != "githubrunner" ]]; then
  echo "STOP=WRONG_USER"; exit 2
fi
date -u +UTC=%FT%TZ
printf 'RUNNER_VERSION='
/home/githubrunner/actions-runner/bin/Runner.Listener --version
echo "== NONSENSITIVE SERVICE STATUS =="
systemctl is-active provider-neutral-domestic-bridge.service 2>/dev/null || true
echo "DOMESTIC_PRODUCTION_MUTATION=NO"
echo "PREFLIGHT=PASS"
