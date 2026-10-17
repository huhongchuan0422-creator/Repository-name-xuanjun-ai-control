"""Pinned UK phase-one read-only diagnostic and strict output reducer.
Not an execution permit. This module never dispatches a cloud request.
"""
import hashlib
import re

COMMAND = "#!/bin/bash\nset -euo pipefail\nexport LC_ALL=C\nexport PYTHONDONTWRITEBYTECODE=1\nprintf 'DIAG_SCHEMA=1\\n'\nprintf 'TARGET_HOST='; /bin/hostname -s\nif [ \"$(/bin/hostname -s)\" != 'iZd7oeikknn1z21sq6ji6zZ' ]; then printf 'STOP=HOST_MISMATCH\\n'; exit 40; fi\nprintf 'EXEC_UID='; /usr/bin/id -u\nprintf 'PYTHON_VERSION='; /usr/bin/python3 -I -B -c 'import sys; print(\"%d.%d.%d\" % sys.version_info[:3])'\nprintf 'CGROUP_MOUNT_TYPE='; /usr/bin/stat -fc '%T' /sys/fs/cgroup\nprintf 'CGROUP_PROC_SELF='; /usr/bin/awk -F: 'NR<=6 {print $1 \":\" $2}' /proc/self/cgroup\nsite='/usr/local/libexec/xuanjun-p2-site/P2_SITE_ENTRY.py'\nprintf 'SITE_PATH=%s\\n' \"$site\"\nif [ -L \"$site\" ]; then printf 'STOP=SITE_SYMLINK\\n'; exit 41; fi\nif [ -f \"$site\" ]; then\n  /usr/bin/stat -c 'SITE_UID=%u SITE_GID=%g SITE_MODE=%a SITE_SIZE=%s' -- \"$site\"\n  /usr/bin/sha256sum -- \"$site\" | /usr/bin/awk '{print \"SITE_SHA256=\" $1}'\nelse\n  printf 'SITE_STATUS=ABSENT\\n'\nfi\nfor unit in xuanjun-stage1-minimal.service openclaw.service xuanjun-owner-callback.service xuanjun-owner-dashboard.service; do\n  printf 'UNIT=%s\\n' \"$unit\"\n  /bin/systemctl show --no-pager --property=LoadState,ActiveState,SubState,MainPID,UnitFileState -- \"$unit\" | /usr/bin/grep -E '^(LoadState|ActiveState|SubState|MainPID|UnitFileState)=' || true\ndone\nfor path in /home/xuanjun_dev/uk-stage1-minimal/state.sqlite /home/xuanjun_dev/uk-stage1-minimal/state.sqlite-wal /home/xuanjun_dev/uk-stage1-minimal/state.sqlite-shm; do\n  if [ -e \"$path\" ]; then\n    /usr/bin/stat -c 'DB_FILE=%n UID=%u GID=%g MODE=%a SIZE=%s' -- \"$path\"\n  else\n    printf 'DB_FILE_ABSENT=%s\\n' \"$path\"\n  fi\ndone\nprintf 'CANONICAL_WRITER=UNKNOWN\\nEPOCH=UNKNOWN\\nLEASE=UNKNOWN\\nFENCE=UNKNOWN\\nROOT_TRUST=UNKNOWN\\nHISTORICAL_INVOKEID=UNKNOWN\\n'\nprintf 'DIAG_END=COMPLETE\\n'\n".encode('utf-8')
COMMAND_SHA256 = '523f3ba132b94efec8bf81980d9db96e083e4779628a29b6540a8bcee67d2794'
TARGET_HOST = 'iZd7oeikknn1z21sq6ji6zZ'
TARGET_REGION = 'eu-west-1'
TARGET_INSTANCE = '40dfc6a47d5e4363b9da7d0d6ab01cb1'
TARGET_WORKING_USER = 'root'
TIMEOUT_SECONDS = 60
MAX_OUTPUT_BYTES = 4096
KEYS = frozenset(('DIAG_SCHEMA','TARGET_HOST','EXEC_UID','PYTHON_VERSION',
    'CGROUP_MOUNT_TYPE','CGROUP_PROC_SELF','SITE_PATH','SITE_UID','SITE_GID',
    'SITE_MODE','SITE_SIZE','SITE_SHA256','SITE_STATUS','UNIT','LoadState',
    'ActiveState','SubState','MainPID','UnitFileState','DB_FILE',
    'DB_FILE_ABSENT','UID','GID','MODE','SIZE','CANONICAL_WRITER',
    'EPOCH','LEASE','FENCE','ROOT_TRUST','HISTORICAL_INVOKEID',
    'DIAG_END','STOP'))
