#!/usr/bin/env python3
"""Root-owned, no-argument read-only contract export. Never exports credentials."""
import ast
import pwd
import grp
import hashlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import tempfile

ROOT = '/home/xuanjun_dev'
BASE = ROOT + '/uk-stage1-minimal'
DEST = '/var/lib/xuanjun-contract-export'
SAFE_STRINGS = {'request_id','task_id','fence','update_id','decision','owner_user_id','owner_chat_id',
                'owner_id','owner_chat','APPROVE','REJECT','PENDING','RUNNING','WAITING_HUMAN',
                'DONE','FAILED','PAUSED_RESOURCE','accepted','Authorization','X-Xuanjun-Signature',
                'X-Signature','/owner/decision','XJ_UK_DB','XJ_UK_AUTH','XJ_UK_SIGN_HEX',
                'XJ_OWNER_USER_ID','XJ_UK_PORT','127.0.0.1'}


def contract(path):
    # Every parent is checked. A fixed file cannot be redirected via a symlink.
    allowed_owners={0,pwd.getpwnam('xuanjun_dev').pw_uid}
    current='/'
    for part in path.strip('/').split('/'):
        current=os.path.join(current,part)
        info=os.lstat(current)
        if os.path.islink(current) or info.st_uid not in allowed_owners:
            raise ValueError('UNTRUSTED_SOURCE_PATH')
    with open(path,'rb') as stream:raw=stream.read(500001)
    if len(raw)>500000:raise ValueError('SOURCE_TOO_LARGE')
    tree=ast.parse(raw.decode('utf-8'))
    class Scrub(ast.NodeTransformer):
        def visit_Str(self,node):
            return ast.copy_location(ast.Str(s=node.s if node.s in SAFE_STRINGS else '[STRING_REDACTED]'),node)
        def visit_Bytes(self,node):
            return ast.copy_location(ast.Bytes(s=b'[BYTES_REDACTED]'),node)
        def visit_Constant(self,node):
            if isinstance(node.value,str):
                return ast.copy_location(ast.Constant(value=node.value if node.value in SAFE_STRINGS else '[STRING_REDACTED]'),node)
            if isinstance(node.value,bytes):
                return ast.copy_location(ast.Constant(value=b'[BYTES_REDACTED]'),node)
            # Numbers may also be credentials; only language constants are retained.
            if isinstance(node.value,(int,float,complex)) and not isinstance(node.value,bool):
                return ast.copy_location(ast.Constant(value=0),node)
            return node
        def visit_Num(self,node):
            return ast.copy_location(ast.Num(n=0),node)
    clean=Scrub().visit(tree)
    return {'path':path,'sha256':hashlib.sha256(raw).hexdigest(),
            'contract_ast':ast.dump(clean),'source_exported':False}


TOKYO_PROGRAM = """import hashlib,json,socket,ast,os,pwd
assert socket.gethostname().split('.')[0]=='iZ6wee8q9z4t03hvqumwfhZ'
paths=['/opt/trading-system/scripts/secure_secrets_portal_server.py','/opt/trading-system/ai_service/telegram_customer_service_canary.py']
result=[]
for path in paths:
 current='/'
 for part in path.strip('/').split('/'):
  current=os.path.join(current,part)
  if os.path.islink(current):raise ValueError('SOURCE_SYMLINK')
 b=open(path,'rb').read(500001)
 if len(b)>500000:raise ValueError('SOURCE_TOO_LARGE')
 tree=ast.parse(b.decode('utf-8'))
 class Scrub(ast.NodeTransformer):
  def visit_Str(self,n):return ast.copy_location(ast.Str(s=n.s if n.s in SAFE_STRINGS else '[STRING_REDACTED]'),n)
  def visit_Bytes(self,n):return ast.copy_location(ast.Bytes(s=b'[BYTES_REDACTED]'),n)
  def visit_Num(self,n):return ast.copy_location(ast.Num(n=0),n)
  def visit_Constant(self,n):
   if isinstance(n.value,str):return ast.copy_location(ast.Constant(value=n.value if n.value in SAFE_STRINGS else '[STRING_REDACTED]'),n)
   if isinstance(n.value,bytes):return ast.copy_location(ast.Constant(value=b'[BYTES_REDACTED]'),n)
   if isinstance(n.value,(int,float,complex)) and not isinstance(n.value,bool):return ast.copy_location(ast.Constant(value=0),n)
   return n
 result.append({'path':path,'sha256':hashlib.sha256(b).hexdigest(),'contract_ast':ast.dump(Scrub().visit(tree)),'source_exported':False})
print(json.dumps(result))
"""


