"""Five fixed-object readonly observations, NOT update/preview admission.

No installed source/backup path is known: report UNKNOWN without searching.
The offline bundler embeds approved readonly helpers; no installation is needed.
"""
import hashlib
import json
import math
import os
import re
import signal
import stat
import sys
import time
from scripts import community_preview_version_inspect as v
from scripts import community_preview_update_composition as approved

PRODUCT='f13155ed63a3137d41766ee587d9b4b96a81477f'
IMAGE='sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a'
COMPOSITION='b09b837b338def5db8485bda8c4fa4e98d98139f'
BASE='/opt/xuanjun-community-preview'
APPROVAL=BASE+'/update-approval.json'
JOURNAL=BASE+'/update-journal'
SOCKET=v.RUN+'/preview.sock'
PUBLIC_PINS={
 'scripts/community_preview_update_composition.py':'1afa61317d7647f7d6fb76f77c15de072f761bc500796659408434d39cc1a0f9',
 'scripts/community_preview_update_checkpoint.py':'a73c1fe8ebb71abaefeb56ca880057e23876b5c005d315e4fb1268d3087064fd',
 'scripts/community_preview_release_plan.py':'e0870cfaf7f1bb16b8664e644ec616e150b0ada93146a8d955e64c5f3f7ec4b9',
 'scripts/community_preview_upgrade.py':'2584441af33e6db1c5d24596f6cbc82077364a0b2b18554c6ba550ec8f66e0ee',
 'scripts/community_preview_version_inspect.py':'98773bcd199f5cb50d15fb3bba1b6959541a12c3f5f2a4879dcd88e5d3bb6cc3'}


def wall():
    value=time.time()
    if type(value) not in (int,float) or not math.isfinite(value) or value<=0:raise v.Hold('CLOCK_UNKNOWN')
    return int(value)


def metadata(path,directory):
    result=v.safe_file(path)
    if (result['type']=='DIRECTORY') is not directory:raise v.Hold('FIXED_OBJECT_TYPE')
    if not directory and result['nlink']!=1:raise v.Hold('FIXED_FILE_LINK')
    return result


def socket_metadata():
    parent,name=v.parent_fd(SOCKET)
    try:
        p_before=v.identity(os.fstat(parent));before=os.stat(name,dir_fd=parent,follow_symlinks=False)
        # Original socket is project-owned 0660 (nginx group); never open/read it
        # as a regular file. Parent chain retains original protected policy.
        if not stat.S_ISSOCK(before.st_mode) or before.st_uid!=v.PROJECT_UID or stat.S_IMODE(before.st_mode)!=0o660:
            raise v.Hold('ORIGINAL_SOCKET_TYPE_OWNER_MODE')
        other,leaf=v.parent_fd(SOCKET)
        try:
            if (v.identity(os.fstat(parent))!=p_before or v.identity(os.fstat(other))!=p_before or leaf!=name
                    or v.identity(os.stat(leaf,dir_fd=other,follow_symlinks=False))!=v.identity(before)):
                raise v.Hold('SOCKET_OR_PARENT_CHANGED')
        finally:os.close(other)
        return dict(status='OBSERVED',type='UNIX_SOCKET',uid=before.st_uid,gid=before.st_gid,
                    mode='0660',device=before.st_dev,inode=before.st_ino)
    finally:os.close(parent)


