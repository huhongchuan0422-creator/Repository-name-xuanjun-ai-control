#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'CHECK_STAGE=%s STATUS=HOLD REASON=%s\n' "${stage}" "$1" >&2; exit 2; }
stage=ARGUMENTS
[[ $(hostname) == iZmj7a5kwr75qc1tul4kf9Z ]] || fail WRONG_HOST
[[ $# -eq 2 && $1 == --expected-transaction ]] || fail EXPECTED_TRANSACTION_REQUIRED
transaction=$2
[[ $transaction == /etc/xuanjun-binance/install-transaction.json ]] || fail TRANSACTION_PATH_INVALID
[[ -f $transaction && ! -L $transaction ]] || fail TRANSACTION_RECORD_INVALID
[[ $(stat -c '%u:%a' "$transaction") == 0:600 ]] || fail TRANSACTION_RECORD_OWNER_MODE_INVALID

stage=TRANSACTION_IDENTITY
eval "$(python3.11 - "$transaction" <<'PY'
import json, shlex, sys
value=json.load(open(sys.argv[1]))
required={"schema_version","transaction_id","manifest_sha256","content_sha256","release_path","current_target","unit_path","unit_sha256","venv_path","venv_python_sha256","owned_objects","preserved_on_uninstall"}
if set(value) != required or value["schema_version"] != 1: raise SystemExit(2)
for key in ("manifest_sha256","content_sha256","unit_sha256","venv_python_sha256"):
    if len(value[key]) != 64 or any(c not in "0123456789abcdef" for c in value[key]): raise SystemExit(2)
for key in ("manifest_sha256","release_path","current_target","unit_path","unit_sha256","venv_path","venv_python_sha256"):
    print(key.upper()+"="+shlex.quote(str(value[key])))
PY
)" || fail TRANSACTION_RECORD_FIELDS_INVALID

[[ -d $RELEASE_PATH && ! -L $RELEASE_PATH ]] || fail RELEASE_INVALID
[[ -L /opt/xuanjun-binance/current && $(readlink -f /opt/xuanjun-binance/current) == "$CURRENT_TARGET" ]] || fail CURRENT_TARGET_MISMATCH
[[ -f $UNIT_PATH && ! -L $UNIT_PATH && $(sha256sum "$UNIT_PATH" | awk '{print $1}') == "$UNIT_SHA256" ]] || fail UNIT_IDENTITY_MISMATCH
[[ -x $VENV_PATH/bin/python && ! -L $VENV_PATH ]] || fail VENV_IDENTITY_INVALID
[[ $(sha256sum "$VENV_PATH/bin/python" | awk '{print $1}') == "$VENV_PYTHON_SHA256" ]] || fail VENV_PYTHON_IDENTITY_MISMATCH
python3.11 "$RELEASE_PATH/migration-prep/korea/validate_runtime_candidate.py" \
  "$RELEASE_PATH" --expected-manifest-sha256 "$MANIFEST_SHA256" >/dev/null || fail INSTALLED_CONTENT_INVALID

stage=EFFECTIVE_UNIT
enabled_state=$(systemctl is-enabled xuanjun-binance-shadow.service 2>/dev/null || true)
[[ $enabled_state == disabled ]] || fail UNIT_NOT_DISABLED
! systemctl is-active --quiet xuanjun-binance-shadow.service || fail UNIT_ACTIVE
systemd-analyze verify "$UNIT_PATH" >/dev/null
show=$(systemctl show xuanjun-binance-shadow.service -p FragmentPath -p DropInPaths -p User -p Group -p ExecStart --no-pager)
grep -Fx "FragmentPath=${UNIT_PATH}" <<<"$show" >/dev/null || fail EFFECTIVE_FRAGMENT_MISMATCH
grep -Fx 'DropInPaths=' <<<"$show" >/dev/null || fail UNEXPECTED_DROPIN
grep -Fx 'User=xuanjun_binance' <<<"$show" >/dev/null || fail EFFECTIVE_USER_MISMATCH
grep -Fx 'Group=xuanjun_binance' <<<"$show" >/dev/null || fail EFFECTIVE_GROUP_MISMATCH
effective=$(systemctl cat xuanjun-binance-shadow.service)
grep -Fx 'IPAddressDeny=any' <<<"$effective" >/dev/null || fail EFFECTIVE_DENY_ALL_MISSING
! grep -Eq '^IPAddressAllow=' <<<"$effective" || fail EFFECTIVE_IP_ALLOW_UNEXPECTED
grep -F -- '--continuous --config /etc/xuanjun-binance/shadow.json --acceptance-config /etc/xuanjun-binance/shadow-acceptance.json' <<<"$show" >/dev/null || fail EFFECTIVE_ENTRYPOINT_MISMATCH
"$VENV_PATH/bin/python" -B -I -c \
  "import sys;sys.path.insert(0,'$CURRENT_TARGET/migration-prep');from korea.migration_shadow_entry import self_check;assert self_check()['status']=='SELF_CHECK_PASS_NO_NETWORK'"
printf 'CHECK_STAGE=COMPLETE STATUS=PASS NO_NETWORK=YES SERVICE_STARTED=NO\n'
