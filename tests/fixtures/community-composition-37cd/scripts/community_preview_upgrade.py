"""Fixed UK community-only upgrade candidate; execute only in Owner's scope.

Preserves existing private inputs/data and old container. No first install,
identity/grant writes, image pull, Owner vhost edit, DNS or P2 operations.
A command timeout is UNKNOWN and never triggers an automatic retry/recovery.
Python 3.6 standard library only; no application imports on the host.
"""
import os,stat,json,hashlib,subprocess,signal,tempfile,zipfile,io,time,re
from urllib.request import build_opener,ProxyHandler,HTTPRedirectHandler
from urllib.parse import urlsplit
from urllib.error import HTTPError,URLError

HOST='iZd7oeikknn1z21sq6ji6zZ'
SOURCE='2330dd55c07f58d7f45a7c4510a9761d0d4735d6'
IMAGE='sha256:0846f7cfc71d443095a6c5e3a59eabf5d2973eda90e29c831f335c163a2c8f32'
OLD_IMAGE='sha256:7fb56688456d5f4d46599d34e2bf8496cbbbd3f3181ded3bab70a2de953e6c30'
OLD_ID='36b54db9973ee39bc71e5e8f8532ee52b79390531c79f593ce57d553a91122cc'
NAME='xuanjun-community-preview'
OLD_NAME=NAME+'-before-2330dd55'
FAILED_NAME=NAME+'-failed-2330dd55'
ROOT='/var/lib/xuanjun-community-preview'
RUN='/run/xuanjun-community-preview'
STAGE='/opt/xuanjun-community-preview/roles-upgrade-2330dd55'
INC='/etc/nginx/community-preview.inc'
VHOST='/etc/nginx/conf.d/xuanjun-p2-owner.conf'
DOCKER=['/usr/bin/docker','--host','unix:///var/run/docker.sock']
ZIP_BYTES=56933085
ZIP_SHA='29044f39c16b976164c723484a496ec57f2cf7874cd12706c491c87ab36e4724'
ARCHIVE_SHA='64ba9ce09e688a27a85ec2278e47cbb66c096a4b35d5f9653d9e1e58af368bbc'
# Fixed source-derived constants inserted before publication, never request input.
FRAGMENT=b'# CANDIDATE ONLY: include inside the EXISTING uk HTTPS server after route/TLS review.\n# No listen/server_name/certificate directives; do not replace the host root routes.\n# API only: browser workspace assets/redirects require separate prefix verification.\nlocation ^~ /community-preview/mini/ {\n    rewrite ^/community-preview(/mini/.*)$ $1 break;\n    proxy_pass http://unix:/run/xuanjun-community-preview/preview.sock:;\n    proxy_http_version 1.1;\n    proxy_set_header Host uk.wenwenwenyiyiyi.work;\n    proxy_set_header X-Forwarded-Proto https;\n    proxy_set_header X-Xuanjun-Client-IP "";\n    proxy_set_header X-Xuanjun-Client-IP $remote_addr;\n    proxy_set_header X-Forwarded-For "";\n    proxy_set_header Forwarded "";\n}\nlocation = /community-preview/community/health {\n    rewrite ^ /community/health break;\n    proxy_pass http://unix:/run/xuanjun-community-preview/preview.sock:;\n    proxy_http_version 1.1;\n    proxy_set_header Host uk.wenwenwenyiyiyi.work;\n    proxy_set_header X-Forwarded-Proto https;\n    proxy_set_header X-Xuanjun-Client-IP "";\n    proxy_set_header X-Xuanjun-Client-IP $remote_addr;\n    proxy_set_header X-Forwarded-For "";\n    proxy_set_header Forwarded "";\n}\n\n# Original browser role pages/assets and their existing authenticated API paths only.\nlocation ~ ^/community-preview/(merchant/(join|review|workbench(\\.js|\\.css)?|onboarding(\\.js|\\.css)?)|community/(portal(\\.js|\\.css)?|web-session\\.js|session/(login|check|logout)|entrypoints|operations|directory|commerce|provider-actions|merchant-bills))$ {\n    rewrite ^/community-preview(/.*)$ $1 break;\n    proxy_pass http://unix:/run/xuanjun-community-preview/preview.sock:;\n    proxy_http_version 1.1;\n    proxy_set_header Host uk.wenwenwenyiyiyi.work;\n    proxy_set_header X-Forwarded-Proto https;\n    proxy_set_header X-Xuanjun-Client-IP "";\n    proxy_set_header X-Xuanjun-Client-IP $remote_addr;\n    proxy_set_header X-Forwarded-For "";\n    proxy_set_header Forwarded "";\n}\n'
OLD_FRAGMENT_SHA='23ced336e2e554b4920c08085fea52d732775e0e341deb5f2187c522d36f76f6'
ASSET_HASHES={'/merchant/workbench': '0292f9a2f02d5cfc28b561079e6f50066a99df7805f8965d00b46f4de593d05a', '/community/portal': 'f27ddf3d60d2271a4ae49c9ac05f6285b833f5cb031306664ae9d3f13f7da357', '/merchant/review': '1beba4ae6fa0fb65f9a7c7302b0cfbdcc3fb33a3774bc6e4d1a4fbf41fbd899e', '/merchant/join': '1beba4ae6fa0fb65f9a7c7302b0cfbdcc3fb33a3774bc6e4d1a4fbf41fbd899e', '/community/web-session.js': 'c01a9ac0781915015ac2873c95ff84badef57ee24b4e5697e4f95b2f5b78c4db'}

