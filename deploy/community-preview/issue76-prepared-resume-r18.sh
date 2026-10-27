#!/bin/sh
set -eu
[ "$#" -eq 1 ] || { echo 'usage: issue76-prepared-resume-r18.sh inspect|update|resume|query|recover' >&2; exit 2; }
case "$1" in inspect|update|resume|query|recover) ;; *) echo HOLD_OPERATION >&2; exit 2;; esac
exec sudo -n /usr/bin/python3 -I -B -S /home/admin/community_preview_prepared_resume_delivery.py "$1"
