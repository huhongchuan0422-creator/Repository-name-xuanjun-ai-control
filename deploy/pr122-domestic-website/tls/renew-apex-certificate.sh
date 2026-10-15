#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "HOLD: root identity required" >&2
  exit 77
fi

CERTBOT=/usr/local/bin/certbot
[[ -x "$CERTBOT" ]] || { echo "HOLD: proven Domestic certbot path missing" >&2; exit 78; }
exec "$CERTBOT" renew \
  --cert-name wenwenwenyiyiyi.work \
  --config-dir /etc/letsencrypt \
  --work-dir /var/lib/letsencrypt \
  --logs-dir /var/log/letsencrypt \
  --deploy-hook /usr/local/libexec/xuanjun-apex-nginx-deploy-hook \
  --quiet
