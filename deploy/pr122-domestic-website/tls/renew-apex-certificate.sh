#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "HOLD: root identity required" >&2
  exit 77
fi

exec certbot renew \
  --cert-name wenwenwenyiyiyi.work \
  --deploy-hook /usr/local/libexec/xuanjun-apex-nginx-deploy-hook \
  --quiet
