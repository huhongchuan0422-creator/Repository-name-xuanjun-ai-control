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
import threading
from scripts import community_preview_update_checkpoint as controller
from scripts import community_preview_release_plan as plan
from scripts import community_preview_upgrade as original
from scripts import community_preview_version_inspect as observation

REFERENCE_UID=0  # fixed production root owner; no argument/environment override
APPROVAL='/opt/xuanjun-community-preview/update-approval.json'  # proposed, never created
PRODUCT='f13155ed63a3137d41766ee587d9b4b96a81477f'
CONTROL='a9324156f94040bb6ff0243815bb91abe2f67b2a'
PINS={controller:'e9029ca3e0c36fb1656995fcbe77f46739ee7abfc490adbd0cf4808f0e41b826',
      plan:'81c01a2f94ff71c0af4555b9026a60db0b5ce226a158601e1cf1b6aa4b646fae',
      original:'2584441af33e6db1c5d24596f6cbc82077364a0b2b18554c6ba550ec8f66e0ee',
      observation:'98773bcd199f5cb50d15fb3bba1b6959541a12c3f5f2a4879dcd88e5d3bb6cc3'}
RECEIPT_SHA='cba144af0ca2f753413f7bdcec92625c370c479c4708b1d4a1db0b35907c8b45'
ACTIONS=['ORIGINAL_CONTAINER_STOP_RENAME_RUN','KNOWN_FAILURE_SERIAL_RECOVERY','JOURNAL_WRITES']


def require(ok,reason):
    if not ok:raise controller.Hold(reason)


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def canonical_isolation(value):
    """Canonicalize only Docker spellings already accepted by validate()."""
    result=dict(value)
    if result.get('network')=='default':result['network']='bridge'
    if result.get('security')==['no-new-privileges:true']:
        result['security']=['no-new-privileges']
    return result


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
    require(stat.S_ISREG(before.st_mode) and before.st_uid==REFERENCE_UID and stat.S_IMODE(before.st_mode)==0o600
            and before.st_nlink==1 and before.st_size<=65536,'PROTECTED_BACKUP_REFERENCE_REQUIRED')
    value=stable_metadata(path)
    after=os.fstat(fd)
    require(observation.identity(before)==observation.identity(after)
            and value['device']==after.st_dev and value['inode']==after.st_ino,'BACKUP_REFERENCE_REPLACED')
    return digest({'path':path,'metadata':value})


INITIALIZE_ENTRYPOINT=['python']
INITIALIZE_CMD=['-B','-m','scripts.community_first_install','--plan',
    plan.ROOT+'/config/initialize.json','--center-keys',plan.ROOT+'/config/center-keys.json']
NORMAL_ENTRYPOINT=['python','-B','-m','scripts.community_platform_host']
NORMAL_CMD=['--plan',plan.ROOT+'/config/host.json','--center-keys',
    plan.ROOT+'/config/center-keys.json','--wechat-secret',plan.ROOT+'/config/wechat.json']


