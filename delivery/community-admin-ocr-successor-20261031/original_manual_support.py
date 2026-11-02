#!/usr/bin/env python3
"""Owner UK TTY-only manual configuration. Python3.6 standard library.
preflight/query are read-only; apply/recover require exact live TTY confirmation.
No credentials in argv/env/output. Uses existing image, locks and container only.
"""
import argparse,fcntl,hashlib,json,os,re,secrets,stat,subprocess,sys,time
from pathlib import Path

HOST='iZd7oeikknn1z21sq6ji6zZ'
BASE='/var/lib/xuanjun-community-preview'
HOST_FILE=BASE+'/config/host.json'
TARGET=BASE+'/config/wechat-provider-reader.json'  # NEW file, not alleged existing source.
JOURNAL='/opt/xuanjun-community-preview/update-journal'
GLOBAL_LOCK=JOURNAL+'/community-update.lock'
NAME='xuanjun-community-preview'
DOCKER=['/usr/bin/docker','--host','unix:///var/run/docker.sock']
ROOT_UID=0
UID=10001
CONFIG_GID=None  # Bound from exact existing host stat in the confirmed plan.
PUBLIC={'sp_mchid':'1118392863','merchant_serial':'7DF440569E569DCC23FDE45870609105735B9285','public_key_id':'PUB_KEY_ID_0111183928632026101700292236001001'}
PUBLIC_SHA='32caeb3710b6c7708d13fb0e56093e48a53404fe48aebc805977c7f084f56e05'
CERT_SHA='fbc02b5b19f6dc7c9d44584b3bca69f6cfb8a5eb65b29402819b6db55cabcf40'
SPKI_SHA='28659fe395a1558e1c59293efab4f550c54572e24fa93551198b48e4aebaf61c'
SOURCE_PINS_SHA='7dee21ff91b2c52d7a1ffdf3e740ade7eec005b92aed2f4c500291869899d098'
HERE=Path(__file__).resolve().parent