class Unknown(RuntimeError):pass
class Rejected(RuntimeError):pass

def command(args,timeout=8):
    try:r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    except subprocess.TimeoutExpired:raise Unknown('COMMAND_TIMEOUT_INSPECT_ONLY')
    if len(r.stdout)>65536 or len(r.stderr)>65536:raise Unknown('COMMAND_OUTPUT_BOUNDARY_INSPECT_ONLY')
    if r.returncode:raise Rejected('COMMAND_REJECTED')
    return r.stdout.decode('utf-8')

def mutate(args,timeout=8):
    print('COMMUNITY_ONLY_ACTION_'+(args[3] if args[:3]==DOCKER else args[1]).upper(),flush=True)
    try:return command(args,timeout)
    except Rejected:raise Unknown('MUTATION_RESULT_INSPECT_ONLY')

def secure_directory(path,owner=0):
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        parts=path.split('/')[1:]
        for i,part in enumerate(parts):
            if not part or part in ('.','..'):raise Rejected('EXACT_DIRECTORY_REQUIRED')
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child;s=os.fstat(fd)
            expected=owner if i==len(parts)-1 else 0
            if s.st_uid!=expected or s.st_mode&0o022:raise Rejected('UNPROTECTED_DIRECTORY')
    finally:os.close(fd)

def read_root_file(path):
    secure_directory(os.path.dirname(path))
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        s=os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022 or s.st_nlink!=1 or s.st_size>65536:
            raise Rejected('FILE_BOUNDARY')
        raw=f.read(65537)
    if len(raw)>65536:raise Rejected('FILE_SIZE')
    return raw,stat.S_IMODE(s.st_mode)

def create(path,raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())

def replace_include(expected,new,mode):
    before,actual_mode=read_root_file(INC)
    if before!=expected or actual_mode!=mode:raise Unknown('INCLUDE_CHANGED_INSPECT_ONLY')
    fd,path=tempfile.mkstemp(prefix='.community-upgrade-',dir=os.path.dirname(INC))
    try:
        with os.fdopen(fd,'wb') as f:
            os.fchmod(f.fileno(),mode);f.write(new);f.flush();os.fsync(f.fileno())
        if read_root_file(INC)!=(expected,mode):raise Unknown('INCLUDE_CHANGED_INSPECT_ONLY')
        os.replace(path,INC)
    finally:
        if os.path.exists(path):os.unlink(path)