def inspect_bound(cid,image,historical_initialize=False):
    # Same original typed projection/validation, with bounded original readonly
    # child transport; additionally prove no published port/device/cap addition.
    # The one historical initialize container has its own exact, source-backed
    # CLI contract. All non-command security and resource checks remain original.
    fields=original.INSPECT_FIELDS+[('ports','.HostConfig.PortBindings'),
        ('published','.NetworkSettings.Ports'),('devices','.HostConfig.Devices'),('capadd','.HostConfig.CapAdd')]
    fmt='\n'.join('{{json '+field+'}}' for _,field in fields)
    rows=observation.capture(plan.DOCKER+['container','inspect','--format',fmt,cid],timeout=8,budget=32768).splitlines()
    require(len(rows)==len(fields),'CURRENT_INSPECT_SHAPE')
    value={key:observation.exact_json(raw) for (key,_),raw in zip(fields,rows)}
    require(type(value['running']) is bool,'CURRENT_RUNNING_UNKNOWN')
    for key in ('cpu','memory','swap','pids'):require(type(value[key]) is int,'CURRENT_RESOURCE_TYPE')
    for key in ('readonly','privileged'):require(type(value[key]) is bool,'CURRENT_ISOLATION_TYPE')
    validation_value=value
    if historical_initialize:
        require(value['entrypoint']==INITIALIZE_ENTRYPOINT,'LEGACY_INITIALIZE_ENTRYPOINT_CHANGED')
        require(value['cmd']==INITIALIZE_CMD,'LEGACY_INITIALIZE_CMD_CHANGED')
        # The one historical first-install container is intentionally network-isolated.
        # Pin this exception exactly; never permit network=none for normal service containers.
        require(value['network']=='none','LEGACY_INITIALIZE_NETWORK_CHANGED')
        # Historical initializer predates the runtime socket mount: exactly two binds.
        expected_initialize_mounts={
            (plan.ROOT+'/config',plan.ROOT+'/config',False),
            (plan.ROOT+'/data',plan.ROOT+'/data',True)}
        mounts=value['mounts']
        require(len(mounts)==2 and all(m.get('Type')=='bind' for m in mounts)
                and {(m['Source'],m['Destination'],m['RW']) for m in mounts}==expected_initialize_mounts,
                'LEGACY_INITIALIZE_MOUNTS_CHANGED')
        validation_value=dict(value)
        validation_value['entrypoint']=NORMAL_ENTRYPOINT
        validation_value['cmd']=NORMAL_CMD
        validation_value['network']='bridge'
        # The shared normal-service validator expects the later runtime socket mount.
        # Add it only to the temporary validation projection, never to observed facts.
        validation_value['mounts']=list(mounts)+[
            {'Type':'bind','Source':plan.RUN,'Destination':plan.RUN,'RW':True}]
    try:
        original.validate(validation_value,image,cid,running=value['running'])
    except original.Rejected as error:
        # Convert only the fixed validator's enum-like reason; never surface raw details.
        reason=str(error)
        require(re.fullmatch('[A-Z][A-Z0-9_]{0,95}',reason) is not None,
                'LEGACY_INITIALIZE_VALIDATION_UNKNOWN')
        raise controller.Hold(reason) from None
    require(value['ports'] in (None,{}) and value['published'] in (None,{})
            and value['devices'] in (None,[]) and value['capadd'] in (None,[]),'NO_NEW_PORT_DEVICE_CAPABILITY')
    return value

# Historical denied-request diagnostics only; never an acceptance path.
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


def socket_binding():
    """Protected stat-only binding of the ORIGINAL Unix socket, no connection."""
    path=plan.RUN+'/preview.sock';parent,name=observation.parent_fd(path)
    try:
        before_parent=observation.identity(os.fstat(parent))
        before=os.stat(name,dir_fd=parent,follow_symlinks=False)
        require(stat.S_ISSOCK(before.st_mode) and before.st_uid==observation.PROJECT_UID
            and before.st_gid==1008 and stat.S_IMODE(before.st_mode)==0o660 and before.st_nlink==1,
            'EXACT_ORIGINAL_SOCKET_REQUIRED')
        current,leaf=observation.parent_fd(path)
        try:
            require(leaf==name and observation.identity(os.fstat(parent))==before_parent
                and observation.identity(os.fstat(current))==before_parent
                and observation.identity(os.stat(leaf,dir_fd=current,follow_symlinks=False))==observation.identity(before),
                'SOCKET_OR_PARENT_CHANGED')
        finally:os.close(current)
        return dict(device=before.st_dev,inode=before.st_ino,uid=before.st_uid,gid=before.st_gid,
            mode=stat.S_IMODE(before.st_mode),mtime_ns=before.st_mtime_ns,ctime_ns=before.st_ctime_ns)
    finally:os.close(parent)