def canon(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def need(ok):
    if not ok:raise ValueError('HOLD')
def ident(s):return {k:getattr(s,k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')}
def parent(path,owner):
    need(type(path)is str and str(Path(path))==path and path.startswith('/') and '..'not in Path(path).parts)
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for name in Path(path).parts[1:-1]:
            child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
        s=os.fstat(fd);need(s.st_uid==owner and not s.st_mode&0o077)
        return fd
    except BaseException:os.close(fd);raise

def metadata(path,owner):
    p=parent(path,owner)
    try:
        s=os.stat(Path(path).name,dir_fd=p,follow_symlinks=False)
        need(stat.S_ISREG(s.st_mode) and s.st_uid==owner and not s.st_mode&0o077 and s.st_nlink==1)
        return ident(s)
    finally:os.close(p)

def read(path,owner,limit=65536):
    p=parent(path,owner)
    try:
        fd=os.open(Path(path).name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=p)
        try:
            s=os.fstat(fd);need(stat.S_ISREG(s.st_mode) and s.st_uid==owner and not s.st_mode&0o077 and s.st_nlink==1 and 0<s.st_size<=limit)
            body=os.read(fd,limit+1)
            need(len(body)==s.st_size and ident(s)==ident(os.fstat(fd))==ident(os.stat(Path(path).name,dir_fd=p,follow_symlinks=False)))
            return body
        finally:os.close(fd)
    finally:os.close(p)

def parse(raw):
    def unique(pairs):
        out={}
        for key,value in pairs:need(key not in out);out[key]=value
        return out
    def invalid(value):raise ValueError('HOLD')
    return json.loads(raw.decode('utf-8'),object_pairs_hook=unique,parse_constant=invalid)

def write(path,raw,owner,replace=False,expected=None):
    need(0<len(raw)<=65536);p=parent(path,owner);name=Path(path).name
    temporary='.'+name+'.tmp-'+secrets.token_hex(8) if replace else name
    try:
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=p)
        with os.fdopen(fd,'wb') as out:
            gid=CONFIG_GID if owner==UID else os.fstat(p).st_gid
            need(type(gid)is int);os.fchown(out.fileno(),owner,gid);os.fchmod(out.fileno(),0o600)
            out.write(raw);out.flush();os.fsync(out.fileno())
        if replace:
            need(metadata(path,owner)==expected)
            again=parent(path,owner)
            try:need((os.fstat(again).st_dev,os.fstat(again).st_ino)==(os.fstat(p).st_dev,os.fstat(p).st_ino))
            finally:os.close(again)
            os.replace(temporary,name,src_dir_fd=p,dst_dir_fd=p)
        os.fsync(p)
    finally:
        if replace:
            try:os.unlink(temporary,dir_fd=p)
            except FileNotFoundError:pass
        os.close(p)

def sync(path,owner):
    expected=metadata(path,owner);p=parent(path,owner)
    try:
        fd=os.open(Path(path).name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=p)
        try:
            need(ident(os.fstat(fd))==expected and stat.S_ISREG(os.fstat(fd).st_mode))
            os.fsync(fd)
        finally:os.close(fd)
        os.fsync(p)
    finally:os.close(p)

def command(args):
    done=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90,check=False)
    need(done.returncode==0 and len(done.stdout)<=65536)
    return done.stdout

def observe():
    fmt='{{json .Id}}\n{{json .Image}}\n{{json .State.Running}}\n{{json .Config.User}}\n{{json .Mounts}}\n{{json .HostConfig.ReadonlyRootfs}}\n{{json .State.Status}}\n{{json .State.Paused}}\n{{json .State.Restarting}}'
    rows=command(DOCKER+['container','inspect','--format',fmt,NAME]).splitlines();need(len(rows)==9)
    cid,image,running,user,mounts,readonly,status,paused,restarting=[json.loads(x) for x in rows]
    need(re.fullmatch('[0-9a-f]{64}',cid) and re.fullmatch('sha256:[0-9a-f]{64}',image) and type(running)is bool and user=='10001:1008' and readonly is True)
    need(status in ('running','exited','created') and paused is False and restarting is False)
    matches=[m for m in mounts if m.get('Destination')==BASE+'/config']
    need(len(matches)==1 and matches[0].get('Source')==BASE+'/config' and matches[0].get('RW')is False)
    return dict(container_id=cid,image_id=image,running=running)

SOURCE_CODE="""import hashlib,json,pathlib,scripts
p=pathlib.Path(scripts.__file__).parent
names=('community_platform_host','community_mini_host_config','community_wechat_sp_readonly','pr122_customer_core')
print(json.dumps({n:hashlib.sha256((p/(n+'.py')).read_bytes()).hexdigest() for n in names},sort_keys=True))
"""
CHECK_CODE="""import hashlib,json,sys
from cryptography.hazmat.primitives import serialization
from scripts.community_mini_host_config import load_protected
from scripts.community_platform_host import _configuration,_open_provider_reader,_require_nonroot
_require_nonroot()
base='/var/lib/xuanjun-community-preview/config/'
c=load_protected(sys.argv[1]);h=load_protected(base+'host.json')
key=serialization.load_pem_private_key(c['private_key_pem'].encode('ascii'),password=None)
spki=key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
if hashlib.sha256(spki).hexdigest()!='28659fe395a1558e1c59293efab4f550c54572e24fa93551198b48e4aebaf61c': raise ValueError('PINNED_MERCHANT_KEY_REQUIRED')
h['provider_reader_config']=sys.argv[1]
_configuration(h,load_protected(base+'center-keys.json'),load_protected(base+'wechat.json'))
_open_provider_reader(sys.argv[1],lambda:0)
print('ORIGINAL_NONROOT_CONFIG_VALIDATED_NO_PROVIDER_IO')
"""

def probe(image,code,args=(),request='preflight'):
    # Exact original config-only restrictions; never business DB/runtimedir mount.
    name='xuanjun-provider-probe-'+sha((request+image+code).encode())[:24]
    existing=command(DOCKER+['container','ls','--all','--filter','name=^/'+name+'$','--format','{{.Names}}']).strip()
    need(not existing)  # Timed-out probe may still exist: inspect, never duplicate.
    return command(DOCKER+['run','--rm','--pull','never','--name',name,'--network','none','--read-only','--user','10001:1008',
        '--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','64','--memory','512m','--memory-swap','512m','--cpus','0.5',
        '--mount','type=bind,src='+BASE+'/config,dst='+BASE+'/config,readonly','--entrypoint','python',image,'-B','-c',code]+list(args))

def probe_observations():
    names=command(DOCKER+['container','ls','--all','--filter','name=^/xuanjun-provider-probe-','--format','{{.Names}}']).decode().splitlines()
    need(len(names)<=32)
    out=[]
    for name in names:
        need(re.fullmatch('xuanjun-provider-probe-[0-9a-f]{24}',name))
        status=command(DOCKER+['container','inspect','--format','{{json .State.Status}}',name])
        out.append({'name':name,'status':json.loads(status)})
    return out

def source_pins(image):
    actual=parse(probe(image,SOURCE_CODE));raw=(HERE/'ORIGINAL_SOURCE_PINS.json').read_bytes();need(sha(raw)==SOURCE_PINS_SHA);known=parse(raw)
    need(actual in list(known.values()));return actual

def preflight(private_path):
    need(os.geteuid()==0 and os.uname().nodename.split('.')[0]==HOST)
    host=parse(read(HOST_FILE,UID));need('provider_reader_config'not in host)
    need(not os.path.lexists(TARGET));metadata(GLOBAL_LOCK,ROOT_UID)
    state=observe();pins=source_pins(state['image_id'])
    need(observe()==state)
    # Only metadata, never private bytes, before Owner confirmation.
    key_owner=None;key_meta=None;blockers=[]
    if not private_path or not os.path.lexists(private_path):
        blockers=['ORIGINAL_PRIVATE_KEY_NOT_YET_AT_VERIFIED_UK_PROTECTED_PATH']
    else:
        key_owner=os.stat(private_path,follow_symlinks=False).st_uid;need(key_owner in (ROOT_UID,UID))
        key_meta=metadata(private_path,key_owner);need(0<key_meta['st_size']<=65536)
    center=str(Path(host['center_root'])/'center.sqlite');center_meta=metadata(center,UID)
    public=(HERE/'pub_key.pem').read_bytes();need(sha(public)==PUBLIC_SHA)
    request='provider-'+secrets.token_hex(12)
    return dict(version=1,request_id=request,host=HOST_FILE,host_sha256=sha(canon(host)),host_identity=metadata(HOST_FILE,UID),
        provider=TARGET,backup=BASE+'/config/.'+request+'-host-backup.json',private_input=private_path,private_owner=key_owner,private_identity=key_meta,
        global_lock=GLOBAL_LOCK,global_lock_identity=metadata(GLOBAL_LOCK,ROOT_UID),center_lock=center,center_lock_identity=center_meta,
        runtime=state,source_sha256=pins,public=dict(PUBLIC),public_pem_sha256=PUBLIC_SHA,merchant_certificate_sha256=CERT_SHA,
        merchant_spki_sha256=SPKI_SHA,blockers=blockers,lock_availability='NOT_ACQUIRED_DURING_READ_ONLY_PREFLIGHT',maintenance='STOP_SAME_CONTAINER_THEN_RESTORE_ORIGINAL_STATE' if state['running'] else 'KEEP_ALREADY_STOPPED')

class Locks:
    def __init__(self):self.fds=[];self.pins=[]
    def acquire(self,path,owner,expected):
        need(metadata(path,owner)==expected);p=parent(path,owner)
        try:fd=os.open(Path(path).name,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=p)
        finally:os.close(p)
        try:
            need(ident(os.fstat(fd))==expected);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:os.close(fd);raise
        self.fds.append(fd);self.pins.append((path,owner,expected));return fd
    def check(self):
        for fd,(path,owner,expected) in zip(self.fds,self.pins):
            # Center DB contents/mtime may change during original orderly stop;
            # compare the post-stop captured identity throughout this window.
            need(metadata(path,owner)==expected and ident(os.fstat(fd))==expected)
    def close(self):
        for fd in reversed(self.fds):os.close(fd)
        self.fds=[];self.pins=[]

def journal_path(request):
    need(re.fullmatch('provider-[0-9a-f]{24}',request));return JOURNAL+'/'+request+'.json'
def save(record,new=False):
    path=journal_path(record['plan']['request_id'])
    write(path,canon(record),ROOT_UID,replace=not new,expected=None if new else metadata(path,ROOT_UID))
def phase(record,value):record['phase']=value;save(record)
def same_container(plan):
    current=observe();need(all(current[k]==plan['runtime'][k] for k in ('container_id','image_id')));return current

def confirm(tty,plan,operation):
    # Output only public metadata, exact paths and intended transitions.
    tty.write(json.dumps(dict(operation=operation,plan=plan),ensure_ascii=False,indent=2)+'\n')
    tty.write('仅配置；运行中原容器将短暂停机并恢复同一实例，不重建。原已停止容器不启动。私钥仅本机读取。\n')
    phrase='CONFIRM '+sha(canon(plan))
    tty.write('同意本次凭据配置/所列维护动作请准确输入 '+phrase+'\n');tty.flush()
    need(tty.readline().strip()==phrase)
    return dict(kind='OWNER_LOCAL_PROTECTED_TTY_CONFIRMATION',operation=operation,confirmation_id=secrets.token_hex(16),plan_sha256=sha(canon(plan)),confirmed_at=int(time.time()),tty_device=os.ttyname(tty.fileno()),euid=os.geteuid())

def perform(record,locks,recover=False):
    global CONFIG_GID
    plan=record['plan'];CONFIG_GID=plan['host_identity']['st_gid']
    need(record['approval']['plan_sha256']==sha(canon(plan)));locks.check()
    current=same_container(plan)
    if record['phase'] in ('CONFIRMED','PREPARE_CONFIG_INTENT'):
        # Confirmed new candidate is validated before any service stop. A wrong
        # key therefore cannot strand the original service in a stopped state.
        need(current==plan['runtime'])
        need(sha(canon(parse(read(HOST_FILE,UID))))==plan['host_sha256'])
        need(metadata(HOST_FILE,UID)==plan['host_identity'])
        need(metadata(plan['private_input'],plan['private_owner'])==plan['private_identity'])
        key=read(plan['private_input'],plan['private_owner']).decode('ascii')
        public=(HERE/'pub_key.pem').read_bytes();need(sha(public)==PUBLIC_SHA)
        config=dict(PUBLIC,private_key_pem=key,public_key_pem=public.decode('ascii'));need(len(canon(config))<=65536)
        if record['phase']=='CONFIRMED':
            record['candidate_sha256']=sha(canon(config));phase(record,'PREPARE_CONFIG_INTENT')
        need(record['candidate_sha256']==sha(canon(config)))
        if not os.path.lexists(TARGET):write(TARGET,canon(config),UID)
        else:need(parse(read(TARGET,UID))==config)
        need(probe(plan['runtime']['image_id'],CHECK_CODE,[TARGET],request=plan['request_id']).strip()==b'ORIGINAL_NONROOT_CONFIG_VALIDATED_NO_PROVIDER_IO')
        phase(record,'PROVIDER_VALIDATED')
    if record['phase']=='PROVIDER_VALIDATED':
        need(same_container(plan)==plan['runtime'])
        need(metadata(HOST_FILE,UID)==plan['host_identity'])
        need(sha(canon(parse(read(TARGET,UID))))==record['candidate_sha256'])
        if current['running']:
            phase(record,'STOP_INTENT');command(DOCKER+['container','stop','--time','20',current['container_id']])
            need(same_container(plan)['running']is False)
        phase(record,'STOPPED')
    elif record['phase']=='STOP_INTENT':
        need(current['running']is False);phase(record,'STOPPED')
    if record['phase'] in ('STOPPED','CONFIG_INTENT'):
        need(same_container(plan)['running']is False)
        poststop=metadata(plan['center_lock'],UID)
        need(all(poststop[k]==plan['center_lock_identity'][k] for k in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink')))
        locks.acquire(plan['center_lock'],UID,poststop)
        need(source_pins(plan['runtime']['image_id'])==plan['source_sha256'])
        host=parse(read(HOST_FILE,UID));target_host=dict(host,provider_reader_config=TARGET)
        if sha(canon(host))==plan['host_sha256']:
            need(metadata(HOST_FILE,UID)==plan['host_identity'])
        else:
            backup=parse(read(plan['backup'],UID));need(sha(canon(backup))==plan['host_sha256'])
            need(host==dict(backup,provider_reader_config=TARGET));target_host=host
        need(len(canon(target_host))<=65536)
        need(metadata(plan['private_input'],plan['private_owner'])==plan['private_identity'])
        key=read(plan['private_input'],plan['private_owner']).decode('ascii')
        public=(HERE/'pub_key.pem').read_bytes();need(sha(public)==PUBLIC_SHA)
        config=dict(PUBLIC,private_key_pem=key,public_key_pem=public.decode('ascii'));need(len(canon(config))<=65536)
        if record['phase']=='STOPPED':phase(record,'CONFIG_INTENT')
        if not os.path.lexists(plan['backup']):write(plan['backup'],canon(host),UID)
        else:need(sha(canon(parse(read(plan['backup'],UID))))==plan['host_sha256'])
        need(parse(read(TARGET,UID))==config) # Partial/foreign state never overwritten.
        need(probe(plan['runtime']['image_id'],CHECK_CODE,[TARGET],request=plan['request_id']).strip()==b'ORIGINAL_NONROOT_CONFIG_VALIDATED_NO_PROVIDER_IO')
        locks.check();need(same_container(plan)['running']is False)
        current_host=parse(read(HOST_FILE,UID))
        if current_host!=target_host:
            need(sha(canon(current_host))==plan['host_sha256'])
            write(HOST_FILE,canon(target_host),UID,replace=True,expected=plan['host_identity'])
        for path in (plan['backup'],TARGET,HOST_FILE):sync(path,UID)
        need(parse(read(HOST_FILE,UID))==target_host and parse(read(TARGET,UID))==config)
        record['configured_host_sha256']=sha(canon(target_host));record['configured_provider_sha256']=sha(canon(config))
        phase(record,'CONFIGURED')
        # Release Center before original application opens it; retain global.
        os.close(locks.fds.pop());locks.pins.pop()
    if record['phase'] in ('CONFIGURED','START_INTENT','COMPLETED'):
        need(sha(canon(parse(read(HOST_FILE,UID))))==record['configured_host_sha256'])
        need(sha(canon(parse(read(TARGET,UID))))==record['configured_provider_sha256'])
        need(source_pins(plan['runtime']['image_id'])==plan['source_sha256'])
    if record['phase']=='CONFIGURED':
        if plan['runtime']['running']:
            need(same_container(plan)['running']is False);phase(record,'START_INTENT')
            command(DOCKER+['container','start',plan['runtime']['container_id']])
        else:need(same_container(plan)['running']is False)
        need(same_container(plan)['running']==plan['runtime']['running']);phase(record,'COMPLETED')
    elif record['phase']=='START_INTENT':
        # Lost response first observes. A still-stopped same instance is retried
        # only after a new explicit TTY recovery confirmation, never in apply.
        if same_container(plan)['running']is False:
            need(recover and record.get('recovery_approval',{}).get('operation')=='RECOVER_SAME_REQUEST')
            need(record['recovery_approval']['plan_sha256']==sha(canon(plan)))
            confirmation=record['recovery_approval']['confirmation_id']
            need(record.get('start_recovery_confirmation')!=confirmation)
            record['start_recovery_confirmation']=confirmation;save(record)
            command(DOCKER+['container','start',plan['runtime']['container_id']])
        need(same_container(plan)['running']is True);phase(record,'COMPLETED')
    need(record['phase']=='COMPLETED')
    need(same_container(plan)['running']==plan['runtime']['running'])
    return {'status':'CONFIGURED_NOT_BUSINESS_ACTIVATED','request_id':plan['request_id'],'original_running_state_restored':True,'provider_io':False}

def query(request=None):
    probes=probe_observations()
    if request is None:return dict(status='READ_ONLY_PROBE_OBSERVATION',probes=probes)
    record=parse(read(journal_path(request),ROOT_UID));plan=record['plan'];current=same_container(plan)
    return dict(request_id=request,phase=record['phase'],runtime=current,probes=probes,status='OBSERVED_ONLY_NOT_RETRIED')

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=('preflight','apply','query','recover'));p.add_argument('--request')
    args=p.parse_args(argv);locks=Locks()
    try:
        need(os.geteuid()==0 and os.uname().nodename.split('.')[0]==HOST)
        if args.operation=='query':print(json.dumps(query(args.request),sort_keys=True));return 0
        with open('/dev/tty','r+') as tty:
            need(os.isatty(tty.fileno()))
            if args.operation in ('preflight','apply'):
                tty.write('输入已由原安全保管路线放在UK的受保护原私钥文件绝对路径（不是正文）：\n');tty.flush()
                plan=preflight(tty.readline().strip())
                if args.operation=='preflight':print(json.dumps(plan,sort_keys=True));return 0
                if plan['blockers']:
                    print(json.dumps(plan,sort_keys=True));return 2
                locks.acquire(GLOBAL_LOCK,ROOT_UID,plan['global_lock_identity'])
                need(same_container(plan)==plan['runtime']);need(metadata(HOST_FILE,UID)==plan['host_identity'])
                approval=confirm(tty,plan,'APPLY');record=dict(version=1,plan=plan,approval=approval,phase='CONFIRMED');save(record,new=True)
            else:
                record=parse(read(journal_path(args.request),ROOT_UID));plan=record['plan']
                locks.acquire(GLOBAL_LOCK,ROOT_UID,plan['global_lock_identity'])
                tty.write(json.dumps(query(args.request),sort_keys=True)+'\n');tty.flush()
                record['recovery_approval']=confirm(tty,plan,'RECOVER_SAME_REQUEST');save(record)
            print(json.dumps(perform(record,locks,recover=args.operation=='recover'),sort_keys=True));return 0
    except Exception:
        # No traceback, provider data or command stderr; no automatic stop/start retry.
        result={'status':'HOLD_QUERY_SAME_REQUEST_NO_AUTOMATIC_RETRY'}
        if 'record' in locals():result['request_id']=record['plan']['request_id']
        print(json.dumps(result,sort_keys=True));return 2
    finally:locks.close()

if __name__=='__main__':raise SystemExit(main())
