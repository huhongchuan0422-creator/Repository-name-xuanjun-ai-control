#!/bin/bash
# Fixed baseline key transport and stream integrity proof; no archive extraction.
set -euo pipefail
test "$EUID" -eq 0
test "$(hostname -s)" = iZmj7a5kwr75qc1tul4kf9Z
umask 077
D=/root/xuanjun-offline-baseline-20261016
F="$D/recovery-baseline.tar.gz.enc"
P="$D/baseline.key.partial"
K="$D/baseline.key"
test ! -e "$P" && test ! -L "$P"
test ! -e "$K" && test ! -L "$K"
test ! -e "$D/key-custody-receipt.json" && test ! -L "$D/key-custody-receipt.json"
/usr/bin/python3.11 -I -B - <<'PY'
import os,stat
from pathlib import Path
d=Path("/root/xuanjun-offline-baseline-20261016")
for p in (Path("/"),Path("/root"),d):
 s=p.lstat()
 assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022,"UNTRUSTED_LOCAL_PARENT"
assert stat.S_IMODE(d.lstat().st_mode)==0o700,"PRIVATE_DIRECTORY_REQUIRED"
p=d/"recovery-baseline.tar.gz.enc";s=p.lstat()
assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600 and s.st_size==1320571760,"CIPHER_IDENTITY"
PY
printf '%s  %s\n' ac43ec29186d4901016083387e6235288004abde6232792a2cc46d23f8e01093 "$F" | sha256sum -c -
KH=$(find /root -maxdepth 1 -type f -name 'pr99-tokyo-hostkey.*' -print -quit)
test -n "$KH"
SSH=(-n -T -o UserKnownHostsFile="$KH" -o GlobalKnownHostsFile=/dev/null -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ecdsa-sha2-nistp256 -o UpdateHostKeys=no -o ConnectTimeout=10 -o ConnectionAttempts=1 -o NumberOfPasswordPrompts=1 -o ClearAllForwardings=yes -o ForwardAgent=no -o ForwardX11=no -o BatchMode=no)
set -o noclobber
trap 'echo "HOLD：保留私有文件和日志；不覆盖、不自动重试。"; exit 2' ERR
ssh "${SSH[@]}" root@47.245.53.152 '/usr/bin/python3 -I -B -c '\''import os,stat,sys
from pathlib import Path
assert os.geteuid()==0 and os.uname().nodename=="iZ6wee8q9z4t03hvqumwfhZ","WRONG_SOURCE_HOST"
p=Path("/root/xj-recovery-package.DZWI6n/key.txt")
for d in (Path("/"),Path("/root"),p.parent):
 s=d.lstat()
 assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022,"UNTRUSTED_KEY_PARENT"
fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW)
try:
 a=os.fstat(fd)
 assert stat.S_ISREG(a.st_mode) and a.st_uid==0 and a.st_nlink==1 and stat.S_IMODE(a.st_mode)==0o600 and a.st_size==65,"KEY_IDENTITY"
 data=os.read(fd,66);b=os.fstat(fd);c=p.lstat()
 assert (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns)==(b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns)==(c.st_dev,c.st_ino,c.st_size,c.st_mtime_ns),"KEY_CHANGED"
 assert len(data)==65 and data.endswith(b"\n") and b"\x00" not in data,"KEY_FORMAT"
finally:os.close(fd)
sys.stdout.buffer.write(data)
'\''' >"$P"
test "$(stat -c %u:%a:%h:%s "$P")" = 0:600:1:65
echo 'BASELINE_KEY_PRIVATE_COPY=RECEIVED; 正在校验解密流，不保存明文。'
timeout 600 openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 -in "$F" -pass "file:$P" 2>"$D/decrypt-stream-check.log" | sha256sum >"$D/decrypted-tar.sha256"
read -r DIGEST _ <"$D/decrypted-tar.sha256"
test "$DIGEST" = 1784372b17b3466ad4de946e03fc1a1866abccdab791fc871db08b827757154a
sync -f "$P"
test ! -e "$K" && test ! -L "$K"
mv -T "$P" "$K"
sync -f "$D"
/usr/bin/python3.11 -I -B - <<'PY'
import json,os,time
from pathlib import Path
d=Path("/root/xuanjun-offline-baseline-20261016")
r={"schema_version":1,"status":"BASELINE_KEY_CUSTODY_AND_DECRYPT_STREAM_PASS","host":os.uname().nodename,"epoch":int(time.time()),"cipher_bytes":1320571760,"cipher_sha256":"ac43ec29186d4901016083387e6235288004abde6232792a2cc46d23f8e01093","plaintext_tar_sha256":"1784372b17b3466ad4de946e03fc1a1866abccdab791fc871db08b827757154a","key_file_mode":"0600","key_value_printed":False,"plaintext_saved":False,"archive_extracted":False,"api_credentials_used":False,"service_actions":0,"scope":"HISTORICAL_BASELINE_RECOVERABILITY_NOT_FINAL_CURRENT_SNAPSHOT"}
with (d/"key-custody-receipt.json").open("x") as f:
 os.fchmod(f.fileno(),0o600);json.dump(r,f,sort_keys=True);f.write("\n");f.flush();os.fsync(f.fileno())
fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
print(json.dumps(r,sort_keys=True))
PY
echo 'KEY_CUSTODY=PASS DECRYPT_STREAM=PASS EXTRACTION=NOT_STARTED SERVICE_ACTIONS=0'
