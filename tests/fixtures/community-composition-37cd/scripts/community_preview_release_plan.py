"""Offline review compiler for the ORIGINAL UK container replacement contract.

No host/network/process/file mutation API; argv values are review data only.
It never grants execution authority, probes a host or imports the old updater.
"""
import hashlib
import json
import re

HOST='iZd7oeikknn1z21sq6ji6zZ'
NAME='xuanjun-community-preview'
ROOT='/var/lib/xuanjun-community-preview'
RUN='/run/xuanjun-community-preview'
DOCKER=['/usr/bin/docker','--host','unix:///var/run/docker.sock']
OBSERVED_OCI='2330dd55c07f58d7f45a7c4510a9761d0d4735d6'
OCR_SHA='90aca1cfca1ec2a354950c394a4b0c2689b37d13'
URL='https://uk.wenwenwenyiyiyi.work/community-preview/community/health'


def exact_hex(value,length):
    return type(value) is str and re.fullmatch('[0-9a-f]{'+str(length)+'}',value) is not None


def require(value,code):
    if not value:raise ValueError(code)


def image_id(value):
    return type(value) is str and value.startswith('sha256:') and exact_hex(value[7:],64)


def current_identity(value):
    return _current_identity(value,True)


def stopped_identity(value):
    return _current_identity(value,False)


def _current_identity(value,running):
    keys={'container_id','image_id','oci_revision','running','user','observed_at',
          'config_identity_sha256','data_identity_sha256','routing_sha256','isolation_sha256',
          'backup_reference_sha256'}
    require(type(value) is dict and set(value)==keys,'EXACT_CURRENT_METADATA_REQUIRED')
    require(exact_hex(value['container_id'],64) and image_id(value['image_id']),'CURRENT_ID_REQUIRED')
    require(value['oci_revision']==OBSERVED_OCI,'CURRENT_OCI_DIFF_REVIEW_REQUIRED')
    require(value['running'] is running and value['user']=='10001:1008','ORIGINAL_NONROOT_WRITER_REQUIRED')
    require(type(value['observed_at']) is int and value['observed_at']>0,'OBSERVATION_TIME_REQUIRED')
    for key in keys-{'container_id','image_id','oci_revision','running','user','observed_at'}:
        require(exact_hex(value[key],64),'PROTECTED_REFERENCE_REQUIRED')
    return dict(value)


def source_evidence(value):
    keys={'source_sha','tree_sha','source_zip_sha256','artifact_id','artifact_sha256','run_id','ocr_source_sha'}
    require(type(value) is dict and set(value) in (keys,keys|{'push_evidence_run_id'}),'EXACT_SOURCE_EVIDENCE_REQUIRED')
    require(exact_hex(value['source_sha'],40) and exact_hex(value['tree_sha'],40),'SOURCE_TREE_REQUIRED')
    for key in ('source_zip_sha256','artifact_sha256'):
        require(exact_hex(value[key],64),'SOURCE_DIGEST_REQUIRED')
    for key in ('artifact_id','run_id'):
        require(type(value[key]) is int and value[key]>0,'SOURCE_RUN_ARTIFACT_REQUIRED')
    if 'push_evidence_run_id' in value:
        require(type(value['push_evidence_run_id']) is int and value['push_evidence_run_id']>0,'PUSH_EVIDENCE_RUN_REQUIRED')
    require(value['ocr_source_sha']==OCR_SHA,'LOCKED_OCR_DEPENDENCY_REQUIRED')
    return dict(value)


def image_evidence(value,source):
    keys={'source_sha','tree_sha','source_zip_sha256','oci_revision','image_id','repo_digest',
          'image_archive_sha256','artifact_sha256','artifact_id','run_id'}
    require(type(value) is dict and set(value)==keys,'EXACT_IMAGE_EVIDENCE_REQUIRED')
    require(type(value['run_id']) is int and value['run_id']>0,'IMAGE_RUN_ID_REQUIRED')
    require(all(value[k]==source[k] for k in ('source_sha','tree_sha','source_zip_sha256','run_id')),
            'SAME_SOURCE_BUILD_REQUIRED')
    require(value['oci_revision']==source['source_sha'] and image_id(value['image_id']),'IMAGE_REVISION_REQUIRED')
    require(value['repo_digest'] is None or image_id(value['repo_digest']),'REPO_DIGEST_INVALID')
    for key in ('image_archive_sha256','artifact_sha256'):
        require(exact_hex(value[key],64),'IMAGE_DIGEST_REQUIRED')
    require(type(value['artifact_id']) is int and value['artifact_id']>0,'IMAGE_ARTIFACT_REQUIRED')
    return dict(value)