INSPECT_FIELDS=[('id','.Id'),('image','.Image'),('running','.State.Running'),('status','.State.Status'),
    ('user','.Config.User'),('cmd','.Config.Cmd'),('entrypoint','.Config.Entrypoint'),('mounts','.Mounts'),
    ('cpu','.HostConfig.NanoCpus'),('memory','.HostConfig.Memory'),('swap','.HostConfig.MemorySwap'),
    ('pids','.HostConfig.PidsLimit'),('readonly','.HostConfig.ReadonlyRootfs'),('privileged','.HostConfig.Privileged'),
    ('restart','.HostConfig.RestartPolicy.Name'),('network','.HostConfig.NetworkMode'),('capdrop','.HostConfig.CapDrop'),
    ('security','.HostConfig.SecurityOpt'),('tmpfs','.HostConfig.Tmpfs'),('log','.HostConfig.LogConfig')]

def inspect(reference):
    fmt='\n'.join('{{json '+field+'}}' for _,field in INSPECT_FIELDS)
    raw=command(DOCKER+['container','inspect','--format',fmt,reference])
    rows=raw.splitlines()
    if len(rows)!=len(INSPECT_FIELDS):raise Unknown('INSPECT_SHAPE_UNKNOWN')
    return {name:json.loads(row) for (name,_),row in zip(INSPECT_FIELDS,rows)}

def validate(info,image,cid=None,running=True):
    if (cid is not None and info['id']!=cid) or info['image']!=image or info['running'] is not running:
        raise Rejected('EXACT_CONTAINER_STATE_REQUIRED')
    expected={'user':'10001:1008','cpu':500000000,'memory':536870912,'swap':536870912,
        'pids':64,'readonly':True,'privileged':False,'restart':'no','capdrop':['ALL'],
        'entrypoint':['python','-B','-m','scripts.community_platform_host'],
        'cmd':['--plan',ROOT+'/config/host.json','--center-keys',ROOT+'/config/center-keys.json','--wechat-secret',ROOT+'/config/wechat.json']}
    if any(info[k]!=v for k,v in expected.items()):raise Rejected('CONTAINER_SCOPE_CHANGED')
    if info['network'] not in ('default','bridge') or info['security'] not in (['no-new-privileges'],['no-new-privileges:true']):
        raise Rejected('CONTAINER_ISOLATION_CHANGED')
    if info['tmpfs']!={'/tmp':'rw,noexec,nosuid,nodev,size=16777216,mode=1777'}:
        raise Rejected('TMPFS_CHANGED')
    if info['log']!={'Type':'json-file','Config':{'max-size':'10m','max-file':'2'}}:
        raise Rejected('LOG_LIMIT_CHANGED')
    expected_mounts={(ROOT+'/config',ROOT+'/config',False),(ROOT+'/data',ROOT+'/data',True),(RUN,RUN,True)}
    if len(info['mounts'])!=3 or any(m.get('Type')!='bind' for m in info['mounts']) or {(m['Source'],m['Destination'],m['RW']) for m in info['mounts']}!=expected_mounts:
        raise Rejected('EXACT_EXISTING_MOUNTS_REQUIRED')

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args):return None

def archive_from_zip(raw):
    if len(raw)!=ZIP_BYTES or hashlib.sha256(raw).hexdigest()!=ZIP_SHA:raise Rejected('ARTIFACT_BYTES_OR_HASH')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist()
        if len(names)!=4 or set(names)!={'community-image-tests.log','community-image-id.txt','community-backend-image.tar.gz','community-backend-image.sha256'}:
            raise Rejected('EXACT_ARTIFACT_MEMBERS_REQUIRED')
        if any(x.file_size>60000000 for x in z.infolist()):raise Rejected('ARCHIVE_MEMBER_LIMIT')
        archive=z.read('community-backend-image.tar.gz')
        if hashlib.sha256(archive).hexdigest()!=ARCHIVE_SHA:raise Rejected('IMAGE_ARCHIVE_HASH')
        if z.read('community-image-id.txt').decode().strip()!=IMAGE:raise Rejected('IMAGE_ID_RECEIPT')
        return archive

