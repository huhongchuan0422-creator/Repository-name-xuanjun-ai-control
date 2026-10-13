#!/usr/bin/env python3
"""Prepare private P2 inputs in protected staging; never install or expose them."""
import json
import os
import re
import secrets
import socket
import stat

HOST='iZd7oeikknn1z21sq6ji6zZ'
STAGING='/var/lib/xuanjun-development/install-staging/private-inputs'
NAMES=('owner-dashboard-token','owner-callback-auth','owner-callback-hmac')

def prepare(directory):
    parent=os.lstat(directory)
    if (os.path.realpath(directory)!=directory or not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid!=os.geteuid() or parent.st_gid!=os.getegid()
            or stat.S_IMODE(parent.st_mode)!=0o700):
        raise ValueError('PROTECTED_STAGING_DIRECTORY_REQUIRED')
    results=[]
    for name in NAMES:
        path=os.path.join(directory,name)
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            try:
                info=os.fstat(fd);value=os.read(fd,129)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid()
                        or info.st_gid!=os.getegid() or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o600
                        or re.fullmatch(br'[A-Za-z0-9_-]{43,86}\n',value) is None):
                    raise ValueError('HOLD_EXISTING_PRIVATE_INPUT_UNSAFE')
            finally:os.close(fd)
            status='EXISTING_VALIDATED_NOT_REPLACED'
        else:
            os.fchmod(fd,0o600)
            with os.fdopen(fd,'wb') as stream:
                stream.write(secrets.token_urlsafe(48).encode('ascii')+b'\n')
                stream.flush();os.fsync(stream.fileno())
            status='GENERATED_IN_PRIVATE_STAGING'
        results.append({'name':name,'state':status})
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {'state':'PRIVATE_STAGING_ONLY','inputs':results,
            'github_credential':'REQUIRES_EXISTING_PROTECTED_AUTHORIZATION',
            'owner_identity':'REQUIRES_VERIFIED_OWNER_USER_AND_CHAT_IDS',
            'tls':'REQUIRES_REAL_CERTIFICATE_BINDING',
            'production_write':False,'install_performed':False,'model_calls':0}

if __name__=='__main__':
    if os.geteuid()!=0 or socket.gethostname().split('.')[0]!=HOST:
        raise SystemExit('HOLD_FIXED_UK_ROOT_PREPARATION_REQUIRED')
    print(json.dumps(prepare(STAGING),sort_keys=True))
