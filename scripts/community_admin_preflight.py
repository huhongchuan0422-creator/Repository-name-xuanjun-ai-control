"""Read-only original-input projection for manual community admin setup.
No account, config, lock, permit, provider call, or DB schema writes.
The generated plan is input to the same reviewed TTY bootstrap, NOT authority.
"""
import os
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote
from scripts.community_mini_host_config import load_protected
from scripts.community_platform_host import _configuration
from scripts.community_admin_authority import ROUTES, full_community_capabilities
from scripts.community_admin_route_gate import binding_digest
from scripts.community_admin_route_inventory import BUSINESS_CAPABILITIES
from scripts.pr122_customer_core import Center, canonical, digest, Denied

SOURCE_NAMES=('community_admin_authority.py','community_admin_bootstrap.py','community_admin_preflight.py','community_admin_management.py','community_admin_route_gate.py','community_admin_route_inventory.py','community_platform_host.py','community_web_session.py','community_mini_http.py','pr122_customer_core.py')

def build_plan(host_path,keys_path,wechat_path,backup_path,identity_record_path,request_id,project=None):
 from scripts.community_admin_bootstrap import _regular, OWNER_SOURCE_MESSAGES
 from scripts.pr122_customer_core import identifier
 identifier(request_id)
 uid=os.geteuid()
 if uid==0:raise Denied('EXACT_NONROOT_OWNER_REQUIRED')
 for path in (host_path,keys_path,wechat_path):_regular(path,uid)
 host=load_protected(host_path);key_material=load_protected(keys_path);wechat=load_protected(wechat_path)
 owner=dict(owner_message_id=OWNER_SOURCE_MESSAGES[-1][0],body=OWNER_SOURCE_MESSAGES[-1][1])
 admin=host.get('community_admin_authority')
 core_only=admin is None
 keys,principals,bindings,operations=_configuration(host,key_material,wechat)
 if core_only:
  application=load_protected(host['application_config'])
  if application.get('appid')!=wechat['appid'] or application.get('https_origin')!=host['https_origin']:raise Denied('SAME_PROTECTED_APPID_AND_ORIGIN_REQUIRED')
  projects={value['project'] for value in application['scenes'].values()}
  if project is not None:
   if project not in projects:raise Denied('EXISTING_COMMUNITY_PROJECT_REQUIRED')
   selected=project
  elif len(projects)==1:selected=next(iter(projects))
  else:raise Denied('UNAMBIGUOUS_COMMUNITY_PROJECT_REQUIRED')
  # Resolve actual original project tenant; never manufacture a realm or UID.
  readonly_path=str(Path(host['center_root'])/'center.sqlite');_regular(readonly_path,uid)
  connection=sqlite3.connect('file:'+quote(readonly_path,safe='/')+'?mode=ro',uri=True)
  try:found=connection.execute('SELECT tenant FROM projects WHERE id=?',(selected,)).fetchone()
  finally:connection.close()
  if found is None:raise Denied('ORIGINAL_COMMUNITY_REALM_REQUIRED')
  empty_binding=digest(canonical(dict(workspace_bindings={},registered={})))
  cap=list(full_community_capabilities())
  admin=dict(project=selected,tenant=found[0],capabilities=cap,workspace_scopes=[],workspace_bindings={},manifest_sha=digest(canonical(dict(capabilities=sorted(cap),workspace_scopes=[],scope_binding_sha=empty_binding))))
 elif type(admin) is not dict:raise Denied('EXACT_PROTECTED_ADMIN_CONFIGURATION_REQUIRED')
 expected={'project','tenant','capabilities','workspace_scopes','workspace_bindings','manifest_sha'}
 if set(admin)!=expected:raise Denied('EXACT_PROTECTED_ADMIN_CONFIGURATION_REQUIRED')
 management={'/community/admin#'+op for op in ('catalog','list','create','grant','revoke')}
 if set(admin['capabilities']) != set(BUSINESS_CAPABILITIES)|management:
  raise Denied('COMPLETE_COMMUNITY_CAPABILITY_INVENTORY_REQUIRED')
 if set(admin['workspace_scopes'])!=set(admin['workspace_bindings']):
  raise Denied('EXACT_ADMIN_SCOPE_TEMPLATES_REQUIRED')
 binding_sha=binding_digest(admin['workspace_bindings'],SimpleNamespace(bindings=bindings),principals)
 manifest=digest(canonical(dict(capabilities=sorted(admin['capabilities']),workspace_scopes=sorted(admin['workspace_scopes']),scope_binding_sha=binding_sha)))
 if manifest!=admin['manifest_sha']:raise Denied('ADMIN_MANIFEST_PIN_CHANGED')
 dbpath=str(Path(host['center_root'])/'center.sqlite');info=_regular(dbpath,uid)
 db=sqlite3.connect('file:'+quote(dbpath,safe='/')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
 try:
  db.execute('PRAGMA query_only=ON')
  row=db.execute('SELECT * FROM projects WHERE id=?',(admin['project'],)).fetchone()
  if row is None or row['tenant']!=admin['tenant'] or row['owner']!='system_community_platform' or row['active']!=1:raise Denied('ORIGINAL_COMMUNITY_REALM_REQUIRED')
  import time
  if row['expires']<=int(time.time()):raise Denied('ACTIVE_ORIGINAL_COMMUNITY_REALM_REQUIRED')
  # Reuse unchanged Core decryption primitive against an explicit read-only key view.
  realm=json.loads(Center.decrypt(SimpleNamespace(keys=keys),row['payload'],'project:'+admin['project']))
  if realm.get('kind')!='COMMUNITY_PLATFORM_REALM' or realm.get('source')!='OWNER_APPROVED_FIRST_INSTALL' or realm.get('requirements')!=[]:raise Denied('ORIGINAL_COMMUNITY_REALM_REQUIRED')
  existing=db.execute("SELECT count(*) FROM links WHERE channel='COMMUNITY_ADMIN_AUTHORITY_V1' AND project=?",(admin['project'],)).fetchone()[0]
 finally:db.close()
 if (info.st_dev,info.st_ino)!=(_regular(dbpath,uid).st_dev,_regular(dbpath,uid).st_ino):raise Denied('ORIGINAL_CENTER_IDENTITY_CHANGED')
 for path in (backup_path,identity_record_path):
  p=Path(path)
  if not p.is_absolute() or str(p)!=path or '..' in p.parts or p.is_symlink():raise Denied('EXACT_PROTECTED_OUTPUT_PATH_REQUIRED')
  for parent in p.parents:
   if parent.is_symlink():raise Denied('SYMLINK_DENIED')
  parent=p.parent.stat()
  if parent.st_uid!=uid or parent.st_mode&0o077:raise Denied('PROTECTED_EXISTING_OUTPUT_DIRECTORY_REQUIRED')
 source=Path(__file__).parent
 pins={p.name:digest(p.read_bytes()) for p in source.glob('*.py') if p.name.startswith('community_') or p.name.startswith('pr122_customer_')}
 if not set(SOURCE_NAMES)<=set(pins):raise Denied('REQUIRED_ADMIN_SOURCE_MISSING')
 host_sha=digest(Path(host_path).read_bytes())
 if load_protected(host_path)!=host:raise Denied('ORIGINAL_HOST_CONFIG_CHANGED')
 plan=dict(version=1,bootstrap_mode='CORE_FIRST_ENABLE' if core_only else 'CONFIGURED_ADMIN',owner_message_id=owner['owner_message_id'],owner_body_sha256=digest(owner['body'].encode()),project=admin['project'],tenant=admin['tenant'],identity_mode='OWNER_TTY_CHOICE',identity_record_path=identity_record_path,request_id=request_id,host_path=host_path,host_sha256=host_sha,keys_path=keys_path,wechat_path=wechat_path,center_db_path=dbpath,center_dev=info.st_dev,center_ino=info.st_ino,run_uid=uid,backup_path=backup_path,capabilities=admin['capabilities'],workspace_scopes=admin['workspace_scopes'],route_coverage_sha256=digest((source/'community_admin_route_inventory.py').read_bytes()),source_pins=pins)
 # Actual live enablement and original writer idle state are NOT inferred here.
 return dict(plan=plan,observation=dict(existing_admin_records=existing,read_only=True,production_login_verified=False,live_service_enablement='UNKNOWN',business_scopes_configured=not core_only,unconfigured_business_not_account_blocker=True,requires_original_serial_maintenance=True))
