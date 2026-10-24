"""Host-only original UK composition; no CLI, network or writes at import.

Requires separately reviewed root installation/approval and an EXISTING backup
reference descriptor. It never loads an image, creates the journal parent, reads
private configuration/DB bodies, or treats the old receipt as a data backup.
"""
import hashlib
import json
import math
import os
import stat
import re
import time
from scripts import community_preview_update_checkpoint as controller
from scripts import community_preview_release_plan as plan
from scripts import community_preview_upgrade as original
from scripts import community_preview_version_inspect as observation

APPROVAL='/opt/xuanjun-community-preview/update-approval.json'  # proposed, never created
PRODUCT='f13155ed63a3137d41766ee587d9b4b96a81477f'
CONTROL='a9324156f94040bb6ff0243815bb91abe2f67b2a'
PINS={controller:'a73c1fe8ebb71abaefeb56ca880057e23876b5c005d315e4fb1268d3087064fd',
      plan:'a44335c587ced937d16c5abef8916a200705adf15f9f86942560ac47d2dd7566',
      original:'2584441af33e6db1c5d24596f6cbc82077364a0b2b18554c6ba550ec8f66e0ee',
      observation:'98773bcd199f5cb50d15fb3bba1b6959541a12c3f5f2a4879dcd88e5d3bb6cc3'}
RECEIPT_SHA='cba144af0ca2f753413f7bdcec92625c370c479c4708b1d4a1db0b35907c8b45'
ACTIONS=['ORIGINAL_CONTAINER_STOP_RENAME_RUN','KNOWN_FAILURE_SERIAL_RECOVERY','JOURNAL_WRITES']


def require(ok,reason):
    if not ok:raise controller.Hold(reason)


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def now():
    value=time.time()
    require(type(value) in (int,float) and math.isfinite(value) and value>0,'CLOCK_UNKNOWN')
    return int(value)


def root_host():
    require(os.getuid()==0 and os.geteuid()==0 and os.uname().nodename.split('.')[0]==plan.HOST,'EXACT_ROOT_HOST_REQUIRED')


def protected_body(path,sha):
    # Original bounded no-follow chain/file helper, root-owned source/receipt only.
    raw,mode=original.read_root_file(path)
    if path==APPROVAL:require(mode==0o600,'ROOT_0600_APPROVAL_REQUIRED')
    require(hashlib.sha256(raw).hexdigest()==sha,'APPROVED_FILE_DIGEST_CHANGED')
    return raw


def stable_metadata(path):
    # Metadata only, never config/key/DB bytes. Directory timestamps/size change
    # during legitimate data/socket writes and are deliberately not identities.
    value=observation.safe_file(path)
    if value['type']=='REGULAR_FILE':require(value['nlink']==1,'REFERENCE_HARDLINK_DENIED')
    keys=('type','uid','gid','mode','device','inode')
    if value['type']=='REGULAR_FILE':keys+=('nlink','size','mtime_ns','ctime_ns')
    return {key:value[key] for key in keys}


def backup_reference(fd):
    # Caller supplies an already-open protected EXISTING reference capability,
    # not a request path. It is an attestation reference, not a verified DB copy.
    require(type(fd) is int and fd>=0,'EXISTING_BACKUP_DESCRIPTOR_REQUIRED')
    path=os.readlink('/proc/self/fd/'+str(fd))
    require(path.startswith('/opt/xuanjun-community-preview/') and not path.endswith(' (deleted)'),
            'ORIGINAL_BACKUP_REFERENCE_SCOPE_REQUIRED')
    before=os.fstat(fd)
    require(stat.S_ISREG(before.st_mode) and before.st_uid==0 and stat.S_IMODE(before.st_mode)==0o600
            and before.st_nlink==1 and before.st_size<=65536,'PROTECTED_BACKUP_REFERENCE_REQUIRED')
    value=stable_metadata(path)
    after=os.fstat(fd)
    require(observation.identity(before)==observation.identity(after)
            and value['device']==after.st_dev and value['inode']==after.st_ino,'BACKUP_REFERENCE_REPLACED')
    return digest({'path':path,'metadata':value})


