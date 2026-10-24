#!/bin/sh
# SOURCE REVIEW ONLY. Fixed STOPPED_HANDOFF_V1 carrier installer; does not run B/C.
set -eu
if [ "$#" -ne 2 ]; then
  echo 'usage: install-stopped-v1.sh ABS_CONTROL_ZIP ABS_MANIFEST_JSON' >&2
  exit 64
fi
case "$1:$2" in
  /*:/*) ;;
  *) echo 'absolute input paths required' >&2; exit 64 ;;
esac
exec /usr/bin/sudo -n /usr/bin/python3 -I -B -S scripts/community_preview_bc_install.py --archive "$1" --manifest "$2"