def load_artifact(url):
    u=urlsplit(url)
    if u.scheme!='https' or u.username or u.password or u.port not in (None,443) or not re.fullmatch(r'sdmntpr[a-z0-9-]+\.oaiusercontent\.com',u.hostname or ''):
        raise Rejected('EXACT_ARTIFACT_TRANSPORT_REQUIRED')
    op=build_opener(ProxyHandler({}),NoRedirect())
    with op.open(url,timeout=12) as response:raw=response.read(ZIP_BYTES+1)
    archive=archive_from_zip(raw)
    target=STAGE+'/community-backend-image.tar.gz';create(target,archive)
    mutate(DOCKER+['image','load','--input',target],60)
    fmt='{{.Id}}|{{.Architecture}}|{{.Os}}|{{.Config.User}}|{{index .Config.Labels "org.opencontainers.image.revision"}}'
    if command(DOCKER+['image','inspect','--format',fmt,IMAGE]).strip()!='|'.join((IMAGE,'amd64','linux','10001:1008',SOURCE)):
        raise Unknown('LOADED_IMAGE_INSPECT_ONLY')

HEALTH_CODE="""import os,socket,json,hashlib
os.setgroups([]);os.setgid(1008);os.setuid(1008)
paths=PATHS
for path,expected in paths.items():
 s=socket.socket(socket.AF_UNIX);s.settimeout(3);s.connect('/run/xuanjun-community-preview/preview.sock')
 s.sendall(('GET '+path+' HTTP/1.0\\r\\nHost: uk.wenwenwenyiyiyi.work\\r\\nX-Xuanjun-Client-IP: 127.0.0.1\\r\\n\\r\\n').encode())
 raw=b''
 while len(raw)<=262144:
  b=s.recv(65536)
  if not b:break
  raw+=b
 s.close()
 assert len(raw)<=262144
 head,body=raw.split(b'\\r\\n\\r\\n',1);assert b' 200 OK' in head.split(b'\\r\\n',1)[0]
 if expected:assert hashlib.sha256(body).hexdigest()==expected
 elif path=='/community/health':
  value=json.loads(body.decode());assert value['status']=='READY' and value['production_acceptance'] is False
 else:
  value=json.loads(body.decode());assert value['source_sha']=='SOURCE' and value['project_ids']==['community_platform'] and value['production_acceptance'] is False
print('PRIVATE_EXPECTED_VERSION_READY_AUTH_NOT_ACCEPTED')
"""

def private_ready(assets=False):
    paths={'/community/health':None}
    if assets:paths.update(ASSET_HASHES);paths['/community/entrypoints']=None
    code=HEALTH_CODE.replace('PATHS',repr(paths)).replace("'SOURCE'",repr(SOURCE))
    return command(['/usr/bin/python3','-I','-B','-S','-c',code],25).strip()=='PRIVATE_EXPECTED_VERSION_READY_AUTH_NOT_ACCEPTED'

def await_private_ready(reference,image,assets=False):
    deadline=time.monotonic()+12
    while True:
        validate(inspect(reference),image,reference)
        try:
            if private_ready(assets):return
        except Rejected:pass
        if time.monotonic()>=deadline:raise Rejected('PRIVATE_NOT_READY')
        time.sleep(.2)

