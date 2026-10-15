#!/usr/bin/env bash
set -euo pipefail

stage=ARGUMENTS
fail() { printf 'INSTALL_STAGE=%s STATUS=HOLD REASON=%s\n' "${stage}" "$1" >&2; exit 2; }

# This prefix exists only so the exact transaction can run in a disposable
# filesystem. Production execution rejects every prefix.
test_mode=${KOREA_CANDIDATE_TEST_MODE:-0}
root_prefix=${KOREA_CANDIDATE_TEST_ROOT:-}
if [[ $test_mode == 1 ]]; then
  [[ -n $root_prefix && $root_prefix == /* && $root_prefix != / && -d $root_prefix ]] || fail TEST_ROOT_INVALID
else
  [[ -z $root_prefix ]] || fail TEST_ROOT_FORBIDDEN
  [[ ${EUID} -eq 0 ]] || fail ROOT_REQUIRED
  [[ $(hostname) == iZmj7a5kwr75qc1tul4kf9Z ]] || fail WRONG_HOST
fi
root_path() { printf '%s%s' "$root_prefix" "$1"; }

[[ $# -eq 2 ]] || fail USAGE_CANDIDATE_ROOT_EXPECTED_MANIFEST_SHA256
candidate_root=$1
expected_manifest=$2
[[ ${expected_manifest} =~ ^[0-9a-f]{64}$ ]] || fail MANIFEST_HASH_INVALID
unit=$(root_path /etc/systemd/system/xuanjun-binance-shadow.service)
transaction=$(root_path /etc/xuanjun-binance/install-transaction.json)
current=$(root_path /opt/xuanjun-binance/current)
venv=$(root_path /opt/xuanjun-binance/venv)
releases=$(root_path /opt/xuanjun-binance/releases)
lock=$(root_path /run/xuanjun-binance-install.lock)

stage=NO_SIDE_EFFECT_PREFLIGHT
expected_owner=0
[[ $test_mode == 1 ]] && expected_owner=${EUID}
test_owner_root=
[[ $test_mode == 1 ]] && test_owner_root=$(dirname "$root_prefix")
python3.11 - "$candidate_root" "$expected_owner" "$test_owner_root" <<'PY' || fail PRIVATE_STAGING_PREFLIGHT_FAILED
import os, stat, sys
path = os.path.abspath(sys.argv[1]); expected_owner = int(sys.argv[2]); test_root = sys.argv[3]
if not os.path.isdir(path) or os.path.islink(path):
    raise SystemExit("HOLD: candidate root must be a real directory")
current = path
while True:
    value = os.lstat(current)
    if stat.S_ISLNK(value.st_mode) or value.st_uid != expected_owner or value.st_mode & 0o022:
        raise SystemExit("HOLD: candidate staging path is not protected")
    if test_root and current == os.path.abspath(test_root): break
    parent = os.path.dirname(current)
    if parent == current: break
    current = parent
if stat.S_IMODE(os.stat(path).st_mode) & 0o077:
    raise SystemExit("HOLD: candidate staging root must be private")
PY
python3.11 "${candidate_root}/migration-prep/korea/validate_runtime_candidate.py" \
  "$candidate_root" --expected-manifest-sha256 "$expected_manifest" >/dev/null || fail INPUT_VALIDATION_FAILED
printf 'SOURCE_MANIFEST_CONTENT_PASS\n'

python3.11 - "$root_prefix" "$test_mode" <<'PY' || fail TARGET_AND_IDENTITY_PREFLIGHT_FAILED
import grp, os, pwd, stat, sys
prefix, test_mode = sys.argv[1], sys.argv[2] == "1"
for raw in ("/opt", "/var", "/var/lib", "/etc", "/var/log", "/etc/systemd", "/etc/systemd/system", "/run"):
    path = prefix + raw; value = os.lstat(path); expected = os.geteuid() if test_mode else 0
    if stat.S_ISLNK(value.st_mode) or value.st_uid != expected or value.st_mode & 0o022:
        raise SystemExit("HOLD: unsafe target parent " + path)
if not test_mode:
    try: group = grp.getgrnam("xuanjun_binance")
    except KeyError: group = None
    try: user = pwd.getpwnam("xuanjun_binance")
    except KeyError: user = None
    if user is not None:
        if user.pw_uid == 0 or user.pw_dir != "/var/lib/xuanjun-binance" or user.pw_shell not in ("/sbin/nologin", "/usr/sbin/nologin"):
            raise SystemExit("HOLD: existing runtime identity attributes invalid")
        if group is None or user.pw_gid != group.gr_gid:
            raise SystemExit("HOLD: existing runtime identity primary group invalid")
PY

stage=LOCK
lock_token="${expected_manifest}:$$:$(date +%s%N)"
mkdir -m 0700 "$lock" 2>/dev/null || fail INSTALL_TRANSACTION_BUSY
printf '%s\n' "$lock_token" >"$lock/owner"; chmod 0600 "$lock/owner"
lock_owned=1
created_group=0; created_user=0; created_staging=0; created_release=0
created_current=0; created_unit=0; created_venv=0; created_transaction=0
staging=; release=; unit_sha=; transaction_id="install-${expected_manifest:0:16}"
committed=0; interrupt_reason=

same_inode() { [[ -e $1 && ! -L $1 && $(stat -c '%d:%i' "$1") == "$2" ]]; }
release_lock() {
  if [[ $lock_owned -eq 1 && -f $lock/owner && ! -L $lock/owner && $(cat "$lock/owner") == "$lock_token" ]]; then
    rm -f -- "$lock/owner"; rmdir -- "$lock" 2>/dev/null || true
  fi
  lock_owned=0
}
cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [[ $committed -eq 0 ]]; then
    if [[ $created_transaction -eq 1 && -f $transaction && ! -L $transaction ]]; then
      python3.11 - "$transaction" "$expected_manifest" "$transaction_id" <<'PY' >/dev/null 2>&1 && rm -f -- "$transaction" || true
import json,sys
v=json.load(open(sys.argv[1])); raise SystemExit(0 if v.get("manifest_sha256")==sys.argv[2] and v.get("transaction_id")==sys.argv[3] else 1)
PY
    fi
    [[ $created_current -eq 1 && -L $current && $(readlink -f "$current") == "$release" ]] && rm -f -- "$current" || true
    [[ $created_unit -eq 1 && -f $unit && ! -L $unit && $(sha256sum "$unit" | awk '{print $1}') == "$unit_sha" ]] && rm -f -- "$unit" || true
    [[ $created_staging -eq 1 && -n $staging ]] && same_inode "$staging" "$staging_inode" && rm -rf --one-file-system "$staging" || true
    [[ $created_release -eq 1 && -n $release ]] && same_inode "$release" "$release_inode" && rm -rf --one-file-system "$release" || true
    [[ $created_venv -eq 1 ]] && same_inode "$venv" "$venv_inode" && rm -rf --one-file-system "$venv" || true
    [[ -d $releases ]] && rmdir "$releases" 2>/dev/null || true
    [[ -d $(root_path /opt/xuanjun-binance) ]] && rmdir "$(root_path /opt/xuanjun-binance)" 2>/dev/null || true
    [[ -d $(root_path /etc/xuanjun-binance/secretref) ]] && rmdir "$(root_path /etc/xuanjun-binance/secretref)" 2>/dev/null || true
    [[ -d $(root_path /etc/xuanjun-binance) ]] && rmdir "$(root_path /etc/xuanjun-binance)" 2>/dev/null || true
    [[ -d $(root_path /var/lib/xuanjun-binance/input) ]] && rmdir "$(root_path /var/lib/xuanjun-binance/input)" 2>/dev/null || true
    [[ -d $(root_path /var/lib/xuanjun-binance/evidence) ]] && rmdir "$(root_path /var/lib/xuanjun-binance/evidence)" 2>/dev/null || true
    [[ -n ${pycache_inode:-} ]] && same_inode "$(root_path /var/lib/xuanjun-binance/pycache)" "$pycache_inode" && rm -rf --one-file-system "$(root_path /var/lib/xuanjun-binance/pycache)" || true
    [[ -d $(root_path /var/lib/xuanjun-binance) ]] && rmdir "$(root_path /var/lib/xuanjun-binance)" 2>/dev/null || true
    [[ -d $(root_path /var/log/xuanjun-binance) ]] && rmdir "$(root_path /var/log/xuanjun-binance)" 2>/dev/null || true
    if [[ $test_mode != 1 ]]; then
      [[ $created_user -eq 1 ]] && userdel xuanjun_binance >/dev/null 2>&1 || true
      [[ $created_group -eq 1 ]] && groupdel xuanjun_binance >/dev/null 2>&1 || true
    fi
    [[ $created_unit -eq 1 ]] && systemctl daemon-reload >/dev/null 2>&1 || true
  fi
  release_lock
  [[ -z $interrupt_reason ]] || printf 'INSTALL_STAGE=%s STATUS=HOLD REASON=%s CLEANUP=COMPLETE\n' "$stage" "$interrupt_reason" >&2
  exit "$status"
}
on_int() { interrupt_reason=INTERRUPTED_SIGINT; exit 130; }
on_term() { interrupt_reason=INTERRUPTED_SIGTERM; exit 143; }
trap cleanup EXIT; trap on_int INT; trap on_term TERM

stage=LOCKED_PREFLIGHT
if [[ -e $transaction || -L $transaction ]]; then
  [[ -f $transaction && ! -L $transaction ]] || fail EXISTING_TRANSACTION_INVALID
  installed_manifest=$(python3.11 - "$transaction" <<'PY'
import json,sys
try: print(json.load(open(sys.argv[1]))["manifest_sha256"])
except Exception: raise SystemExit(2)
PY
  ) || fail EXISTING_TRANSACTION_FIELDS_INVALID
  [[ $installed_manifest == "$expected_manifest" ]] || fail DIFFERENT_VERSION_REQUIRES_SEPARATE_APPROVED_UPGRADE
  "${candidate_root}/migration-prep/korea/check-candidate.sh" --expected-transaction "$transaction" \
    --expected-manifest-sha256 "$expected_manifest" || fail EXISTING_TRANSACTION_CHECK_FAILED
  committed=1
  printf 'INSTALL_STAGE=LOCKED_PREFLIGHT STATUS=PASS ALREADY_INSTALLED=YES SAME_VERSION=YES\n'
  exit 0
fi
for path in "$(root_path /opt/xuanjun-binance)" "$(root_path /var/lib/xuanjun-binance)" \
            "$(root_path /etc/xuanjun-binance)" "$(root_path /var/log/xuanjun-binance)" "$unit"; do
  [[ ! -e $path && ! -L $path ]] || fail PREEXISTING_OR_DANGLING_TARGET
done
for protected in morelogin-socks5-permanent.service xuanjun-novel-factory.service postgresql.service redis.service yibi-api.service yibi-scheduler.service; do
  systemctl show "$protected" -p ActiveState -p SubState --no-pager >/dev/null || true
done

stage=MUTATION
if [[ $test_mode != 1 ]]; then
  if ! getent group xuanjun_binance >/dev/null; then groupadd --system xuanjun_binance; created_group=1; fi
  if ! getent passwd xuanjun_binance >/dev/null; then
    useradd --system --gid xuanjun_binance --home-dir /var/lib/xuanjun-binance --shell /sbin/nologin xuanjun_binance; created_user=1
  fi
fi
install -d -m 0755 "$(root_path /opt/xuanjun-binance)" "$releases"
install -d -m 0700 "$(root_path /var/lib/xuanjun-binance)" "$(root_path /var/lib/xuanjun-binance/input)" \
  "$(root_path /var/lib/xuanjun-binance/evidence)" "$(root_path /var/lib/xuanjun-binance/pycache)" "$(root_path /var/log/xuanjun-binance)"
pycache_inode=$(stat -c '%d:%i' "$(root_path /var/lib/xuanjun-binance/pycache)")
install -d -m 0750 "$(root_path /etc/xuanjun-binance)" "$(root_path /etc/xuanjun-binance/secretref)"
if [[ $test_mode != 1 ]]; then
  chown xuanjun_binance:xuanjun_binance "$(root_path /var/lib/xuanjun-binance)" "$(root_path /var/lib/xuanjun-binance/input)" \
    "$(root_path /var/lib/xuanjun-binance/evidence)" "$(root_path /var/lib/xuanjun-binance/pycache)" "$(root_path /var/log/xuanjun-binance)"
  chown root:xuanjun_binance "$(root_path /etc/xuanjun-binance)" "$(root_path /etc/xuanjun-binance/secretref)"
fi

release_id=${expected_manifest:0:16}; release="$releases/${release_id}"
staging="$(root_path /opt/xuanjun-binance/.staging-${release_id}-$$)"
[[ ! -e $release && ! -L $release && ! -e $staging && ! -L $staging ]] || fail RELEASE_TARGET_EXISTS
install -d -m 0700 "$staging"; created_staging=1; staging_inode=$(stat -c '%d:%i' "$staging")
cp -a --no-preserve=ownership -- "$candidate_root"/. "$staging"/
find "$staging" -type d -exec chmod 0755 {} +
find "$staging" -type f -exec chmod 0644 {} +
find "$staging" -type f -name '*.sh' -exec chmod 0755 {} +
chmod 0600 "$staging/minimal-runtime-manifest.json"
python3.11 "$staging/migration-prep/korea/validate_runtime_candidate.py" \
  "$staging" --expected-manifest-sha256 "$expected_manifest" >/dev/null || fail STAGING_VALIDATION_FAILED
mv -- "$staging" "$release"; created_staging=0; staging=; created_release=1; release_inode=$(stat -c '%d:%i' "$release")
python3.11 -m venv "$venv"; created_venv=1; venv_inode=$(stat -c '%d:%i' "$venv")
PYTHONPYCACHEPREFIX="$(root_path /var/lib/xuanjun-binance/pycache)" "$venv/bin/python" -m compileall -q "$release/migration-prep"
ln -s "$release" "$current"; created_current=1
install -m 0644 "$release/migration-prep/korea/xuanjun-binance-shadow.service.in" "$unit"; created_unit=1
unit_sha=$(sha256sum "$unit" | awk '{print $1}')
venv_python_sha=$(sha256sum "$venv/bin/python" | awk '{print $1}')
content_sha=$(python3.11 - "$release/minimal-runtime-manifest.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["content_sha256"])
PY
)
python3.11 - "$transaction" "$expected_manifest" "$content_sha" "$release" "$current" "$unit" "$unit_sha" "$venv" "$venv_python_sha" "$transaction_id" <<'PY'
import json, os, sys, tempfile
target, manifest, content, release, current, unit, unit_sha, venv, python_sha, transaction_id = sys.argv[1:]
value = {"schema_version": 1, "transaction_id": transaction_id, "manifest_sha256": manifest,
         "content_sha256": content, "release_path": release, "current_target": release,
         "unit_path": unit, "unit_sha256": unit_sha, "venv_path": venv,
         "venv_python_sha256": python_sha, "owned_objects": [release, current, venv, unit],
         "preserved_on_uninstall": ["/var/lib/xuanjun-binance", "/var/log/xuanjun-binance",
                                    "/etc/xuanjun-binance/secretref", "xuanjun_binance"]}
fd, temporary = tempfile.mkstemp(prefix=".install-transaction-", dir=os.path.dirname(target))
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, sort_keys=True); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, target)
finally:
    if os.path.exists(temporary): os.unlink(temporary)
PY
created_transaction=1
systemctl daemon-reload
systemctl disable xuanjun-binance-shadow.service >/dev/null 2>&1 || true
systemctl is-active --quiet xuanjun-binance-shadow.service && fail SERVICE_UNEXPECTEDLY_ACTIVE
systemd-analyze verify "$unit"
"$release/migration-prep/korea/check-candidate.sh" --expected-transaction "$transaction" \
  --expected-manifest-sha256 "$expected_manifest"
committed=1
printf 'INSTALL_STAGE=COMMIT STATUS=PASS SERVICE_ENABLED=NO SERVICE_STARTED=NO TRANSACTION_ID=%s\n' "$transaction_id"