def run_argv(image,source):
    # Same socket/mount/uid/limits as the original UK run_args, no port publish.
    return DOCKER+['run','--pull','never','--detach','--restart','no','--name',NAME,
        '--label','community.source='+source,'--read-only','--user','10001:1008',
        '--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','64',
        '--cpus','0.5','--memory','512m','--memory-swap','512m',
        '--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=16777216,mode=1777',
        '--log-driver','json-file','--log-opt','max-size=10m','--log-opt','max-file=2',
        '--mount','type=bind,src='+ROOT+'/config,dst='+ROOT+'/config,readonly',
        '--mount','type=bind,src='+ROOT+'/data,dst='+ROOT+'/data',
        '--mount','type=bind,src='+RUN+',dst='+RUN,image,
        '--plan',ROOT+'/config/host.json','--center-keys',ROOT+'/config/center-keys.json',
        '--wechat-secret',ROOT+'/config/wechat.json']


def prepare(source,current=None,image=None):
    return _prepare(source,current,image,False)


def prepare_stopped(source,current,image):
    return _prepare(source,current,image,True)


def _prepare(source,current,image,stopped):
    source=source_evidence(source)
    if current is not None:current=stopped_identity(current) if stopped else current_identity(current)
    if image is not None:image=image_evidence(image,source)
    missing=[]
    if current is None:missing.append('EXACT_CURRENT_ID_IMAGE_CONFIG_DATA_ROUTE_ISOLATION_BACKUP_METADATA')
    if image is None:missing.append('SAME_SHA_IMAGE_BUILD_ARTIFACT_AND_DIGEST_NOT_EXECUTED')
    report=dict(format=1,purpose='OFFLINE_REVIEW_ONLY_NOT_AN_EXECUTOR',host=HOST,source=source,
        observed_current_oci=OBSERVED_OCI,current=current,image=image,executable=False,
        execution_approved=False,ocr_enabled=False,payments=False,site_executed=False,
        state='HOLD_MISSING_EVIDENCE' if missing else 'REVIEW_CANDIDATE_NOT_AUTHORIZED',missing=missing,
        manual_preview=dict(workflow='.github/workflows/chatgpt-community-wechat-sp-offline.yml',
            branch='feature/chatgpt-community-wechat-sp-offline-20261017',preview_enabled=False,
            preview_source_sha=source['source_sha'],preview_target='uk-path-candidate',
            preview_evidence_run_id=str(source.get('push_evidence_run_id',source['run_id'])),entry_page='pages/home/index',scene=None,
            next_enable_requires='ROOT_REVIEW_AND_EXPLICIT_OWNER_PREVIEW_AUTHORIZATION'),
        actions=[])
    if missing:return report
    require(current['image_id']!=image['image_id'],'ALREADY_CURRENT_NO_REPLACEMENT')
    attempt='community-update-'+source['source_sha'][:12]+'-'+current['container_id'][:12]
    rollback_name=NAME+'-before-'+source['source_sha'][:12]+'-'+current['container_id'][:12]
    failed_name=NAME+'-failed-'+source['source_sha'][:12]+'-'+current['container_id'][:12]
    report.update(attempt=attempt,rollback_name=rollback_name,failed_name=failed_name,
        receipt_root='/opt/xuanjun-community-preview/'+attempt,
        actions=[
            dict(phase='PREPARED',requires=['ROOT_0700_ATTEMPT_O_EXCL_NOFOLLOW_DURABLE_JOURNAL',
                'RECHECK_EXACT_CURRENT_AND_PROTECTED_REFERENCES','EXISTING_OLD_ROLLBACK_UNTOUCHED',
                'CANDIDATE_IMAGE_ALREADY_LOADED_EXACT_DIGEST','FRESH_BACKUP_AND_DOWNGRADE_REVIEW']),
            dict(phase='OLD_STOP_INTENT',argv=DOCKER+['stop','--time','10',current['container_id']],
                postcondition='EXACT_OLD_STOPPED_AND_OWN_SOCKET_REMOVED'),
            dict(phase='OLD_RENAME_INTENT',argv=DOCKER+['rename',current['container_id'],rollback_name],
                postcondition='EXACT_OLD_RETAINED_NEVER_DELETE'),
            dict(phase='NEW_RUN_INTENT',argv=run_argv(image['image_id'],source['source_sha']),
                postcondition='PERSIST_ACTUAL_NEW_64_HEX_ID_BEFORE_NEXT_ACTION'),
            dict(phase='VERIFY_ONLY',requires=['EXACT_NEW_ID_IMAGE_NONROOT_ISOLATION_MOUNTS',
                'ROUTES_UNCHANGED','PRIVATE_AND_PUBLIC_FRESH_RUNTIME_SOURCE_IMAGE_MATCH',
                'RECHECK_OLD_STOPPED_NEW_ONLY_WRITER']),
            dict(phase='COMMITTED',requires=['DURABLE_SUCCESS_RECEIPT','RETAIN_ORIGINAL_CONFIG_DATA_AND_OLD_CONTAINER'])],
        rollback=dict(trigger='KNOWN_FAILURE_ONLY_AFTER_EXACT_NEW_RUN_RECEIPT',
            first='PERSIST_FAILURE_AND_ROLLBACK_INTENT',new_stop='EXACT_NEW_RECEIPT_ID_ONLY',
            new_stopped_required=True,socket_removed_required=True,old_identity=current,
            old_rename_argv=DOCKER+['rename',current['container_id'],NAME],
            old_start_argv=DOCKER+['start',current['container_id']],failed_name=failed_name,
            verify='ORIGINAL_ID_IMAGE_CONFIG_DATA_ROUTE_AND_ORIGINAL_PROCESS_DB_HEALTH',
            runtime_sha_required_for_old=False,preview_after_rollback='HOLD',
            database_restore='NOT_AUTOMATIC_NOT_PROVEN',atomicity='SERIAL_RECOVERY_NOT_ATOMIC_DOCKER_TRANSACTION'),
        stop_rules=['UNKNOWN_TIMEOUT_OR_MISSING_RECEIPT_INSPECT_SAME_ATTEMPT_ONLY',
            'NO_RETRY_NO_NEW_ATTEMPT_NO_SECOND_WRITER','CHANGED_ID_CONFIG_DATA_ROUTE_OR_BACKUP_STOP',
            'EXISTING_PARTIAL_JOURNAL_STOP','RECOVERY_MUST_NEVER_START_OLD_WHILE_NEW_STOP_IS_UNKNOWN'])
    if stopped:
        report.update(handoff_mode='STOPPED_HANDOFF_V1',handoff_version=1)
        report['attempt']+='-stopped-v1'
        report['receipt_root']+='-stopped-v1'
    report['plan_sha256']=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return report