def run_args():
    return DOCKER+['run','--pull','never','--detach','--restart','no','--name',NAME,'--label','community.source='+SOURCE,
        '--read-only','--user','10001:1008','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','64',
        '--cpus','0.5','--memory','512m','--memory-swap','512m','--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=16777216,mode=1777',
        '--log-driver','json-file','--log-opt','max-size=10m','--log-opt','max-file=2',
        '--mount','type=bind,src='+ROOT+'/config,dst='+ROOT+'/config,readonly',
        '--mount','type=bind,src='+ROOT+'/data,dst='+ROOT+'/data',
        '--mount','type=bind,src='+RUN+',dst='+RUN,IMAGE,
        '--plan',ROOT+'/config/host.json','--center-keys',ROOT+'/config/center-keys.json','--wechat-secret',ROOT+'/config/wechat.json']

def public_ready_once():
    op=build_opener(ProxyHandler({}),NoRedirect())
    paths=dict(ASSET_HASHES);paths['/community/health']=None;paths['/community/entrypoints']=None
    for path,expected in paths.items():
        try:
            with op.open('https://uk.wenwenwenyiyiyi.work/community-preview'+path,timeout=5) as response:
                if response.status!=200:raise Rejected('PUBLIC_STATUS')
                raw=response.read(262145)
        except HTTPError as error:
            print(json.dumps({'check':'PUBLIC','path':path,'http_status':error.code}),flush=True)
            error.close()
            if error.code in (404,502,503):raise PublicPending('PUBLIC_HTTP_'+str(error.code))
            raise Rejected('PUBLIC_HTTP_STATUS')
        except (URLError,TimeoutError):raise Unknown('PUBLIC_NETWORK_INSPECT_ONLY')
        if len(raw)>262144:raise Rejected('PUBLIC_BODY_LIMIT')
        if expected:
            if hashlib.sha256(raw).hexdigest()!=expected:raise Rejected('PUBLIC_ASSET_HASH')
        else:
            value=json.loads(raw.decode())
            if value.get('production_acceptance') is not False:raise Rejected('PUBLIC_CONTRACT')
            if path.endswith('health'):
                if value.get('status')!='READY':raise Rejected('PUBLIC_HEALTH')
            elif value.get('source_sha')!=SOURCE or value.get('project_ids')!=['community_platform']:raise Rejected('PUBLIC_VERSION')


class PublicPending(Rejected):pass

def public_ready():
    # Reload acknowledgement precedes worker readiness. Retry only bounded,
    # read-only probes for explicit transitional HTTP statuses. Every attempt
    # rechecks ALL exact assets and version fields; UNKNOWN never replays.
    deadline=time.monotonic()+15
    for attempt in range(4):
        try:return public_ready_once()
        except PublicPending as error:
            print(json.dumps({'check':'PUBLIC_RELOAD_WAIT','attempt':attempt+1,
                              'reason':str(error)}),flush=True)
            if attempt==3 or time.monotonic()+1>=deadline:raise
            time.sleep(1)


def rollback(new_id,old_include,mode,vhost_hash):
    # Called only after a known failure and a known run receipt. UNKNOWN never
    # reaches this function; confirm the new writer stopped before old start.
    current=inspect(new_id);validate(current,IMAGE,new_id,running=current['running'])
    if current['running']:mutate(DOCKER+['stop','--time','10',new_id],15)
    validate(inspect(new_id),IMAGE,new_id,running=False)
    if os.path.lexists(RUN+'/preview.sock'):raise Unknown('SOCKET_REMAINS_INSPECT_ONLY')
    mutate(DOCKER+['rename',new_id,FAILED_NAME])
    if hashlib.sha256(read_root_file(VHOST)[0]).hexdigest()!=vhost_hash:raise Unknown('OWNER_VHOST_CHANGED_INSPECT_ONLY')
    value,_=read_root_file(INC)
    if value==FRAGMENT:replace_include(FRAGMENT,old_include,mode)
    elif value!=old_include:raise Unknown('INCLUDE_CHANGED_INSPECT_ONLY')
    command(['/usr/sbin/nginx','-t'])
    mutate(DOCKER+['rename',OLD_ID,NAME]);mutate(DOCKER+['start',OLD_ID],15)
    validate(inspect(OLD_ID),OLD_IMAGE,OLD_ID)
    await_private_ready(OLD_ID,OLD_IMAGE)
    mutate(['/usr/bin/systemctl','reload','nginx.service'])
    print('KNOWN_FAILURE_ROLLED_BACK_ORIGINAL_CONTAINER_DATA_PRESERVED',flush=True)