UNIT_NAMES = frozenset(('xuanjun-stage1-minimal.service', 'openclaw.service',
    'xuanjun-owner-callback.service','xuanjun-owner-dashboard.service'))
DB_NAMES = frozenset(('/home/xuanjun_dev/uk-stage1-minimal/state.sqlite',
    '/home/xuanjun_dev/uk-stage1-minimal/state.sqlite-wal',
    '/home/xuanjun_dev/uk-stage1-minimal/state.sqlite-shm'))
SITE_PATH = '/usr/local/libexec/xuanjun-p2-site/P2_SITE_ENTRY.py'

class DiagnosticHold(Exception):
    pass

def require(condition):
    if not condition:
        raise DiagnosticHold('DIAGNOSTIC_HOLD_NO_RETRY')

def command_content():
    require(len(COMMAND) == 1771 and
            hashlib.sha256(COMMAND).hexdigest() == COMMAND_SHA256)
    return COMMAND.decode('utf-8')

def safe_receipt(output, stderr='', exit_code=0):
    """Reject unknown or sensitive data rather than returning untrusted output.

    stderr is never included in successful or failed public receipts.
    Caller must not log the raw response before invoking this reducer.
    """
    require(type(output) is str and type(stderr) is str and not stderr)
    require(type(exit_code) is int and exit_code == 0)
    raw = output.encode('utf-8')
    require(len(raw) <= MAX_OUTPUT_BYTES and raw.endswith(b'\\n'))
    require(b'\\r' not in raw and b'\\x00' not in raw)
    rows = output.splitlines()
    require(rows and rows[0] == 'DIAG_SCHEMA=1' and rows[-1] == 'DIAG_END=COMPLETE')
    values = []
    for row in rows:
        require(row.count('=') == 1)
        key, value = row.split('=', 1)
        require(key in KEYS and len(value) <= 160 and
                re.fullmatch(r'[A-Za-z0-9_./:-]*', value) is not None)
        if key == 'TARGET_HOST': require(value == TARGET_HOST)
        elif key == 'EXEC_UID': require(value == '0')
        elif key == 'PYTHON_VERSION': require(value == '3.6.8')
        elif key == 'SITE_PATH': require(value == SITE_PATH)
        elif key == 'UNIT': require(value in UNIT_NAMES)
        elif key in ('DB_FILE','DB_FILE_ABSENT'): require(value in DB_NAMES)
        elif key in ('CANONICAL_WRITER','EPOCH','LEASE','FENCE',
                     'ROOT_TRUST','HISTORICAL_INVOKEID'): require(value == 'UNKNOWN')
        elif key == 'SITE_SHA256': require(re.fullmatch(r'[0-9a-f]{64}', value) is not None)
        elif key == 'STOP': raise DiagnosticHold('REMOTE_STOP_NO_RETRY')
        values.append((key, value))
    require(sum(k == 'TARGET_HOST' for k,v in values) == 1)
    require(sum(k == 'EXEC_UID' for k,v in values) == 1)
    require(sum(k == 'PYTHON_VERSION' for k,v in values) == 1)
    return {'state':'DIAGNOSTIC_METADATA_ONLY',
            'command_sha256': COMMAND_SHA256,
            'output_sha256': hashlib.sha256(raw).hexdigest(),
            'redispatch_allowed':False,
            'writer_verified':False,
            'site_execution_authorized':False,
            'metadata':values}