def next_phase(phase,event):
    # Pure transaction model. No callable actions or journal writer are exported.
    if event=='UNKNOWN':return 'HOLD_INSPECT_SAME_ATTEMPT'
    transitions={('PREPARED','OLD_STOPPED'):'OLD_STOPPED',('OLD_STOPPED','OLD_RENAMED'):'OLD_RETAINED',
        ('OLD_RETAINED','NEW_RECEIPT'):'NEW_KNOWN',('NEW_KNOWN','EXACT_HEALTH'):'COMMITTED',
        ('NEW_KNOWN','KNOWN_FAILURE'):'ROLLBACK_STOP_NEW',('ROLLBACK_STOP_NEW','NEW_STOPPED'):'ROLLBACK_RENAME_NEW',
        ('ROLLBACK_RENAME_NEW','NEW_RENAMED_SOCKET_ABSENT'):'ROLLBACK_RESTORE_OLD',
        ('ROLLBACK_RESTORE_OLD','OLD_EXACT_READY'):'ROLLED_BACK_PREVIEW_HOLD'}
    require((phase,event) in transitions,'UNPROVED_TRANSACTION_TRANSITION')
    return transitions[(phase,event)]


def exact_health(value,source_sha,image_revision,now):
    if (type(value) is not dict or type(now) is not int or not exact_hex(source_sha,40)
            or type(value.get('http_status')) is not int or value.get('http_status')!=200 or value.get('url')!=URL
            or value.get('status')!='READY' or value.get('scope')!='PROCESS_AND_DATABASE_CONNECTIVITY'
            or value.get('production_acceptance') is not False
            or value.get('runtime_source_sha')!=source_sha or image_revision!=source_sha
            or value.get('version_source')!='IMAGE_BUILD_STAMP'):return False
    observed=value.get('observed_at')
    return type(observed) is int and now-600<=observed<=now+30
