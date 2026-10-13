"""Bounded process/service inventory and immutable migration source inspection."""
import os,socket,json,subprocess,base64,hashlib
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
uids={1002,1003,1004,1005,1008};processes=[];races=0
for name in os.listdir('/proc'):
 if not name.isdigit():continue
 try:
  with open('/proc/'+name+'/status') as f:s=f.read(65537)
  uid=int(next(x for x in s.splitlines() if x.startswith('Uid:')).split()[1])
  if uid not in uids:continue
  exe=os.readlink('/proc/'+name+'/exe')
  with open('/proc/'+name+'/cgroup') as f:cg=f.read(65537)
  processes.append({'pid':int(name),'uid':uid,'exe':exe,'cgroup':cg})
 except (FileNotFoundError,ProcessLookupError):races+=1
units={}
for kind,args in [('running_services',['list-units','--type=service','--state=running']),('all_timers',['list-timers','--all']),('related_unit_files',['list-unit-files'])]:
 r=subprocess.run(['/usr/bin/systemctl']+args+['--no-pager','--no-legend'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
 assert r.returncode==0 and len(r.stdout)<=1048576
 units[kind]=[x for x in r.stdout.decode().splitlines() if 'xuanjun' in x.lower() or 'openclaw' in x.lower()]
root='/tmp/p2-adopted-plan-38432771093/xuanjun-p2-package'
with open(root+'/deploy/integration-manifest.json','rb') as f:mraw=f.read()
assert hashlib.sha256(mraw).hexdigest()=='508fcce851c7ea6e78efe28044871f44fff3e3dbfa8bffd94dffae2a2f89d3fd'
manifest=json.loads(mraw)
for rel in ('stage1/ledger_install_stage.py','stage1/ledger_backup.py'):
 with open(root+'/'+rel,'rb') as f:r=f.read(131073)
 assert len(r)<=131072 and hashlib.sha256(r).hexdigest()==manifest['files'][rel]
 print('MIGRATION_SOURCE='+json.dumps({'path':rel,'base64':base64.b64encode(r).decode()}))
print('BOUNDED_WRITER_INVENTORY='+json.dumps({'development_uid_processes':processes,'units':units,'process_races':races,'scope':'UID1002_1003_1004_1005_1008_AND_RELATED_SYSTEMD_NAMES','other_writers_outside_scope':'UNKNOWN','canonical_ledger_opened':False,'fence_mutation':False,'services_changed':False,'install':False,'model_calls':0},sort_keys=True))

import ast,re,shlex,stat
aux={}
for unit in ('xuanjun-uk-owner-callback.service','xuanjun-uk-owner-dashboard.service','xuanjun-p2-mechanical.service','xuanjun-p2-mechanical.timer','xuanjun-p2-mechanical.path'):
 r=subprocess.run(['/usr/bin/systemctl','show',unit,'--property=FragmentPath,ActiveState,SubState,MainPID,UnitFileState,ControlGroup'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
 assert r.returncode==0
 info=dict(x.split('=',1) for x in r.stdout.decode().splitlines() if '=' in x)
 path=info['FragmentPath'];assert path.startswith('/etc/systemd/system/') and os.path.realpath(path)==path
 with open(path,'rb') as f:raw=f.read(65537)
 assert len(raw)<=65536;info['fragment_sha256']=hashlib.sha256(raw).hexdigest()
 commands=[x.split('=',1)[1] for x in raw.decode().splitlines() if x.startswith('ExecStart=')]
 sourcepaths=set()
 for command in commands:
  for token in shlex.split(command):
   if token.startswith('/') and token.endswith(('.py','.sh')) and os.path.isfile(token):sourcepaths.add(token)
 findings=[]
 for p in sorted(sourcepaths):
  assert os.path.realpath(p)==p
  with open(p,'rb') as f:code=f.read(262145)
  assert len(code)<=262144
  value={'path':p,'sha256':hashlib.sha256(code).hexdigest(),'size':len(code)}
  text=code.decode()
  value['legacy_database_path_literal']= '/home/xuanjun_dev/uk-stage1-minimal/state.sqlite' in text
  value['contains_sqlite_connect']= 'sqlite3.connect' in text
  value['contains_ledger_claim_or_finish']=any(x in text for x in ('.claim(','.finish(','.execute('))
  value['contains_service_start_or_restart']=bool(re.search(r'(systemctl.*(?:start|restart)|openclaw.*gateway)',text))
  if p.endswith('.py'):
   tree=ast.parse(text)
   value['imports']=sorted(set(x.module for x in ast.walk(tree) if isinstance(x,ast.ImportFrom) and x.module))
   sql=[]
   for node in ast.walk(tree):
    if isinstance(node,ast.Str):
     q=node.s.strip().split()
     if q and q[0].upper() in ('UPDATE','INSERT','DELETE','REPLACE','SELECT','CREATE'):sql.append(q[0].upper())
   value['sql_verbs']=sorted(set(sql))
  findings.append(value)
 info['entrypoint_sources']=findings;aux[unit]=info
print('AUXILIARY_STATIC_EFFECT_SCOPE='+json.dumps(aux,sort_keys=True))
print('AUXILIARY_STOP=NO; AUTHORIZATION_NOT_EXPANDED')

import glob
modules=[]
for path in glob.glob('/home/xuanjun_dev/uk-stage1-minimal/**/uk_owner_callback.py',recursive=True):
 assert os.path.realpath(path)==path
 with open(path,'rb') as f:raw=f.read(262145)
 assert len(raw)<=262144
 text=raw.decode();tree=ast.parse(text);verbs=[];imports=[];calls=[]
 for node in ast.walk(tree):
  if isinstance(node,ast.ImportFrom):imports.append(node.module)
  if isinstance(node,ast.Import):imports.extend(x.name for x in node.names)
  if isinstance(node,ast.Str):
   q=node.s.strip().split()
   if q and q[0].upper() in ('INSERT','UPDATE','DELETE','REPLACE','SELECT','CREATE'):verbs.append(q[0].upper())
  if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
   if node.func.attr in ('claim','finish','approve','reject','execute','executemany','commit','connect'):calls.append(node.func.attr)
 modules.append({'path':path,'sha256':hashlib.sha256(raw).hexdigest(),'imports':sorted(set(imports)),'sql_verbs':sorted(set(verbs)),'effect_call_names':sorted(set(calls)),'old_database_literal':'state.sqlite' in text})
print('CALLBACK_DEPENDENCY_EFFECTS='+json.dumps(modules,sort_keys=True))
