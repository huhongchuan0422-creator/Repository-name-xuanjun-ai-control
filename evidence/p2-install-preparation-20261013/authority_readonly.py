"""Read-only bounded UK P2 authority snapshot; never grants admission."""
import collections, datetime, hashlib, json, os, socket, sqlite3, stat, subprocess
DB='/home/xuanjun_dev/uk-stage1-minimal/state.sqlite'
UNITS=['xuanjun-uk-stage1-minimal.service','xuanjun-uk-openclaw.service','xuanjun-uk-owner-callback.service','xuanjun-uk-owner-dashboard.service','xuanjun-p2-mechanical.timer','xuanjun-p2-mechanical.path','xuanjun-p2-mechanical.service','xj-uk-owner-notify.service','xj-uk-owner-notify.timer']
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
    # Inspect fixed notifier files without exposing arguments, environment or file content.
    import shlex
    notifier={}
    for unit in ['xj-uk-owner-notify.service','xj-uk-owner-notify.timer']:
        path='/etc/systemd/system/'+unit
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as f:
            st=os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_size>262144:raise ValueError('NOTIFIER_UNIT_BOUND_REQUIRED')
            raw=f.read(262145)
        value={'unit_sha256':hashlib.sha256(raw).hexdigest(),'script_capabilities':[]}
        if unit.endswith('.service'):
            for line in raw.decode('utf-8').splitlines():
                if not line.startswith('ExecStart='):continue
                tokens=shlex.split(line[len('ExecStart='):])
                for token in tokens:
                    if not token.startswith(('/home/xuanjun_dev/','/opt/xuanjun-uk-control/')) or not token.endswith(('.py','.sh')):continue
                    if os.path.realpath(token)!=token:raise ValueError('NOTIFIER_SCRIPT_SYMLINK_HOLD')
                    fd=os.open(token,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                    with os.fdopen(fd,'rb') as f:
                        st=os.fstat(f.fileno())
                        if not stat.S_ISREG(st.st_mode) or st.st_size>1048576:raise ValueError('NOTIFIER_SCRIPT_BOUND_REQUIRED')
                        b=f.read(1048577)
                    text=b.decode('utf-8')
                    value['script_capabilities'].append({'path':token,'sha256':hashlib.sha256(b).hexdigest(),'sqlite_reference':'sqlite' in text.lower(),'sql_mutation_tokens':any(x in text.upper() for x in ['INSERT INTO','UPDATE ','DELETE FROM','CREATE TABLE']),'telegram_send_reference':'sendMessage' in text,'readonly_immutable_reference':'immutable=1' in text,'expiry_guard_reference':'expires_at' in text})
        notifier[unit]=value
    out['notifier_static_metadata']=notifier
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
            for c in ['status','state']:
                if c in cols:out['task_'+c+'_counts']=list(con.execute('SELECT "'+c+'",count(*) FROM tasks GROUP BY "'+c+'"'))
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
