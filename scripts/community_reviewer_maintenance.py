"""One-shot original-host maintenance integration. No listener or self-approval.

OWNER_CONFIRMATION_PIN is deliberately unfilled. Only a newly reviewed successor
may bind it to the exact real Owner confirmation after provenance verification
in the original controlled execution window. CLI/files cannot supply this pin.
Do not replace it with a permissive verifier or environment-variable admission.
"""
import contextlib
import fcntl
import argparse
import json
import os
import secrets
from pathlib import Path
from scripts.pr122_customer_core import canonical, digest, Denied, Conflict
from scripts.community_mini_host_config import load_protected
from scripts.community_platform_host import PlatformHost, _configuration, _open_provider_reader
try:
    from scripts.community_platform_reviewer_admission import ReviewerAdmission
except ImportError:  # Local candidate import, same bytes before package integration.
    from community_platform_reviewer_admission import ReviewerAdmission

OWNER_CONFIRMATION_PIN = None
# After exact actual confirmation, reviewed successor pins:
# {owner_message_id, owner_body_sha256, plan_sha256, host_base_sha256,
#  project, uid, action, request_id}. No wildcard, role chooser or expiry.


def _owner_record(path, plan, plan_sha, host_sha):
    pin=OWNER_CONFIRMATION_PIN
    fields={'owner_message_id','owner_body_sha256','plan_sha256','host_base_sha256','project','uid','action','request_id'}
    if type(pin) is not dict or set(pin)!=fields:
        raise Denied('EXACT_OWNER_CONFIRMATION_NOT_YET_BOUND')
    record=load_protected(path)
    if type(record) is not dict or set(record)!={'owner_message_id','body'} or type(record['body']) is not str:
        raise Denied('EXACT_ORIGINAL_OWNER_RECORD_REQUIRED')
    expected=dict(owner_message_id=record['owner_message_id'],owner_body_sha256=digest(record['body'].encode()),
                  plan_sha256=plan_sha,host_base_sha256=host_sha,
                  **{k:plan[k] for k in ('project','uid','action','request_id')})
    if expected!=pin or plan['approval']!={k:pin[k] for k in ('owner_message_id','owner_body_sha256')}:
        raise Denied('OWNER_CONFIRMATION_BINDING_MISMATCH')
    return pin


