"""Candidate only: retained archive analysis/materials, no Node/SDK/live-tree execution.
Host Python3.6.8. Requires separate approval before running on the UK host.
"""
import hashlib,io,json,os,posixpath,pwd,re,resource,signal,stat,sys,tarfile,time,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
PINS={'p2_b5_three_files.py':'90684e11592552336663f1a3c53b70787af79e48ee3819c6e8a655d3f9936980','p2_b5_snapshot.py':'505fbcaca2edb0ce3d9cfc697008242dd2e270d71dd394beede82679b003bf85'}
FRONTIER_SHA='0ff682af0549837ffb7399fdd3964b37f6c2d817d518486ea2c591f30aff3977'
OUTPUT='p2-b5-retained-materials-v1-20261020'
MAX_SELECTED=16*1024*1024;MAX_SOURCE=2*1024*1024;MAX_FILES=2000;MAX_REPORT=2*1024*1024
NODE='home/xuanjun_dev/.openclaw/tools/node-v24.21.0/bin/node'
def need(ok,code):
 if not ok:raise ValueError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def support(name):
 raw=(HERE/name).read_bytes();need(len(raw)<=65536 and sha(raw)==PINS[name],'SUPPORT_SHA')
 m=types.ModuleType('b5_retained_'+name.replace('.','_'));m.__file__=str(HERE/name);exec(compile(raw,m.__file__,'exec'),m.__dict__);return m

def literal_refs(text):
 # Inventory only: neither regex nor a parser package's presence proves closure.
 return sorted(set(re.findall(r'(?:\bfrom\s*|\bimport\s*\(\s*|\bimport\s*|\brequire\s*\(\s*)[\x22\x27]([^\x22\x27\r\n]{1,1024})[\x22\x27]',text)))
def resolve_relative(parent,ref,available):
 if '?' in ref or '#' in ref or '\\' in ref:return None
 path=posixpath.normpath(posixpath.join(posixpath.dirname(parent),ref))
 if path.startswith('../') or path.startswith('/'):return None
 # Do not guess extension/index/exports resolution. Exact file literal only.
 return path if path in available else None

