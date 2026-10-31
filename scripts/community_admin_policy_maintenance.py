"""Same-image, original-Host serial maintenance; no host Python crypto assumption.
Run inside the fixed application image as its original nonroot UID, after the
original service has stopped and released its locks. Never an HTTP endpoint.
"""
import json,os,sys
from pathlib import Path
from scripts.community_admin_bootstrap import _binding,_regular,_record_identity
from scripts.community_admin_policy import policy_intent,adopt_policy
from scripts.community_admin_authority import CommunityAdminAuthority
from scripts.community_admin_recovery import ensure_backup
from scripts.community_platform_host import PlatformHost
from scripts.community_mini_host_config import load_protected
from scripts.pr122_customer_core import canonical,digest,Denied,Conflict

def run(plan,action):
    b=_binding(plan)
    if action not in ('--inspect','--adopt','--query'):raise Denied('EXACT_POLICY_ACTION_REQUIRED')
    if b['bootstrap_mode']!='CONFIGURED_ADMIN':raise Denied('EXPLICIT_BUSINESS_CONFIGURATION_REQUIRED')
    _regular(b['host_path'],b['run_uid']);info=_regular(b['center_db_path'],b['run_uid'])
    if digest(Path(b['host_path']).read_bytes())!=b['host_sha256']:raise Denied('ORIGINAL_HOST_CONFIG_CHANGED')
    if (info.st_dev,info.st_ino)!=(b['center_dev'],b['center_ino']):raise Denied('ORIGINAL_CENTER_IDENTITY_CHANGED')
    host=PlatformHost.open(b['host_path'],b['keys_path'],b['wechat_path'])
    try:
        held=os.fstat(host.center_lock)
        if (held.st_dev,held.st_ino)!=(b['center_dev'],b['center_ino']) or str(Path(host.plan['center_root'])/'center.sqlite')!=b['center_db_path']:raise Denied('ORIGINAL_CENTER_IDENTITY_CHANGED')
        if digest(Path(b['host_path']).read_bytes())!=b['host_sha256'] or load_protected(b['host_path'])!=host.plan:raise Denied('ORIGINAL_HOST_CONFIG_CHANGED')
        api=getattr(host.center,'community_admin_authority',None)
        if type(api) is not CommunityAdminAuthority or api.c is not host.center or api.project!=b['project'] or api.tenant!=b['tenant'] or api.capabilities!=frozenset(b['capabilities']) or api.workspace_scopes!=frozenset(b['workspace_scopes']):raise Denied('EXACT_COMMUNITY_AUTHORITY_COMPOSITION_REQUIRED')
        record=Path(b['identity_record_path'])
        saved=None
        if record.exists():
            _regular(str(record),b['run_uid']);saved=load_protected(str(record))
            if set(saved)!= {'kind','policy','source_pins','host_sha256','request_id'} or saved['kind']!='OWNER_TTY_COMMUNITY_POLICY_ADOPTION' or saved['request_id']!=b['request_id'] or saved['host_sha256']!=b['host_sha256'] or saved['source_pins']!=b['source_pins']:raise Denied('EXACT_POLICY_EXECUTION_RECORD_REQUIRED')
            intent=saved['policy'];execution_sha=digest(canonical(saved))
            prior=api._request(b['request_id'],dict(intent,execution_binding_sha256=execution_sha))
            if prior is not None:
                current=api.authority(prior['uid'])
                if current['revision']!=prior['revision'] or current['manifest_sha']!=prior['manifest_sha']:raise Conflict('POLICY_REQUEST_SUPERSEDED')
                return dict(prior,status='EXISTING_POLICY_COMMIT_READBACK',replayed=True,complete_delivery=False)
        intent=policy_intent(api,b['request_id'])
        execution=dict(kind='OWNER_TTY_COMMUNITY_POLICY_ADOPTION',policy=intent,source_pins=b['source_pins'],host_sha256=b['host_sha256'],request_id=b['request_id'])
        if saved is not None and saved!=execution:raise Conflict('POLICY_INPUT_CHANGED')
        if action in ('--inspect','--query'):
            return dict(status='POLICY_NOT_COMMITTED',intent=intent,backup_state=ensure_backup(host.center,b['backup_path'],b['run_uid'],digest(canonical(execution)),b['request_id'],inspect_only=True),account_written=False)
        if not sys.stdin.isatty():raise Denied('INTERACTIVE_TTY_REQUIRED')
        print(json.dumps(execution,ensure_ascii=False,sort_keys=True))
        print('仅迁移本社区超级管理员业务绑定。所有子管理员停权，不自动继承新增范围；由超级管理员重新明确授权。这些管理员在同一 Center 的所有会话（包括其他项目窗口）都将退出并需重新登录，不授予其他项目权限。')
        expected='ADOPT '+b['project']+' '+intent['to_manifest']+' REVOKE CHILDREN'
        if input('确认后输入 '+expected+': ')!=expected:raise Denied('EXACT_OWNER_POLICY_CONFIRMATION_REQUIRED')
        execution_sha=_record_identity(b['identity_record_path'],execution,b['run_uid'])
        backup=ensure_backup(host.center,b['backup_path'],b['run_uid'],execution_sha,b['request_id'])
        result=adopt_policy(api,intent,execution_sha,lambda value:value==intent)
        return dict(result,status='POLICY_COMMITTED_READBACK',backup=backup,complete_delivery=False)
    finally:host.close()

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(allow_abbrev=False);parser.add_argument('--plan',required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    for action in ('inspect','adopt','query'):group.add_argument('--'+action,action='store_true')
    args=parser.parse_args()
    try:
        value=load_protected(args.plan)
        if type(value) is dict and set(value)=={'plan','observation'}:value=value['plan']
        print(json.dumps(run(value,next('--'+x for x in ('inspect','adopt','query') if getattr(args,x))),sort_keys=True))
    except Exception:
        print(json.dumps(dict(status='HOLD',code='POLICY_CHECK_EXACT_ORIGINAL_STATE',complete_delivery=False)));raise SystemExit(1) from None