class BoundHttpsHealth:
    """ONE anonymous HTTPS response bracketed by protected original-host facts.

    No private request, proxy header, identity switch or independent dual-path
    assertion. Journal IDs/plan and root live readers are the authority source.
    """
    def __init__(self,journal,bindings):
        require(journal is not None and callable(bindings),'PROTECTED_HEALTH_CONTEXT_REQUIRED')
        self.journal=journal;self.bindings=bindings;self.last_evidence=None;self.last_time=None
        self.plan_fingerprint=digest(journal.plan)
    def clock(self):
        value=now()
        require(self.last_time is None or value>=self.last_time,'HEALTH_CLOCK_REVERSED')
        self.last_time=value;return value
    def checked_live(self,current,rollback):
        live=self.bindings()
        require(type(live) is dict and set(live)==set(current)
            and all(type(live[k]) is type(current[k]) for k in current)
            and all(live[k]==current[k] for k in current if k not in ('running','observed_at')),
            'HEALTH_PROTECTED_SOURCE_INVALID')
        clock=self.clock()
        require(clock-600<=live['observed_at']<=clock+30,'HEALTH_PROTECTED_SOURCE_EXPIRED')
        require(live['running'] is rollback,'HEALTH_OLD_WRITER_STATE_CHANGED')
        return live
    def snapshot(self,frozen):
        root_host();j=self.journal;p=j.plan;c=p['current']
        require(digest(p)==self.plan_fingerprint,'HEALTH_PLAN_CHANGED')
        require(not j.poisoned and threading.get_ident()==j.owner and j.state==frozen
            and frozen['plan_sha256']==p['plan_sha256'],'HEALTH_JOURNAL_CHANGED')
        new=frozen['new_id'];require(plan.exact_hex(new,64) and new!=c['container_id'],'HEALTH_EXACT_NEW_ID_REQUIRED')
        rollback=frozen['phase']=='RECOVERY_START_OLD_INTENT'
        require(rollback or frozen['phase']=='NEW_KNOWN','HEALTH_PHASE_NOT_ADMISSIBLE')
        live=self.checked_live(c,rollback)
        old=inspect_bound(c['container_id'],c['image_id']);new_info=inspect_bound(new,p['image']['image_id'])
        require(old['running'] is rollback and new_info['running'] is (not rollback),'HEALTH_WRITER_PAIR_CHANGED')
        target=c['container_id'] if rollback else new
        image=c['image_id'] if rollback else p['image']['image_id']
        revision=c['oci_revision'] if rollback else p['source']['source_sha']
        require(rollback or revision==PRODUCT,'HEALTH_FIXED_PRODUCT_REQUIRED')
        fmt='{{json .Id}}\n{{json (index .Config.Labels "org.opencontainers.image.revision")}}\n{{json .Config.User}}'
        rows=observation.capture(plan.DOCKER+['image','inspect','--format',fmt,image],timeout=8,budget=4096).splitlines()
        require([observation.exact_json(v) for v in rows]==[image,revision,'10001:1008'],'HEALTH_IMAGE_OCI_CHANGED')
        fmt='{{json .Id}}\n{{json .Image}}'
        rows=observation.capture(plan.DOCKER+['container','inspect','--format',fmt,plan.NAME],timeout=8,budget=4096).splitlines()
        require([observation.exact_json(v) for v in rows]==[target,image],'HEALTH_ROUTE_TARGET_CHANGED')
        routes={path:observation.safe_file(path,body=True)[0]['sha256'] for path in observation.ROUTE_PATHS.values()}
        require(routes[original.INC]==hashlib.sha256(original.FRAGMENT).hexdigest(), 'HEALTH_FIXED_COMMUNITY_ROUTE_REQUIRED')
        require(digest(routes)==c['routing_sha256'] and live['routing_sha256']==c['routing_sha256'], 'HEALTH_ROUTE_BINDING_CHANGED')
        sock=socket_binding()
        # Recheck authority after bounded host reads as well as after HTTPS.
        require(self.checked_live(c,rollback)['running'] is rollback and j.state==frozen,'HEALTH_SOURCE_CHANGED')
        self.clock()
        return dict(target_id=target,image_id=image,oci_revision=revision,socket=sock,routes=routes,
            live={k:v for k,v in live.items() if k!='observed_at'},rollback=rollback)
    def __call__(self):
        self.last_evidence=None;frozen=dict(self.journal.state);started=self.clock()
        before=self.snapshot(frozen)
        public=read_health_probe(observation.HTTP_PROBE)  # ONE fixed anonymous GET via real Nginx
        after=self.snapshot(frozen);finished=self.clock()
        require(before==after,'HEALTH_HOST_BINDING_CHANGED_DURING_RESPONSE')
        require(public['scope']=='PROCESS_AND_DATABASE_CONNECTIVITY' and public['production_acceptance'] is False
            and type(public['status']) is str and public['status'] in ('READY','MAINTENANCE','UNAVAILABLE')
            and finished-600<=public['observed_at']<=finished+30,'HEALTH_PUBLIC_EVIDENCE_UNKNOWN')
        if not before['rollback']:
            require(public['runtime_source_sha']==before['oci_revision']==PRODUCT
                and public['version_source']=='IMAGE_BUILD_STAMP','HEALTH_RUNTIME_VERSION_UNKNOWN')
        elif public['runtime_source_sha'] is not None or public['version_source'] is not None:
            require(public['runtime_source_sha']==before['oci_revision'] and public['version_source']=='IMAGE_BUILD_STAMP',
                'ROLLBACK_RUNTIME_VERSION_INCONSISTENT')
        self.last_evidence=dict(contract='ANONYMOUS_HTTPS_ORIGINAL_NGINX_PATH',independent_private_health=False,
            target_id=before['target_id'],image_id=before['image_id'],oci_revision=before['oci_revision'],
            binding_sha256=digest(before),started_at=started,finished_at=finished,
            backend_observed_at=public['observed_at'],runtime_source_sha=public['runtime_source_sha'],
            version_source=public['version_source'],scope='LEGACY_ROLLBACK_PROCESS_DB_ONLY' if before['rollback'] else 'EXACT_PRODUCT_RUNTIME_AND_HOST_BINDING')
        return public


