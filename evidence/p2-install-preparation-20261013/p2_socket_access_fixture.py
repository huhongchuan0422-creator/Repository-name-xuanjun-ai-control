"""Isolated numeric-UID kernel proof; no NSS, systemd, or production socket writes."""
import hashlib, json, os, pathlib, shutil, socket, stat, subprocess, sys
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
run=sys.argv[1];assert run.isdigit()
root='/tmp/xj-p2-socket-access-'+run
os.mkdir(root,0o711);os.chmod(root,0o711)
clients=[('gateway',1002,1002,[]),('dispatcher',1003,1003,[1006]),
         ('callback',1004,1006,[]),('worker',1005,1005,[])]
probe="""import os,socket,sys,json
uid,gid=int(sys.argv[1]),int(sys.argv[2]);os.setgroups(json.loads(sys.argv[3]));os.setgid(gid);os.setuid(uid)
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(2)
try:s.connect(sys.argv[4]);status='ALLOWED'
except PermissionError:status='DENIED'
finally:s.close()
print(json.dumps({'uid':uid,'connect':status}))
"""
rows=[]
try:
    for name,mode,gid,scoped in [('current_root_parent',0o750,1006,False),
      ('current_socket_traversable_parent',0o711,1006,False),
      ('candidate_dedicated_socket_group',0o711,1007,True)]:
        directory=root+'/'+name;os.mkdir(directory,mode);os.chmod(directory,mode)
        endpoint=directory+'/ledger.sock';server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            server.bind(endpoint);os.chown(endpoint,1003,gid);os.chmod(endpoint,0o660);server.listen(16)
            outcomes=[]
            for role,uid,primary,groups in clients:
                groups=list(groups)+([1007] if scoped and role!='worker' else [])
                p=subprocess.run(['/usr/bin/python3','-I','-B','-c',probe,str(uid),str(primary),json.dumps(groups),endpoint],
                  env={'PATH':'/usr/bin:/bin','LANG':'C'},stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=5)
                assert p.returncode==0
                item=json.loads(p.stdout.decode());item['role']=role;outcomes.append(item)
            rows.append({'case':name,'directory_mode':oct(mode),'socket_mode':'0o660','socket_gid':gid,'clients':outcomes})
        finally:server.close()
    assert all(r['connect']=='DENIED' for r in rows[0]['clients'])
    assert [r['connect'] for r in rows[1]['clients']]==['DENIED','ALLOWED','ALLOWED','DENIED']
    assert [r['connect'] for r in rows[2]['clients']]==['ALLOWED','ALLOWED','ALLOWED','DENIED']
finally:
    shutil.rmtree(root)
result={'schema':1,'state':'SOCKET_PERMISSION_BLOCKER_REPRODUCED_AND_SCOPED_GROUP_FIXTURE_PASS',
 'cases':rows,'fixture_removed':not os.path.exists(root),'candidate_gid_unreserved':True,
 'candidate_applied':False,'production_services_changed':False,'nss_changed':False,
 'canonical_ledger_changed':False,'writer_admission':False,'model_calls':0}
raw=(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode()
parent='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
info=os.lstat(parent);assert stat.S_ISDIR(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700 and os.path.realpath(parent)==parent
fd=os.open(parent+'/socket-permission-proof-'+run+'.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
print(json.dumps(result,sort_keys=True));print('SOCKET_PERMISSION_PROOF_SHA256='+hashlib.sha256(raw).hexdigest())
