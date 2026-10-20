#!/usr/bin/env python3
"""Read-only combined Korea/Tokyo financial takeover inspection. No job activation."""
import os,sys,json,sqlite3,hashlib,subprocess,shutil,datetime,stat
from pathlib import Path
HOST='iZmj7a5kwr75qc1tul4kf9Z'
TOKYO='iZ6wee8q9z4t03hvqumwfhZ'
BASE=Path('/opt/xuanjun-migration-s07/releases/korea-model-handoff-v1')
TABLES=('invoices','invoice_lines','payment_records','payment_exceptions',
        'weekly_settlement_snapshots','finance_payment_reconciliations','credential_records')
REMOTE=r'''
import os,json,sqlite3,hashlib,subprocess,re
from pathlib import Path
if os.uname().nodename.split('.')[0]!='iZ6wee8q9z4t03hvqumwfhZ' or os.geteuid()!=0:
    raise SystemExit('HOLD_SOURCE_HOST_OR_PRIVILEGE')
root=Path('/opt/trading-system')
db=root/'database/data/trading.db'
if not db.is_file() or db.is_symlink():raise SystemExit('HOLD_SOURCE_DATABASE')
con=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=5)
report={'host':os.uname().nodename.split('.')[0],'ledger':{},'units':{},'env_files':{}}
try:
 con.execute('PRAGMA query_only=ON');con.execute('BEGIN')
 report['integrity']=con.execute('PRAGMA quick_check').fetchone()[0]
 tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 for name in ('invoices','invoice_lines','payment_records','payment_exceptions','weekly_settlement_snapshots','finance_payment_reconciliations','credential_records'):
  if name not in tables:report['ledger'][name]=None;continue
  rows=con.execute('SELECT * FROM "'+name+'"').fetchall()
  values=sorted(json.dumps(row,ensure_ascii=False,sort_keys=True,default=lambda v:v.hex() if isinstance(v,bytes) else str(v)) for row in rows)
  report['ledger'][name]={'count':len(rows),'sha256':hashlib.sha256('\n'.join(values).encode()).hexdigest()}
finally:con.close()
for name in ('finance-collection-sync','owner-commercial-ledger-sync','billing-operations-weekly-settlement','billing-operations-weekly-final-invoice'):
 for suffix in ('.timer','.service'):
  unit=name+suffix
  r=subprocess.run(['systemctl','show',unit,'--property=ActiveState,SubState,MainPID,FragmentPath,UnitFileState'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=10)
  info=dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)
  p=Path('/etc/systemd/system')/unit
  if p.is_file():
   lines=p.read_text().splitlines()
   info['configuration']=[line for line in lines if line.startswith(('Type=','User=','Group=','WorkingDirectory=','EnvironmentFile=','Restart=','OnCalendar=','Persistent=','Unit='))]
   commands=[line for line in lines if line.startswith('ExecStart=')]
   # Known financial CLI command only, never export arbitrary credential-bearing arguments.
   for command in commands:
    if re.search(r'(?i)token|secret|password|api[_-]?key|authorization',command):
     raise SystemExit('HOLD_SENSITIVE_EXECSTART')
   info['commands']=commands
  report['units'][unit]=info
for name in ('config/env/.env','runtime/secure-secrets-portal/credential-store.env'):
 p=root/name;keys=[]
 if p.is_file():
  for line in p.read_text().splitlines():
   if '=' in line and not line.lstrip().startswith('#'):
    key,value=line.split('=',1)
    if value.strip().strip('"').strip("'"):keys.append(key.strip())
 report['env_files'][name]={'exists':p.is_file(),'defined_names':sorted(set(keys))}
print('BEGIN_FINANCE_SOURCE_JSON')
print(json.dumps(report,ensure_ascii=False,sort_keys=True))
print('END_FINANCE_SOURCE_JSON')
'''

def ledger(db):
    if not db.is_file() or db.is_symlink():raise ValueError('KOREA_DATABASE_MISSING')
    con=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=5)
    result={}
    try:
        con.execute('PRAGMA query_only=ON');con.execute('BEGIN')
        if con.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('KOREA_DATABASE_INTEGRITY')
        tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name in TABLES:
            if name not in tables:result[name]=None;continue
            rows=con.execute('SELECT * FROM "'+name+'"').fetchall()
            values=sorted(json.dumps(row,ensure_ascii=False,sort_keys=True,
                default=lambda v:v.hex() if isinstance(v,bytes) else str(v)) for row in rows)
            result[name]={'count':len(rows),'sha256':hashlib.sha256('\n'.join(values).encode()).hexdigest()}
        return result
    finally:con.close()

