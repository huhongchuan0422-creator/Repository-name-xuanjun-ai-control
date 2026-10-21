#!/bin/bash
# Root execution candidate. DO NOT execute without a later explicit Owner gate.
set -euo pipefail
: "${COMMUNITY_PREVIEW_RELEASE_SHA:?release sha required}"
: "${COMMUNITY_PREVIEW_PACKAGE:?package path required}"
: "${COMMUNITY_PREVIEW_PACKAGE_SHA256:?package sha required}"
HOST=community-preview.wenwenwenyiyiyi.work
SERVICE=xuanjun-community-preview.service
RELEASE_CREATED=0
if [ "${COMMUNITY_PREVIEW_TEST_MODE:-0}" = 1 ]; then
  test "$(/usr/bin/id -u)" -ne 0 || { echo ROOT_TEST_MODE_DENIED >&2; exit 65; }
  : "${COMMUNITY_PREVIEW_TEST_ROOT:?test root required}"
  case "$COMMUNITY_PREVIEW_TEST_ROOT" in /tmp/*|/var/tmp/*) ;; *) echo TEST_ROOT_DENIED >&2; exit 64;; esac
  BASE="$COMMUNITY_PREVIEW_TEST_ROOT/opt/xuanjun-community-preview"
  UNIT="$COMMUNITY_PREVIEW_TEST_ROOT/etc/systemd/system/$SERVICE"
  NGINX="$COMMUNITY_PREVIEW_TEST_ROOT/etc/nginx/conf.d/xuanjun-community-preview.conf"
  CERT_BASE="$COMMUNITY_PREVIEW_TEST_ROOT/etc/letsencrypt/live/$HOST"
  PROC_ROOT="$COMMUNITY_PREVIEW_TEST_ROOT/proc"
  SYSTEMCTL="${COMMUNITY_PREVIEW_SYSTEMCTL:?}"
  NGINX_BIN="${COMMUNITY_PREVIEW_NGINX:?}"
  CURL_BIN="${COMMUNITY_PREVIEW_CURL:?}"
  GETENT_BIN="${COMMUNITY_PREVIEW_GETENT:?}"
  ID_BIN="${COMMUNITY_PREVIEW_ID:?}"
else
  BASE=/opt/xuanjun-community-preview
  UNIT=/etc/systemd/system/$SERVICE
  NGINX=/etc/nginx/conf.d/xuanjun-community-preview.conf
  CERT_BASE=/etc/letsencrypt/live/$HOST
  PROC_ROOT=/proc
  SYSTEMCTL=systemctl
  NGINX_BIN=nginx
  CURL_BIN=curl
  GETENT_BIN=getent
  ID_BIN=id
fi
RELEASE="$BASE/releases/$COMMUNITY_PREVIEW_RELEASE_SHA"
CURRENT="$BASE/current"
TX="$BASE/transactions/$COMMUNITY_PREVIEW_RELEASE_SHA"
BACKUP="$TX/backup"
systemctl_cmd(){ "$SYSTEMCTL" "$@"; }
nginx_cmd(){ "$NGINX_BIN" "$@"; }
curl_cmd(){ "$CURL_BIN" "$@"; }
getent_cmd(){ "$GETENT_BIN" "$@"; }
id_cmd(){ "$ID_BIN" "$@"; }
if [ "${COMMUNITY_PREVIEW_TEST_MODE:-0}" != 1 ];then test "$(id_cmd -u)" -eq 0;fi
test "$(sha256sum "$COMMUNITY_PREVIEW_PACKAGE" | awk '{print $1}')" = "$COMMUNITY_PREVIEW_PACKAGE_SHA256"
test -f "$CERT_BASE/fullchain.pem"
test -f "$CERT_BASE/privkey.pem"
getent_cmd ahostsv4 "$HOST" >/dev/null
mkdir -p "$BASE/releases" "$BASE/transactions"
if [ -e "$RELEASE" ];then echo RELEASE_ALREADY_EXISTS >&2;exit 32;fi
test ! -e "$TX";mkdir -m 0700 "$TX";mkdir -m 0700 "$BACKUP"
if [ -L "$CURRENT" ];then readlink "$CURRENT" >"$BACKUP/current.symlink";elif [ -e "$CURRENT" ];then exit 31;else : >"$BACKUP/current.absent";fi
if [ -e "$UNIT" ];then cp -a "$UNIT" "$BACKUP/unit";else : >"$BACKUP/unit.absent";fi
if [ -e "$NGINX" ];then cp -a "$NGINX" "$BACKUP/nginx";else : >"$BACKUP/nginx.absent";fi
if systemctl_cmd is-enabled xuanjun-community-preview.service >/dev/null 2>&1;then : >"$BACKUP/enabled";else : >"$BACKUP/disabled";fi
if systemctl_cmd is-active "$SERVICE" >/dev/null 2>&1;then
  : >"$BACKUP/active"
  OLD_PID="$(systemctl_cmd show -p MainPID --value "$SERVICE")"
  case "$OLD_PID" in ''|*[!0-9]*) exit 33;; esac
  test "$OLD_PID" -gt 0
  printf '%s\n' "$OLD_PID" >"$BACKUP/mainpid"
else
  : >"$BACKUP/inactive"
  OLD_PID=0
fi
rollback(){
 set +e
 failures=""
 record(){ "$@" || failures="$failures\n$*"; }
 record systemctl_cmd stop xuanjun-community-preview.service
 if [ -e "$BACKUP/unit" ];then record cp -a "$BACKUP/unit" "$UNIT";else record rm -f "$UNIT";fi
 if [ -e "$BACKUP/nginx" ];then record cp -a "$BACKUP/nginx" "$NGINX";else record rm -f "$NGINX";fi
 if [ -e "$BACKUP/current.symlink" ];then record ln -sfn "$(cat "$BACKUP/current.symlink")" "$CURRENT";else record rm -f "$CURRENT";fi
 record systemctl_cmd daemon-reload
 if nginx_cmd -t >/dev/null 2>&1;then record systemctl_cmd reload nginx;else failures="$failures\nnginx_cmd -t";fi
 if [ -e "$BACKUP/enabled" ];then record systemctl_cmd enable xuanjun-community-preview.service;else record systemctl_cmd disable xuanjun-community-preview.service;fi
 if [ -e "$BACKUP/active" ];then
   if systemctl_cmd start "$SERVICE";then
     RESTORED_PID="$(systemctl_cmd show -p MainPID --value "$SERVICE" 2>/dev/null || true)"
     case "$RESTORED_PID" in ''|*[!0-9]*) failures="$failures\nrestore MainPID";;
       *) if [ "$RESTORED_PID" -le 0 ] || [ "$(readlink -f "$PROC_ROOT/$RESTORED_PID/cwd" 2>/dev/null || true)" != "$(readlink -f "$CURRENT" 2>/dev/null || true)" ];then failures="$failures\nrestore running version";fi;;
     esac
   else failures="$failures\nsystemctl start $SERVICE";fi
 else
   record systemctl_cmd stop "$SERVICE"
 fi
 if [ "$RELEASE_CREATED" = 1 ] && [ -d "$RELEASE" ];then record rm -rf --one-file-system "$RELEASE";fi
 if [ -n "$failures" ];then
   printf 'ROLLBACK_HOLD%s\n' "$failures" >"$TX/HOLD"
   sync "$TX/HOLD" 2>/dev/null || true
   echo ROLLBACK_HOLD
   return 1
 fi
 printf '%s\n' ROLLBACK_COMPLETE >"$TX/ROLLED_BACK"
 sync "$TX/ROLLED_BACK" 2>/dev/null || { printf '%s\n' ROLLBACK_DURABILITY_UNKNOWN >"$TX/HOLD"; echo ROLLBACK_HOLD; return 1; }
 echo ROLLBACK_COMPLETE
 return 0
}
trap 'rc=$?; if rollback; then exit 90; else exit 91; fi' ERR
mkdir "$RELEASE"
RELEASE_CREATED=1
tar -xzf "$COMMUNITY_PREVIEW_PACKAGE" -C "$RELEASE"
if [ "${COMMUNITY_PREVIEW_TEST_MODE:-0}" != 1 ];then chown -R root:root "$RELEASE";fi
find "$RELEASE" -type d -exec chmod 0755 {} +;find "$RELEASE" -type f -exec chmod 0644 {} +
NGINX_USER="$(nginx_cmd -T 2>&1 | sed -n 's/^user[[:space:]]\+\([^ ;]*\).*/\1/p' | head -1)"
test -n "$NGINX_USER";NGINX_UID="$(id_cmd -u "$NGINX_USER")";NGINX_GROUP="$(id_cmd -gn "$NGINX_USER")"
mkdir -p "$(dirname "$UNIT")" "$(dirname "$NGINX")"
cat >"$UNIT" <<EOF
[Unit]
Description=Xuanjun Community Isolated Preview
After=network.target
[Service]
Type=simple
User=githubrunner
Group=$NGINX_GROUP
RuntimeDirectory=xuanjun-community-preview
RuntimeDirectoryMode=0750
Environment=PYTHONUNBUFFERED=1
Environment=COMMUNITY_PREVIEW_ORIGIN=https://$HOST
Environment=COMMUNITY_PREVIEW_SOCKET=/run/xuanjun-community-preview/preview.sock
Environment=COMMUNITY_PREVIEW_NGINX_UID=$NGINX_UID
WorkingDirectory=$CURRENT
ExecStart=/usr/bin/python3 -I -B $CURRENT/deploy/community-preview/server.py
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/run/xuanjun-community-preview
EOF
cp "$RELEASE/deploy/community-preview/nginx.conf" "$NGINX"
ln -sfn "$RELEASE" "$CURRENT"
systemctl_cmd daemon-reload
nginx_cmd -t
if [ -e "$BACKUP/active" ];then systemctl_cmd restart "$SERVICE";else systemctl_cmd start "$SERVICE";fi
NEW_PID=0
for i in $(seq 1 30);do
  candidate="$(systemctl_cmd show -p MainPID --value "$SERVICE" 2>/dev/null || true)"
  case "$candidate" in ''|*[!0-9]*) candidate=0;; esac
  if [ "$candidate" -gt 0 ] 2>/dev/null;then
    NEW_PID="$candidate"
    if [ "$OLD_PID" -eq 0 ] || [ "$NEW_PID" -ne "$OLD_PID" ];then break;fi
  fi
  sleep 1