def _cas_mapping(path, base_sha, uid, project, granted):
    """Original Center lock must cover every cooperating config writer.

    Preserve every other field and reviewer. Atomic rename+directory fsync is
    separate from DB commit. A response lost after rename is recognized by
    reconstructing the pinned original config, not by re-granting membership.
    """
    current=load_protected(path)
    if type(current.get('reviewers')) is not dict:raise Conflict('HOST_REVIEWERS_INVALID')
    target=dict(current);target['reviewers']=dict(current['reviewers'])
    old=current['reviewers'].get(uid)
    if granted:
        if old not in (None,project):raise Conflict('HOST_REVIEWER_CONFLICT')
        target['reviewers'][uid]=project
    else:
        if old not in (None,project):raise Conflict('HOST_REVIEWER_CONFLICT')
        target['reviewers'].pop(uid,None)
    if digest(canonical(current))!=base_sha:
        original=dict(current);original['reviewers']=dict(current['reviewers'])
        if granted:original['reviewers'].pop(uid,None)
        else:original['reviewers'][uid]=project
        if current!=target or digest(canonical(original))!=base_sha:
            raise Conflict('HOST_CONFIG_CAS_DRIFT')
        return 'CONFIG_ALREADY_APPLIED'
    if current==target:return 'CONFIG_ALREADY_APPLIED'
    path=Path(path);parent=os.open(str(path.parent),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    temp='.'+path.name+'.reviewer-'+secrets.token_hex(12)
    try:
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
        with os.fdopen(fd,'wb') as out:
            out.write(canonical(target));out.flush();os.fsync(out.fileno())
        # Re-read protections + full CAS under the original exclusive host lock.
        if load_protected(str(path))!=current:raise Conflict('HOST_CONFIG_CAS_DRIFT')
        os.replace(temp,path.name,src_dir_fd=parent,dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        try:os.unlink(temp,dir_fd=parent)
        except FileNotFoundError:pass
        os.close(parent)
    if load_protected(str(path))!=target:raise Conflict('HOST_CONFIG_POSTWRITE_DRIFT')
    return 'CONFIG_APPLIED'


@contextlib.contextmanager
def _revocation_host(host_path, keys_path, wechat_path):
    """Exact original storage-lock composition, without live applicant startup.
    Expired registration must not prevent removing an already managed role.
    This branch has no login/registration/grant or application/listener surface.
    """
    from scripts import community_platform_host as original
    from scripts.community_persistent_runtime import _directory, _file, NAMES, PersistentRuntime
    from scripts.pr122_customer_core import Center
    original._require_nonroot()
    if digest(Path(original.__file__).with_name('pr122_customer_core.py').read_bytes())!=original.CORE_SHA256:
        raise Denied('PINNED_CENTER_SOURCE_REQUIRED')
    plan=load_protected(host_path);material=load_protected(keys_path)
    keys,principals,bindings,operations=_configuration(plan,material,load_protected(wechat_path))
    root=_directory(plan['center_root']);database=_file(root/'center.sqlite')
    _directory(str(root/'objects'))
    for suffix in ('-wal','-shm','-journal'):
        path=root/('center.sqlite'+suffix)
        if path.exists() or path.is_symlink():_file(path)
    runtime=_directory(plan['runtime_directory'])
    for name in NAMES:
        info=_file(runtime/(name+'.sqlite'))
        if (database.st_dev,database.st_ino)==(info.st_dev,info.st_ino):
            raise Denied('SEPARATE_CENTER_STORE_REQUIRED')
    host=PlatformHost()
    try:
        host.center_lock=os.open(str(root/'center.sqlite'),os.O_RDWR|os.O_NOFOLLOW)
        locked=os.fstat(host.center_lock)
        if (locked.st_dev,locked.st_ino)!=(database.st_dev,database.st_ino):raise Denied('CENTER_FILE_CHANGED')
        fcntl.flock(host.center_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        host.persistence=PersistentRuntime.open(plan['runtime_directory'],bindings,clock=lambda:host.center.now())
        host.center=Center(root,keys,material['active_key']);host.plan=plan
        yield host
    finally:host.close()


def execute(host_path, keys_path, wechat_path, operation, *, project=None, uid=None,
            request_id=None, admission_path=None, approval_path=None,
            plan_sha256=None, host_base_sha256=None):
    if operation not in ('inspect','query','grant','revoke','recover'):
        raise ValueError('FIXED_MAINTENANCE_ACTION_REQUIRED')
    plan=None
    if operation in ('grant','revoke','recover'):
        plan=load_protected(admission_path)
        if digest(canonical(plan))!=plan_sha256:raise Denied('REVIEWED_PLAN_REQUIRED')
        if operation in ('grant','revoke') and plan['action']!=operation.upper():
            raise Denied('EXACT_ACTION_REQUIRED')
        pin=_owner_record(approval_path,plan,plan_sha256,host_base_sha256)
    # Reuses original nonroot guard, Core pin, Center inode flock, business lock,
    # protected input validation and existing runtime. Never opens a listener.
    opener=_revocation_host if operation=='query' or (plan is not None and plan['action']=='REVOKE') else PlatformHost.open
    with opener(host_path,keys_path,wechat_path) as host:
        service=ReviewerAdmission(host.center,host.application.identity if host.application is not None else None)
        if operation=='inspect':return service.inspect(project,uid)
        if operation=='query':return service.query(request_id)
        if plan['action']=='GRANT':
            # Validate exact resulting host schema and original provider Reader
            # before member mutation. Reader construction has no provider IO.
            proposed=dict(host.plan);proposed['reviewers']=dict(host.plan['reviewers'])
            if proposed['reviewers'].get(plan['uid']) not in (None,plan['project']):raise Conflict('HOST_REVIEWER_CONFLICT')
            proposed['reviewers'][plan['uid']]=plan['project']
            _configuration(proposed,load_protected(keys_path),load_protected(wechat_path))
            _open_provider_reader(proposed['provider_reader_config'],host.center.now)
        current=service.query(plan['request_id'])
        if operation=='recover':
            if current['status']=='NOT_FOUND':raise Conflict('NO_COMMITTED_REQUEST_TO_RECOVER')
            result=current
        else:
            # Exact source-pinned record was checked above. This closure cannot
            # be supplied by HTTP, CLI or JSON and grants no broader authority.
            result=service.apply_protected(admission_path,plan_sha256,
                lambda sha,meta: sha==pin['plan_sha256'] and meta=={k:pin[k] for k in ('owner_message_id','owner_body_sha256')})
        if result.get('superseded'):raise Conflict('SUPERSEDED_REQUEST_CONFIG_RECOVERY_DENIED')
        # Recovery must also match the actual committed request digest.
        stored=service._read('COMMUNITY_PLATFORM_REVIEWER_REQUEST_V1',plan['request_id'],'')
        if stored['plan_sha256']!=plan_sha256:raise Conflict('REQUEST_REPLAY_CONFLICT')
        try:
            config=_cas_mapping(host_path,host_base_sha256,plan['uid'],plan['project'],result['status']=='GRANTED')
        except (OSError,ValueError,PermissionError):
            return dict(result,config_status='MEMBER_COMMITTED_CONFIG_PENDING')
        return dict(result,config_status=config)


def main(argv=None):
    p=argparse.ArgumentParser(description='Protected original community reviewer maintenance')
    p.add_argument('operation',choices=('inspect','query','grant','revoke','recover'))
    for arg in ('host','center-keys','wechat-secret'):p.add_argument('--'+arg,required=True)
    for arg in ('project','uid','request-id','admission-plan','owner-record','plan-sha256','host-base-sha256'):
        p.add_argument('--'+arg)
    a=p.parse_args(argv)
    try:
        result=execute(a.host,a.center_keys,a.wechat_secret,a.operation,project=a.project,uid=a.uid,
            request_id=a.request_id,admission_path=a.admission_plan,approval_path=a.owner_record,
            plan_sha256=a.plan_sha256,host_base_sha256=a.host_base_sha256)
        print(json.dumps(result,sort_keys=True));return 0
    except Exception:
        print('REVIEWER_MAINTENANCE_HOLD');return 2

if __name__=='__main__':raise SystemExit(main())
