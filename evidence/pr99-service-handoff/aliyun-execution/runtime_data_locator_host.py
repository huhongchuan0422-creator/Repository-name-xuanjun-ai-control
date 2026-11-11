"""Fixed metadata-only locator. No database opens, source imports or effects."""
import datetime
import hashlib
import json
import os
import re
import stat
import subprocess
import urllib.parse

SCOPES={
 'iZ6wee8q9z4t03hvqumwfhZ':(
 ('secure-secrets-portal.service','TRADING_DATABASE_URL','URL'),
 ('xuanjun-wecom-customer-contact.service','TRADING_DATABASE_URL','URL'),
 ('xuanjun-wecom-customer-service.service','TRADING_DATABASE_URL','URL')),
 'iZvt5t8tlrm8oiZ':(
 ('windows-interaction-http.service','WINDOWS_INTERACTION_STATE_DB','PATH'),
 ('provider-neutral-domestic-bridge.service','DOMESTIC_BRIDGE_CUSTOMER_STATE','PATH')),
}

def bounded_read(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        raw=b''
        while len(raw)<=limit:
            chunk=os.read(fd,min(65536,limit+1-len(raw)))
            if not chunk:break
            raw+=chunk
        if len(raw)>limit:raise ValueError('INPUT_BOUND')
        return raw
    finally:os.close(fd)

def start_ticks(pid):
    raw=bounded_read('/proc/'+str(pid)+'/stat',8192)
    return int(raw[raw.rfind(b')')+2:].split()[19])

def locate(value,kind,cwd):
    if type(value)is not str or not value or '\x00' in value:return 'UNRESOLVED',None
    if kind=='URL':
        m=re.match(r'^sqlite(?:\+pysqlite)?:///',value)
        if not m:return 'NON_SQLITE_OR_UNSUPPORTED_URL',None
        value=value[m.end():]
        if '?' in value or '#' in value or value.startswith('file:'):return 'URI_OPTIONS_UNRESOLVED',None
        value=urllib.parse.unquote(value)
        if not value or value==':memory:':return 'NON_FILE_SQLITE',None
    if not value.startswith('/'):
        if not cwd.startswith('/'):return 'RELATIVE_CWD_UNRESOLVED',None
        value=os.path.join(cwd,value)
    if '\x00' in value:return 'UNRESOLVED',None
    return 'FILE_CANDIDATE',os.path.normpath(value)

def descriptor(path):
    try:s=os.lstat(path)
    except FileNotFoundError:return {'state':'MISSING'}
    except OSError:return {'state':'METADATA_UNREADABLE'}
    if stat.S_ISLNK(s.st_mode):return {'state':'SYMLINK_UNRESOLVED'}
    if not stat.S_ISREG(s.st_mode):return {'state':'NOT_REGULAR'}
    return {'state':'REGULAR_METADATA_CANDIDATE','device':s.st_dev,'inode':s.st_ino,'uid':s.st_uid,'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode),'bytes':s.st_size,'nlink':s.st_nlink}

def observe_unit(unit,key,kind):
    row={'unit':unit,'environment_key':key,'status':'UNKNOWN','pid':0,'start_ticks':0,'data':[]}
    try:
        result=subprocess.run(['/bin/systemctl','show',unit,'--property=LoadState,ActiveState,MainPID'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=6,check=False)
        if result.returncode or len(result.stdout)>8192:row['status']='UNIT_QUERY_UNKNOWN';return row
        fields=dict(x.split('=',1) for x in result.stdout.decode().splitlines() if '=' in x)
        if fields.get('LoadState')!='loaded' or fields.get('ActiveState')!='active':row['status']='UNIT_NOT_ACTIVE';return row
        pid=int(fields['MainPID']);assert pid>0
        ticks=start_ticks(pid);row.update(pid=pid,start_ticks=ticks)
        if os.readlink('/proc/'+str(pid)+'/root')!='/':row['status']='NONHOST_PROCESS_ROOT_UNKNOWN';return row
        cwd=os.readlink('/proc/'+str(pid)+'/cwd')
        environment=bounded_read('/proc/'+str(pid)+'/environ',1048576)
        values=[x[len(key)+1:] for x in environment.split(b'\0') if x.startswith(key.encode()+b'=')]
        if not values:row['status']='INITIAL_ENVIRONMENT_KEY_NOT_SET_UNKNOWN';return row
        if len(values)!=1:row['status']='DUPLICATE_ENVIRONMENT_KEY_UNKNOWN';return row
        value=values[0].decode('utf-8','strict')
        status,path=locate(value,kind,cwd);row['status']=status
        if path is not None:
            row['data']=[{'part':part,'metadata':descriptor(path+suffix)} for part,suffix in (('MAIN',''),('WAL','-wal'),('SHM','-shm'))]
        # Process/active service binding must still be the same after private input use.
        current=subprocess.run(['/bin/systemctl','show',unit,'--property=MainPID','--value'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=6,check=False)
        if current.returncode or current.stdout.strip()!=str(pid).encode() or start_ticks(pid)!=ticks:
            row['data']=[];row['status']='PID_BINDING_CHANGED_UNKNOWN'
        return row
    except Exception:
        row['data']=[];row['status']='PRIVATE_INPUT_OR_IDENTITY_UNKNOWN';return row

def observe(expected,nonce):
    assert os.geteuid()==0 and os.uname().nodename==expected and expected in SCOPES
    return {'scope':'PR99_INITIAL_PROCESS_ENV_DATA_METADATA_NOT_AUTHORITY','hostname':expected,'nonce':nonce,
        'observed_at':datetime.datetime.utcnow().isoformat()+'Z','units':[observe_unit(*x) for x in SCOPES[expected]],
        'private_environment_values_disclosed':False,'database_opened':False,'business_source_imports':0,
        'service_actions':0,'business_requests':0,'authoritative_writer':'UNKNOWN','enforced_fence':'UNKNOWN',
        'limitations':['INITIAL_ENV_ONLY_NOT_RUNTIME_OR_DEFAULT_CONFIG','NO_DATABASE_FORMAT_OR_AUTHORITY_PROOF','ANCESTOR_LINKS_NOT_ADMITTED_PATHGUARD','IDLE_OTHER_AND_SCHEDULED_WRITERS_NOT_PROVEN','NO_FENCE_DRAIN_OR_STOP']}

if __name__=='__main__':
    print(json.dumps(observe(EXPECTED,NONCE),sort_keys=True),flush=True)
