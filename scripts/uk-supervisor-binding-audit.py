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
    if 'installed_supervisor_source' in result:
        functions={}
        for node in tree.body:
            if isinstance(node,ast.FunctionDef) and node.name in ('load_state','save_state'):
                # These helpers only expose source structure; no values from state.
                keys=[]
                for child in ast.walk(node):
                    if isinstance(child,ast.Str) and len(child.s)<100 and re.fullmatch(r'[A-Za-z0-9_./-]+',child.s):
                        if not any(w in child.s.lower() for w in ('secret','token','password','credential')):
                            keys.append(child.s)
                functions[node.name]={'parameters':[a.arg for a in node.args.args],'constant_names':sorted(set(keys))}
        result['installed_state_helpers']=functions
        paths=[]
        for node in tree.body:
            if isinstance(node,ast.Assign) and isinstance(node.value,ast.Str):
                val=node.value.s
                if val.startswith(('/home/xuanjun_dev/','/var/lib/xuanjun','/tmp/xuanjun')) and re.fullmatch(r'[A-Za-z0-9_./-]+',val) and not any(w in val.lower() for w in ('credential','secret','token','auth')):
                    paths.append({'names':[n.id for n in node.targets if isinstance(n,ast.Name)],'path':val})
        result['installed_top_level_paths']=paths
    # Read existing unit metadata; never print ExecStart or raw command lines.
    unit_names=('xuanjun-ledger.service','xuanjun-p2-supervisor.service','xuanjun-p2-supervisor.timer')
    result['existing_units']={}
    for unit in unit_names:
        p=subprocess.run(['/usr/bin/systemctl','show',unit,
            '--property=LoadState,ActiveState,SubState,MainPID,FragmentPath'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,
            env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        result['existing_units'][unit]={a:b[:256] for a,sep,b in (line.partition('=') for line in p.stdout.decode('utf-8','replace').splitlines()) if sep and a in ('LoadState','ActiveState','SubState','MainPID','FragmentPath')}
    result['existing_controller_paths']=[]
    for root in ('/var/lib/xuanjun-development','/var/lib/xuanjun-p2-mechanical'):
        if not os.path.lexists(root):
            result['existing_controller_paths'].append({'path':root,'exists':False});continue
        meta=os.lstat(root)
        result['existing_controller_paths'].append({'path':root,'exists':True,'uid':meta.st_uid,'mode':oct(stat.S_IMODE(meta.st_mode))})
        try:
            names=sorted(os.listdir(root))[:50]
        except OSError:
            result['existing_controller_paths'][-1]['read']='PERMISSION_UNAVAILABLE';continue
        for name in names:
            if not any(word in name.lower() for word in ('ledger','state','supervis')) or any(word in name.lower() for word in ('auth','secret','token','credential')):
                continue
            path=root+'/'+name;meta=os.lstat(path)
            row={'path':path,'uid':meta.st_uid,'mode':oct(stat.S_IMODE(meta.st_mode)),'size':meta.st_size,'canonical_authority':'NOT_PROVEN'}
            if stat.S_ISREG(meta.st_mode) and name.endswith(('.db','.sqlite','.sqlite3')) and meta.st_size<16777216:
                from urllib.parse import quote
                try:
                    db=sqlite3.connect('file:'+quote(path,safe='/')+'?mode=ro',uri=True,timeout=3)
                    try:
                        row['application_id']=db.execute('PRAGMA application_id').fetchone()[0]
                        row['user_version']=db.execute('PRAGMA user_version').fetchone()[0]
                        row['table_names']=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 20")]
                    finally:db.close()
                except Exception:row['read']='SCHEMA_UNAVAILABLE_NO_RAW_OUTPUT'
            result['existing_controller_paths'].append(row)
    # Resolve only argv structure and job identity from the existing helpers.
    helper_commands={}
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name in ('load_state','save_state'):
            commands=[]
            for child in ast.walk(node):
                if isinstance(child,ast.Call) and isinstance(child.func,ast.Name) and child.func.id=='run' and child.args and isinstance(child.args[0],(ast.List,ast.Tuple)):
                    values=[]
                    for arg in child.args[0].elts:
                        if isinstance(arg,ast.Str) and len(arg.s)<100 and re.fullmatch(r'[A-Za-z0-9_./:-]+',arg.s):
                            values.append(arg.s)
                        elif isinstance(arg,ast.Name):values.append('VARIABLE:'+arg.id)
                        else:values.append('EXPRESSION_NOT_EVALUATED')
                    commands.append(values)
            helper_commands[node.name]=commands
    result['existing_scratch_argv']=helper_commands
    jobs=[]
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(n,ast.Name) and ('JOB' in n.id or 'SUPERVISOR' in n.id) for n in node.targets):
            for child in ast.walk(node.value):
                if isinstance(child,ast.Str) and re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',child.s):
                    jobs.append(child.s)
    result['supervisor_job_constants']=sorted(set(jobs))
    result['scratch_help']={}
    cli=HOME_PATH+'/.openclaw/bin/openclaw'
    for args in (['automations','--help'],['automations','scratch','--help']):
        p=subprocess.run([cli]+args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,env=env)
        helptext=p.stdout.decode('utf-8','replace')
        result['scratch_help'][' '.join(args)]={'exit_code':p.returncode,'options':sorted(set(re.findall(r'--[a-z][a-z-]+',helptext)))}
    job='a96b9a83-5e58-412c-ab66-ba3bf0add8b9'
    if job not in result.get('supervisor_job_constants',[]):
        result['canonical_scratch']={'state':'HOLD_JOB_BINDING_CHANGED'}
    else:
        p=subprocess.run([cli,'automations','scratch',job,'--json'],env=env,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
        if p.returncode!=0 or len(p.stdout)>1048576:
            result['canonical_scratch']={'state':'HOLD_SCRATCH_READ_UNAVAILABLE','exit_code':p.returncode}
        else:
            wrapper=json.loads(p.stdout.decode('utf-8'))
            value=wrapper.get('content')
            if isinstance(value,str):value=json.loads(value)
            if not isinstance(value,dict):
                result['canonical_scratch']={'state':'HOLD_SCRATCH_FORMAT_UNCONFIRMED','wrapper_keys':sorted(wrapper)[:40]}
            else:
                selected=[]
                keys={'task_id','taskId','parent_task_id','state','status','owner','role','entry','attempt_id','run_id','session_id','lease_id','fence','epoch','revision','checkpoint_sha256','spec_sha256','last_real_progress_at','progress_deadline','next_owner','child_started','live_execution_units','canonical_ledger_path'}
                def inspect(v,path,depth=0):
                    if depth>5 or len(selected)>=80:return
                    if isinstance(v,dict):
                        for key,item in sorted(v.items()):
                            if any(w in key.lower() for w in ('prompt','message','history','secret','credential','token','auth')):continue
                            here=path+'.'+key
                            if key in keys:
                                if isinstance(item,str) and len(item)<=180 and re.fullmatch(r'[A-Za-z0-9_./:-]+',item):
                                    selected.append({'path':here,'value':item})
                                elif type(item) in (bool,int,float) or item is None:
                                    selected.append({'path':here,'value':item})
                            elif isinstance(item,(list,dict)):inspect(item,here,depth+1)
                    elif isinstance(v,list):
                        for i,item in enumerate(v[:20]):inspect(item,path+'[%d]'%i,depth+1)
                inspect(value,'content')
                result['canonical_scratch']={'state':'READ_ONLY_VERIFIED_JOB','job_id':job,
                    'revision':wrapper.get('currentRevision',wrapper.get('revision')),
                    'wrapper_keys':sorted(wrapper)[:40],'content_keys':sorted(value)[:60],
                    'content_sha256':hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),
                    'selected_fields':selected,'write_performed':False}
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