def health_probe(probe,private=False):
    # Reuse exact approved bounded public/private probes, not a new endpoint.
    raw=v.capture(['/usr/bin/python3','-I','-B','-S','-c',probe],timeout=10,budget=10000)
    frame=v.exact_json(raw)
    if (type(frame) is not dict or set(frame)!={'http_status','body_hex'}
            or type(frame['http_status']) is not int or frame['http_status'] not in (200,503)
            or type(frame['body_hex']) is not str or len(frame['body_hex'])>8192
            or re.fullmatch('[0-9a-f]*',frame['body_hex']) is None):raise v.Hold('HEALTH_FRAME')
    body=v.exact_json(bytes.fromhex(frame['body_hex']).decode('utf-8'))
    if type(body) is not dict:raise v.Hold('HEALTH_OBJECT')
    remote=body.get('observed_at');local=wall()
    valid=type(remote) is int and 0<=remote<=9007199254740991
    return dict(status='OBSERVED',http_status=frame['http_status'],
        transport='ORIGINAL_UNIX_SOCKET' if private else 'ANONYMOUS_HTTPS_NO_REDIRECT_PROXY',
        endpoint=SOCKET+':/community/health' if private else v.URL,
        backend_status=body.get('status') if type(body.get('status')) is str and body['status'] in ('READY','MAINTENANCE','UNAVAILABLE') else 'UNKNOWN',
        scope='PROCESS_AND_DATABASE_CONNECTIVITY' if body.get('scope')=='PROCESS_AND_DATABASE_CONNECTIVITY' else 'UNKNOWN',
        production_acceptance=False if body.get('production_acceptance') is False else 'UNKNOWN',
        runtime_source_sha=body.get('runtime_source_sha') if type(body.get('runtime_source_sha')) is str and v.SHA.fullmatch(body['runtime_source_sha']) else 'UNKNOWN',
        version_source='IMAGE_BUILD_STAMP' if body.get('version_source')=='IMAGE_BUILD_STAMP' else 'UNKNOWN',
        collection_observed_at=local,backend_observed_at=remote if valid else 'UNKNOWN',
        freshness='UNKNOWN' if not valid else 'FUTURE' if remote>local+30 else 'STALE' if local-remote>600 else 'FRESH')


def names_for(current):
    names=[v.CURRENT,v.CURRENT+'-before-'+PRODUCT[:12]+'-'+current['container_id'][:12],
                   v.CURRENT+'-failed-'+PRODUCT[:12]+'-'+current['container_id'][:12]]
    result={}
    fmt='{{json .Id}}\n{{json .Name}}\n{{json .Image}}\n{{json .State.Running}}'
    for name in names:
        try:
            rows=v.capture(v.DOCKER+['container','ls','--all','--no-trunc','--format','{"id":{{json .ID}},"name":{{json .Names}}}',
                '--filter','name=^/'+name+'$'],timeout=8,budget=4096).splitlines()
            if not rows:
                result[name]=dict(status='OBSERVED_ABSENT');continue
            if len(rows)!=1:raise v.Hold('EXACT_NAME_QUERY')
            lookup=v.exact_json(rows[0])
            if (type(lookup) is not dict or set(lookup)!={'id','name'} or lookup['name']!=name
                    or type(lookup['id']) is not str or not v.CID.fullmatch(lookup['id'])):raise v.Hold('EXACT_NAME_QUERY')
            values=[v.exact_json(r) for r in v.capture(v.DOCKER+['container','inspect','--format',fmt,lookup['id']],timeout=8,budget=4096).splitlines()]
            if (len(values)!=4 or type(values[0]) is not str or not v.CID.fullmatch(values[0])
                    or values[0]!=lookup['id'] or values[1]!='/'+name or type(values[2]) is not str or not v.IMAGE.fullmatch(values[2])
                    or type(values[3]) is not bool):raise v.Hold('NAME_FRAME')
            result[name]=dict(status='OBSERVED',container_id=values[0],image_id=values[2],running=values[3])
        except Exception:
            # Nonzero CLI cannot distinguish absent from daemon/permission error.
            result[name]=dict(status='UNKNOWN_NOT_PROVEN_ABSENT')
    current_name=result[v.CURRENT]
    if current_name.get('container_id')!=current['container_id'] or current_name.get('image_id')!=current['image_id']:
        raise v.Hold('FIXED_NAME_REBOUND')
    return result


