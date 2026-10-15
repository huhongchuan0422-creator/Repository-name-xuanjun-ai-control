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

# The HTTP bootstrap server and DNS routing to this host must be independently
# proven before this command is authorized. This script is not run by CI.
exec certbot certonly --webroot \
  --webroot-path /var/www/letsencrypt \
  --cert-name wenwenwenyiyiyi.work \
  --domain wenwenwenyiyiyi.work \
  --key-type ecdsa \
  --email "$ACCOUNT_EMAIL" \
  --agree-tos \
  --no-eff-email \
  --non-interactive
