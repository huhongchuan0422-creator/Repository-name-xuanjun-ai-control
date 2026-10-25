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
    args=parser.parse_args(argv)
    target=os.path.realpath(args.output)
    if os.path.exists(target):raise ValueError('REFUSE_OVERWRITE_IDENTITY_FILE')
    first=getpass.getpass('TEST_ONLY password: ')
    second=getpass.getpass('Repeat password: ')
    if first!=second:raise ValueError('PASSWORD_CONFIRMATION_MISMATCH')
    roles=sorted(set(x.strip() for x in args.roles.split(',') if x.strip()))
    if not roles:raise ValueError('ROLE_REQUIRED')
    body={'users':{args.username:{'password_hash':password_hash(first),
      'tenant_id':args.tenant,'principal_id':args.principal,'roles':roles,
      'enabled':True}}}
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