def current_projection():
    fmt='{{json .Id}}\n{{json .Image}}'
    rows=v.capture(v.DOCKER+['container','inspect','--format',fmt,v.CURRENT],timeout=8,budget=4096).splitlines()
    if len(rows)!=2:raise v.Hold('CURRENT_SHAPE')
    cid,image=[v.exact_json(r) for r in rows]
    if type(cid) is not str or not v.CID.fullmatch(cid) or type(image) is not str or not v.IMAGE.fullmatch(image):raise v.Hold('CURRENT_IDS')
    info=approved.inspect_bound(cid,image)  # original full readonly isolation validation
    image_fmt='{{json .Id}}\n{{json .RepoDigests}}\n{{json (index .Config.Labels "org.opencontainers.image.revision")}}\n{{json .Config.User}}'
    image_info=v.project_image(v.capture(v.DOCKER+['image','inspect','--format',image_fmt,image],timeout=8,budget=4096),image)
    config={p:approved.stable_metadata(p) for p in (v.ROOT+'/config',v.ROOT+'/config/host.json',v.ROOT+'/config/center-keys.json',v.ROOT+'/config/wechat.json')}
    data={p:approved.stable_metadata(p) for p in (v.ROOT+'/data',v.RUN)}
    routes={p:v.safe_file(p,True)[0]['sha256'] for p in v.ROUTE_PATHS.values()}
    isolation={k:value for k,value in info.items() if k not in ('id','image','running','status')}
    # Exactly the four calculable composition digests. No invented backup file
    # capability: the fifth field must remain UNKNOWN without a real reference.
    return dict(status='OBSERVED_PARTIAL_NO_BACKUP_BINDING',container_id=cid,image_id=image,
        oci_revision=image_info['oci_revision'],running=info['running'],user=info['user'],observed_at=wall(),
        config_identity_sha256=approved.digest(config),data_identity_sha256=approved.digest(data),
        routing_sha256=approved.digest(routes),isolation_sha256=approved.digest(isolation),backup_reference_sha256='UNKNOWN',
        isolation_validation='ORIGINAL_NONROOT_NO_PUBLISHED_PORT_DEVICE_CAPADD',
        source_references=dict(config=config,data=data,route_sha256=routes))


def loaded_image():
    fmt='{{json .Id}}\n{{json .RepoDigests}}\n{{json (index .Config.Labels "org.opencontainers.image.revision")}}\n{{json .Config.User}}'
    value=v.project_image(v.capture(v.DOCKER+['image','inspect','--format',fmt,IMAGE],timeout=8,budget=4096),IMAGE)
    value['candidate_relation']='EXACT_ID_OCI_USER_MATCH' if value['oci_revision']==PRODUCT and value['original_nonroot_user']=='MATCH' else 'HOLD_IMAGE_METADATA_MISMATCH'
    return value


