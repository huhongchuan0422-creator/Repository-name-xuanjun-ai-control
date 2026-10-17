#!/bin/bash
set -euo pipefail
test "$EUID" -eq 0
test "$(hostname -s)" = iZmj7a5kwr75qc1tul4kf9Z
umask 077
XJ_KH=$(find /root -maxdepth 1 -type f -name 'pr99-tokyo-hostkey.*' -print -quit)
test -n "$XJ_KH"
D=/root/xuanjun-offline-baseline-20261016
if test -e "$D" || test -L "$D"; then
  echo 'HOLD：目标目录已存在，先核对现有文件，未重新复制。'
  exit 2
fi
XJ_SESSION=$(mktemp -d /root/pr99-copy-session.XXXXXXXX)
XJ_SSH=(-T -S "$XJ_SESSION/socket" -o ControlMaster=auto -o ControlPersist=60 -o UserKnownHostsFile="$XJ_KH" -o GlobalKnownHostsFile=/dev/null -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ecdsa-sha2-nistp256 -o UpdateHostKeys=no -o ConnectTimeout=10 -o ConnectionAttempts=1 -o ClearAllForwardings=yes)
xj_close() { ssh -n "${XJ_SSH[@]}" -o BatchMode=yes -O exit root@47.245.53.152 >/dev/null 2>&1 || :; }
trap xj_close EXIT

ssh -n "${XJ_SSH[@]}" -o BatchMode=no -o NumberOfPasswordPrompts=1 root@47.245.53.152  'test "$(hostname -s)" = iZ6wee8q9z4t03hvqumwfhZ && test "$(id -u)" = 0 && test -r /root/xj-recovery-package.DZWI6n/recovery-baseline.tar.gz.enc'  || { echo 'STOP：东京root登录或源备份读取未通过，尚未复制。'; exit 2; }

mkdir -m 0700 "$D"
trap 'echo "HOLD：保留未完成文件，不覆盖、不重跑。"; exit 2' ERR
echo '东京root认证通过，开始复制1.32GB密文：'
timeout 900 ssh "${XJ_SSH[@]}" -o BatchMode=yes root@47.245.53.152  '/usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C /bin/bash -s' <<'REMOTE' | dd of="$D/baseline.enc.partial" bs=4M status=progress
set -euo pipefail
test "$EUID" -eq 0
test "$(hostname -s)" = iZ6wee8q9z4t03hvqumwfhZ
F=/root/xj-recovery-package.DZWI6n/recovery-baseline.tar.gz.enc
test -f "$F" && test ! -L "$F"
test "$(stat -c %u:%h "$F")" = 0:1
test "$(stat -c %s "$F")" = 1320571760
printf '%s  %s\n' ac43ec29186d4901016083387e6235288004abde6232792a2cc46d23f8e01093 "$F" | sha256sum -c - >/dev/null
cat "$F"
REMOTE
test "$(stat -c %s "$D/baseline.enc.partial")" = 1320571760
printf '%s  %s\n' ac43ec29186d4901016083387e6235288004abde6232792a2cc46d23f8e01093 "$D/baseline.enc.partial" | sha256sum -c -
mv -T "$D/baseline.enc.partial" "$D/recovery-baseline.tar.gz.enc"
sync -f "$D/recovery-baseline.tar.gz.enc"
echo "ENCRYPTED_BASELINE_OFFSITE=PASS API_UNTOUCHED=YES SERVICE_ACTIONS=0"