def analyze(rows,get,root,frontier,elf):
 available={n[len(root):]:row for n,row in rows.items() if n.startswith(root)}
 selected={};missing=set();unresolved=set();dynamic=[];queue=[];visited=set();bounded=[]
 def enqueue(n):
  if n not in available:missing.add(n)
  elif n not in visited and n not in queue:queue.append(n)
 seeds=['package.json','openclaw.mjs','dist/index.js','dist/loader-runtime-load-DpgEqnzx.mjs','dist/context-DyPstb2Q.mjs']+list(frontier)
 # All matching code entry candidates are reported as candidates, never aliases.
 auth_candidates=sorted(n for n in available if re.fullmatch(r'dist/[^/]*(?:server-methods|gateway|auth|request-rpc)[^/]*\.(?:mjs|js|cjs)',n))
 parsers=sorted(n for n in available if n.endswith(('/acorn/package.json','/@babel/parser/package.json')) or n in ('node_modules/acorn/package.json','node_modules/@babel/parser/package.json'))
 for n in seeds+auth_candidates+parsers:enqueue(n)
 while queue:
  n=queue.pop(0)
  if n in visited:continue
  if len(visited)>=MAX_FILES:bounded.append('MAX_FILES');break
  visited.add(n);row=available[n]
  if row['bytes']>MAX_SOURCE:bounded.append('SOURCE_SIZE:'+n);continue
  if sum(map(len,selected.values()))+row['bytes']>MAX_SELECTED:bounded.append('SELECTED_BYTES:'+n);continue
  raw=get(root+n);need(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'SELECTED_SOURCE_SHA');selected[n]=raw
  if n.endswith(('.js','.mjs','.cjs')):
   try:text=raw.decode('utf8')
   except UnicodeDecodeError:unresolved.add('UTF8:'+n);continue
   for ref in literal_refs(text):
    if ref.startswith('node:'):continue
    if ref.startswith('.'):
     target=resolve_relative(n,ref,available)
     if target:enqueue(target)
     else:unresolved.add('RELATIVE:'+n+':'+ref)
    else:unresolved.add('PACKAGE_RESOLUTION:'+n+':'+ref)
   # Conservative indicators, including false positives, are not silently resolved.
   for index,line in enumerate(text.splitlines(),1):
    if len(dynamic)<4000 and re.search(r'\b(?:import|require)\s*\(\s*(?![\s\x22\x27])|\b(?:readFile|readFileSync|createRequire|dlopen|new URL)\b',line):
     dynamic.append({'source':n,'line':index,'kind':'DYNAMIC_OR_RESOURCE_REQUIRES_AST_AND_RUNTIME_POLICY'})
     if len(dynamic)>=4000:bounded.append('DYNAMIC_INDICATOR_BOUND');break
  elif n.endswith('package.json'):
   for license_name in ('LICENSE','LICENSE.md','LICENSE.txt'):
    candidate=posixpath.join(posixpath.dirname(n),license_name)
    if candidate in available:enqueue(candidate)
   try:pkg=json.loads(raw.decode('utf8'))
   except (ValueError,UnicodeDecodeError):unresolved.add('PACKAGE_JSON:'+n);continue
   for field in ('main','module'):
    v=pkg.get(field)
    if isinstance(v,str):
     target=resolve_relative(n,'./'+v,available)
     if target:enqueue(target)
     else:unresolved.add('PACKAGE_ENTRY:'+n+':'+v)
   if pkg.get('exports'):unresolved.add('CONDITIONAL_EXPORTS:'+n)
   dependencies=dict(pkg.get('dependencies',{}));dependencies.update(pkg.get('optionalDependencies',{}))
   for dep,version in sorted(dependencies.items()):
    # Location can vary (pnpm/symlinks); enumerate retained manifests, not host search paths.
    matches=[p for p in available if p.endswith('/node_modules/'+dep+'/package.json') or p=='node_modules/'+dep+'/package.json']
    if not matches:unresolved.add('PACKAGE_MISSING:'+dep+'@'+str(version))
    for target in matches:enqueue(target)
  elif not n.endswith(('LICENSE','LICENSE.md','LICENSE.txt')):unresolved.add('NATIVE_OR_RESOURCE_REQUIRES_POLICY:'+n)
 report={'scope':'ISOLATED_TEST_ONLY_RETAINED_MATERIALS','dependency_closure':'UNKNOWN','analysis':'BOUNDED_LEXICAL_NOT_AST_OR_TRANSITIVE_CLOSURE','first_frontier_count':len(frontier),'first_frontier_missing':sorted(set(frontier)-set(available)),'missing_members':sorted(missing),'unresolved':sorted(unresolved),'dynamic_resource_indicators':dynamic,'bounds_reached':bounded,'unprocessed_count':len(queue),'auth_entry_candidates':auth_candidates,'parser_manifests':parsers,'parser_bindings':{n:{'sha256':sha(selected[n]),'version':json.loads(selected[n].decode('utf8')).get('version'),'execution':'NOT_EXECUTED'} for n in parsers if n in selected},'selected':{n:{'bytes':len(b),'sha256':sha(b),'source_member':root+n} for n,b in sorted(selected.items())},'node':{'state':'ABSENT_FROM_RETAINED_MANIFEST','path':'/'+NODE},'isolation_image':{'known_python_image_id':'sha256:5341f193a5741b64f2acc63a99dc95910289fcc39ff17dacff373a50e233724d','source_receipt':'PR17#6281525690','inherited_evidence':'Python3.11.2 UID/GID1002:1002 only','node_compatibility':'UNKNOWN','required':['compatible Node execution proof','UID1002 read-only mount map','ELF interpreter/shared-library resolution']},'real_cli_authentication':{'state':'UNBOUND','required':['exact openclaw.mjs and compiled CLI imports','real auth dispatcher and active plugin registry relationship','isolated config schema and test-auth transport','bounded invocation and release/restart evidence']},'sdk':'NOT_EXECUTED','authenticated_dispatch':'NOT_EXECUTED','cp11':'NOT_EXECUTED'}
 if NODE in rows:
  node=rows[NODE];report['node'].update(state='RETAINED_BYTES_BOUND_NOT_EXECUTED',bytes=node['bytes'],sha256=node['sha256'])
  try:
   need(node['bytes']<=128*1024*1024,'NODE_BOUND');raw=get(NODE);need(len(raw)==node['bytes'] and sha(raw)==node['sha256'],'NODE_SHA');deps=elf(raw);report['node']['elf']=deps
   report['node']['retained_library_candidates']={name:[{'path':'/'+p,'sha256':v['sha256'],'bytes':v['bytes']} for p,v in rows.items() if posixpath.basename(p)==name] for name in deps['needed']}
   interp=deps.get('interpreter');report['node']['interpreter_record']=rows.get(interp.lstrip('/')) if interp else None
   report['node']['resolution']='UNKNOWN_NO_LOADER_SEARCH_OR_IMAGE_PROOF'
  except Exception as e:report['node']['elf_error']=str(e) if isinstance(e,ValueError) else type(e).__name__
 return report,selected

