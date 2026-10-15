#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'INSTALL_STAGE=%s STATUS=HOLD REASON=%s\n' "${stage}" "$1" >&2; exit 2; }
stage=ARGUMENTS
[[ ${EUID} -eq 0 ]] || fail ROOT_REQUIRED
[[ $(hostname) == iZmj7a5kwr75qc1tul4kf9Z ]] || fail WRONG_HOST
[[ $# -eq 2 ]] || fail USAGE_CANDIDATE_ROOT_EXPECTED_MANIFEST_SHA256
candidate_root=$1
expected_manifest=$2
[[ ${expected_manifest} =~ ^[0-9a-f]{64}$ ]] || fail MANIFEST_HASH_INVALID

unit=/etc/systemd/system/xuanjun-binance-shadow.service
transaction=/etc/xuanjun-binance/install-transaction.json
current=/opt/xuanjun-binance/current
venv=/opt/xuanjun-binance/venv

stage=NO_SIDE_EFFECT_PREFLIGHT
python3.11 - "$candidate_root" <<'PY' || fail PRIVATE_STAGING_PREFLIGHT_FAILED
import os, stat, sys
path = os.path.abspath(sys.argv[1])
if not os.path.isdir(path) or os.path.islink(path):
    raise SystemExit("HOLD: candidate root must be a real directory")
current = path
while True:
    value = os.lstat(current)
    if stat.S_ISLNK(value.st_mode) or value.st_uid != 0 or value.st_mode & 0o022:
        raise SystemExit("HOLD: candidate staging path is not root-protected")
    parent = os.path.dirname(current)
    if parent == current: break
    current = parent
if stat.S_IMODE(os.stat(path).st_mode) & 0o077:
    raise SystemExit("HOLD: candidate staging root must be private")
PY
python3.11 "${candidate_root}/migration-prep/korea/validate_runtime_candidate.py" \
  "$candidate_root" --expected-manifest-sha256 "$expected_manifest" >/dev/null || fail INPUT_VALIDATION_FAILED
printf 'SOURCE_MANIFEST_CONTENT_PASS\n'

python3.11 - <<'PY' || fail TARGET_AND_IDENTITY_PREFLIGHT_FAILED
import grp, os, pwd, stat
for path in ("/opt", "/var", "/var/lib", "/etc", "/var/log", "/etc/systemd", "/etc/systemd/system"):
    value = os.lstat(path)
    if stat.S_ISLNK(value.st_mode) or value.st_uid != 0 or value.st_mode & 0o022:
        raise SystemExit("HOLD: unsafe target parent " + path)
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

if [[ -e $transaction || -L $transaction ]]; then
  "${candidate_root}/migration-prep/korea/check-candidate.sh" --expected-transaction "$transaction" \
    || fail EXISTING_TRANSACTION_CHECK_FAILED
  printf 'INSTALL_STAGE=NO_SIDE_EFFECT_PREFLIGHT STATUS=PASS ALREADY_INSTALLED=YES\n'
  exit 0
fi
for path in /opt/xuanjun-binance /var/lib/xuanjun-binance /etc/xuanjun-binance /var/log/xuanjun-binance "$unit"; do
  [[ ! -e $path && ! -L $path ]] || fail PREEXISTING_OR_DANGLING_TARGET
done
for protected in morelogin-socks5-permanent.service xuanjun-novel-factory.service postgresql.service redis.service yibi-api.service yibi-scheduler.service; do
  systemctl show "$protected" -p ActiveState -p SubState --no-pager >/dev/null || true
done

stage=MUTATION
created_group=0; created_user=0; staging=; release=; committed=0
cleanup() {
  status=$?
  if [[ $committed -eq 0 ]]; then
    [[ -e $transaction && ! -L $transaction ]] && rm -f -- "$transaction"
    [[ -n ${staging} && -e ${staging} ]] && rm -rf --one-file-system "$staging"
    [[ -L $current ]] && rm -f -- "$current"
    [[ -e $unit && ! -L $unit ]] && rm -f -- "$unit"
    [[ -n ${release} && -d ${release} && ! -L ${release} ]] && rm -rf --one-file-system "$release"
    [[ -d $venv && ! -L $venv ]] && rm -rf --one-file-system "$venv"
    [[ -d /opt/xuanjun-binance/releases ]] && rmdir /opt/xuanjun-binance/releases 2>/dev/null || true
    [[ -d /opt/xuanjun-binance ]] && rmdir /opt/xuanjun-binance 2>/dev/null || true
    [[ -d /etc/xuanjun-binance/secretref ]] && rmdir /etc/xuanjun-binance/secretref 2>/dev/null || true
    [[ -d /etc/xuanjun-binance ]] && rmdir /etc/xuanjun-binance 2>/dev/null || true
    [[ -d /var/lib/xuanjun-binance/input ]] && rmdir /var/lib/xuanjun-binance/input 2>/dev/null || true
    [[ -d /var/lib/xuanjun-binance/evidence ]] && rmdir /var/lib/xuanjun-binance/evidence 2>/dev/null || true
    [[ -d /var/lib/xuanjun-binance/pycache && ! -L /var/lib/xuanjun-binance/pycache ]] && rm -rf --one-file-system /var/lib/xuanjun-binance/pycache
    [[ -d /var/lib/xuanjun-binance ]] && rmdir /var/lib/xuanjun-binance 2>/dev/null || true
    [[ -d /var/log/xuanjun-binance ]] && rmdir /var/log/xuanjun-binance 2>/dev/null || true
    [[ $created_user -eq 1 ]] && userdel xuanjun_binance >/dev/null 2>&1 || true
    [[ $created_group -eq 1 ]] && groupdel xuanjun_binance >/dev/null 2>&1 || true
    systemctl daemon-reload >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap cleanup EXIT INT TERM

if ! getent group xuanjun_binance >/dev/null; then groupadd --system xuanjun_binance; created_group=1; fi
if ! getent passwd xuanjun_binance >/dev/null; then
  useradd --system --gid xuanjun_binance --home-dir /var/lib/xuanjun-binance --shell /sbin/nologin xuanjun_binance
  created_user=1
fi
install -d -o root -g root -m 0755 /opt/xuanjun-binance /opt/xuanjun-binance/releases
install -d -o xuanjun_binance -g xuanjun_binance -m 0700 /var/lib/xuanjun-binance /var/lib/xuanjun-binance/input /var/lib/xuanjun-binance/evidence /var/lib/xuanjun-binance/pycache /var/log/xuanjun-binance
install -d -o root -g xuanjun_binance -m 0750 /etc/xuanjun-binance /etc/xuanjun-binance/secretref

release_id=${expected_manifest:0:16}
release="/opt/xuanjun-binance/releases/${release_id}"
staging="/opt/xuanjun-binance/.staging-${release_id}"
[[ ! -e $release && ! -L $release && ! -e $staging && ! -L $staging ]] || fail RELEASE_TARGET_EXISTS
install -d -o root -g root -m 0700 "$staging"
cp -a --no-preserve=ownership -- "$candidate_root"/. "$staging"/
chown -R root:root "$staging"
find "$staging" -type d -exec chmod 0755 {} +
find "$staging" -type f -exec chmod 0644 {} +
find "$staging" -type f -name '*.sh' -exec chmod 0755 {} +
chmod 0600 "$staging/minimal-runtime-manifest.json"
python3.11 "$staging/migration-prep/korea/validate_runtime_candidate.py" \
  "$staging" --expected-manifest-sha256 "$expected_manifest" >/dev/null || fail STAGING_VALIDATION_FAILED
mv -- "$staging" "$release"; staging=
python3.11 -m venv "$venv"
PYTHONPYCACHEPREFIX=/var/lib/xuanjun-binance/pycache "$venv/bin/python" -m compileall -q "$release/migration-prep"
ln -s "$release" "$current"
install -o root -g root -m 0644 "$release/migration-prep/korea/xuanjun-binance-shadow.service.in" "$unit"
unit_sha=$(sha256sum "$unit" | awk '{print $1}')
venv_python_sha=$(sha256sum "$venv/bin/python" | awk '{print $1}')
content_sha=$(python3.11 - "$release/minimal-runtime-manifest.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["content_sha256"])
PY
)
python3.11 - "$transaction" "$expected_manifest" "$content_sha" "$release" "$unit_sha" "$venv_python_sha" <<'PY'
import json, os, sys, tempfile
target, manifest, content, release, unit_sha, python_sha = sys.argv[1:]
value = {"schema_version": 1, "transaction_id": "install-" + manifest[:16],
         "manifest_sha256": manifest, "content_sha256": content,
         "release_path": release, "current_target": release,
         "unit_path": "/etc/systemd/system/xuanjun-binance-shadow.service",
         "unit_sha256": unit_sha, "venv_path": "/opt/xuanjun-binance/venv",
         "venv_python_sha256": python_sha,
         "owned_objects": [release, "/opt/xuanjun-binance/current", "/opt/xuanjun-binance/venv",
                           "/etc/systemd/system/xuanjun-binance-shadow.service"],
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
systemctl daemon-reload
systemctl disable xuanjun-binance-shadow.service >/dev/null 2>&1 || true
systemctl is-active --quiet xuanjun-binance-shadow.service && fail SERVICE_UNEXPECTEDLY_ACTIVE
systemd-analyze verify "$unit"
"$release/migration-prep/korea/check-candidate.sh" --expected-transaction "$transaction"
committed=1
printf 'INSTALL_STAGE=COMMIT STATUS=PASS SERVICE_ENABLED=NO SERVICE_STARTED=NO\n'
