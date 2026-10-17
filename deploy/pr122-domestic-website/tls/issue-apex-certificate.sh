#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--release-gate-approved" ]]; then
  echo "HOLD: explicit Release Gate argument required" >&2
  exit 64
fi
ACCOUNT_EMAIL="${2:-}"
if [[ -z "$ACCOUNT_EMAIL" || "$ACCOUNT_EMAIL" != *@* ]]; then
  echo "HOLD: exact ACME account email argument required" >&2
  exit 64
fi
if [[ "$(id -u)" -ne 0 ]]; then
  echo "HOLD: root identity required" >&2
  exit 77
fi

# Apex DNS remains on Tokyo. A separately reviewed Tokyo location must forward
# only this challenge prefix to Domestic before authorization. Never switch DNS
# or expose the rest of the bootstrap server to obtain the certificate.
CERTBOT=/usr/local/bin/certbot
[[ -x "$CERTBOT" ]] || { echo "HOLD: proven Domestic certbot path missing" >&2; exit 78; }
[[ "$("$CERTBOT" --version 2>&1)" == "certbot 5.8.0" ]] || {
  echo "HOLD: certbot version drift" >&2; exit 78;
}
exec "$CERTBOT" certonly --webroot \
  --webroot-path /var/www/letsencrypt \
  --config-dir /etc/letsencrypt \
  --work-dir /var/lib/letsencrypt \
  --logs-dir /var/log/letsencrypt \
  --cert-name wenwenwenyiyiyi.work \
  --domain wenwenwenyiyiyi.work \
  --key-type ecdsa \
  --email "$ACCOUNT_EMAIL" \
  --agree-tos \
  --no-eff-email \
  --non-interactive
