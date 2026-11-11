#!/bin/bash
# Explicit continuation of fixed encrypted bytes; no automatic retry or decrypt.
set -euo pipefail
test "$EUID" -eq 0
test "$(hostname -s)" = iZmj7a5kwr75qc1tul4kf9Z
umask 077
D=/root/xuanjun-offline-baseline-20261016
F="$D/baseline.enc.partial"
SHA=ac43ec29186d4901016083387e6235288004abde6232792a2cc46d23f8e01093
TOTAL=1320571760
if test -f "$D/recovery-baseline.tar.gz.enc" && test ! -L "$D/recovery-baseline.tar.gz.enc"; then
  test "$(stat -c %s "$D/recovery-baseline.tar.gz.enc")" = "$TOTAL"
  printf '%s  %s\n' "$SHA" "$D/recovery-baseline.tar.gz.enc" | sha256sum -c -
  echo 'ENCRYPTED_BASELINE_OFFSITE=PASS ALREADY_COMPLETE=YES NO_TRANSFER=YES'
  exit 0
fi
/usr/bin/python3.11 -I -B - <<'PY'
import os,stat
from pathlib import Path
d=Path("/root/xuanjun-offline-baseline-20261016")
for p in (Path("/"),Path("/root"),d):
 s=p.lstat()
 assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022,"UNTRUSTED_PARENT"
assert stat.S_IMODE(d.lstat().st_mode)==0o700,"PRIVATE_DIRECTORY_REQUIRED"
p=d/"baseline.enc.partial";s=p.lstat()
assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,"PRIVATE_PARTIAL_REQUIRED"
assert 0<=s.st_size<=1320571760,"PARTIAL_SIZE_INVALID"
for proc in Path("/proc").iterdir():
 if not proc.name.isdigit():continue
 try:fds=list((proc/"fd").iterdir())
 except FileNotFoundError:continue
 for fd in fds:
  try:
   info=fd.stat()
   if (info.st_dev,info.st_ino)!=(s.st_dev,s.st_ino):continue
   data=(proc/"fdinfo"/fd.name).read_text()
   flags=int(next(v.split()[1] for v in data.splitlines() if v.startswith("flags:")),8)
   assert flags&os.O_ACCMODE==os.O_RDONLY,"TRANSFER_STILL_RUNNING_DO_NOT_RESUME"
  except FileNotFoundError:continue
print("NO_ACTIVE_PARTIAL_WRITER=PASS")
PY
finish() {
  test "$(stat -c %s "$F")" = "$TOTAL"
  printf '%s  %s\n' "$SHA" "$F" | sha256sum -c -
  test ! -e "$D/recovery-baseline.tar.gz.enc"
  test ! -L "$D/recovery-baseline.tar.gz.enc"
  sync -f "$F"
  mv -T "$F" "$D/recovery-baseline.tar.gz.enc"
  sync -f "$D"
  echo 'ENCRYPTED_BASELINE_OFFSITE=PASS API_UNTOUCHED=YES SERVICE_ACTIONS=0'
}
N=$(stat -c %s "$F")
if test "$N" = "$TOTAL"; then finish; exit 0; fi
PREFIX=$(sha256sum "$F"); PREFIX=${PREFIX%% *}
XJ_KH=$(find /root -maxdepth 1 -type f -name 'pr99-tokyo-hostkey.*' -print -quit)
test -n "$XJ_KH"
XJ_SESSION=$(mktemp -d /root/pr99-resume-session.XXXXXXXX)
XJ_SSH=(-T -S "$XJ_SESSION/socket" -o ControlMaster=auto -o ControlPersist=60 -o UserKnownHostsFile="$XJ_KH" -o GlobalKnownHostsFile=/dev/null -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ecdsa-sha2-nistp256 -o UpdateHostKeys=no -o ConnectTimeout=10 -o ConnectionAttempts=1 -o ClearAllForwardings=yes)
xj_close() { ssh -n "${XJ_SSH[@]}" -o BatchMode=yes -O exit root@47.245.53.152 >/dev/null 2>&1 || :; }
trap xj_close EXIT
ssh -n "${XJ_SSH[@]}" -o BatchMode=no -o NumberOfPasswordPrompts=1 root@47.245.53.152  'test "$(hostname -s)" = iZ6wee8q9z4t03hvqumwfhZ && test "$(id -u)" = 0'
test "$(stat -c %s "$F")" = "$N"
CHECK=$(sha256sum "$F"); test "${CHECK%% *}" = "$PREFIX"
set -o noclobber
printf 'offset=%s\nprefix_sha256=%s\n' "$N" "$PREFIX" > "$D/resume-$N.started"
set +o noclobber
trap 'echo "HOLD：保留续传部分和记录，禁止自动重试。"; exit 2' ERR
printf '已保留 %s 字节；从此位置续传，最长2小时。\n' "$N"
timeout 7200 ssh "${XJ_SSH[@]}" -o BatchMode=yes root@47.245.53.152  "/usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C XJ_OFFSET=$N XJ_PREFIX=$PREFIX /bin/bash -s" <<'REMOTE' | dd of="$F" oflag=append conv=notrunc bs=4M status=progress
set -euo pipefail
test "$EUID" -eq 0
test "$(hostname -s)" = iZ6wee8q9z4t03hvqumwfhZ
F=/root/xj-recovery-package.DZWI6n/recovery-baseline.tar.gz.enc
test -f "$F" && test ! -L "$F"
test "$(stat -c %u:%h "$F")" = 0:1
test "$(stat -c %s "$F")" = 1320571760
printf '%s  %s\n' ac43ec29186d4901016083387e6235288004abde6232792a2cc46d23f8e01093 "$F" | sha256sum -c - >/dev/null
SOURCE_PREFIX=$(head -c "$XJ_OFFSET" "$F" | sha256sum)
test "${SOURCE_PREFIX%% *}" = "$XJ_PREFIX"
tail -c "+$((XJ_OFFSET+1))" "$F"
REMOTE
finish