def actual_health(journal=None,bindings=None):
    # Unbound use cannot fall back to a bare public GET or synthetic authority.
    require(journal is not None and bindings is not None,'PROTECTED_HEALTH_CONTEXT_REQUIRED')
    return BoundHttpsHealth(journal,bindings)()


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
    isolation=canonical_isolation({k:v for k,v in value.items() if k not in ('id','image','running','status')})
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
        self.current=dict(current);self.backup_fd=os.dup(backup_fd);self.approval_check=approval_check;self.cleanup_unproven=False
    def close(self):
        if self.cleanup_unproven:raise controller.Hold('LIVE_BINDINGS_CLEANUP_UNKNOWN')
        fd=self.backup_fd;self.backup_fd=None
        if fd is None:return
        try:os.close(fd)
        except BaseException:
            self.cleanup_unproven=True
            raise controller.Hold('LIVE_BINDINGS_CLEANUP_UNKNOWN')
    def __call__(self):
        root_host();self.approval_check();c=self.current
        live=read_current(c['container_id'],c['image_id'],self.backup_fd)
        self.approval_check()
        require(all(live[k]==c[k] and type(live[k]) is type(c[k]) for k in c if k not in ('running','observed_at')),
                'CURRENT_PROTECTED_BINDING_CHANGED')
        return live


class Composition:
    def __init__(self,journal,bindings,transport):
        self.journal=journal;self.bindings=bindings;self.cleanup_unproven=False
        self.update=controller.Update(journal,transport,execution_enabled=True)
    def close(self):
        if self.cleanup_unproven:raise controller.Hold('COMPOSITION_CLEANUP_UNKNOWN')
        unknown=False
        journal=self.journal;self.journal=None
        bindings=self.bindings;self.bindings=None
        if journal is not None:
            try:journal.close()
            except BaseException:unknown=True
        if bindings is not None:
            try:bindings.close()
            except BaseException:unknown=True
        if unknown:
            self.cleanup_unproven=True
            raise controller.Hold('COMPOSITION_CLEANUP_UNKNOWN')


