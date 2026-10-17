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
    """Fail closed: structured metadata only, no raw strings on errors."""
    require(type(output) is str and type(stderr) is str and stderr == '')
    require(type(exit_code) is int and exit_code == 0)
    raw=output.encode('utf-8')
    require(len(raw) <= MAX_OUTPUT_BYTES and raw.endswith(b'\\n'))
    require(b'\\r' not in raw and b'\\x00' not in raw)
    rows=output.splitlines()
    require(25 <= len(rows) <= 75)
    pos=0
    values=[]
    def take(line):
        nonlocal pos
        require(pos<len(rows) and rows[pos]==line)
        pos+=1
        values.append(tuple(line.split('=',1)))
    def key(name, predicate):
        nonlocal pos
        require(pos<len(rows))
        row=rows[pos]
        require(row.startswith(name+'=') and row.count('=')==1)
        value=row[len(name)+1:]
        require(len(value)<=120 and predicate(value))
        values.append((name,value))
        pos+=1
        return value
    token=lambda x: re.fullmatch(r'[A-Za-z0-9_./:-]{1,120}',x) is not None
    number=lambda x: re.fullmatch(r'[0-9]{1,16}',x) is not None
    mode=lambda x: re.fullmatch(r'[0-7]{3,4}',x) is not None
    take('DIAG_SCHEMA=1')
    take('TARGET_HOST='+TARGET_HOST)
    take('EXEC_UID=0')
    key('PYTHON_VERSION',lambda x: re.fullmatch(r'3\\.6\\.[0-9]{1,3}',x) is not None)
    key('CGROUP_MOUNT_TYPE',lambda x:x in ('tmpfs','cgroup2fs'))
    # The fixed awk command prefixes only its first record; following v1
    # controller rows can contain commas, and name=systemd is legal.
    require(pos<len(rows) and rows[pos].startswith('CGROUP_PROC_SELF='))
    controllers=[]
    while pos<len(rows):
        line=rows[pos]
        if pos == 5:
            require(line.startswith('CGROUP_PROC_SELF='))
            line=line[len('CGROUP_PROC_SELF='):]
        elif line.startswith('SITE_PATH='):
            break
        require(len(line)<=140 and re.fullmatch(r'[0-9]{1,6}:[A-Za-z0-9_,=.-]*',line) is not None)
        require(line not in controllers and len(controllers)<6)
        controllers.append(line)
        pos+=1
    require(controllers and (controllers==['0:'] or all(x!='0:' for x in controllers)))
    values.append(('CGROUP_PROC_SELF_COUNT',str(len(controllers))))
    take('SITE_PATH='+SITE_PATH)
    if pos<len(rows) and rows[pos]=='SITE_STATUS=ABSENT':
        take('SITE_STATUS=ABSENT')
    else:
        require(pos<len(rows))
        line=rows[pos]
        match=re.fullmatch(r'SITE_UID=([0-9]{1,12}) SITE_GID=([0-9]{1,12}) SITE_MODE=([0-7]{3,4}) SITE_SIZE=([0-9]{1,16})',line)
        require(match is not None)
        require(match.group(1)=='0' and match.group(2)=='0')
        values.extend(zip(('SITE_UID','SITE_GID','SITE_MODE','SITE_SIZE'),match.groups()))
        pos+=1
        key('SITE_SHA256',lambda x:re.fullmatch(r'[0-9a-f]{64}',x) is not None)
    units=set()
    for unused in range(4):
        unit=key('UNIT',lambda x:x in UNIT_NAMES)
        require(unit not in units)
        units.add(unit)
        fields={}
        while pos<len(rows) and rows[pos].split('=',1)[0] in ('LoadState','ActiveState','SubState','MainPID','UnitFileState'):
            item=rows[pos]
            require(item.count('=')==1)
            k,v=item.split('=',1)
            require(k not in fields)
            allowed={'LoadState':('loaded','not-found','masked','error','bad-setting'),
                     'ActiveState':('active','inactive','failed','activating','deactivating','reloading'),
                     'SubState':('dead','running','exited','failed','start','stop','auto-restart','waiting','condition','listening','mounted'),
                     'UnitFileState':('enabled','disabled','masked','static','indirect','generated','transient','linked','linked-runtime','enabled-runtime','masked-runtime','bad','alias')}
            require(number(v) if k=='MainPID' else v in allowed[k])
            fields[k]=v
            values.append((k,v))
            pos+=1
        require(set(fields)=={'LoadState','ActiveState','SubState','MainPID','UnitFileState'})
    require(units==UNIT_NAMES)
    files=set()
    for unused in range(3):
        require(pos<len(rows))
        line=rows[pos]
        if line.startswith('DB_FILE_ABSENT='):
            path=key('DB_FILE_ABSENT',lambda x:x in DB_NAMES)
        else:
            m=re.fullmatch(r'DB_FILE=(\\S+) UID=([0-9]{1,12}) GID=([0-9]{1,12}) MODE=([0-7]{3,4}) SIZE=([0-9]{1,16})',line)
            require(m is not None and m.group(1) in DB_NAMES)
            path=m.group(1)
            values.append(('DB_FILE',path))
            pos+=1
        require(path not in files)
        files.add(path)
    require(files==DB_NAMES)
    for name in ('CANONICAL_WRITER','EPOCH','LEASE','FENCE','ROOT_TRUST','HISTORICAL_INVOKEID'):
        # Fixed command prints six consecutive lines, not six newlines in one value.
        if name=='CANONICAL_WRITER':
            require(pos<len(rows))
            value=rows[pos]
            expected='CANONICAL_WRITER=UNKNOWN'
            require(value==expected)
            pos+=1;values.append((name,'UNKNOWN'))
        else:
            take(name+'=UNKNOWN')
    take('DIAG_END=COMPLETE')
    require(pos==len(rows))
    return {'state':'DIAGNOSTIC_METADATA_ONLY','command_sha256':COMMAND_SHA256,
            'output_sha256':hashlib.sha256(raw).hexdigest(),
            'redispatch_allowed':False,'writer_verified':False,
            'site_execution_authorized':False,'metadata':values}
