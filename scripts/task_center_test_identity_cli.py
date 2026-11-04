"""Create an owner-only TEST_ONLY identity fixture interactively.

This is not a production account system.  A deployment must replace the
verifier with the existing unified identity provider.
"""
from __future__ import print_function

import argparse
import getpass
import json
import os
import tempfile

from task_center_session_auth import password_hash


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--tenant',required=True)
    parser.add_argument('--username',required=True)
    parser.add_argument('--principal',required=True)
    parser.add_argument('--roles',default='TASK_CENTER_ADMIN,TASK_EXECUTOR')
    parser.add_argument('--append',action='store_true',
      help='add a distinct TEST_ONLY subject to an existing owner-only file')
    args=parser.parse_args(argv)
    target=os.path.realpath(args.output)
    body={'users':{}}
    if os.path.exists(target):
        if not args.append:raise ValueError('REFUSE_OVERWRITE_IDENTITY_FILE')
        info=os.stat(target)
        if (not os.path.isfile(target) or info.st_uid!=os.geteuid() or
                info.st_mode & 0o077):
            raise ValueError('INSECURE_IDENTITY_FILE')
        with open(target) as stream:body=json.load(stream)
        if not isinstance(body.get('users'),dict):
            raise ValueError('INVALID_IDENTITY_FILE')
    first=getpass.getpass('TEST_ONLY password: ')
    second=getpass.getpass('Repeat password: ')
    if first!=second:raise ValueError('PASSWORD_CONFIRMATION_MISMATCH')
    roles=sorted(set(x.strip() for x in args.roles.split(',') if x.strip()))
    if not roles:raise ValueError('ROLE_REQUIRED')
    if args.username in body['users']:raise ValueError('IDENTITY_ALREADY_EXISTS')
    body['users'][args.username]={'password_hash':password_hash(first),
      'tenant_id':args.tenant,'principal_id':args.principal,'roles':roles,
      'enabled':True}
    parent=os.path.dirname(target);os.makedirs(parent,exist_ok=True)
    descriptor,temp=tempfile.mkstemp(prefix='.identity-',dir=parent)
    try:
        os.fchmod(descriptor,0o600)
        with os.fdopen(descriptor,'w') as stream:
            json.dump(body,stream,sort_keys=True,separators=(',',':'))
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temp,target)
    except Exception:
        try:os.unlink(temp)
        except OSError:pass
        raise
    print(json.dumps({'state':'CREATED','path':target,'mode':'0600',
      'identity_kind':'TEST_ONLY_FIXTURE'},sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
