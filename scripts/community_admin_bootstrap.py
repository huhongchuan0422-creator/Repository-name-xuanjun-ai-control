"""Original-host, nonroot serial bootstrap candidate. NOT production-bound.

No alternate endpoint or database. Binding must be independently reviewed after
all business route integrations pass. None means no account/config mutation.
"""
import getpass
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
from pathlib import Path
from scripts.community_platform_host import PlatformHost
from scripts.community_mini_host_config import load_protected
from scripts.community_admin_authority import CommunityAdminAuthority
from scripts.pr122_customer_core import canonical, digest, email, Denied

REVIEWED_BINDING = None
# Conversation provenance only. These hashes are not permits or execution tokens.
OWNER_SOURCE_MESSAGES = (
 ('Sentinel_6954f66b272c8191aa0ac234c3e01b31','你给代码指令，我去英国服务器里生成审核员'),
 ('Sentinel_2a9a1a5e51688191b7ad265699d808a6','这个审核员就是管理后台全账户管理员'),
 ('Sentinel_a578e55bb308819182d5292e10640166','不要只给他审核权限，而是全部权限'),
 ('Sentinel_639747a72024819185a3aea9eeb05b39','这是超级管理员，然后可以配置其他管理员（权限不完整的，被超级管理员限制的）'),
)


def _binding(candidate=None):
    b=REVIEWED_BINDING if candidate is None else candidate
    fields={'version','bootstrap_mode','owner_message_id','owner_body_sha256','project','tenant','identity_mode','identity_record_path','request_id','host_path','host_sha256','keys_path','wechat_path','center_db_path','center_dev','center_ino','run_uid','backup_path','capabilities','workspace_scopes','route_coverage_sha256','source_pins'}
    if type(b) is not dict or set(b)!=fields or b['version']!=1:
        raise Denied('COMPLETE_REVIEWED_BOOTSTRAP_NOT_BOUND')
    if b['bootstrap_mode'] not in ('CORE_FIRST_ENABLE','CONFIGURED_ADMIN'):raise Denied('EXACT_BOOTSTRAP_MODE_REQUIRED')
    if b['owner_message_id']!=OWNER_SOURCE_MESSAGES[-1][0] or b['owner_body_sha256']!=digest(OWNER_SOURCE_MESSAGES[-1][1].encode()):raise Denied('ORIGINAL_TASK_SOURCE_REFERENCE_CHANGED')
    if b['identity_mode']!='OWNER_TTY_CHOICE':raise Denied('EXACT_OWNER_TTY_CONFIRMATION_REQUIRED')
    if b['run_uid']==0 or os.geteuid()!=b['run_uid']:
        raise Denied('EXACT_NONROOT_OWNER_REQUIRED')
    # Review artifact pins only; not a client assertion that all routes exist.
    if type(b['source_pins']) is not dict or not b['source_pins'] or type(b['route_coverage_sha256']) is not str or len(b['route_coverage_sha256'])!=64:
        raise Denied('COMPLETE_ROUTE_COVERAGE_REQUIRED')
    for name in ('owner_body_sha256','host_sha256','route_coverage_sha256'):
        if type(b[name]) is not str or re.fullmatch('[0-9a-f]{64}',b[name]) is None:raise Denied('COMPLETE_REVIEWED_BOOTSTRAP_NOT_BOUND')
    base=Path(__file__).parent
    for name, sha in b['source_pins'].items():
        if type(name) is not str or '/' in name or not name.endswith('.py') or digest((base/name).read_bytes())!=sha:
            raise Denied('REVIEWED_SOURCE_CHANGED')
    return b

def _regular(path, expected_uid):
    p=Path(path)
    if not p.is_absolute() or str(p)!=path or '..' in p.parts:
        raise Denied('EXACT_ABSOLUTE_PATH_REQUIRED')
    for part in [p,*p.parents]:
        if part.is_symlink():raise Denied('SYMLINK_DENIED')
    info=p.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=expected_uid or info.st_mode&0o077:
        raise Denied('PROTECTED_FILE_REQUIRED')
    return info

