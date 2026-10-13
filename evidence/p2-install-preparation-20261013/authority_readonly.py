"""Read-only bounded UK P2 authority snapshot; never grants admission."""
import collections, datetime, hashlib, json, os, socket, sqlite3, stat, subprocess
DB='/home/xuanjun_dev/uk-stage1-minimal/state.sqlite'
UNITS=['xuanjun-uk-stage1-minimal.service','xuanjun-uk-openclaw.service','xuanjun-uk-owner-callback.service','xuanjun-uk-owner-dashboard.service','xuanjun-p2-mechanical.timer','xuanjun-p2-mechanical.path','xuanjun-p2-mechanical.service']
def command(args):
    r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=20)
    if r.returncode: raise ValueError('READONLY_COMMAND_FAILED')
    return r.stdout.decode('utf-8','replace')
def digest(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        st=os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_size>1048576:raise ValueError('BOUNDED_REGULAR_FILE_REQUIRED')
        return hashlib.sha256(f.read(1048577)).hexdigest()
def main():
    if os.geteuid()!=0 or socket.gethostname().split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ':raise ValueError('FIXED_UK_ROOT_REQUIRED')
    before=digest(DB)
    if before!='a6b3847009ca7ee394772b7cf0144b90f82d1c68a3e9b4d3e9c4656f50c28d60':raise ValueError('LEGACY_DATABASE_DRIFT')
    for suffix in ['-wal','-journal']:
        if os.path.exists(DB+suffix) and os.stat(DB+suffix).st_size:raise ValueError('NONEMPTY_DATABASE_JOURNAL_HOLD')
    out={'schema':1,'observed_utc':datetime.datetime.utcnow().isoformat()+'Z','units':{},'global_writer_exclusion':'UNKNOWN','effects':0}
    props=['Id','LoadState','ActiveState','SubState','MainPID','UnitFileState','ControlGroup','FragmentPath']
    for unit in UNITS:
        raw=command(['/usr/bin/systemctl','show',unit]+['--property='+p for p in props])
        out['units'][unit]=dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
    # Inventory unit names/states only; never export ExecStart, environment or command lines.
    inventory=command(['/usr/bin/systemctl','list-units','--all','--no-legend','--no-pager','--plain']).splitlines()
    out['loaded_xuanjun_units']=[r for r in inventory if 'xuanjun' in r or 'xj-' in r][:2048]
    out['unit_inventory_truncated']=len(inventory)>2048
    con=sqlite3.connect('file:'+DB+'?mode=ro&immutable=1',uri=True)
    try:
        con.execute('PRAGMA query_only=ON')
        deadline=datetime.datetime.utcnow()+datetime.timedelta(seconds=15)
        con.set_progress_handler(lambda: 1 if datetime.datetime.utcnow()>deadline else 0,1000)
        out['quick_check']=con.execute('PRAGMA quick_check').fetchone()[0]
        tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        out['tables']=sorted(tables)
        if 'tasks' in tables:
            cols={r[1] for r in con.execute('PRAGMA table_info(tasks)')}
            out['task_columns']=sorted(cols)
            if 'status' in cols:out['task_status_counts']=list(con.execute('SELECT status,count(*) FROM tasks GROUP BY status'))
            for c in ['lease_owner','lease_until']:
                if c in cols:out[c+'_nonempty']=con.execute('SELECT count(*) FROM tasks WHERE "'+c+'" IS NOT NULL AND CAST("'+c+'" AS TEXT)<>\'\'').fetchone()[0]
            if 'fence' in cols:out['fence_counts']=list(con.execute('SELECT fence,count(*) FROM tasks GROUP BY fence'))
        for name in ['owner_callback_requests','owner_notification_outbox','xj_owner_notification_outbox']:
            if name not in tables:continue
            cols={r[1] for r in con.execute('PRAGMA table_info('+name+')')}
            row={'count':con.execute('SELECT count(*) FROM '+name).fetchone()[0],'columns':sorted(cols)}
            for c in ['status','state','consumed']:
                if c in cols:row[c+'_counts']=list(con.execute('SELECT "'+c+'",count(*) FROM '+name+' GROUP BY "'+c+'"'))
            # Expiry values only: do not export request IDs, auth tokens, message text or task bodies.
            for c in ['expires_at','expiry','expires_at_ms','expiry_at']:
                if c in cols:row[c+'_values']=[r[0] for r in con.execute('SELECT "'+c+'" FROM '+name+' LIMIT 32')]
            out[name]=row
    finally:con.close()
    out['database_unchanged']=before==digest(DB)
    if not out['database_unchanged']:raise ValueError('DATABASE_CHANGED_DURING_AUDIT')
    out['database_sha256']=before
    print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
