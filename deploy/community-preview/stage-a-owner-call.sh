# REVIEW CANDIDATE ONLY. Exact stage-A approval still required.
# Acceptance requires BOTH the Python completion record and matching sudo exit.
if (
  set +e
  /usr/bin/sudo -n /usr/bin/python3 -I -B -S -c 'import os,stat,pwd,hashlib,io,json,zipfile
PATH='"'"'/home/admin/ISSUE76_STAGE_A_94326ff1f3eb.zip'"'"'
SIZE=57179504
DIGEST='"'"'258ce847ff8b3e4b2046a35c99ced9cf1b9011a523ea802a77e59c657cccca43'"'"'
ENTRY_SHA='"'"'94326ff1f3eb5a3d71cdd0cd7ab1846e0beca3dc5e11d4be34c9cc8d2d000f65'"'"'
MANIFEST_SHA='"'"'8660d85b3a378bfaf426cb7715ac9da34be2b4a08ada06271758174c3d419e81'"'"'
def need(v):
 if not v:raise RuntimeError('"'"'FIXED_STAGE_A_INPUT_HOLD'"'"')
def identity(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def unique(rows):
 out={}
 for k,v in rows:need(k not in out);out[k]=v
 return out
try:
 need(os.getuid()==0 and os.geteuid()==0 and os.uname().nodename.split('"'"'.'"'"')[0]=='"'"'iZd7oeikknn1z21sq6ji6zZ'"'"')
 admin=pwd.getpwnam('"'"'admin'"'"').pw_uid;need(admin>0)
 parent=os.open('"'"'/'"'"',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  for part in PATH.split('"'"'/'"'"')[1:-1]:
   child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);os.close(parent);parent=child
   s=os.fstat(parent);need(s.st_uid in (0,admin) and not s.st_mode&0o022)
  fd=os.open(PATH.split('"'"'/'"'"')[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
  try:
   before=os.fstat(fd);need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid in (0,admin) and not before.st_mode&0o022 and before.st_size==SIZE)
   chunks=[];count=0
   while True:
    b=os.read(fd,min(1048576,SIZE-count+1))
    if not b:break
    chunks.append(b);count+=len(b);need(count<=SIZE)
   body=b'"'"''"'"'.join(chunks);need(len(body)==SIZE and hashlib.sha256(body).hexdigest()==DIGEST)
   need(identity(before)==identity(os.fstat(fd))==identity(os.stat(PATH.split('"'"'/'"'"')[-1],dir_fd=parent,follow_symlinks=False)))
  finally:os.close(fd)
 finally:os.close(parent)
 with zipfile.ZipFile(io.BytesIO(body)) as archive:
  info=archive.infolist();need(len(info)==6 and len({x.filename for x in info})==6 and sum(x.file_size for x in info)<=58000000)
  need(all(not x.flag_bits&1 and (x.external_attr>>16)&0o170000==0o100000 for x in info))
  raw=archive.read('"'"'manifest.json'"'"');need(len(raw)<=16384 and hashlib.sha256(raw).hexdigest()==MANIFEST_SHA)
  m=json.loads(raw,object_pairs_hook=unique);need(raw==json.dumps(m,sort_keys=True,separators=('"'"','"'"','"'"':'"'"')).encode())
  need(type(m) is dict and set(m)=={'"'"'format'"'"','"'"'purpose'"'"','"'"'entry'"'"','"'"'payload'"'"'} and type(m['"'"'format'"'"']) is int and m['"'"'format'"'"']==1 and m['"'"'purpose'"'"']=='"'"'STAGE_A_FOUR_PUBLIC_INPUTS_NOT_AUTHORIZATION'"'"')
  names={'"'"'stage-a-entry.py'"'"','"'"'manifest.json'"'"'}|set(m['"'"'payload'"'"']);need(set(archive.namelist())==names)
  source=archive.read('"'"'stage-a-entry.py'"'"');need(hashlib.sha256(source).hexdigest()==ENTRY_SHA and m['"'"'entry'"'"']=={'"'"'bytes'"'"':len(source),'"'"'sha256'"'"':ENTRY_SHA})
  blobs={}
  for name,meta in m['"'"'payload'"'"'].items():
   b=archive.read(name);need(meta=={'"'"'bytes'"'"':len(b),'"'"'sha256'"'"':hashlib.sha256(b).hexdigest()});blobs[name]=b
 ns={'"'"'__name__'"'"':'"'"'verified_stage_a_entry'"'"'};exec(compile(source,'"'"'<verified-stage-a-entry>'"'"','"'"'exec'"'"'),ns)
 # Only Python-level completion output is captured, never the sudo OS stdin/stdout.
 # Production confirm uses the inherited controlling TTY, including select/read.
 import contextlib
 output=io.StringIO()
 with contextlib.redirect_stdout(output):result=ns['"'"'run'"'"'](blobs,MANIFEST_SHA)
 value=json.loads(output.getvalue(),object_pairs_hook=unique)
 expected={'"'"'state'"'"':'"'"'STAGE_A_ORIGINAL_CALLER_COMPLETED'"'"','"'"'image'"'"':'"'"'sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a'"'"','"'"'site_update'"'"':False,'"'"'private_data'"'"':False,'"'"'ocr_enabled'"'"':False,'"'"'servertrust'"'"':False}
 valid=type(result) is int and result==0 and value==expected and all(type(value[k]) is bool for k in ('"'"'site_update'"'"','"'"'private_data'"'"','"'"'ocr_enabled'"'"','"'"'servertrust'"'"'))
 if not valid:raise RuntimeError('"'"'COMPLETION_RECEIPT_INVALID'"'"')
 print(json.dumps({'"'"'schema'"'"':1,'"'"'state'"'"':'"'"'STAGE_A_RECEIPT_VALID_NOT_UPDATE'"'"','"'"'child_exit'"'"':0,'"'"'stage_a_result_valid'"'"':True,'"'"'completion'"'"':value,'"'"'servertrust'"'"':False},sort_keys=True),flush=True)
 result=0
except BaseException:
 print('"'"'{"schema":1,"state":"HOLD_STAGE_A_INPUT_CONTEXT_OR_COMPLETION","child_exit":2,"stage_a_result_valid":false,"servertrust":false}'"'"',flush=True);result=2
raise SystemExit(result)
'
  community_stage_a_inner=$?
  printf '{"schema":1,"record":"SUDO_CHILD_EXIT","child_exit":%s,"login_shell_preserved":true,"shell_exit_not_acceptance":true,"servertrust":false}\n' "$community_stage_a_inner"
  exit "$community_stage_a_inner"
); then
  :
else
  :
fi