def exact_stage_names(candidate,new_id=None):
    """Bounded names/IDs only; never a full Docker JSON/Env projection."""
    fmt='{"id":{{json .ID}},"name":{{json .Names}}}'
    rows=observation.capture(plan.DOCKER+['container','ls','--all','--no-trunc','--format',fmt,
        '--filter','name=^/xuanjun-community-preview'],timeout=8,budget=16384).splitlines()
    require(len(rows)<=64,'CONTAINER_NAMES_UNKNOWN')
    names={};ids=set()
    for row in rows:
        value=observation.exact_json(row)
        require(type(value) is dict and set(value)=={'id','name'} and plan.exact_hex(value['id'],64)
            and type(value['name']) is str and re.fullmatch('xuanjun-community-preview[A-Za-z0-9_.-]*',value['name']) is not None,
            'CONTAINER_NAME_FRAME_UNKNOWN')
        require(value['name'] not in names and value['id'] not in ids,'DUPLICATE_CONTAINER_NAME_OR_ID')
        names[value['name']]=value['id'];ids.add(value['id'])
    old=candidate['current']['container_id']
    if new_id is None:
        require(names.get(plan.NAME)==old and candidate['rollback_name'] not in names
            and candidate['failed_name'] not in names,'INITIAL_CONTAINER_NAMES_CHANGED')
    else:
        require(names.get(plan.NAME)==new_id and names.get(candidate['rollback_name'])==old
            and candidate['failed_name'] not in names,'RECOVERY_CONTAINER_NAME_OWNERSHIP_CHANGED')


def recovery_admission(journal,transport,bindings):
    """Only a fully validated same-plan KNOWN_FAILURE can admit recover().

    Other durable intents, UNKNOWN and terminal records remain inspect-only;
    this does not resume/retry a mutation or rewrite the original history.
    """
    p=journal.plan;new_id=journal.state['new_id']
    require(journal.state['phase']=='KNOWN_FAILURE' and plan.exact_hex(new_id,64)
            and new_id!=p['current']['container_id'],'KNOWN_FAILURE_EXACT_NEW_RECEIPT_REQUIRED')
    require(bindings()['running'] is False,'RECOVERY_OLD_WRITER_MUST_BE_STOPPED')
    transport.inspect(p['current']['container_id'],p['current']['image_id'],False)
    # A known new writer may already be stopped; original recover proves state
    # before deciding whether its single stop is needed. No unknown bool coercion.
    inspect_bound(new_id,p['image']['image_id'])
    fmt='{{json .Id}}\n{{json (index .Config.Labels "org.opencontainers.image.revision")}}\n{{json .Config.User}}'
    rows=observation.capture(plan.DOCKER+['image','inspect','--format',fmt,p['image']['image_id']],timeout=8,budget=4096).splitlines()
    require([observation.exact_json(v) for v in rows]==[p['image']['image_id'],PRODUCT,'10001:1008'],
            'RECOVERY_LOADED_IMAGE_CHANGED')
    exact_stage_names(p,new_id)
    require(bindings()['running'] is False,'RECOVERY_OLD_WRITER_MUST_BE_STOPPED')
    transport.inspect(p['current']['container_id'],p['current']['image_id'],False)
    inspect_bound(new_id,p['image']['image_id'])
    exact_stage_names(p,new_id)


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
        live=bindings()  # protected identity is live; running is phase-dependent
        transport=controller.OriginalTransport(bindings,actual_health)
        # Validate the existing complete protected history and same-attempt lock
        # BEFORE applying first-run gates. Journal never creates its parent.
        journal=controller.Journal.from_original_parent(candidate)
        transport.health=BoundHttpsHealth(journal,bindings)
        if journal.state['phase']=='PREPARED':
            require(live['running'] is True,'ORIGINAL_OLD_WRITER_NOT_RUNNING')
            transport.image_and_names_ready(candidate)  # original FIRST-run gate only
            exact_stage_names(candidate)
        elif journal.state['phase']=='KNOWN_FAILURE':
            recovery_admission(journal,transport,bindings)
        else:raise controller.Hold('EXISTING_PHASE_INSPECT_ONLY_NO_AUTOMATIC_RESUME')
        return Composition(journal,bindings,transport)
    except BaseException as error:
        cleanup_unknown=False
        if journal is not None:
            try:journal.close()
            except BaseException:cleanup_unknown=True
        try:bindings.close()
        except BaseException:cleanup_unknown=True
        if cleanup_unknown:raise controller.Hold('COMPOSE_CLEANUP_UNKNOWN') from error
        raise

