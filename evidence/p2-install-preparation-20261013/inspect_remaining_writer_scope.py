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
