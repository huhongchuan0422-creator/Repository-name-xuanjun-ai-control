"""Normal transport repair after a terminal URL error; no production activation."""
import ast
import hashlib
from pathlib import Path
base=Path(__file__).parent
source=(base.parent/'pr99-dev/owner-start/owner_production_start.py').read_bytes()
old=(base/'stage_owner_start_probe.py').read_text()
host=(base/'stage_owner_start_host.py').read_text()
host=host[:host.index('\ndef observe(')]
chunks=[source[i:i+11500] for i in range(0,len(source),11500)]
prefixes=[hashlib.sha256(source[:i*11500]).hexdigest() for i in range(4)]
host+='''
TRANSFER=PARENT/'owner_production_start.py.transfer-v1'

def receive(directory,index,chunk):
    need(type(index)is int and 0<=index<3,'PART_INDEX')
    need(hashlib.sha256(chunk).hexdigest()==CHUNK_HASHES[index],'PART_SOURCE_DRIFT')
    s=directory.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.geteuid() and not s.st_mode&0o022,'CODE_DIRECTORY_IDENTITY')
    path=directory/TRANSFER.name
    flags=os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC
    fd=os.open(path,flags|(os.O_CREAT|os.O_EXCL if index==0 else 0),0o600)
    try:
        s=os.fstat(fd)
        need(stat.S_ISREG(s.st_mode) and s.st_uid==os.geteuid() and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,'PART_FILE_IDENTITY')
        prior=os.pread(fd,34426,0)
        need(len(prior)==index*11500 and hashlib.sha256(prior).hexdigest()==PREFIX_HASHES[index],'PART_PRIOR_CONFLICT_PRESERVE')
        need(os.lseek(fd,0,os.SEEK_END)==len(prior),'PART_OFFSET')
        off=0
        while off<len(chunk):
            size=os.write(fd,chunk[off:]);need(size>0,'PARTIAL_CODE_PRESERVE');off+=size
        os.fsync(fd)
        raw=os.pread(fd,34426,0)
        need(raw==prior+chunk,'PART_WRITE_DRIFT_PRESERVE')
    finally:os.close(fd)
    if index==2:
        need(len(raw)==34425 and hashlib.sha256(raw).hexdigest()==SOURCE_SHA,'FINAL_SOURCE_DRIFT')
        stage_file(directory,raw)
        ns={'__name__':'installed_owner_start_definitions','__file__':str(directory/'owner_production_start.py')}
        exec(compile(raw,ns['__file__'],'exec'),ns)
        need(len(ns['units']('xuanjun-s07'))==3,'FINAL_DEFINITION_BINDING')
    return len(raw),hashlib.sha256(raw).hexdigest()

def observe(expected,nonce):
    need(os.geteuid()==0 and os.uname().nodename==expected=='iZvt5t8tlrm8oiZ','FIXED_DOMESTIC_ROOT')
    before=states()
    for parent in reversed(PARENT.parents):
        s=parent.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022,'CODE_PARENT_IDENTITY')
    if not os.path.lexists(PARENT):PARENT.mkdir(mode=0o700)
    size,digest=receive(PARENT,PART,CHUNK)
    need(before==states(),'PROTECTED_STATE_CHANGED_NO_FURTHER_ACTION')
    return {'scope':'PR99_INLINE_OWNER_HELPER_ONLY','hostname':expected,'nonce':nonce,'part':PART,
      'prefix_bytes':size,'prefix_sha256':digest,'final_installed':PART==2,'source_sha256':SOURCE_SHA,
      'protected_state_unchanged':True,'service_actions':0,'production_started':False,'route_changed':False}

if __name__=='__main__':
    try:print(json.dumps(observe(EXPECTED,NONCE),sort_keys=True),flush=True)
    except BaseException as error:
        import re
        code=str(error)
        print(json.dumps({'status':'OWNER_INLINE_STAGE_HOLD','error_type':type(error).__name__,
          'code':code if re.fullmatch('[A-Z0-9_]{1,160}',code) else 'PRIVATE_DETAIL_WITHHELD','retry_allowed':False}),flush=True)
        raise SystemExit(2)
'''
host='CHUNK_HASHES='+repr([hashlib.sha256(c).hexdigest() for c in chunks])+'\nPREFIX_HASHES='+repr(prefixes)+'\n'+host
shell='''def shell_for(expected,nonce):
    program='EXPECTED='+repr(expected)+'\\nNONCE='+repr(nonce)+'\\nPART='+repr(PART)+'\\nCHUNK='+repr(CHUNKS[PART])+'\\n'+HOST_PROGRAM
    payload=base64.b64encode(zlib.compress(program.encode(),9)).decode()
    digest=hashlib.sha256(program.encode()).hexdigest()
    bootstrap="import base64,zlib,hashlib; b=zlib.decompress(base64.b64decode("+repr(payload)+")); assert hashlib.sha256(b).hexdigest()=="+repr(digest)+"; exec(compile(b,'<pr99-inert-owner-helper>','exec'))"
    shell="#!/bin/sh\\nset -eu\\n/usr/bin/python3.11 -I -B - <<'PR99_INLINE'\\n"+bootstrap+"\\nPR99_INLINE\\n"
    if len(shell.encode())>11000:raise Hold('COMMAND_LENGTH')
    return shell
'''
contract='''def validate_observation(d,expected,nonce):
    def need(ok):
        if not ok:raise ValueError('INLINE_STAGE_CONTRACT')
    need(type(d)is dict and set(d)==set('scope hostname nonce part prefix_bytes prefix_sha256 final_installed source_sha256 protected_state_unchanged service_actions production_started route_changed'.split()))
    need(d['scope']=='PR99_INLINE_OWNER_HELPER_ONLY' and d['hostname']==expected and d['nonce']==nonce)
    need(type(d['part'])is int and d['part']==PART)
    raw=b''.join(CHUNKS[:PART+1])
    need(type(d['prefix_bytes'])is int and d['prefix_bytes']==len(raw) and d['prefix_sha256']==hashlib.sha256(raw).hexdigest())
    need(type(d['final_installed'])is bool and d['final_installed']==(PART==2))
    need(d['source_sha256']==hashlib.sha256(TEST_START_SOURCE.encode()).hexdigest())
    need(d['protected_state_unchanged']is True and d['production_started']is d['route_changed']is False)
    need(type(d['service_actions'])is int and d['service_actions']==0)
    return d
'''
test='''def self_test():
    import tempfile
    global PART
    n={'__name__':'inline_fixture'};exec(compile(HOST_PROGRAM,'inline_fixture','exec'),n)
    with tempfile.TemporaryDirectory() as directory:
        p=Path(directory)
        try:n['receive'](p,1,CHUNKS[1])
        except FileNotFoundError:pass
        else:raise AssertionError('OUT_OF_ORDER_ACCEPTED')
        for PART in range(3):
            size,digest=n['receive'](p,PART,CHUNKS[PART])
            assert size==len(b''.join(CHUNKS[:PART+1]))
            assert len(shell_for(HOSTS[0][4],'a'*32).encode())<11000
        assert (p/'owner_production_start.py').read_bytes()==TEST_START_SOURCE.encode()
        before=(p/n['TRANSFER'].name).read_bytes()
        for i in range(3):
            try:n['receive'](p,i,CHUNKS[i])
            except (RuntimeError,FileExistsError):pass
            else:raise AssertionError('PART_REPLAY_ACCEPTED')
        assert (p/n['TRANSFER'].name).read_bytes()==before
    print('PR99_INLINE_EXACT_SOURCE_ORDER_CONFLICT_NO_ACTIVATION_PASS_NO_CLOUD',flush=True)
'''
changes=[]
for node in ast.parse(old).body:
    if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='HOST_PROGRAM':
        changes.append((node.lineno,node.end_lineno,'PART=0\nCHUNKS='+repr(chunks)+'\nHOST_PROGRAM='+repr(host)))
    if isinstance(node,ast.FunctionDef) and node.name in ('shell_for','validate_observation','self_test'):
        changes.append((node.lineno,node.end_lineno,{'shell_for':shell,'validate_observation':contract,'self_test':test}[node.name]))