def main(url):
    if os.getuid()!=0 or os.geteuid()!=0 or os.uname().nodename.split('.')[0]!=HOST:raise Rejected('HOST_OR_ROOT')
    os.umask(0o077)
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(Unknown('DEADLINE_INSPECT_ONLY')));signal.alarm(180)
    for p in ('/opt/xuanjun-community-preview','/etc/nginx/conf.d'):secure_directory(p)
    secure_directory(ROOT);secure_directory(ROOT+'/config',10001);secure_directory(ROOT+'/data',10001);secure_directory(RUN,10001)
    if os.path.lexists(STAGE):raise Rejected('EXISTING_ATTEMPT_INSPECT_ONLY')
    current=inspect(NAME);validate(current,OLD_IMAGE,OLD_ID)
    names=command(DOCKER+['container','ls','--all','--format','{{.Names}}','--filter','name=^/xuanjun-community-preview']).splitlines()
    if OLD_NAME in names or FAILED_NAME in names:raise Rejected('EXISTING_RECOVERY_CONTAINER')
    old_include,mode=read_root_file(INC)
    if hashlib.sha256(old_include).hexdigest()!=OLD_FRAGMENT_SHA:raise Rejected('ORIGINAL_INCLUDE_CHANGED')
    vhost=read_root_file(VHOST)[0];vhost_hash=hashlib.sha256(vhost).hexdigest()
    if vhost.count(b'include /etc/nginx/community-preview.inc;')!=1:raise Rejected('EXISTING_INCLUDE_REQUIRED')
    command(['/usr/bin/systemctl','is-active','--quiet','nginx.service']);command(['/usr/sbin/nginx','-t'])
    if not private_ready():raise Rejected('ORIGINAL_BACKEND_NOT_READY')
    os.mkdir(STAGE,0o700);create(STAGE+'/include.before',old_include)
    create(STAGE+'/attempt.json',json.dumps({'source_sha':SOURCE,'old_id':OLD_ID,'new_image':IMAGE,'owner_vhost_sha256':vhost_hash,'phase':'PREPARED'},sort_keys=True).encode())
    load_artifact(url)
    # Candidate parser validates own include while old backend still runs.
    replace_include(old_include,FRAGMENT,mode)
    try:command(['/usr/sbin/nginx','-t'])
    except Rejected:
        replace_include(FRAGMENT,old_include,mode);raise Rejected('CANDIDATE_INVALID_ORIGINAL_NOT_RELOADED')
    # Recheck old writer and vhost immediately before the only stop action.
    validate(inspect(NAME),OLD_IMAGE,OLD_ID)
    if hashlib.sha256(read_root_file(VHOST)[0]).hexdigest()!=vhost_hash:raise Unknown('OWNER_VHOST_CHANGED_INSPECT_ONLY')
    mutate(DOCKER+['stop','--time','10',OLD_ID],15)
    validate(inspect(OLD_ID),OLD_IMAGE,OLD_ID,running=False)
    if os.path.lexists(RUN+'/preview.sock'):raise Unknown('OLD_SOCKET_REMAINS_INSPECT_ONLY')
    mutate(DOCKER+['rename',OLD_ID,OLD_NAME])
    new_id=mutate(run_args(),20).strip()
    if not re.fullmatch('[0-9a-f]{64}',new_id):raise Unknown('RUN_RECEIPT_UNKNOWN_INSPECT_ONLY')
    create(STAGE+'/new-container-id.txt',(new_id+'\n').encode())
    try:
        validate(inspect(new_id),IMAGE,new_id)
        await_private_ready(new_id,IMAGE,True)
        if hashlib.sha256(read_root_file(VHOST)[0]).hexdigest()!=vhost_hash:raise Unknown('OWNER_VHOST_CHANGED_INSPECT_ONLY')
        mutate(['/usr/bin/systemctl','reload','nginx.service'])
        public_ready()
        if hashlib.sha256(read_root_file(VHOST)[0]).hexdigest()!=vhost_hash:raise Unknown('OWNER_VHOST_CHANGED_INSPECT_ONLY')
    except Unknown:raise
    except Exception as error:
        print(json.dumps({'check':'KNOWN_FAILURE','reason':str(error) if isinstance(error,Rejected) else type(error).__name__}),flush=True)
        rollback(new_id,old_include,mode,vhost_hash)
        raise Rejected('KNOWN_FAILURE_ROLLED_BACK')
    signal.alarm(0)
    receipt={'state':'PUBLIC_ORIGINAL_ROLE_ASSETS_READY_AUTH_ACCEPTANCE_PENDING','source_sha':SOURCE,'image_id':IMAGE,'container_id':new_id,
        'owner_vhost_sha256':vhost_hash,'rollback_container':OLD_NAME,'private_inputs_and_data':'REUSED_UNCHANGED',
        'cpu':'0.5','memory_bytes':536870912,'pids':64,'payments':False,'role_acceptance':False,'wechat_login_verified':False,'disk_hard_quota':'NOT_CONFIGURED'}
    create(STAGE+'/receipt.json',json.dumps(receipt,sort_keys=True).encode());print(json.dumps(receipt,sort_keys=True),flush=True)

