"""Bounded read-only UK supervision binding audit; no model or dispatch."""
import json, os, pwd, socket, sqlite3, stat, subprocess, time
HOME_PATH='/home/xuanjun_dev'
KEY='f99816db392e0f8e50af028cdd2f2782f0bdeb8e8f2a0e23713a2b1f38350c0a'
def main():
    if os.geteuid()!=pwd.getpwnam('xuanjun_dev').pw_uid or os.geteuid()==0 or socket.gethostname().split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ':
        raise SystemExit('HOLD_FIXED_NONROOT_UK_AUDIT')
    result={'state':'READONLY_BINDING_AUDIT','observed_at':time.time(),
            'model_calls':0,'dispatch_calls':0,'authority_mutation':'NONE',
            'ledger_creation':'NO','install':'NO','canonical_binding':'NOT_PROVEN'}
    journal={}
    for suffix in ('.json','.json.terminal'):
        path=HOME_PATH+'/p2-platform-delivery-receipts/'+KEY+suffix
        if not os.path.lexists(path):
            journal[suffix]={'exists':False};continue
        info=os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_size>65536:
            journal[suffix]={'state':'HOLD_UNSAFE_JOURNAL'};continue
        with open(path) as stream:value=json.load(stream)
        keys=('state','task_id','role_requested','authority_comment','dispatch_key',
              'child_started','model_calls_requested','main_sessionId','main_runId',
              'reported_state','reported_run_id','reported_session_key',
              'reported_process_or_unit','transport_started_at','install')
        journal[suffix]={key:value[key] for key in keys if key in value}
    result['dispatch_journal']=journal
    units={}
    for unit in ('xuanjun-task-supervisor.service','xuanjun-task-supervisor.timer'):
        p=subprocess.run(['/usr/bin/systemctl','show',unit,
            '--property=LoadState,ActiveState,SubState,MainPID,FragmentPath'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,
            env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        data={}
        for line in p.stdout.decode('utf-8','replace').splitlines():
            key,sep,value=line.partition('=')
            if sep and key in ('LoadState','ActiveState','SubState','MainPID','FragmentPath'):
                data[key]=value[:256]
        units[unit]=data
    result['supervisor_units']=units
    root=HOME_PATH+'/.openclaw/workspace'
    candidates=[];visited=0
    for directory,folders,files in os.walk(root,followlinks=False):
        depth=os.path.relpath(directory,root).count(os.sep)
        folders[:]=[n for n in folders if not n.startswith('.') and n not in ('node_modules','memory','credentials','secrets','auth','sessions') and depth<3]
        visited+=len(files)
        if visited>2000:
            result['discovery_truncated']=True;break
        for name in sorted(files):
            if not any(word in name.lower() for word in ('ledger','supervis','scratch')):
                continue
            if any(word in name.lower() for word in ('auth','credential','secret','token')):
                continue
            path=os.path.join(directory,name);info=os.lstat(path)
            if not stat.S_ISREG(info.st_mode):continue
            row={'path':path,'mode':oct(stat.S_IMODE(info.st_mode)),
                 'uid':info.st_uid,'size':info.st_size,
                 'identity':'%d:%d'%(info.st_dev,info.st_ino),
                 'canonical_authority':'NOT_PROVEN'}
            if name.endswith(('.sqlite','.sqlite3','.db')) and info.st_size<16777216:
                from urllib.parse import quote
                db=sqlite3.connect('file:'+quote(path,safe='/')+'?mode=ro',uri=True,timeout=3)
                try:
                    row['application_id']=db.execute('PRAGMA application_id').fetchone()[0]
                    row['user_version']=db.execute('PRAGMA user_version').fetchone()[0]
                    row['table_names']=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 20")]
                finally:db.close()
            candidates.append(row)
            if len(candidates)>=32:break
        if len(candidates)>=32:break
    result['observed_ledger_candidates']=candidates
    env={'HOME':HOME_PATH,'PATH':HOME_PATH+'/.openclaw/tools/node-v24.21.0/bin:/usr/bin:/bin','LANG':'C.UTF-8'}
    try:
        p=subprocess.run([HOME_PATH+'/.openclaw/bin/openclaw','sessions','--json','--agent','main'],
            env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
        if p.returncode!=0 or len(p.stdout)>1048576:
            result['native_registry']='UNAVAILABLE'
        else:
            value=json.loads(p.stdout.decode('utf-8'))
            rows=value if isinstance(value,list) else value.get('sessions',[])
            selected=[]
            for row in rows[:200]:
                if not isinstance(row,dict):continue
                sid=row.get('sessionId') or row.get('id')
                if sid!='e2474bef-73d5-4c39-9428-4d610697db29':continue
                selected.append({k:row[k] for k in ('sessionId','key','updatedAt','kind','status') if k in row})
            result['requested_main_session_records']=selected
    except Exception:
        result['native_registry']='HOLD_REGISTRY_READ_FAILED_NO_RAW_OUTPUT'
    # Inspect installed supervisor code as data, never import or execute it.
    import ast, hashlib, re
    installed=HOME_PATH+'/.openclaw/workspace/scripts/p2_supervisor.py'
    info=os.lstat(installed)
    if stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_size<131072:
        with open(installed,'rb') as stream:raw=stream.read(131073)
        tree=ast.parse(raw.decode('utf-8'))
        literals=[]
        for node in ast.walk(tree):
            if not isinstance(node,ast.Str):continue
            value=node.s
            if len(value)>160 or any(word in value.lower() for word in ('secret','credential','token','password','oauth','auth.json')):continue
            if (value.startswith(('/home/xuanjun_dev/','/tmp/xuanjun','/var/lib/xuanjun')) and re.fullmatch(r'[A-Za-z0-9_./-]+',value)) or (re.fullmatch(r'[A-Za-z0-9_./-]+',value) and any(word in value.lower() for word in ('ledger','supervis','scratch','checkpoint'))):
                literals.append(value)
        result['installed_supervisor_source']={
            'path':installed,'sha256':hashlib.sha256(raw).hexdigest(),
            'functions':[n.name for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)],
            'imports':[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]+[a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names],
            'state_path_literals':sorted(set(literals)),
            'calls':sorted(set(n.func.attr if isinstance(n.func,ast.Attribute) else n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,(ast.Attribute,ast.Name))))}
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
