#!/usr/bin/env python3
"""P2 UK read-only install-plan facts collector.

Python 3.6.8 compatible. Reads fixed operational metadata and file identities
only. It never emits credential/certificate contents and performs no mutation.
"""
from __future__ import print_function

import grp
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
LEGACY_DB='/home/xuanjun_dev/uk-stage1-minimal/state.sqlite'
ACTIVATION='/var/lib/xuanjun-development/activation/active.json'
NGINX_CONF='/etc/nginx/conf.d/xuanjun-owner-workbench.conf'
AUTH_DB='/home/xuanjun_dev/.openclaw/agents/developer/agent/openclaw-agent.sqlite'
UNITS=('xuanjun-uk-stage1-minimal.service','xuanjun-uk-openclaw.service')
IDENTITIES=('xuanjun-dispatcher','xuanjun-callback','xj_codex_worker')
GROUPS=('xuanjun-dispatcher','xuanjun-callback','xj_codex_worker','xuanjun-control-db')
TLS_RE=re.compile(r'^\s*ssl_certificate(_key)?\s+([^;]+);\s*$')

def file_identity(path,limit=536870912):
    real=os.path.realpath(path)
    if real!=path:
        raise ValueError('NON_CANONICAL_FILE:'+path)
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>limit:
            raise ValueError('UNSAFE_FILE:'+path)
        h=hashlib.sha256()
        total=0
        while True:
            raw=os.read(fd,65536)
            if not raw:break
            total+=len(raw)
            if total>limit:raise ValueError('FILE_LIMIT:'+path)
            h.update(raw)
        return {'path':path,'sha256':h.hexdigest(),'owner_uid':info.st_uid,
                'owner_gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode),
                'size':info.st_size}
    finally:
        os.close(fd)

def maybe_identity(path):
    try:return file_identity(path)
    except (OSError,ValueError) as error:
        return {'path':path,'status':'UNAVAILABLE','reason':type(error).__name__}

def unit_fact(unit):
    props=('Id','LoadState','ActiveState','SubState','MainPID','ControlGroup',
           'UnitFileState','FragmentPath')
    out=subprocess.check_output(['/usr/bin/systemctl','show',unit,
        '--property='+','.join(props)],universal_newlines=True,timeout=10)
    value={}
    for row in out.splitlines():
        key,sep,item=row.partition('=')
        if sep:value[key]=item
    fragment='/etc/systemd/system/'+unit
    return {'unit':unit,'observed':value,'binding':{
        'fragment_path':fragment,
        'sha256':file_identity(fragment,1048576)['sha256'],
        'cgroup':'/system.slice/'+unit}}

def identity_fact(name):
    try:
        u=pwd.getpwnam(name)
        return {'status':'PRESENT','uid':u.pw_uid,'gid':u.pw_gid,
                'home':u.pw_dir,'shell':u.pw_shell,
                'supplementary_gids':sorted(os.getgrouplist(name,u.pw_gid))}
    except KeyError:
        return {'status':'ABSENT'}

def group_fact(name):
    try:
        g=grp.getgrnam(name)
        return {'status':'PRESENT','gid':g.gr_gid,'members':sorted(g.gr_mem)}
    except KeyError:
        return {'status':'ABSENT'}

def tls_refs():
    if not os.path.exists(NGINX_CONF):
        return {'status':'UNAVAILABLE','config':NGINX_CONF}
    refs=[]
    raw=open(NGINX_CONF,'r').read().splitlines()
    for line in raw:
        m=TLS_RE.match(line)
        if m:
            path=m.group(2).strip()
            refs.append(file_identity(path,16*1024*1024))
    if len(refs)!=2 or len(set(x['path'] for x in refs))!=2:
        return {'status':'UNAVAILABLE','config':NGINX_CONF,'reference_count':len(refs)}
    return {'status':'PRESENT','config':file_identity(NGINX_CONF,1048576),
            'references':refs}

def activation_fact():
    if not os.path.exists(ACTIVATION):
        return {'status':'ABSENT','path':ACTIVATION}
    ident=file_identity(ACTIVATION,1048576)
    value=json.load(open(ACTIVATION,'r'))
    allowed=('state','release_sha256','config_sha256','binary_sha256','ledger_uuid',
             'generation','epoch','instance','db_path','ledger_socket')
    return {'status':'PRESENT','identity':ident,
            'value':dict((k,value.get(k)) for k in allowed)}

def main():
    if socket.gethostname().split('.')[0]!=HOST or os.geteuid()!=0:
        raise SystemExit('HOLD_FIXED_UK_ROOT_IDENTITY')
    if sys.version_info[:3]!=(3,6,8):
        raise SystemExit('HOLD_PYTHON_VERSION')
    result={
      'schema':1,
      'state':'P2_UK_INSTALL_PLAN_FACTS',
      'python_version':list(sys.version_info[:3]),
      'model_calls':0,
      'effects':0,
      'legacy_database':maybe_identity(LEGACY_DB),
      'activation':activation_fact(),
      'units':[unit_fact(x) for x in UNITS],
      'users':dict((x,identity_fact(x)) for x in IDENTITIES),
      'groups':dict((x,group_fact(x)) for x in GROUPS),
      'oauth_reference':maybe_identity(AUTH_DB),
      'tls':tls_refs(),
      'docker_socket':maybe_identity('/var/run/docker.sock'),
      'python':file_identity('/usr/libexec/platform-python3.6',64*1024*1024),
      'openclaw':file_identity('/home/xuanjun_dev/.openclaw/bin/openclaw',16*1024*1024),
    }
    print(json.dumps(result,sort_keys=True,separators=(',',':')))

if __name__=='__main__':main()