lines=old.splitlines()
for begin,end,value in reversed(changes):lines[begin-1:end]=value.splitlines()
program='\n'.join(lines)+'\n'
program=program.replace("claim=Path('pr99-stage-owner-start-'+name+'.once')","claim=Path('pr99-inline-owner-start-'+name+'-'+str(PART)+'.once')")
program=program.replace('pr99-stage-owner-start-','pr99-inline-owner-start-')
# Three strictly sequential independent native calls; any unknown/failure stops later parts.
program=program.replace('def probe_current(host,master):','def probe_part(host,master):')
start=program.index('\ndef self_test():')
wrapper='''
def probe_current(host,master):
    global PART
    rows=[]
    for PART in range(3):
        row=probe_part(host,master);row['part']=PART;rows.append(row)
        if row.get('status')!='OWNER_START_HELPER_STAGED_NOT_STARTED':break
    return {'host':host[0],'parts':rows,'all_parts_complete':len(rows)==3 and all(r.get('status')=='OWNER_START_HELPER_STAGED_NOT_STARTED' for r in rows),
      'production_started':False,'writer_acquired':False,'route_changed':False}
'''
program=program[:start]+wrapper+program[start:]
# Existing main checks host status; adapt to the explicit three-part result.
program=program.replace("all(r['status']=='OWNER_START_HELPER_STAGED_NOT_STARTED' for r in rows)","all(r['all_parts_complete'] for r in rows)")
program=program.replace('PR99_OWNER_STAGE_', 'PR99_OWNER_INLINE_')
(base/'inline_owner_stage_probe.py').write_text(program)
(base/'inline_owner_stage_host.py').write_text(host)
workflow=(base/'pr99-stage-owner-start.yml').read_text()
a='\n'.join('          '+s for s in old.rstrip('\n').split('\n'))
b='\n'.join('          '+s for s in program.rstrip('\n').split('\n'))
assert workflow.count(a)==2
workflow=workflow.replace(a,b).replace('pr99-stage-owner-start-','pr99-inline-owner-start-').replace('pr99-stage-owner-start-v1','pr99-inline-owner-start-v1')
workflow=workflow.replace('PR99 Owner start helper code staging','PR99 pinned inline inert Owner helper staging').replace('stage-owner-start:', 'inline-owner-start:')
(base/'pr99-inline-owner-start.yml').write_text(workflow)
compile(program,'inline_owner_stage_probe','exec')
print('PR99_INLINE_STAGE_BUILD_COMPLETE')