def inspect_bound(cid,image):
    # Same original typed projection/validation, with bounded original readonly
    # child transport; additionally prove no published port/device/cap addition.
    fields=original.INSPECT_FIELDS+[('ports','.HostConfig.PortBindings'),
        ('published','.NetworkSettings.Ports'),('devices','.HostConfig.Devices'),('capadd','.HostConfig.CapAdd')]
    fmt='\n'.join('{{json '+field+'}}' for _,field in fields)
    rows=observation.capture(plan.DOCKER+['container','inspect','--format',fmt,cid],timeout=8,budget=32768).splitlines()
    require(len(rows)==len(fields),'CURRENT_INSPECT_SHAPE')
    value={key:observation.exact_json(raw) for (key,_),raw in zip(fields,rows)}
    require(type(value['running']) is bool,'CURRENT_RUNNING_UNKNOWN')
    for key in ('cpu','memory','swap','pids'):require(type(value[key]) is int,'CURRENT_RESOURCE_TYPE')
    for key in ('readonly','privileged'):require(type(value[key]) is bool,'CURRENT_ISOLATION_TYPE')
    original.validate(value,image,cid,running=value['running'])
    require(value['ports'] in (None,{}) and value['published'] in (None,{})
            and value['devices'] in (None,[]) and value['capadd'] in (None,[]),'NO_NEW_PORT_DEVICE_CAPABILITY')
    return value


PRIVATE_PROBE = r"""import http.client,json,socket
class Local(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(8)
        self.sock.connect('/run/xuanjun-community-preview/preview.sock')
try:
    c=Local('localhost',timeout=8)
    c.request('GET','/community/health',headers={'Accept':'application/json','Host':'uk.wenwenwenyiyiyi.work'})
    r=c.getresponse()
    if r.status not in (200,503) or r.getheader('Content-Type','').split(';')[0].strip()!='application/json':raise ValueError()
    raw=r.read(4097)
    if len(raw)>4096:raise ValueError()
    print(json.dumps({'http_status':r.status,'body_hex':raw.hex()},sort_keys=True))
    c.close()
except Exception:raise SystemExit('PRIVATE_HEALTH_UNAVAILABLE')
"""


def read_health_probe(probe):
    # Reuse the reviewed bounded fixed-URL subprocess, TLS, no proxy/redirect,
    # application/json, 4096B and duplicate/nonfinite rejection. Do NOT use
    # observation.health(): it labels local collection time observed_at.
    frame=observation.exact_json(observation.capture(
        ['/usr/bin/python3','-I','-B','-S','-c',probe],timeout=10,budget=10000))
    require(type(frame) is dict and set(frame)=={'http_status','body_hex'}
            and type(frame['http_status']) is int and frame['http_status'] in (200,503)
            and type(frame['body_hex']) is str and len(frame['body_hex'])<=8192
            and re.fullmatch('[0-9a-f]*',frame['body_hex']) is not None,'HEALTH_FRAME_UNKNOWN')
    try:raw=bytes.fromhex(frame['body_hex']);body=observation.exact_json(raw.decode('utf-8'))
    except (ValueError,UnicodeError):raise controller.Hold('HEALTH_JSON_UNKNOWN') from None
    require(type(body) is dict,'HEALTH_OBJECT_REQUIRED')
    # Remote timestamp is never minted from local time, even for old rollback.
    require(type(body.get('observed_at')) is int and now()-600<=body['observed_at']<=now()+30,
            'REMOTE_HEALTH_TIME_REQUIRED')
    value={key:body.get(key) for key in ('status','scope','production_acceptance',
        'runtime_source_sha','version_source','observed_at')}
    value.update(http_status=frame['http_status'],url=plan.URL)
    return value


