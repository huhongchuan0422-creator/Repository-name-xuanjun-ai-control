"""Read-only certificate renewal asset inventory; values never exported."""
import os,json,socket,stat,hashlib
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
roots=["/etc/letsencrypt","/root/.acme.sh","/home/admin/.acme.sh","/home/xuanjun_dev/.acme.sh","/tmp/p2pkg-38369525772-1"];out=[]
for root in roots:
 if not os.path.lexists(root):out.append({'root':root,'exists':False});continue
 row={'root':root,'exists':True,'entries':[]};count=0
 for parent,dirs,files in os.walk(root,followlinks=False):
  dirs[:]=[n for n in dirs if not os.path.islink(parent+'/'+n)]
  for n in files:
   count+=1;assert count<4096
   p=parent+'/'+n
   if not (n.endswith(('.conf','.json','.pem','.key','.cer')) or n in ('acme.sh','account.key','account.conf')):continue
   s=os.lstat(p)
   if not stat.S_ISREG(s.st_mode) or s.st_size>1048576:continue
   row['entries'].append({'path':p,'uid':s.st_uid,'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode),'size':s.st_size})
 out.append(row)
print('TLS_RENEWAL_ASSET_METADATA='+json.dumps(out,sort_keys=True))
