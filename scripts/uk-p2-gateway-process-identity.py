"""Read active UK OpenClaw Gateway process identity without mutation.

Python 3.6.8 compatible. No model calls, no secret values.
"""
from __future__ import print_function

import hashlib
import json
import os
import pwd
import socket
import stat
import subprocess
import sys

HOST='iZd7oeikknn1z21sq6ji6zZ'
USER='xuanjun_dev'
UNIT='xuanjun-uk-openclaw.service'


def file_digest(path, maximum=256*1024*1024):
    real=os.path.realpath(path)
    fd=os.open(real,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>maximum:
            raise ValueError('UNSAFE_FILE')
        h=hashlib.sha256();total=0
        while True:
            raw=os.read(fd,65536)
            if not raw:break
            total+=len(raw)
            if total>maximum:raise ValueError('FILE_LIMIT')
            h.update(raw)
        return {'path':real,'sha256':h.hexdigest(),'uid':info.st_uid,
                'mode':oct(stat.S_IMODE(info.st_mode))}
    finally:
        os.close(fd)


def show(*names):
    out={}
    for name in names:
        value=subprocess.check_output(
            ['/usr/bin/systemctl','show',UNIT,'--property='+name,'--value'],
            universal_newlines=True,timeout=10).strip()
        out[name]=value
    return out


def read_text(path,maximum=131072):
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        raw=os.read(fd,maximum+1)
        if len(raw)>maximum:raise ValueError('PROC_LIMIT')
        return raw
    finally:os.close(fd)


def main():
    uid=pwd.getpwnam(USER).pw_uid
    if socket.gethostname().split('.')[0]!=HOST or os.geteuid()!=uid:
        raise SystemExit('HOLD_FIXED_UK_IDENTITY')
    if sys.version_info[:3]!=(3,6,8):
        raise SystemExit('HOLD_PYTHON_VERSION')

    unit=show('User','ActiveState','SubState','ControlGroup','MainPID','FragmentPath')
    if unit['User']!=USER or unit['ActiveState']!='active' or unit['SubState']!='running':
        raise SystemExit('HOLD_GATEWAY_UNIT_NOT_ACTIVE')
    pid=int(unit['MainPID'])
    if pid<2:raise SystemExit('HOLD_GATEWAY_PID')
    status=read_text('/proc/%d/status'%pid).decode('ascii','strict')
    uid_line=next((v for v in status.splitlines() if v.startswith('Uid:')),None)
    if uid_line is None or any(int(v)!=uid for v in uid_line.split()[1:]):
        raise SystemExit('HOLD_GATEWAY_UID')
    cgroup=read_text('/proc/%d/cgroup'%pid).decode('utf-8','strict').splitlines()
    paths=[line.split(':',2)[-1] for line in cgroup if line.count(':')>=2]
    if unit['ControlGroup'] not in paths:
        raise SystemExit('HOLD_GATEWAY_CGROUP')

    gateway=file_digest('/proc/%d/exe'%pid)
    python=file_digest('/usr/bin/python3')
    cmdline=read_text('/proc/%d/cmdline'%pid)
    print(json.dumps({
        'state':'P2_UK_GATEWAY_PROCESS_IDENTITY_VERIFIED',
        'python_version':list(sys.version_info[:3]),
        'gateway':gateway,
        'gateway_uid':uid,
        'gateway_cgroup':unit['ControlGroup'],
        'gateway_pid':pid,
        'gateway_cmdline_sha256':hashlib.sha256(cmdline).hexdigest(),
        'python':python,
        'fragment_path':unit['FragmentPath'],
        'model_calls':0,
        'authority_mutation':'NONE'
    },sort_keys=True))


if __name__=='__main__':main()

# verify-only trigger: controller high-finding repair 3d7928b