def _backup(center, path, uid):
    p=Path(path)
    if not p.is_absolute() or str(p)!=path or '..' in p.parts or p.exists() or p.is_symlink():
        raise Denied('NEW_EXACT_BACKUP_REQUIRED')
    for part in [p.parent,*p.parent.parents]:
        if part.is_symlink():raise Denied('SYMLINK_DENIED')
    parent=p.parent.stat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=uid or parent.st_mode&0o077:
        raise Denied('PROTECTED_EXISTING_BACKUP_DIRECTORY_REQUIRED')
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600)
    os.close(fd)
    destination=sqlite3.connect(path)
    try:
        # SQLite online backup includes committed WAL; never cp live files.
        center.db.backup(destination)
        if destination.execute('PRAGMA integrity_check').fetchall()!=[('ok',)] or destination.execute('PRAGMA foreign_key_check').fetchall():
            raise Denied('BACKUP_INTEGRITY_FAILED')
    finally:destination.close()
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    directory=os.open(str(p.parent),os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)
    return digest(p.read_bytes())

def _record_identity(path, value, uid):
    """Immutable exact execution intent, not a server approval/permit system."""
    p=Path(path)
    if len(canonical(value))>65536:raise Denied('PROTECTED_IDENTITY_RECORD_SIZE_REQUIRED')
    if not p.is_absolute() or str(p)!=path or '..' in p.parts:raise Denied('EXACT_IDENTITY_RECORD_PATH_REQUIRED')
    for part in [p,*p.parents]:
        if part.is_symlink():raise Denied('SYMLINK_DENIED')
    parent=p.parent.stat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=uid or parent.st_mode&0o077:raise Denied('PROTECTED_IDENTITY_RECORD_DIRECTORY_REQUIRED')
    if p.exists():
        _regular(path,uid)
        if load_protected(path)!=value:raise Denied('EXACT_IDENTITY_RECORD_CONFLICT')
        return digest(canonical(value))
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb',closefd=False) as stream:
            stream.write(canonical(value));stream.flush();os.fsync(fd)
    finally:os.close(fd)
    directory=os.open(str(p.parent),os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)
    return digest(canonical(value))

