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
manage_identities=1
if [[ $test_mode == 1 && ${KOREA_CANDIDATE_TEST_IDENTITIES:-0} != 1 ]]; then manage_identities=0; fi

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
lock_inode=$(stat -c '%d:%i' "$lock") || fail LOCK_IDENTITY_UNAVAILABLE
lock_owner_inode=$(stat -c '%d:%i' "$lock/owner") || fail LOCK_OWNER_IDENTITY_UNAVAILABLE
created_group=0; created_user=0; created_staging=0; created_release=0
created_current=0; created_unit=0; created_venv=0; created_transaction=0
created_directories=(); created_directory_inodes=(); cleanup_retained=()
staging=; release=; unit_sha=; transaction_id="install-${expected_manifest:0:16}"
staging_inode=; release_inode=; venv_inode=; pycache_inode=
current_inode=; unit_inode=; transaction_inode=; created_user_record=; created_group_record=
committed=0; interrupt_reason=

same_inode() { [[ -e $1 && ! -L $1 && $(stat -c '%d:%i' "$1") == "$2" ]]; }
path_present() { [[ -e $1 || -L $1 ]]; }
same_lstat_inode() {
  local actual
  path_present "$1" || return 1
  actual=$(stat -c '%d:%i' -- "$1" 2>/dev/null) || return 1
  [[ $actual == "$2" ]]
}
retain_cleanup() {
  local item="$1:$2" existing
  for existing in "${cleanup_retained[@]}"; do [[ $existing == "$item" ]] && return 0; done
  cleanup_retained+=("$item")
}
remove_owned_tree() {
  local path=$1 inode=$2
  path_present "$path" || return 0
  if [[ -z $inode ]]; then
    retain_cleanup "$path" IDENTITY_UNAVAILABLE
  elif ! same_inode "$path" "$inode"; then
    retain_cleanup "$path" IDENTITY_CHANGED
  elif ! rm -rf --one-file-system -- "$path"; then
    retain_cleanup "$path" REMOVE_FAILED
  fi
}
record_remaining_path() {
  local path=$1
  path_present "$path" && retain_cleanup "$path" STILL_PRESENT
  return 0
}
create_owned_directory() {
  local mode=$1 path=$2 inode
  [[ ! -e $path && ! -L $path ]] || fail PREEXISTING_OR_DANGLING_TARGET
  install -d -m "$mode" "$path"
  if ! inode=$(stat -c '%d:%i' "$path"); then
    cleanup_retained+=("$path:IDENTITY_UNAVAILABLE")
    fail CREATED_DIRECTORY_IDENTITY_UNAVAILABLE
  fi
  created_directories+=("$path"); created_directory_inodes+=("$inode")
}
release_lock() {
  if [[ $lock_owned -eq 1 ]] && path_present "$lock"; then
    if [[ -z $lock_inode ]] || ! same_inode "$lock" "$lock_inode"; then
      retain_cleanup "$lock" IDENTITY_CHANGED
    elif [[ ! -f $lock/owner || -L $lock/owner || -z $lock_owner_inode ]] || \
         ! same_lstat_inode "$lock/owner" "$lock_owner_inode" || \
         [[ $(cat "$lock/owner" 2>/dev/null) != "$lock_token" ]]; then
      retain_cleanup "$lock/owner" IDENTITY_CHANGED
    else
      if ! rm -f -- "$lock/owner"; then retain_cleanup "$lock/owner" REMOVE_FAILED; fi
      if path_present "$lock/owner"; then
        retain_cleanup "$lock/owner" STILL_PRESENT
      elif ! rmdir -- "$lock" 2>/dev/null; then
        retain_cleanup "$lock" REMOVE_FAILED
      fi
    fi
  fi
  record_remaining_path "$lock"
  lock_owned=0
}
cleanup() {
  local status=$? index path inode cleanup_state identity identity_rc
  trap - EXIT INT TERM
  if [[ $committed -eq 0 ]]; then
    if [[ $created_transaction -eq 1 ]] && path_present "$transaction"; then
      if [[ -z $transaction_inode ]] || ! same_lstat_inode "$transaction" "$transaction_inode"; then
        retain_cleanup "$transaction" IDENTITY_CHANGED
      elif ! python3.11 - "$transaction" "$expected_manifest" "$transaction_id" <<'PY' >/dev/null 2>&1
import json,sys
v=json.load(open(sys.argv[1])); raise SystemExit(0 if v.get("manifest_sha256")==sys.argv[2] and v.get("transaction_id")==sys.argv[3] else 1)
PY
      then
        retain_cleanup "$transaction" CONTENT_CHANGED
      elif ! rm -f -- "$transaction"; then
        retain_cleanup "$transaction" REMOVE_FAILED
      fi
    fi
    if [[ $created_current -eq 1 ]] && path_present "$current"; then
      if [[ -z $current_inode ]] || ! same_lstat_inode "$current" "$current_inode" || \
         [[ ! -L $current ]] || [[ $(readlink -f "$current" 2>/dev/null) != "$release" ]]; then
        retain_cleanup "$current" IDENTITY_CHANGED
      elif ! rm -f -- "$current"; then
        retain_cleanup "$current" REMOVE_FAILED
      fi
    fi
    if [[ $created_unit -eq 1 ]] && path_present "$unit"; then
      if [[ -z $unit_inode ]] || ! same_lstat_inode "$unit" "$unit_inode" || \
         [[ ! -f $unit || -L $unit ]] || \
         [[ $(sha256sum "$unit" 2>/dev/null | awk '{print $1}') != "$unit_sha" ]]; then
        retain_cleanup "$unit" IDENTITY_CHANGED
      elif ! rm -f -- "$unit"; then
        retain_cleanup "$unit" REMOVE_FAILED
      fi
    fi
    [[ $created_staging -eq 0 || -z $staging ]] || remove_owned_tree "$staging" "$staging_inode"
    [[ $created_release -eq 0 || -z $release ]] || remove_owned_tree "$release" "$release_inode"
    [[ $created_venv -eq 0 ]] || remove_owned_tree "$venv" "$venv_inode"
    [[ -z $pycache_inode ]] || remove_owned_tree "$(root_path /var/lib/xuanjun-binance/pycache)" "$pycache_inode"
    for ((index=${#created_directories[@]}-1; index>=0; index--)); do
      path=${created_directories[$index]}; inode=${created_directory_inodes[$index]}
      path_present "$path" || continue
      if ! same_inode "$path" "$inode"; then
        retain_cleanup "$path" IDENTITY_CHANGED
      elif ! rmdir -- "$path" 2>/dev/null; then
        retain_cleanup "$path" REMOVE_FAILED
      fi
    done
    if [[ $manage_identities -eq 1 ]]; then
      if [[ $created_user -eq 1 ]]; then
        identity_rc=0; identity=$(getent passwd xuanjun_binance 2>/dev/null) || identity_rc=$?
        if [[ $identity_rc -ne 0 ]]; then
          [[ $identity_rc -eq 2 ]] || retain_cleanup xuanjun_binance:passwd LOOKUP_FAILED
        elif [[ $identity != "$created_user_record" ]]; then
          retain_cleanup xuanjun_binance:passwd IDENTITY_CHANGED
        elif ! userdel xuanjun_binance >/dev/null 2>&1; then
          retain_cleanup xuanjun_binance:passwd REMOVE_FAILED
        fi
      fi
      if [[ $created_group -eq 1 ]]; then
        identity_rc=0; identity=$(getent group xuanjun_binance 2>/dev/null) || identity_rc=$?
        if [[ $identity_rc -ne 0 ]]; then
          [[ $identity_rc -eq 2 ]] || retain_cleanup xuanjun_binance:group LOOKUP_FAILED
        elif [[ $identity != "$created_group_record" ]]; then
          retain_cleanup xuanjun_binance:group IDENTITY_CHANGED
        elif ! groupdel xuanjun_binance >/dev/null 2>&1; then
          retain_cleanup xuanjun_binance:group REMOVE_FAILED
        fi
      fi
    fi
    if [[ $created_unit -eq 1 ]] && ! systemctl daemon-reload >/dev/null 2>&1; then
      retain_cleanup systemd:daemon-reload FAILED
    fi

    [[ $created_transaction -eq 0 ]] || record_remaining_path "$transaction"
    [[ $created_current -eq 0 ]] || record_remaining_path "$current"
    [[ $created_unit -eq 0 ]] || record_remaining_path "$unit"
    [[ $created_staging -eq 0 || -z $staging ]] || record_remaining_path "$staging"
    [[ $created_release -eq 0 || -z $release ]] || record_remaining_path "$release"
    [[ $created_venv -eq 0 ]] || record_remaining_path "$venv"
    [[ -z $pycache_inode ]] || record_remaining_path "$(root_path /var/lib/xuanjun-binance/pycache)"
    for path in "${created_directories[@]}"; do record_remaining_path "$path"; done
    if [[ $manage_identities -eq 1 && $created_user -eq 1 ]]; then
      if getent passwd xuanjun_binance >/dev/null 2>&1; then
        retain_cleanup xuanjun_binance:passwd STILL_PRESENT
      else
        identity_rc=$?; [[ $identity_rc -eq 2 ]] || retain_cleanup xuanjun_binance:passwd LOOKUP_FAILED
      fi
    fi
    if [[ $manage_identities -eq 1 && $created_group -eq 1 ]]; then
      if getent group xuanjun_binance >/dev/null 2>&1; then
        retain_cleanup xuanjun_binance:group STILL_PRESENT
      else
        identity_rc=$?; [[ $identity_rc -eq 2 ]] || retain_cleanup xuanjun_binance:group LOOKUP_FAILED
      fi
    fi
  fi
  release_lock
  cleanup_state=COMPLETE
  if [[ ${#cleanup_retained[@]} -gt 0 ]]; then cleanup_state=PARTIAL; fi
  if [[ $committed -eq 0 ]]; then
    printf 'INSTALL_STAGE=%s STATUS=HOLD CLEANUP=%s' "$stage" "$cleanup_state" >&2
    [[ ${#cleanup_retained[@]} -eq 0 ]] || printf ' RETAINED=%s' "$(IFS=,; printf '%s' "${cleanup_retained[*]}")" >&2
    printf '\n' >&2
  fi
  [[ -z $interrupt_reason ]] || printf 'INSTALL_STAGE=%s STATUS=HOLD REASON=%s CLEANUP=%s\n' "$stage" "$interrupt_reason" "$cleanup_state" >&2
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
if [[ $manage_identities -eq 1 ]]; then
  if ! getent group xuanjun_binance >/dev/null; then
    created_group=1; groupadd --system xuanjun_binance
    created_group_record=$(getent group xuanjun_binance) || fail CREATED_GROUP_IDENTITY_UNAVAILABLE
  fi
  if ! getent passwd xuanjun_binance >/dev/null; then
    created_user=1
    useradd --system --gid xuanjun_binance --home-dir /var/lib/xuanjun-binance --shell /sbin/nologin xuanjun_binance
    created_user_record=$(getent passwd xuanjun_binance) || fail CREATED_USER_IDENTITY_UNAVAILABLE
  fi
fi
create_owned_directory 0755 "$(root_path /opt/xuanjun-binance)"
create_owned_directory 0755 "$releases"
create_owned_directory 0700 "$(root_path /var/lib/xuanjun-binance)"
create_owned_directory 0700 "$(root_path /var/lib/xuanjun-binance/input)"
create_owned_directory 0700 "$(root_path /var/lib/xuanjun-binance/evidence)"
create_owned_directory 0700 "$(root_path /var/lib/xuanjun-binance/pycache)"
create_owned_directory 0700 "$(root_path /var/log/xuanjun-binance)"
pycache_inode=$(stat -c '%d:%i' "$(root_path /var/lib/xuanjun-binance/pycache)")
create_owned_directory 0750 "$(root_path /etc/xuanjun-binance)"
create_owned_directory 0750 "$(root_path /etc/xuanjun-binance/secretref)"
if [[ $test_mode != 1 ]]; then
  chown xuanjun_binance:xuanjun_binance "$(root_path /var/lib/xuanjun-binance)" "$(root_path /var/lib/xuanjun-binance/input)" \
    "$(root_path /var/lib/xuanjun-binance/evidence)" "$(root_path /var/lib/xuanjun-binance/pycache)" "$(root_path /var/log/xuanjun-binance)"
  chown root:xuanjun_binance "$(root_path /etc/xuanjun-binance)" "$(root_path /etc/xuanjun-binance/secretref)"
fi

release_id=${expected_manifest:0:16}; release="$releases/${release_id}"
staging="$(root_path /opt/xuanjun-binance/.staging-${release_id}-$$)"
[[ ! -e $release && ! -L $release && ! -e $staging && ! -L $staging ]] || fail RELEASE_TARGET_EXISTS
created_staging=1; install -d -m 0700 "$staging"; staging_inode=$(stat -c '%d:%i' "$staging") || fail STAGING_IDENTITY_UNAVAILABLE
cp -a --no-preserve=ownership -- "$candidate_root"/. "$staging"/
find "$staging" -type d -exec chmod 0755 {} +
find "$staging" -type f -exec chmod 0644 {} +
find "$staging" -type f -name '*.sh' -exec chmod 0755 {} +
chmod 0600 "$staging/minimal-runtime-manifest.json"
python3.11 "$staging/migration-prep/korea/validate_runtime_candidate.py" \
  "$staging" --expected-manifest-sha256 "$expected_manifest" >/dev/null || fail STAGING_VALIDATION_FAILED
mv -- "$staging" "$release"; created_staging=0; staging=; created_release=1; release_inode=$(stat -c '%d:%i' "$release")
created_venv=1; python3.11 -m venv "$venv"; venv_inode=$(stat -c '%d:%i' "$venv") || fail VENV_IDENTITY_UNAVAILABLE
PYTHONPYCACHEPREFIX="$(root_path /var/lib/xuanjun-binance/pycache)" "$venv/bin/python" -m compileall -q "$release/migration-prep"
ln -s "$release" "$current"; created_current=1; current_inode=$(stat -c '%d:%i' "$current") || fail CURRENT_IDENTITY_UNAVAILABLE
install -m 0644 "$release/migration-prep/korea/xuanjun-binance-shadow.service.in" "$unit"; created_unit=1
unit_inode=$(stat -c '%d:%i' "$unit") || fail UNIT_IDENTITY_UNAVAILABLE
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
created_transaction=1; transaction_inode=$(stat -c '%d:%i' "$transaction") || fail TRANSACTION_IDENTITY_UNAVAILABLE
systemctl daemon-reload
systemctl disable xuanjun-binance-shadow.service >/dev/null 2>&1 || true
systemctl is-active --quiet xuanjun-binance-shadow.service && fail SERVICE_UNEXPECTEDLY_ACTIVE
systemd-analyze verify "$unit"
"$release/migration-prep/korea/check-candidate.sh" --expected-transaction "$transaction" \
  --expected-manifest-sha256 "$expected_manifest"
release_lock
[[ ${#cleanup_retained[@]} -eq 0 ]] || fail COMMIT_LOCK_RELEASE_INCOMPLETE
committed=1
printf 'INSTALL_STAGE=COMMIT STATUS=PASS SERVICE_ENABLED=NO SERVICE_STARTED=NO TRANSACTION_ID=%s\n' "$transaction_id"
