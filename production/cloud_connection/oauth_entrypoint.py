"""Protected host configuration -> actual loopback WSGI listener.

Never called by the current worker or tunnel launcher. New configuration must
be reviewed/enrolled explicitly. No bootstrap, credential creation or dispatch.
"""
import argparse
import base64
import hashlib
import json
import logging
import os
import sqlite3
import stat

from .queue import Hold, unique

HOSTS={'authority':'iZvt5t8tlrm8oiZ','resource':'iZd7oeikknn1z21sq6ji6zZ'}


def private_bytes(path, limit, contents=True):
    if type(path) is not str or not path.startswith('/') or os.path.normpath(path)!=path:
        raise Hold('OAUTH_CONFIG_PATH')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        parts=path.split('/')[1:]
        for part in parts[:-1]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=nxt
            s=os.fstat(fd)
            if s.st_uid not in (0,os.geteuid()) or s.st_mode & 0o022:
                raise Hold('OAUTH_CONFIG_PARENT')
        file_fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            before=os.fstat(file_fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid not in (0,os.geteuid())
                    or stat.S_IMODE(before.st_mode) not in (0o400,0o600)
                    or before.st_nlink!=1 or before.st_size>limit):raise Hold('OAUTH_CONFIG_METADATA')
            raw=os.read(file_fd,limit+1) if contents else None
            after=os.fstat(file_fd)
            a=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_nlink)
            if a(before)!=a(after) or (contents and (len(raw)!=before.st_size or len(raw)>limit)):
                raise Hold('OAUTH_CONFIG_CHANGED')
            live=os.stat(parts[-1],dir_fd=fd,follow_symlinks=False)
            if a(live)!=a(before):raise Hold('OAUTH_CONFIG_REPLACED')
            return raw if contents else a(before)
        finally:os.close(file_fd)
    finally:os.close(fd)


def load_app(kind,path,expected_sha):
    from .oauth_authority import create_app
    from .oauth_http import create_resource_app
    from .oauth_resource import Introspection
    from .private_mcp import PrivateMcp
    from .private_transfer import Catalog
    if kind not in HOSTS or os.uname().nodename!=HOSTS[kind]:raise Hold('OAUTH_HOST')
    raw=private_bytes(path,262144)
    if hashlib.sha256(raw).hexdigest()!=expected_sha:raise Hold('OAUTH_CONFIG_SHA')
    config=json.loads(raw.decode(),object_pairs_hook=unique)
    if config.get('enabled') is not True:raise Hold('OAUTH_NOT_ENROLLED')
    if type(config.get('schema')) is not int or config['schema']!=1 or config.get('hostname')!=HOSTS[kind]:
        raise Hold('OAUTH_CONFIG_BINDING')
    if kind=='authority':
        import pwd
        if os.geteuid()==0 or pwd.getpwuid(os.geteuid()).pw_name!='xuanjun_oauth':
            raise Hold('OAUTH_DEDICATED_SERVICE_IDENTITY')
        if set(config)!={'schema','enabled','hostname','settings','database','session_secret_ref','github_secret_ref'}:
            raise Hold('OAUTH_CONFIG_FIELDS')
        database=config['database']
        if database!='/var/lib/xuanjun-cloud-oauth/authority.sqlite':raise Hold('OAUTH_AUTHORITY_STATE')
        def connect():
            # Never create a missing database or silently replace unknown state.
            # Parent is dedicated-private and pre-enrolled, no remote path input.
            parent=os.stat(os.path.dirname(database),follow_symlinks=False)
            if not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=os.geteuid() or stat.S_IMODE(parent.st_mode)!=0o700:
                raise Hold('OAUTH_STATE_DIRECTORY')
            before=private_bytes(database,64*1024*1024,contents=False)
            db=sqlite3.connect('file:'+database+'?mode=rw',uri=True,timeout=0,isolation_level=None)
            after=private_bytes(database,64*1024*1024,contents=False)
            if before[:2]!=after[:2]:
                db.close();raise Hold('OAUTH_STATE_REPLACED')
            return db
        secret=base64.b64decode(private_bytes(config['session_secret_ref'],4096).strip(),validate=True)
        github_secret=private_bytes(config['github_secret_ref'],4096).decode().strip()
        if not github_secret:raise Hold('OAUTH_GITHUB_SECRET')
        return create_app(config['settings'],connect,secret,github_secret,True)
    if os.geteuid()!=0:raise Hold('OAUTH_EXISTING_PRIVATE_READER_ROOT')
    if set(config)!={'schema','enabled','hostname','settings','client_secret_ref','catalogs'}:
        raise Hold('OAUTH_CONFIG_FIELDS')
    settings=config['settings']
    if set(settings)!={'issuer','endpoint','client_id','audience','subjects'}:raise Hold('OAUTH_RESOURCE_SETTINGS')
    auth=Introspection(secret_provider=lambda:private_bytes(config['client_secret_ref'],4096).decode().strip(),**settings)
    catalogs={}
    if type(config['catalogs']) is not list or len(config['catalogs'])>32:raise Hold('OAUTH_CATALOG_COUNT')
    for item in config['catalogs']:
        if set(item)!={'manifest_ref','manifest_sha256','policy','roots'}:raise Hold('OAUTH_CATALOG_FIELDS')
        catalog=Catalog(private_bytes(item['manifest_ref'],131072),item['manifest_sha256'],item['policy'])
        if catalog.sha in catalogs:raise Hold('OAUTH_DUPLICATE_CATALOG')
        roots=item['roots']
        if type(roots) is not dict or set(roots)!=set(item['policy']['root_refs']):raise Hold('OAUTH_ROOT_BINDING')
        for root in roots.values():
            if type(root) is not list or len(root)!=2 or type(root[0]) is not str or type(root[1]) is not int:
                raise Hold('OAUTH_ROOT_BINDING')
        catalogs[catalog.sha]=(catalog,roots)
    return create_resource_app(auth,lambda:PrivateMcp('/var/lib/xuanjun-cloud-connection'),catalogs,settings['audience'],True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--kind',required=True,choices=sorted(HOSTS))
    parser.add_argument('--config',required=True)
    parser.add_argument('--sha256',required=True)
    args=parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    for name in ('authlib','urllib3','requests'):logging.getLogger(name).setLevel(logging.WARNING)
    app=load_app(args.kind,args.config,args.sha256)
    from waitress import serve
    serve(app,host='127.0.0.1',port=18770 if args.kind=='authority' else 18769,
          url_scheme='https' if args.kind=='authority' else 'http',threads=4,
          connection_limit=64,channel_timeout=10,cleanup_interval=1,
          max_request_body_size=16384,max_request_header_size=16384,
          expose_tracebacks=False,clear_untrusted_proxy_headers=True)


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('HOLD_OAUTH_STARTUP') from None
