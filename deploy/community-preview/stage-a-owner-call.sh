# REVIEW CANDIDATE ONLY. Run only after root review and Owner's exact stage-A approval.
if (
  set +e
  /usr/bin/sudo -n /usr/bin/python3 -I -B -S - <<'STAGE_A'
import os,stat,pwd,hashlib,io,json,zipfile
PATH='/home/admin/ISSUE76_STAGE_A_9b071542577c.zip'
SIZE=57177136
DIGEST='0b1dbd4e31fe55de1be29c7a140fea155a05b9178f6a1681c721029cc97e0754'
ENTRY_SHA='9b071542577c6ddd932826a167dbbd262c2f8493c093c147d475915c5aa7a727'
MANIFEST_SHA='2c56e970ffaf67838d00c7f950fb9e37692b51b45b851412cc955e93b28539c6'
def need(v):
 if not v:raise RuntimeError('FIXED_STAGE_A_INPUT_HOLD')
def identity(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def unique(rows):
 out={}
 for k,v in rows:need(k not in out);out[k]=v
 return out
try:
 need(os.getuid()==0 and os.geteuid()==0 and os.uname().nodename.split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ')
 admin=pwd.getpwnam('admin').pw_uid;need(admin>0)
 parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  for part in PATH.split('/')[1:-1]:
   child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);os.close(parent);parent=child
   s=os.fstat(parent);need(s.st_uid in (0,admin) and not s.st_mode&0o022)
  fd=os.open(PATH.split('/')[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
  try:
   before=os.fstat(fd);need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid in (0,admin) and not before.st_mode&0o022 and before.st_size==SIZE)
   chunks=[];count=0
   while True:
    b=os.read(fd,min(1048576,SIZE-count+1))
    if not b:break
    chunks.append(b);count+=len(b);need(count<=SIZE)
   body=b''.join(chunks);need(len(body)==SIZE and hashlib.sha256(body).hexdigest()==DIGEST)
   need(identity(before)==identity(os.fstat(fd))==identity(os.stat(PATH.split('/')[-1],dir_fd=parent,follow_symlinks=False)))
  finally:os.close(fd)
 finally:os.close(parent)
 with zipfile.ZipFile(io.BytesIO(body)) as archive:
  info=archive.infolist();need(len(info)==6 and len({x.filename for x in info})==6 and sum(x.file_size for x in info)<=58000000)
  need(all(not x.flag_bits&1 and (x.external_attr>>16)&0o170000==0o100000 for x in info))
  raw=archive.read('manifest.json');need(len(raw)<=16384 and hashlib.sha256(raw).hexdigest()==MANIFEST_SHA)
  m=json.loads(raw,object_pairs_hook=unique);need(raw==json.dumps(m,sort_keys=True,separators=(',',':')).encode())
  need(type(m) is dict and set(m)=={'format','purpose','entry','payload'} and type(m['format']) is int and m['format']==1 and m['purpose']=='STAGE_A_FOUR_PUBLIC_INPUTS_NOT_AUTHORIZATION')
  names={'stage-a-entry.py','manifest.json'}|set(m['payload']);need(set(archive.namelist())==names)
  source=archive.read('stage-a-entry.py');need(hashlib.sha256(source).hexdigest()==ENTRY_SHA and m['entry']=={'bytes':len(source),'sha256':ENTRY_SHA})
  blobs={}
  for name,meta in m['payload'].items():
   b=archive.read(name);need(meta=={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()});blobs[name]=b
 ns={'__name__':'verified_stage_a_entry'};exec(compile(source,'<verified-stage-a-entry>','exec'),ns)
 result=ns['run'](blobs,MANIFEST_SHA)
except BaseException:
 print('{"state":"HOLD_STAGE_A_INPUT_OR_CONTEXT","site_update":false,"servertrust":false}');result=2
raise SystemExit(result)
STAGE_A
  community_stage_a_inner=$?
  printf 'STAGE_A_INNER_EXIT=%s\n' "$community_stage_a_inner"
  exit "$community_stage_a_inner"
); then
  community_stage_a_outer=0
else
  community_stage_a_outer=$?
fi
printf 'STAGE_A_OUTER_EXIT=%s LOGIN_SHELL_PRESERVED\n' "$community_stage_a_outer"