def main():
    if os.geteuid()!=0 or os.uname().nodename.split('.')[0]!=HOST:raise SystemExit('HOLD_NOT_KOREA')
    os.umask(0o077)
    checkpoint=Path('/root')/('xuanjun-finance-takeover-inspect-'+datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S%fZ'))
    checkpoint.mkdir(mode=0o700)
    print('CHECKPOINT:',str(checkpoint),flush=True)
    local=ledger(BASE/'app/database/data/trading.db')
    contract=json.loads((BASE/'contract.json').read_text())
    argv=(contract.get('korea_source_tunnel') or {}).get('argv') or []
    if '43.108.99.66' not in argv or '/home/admin/.ssh/yibi_openclaw' not in argv:
        raise SystemExit('HOLD_ORIGINAL_SSH_BINDING_CHANGED')
    candidates=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            args=(proc/'cmdline').read_bytes().decode(errors='replace').split('\0')
            if args and Path(args[0]).name=='ssh' and '43.108.99.66' in args and '127.0.0.1:18761:127.0.0.1:18760' in args:
                candidates.append(proc.name)
        except (OSError,ValueError):pass
    if len(candidates)!=1:raise SystemExit('HOLD_ORIGINAL_SOURCE_TUNNEL_PID_NOT_UNIQUE:'+str(len(candidates)))
    entry=shutil.which('nsenter')
    if not entry:raise SystemExit('HOLD_NSENTER_MISSING')
    # Same existing identity, destination and strict host-key verification; no new tunnel.
    command=[entry,'--target',candidates[0],'--mount','--','/usr/bin/ssh',
        '-F','/dev/null','-i','/home/admin/.ssh/yibi_openclaw','-l','admin','-p','22',
        '-o','UserKnownHostsFile=/home/admin/.ssh/known_hosts','-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',
        '43.108.99.66','sudo -n /usr/bin/python3 -I -B -S -']
    print('SOURCE_LEDGER_AND_JOB_WIRING_CHECK: RUNNING',flush=True)
    r=subprocess.run(command,input=REMOTE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        universal_newlines=True,timeout=55)
    (checkpoint/'source-ssh.private.log').write_text(r.stderr)
    if r.returncode:
        print('HOLD_SOURCE_SSH_COMMAND_FAILED:',r.returncode,'PRIVATE_LOG:',str(checkpoint/'source-ssh.private.log'))
        raise SystemExit(2)
    try:
        body=r.stdout.split('BEGIN_FINANCE_SOURCE_JSON\n',1)[1].split('\nEND_FINANCE_SOURCE_JSON',1)[0]
        source=json.loads(body)
    except Exception:
        (checkpoint/'source-output.private.log').write_text(r.stdout)
        raise SystemExit('HOLD_SOURCE_RECEIPT_INVALID')
    if source.get('host')!=TOKYO or source.get('integrity')!='ok':raise SystemExit('HOLD_SOURCE_IDENTITY_OR_INTEGRITY')
    differences=[name for name in TABLES if local.get(name)!=source['ledger'].get(name)]
    local_env={}
    for name in ('config/env/.env','runtime/secure-secrets-portal/credential-store.env'):
        p=BASE/'app'/name;keys=[]
        if p.is_file():
            for line in p.read_text().splitlines():
                if '=' in line and not line.lstrip().startswith('#'):
                    key,value=line.split('=',1)
                    if value.strip().strip('"').strip("'"):keys.append(key.strip())
        local_env[name]={'exists':p.is_file(),'defined_names':sorted(set(keys))}
    receipt={'korea':local,'tokyo':source,'different_tables':differences,'korea_env_files':local_env,
        'side_effects':{'database_writes':0,'timer_changes':0,'binance_calls':0,'credential_changes':0}}
    (checkpoint/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    for name in TABLES:
        print('LEDGER_COMPARE:',name,'MATCH' if name not in differences else 'DIFFERENT')
    for name,info in source['units'].items():
        print('SOURCE_UNIT:',name,'STATE:',info.get('ActiveState'),'PID:',info.get('MainPID'))
        for line in info.get('configuration',[]):print(line)
        for line in info.get('commands',[]):print(line)
    for name,info in local_env.items():
        remote=source['env_files'][name]
        print('CREDENTIAL_ENV_FILE:',name,'KOREA_EXISTS:',info['exists'],'TOKYO_EXISTS:',remote['exists'],
            'MISSING_KOREA_NAMES:',json.dumps(sorted(set(remote['defined_names'])-set(info['defined_names']))))
    print('RECEIPT:',str(checkpoint/'receipt.json'))
    print('SOURCE_AND_TARGET_INSPECTION_COMPLETE; NO_TASKS_STOPPED_OR_STARTED')
    if differences:print('TAKEOVER_HOLD: SOURCE_AND_TARGET_LEDGER_DIFFERENCES')
    else:print('LEDGER_HISTORY_MATCH; NEXT_ACTIVATION_MUST_USE_ONE_FINANCE_WRITER')
if __name__=='__main__':
    try:main()
    except subprocess.TimeoutExpired:raise SystemExit('HOLD_SOURCE_CHECK_TIMEOUT; NO_TASKS_CHANGED')