def observe(report):
    sections=report['sections']
    def collect(key,call):
        try:sections[key]=call()
        except FileNotFoundError:sections[key]=dict(status='MISSING_FIXED_PATH')
        except v.TotalDeadline:
            sections[key]=dict(status='HOLD_TOTAL_TIMEOUT');raise
        except Exception:sections[key]=dict(status='HOLD_UNKNOWN')
        return sections[key]
    collect('docker_binary',lambda:metadata('/usr/bin/docker',False))
    if sections['docker_binary'].get('status')=='OBSERVED':
        current=collect('current',current_projection)
        if current.get('container_id'):
            collect('phase_names',lambda:names_for(current))
        collect('f131_loaded_image',loaded_image)
    collect('socket',socket_metadata)
    collect('public_health',lambda:health_probe(v.HTTP_PROBE))
    if sections['socket'].get('status')=='OBSERVED':collect('private_health',lambda:health_probe(approved.PRIVATE_PROBE,True))
    for label,path,isdir in (('root_base',BASE,True),('historical_stage',v.STAGE,True),
                            ('approval',APPROVAL,False),('journal_parent',JOURNAL,True)):
        value=collect(label,lambda p=path,d=isdir:metadata(p,d))
        if label in ('approval','journal_parent'):
            required='0600' if label=='approval' else '0700'
            value['required_mode']=required
            value['protected_policy_relation']='MATCH' if value.get('status')=='OBSERVED' and value.get('mode')==required else 'HOLD_NOT_PROVEN'
    # Known original object, classified ROUTE ONLY; never relabel as data backup.
    route_backup=collect('historical_route_backup',lambda:metadata(v.STAGE+'/include.before',False))
    route_backup['scope']='ROUTE_BACKUP_ONLY_NOT_DATABASE_OR_RECOVERY_PROOF'
    sections['root_caller_sources']=dict(status='UNKNOWN_INSTALLED_PATHS_NOT_PROVIDED_NO_SEARCH',
        files={p:dict(expected_source_sha256=h,installed_path='UNKNOWN',observed_sha256='UNKNOWN',owner='UNKNOWN',mode='UNKNOWN') for p,h in PUBLIC_PINS.items()})
    sections['database_backup']=dict(status='UNKNOWN_NO_FIXED_BACKUP_REFERENCE_OR_RESTORE_PROOF',
        reference_path='UNKNOWN',reference_sha256='UNKNOWN',verified_restore='UNKNOWN',downgrade_compatibility='UNKNOWN')
    initial_socket=sections.get('socket',{})
    if initial_socket.get('status')=='OBSERVED':
        def socket_recheck():
            last=socket_metadata()
            if last!=initial_socket:raise v.Hold('SOCKET_CHANGED')
            return dict(status='OBSERVED',identity='MATCH')
        collect('socket_recheck',socket_recheck)
    public=sections.get('public_health',{});private=sections.get('private_health',{})
    report['private_public_runtime_relation']='UNKNOWN'
    if all(h.get('runtime_source_sha') not in (None,'UNKNOWN') for h in (public,private)):
        report['private_public_runtime_relation']='MATCH' if public['runtime_source_sha']==private['runtime_source_sha'] else 'DIFFERENT'
    initial=sections.get('current',{})
    if initial.get('container_id'):
        def recheck():
            last=current_projection()
            if any(last[k]!=initial[k] for k in initial if k!='observed_at'):raise v.Hold('CURRENT_BINDING_CHANGED')
            return dict(status='OBSERVED',identity_image_isolation_four_digests='MATCH',names=names_for(last))
        collect('current_recheck',recheck)
    return report


def main():
    if len(sys.argv)!=1 or os.getuid()!=0 or os.geteuid()!=0 or os.uname().nodename.split('.')[0]!=v.HOST:
        print('{"state":"HOLD_HOST_IDENTITY_OR_ARGUMENTS","site_updated":false}');return 2
    keys=('docker_binary','current','phase_names','f131_loaded_image','socket','public_health','private_health',
          'root_base','historical_stage','approval','journal_parent','root_caller_sources','database_backup','socket_recheck','current_recheck')
    report=dict(candidate='UK_PREUPDATE_FIVE_FIXED_OBJECT_READONLY',composition_source=COMPOSITION,product_source=PRODUCT,
        sections={k:dict(status='NOT_OBSERVED') for k in keys},state='HOLD_MISSING_INSTALLATION_AND_RECOVERY_PROOF',
        executable_update=False,site_updated=False,preview_acceptance='HOLD_NOT_EVALUATED',production_acceptance=False,
        snapshot_atomic=False,execution_permission='NOT_GRANTED',observation_validity_seconds=600,
        docker_boundary='CLI_DAEMON_MAY_ACCESS_ENV_PYTHON_RECEIVES_FIXED_WHITELIST_ONLY')
    def deadline(*args):raise v.TotalDeadline('TOTAL_TIMEOUT')
    previous=signal.signal(signal.SIGALRM,deadline);signal.alarm(90)
    try:observe(report)
    except (Exception,v.TotalDeadline):report['state']='HOLD_PARTIAL_BOUNDED_OBSERVATION'
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous)
    try:
        raw=json.dumps(report,sort_keys=True,allow_nan=False)
        if len(raw.encode())>32768:raise v.Hold('OUTPUT_BOUND')
        print(raw)
    except Exception:print('{"state":"HOLD_OUTPUT_BOUND","site_updated":false}')
    return 2  # Missing installation/backup cannot become admission by HTTP200.


if __name__=='__main__':raise SystemExit(main())
