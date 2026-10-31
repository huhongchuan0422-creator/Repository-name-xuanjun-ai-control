"""Administrator actions inside original community HTTP/session composition."""
import json
from scripts.community_admin_authority import CommunityAdminAuthority, CHANNEL
from scripts.pr122_customer_core import Denied, identifier

FIELDS={
 'self':set(),
 'catalog':set(),
 'list':{'after_uid'},
 'create':{'email','password','capabilities','workspace_scopes','request_id'},
 'grant':{'uid','capabilities','workspace_scopes','request_id','expected_revision'},
 'revoke':{'uid','expected_revision','request_id'},
}

def dispatch(center,session,csrf,body):
 api=getattr(center,'community_admin_authority',None)
 if type(api) is not CommunityAdminAuthority or api.c is not center:
  raise Denied('EXACT_COMMUNITY_AUTHORITY_COMPOSITION_REQUIRED')
 if type(body) is not dict or set(body)!={'operation','params'} or body['operation'] not in FIELDS or type(body['params']) is not dict or set(body['params'])!=FIELDS[body['operation']]:
  raise ValueError('EXACT_ADMIN_ACTION_FIELDS_REQUIRED')
 if type(csrf) is not str or not csrf:raise Denied('CSRF_REQUIRED')
 uid=center.session(session,csrf);authority=api.authority(uid)
 operation,params=body['operation'],body['params']
 if operation=='self':
  return {k:authority[k] for k in ('uid','project','tenant','kind','revision','capabilities','workspace_scopes')}
 if authority['kind']!='ROOT':raise Denied('ROOT_ADMIN_MANAGEMENT_REQUIRED')
 api.authorize(session,csrf,'/community/admin',operation)
 if operation=='catalog':
  return dict(capabilities=sorted(api.capabilities),workspace_scopes=sorted(api.workspace_scopes),manifest_sha=api.manifest_sha)
 if operation=='create':return api.create_subadmin(session,csrf,params['email'],params['password'],params['capabilities'],params['request_id'],params['workspace_scopes'])
 if operation=='grant':return api.delegate(session,csrf,params['uid'],params['capabilities'],params['request_id'],params['expected_revision'],params['workspace_scopes'])
 if operation=='revoke':return api.revoke(session,csrf,params['uid'],params['expected_revision'],params['request_id'])
 after=params['after_uid']
 if after!='':identifier(after)
 records=[]
 for row in center.db.execute('SELECT subject_idx,payload,active FROM links WHERE channel=? AND project=? AND subject_idx>? ORDER BY subject_idx LIMIT 51',(CHANNEL,api.project,after)):
  value=json.loads(center.decrypt(row['payload'],CHANNEL+':'+row['subject_idx']+':'+api.project))
  account=center.db.execute('SELECT email_enc FROM accounts WHERE id=?',(row['subject_idx'],)).fetchone()
  login_label=center.decrypt(account[0],row['subject_idx']).decode() if account else ''
  records.append(dict(uid=row['subject_idx'],login_label=login_label,kind=value['kind'],revision=value['revision'],active=bool(row['active']),capabilities=value['capabilities'],workspace_scopes=value['workspace_scopes']))
 return dict(records=records[:50],has_more=len(records)>50,next_cursor=records[49]['uid'] if len(records)>50 else None)
