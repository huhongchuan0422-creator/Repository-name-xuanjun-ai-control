#!/bin/bash
# Root execution candidate. DO NOT execute without a later explicit Owner gate.
set -euo pipefail
: "${COMMUNITY_PREVIEW_RELEASE_SHA:?release sha required}"
: "${COMMUNITY_PREVIEW_PACKAGE:?package path required}"
: "${COMMUNITY_PREVIEW_PACKAGE_SHA256:?package sha required}"
HOST=community-preview.wenwenwenyiyiyi.work
BASE=/opt/xuanjun-community-preview
RELEASE="$BASE/releases/$COMMUNITY_PREVIEW_RELEASE_SHA"
CURRENT="$BASE/current"
UNIT=/etc/systemd/system/xuanjun-community-preview.service
NGINX=/etc/nginx/conf.d/xuanjun-community-preview.conf
TX="$BASE/transactions/$COMMUNITY_PREVIEW_RELEASE_SHA"
BACKUP="$TX/backup"
test "$(id -u)" -eq 0
test "$(sha256sum "$COMMUNITY_PREVIEW_PACKAGE" | awk '{print $1}')" = "$COMMUNITY_PREVIEW_PACKAGE_SHA256"
test -f /etc/letsencrypt/live/$HOST/fullchain.pem
test -f /etc/letsencrypt/live/$HOST/privkey.pem
getent ahostsv4 "$HOST" >/dev/null
mkdir -p "$BASE/releases" "$BASE/transactions"
test ! -e "$TX";mkdir -m 0700 "$TX";mkdir -m 0700 "$BACKUP"
if [ -L "$CURRENT" ];then readlink "$CURRENT" >"$BACKUP/current.symlink";elif [ -e "$CURRENT" ];then exit 31;else : >"$BACKUP/current.absent";fi
if [ -e "$UNIT" ];then cp -a "$UNIT" "$BACKUP/unit";else : >"$BACKUP/unit.absent";fi
if [ -e "$NGINX" ];then cp -a "$NGINX" "$BACKUP/nginx";else : >"$BACKUP/nginx.absent";fi
if systemctl is-enabled xuanjun-community-preview.service >/dev/null 2>&1;then : >"$BACKUP/enabled";else : >"$BACKUP/disabled";fi
if systemctl is-active xuanjun-community-preview.service >/dev/null 2>&1;then : >"$BACKUP/active";else : >"$BACKUP/inactive";fi
rollback(){
 set +e
 systemctl stop xuanjun-community-preview.service >/dev/null 2>&1
 if [ -e "$BACKUP/unit" ];then cp -a "$BACKUP/unit" "$UNIT";else rm -f "$UNIT";fi
 if [ -e "$BACKUP/nginx" ];then cp -a "$BACKUP/nginx" "$NGINX";else rm -f "$NGINX";fi
 if [ -e "$BACKUP/current.symlink" ];then ln -sfn "$(cat "$BACKUP/current.symlink")" "$CURRENT";else rm -f "$CURRENT";fi
 systemctl daemon-reload
 nginx -t && systemctl reload nginx
 if [ -e "$BACKUP/enabled" ];then systemctl enable xuanjun-community-preview.service >/dev/null 2>&1;else systemctl disable xuanjun-community-preview.service >/dev/null 2>&1;fi
 if [ -e "$BACKUP/active" ];then systemctl start xuanjun-community-preview.service;fi
 if [ -d "$RELEASE" ];then rm -rf --one-file-system "$RELEASE";fi
 echo ROLLBACK_COMPLETE
}
trap 'rollback; exit 90' ERR
test ! -e "$RELEASE";mkdir "$RELEASE"
tar -xzf "$COMMUNITY_PREVIEW_PACKAGE" -C "$RELEASE"
chown -R root:root "$RELEASE";find "$RELEASE" -type d -exec chmod 0755 {} +;find "$RELEASE" -type f -exec chmod 0644 {} +
NGINX_USER="$(nginx -T 2>&1 | sed -n 's/^user[[:space:]]\+\([^ ;]*\).*/\1/p' | head -1)"
test -n "$NGINX_USER";NGINX_UID="$(id -u "$NGINX_USER")";NGINX_GROUP="$(id -gn "$NGINX_USER")"
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
systemctl daemon-reload
nginx -t
systemctl start xuanjun-community-preview.service
for i in $(seq 1 30);do test -S /run/xuanjun-community-preview/preview.sock&&break;sleep 1;done
test -S /run/xuanjun-community-preview/preview.sock
nginx -t
systemctl reload nginx
curl --fail --silent --show-error --max-time 10 --resolve "$HOST:443:127.0.0.1" "https://$HOST/community/health"|grep -q '"READY"'
curl --fail --silent --show-error --max-time 10 --resolve "$HOST:443:127.0.0.1" "https://$HOST/"|grep -q 'Synthetic identities/data'
curl --fail --silent --show-error --max-time 10 "https://$HOST/community/health"|grep -q '"READY"'
curl --fail --silent --show-error --max-time 10 "https://$HOST/"|grep -q 'Synthetic identities/data'
trap - ERR
printf '%s\n' "$COMMUNITY_PREVIEW_RELEASE_SHA" >"$TX/COMMITTED"
echo COMMUNITY_PREVIEW_CANDIDATE_COMMITTED