# Owner's bounded rollback receipt pins this exact stopped container.
RESUME_ID='818fe0b0622c26c43685f61e79c6138ec0afce28adc7adb20aa56e68aac0b23c'

def resume_rolled_back():
    if os.getuid()!=0 or os.geteuid()!=0 or os.uname().nodename.split('.')[0]!=HOST:raise Rejected('HOST_OR_ROOT')
    os.umask(0o077)
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(Unknown('DEADLINE_INSPECT_ONLY')));signal.alarm(180)
    for p in ('/opt/xuanjun-community-preview','/etc/nginx/conf.d',ROOT,STAGE):secure_directory(p)
    for p in (ROOT+'/config',ROOT+'/data',RUN):secure_directory(p,10001)
    attempt=json.loads(read_root_file(STAGE+'/attempt.json')[0].decode())
    if (attempt.get('source_sha')!=SOURCE or attempt.get('old_id')!=OLD_ID or
        attempt.get('new_image')!=IMAGE or attempt.get('phase')!='PREPARED'):
        raise Rejected('ORIGINAL_ATTEMPT_MISMATCH')
    if read_root_file(STAGE+'/new-container-id.txt')[0].decode().strip()!=RESUME_ID:raise Rejected('RESUME_RECEIPT_MISMATCH')
    resume=STAGE+'/resume-01'
    if os.path.lexists(resume) or os.path.lexists(STAGE+'/receipt.json'):raise Rejected('EXISTING_RESUME_INSPECT_ONLY')
    validate(inspect(NAME),OLD_IMAGE,OLD_ID)
    validate(inspect(FAILED_NAME),IMAGE,RESUME_ID,running=False)
    names=command(DOCKER+['container','ls','--all','--format','{{.Names}}','--filter','name=^/xuanjun-community-preview']).splitlines()
    if OLD_NAME in names:raise Rejected('EXISTING_RECOVERY_CONTAINER')
    old_include,mode=read_root_file(INC)
    if hashlib.sha256(old_include).hexdigest()!=OLD_FRAGMENT_SHA or read_root_file(STAGE+'/include.before')[0]!=old_include:
        raise Rejected('ROLLBACK_INCLUDE_MISMATCH')
    vhost_hash=hashlib.sha256(read_root_file(VHOST)[0]).hexdigest()
    if vhost_hash!=attempt.get('owner_vhost_sha256'):raise Unknown('OWNER_VHOST_CHANGED_INSPECT_ONLY')
    command(['/usr/bin/systemctl','is-active','--quiet','nginx.service']);command(['/usr/sbin/nginx','-t'])
    if not private_ready():raise Rejected('ORIGINAL_BACKEND_NOT_READY')
    os.mkdir(resume,0o700)
    create(resume+'/attempt.json',json.dumps({'source_sha':SOURCE,'new_id':RESUME_ID,'phase':'RESUME_PREPARED'},sort_keys=True).encode())
    replace_include(old_include,FRAGMENT,mode)
    try:command(['/usr/sbin/nginx','-t'])
    except Rejected:
        replace_include(FRAGMENT,old_include,mode);raise Rejected('CANDIDATE_INVALID_ORIGINAL_NOT_RELOADED')
    validate(inspect(NAME),OLD_IMAGE,OLD_ID)
    validate(inspect(FAILED_NAME),IMAGE,RESUME_ID,running=False)
    if hashlib.sha256(read_root_file(VHOST)[0]).hexdigest()!=vhost_hash:raise Unknown('OWNER_VHOST_CHANGED_INSPECT_ONLY')
    mutate(DOCKER+['stop','--time','10',OLD_ID],15)
    validate(inspect(OLD_ID),OLD_IMAGE,OLD_ID,running=False)
    if os.path.lexists(RUN+'/preview.sock'):raise Unknown('OLD_SOCKET_REMAINS_INSPECT_ONLY')
    mutate(DOCKER+['rename',OLD_ID,OLD_NAME])
    mutate(DOCKER+['rename',RESUME_ID,NAME])
    mutate(DOCKER+['start',RESUME_ID],15)
    try:
        validate(inspect(RESUME_ID),IMAGE,RESUME_ID)
        await_private_ready(RESUME_ID,IMAGE,True)
        if hashlib.sha256(read_root_file(VHOST)[0]).hexdigest()!=vhost_hash:raise Unknown('OWNER_VHOST_CHANGED_INSPECT_ONLY')
        mutate(['/usr/bin/systemctl','reload','nginx.service'])
        public_ready()
        if hashlib.sha256(read_root_file(VHOST)[0]).hexdigest()!=vhost_hash:raise Unknown('OWNER_VHOST_CHANGED_INSPECT_ONLY')
    except Unknown:raise
    except Exception as error:
        reason=str(error) if isinstance(error,Rejected) else type(error).__name__
        create(resume+'/failure.json',json.dumps({'check':'KNOWN_FAILURE','reason':reason},sort_keys=True).encode())
        print(json.dumps({'check':'KNOWN_FAILURE','reason':reason}),flush=True)
        rollback(RESUME_ID,old_include,mode,vhost_hash)
        raise Rejected('KNOWN_FAILURE_ROLLED_BACK')
    receipt={'state':'PUBLIC_ORIGINAL_ROLE_ASSETS_READY_AUTH_ACCEPTANCE_PENDING','source_sha':SOURCE,
        'image_id':IMAGE,'container_id':RESUME_ID,'rollback_container':OLD_NAME,
        'private_inputs_and_data':'REUSED_UNCHANGED','payments':False,'role_acceptance':False,'wechat_login_verified':False}
    create(resume+'/receipt.json',json.dumps(receipt,sort_keys=True).encode())
    signal.alarm(0);print(json.dumps(receipt,sort_keys=True),flush=True)

if __name__=='__main__':
    try:
        if globals().get('RESUME_ROLLED_BACK') is True:resume_rolled_back()
        else:main(ARTIFACT_URL)
    except Unknown:raise SystemExit('HOLD_UNKNOWN_INSPECT_ONLY_NO_RETRY')
    except Rejected as error:raise SystemExit('HOLD_'+str(error))
    except Exception as error:raise SystemExit('HOLD_'+type(error).__name__+'_INSPECT_ONLY')
