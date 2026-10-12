"""P2 UK verify-only host identity and compatibility probe.

Zero model calls. No config/lease/database/container mutation. Python 3.6.8.
"""
from __future__ import print_function

import hashlib
import json
import os
import pwd
import re
import socket
import stat
import subprocess
import sys

HOST='iZd7oeikknn1z21sq6ji6zZ'
USER='xuanjun_dev'
OPENCLAW_ROOT='/home/xuanjun_dev/.openclaw'
NODE='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/bin/node'
DIST='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist'


def read(path,maximum=64*1024*1024):
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>maximum:
            raise ValueError('UNSAFE_FILE')
        raw=b''
        while len(raw)<=maximum:
            chunk=os.read(fd,min(65536,maximum+1-len(raw)))
            if not chunk:break
            raw+=chunk
        if len(raw)>maximum:raise ValueError('FILE_LIMIT')
        return raw,info
    finally:os.close(fd)


def digest(path):
    raw,info=read(path)
    return {'path':path,'sha256':hashlib.sha256(raw).hexdigest(),
            'uid':info.st_uid,'mode':oct(stat.S_IMODE(info.st_mode))}


def proc_status(pid):
    raw,_=read('/proc/%d/status'%pid,maximum=65536)
    out={}
    for line in raw.decode('ascii','strict').splitlines():
        if ':' in line:
            k,v=line.split(':',1);out[k]=v.strip()
    return out


def main():
    uid=pwd.getpwnam(USER).pw_uid
    if socket.gethostname().split('.')[0]!=HOST or os.geteuid()!=uid:
        raise SystemExit('HOLD_FIXED_UK_IDENTITY')
    if sys.version_info[:3]!=(3,6,8):
        raise SystemExit('HOLD_PYTHON_VERSION_'+'.'.join(str(v) for v in sys.version_info[:3]))

    candidates=[]
    for name in os.listdir('/proc'):
        if not name.isdigit():continue
        pid=int(name)
        try:
            st=proc_status(pid)
            uids=st.get('Uid','').split()
            if len(uids)!=4 or any(int(v)!=uid for v in uids):continue
            raw,_=read('/proc/%d/cmdline'%pid,maximum=131072)
            args=[v.decode('utf-8','replace') for v in raw.rstrip(b'\0').split(b'\0') if v]
            joined=' '.join(args)
            if 'openclaw' in joined.lower() and 'gateway' in joined.lower():
                exe=os.path.realpath('/proc/%d/exe'%pid)
                cgroup,_=read('/proc/%d/cgroup'%pid,maximum=131072)
                candidates.append({'pid':pid,'ppid':int(st.get('PPid','0')),
                    'exe':exe,'exe_sha256':digest(exe)['sha256'],
                    'cgroup':cgroup.decode('utf-8','strict').splitlines(),
                    'cmdline_sha256':hashlib.sha256(raw).hexdigest()})
        except (IOError,OSError,ValueError,UnicodeError):
            continue
    if len(candidates)!=1:
        raise SystemExit('HOLD_GATEWAY_PROCESS_COUNT_%d'%len(candidates))

    sources=[]
    for path in [
        NODE,
        OPENCLAW_ROOT+'/bin/openclaw',
        OPENCLAW_ROOT+'/tools/node-v24.21.0/lib/node_modules/openclaw/package.json',
        DIST+'/context-DyPstb2Q.mjs',
        DIST+'/loader-runtime-load-DpgEqnzx.mjs',
        DIST+'/store-BVWJOVBa.mjs',
        '/usr/bin/python3',
        '/usr/bin/docker',
    ]:
        sources.append(digest(path))

    plugin_runtime=[]
    for name in sorted(os.listdir(DIST)):
        if ('plugin' in name.lower() or 'sandbox' in name.lower()) and name.endswith('.mjs'):
            path=os.path.join(DIST,name)
            try:
                item=digest(path)
            except (IOError,OSError,ValueError):
                continue
            plugin_runtime.append(item)
            if len(plugin_runtime)>=64:break

    docker=subprocess.check_output(
        ['/usr/bin/docker','--host=unix:///var/run/docker.sock','version','--format','{{.Server.Version}}'],
        env={'HOME':'/home/xuanjun_dev','PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},
        universal_newlines=True,timeout=15).strip()
    if not re.fullmatch(r'[0-9][A-Za-z0-9._+-]{0,63}',docker):
        raise SystemExit('HOLD_DOCKER_VERSION')

    print(json.dumps({
        'state':'P2_UK_VERIFY_ONLY_HOST_FACTS',
        'model_calls':0,'authority_mutation':'NONE','container_mutation':'NONE',
        'python_version':list(sys.version_info[:3]),
        'gateway':candidates[0],
        'sources':sources,
        'plugin_runtime_files':plugin_runtime,
        'docker_server_version':docker,
    },sort_keys=True))


if __name__=='__main__':main()