def exact_stopped_names(candidate,phase,new_id=None,pre_action=False):
    """Stopped-handoff full prefix inventory for every durable phase."""
    require(candidate.get('handoff_mode')=='STOPPED_HANDOFF_V1','EXPLICIT_STOPPED_MODE_REQUIRED')
    fmt='{"id":{{json .ID}},"name":{{json .Names}}}'
    rows=observation.capture(plan.DOCKER+['container','ls','--all','--no-trunc','--format',fmt,
        '--filter','name=^/xuanjun-community-preview'],timeout=8,budget=16384).splitlines()
    require(len(rows)<=64,'CONTAINER_NAMES_UNKNOWN')
    names={}
    before='xuanjun-community-preview-before-2330dd55'
    initialize='xuanjun-community-preview-initialize'
    allowed={plan.NAME,candidate['rollback_name'],candidate['failed_name'],before,initialize}
    for row in rows:
        value=observation.exact_json(row)
        require(type(value) is dict and set(value)=={'id','name'} and plan.exact_hex(value['id'],64)
             and value['name'] in allowed and value['name'] not in names
             and value['id'] not in names.values(),'STOPPED_NAME_INVENTORY_CHANGED')
        names[value['name']]=value['id']
    historical=(
        (before,'36b54db9973ee39bc71e5e8f8532ee52b79390531c79f593ce57d553a91122cc',
         'sha256:7fb56688456d5f4d46599d34e2bf8496cbbbd3f3181ded3bab70a2de953e6c30',
         'LEGACY_BEFORE_2330_NOT_STOPPED'),
        (initialize,'ef62749e3efb1b41f69d241f0fe4aab5d6a4fb7356c2f732eff4522f947ffa21',
         'sha256:7fb56688456d5f4d46599d34e2bf8496cbbbd3f3181ded3bab70a2de953e6c30',
         'LEGACY_INITIALIZE_NOT_STOPPED'))
    for name,cid,image,error in historical:
        if name in names:
            require(names[name]==cid and (inspect_bound(cid,image,True) if name==initialize else inspect_bound(cid,image))['running'] is False,error)
    old=candidate['current']['container_id'];rb=candidate['rollback_name'];failed=candidate['failed_name']
    pre=('PREPARED','STOPPED_HANDOFF_ACCEPTED','OLD_RENAME_INTENT')
    retained=('OLD_RETAINED','NEW_RUN_INTENT')
    live_new=('NEW_KNOWN','KNOWN_FAILURE','RECOVERY_STOP_NEW_INTENT','COMMITTED')
    if phase in pre:
        require(names.get(plan.NAME)==old and rb not in names and failed not in names,'INITIAL_STOPPED_NAME_CHANGED')
    elif phase in retained:
        require(plan.NAME not in names and names.get(rb)==old and failed not in names,'RETAINED_STOPPED_NAME_CHANGED')
    elif phase in live_new:
        require(plan.exact_hex(new_id,64) and names.get(plan.NAME)==new_id and names.get(rb)==old
                and failed not in names,'NEW_WRITER_NAME_CHANGED')
    elif phase in ('RECOVERY_RENAME_NEW_INTENT',):
        before=(names.get(plan.NAME)==new_id and names.get(rb)==old and failed not in names)
        after=(plan.NAME not in names and names.get(rb)==old and names.get(failed)==new_id)
        require(plan.exact_hex(new_id,64) and (before if pre_action else before or after),'RECOVERY_NEW_NAME_CHANGED')
    elif phase in ('RECOVERY_RESTORE_OLD_INTENT',):
        before=(plan.NAME not in names and names.get(rb)==old and names.get(failed)==new_id)
        after=(names.get(plan.NAME)==old and rb not in names and names.get(failed)==new_id)
        require(plan.exact_hex(new_id,64) and (before if pre_action else before or after),'RECOVERY_FAILED_NAME_CHANGED')
    elif phase in ('RECOVERY_START_OLD_INTENT','ROLLED_BACK_PREVIEW_HOLD'):
        require(plan.exact_hex(new_id,64) and names.get(plan.NAME)==old and rb not in names
                and names.get(failed)==new_id,'RECOVERY_OLD_NAME_CHANGED')
    else:raise controller.Hold('PHASE_NAME_INVENTORY_INSPECT_ONLY')
    return True
