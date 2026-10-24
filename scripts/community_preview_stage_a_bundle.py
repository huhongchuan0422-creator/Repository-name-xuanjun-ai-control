"""Offline stage A single four-input package; no transport/installation."""
import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path
from scripts import community_preview_stage_a as stage
ROOT=Path(__file__).resolve().parents[1]

def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()

def outer_script(filename,size,digest,entry_sha,manifest_sha):
    # Complete conditional subshell: no PHASE/PERMIT_SHA or exit in login shell.
    text=r'''# REVIEW CANDIDATE ONLY. Run only after root review and Owner's exact stage-A approval.
if (
  set +e
  community_stage_a_output="$(
  /usr/bin/sudo -n /usr/bin/python3 -I -B -S - <<'STAGE_A'
import os,stat,pwd,hashlib,io,json,zipfile
PATH='/home/admin/FILENAME'
SIZE=ARCHIVE_BYTES
DIGEST='ARCHIVE_DIGEST'
ENTRY_SHA='ENTRY_DIGEST'
MANIFEST_SHA='MANIFEST_DIGEST'
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
  )"
  community_stage_a_inner=$?
  printf '%s\n' "$community_stage_a_output"
  /usr/bin/python3 -I -B -S - "$community_stage_a_inner" "$community_stage_a_output" <<'RESULT'
import json,sys
code=int(sys.argv[1]);valid=False;child_state='UNVERIFIED'
try:
 def unique(rows):
  value={}
  for k,v in rows:
   if k in value:raise ValueError()
   value[k]=v
  return value
 value=json.loads(sys.argv[2],object_pairs_hook=unique)
 expected={'state':'STAGE_A_ORIGINAL_CALLER_COMPLETED','image':'sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a','site_update':False,'private_data':False,'ocr_enabled':False,'servertrust':False}
 valid=code==0 and value==expected and all(type(value[k]) is bool for k in ('site_update','private_data','ocr_enabled','servertrust'))
 if type(value) is dict and value.get('state') in ('STAGE_A_ORIGINAL_CALLER_COMPLETED','HOLD_STAGE_A_PRESERVE_NO_RETRY','HOLD_STAGE_A_INPUT_OR_CONTEXT'):child_state=value['state']
except Exception:pass
state='STAGE_A_RECEIPT_VALID_NOT_UPDATE' if valid else ('HOLD_CHILD_NONZERO' if code else 'HOLD_COMPLETION_RECEIPT_INVALID')
print(json.dumps({'schema':1,'child_exit':code,'child_state':child_state,'state':state,'stage_a_result_valid':valid,'login_shell_preserved':True,'shell_exit_not_acceptance':True,'servertrust':False},sort_keys=True))
RESULT
  # Root's real child status is in the structured record above. This subshell
  # may fail without exiting the interactive parent; shell $? is NOT acceptance.
  exit "$community_stage_a_inner"
); then
  :
else
  :
fi
'''
    return (text.replace('FILENAME',filename).replace('ARCHIVE_BYTES',str(size)).replace('ARCHIVE_DIGEST',digest)
        .replace('ENTRY_DIGEST',entry_sha).replace('MANIFEST_DIGEST',manifest_sha)).encode()

def build(image_file):
    # Only already reviewed original artifact bytes; never downloads a signedURL.
    blobs={name:(Path(image_file).read_bytes() if name=='artifact12546452389.zip'
        else (ROOT/('scripts/'+name if name.endswith('.py') else 'deploy/community-preview/'+name)).read_bytes())
        for name in stage.PAYLOAD}
    stage.verify_payload(blobs)
    entry=(ROOT/'scripts/community_preview_stage_a.py').read_bytes()
    manifest=canonical({'format':1,'purpose':'STAGE_A_FOUR_PUBLIC_INPUTS_NOT_AUTHORIZATION',
        'entry':{'bytes':len(entry),'sha256':sha(entry)},
        'payload':{p:{'bytes':len(b),'sha256':sha(b)} for p,b in sorted(blobs.items())}})
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_STORED) as archive:
        for p,b in sorted(dict(blobs,**{'stage-a-entry.py':entry,'manifest.json':manifest}).items()):
            info=zipfile.ZipInfo(p,(2026,10,24,0,0,0));info.create_system=3;info.external_attr=0o100600<<16
            archive.writestr(info,b)
    raw=buffer.getvalue();filename='ISSUE76_STAGE_A_'+sha(entry)[:12]+'.zip'
    command=outer_script(filename,len(raw),sha(raw),sha(entry),sha(manifest))
    report={'format':1,'package_filename':filename,'package_bytes':len(raw),'package_sha256':sha(raw),
        'destination':'/home/admin/'+filename,'manifest_sha256':sha(manifest),'entry_sha256':sha(entry),
        'scope_sha256':stage.StageA(blobs,sha(manifest)).scope,
        'outer_bytes':len(command),'outer_sha256':sha(command),'payload':json.loads(manifest)['payload'],
        'site_uploaded':False,'site_executed':False,'servertrust':False,'requires_original_owner_sudo_tty':True}
    return filename,raw,command,canonical(report)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--image-input',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();name,raw,command,report=build(args.image_input)
    target=Path(args.output);target.mkdir(exist_ok=False)
    (target/name).write_bytes(raw);(target/'stage-a-owner-call.sh').write_bytes(command);(target/'stage-a-delivery.json').write_bytes(report)
    print(report.decode())