def write_new(fd,name,raw):
 need(len(raw)<=MAX_SELECTED+2*1024*1024 if name.endswith('.tar') else len(raw)<=MAX_REPORT,'OUTPUT_BOUND')
 f=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
 with os.fdopen(f,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
 os.fsync(fd)
def run(a,m,out,reader,frontier,elf):
 result={'state':'HOLD','stage':'FULL_INPUT_VERIFY','dependency_closure':'UNKNOWN','sdk':'NOT_EXECUTED'}
 try:
  _,verified=reader.select_files(a,m,reader.PINS);result['stage']='RETAINED_ANALYSIS';rows=reader.manifest_map(m,reader.PINS)
  os.lseek(a,0,os.SEEK_SET)
  with os.fdopen(os.dup(a),'rb') as stream:
   with tarfile.open(fileobj=stream,mode='r:') as archive:
    members={v.name:v for v in archive.getmembers()}
    need(set(members)==set(rows),'SECOND_PASS_MEMBER_SET')
    def get(n):
     member=members[n];need(member.isfile() and member.size==rows[n]['bytes'],'SECOND_PASS_TYPE');need(member.size<=128*1024*1024,'READ_BOUND')
     f=archive.extractfile(member)
     try:return f.read(member.size+1)
     finally:f.close()
    report,selected=analyze(rows,get,reader.ROOT,frontier,elf)
  report['source_validation']=verified;report['source_tar_sha256']=reader.PINS['tar_sha256'];report['source_manifest_sha256']=reader.PINS['manifest_sha256']
  report_raw=json.dumps(report,sort_keys=True).encode();need(len(report_raw)<=MAX_REPORT,'REPORT_BOUND')
  buf=io.BytesIO()
  with tarfile.open(fileobj=buf,mode='w',format=tarfile.PAX_FORMAT) as tar:
   for n,b in sorted(selected.items()):
    info=tarfile.TarInfo(n);info.size=len(b);info.mode=0o600;info.mtime=0;tar.addfile(info,io.BytesIO(b))
  packet=buf.getvalue();result['stage']='WRITE_OUTPUTS';write_new(out,'materials.tar',packet);write_new(out,'report.json',report_raw)
  result.update(state='MATERIALS_WRITTEN_AWAIT_PARENT',stage='OUTPUTS_WRITTEN',materials_bytes=len(packet),materials_sha256=sha(packet),report_sha256=sha(report_raw),selected_bytes=sum(map(len,selected.values())))
  code=0
 except Exception as e:result['error']=str(e) if isinstance(e,(ValueError,reader.Hold)) else type(e).__name__;result['error_type']=type(e).__name__;result['errno']=getattr(e,'errno',None);code=2
 write_new(out,'child-receipt.json',json.dumps(result,sort_keys=True).encode());return code

def verify_outputs(out,uid):
 records={}
 for name,limit in (('child-receipt.json',MAX_REPORT),('report.json',MAX_REPORT),('materials.tar',MAX_SELECTED+2*1024*1024)):
  fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=out)
  try:
   before=os.fstat(fd);need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==uid and stat.S_IMODE(before.st_mode)==0o600 and before.st_size<=limit,'OUTPUT_IDENTITY')
   h=hashlib.sha256();chunks=[];left=before.st_size
   while left:
    b=os.read(fd,min(65536,left));need(b,'OUTPUT_TRUNCATED');left-=len(b);h.update(b)
    if name!='materials.tar':chunks.append(b)
   after=os.fstat(fd);need(not os.read(fd,1) and (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'OUTPUT_CHANGED')
   records[name]={'bytes':before.st_size,'sha256':h.hexdigest()}
   if name!='materials.tar':records[name]['json']=json.loads(b''.join(chunks).decode('utf8'))
  finally:os.close(fd)
 child=records['child-receipt.json']['json'];report=records['report.json']['json']
 need(child.get('state')=='MATERIALS_WRITTEN_AWAIT_PARENT' and child.get('materials_sha256')==records['materials.tar']['sha256'] and child.get('materials_bytes')==records['materials.tar']['bytes'] and child.get('report_sha256')==records['report.json']['sha256'],'OUTPUT_RECEIPT_BINDING')
 need(report.get('dependency_closure')=='UNKNOWN' and report.get('sdk')=='NOT_EXECUTED' and report.get('cp11')=='NOT_EXECUTED','OUTPUT_SCOPE')
 return {n:{'bytes':r['bytes'],'sha256':r['sha256']} for n,r in records.items()}

def main():
 need(os.getuid()==os.geteuid()==0 and os.uname().nodename.split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ','HOST_ROOT')
 need(sys.version_info[:3]==(3,6,8),'HOST_PYTHON368')
 reader=support('p2_b5_three_files.py');snapshot=support('p2_b5_snapshot.py')
 raw=(HERE.parent/'evidence/p2-b5-20261020/first-frontier.json').read_bytes();need(len(raw)<=65536 and sha(raw)==FRONTIER_SHA,'FRONTIER_SHA');frontier=json.loads(raw.decode())['members'];need(len(frontier)==156,'FRONTIER_COUNT')
 admin=pwd.getpwnam('admin');need(admin.pw_uid not in (0,1002),'ADMIN_IDENTITY');os.umask(0o077)
 a=reader.PinnedFile(reader.SOURCE+'/source-tree.tar.pending',(0,1002));m=None;home=None;out=None
 try:
  m=reader.PinnedFile(reader.SOURCE+'/manifest.json',(0,1002));home=reader.private_home(admin.pw_dir,admin.pw_uid)
  os.mkdir(OUTPUT,0o700,dir_fd=home);out=os.open(OUTPUT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=home);os.fchown(out,admin.pw_uid,admin.pw_gid);os.fsync(home)
  pid=os.fork()
  if pid==0:
   try:
    os.setsid()
    for fd in a.parents+m.parents+[home]:os.close(fd)
    os.setgroups([]);os.setgid(admin.pw_gid);os.setuid(admin.pw_uid)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024));resource.setrlimit(resource.RLIMIT_CPU,(180,180));resource.setrlimit(resource.RLIMIT_FSIZE,(20*1024*1024,20*1024*1024));resource.setrlimit(resource.RLIMIT_NOFILE,(128,128))
    def timeout(s,f):raise ValueError('WALL_TIME_BOUND')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(240)
    os._exit(run(a.fd,m.fd,out,reader,frontier,snapshot.elf_needs))
   except BaseException:os._exit(2)
  deadline=time.monotonic()+270;status=None
  while status is None:
   p,s=os.waitpid(pid,os.WNOHANG)
   if p:status=s;break
   if time.monotonic()>=deadline:os.killpg(pid,signal.SIGKILL);_,status=os.waitpid(pid,0);break
   time.sleep(.1)
  result={'state':'HOLD','child_wait_status':status,'dependency_closure':'UNKNOWN','sdk':'NOT_EXECUTED','cp11':'NOT_EXECUTED','output':admin.pw_dir+'/'+OUTPUT}
  try:
   a.check();m.check();result['original_inputs']='UNCHANGED'
   if status==0:result['outputs']=verify_outputs(out,admin.pw_uid);result['state']='MATERIALS_ONLY_NOT_CLOSURE'
   else:result['state']='HOLD_RETAIN_OUTPUT'
  except Exception as e:result['state']='HOLD_INPUT_OR_OUTPUT_UNKNOWN';result['error']=str(e) if isinstance(e,(ValueError,reader.Hold)) else type(e).__name__
  # Parent writes as admin too; never makes old output or source readable.
  os.setgroups([]);os.setgid(admin.pw_gid);os.setuid(admin.pw_uid)
  write_new(out,'host-result.json',json.dumps(result,sort_keys=True).encode());print(json.dumps(result,sort_keys=True));return 0 if result['state']=='MATERIALS_ONLY_NOT_CLOSURE' else 2
 finally:
  a.close()
  if m:m.close()
  for fd in (home,out):
   if fd is not None:os.close(fd)
if __name__=='__main__':
 try:sys.exit(main())
 except Exception as e:print(json.dumps({'state':'HOLD','error':str(e) if isinstance(e,ValueError) or re.fullmatch('[A-Z][A-Z0-9_]{0,160}',str(e)) else type(e).__name__,'error_type':type(e).__name__,'errno':getattr(e,'errno',None),'sdk':'NOT_EXECUTED'}));sys.exit(2)