def run(candidate=None, action=None):
    b=_binding(candidate)  # Refuse before credential prompt / file or account mutation.
    action=action or (sys.argv[1] if len(sys.argv)==2 else None)
    if action not in ('--inspect','--bootstrap'):
        raise Denied('EXPLICIT_FIXED_ACTION_REQUIRED')
    _regular(b['host_path'],b['run_uid'])
    if digest(Path(b['host_path']).read_bytes())!=b['host_sha256']:
        raise Denied('ORIGINAL_HOST_CONFIG_CHANGED')
    for field in ('keys_path','wechat_path'):load_protected(b[field])
    dbinfo=_regular(b['center_db_path'],b['run_uid'])
    if (dbinfo.st_dev,dbinfo.st_ino)!=(b['center_dev'],b['center_ino']):
        raise Denied('ORIGINAL_CENTER_IDENTITY_CHANGED')
    host=PlatformHost.open(b['host_path'],b['keys_path'],b['wechat_path'])
    try:
        # PlatformHost owns original Center inode flock and runtime lock here.
        locked=os.fstat(host.center_lock)
        if (locked.st_dev,locked.st_ino)!=(b['center_dev'],b['center_ino']):raise Denied('ORIGINAL_CENTER_IDENTITY_CHANGED')
        if str(Path(host.plan['center_root'])/'center.sqlite')!=b['center_db_path']:
            raise Denied('ORIGINAL_CENTER_PATH_MISMATCH')
        if digest(Path(b['host_path']).read_bytes())!=b['host_sha256'] or load_protected(b['host_path'])!=host.plan:
            raise Denied('ORIGINAL_HOST_CONFIG_CHANGED')
        api=getattr(host.center,'community_admin_authority',None)
        if api is None and b['bootstrap_mode']=='CORE_FIRST_ENABLE' and 'community_admin_authority' not in host.plan:
            from scripts.community_admin_authority import full_community_capabilities
            if b['workspace_scopes'] or set(b['capabilities'])!=set(full_community_capabilities()):raise Denied('COMPLETE_COMMUNITY_CAPABILITY_INVENTORY_REQUIRED')
            api=CommunityAdminAuthority(host.center,b['project'],b['tenant'],full_community_capabilities(),(),digest(canonical(dict(workspace_bindings={},registered={}))))
        if type(api) is not CommunityAdminAuthority or api.c is not host.center or api.project!=b['project'] or api.tenant!=b['tenant'] or api.capabilities!=frozenset(b['capabilities']) or api.workspace_scopes!=frozenset(b['workspace_scopes']):
            raise Denied('EXACT_COMMUNITY_AUTHORITY_COMPOSITION_REQUIRED')
        api._realm()
        if action=='--inspect':
            return dict(status='INSPECTED',project=b['project'],tenant=b['tenant'],manifest_sha=api.manifest_sha,account_written=False)
        if not sys.stdin.isatty():raise Denied('INTERACTIVE_TTY_REQUIRED')
        address=email(input('本社区固定超级管理员登录邮箱: '))
        execution=dict(conversation_sources=[dict(message_id=mid,body_sha256=digest(body.encode())) for mid,body in OWNER_SOURCE_MESSAGES],kind='OWNER_TTY_COMMUNITY_SUPERADMIN',email=address,project=b['project'],tenant=b['tenant'],role='COMMUNITY_SUPERADMIN',capabilities=sorted(api.capabilities),workspace_scopes=sorted(api.workspace_scopes),manifest_sha=api.manifest_sha,scope_binding_sha=api.scope_binding_sha,host_sha256=b['host_sha256'],source_pins=b['source_pins'],route_coverage_sha256=b['route_coverage_sha256'],request_id=b['request_id'],owner_message_id=b['owner_message_id'],owner_body_sha256=b['owner_body_sha256'])
        print(json.dumps(execution,ensure_ascii=False,sort_keys=True))
        print('此账户管理上述本社区业务，可创建/限权/撤销子管理员；不授予服务器root或其他项目权限，也不跳过支付/外部平台本身条件。')
        confirmation='CONFIRM '+address+' '+b['project']+' SUPERADMIN'
        if input('确认后输入 '+confirmation+': ')!=confirmation:raise Denied('EXACT_OWNER_TTY_CONFIRMATION_REQUIRED')
        password=getpass.getpass('设置登录密码（隐藏输入，12–128字符）: ')
        repeat=getpass.getpass('再次输入密码: ')
        if password!=repeat:raise Denied('PASSWORD_CONFIRMATION_MISMATCH')
        # Validate before backup/DB writes. No password in argv/environment/file.
        host.center.password(password,b'\x00'*16)
        execution_sha=_record_identity(b['identity_record_path'],execution,b['run_uid'])
        owner=dict(execution_binding_sha256=execution_sha,owner_message_id=b['owner_message_id'],owner_body_sha256=b['owner_body_sha256'],project=b['project'],tenant=b['tenant'],email=address,manifest_sha=api.manifest_sha,request_id=b['request_id'],action='BOOTSTRAP_COMMUNITY_SUPERADMIN')
        intent=dict(execution_binding_sha256=execution_sha,project=b['project'],tenant=b['tenant'],email=address,manifest_sha=api.manifest_sha,request_id=b['request_id'],action='BOOTSTRAP_COMMUNITY_SUPERADMIN',owner_message_id=b['owner_message_id'],owner_body_sha256=b['owner_body_sha256'])
        prior=api._request(b['request_id'],intent)
        if prior is not None:
            api.authority(prior['uid'])
            password=repeat=None
            return dict(prior,status='EXISTING_DATABASE_COMMIT_READBACK',replayed=True,production_login_verified=False,complete_delivery=False)
        backup_sha=_backup(host.center,b['backup_path'],b['run_uid'])
        result=api.bootstrap(address,password,b['request_id'],owner,lambda supplied:supplied==owner)
        password=repeat=None
        observed=api.authority(result['uid'])
        if observed['kind']!='ROOT' or observed['manifest_sha']!=api.manifest_sha:raise Denied('ROOT_READBACK_FAILED')
        return dict(result,status='DATABASE_COMMITTED_READBACK',backup_sha256=backup_sha,production_login_verified=False,complete_delivery=False)
    finally:host.close()

