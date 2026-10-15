#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'UNINSTALL_STAGE=%s STATUS=HOLD REASON=%s\n' "${stage}" "$1" >&2; exit 2; }
stage=ARGUMENTS
[[ ${EUID} -eq 0 ]] || fail ROOT_REQUIRED
[[ $(hostname) == iZmj7a5kwr75qc1tul4kf9Z ]] || fail WRONG_HOST
[[ $# -eq 3 && $1 == --confirm-disabled-candidate-only && $2 == --transaction-sha256 ]] || fail EXPLICIT_CONFIRMATION_AND_TRANSACTION_HASH_REQUIRED
expected_transaction_sha=$3
[[ $expected_transaction_sha =~ ^[0-9a-f]{64}$ ]] || fail TRANSACTION_HASH_INVALID
transaction=/etc/xuanjun-binance/install-transaction.json
[[ -f $transaction && ! -L $transaction ]] || fail TRANSACTION_RECORD_INVALID
[[ $(sha256sum "$transaction" | awk '{print $1}') == "$expected_transaction_sha" ]] || fail TRANSACTION_RECORD_HASH_MISMATCH

stage=OWNERSHIP_PREFLIGHT
eval "$(python3.11 - "$transaction" <<'PY'
import json, shlex, sys
v=json.load(open(sys.argv[1]))
for key in ("release_path","current_target","unit_path","unit_sha256","venv_path","manifest_sha256","transaction_id"):
 print(key.upper()+"="+shlex.quote(str(v[key])))
PY
)" || fail TRANSACTION_RECORD_FIELDS_INVALID
systemctl is-active --quiet xuanjun-binance-shadow.service && fail ACTIVE_SERVICE_REFUSED
[[ -f $UNIT_PATH && ! -L $UNIT_PATH && $(sha256sum "$UNIT_PATH" | awk '{print $1}') == "$UNIT_SHA256" ]] || fail REPLACED_UNIT_REFUSED
[[ -L /opt/xuanjun-binance/current && $(readlink -f /opt/xuanjun-binance/current) == "$CURRENT_TARGET" ]] || fail REPLACED_CURRENT_REFUSED
[[ -d $RELEASE_PATH && ! -L $RELEASE_PATH ]] || fail REPLACED_RELEASE_REFUSED
python3.11 "$RELEASE_PATH/migration-prep/korea/validate_runtime_candidate.py" \
  "$RELEASE_PATH" --expected-manifest-sha256 "$MANIFEST_SHA256" >/dev/null || fail REPLACED_CONTENT_REFUSED
[[ -d $VENV_PATH && ! -L $VENV_PATH ]] || fail REPLACED_VENV_REFUSED

stage=REMOVE_EXACT_TRANSACTION_OBJECTS
evidence=/var/lib/xuanjun-binance/evidence
install -d -o xuanjun_binance -g xuanjun_binance -m 0700 "$evidence"
archive="$evidence/uninstalled-${TRANSACTION_ID}.json"
[[ ! -e $archive && ! -L $archive ]] || fail UNINSTALL_RECEIPT_ALREADY_EXISTS
install -o xuanjun_binance -g xuanjun_binance -m 0600 "$transaction" "$archive"
rm -f -- "$UNIT_PATH"
rm -f -- /opt/xuanjun-binance/current
rm -rf --one-file-system "$RELEASE_PATH"
rm -rf --one-file-system "$VENV_PATH"
rm -f -- "$transaction"
systemctl daemon-reload
printf 'UNINSTALL_STAGE=COMPLETE STATUS=PASS STATE_CREDENTIALS_EVIDENCE_IDENTITY=PRESERVED\n'