def atomic(name, data):
    group = grp.getgrnam('githubrunner').gr_gid
    encoded = json.dumps(data, ensure_ascii=True).encode('utf-8')
    fd, tmp = tempfile.mkstemp(dir=DEST, prefix='.export-')
    try:
        os.fchmod(fd,0o640)
        os.fchown(fd,0,group)
        with os.fdopen(fd,'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp,os.path.join(DEST,name))
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def main():
    import sys
    if os.geteuid()!=0 or len(sys.argv)!=1 or socket.gethostname().split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ':
        raise SystemExit('STOP_FIXED_UK_EXPORT_SCOPE')
    group=grp.getgrnam('githubrunner').gr_gid
    os.makedirs(DEST,mode=0o750,exist_ok=True)
    if os.path.islink(DEST):raise SystemExit('STOP_EXPORT_SYMLINK')
    os.chown(DEST,0,group);os.chmod(DEST,0o750)
    files=[contract(BASE+'/coordinator.py')]
    for name in ['serve_uk_callback.py','uk_owner_callback.py']:
        path=BASE+'/owner-callback/'+name
        if os.path.exists(path):files.append(contract(path))
    db=sqlite3.connect('file:'+BASE+'/state.sqlite?mode=ro',uri=True)
    try:
        schema={}
        for table in ['tasks','approvals','events','owner_callback_requests','owner_callback_replays','owner_notification_outbox','worker_heartbeats','execution_specs']:
            rows=db.execute('PRAGMA table_info('+table+')').fetchall()
            if rows:
                schema[table]=[{'name':r[1],'type':r[2] if r[2].upper() in ('TEXT','INTEGER','REAL','BLOB','NUMERIC','') else 'UNKNOWN','notnull':bool(r[3]),'pk':bool(r[5])} for r in rows]
    finally:db.close()
    units={}
    for unit in ['xuanjun-uk-openclaw.service','xuanjun-uk-stage1-minimal.service','xuanjun-uk-owner-callback.service']:
        proc=subprocess.Popen(['/usr/bin/systemctl','is-active',unit],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,universal_newlines=True)
        output=proc.communicate(timeout=5)[0].strip()
        units[unit]=output if output in ('active','inactive','failed','activating','deactivating','unknown') else 'UNKNOWN'
    # Expose model routing only; never emit provider entries or auth profiles.
    model={}
    config=ROOT+'/.openclaw/openclaw.json'
    if os.path.isfile(config):
        with open(config) as stream:cfg=json.load(stream)
        configured=cfg.get('agents',{}).get('defaults',{}).get('model')
        if isinstance(configured,str):model={'primary':configured if configured=='openai/gpt-6.1-sol' else 'OTHER_OR_UNKNOWN'}
        elif isinstance(configured,dict):
            model={'primary':'openai/gpt-6.1-sol' if configured.get('primary')=='openai/gpt-6.1-sol' else 'OTHER_OR_UNKNOWN',
                   'fallback_count':len(configured['fallbacks']) if isinstance(configured.get('fallbacks'),list) else None}
    binaries=[p for p in [ROOT+'/.openclaw/bin/codex',ROOT+'/.local/bin/codex','/usr/local/bin/codex','/usr/bin/codex'] if os.path.isfile(p)]
    atomic('uk.json',{'files':files,'schema':schema,'units':units,'model':model,'codex_bins':binaries,
                      'codex_auth_present':os.path.isfile(ROOT+'/.codex/auth.json')})
    command=['/usr/sbin/runuser','-u','xuanjun_dev','--','/usr/bin/ssh','-i',ROOT+'/.ssh/xj_uk_tokyo_admin',
             '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',
             'admin@47.245.53.152','sudo -n /usr/bin/python3 -']
    try:
        output=subprocess.check_output(command,input=('SAFE_STRINGS='+repr(SAFE_STRINGS)+'\n'+TOKYO_PROGRAM).encode('utf-8'),
                                       stderr=subprocess.DEVNULL,timeout=40)
        result=json.loads(output.decode('utf-8'))
        atomic('tokyo.json',{'files':result,'ssh':'VERIFIED_EXISTING_IDENTITY'})
        print('TOKYO_CONTRACT_EXPORT=PASS')
    except (subprocess.SubprocessError,ValueError,OSError):
        atomic('tokyo.json',{'files':[],'ssh':'EXPORT_FAILED_NO_CREDENTIAL_DISCLOSURE'})
        print('TOKYO_CONTRACT_EXPORT=WAITING_HUMAN')
    print('UK_CONTRACT_EXPORT=PASS')


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('CONTRACT_EXPORT_FAILED_NO_RAW_DIAGNOSTICS')