if __name__=='__main__':
    try:
        import argparse
        parser=argparse.ArgumentParser(allow_abbrev=False)
        parser.add_argument('--plan');parser.add_argument('--inspect',action='store_true');parser.add_argument('--bootstrap',action='store_true')
        parser.add_argument('--preflight',action='store_true')
        for name in ('host','keys','wechat','backup','identity-record','request-id','project'):parser.add_argument('--'+name)
        args=parser.parse_args()
        if args.preflight:
            if args.plan or args.inspect or args.bootstrap or not all(getattr(args,n.replace('-','_')) for n in ('host','keys','wechat','backup','identity-record','request-id')):raise Denied('EXPLICIT_FIXED_ACTION_REQUIRED')
            from scripts.community_admin_preflight import build_plan
            result=build_plan(args.host,args.keys,args.wechat,args.backup,args.identity_record,args.request_id,args.project)
        else:
            if args.inspect==args.bootstrap:raise Denied('EXPLICIT_FIXED_ACTION_REQUIRED')
            candidate=load_protected(args.plan) if args.plan else None
            if type(candidate) is dict and set(candidate)=={'plan','observation'}:candidate=candidate['plan']
            result=run(candidate,'--bootstrap' if args.bootstrap else '--inspect')
        print(json.dumps(result,sort_keys=True))
    except Exception as exc:
        # Error messages can include credentials/paths in third-party exceptions.
        known={'COMPLETE_REVIEWED_BOOTSTRAP_NOT_BOUND','EXACT_NONROOT_OWNER_REQUIRED','COMPLETE_ROUTE_COVERAGE_REQUIRED','REVIEWED_SOURCE_CHANGED','EXPLICIT_FIXED_ACTION_REQUIRED','ORIGINAL_HOST_CONFIG_CHANGED','ORIGINAL_CENTER_IDENTITY_CHANGED','ORIGINAL_CENTER_PATH_MISMATCH','INTERACTIVE_TTY_REQUIRED','EXACT_CONFIRMED_ACCOUNT_REQUIRED','PASSWORD_CONFIRMATION_MISMATCH','ROOT_READBACK_FAILED'}
        known.update({'ORIGINAL_ADMIN_SCOPE_CONFIGURATION_MISSING','EXACT_PROTECTED_ADMIN_CONFIGURATION_REQUIRED','COMPLETE_COMMUNITY_CAPABILITY_INVENTORY_REQUIRED','EXACT_ADMIN_SCOPE_TEMPLATES_REQUIRED','ADMIN_MANIFEST_PIN_CHANGED','ORIGINAL_COMMUNITY_REALM_REQUIRED','ACTIVE_ORIGINAL_COMMUNITY_REALM_REQUIRED','EXACT_PROTECTED_OUTPUT_PATH_REQUIRED','PROTECTED_EXISTING_OUTPUT_DIRECTORY_REQUIRED','REQUIRED_ADMIN_SOURCE_MISSING','EXACT_OWNER_TTY_CONFIRMATION_REQUIRED','ORIGINAL_TASK_SOURCE_REFERENCE_CHANGED','EXACT_IDENTITY_RECORD_CONFLICT','EXACT_COMMUNITY_AUTHORITY_COMPOSITION_REQUIRED'})
        code=str(exc) if type(exc) is Denied and str(exc) in known else 'BOOTSTRAP_HOLD_CHECK_ORIGINAL_STATE'
        print(json.dumps({'status':'HOLD','code':code,'complete_delivery':False}))
        raise SystemExit(1) from None