done
test "$NEW_PID" -gt 0
if [ "$OLD_PID" -gt 0 ];then test "$NEW_PID" -ne "$OLD_PID";fi
test "$(readlink -f "$PROC_ROOT/$NEW_PID/cwd")" = "$(readlink -f "$RELEASE")"
SOCKET_PATH="${COMMUNITY_PREVIEW_SOCKET_PATH:-/run/xuanjun-community-preview/preview.sock}"
for i in $(seq 1 30);do test -S "$SOCKET_PATH"&&break;sleep 1;done
test -S "$SOCKET_PATH"
nginx_cmd -t
systemctl_cmd reload nginx
curl_cmd --fail --silent --show-error --max-time 10 --resolve "$HOST:443:127.0.0.1" "https://$HOST/community/health"|grep -q '"READY"'
curl_cmd --fail --silent --show-error --max-time 10 --resolve "$HOST:443:127.0.0.1" "https://$HOST/"|grep -q 'Synthetic identities/data'
curl_cmd --fail --silent --show-error --max-time 10 "https://$HOST/community/health"|grep -q '"READY"'
curl_cmd --fail --silent --show-error --max-time 10 "https://$HOST/"|grep -q 'Synthetic identities/data'
FINAL_PID="$(systemctl_cmd show -p MainPID --value "$SERVICE")"
test "$FINAL_PID" = "$NEW_PID"
test "$(readlink -f "$PROC_ROOT/$FINAL_PID/cwd")" = "$(readlink -f "$RELEASE")"
trap - ERR
printf '%s\n' "$COMMUNITY_PREVIEW_RELEASE_SHA" >"$TX/COMMITTED"
echo COMMUNITY_PREVIEW_CANDIDATE_COMMITTED
