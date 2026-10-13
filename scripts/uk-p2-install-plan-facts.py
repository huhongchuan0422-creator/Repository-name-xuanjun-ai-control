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
NGINX_CONF='/etc/nginx/nginx.conf'
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

def socket_identity(path):
    real=os.path.realpath(path)
    if path!='/var/run/docker.sock' or real!='/run/docker.sock':
        raise ValueError('UNEXPECTED_DOCKER_SOCKET_PATH:'+path+'->'+real)
    info=os.stat(real)
    if not stat.S_ISSOCK(info.st_mode):
        raise ValueError('NOT_SOCKET:'+real)
    return {'path':path,'realpath':real,'kind':'socket','owner_uid':info.st_uid,
            'owner_gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode)}

def maybe_identity(path):
    try:return file_identity(path)
    except (OSError,ValueError) as error:
        return {'path':path,'status':'UNAVAILABLE','reason':type(error).__name__}

def path_fact(path):
    try:
        info=os.stat(path)
        return {'path':path,'status':'PRESENT','kind':'dir' if stat.S_ISDIR(info.st_mode) else 'file',
                'owner_uid':info.st_uid,'owner_gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode)}
    except OSError as error:
        return {'path':path,'status':'UNAVAILABLE','reason':type(error).__name__}


def unit_fact(unit):
    props=('Id','LoadState','ActiveState','SubState','MainPID','ControlGroup',
           'UnitFileState','FragmentPath','EnvironmentFiles','ProtectHome',
           'ReadOnlyPaths','BindReadOnlyPaths','BindPaths','User','Group')
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
    root='/etc/nginx'
    paths=[]
    scanned=0
    for base,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if not os.path.islink(os.path.join(base,d))]
        for name in sorted(files):
            if scanned>=256:
                raise ValueError('NGINX_CONFIG_SCAN_LIMIT')
            candidate=os.path.join(base,name)
            real=os.path.realpath(candidate)
            if not real.startswith(root+'/') and real!=NGINX_CONF:
                continue
            try:
                raw,info=file_identity(real,1048576),os.stat(real)
                text=open(real,'r').read().splitlines()
            except (OSError,ValueError,UnicodeError):
                continue
            scanned+=1
            for line in text:
                m=TLS_RE.match(line)
                if not m:
                    continue
                ref=m.group(2).strip()
                if not os.path.isabs(ref):
                    return {'status':'UNAVAILABLE','config':NGINX_CONF,
                            'reason':'RELATIVE_TLS_REFERENCE','path':ref}
                ref=os.path.realpath(ref)
                if ref not in paths:
                    paths.append(ref)
    refs=[]
    for ref in paths:
        try:
            refs.append(file_identity(ref,16*1024*1024))
        except (OSError,ValueError) as error:
            return {'status':'UNAVAILABLE','config':NGINX_CONF,
                    'reason':'TLS_REFERENCE_'+type(error).__name__,'path':ref}
    if not refs:
        return {'status':'UNAVAILABLE','config':NGINX_CONF,
                'reason':'NO_TLS_REFERENCE_FOUND','scanned_files':scanned}
    config=file_identity(NGINX_CONF,1048576) if os.path.exists(NGINX_CONF) else {'path':NGINX_CONF,'status':'UNAVAILABLE'}
    return {'status':'PRESENT','config':config,'references':refs,'scanned_files':scanned}

def gateway_auth_env_fact():
    out=subprocess.check_output(['/usr/bin/systemctl','show','xuanjun-uk-openclaw.service',
        '--property=MainPID','--value'],universal_newlines=True,timeout=10).strip()
    pid=int(out)
    raw=open('/proc/%d/environ'%pid,'rb').read(1024*1024)
    names=set(item.split(b'=',1)[0].decode('ascii','ignore') for item in raw.split(b'\0') if b'=' in item)
    return {'token_present':'OPENCLAW_GATEWAY_TOKEN' in names,
            'password_present':'OPENCLAW_GATEWAY_PASSWORD' in names,
            'url_present':'OPENCLAW_GATEWAY_URL' in names}

def proposed_identity_ids():
    free=[]
    for value in range(21000,22000):
        try:pwd.getpwuid(value);uid_free=False
        except KeyError:uid_free=True
        try:grp.getgrgid(value);gid_free=False
        except KeyError:gid_free=True
        if uid_free and gid_free:
            free.append(value)
        if len(free)==4:break
    if len(free)!=4:raise ValueError('NO_REVIEWABLE_ID_RANGE')
    return {'xuanjun-dispatcher':free[0],'xuanjun-callback':free[1],
            'xj_codex_worker':free[2],'xuanjun-control-db':free[3]}

def find_named_files(root,name,limit=100000):
    found=[];scanned=0
    for base,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=sorted(d for d in dirs if not os.path.islink(os.path.join(base,d)))
        for item in sorted(files):
            scanned+=1
            if scanned>limit:raise ValueError('BINARY_SEARCH_LIMIT')
            if item!=name:continue
            path=os.path.join(base,item)
            try:found.append(file_identity(path))
            except (OSError,ValueError):continue
            if len(found)>=8:return found
    return found

def activation_fact():
    if not os.path.exists(ACTIVATION):
        return {'status':'ABSENT','path':ACTIVATION}
    ident=file_identity(ACTIVATION,1048576)
    value=json.load(open(ACTIVATION,'r'))
    allowed=('state','release_sha256','config_sha256','binary_sha256','ledger_uuid',
             'generation','epoch','instance','db_path','ledger_socket')
    return {'status':'PRESENT','identity':ident,
            'value':dict((k,value.get(k)) for k in allowed)}

def codex_version_facts():
    # Offline --version only, exact previously measured bytes, never root execution.
    pinned=[{"path":"/home/xuanjun_dev/.openclaw/npm/projects/openclaw-codex-8902d781d4/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex", "sha256":"167c0148a849d2444f1b5a7fb5f8bb2de1de5ae13a2a504b833fc765980f5cd9"},{"path":"/home/xuanjun_dev/.openclaw/npm/projects/openclaw-codex-8902d781d4__openclaw-generation__g-d803e8e002e42fe5/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex", "sha256":"12eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad"}]
    results=[]
    for binding in pinned:
        before=file_identity(binding['path'])
        if before['sha256']!=binding['sha256'] or before['owner_uid']!=1002:
            raise ValueError('CODEX_VERSION_SOURCE_DRIFT')
        process=subprocess.run(['/usr/sbin/runuser','--user','xuanjun_dev','--',binding['path'],'--version'],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,check=False,
            env={'HOME':'/nonexistent','PATH':'/usr/bin:/bin','LANG':'C','NO_COLOR':'1'})
        after=file_identity(binding['path'])
        if before!=after:raise ValueError('CODEX_VERSION_SOURCE_CHANGED')
        text=process.stdout.decode('ascii').strip()
        if process.returncode!=0 or re.fullmatch(r'codex-cli [0-9]+[.][0-9]+[.][0-9]+',text) is None:
            raise ValueError('CODEX_VERSION_INVALID')
        results.append({'identity':after,'version':text,'model_calls':0,'operation':'offline_version_only'})
    return results

def protected_input_fact(path):
    # Fixed reviewed paths only; never expose contents or secret digests.
    try:
        info=os.lstat(path)
    except OSError:
        return {'path':path,'state':'HOLD_MISSING_PROTECTED_INPUT'}
    if (not stat.S_ISREG(info.st_mode) or os.path.realpath(path)!=path
            or info.st_uid!=0 or info.st_gid!=0
            or stat.S_IMODE(info.st_mode)!=0o600
            or not 0<info.st_size<=65536):
        return {'path':path,'state':'HOLD_UNSAFE_PROTECTED_INPUT'}
    parent=os.lstat(os.path.dirname(path))
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=0
            or parent.st_mode&0o022):
        return {'path':path,'state':'HOLD_UNSAFE_INPUT_PARENT'}
    return {'path':path,'state':'METADATA_READY_CONTENT_NOT_VERIFIED'}


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
      'docker_socket':socket_identity('/var/run/docker.sock'),
      'python':file_identity('/usr/libexec/platform-python3.6',64*1024*1024),
      'openclaw':file_identity('/home/xuanjun_dev/.openclaw/bin/openclaw',16*1024*1024),
      'gateway_auth_env':gateway_auth_env_fact(),
      'proposed_identity_ids':proposed_identity_ids(),
      'gh_binary':maybe_identity('/usr/bin/gh'),
      'gh_binary_candidates':[maybe_identity(os.path.realpath(p)) for p in (
          '/usr/bin/gh','/usr/local/bin/gh','/opt/xuanjun-runtime/gh/gh',
          '/home/xuanjun_dev/.local/bin/gh')],
      # File metadata only: never print tokens, HMAC keys or identities.
      'required_private_input_paths':[protected_input_fact(p) for p in (
          '/etc/xuanjun-development/github-intake-token',
          '/etc/xuanjun-owner-callback/owner-dashboard-token',
          '/etc/xuanjun-owner-callback/owner-callback-auth',
          '/etc/xuanjun-owner-callback/owner-callback-hmac',
          '/etc/xuanjun-owner-callback/owner-user-id',
          '/etc/xuanjun-owner-callback/owner-chat-id')],
      'https_runtime_paths':[path_fact(p) for p in (
          '/usr/sbin/nginx','/etc/nginx','/usr/bin/caddy',
          '/etc/caddy','/etc/letsencrypt','/etc/ssl/private')],
      'codex_version_facts':codex_version_facts(),
      'codex_binary_candidates':find_named_files('/home/xuanjun_dev/.openclaw','codex'),
      'plan_parents':[path_fact(x) for x in (
          '/etc','/opt','/var/lib','/var/lib/xuanjun-development',
          '/opt/xuanjun-runtime','/home/xuanjun_dev/uk-stage1-minimal')],
      'openclaw_paths':[path_fact(x) for x in (
          '/home/xuanjun_dev','/home/xuanjun_dev/.openclaw',
          '/home/xuanjun_dev/.openclaw/bin',
          '/home/xuanjun_dev/.openclaw/tools',
          '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0',
          '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/bin/node',
          '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw')],
    }
    print(json.dumps(result,sort_keys=True,separators=(',',':')))

if __name__=='__main__':main()