def actual_health():
    public=read_health_probe(observation.HTTP_PROBE)
    private=read_health_probe(PRIVATE_PROBE)
    require(all(type(public[k]) is type(private[k]) and public[k]==private[k]
                for k in public if k!='observed_at'),'PUBLIC_PRIVATE_HEALTH_MISMATCH')
    # Keep the public responder timestamp intact, never label local collection
    # time as remote time. Both timestamps were independently freshness-checked.
    return public


def read_current(cid,image,backup_fd):
    """Actual bounded projection; no caller-supplied identity hash is emitted."""
    root_host()
    value=inspect_bound(cid,image)
    rows=observation.capture(plan.DOCKER+['image','inspect','--format',
        '{{json .Id}}\n{{json (index .Config.Labels "org.opencontainers.image.revision")}}\n{{json .Config.User}}',
        image],timeout=8,budget=4096).splitlines()
    require([observation.exact_json(v) for v in rows]==[image,plan.OBSERVED_OCI,'10001:1008'],
            'ORIGINAL_CURRENT_IMAGE_CHANGED')
    config={path:stable_metadata(path) for path in (plan.ROOT+'/config',plan.ROOT+'/config/host.json',
        plan.ROOT+'/config/center-keys.json',plan.ROOT+'/config/wechat.json')}
    data={path:stable_metadata(path) for path in (plan.ROOT+'/data',plan.RUN)}
    routes={path:observation.safe_file(path,body=True)[0]['sha256'] for path in observation.ROUTE_PATHS.values()}
    isolation={k:v for k,v in value.items() if k not in ('id','image','running','status')}
    live=dict(container_id=value['id'],image_id=value['image'],oci_revision=plan.OBSERVED_OCI,
        running=value['running'],user=value['user'],observed_at=now(),
        config_identity_sha256=digest(config),data_identity_sha256=digest(data),routing_sha256=digest(routes),
        isolation_sha256=digest(isolation),backup_reference_sha256=backup_reference(backup_fd))
    return live


def observe_current(*,backup_fd):
    """Future separately approved readonly root invocation, NOT run here.

    Resolves fixed original NAME once, then freezes/rechecks its exact ID/image.
    No approval, image load, journal write, private body or mutating Docker call.
    """
    root_host()
    fmt='{{json .Id}}\n{{json .Image}}'
    rows=observation.capture(plan.DOCKER+['container','inspect','--format',fmt,plan.NAME],timeout=8,budget=4096).splitlines()
    require(len(rows)==2,'EXACT_CURRENT_NAME_REQUIRED')
    cid,image=[observation.exact_json(v) for v in rows]
    require(plan.exact_hex(cid,64) and plan.image_id(image),'CURRENT_ID_IMAGE_UNKNOWN')
    first=read_current(cid,image,backup_fd);second=read_current(cid,image,backup_fd)
    require(all(type(first[k]) is type(second[k]) and first[k]==second[k] for k in first if k!='observed_at'),
            'CURRENT_OBSERVATION_CHANGED')
    final=observation.capture(plan.DOCKER+['container','inspect','--format',fmt,plan.NAME],timeout=8,budget=4096).splitlines()
    require([observation.exact_json(v) for v in final]==[cid,image],'CURRENT_NAME_REBOUND')
    return plan.current_identity(second)  # initial writer MUST be running


class LiveBindings:
    def __init__(self,current,backup_fd,approval_check):
        self.current=dict(current);self.backup_fd=os.dup(backup_fd);self.approval_check=approval_check
    def close(self):
        if self.backup_fd is not None:os.close(self.backup_fd);self.backup_fd=None
    def __call__(self):
        root_host();self.approval_check();c=self.current
        live=read_current(c['container_id'],c['image_id'],self.backup_fd)
        self.approval_check()
        require(all(live[k]==c[k] and type(live[k]) is type(c[k]) for k in c if k not in ('running','observed_at')),
                'CURRENT_PROTECTED_BINDING_CHANGED')
        return live


class Composition:
    def __init__(self,journal,bindings,transport):
        self.journal=journal;self.bindings=bindings
        self.update=controller.Update(journal,transport,execution_enabled=True)
    def close(self):
        self.journal.close();self.bindings.close()


