#!/bin/bash
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL=C
export SYSTEMD_PAGER=cat
export SYSTEMD_COLORS=0
unset BASH_ENV ENV CDPATH
[ "$(id -u)" -eq 0 ] && [ "$#" -eq 0 ] || exit 2
[ "$(date -u +%s)" -lt 1792540800 ] || { echo STOP_AUTHORIZATION_EXPIRED; exit 3; }
case "$(hostname -s)" in
iZ6wee8q9z4t03hvqumwfhZ) XJ_ROLE=TOKYO ;;
iZmj7a5kwr75qc1tul4kf9Z) XJ_ROLE=KOREA ;;
*) echo STOP_HOST_MISMATCH; exit 4 ;;
esac
printf 'ROLE=%s\nHOST=%s\n' "$XJ_ROLE" "$(hostname -s)"
date -u '+UTC=%Y-%m-%dT%H:%M:%SZ'
awk '/MemTotal|MemAvailable/ {print}' /proc/meminfo
df -hP /
systemctl list-units --type=service --all --no-legend --no-pager |
awk '$1 ~ /^(xuanjun|yibi|finance|provider-neutral|tokyo-restricted|domestic-model|korea-novel|actions\.runner)/ {print $1,$3,$4}'
systemctl list-timers --all --no-pager |
awk '/xuanjun|yibi|finance/ {print $NF}'
printf 'PRODUCTION_MUTATION=NO\nINSPECTION_COMPLETE=YES\n'