def compose(*,approval_sha256,backup_fd,execution_enabled=False):
    """Future original root caller only. No shipped CLI turns this on.

    Approval values originate ONLY in the fixed protected root file. It binds
    this exact composition and old current metadata. Caller SHA is review input,
    not permission from HTTP/environment. No live observation is run by default.
    """
    require(execution_enabled is True,'COMPOSITION_EXECUTION_DISABLED');root_host()
    require(plan.exact_hex(approval_sha256,64),'EXACT_APPROVAL_DIGEST_REQUIRED')
    raw=protected_body(APPROVAL,approval_sha256)
    a=observation.exact_json(raw.decode('utf-8'))
    keys={'format','host','control_source_sha','product_source_sha','composition_sha256','receipt_sha256',
          'current','issued_at','expires_at','backup_verified_at','downgrade_compatibility_reviewed','actions'}
    require(type(a) is dict and set(a)==keys and type(a['format']) is int and a['format']==1,'EXACT_APPROVAL_SHAPE')
    require(a['host']==plan.HOST and a['control_source_sha']==CONTROL and a['product_source_sha']==PRODUCT
            and a['receipt_sha256']==RECEIPT_SHA and a['actions']==ACTIONS
            and a['downgrade_compatibility_reviewed'] is True,'EXACT_REVIEWED_SCOPE_REQUIRED')
    require(plan.exact_hex(a['composition_sha256'],64),'COMPOSITION_DIGEST_REQUIRED')
    c=plan.current_identity(a['current'])
    def approval_check():
        root_host();protected_body(APPROVAL,approval_sha256)
        clock=now()
        require(all(type(a[k]) is int for k in ('issued_at','expires_at','backup_verified_at'))
            and a['issued_at']<=clock<=a['expires_at']<=a['issued_at']+600
            and clock-600<=a['backup_verified_at']<=clock
            and clock-600<=c['observed_at']<=clock+30,'APPROVAL_OR_BACKUP_EXPIRED')
        protected_body(os.path.abspath(__file__),a['composition_sha256'])
        for module,sha in PINS.items():protected_body(os.path.abspath(module.__file__),sha)
    approval_check()
    receipt_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              'deploy/community-preview/f131-image-receipt.json')
    receipt=observation.exact_json(protected_body(receipt_path,RECEIPT_SHA).decode('utf-8'))
    source=dict(source_sha=PRODUCT,tree_sha=receipt['product_tree'],source_zip_sha256=receipt['source_artifact']['inner_zip_sha256'],
        artifact_id=receipt['source_artifact']['id'],artifact_sha256=receipt['source_artifact']['outer_sha256'],
        run_id=receipt['build_run_id'],push_evidence_run_id=receipt['push_evidence_run_id'],ocr_source_sha=plan.OCR_SHA)
    image=dict(source_sha=PRODUCT,tree_sha=source['tree_sha'],source_zip_sha256=source['source_zip_sha256'],
        oci_revision=PRODUCT,image_id=receipt['release_image_id'],repo_digest=None,
        image_archive_sha256=receipt['image_artifact']['inner_tar_sha256'],artifact_sha256=receipt['image_artifact']['outer_sha256'],
        artifact_id=receipt['image_artifact']['id'],run_id=receipt['build_run_id'])
    require(now()<1793072670,'FROZEN_ARTIFACT_EXPIRED')  # 2026-10-27T03:44:30Z
    candidate=plan.prepare(source,c,image)
    bindings=LiveBindings(c,backup_fd,approval_check)
    journal=None
    try:
        live=bindings();require(live['running'] is True,'ORIGINAL_OLD_WRITER_NOT_RUNNING')
        transport=controller.OriginalTransport(bindings,actual_health)
        transport.image_and_names_ready(candidate)  # NO image loading
        journal=controller.Journal.from_original_parent(candidate)  # NO parent creation
        return Composition(journal,bindings,transport)
    except BaseException:
        if journal is not None:journal.close()
        bindings.close();raise
