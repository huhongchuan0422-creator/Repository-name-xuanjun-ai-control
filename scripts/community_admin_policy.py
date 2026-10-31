"""Explicit original-community policy adoption; trusted maintenance composition only.
No HTTP policy writer. Original host serial locks and exact TTY intent are caller gates.
"""
import json
from scripts.community_admin_authority import CommunityAdminAuthority, CHANNEL, full_community_capabilities
from scripts.pr122_customer_core import canonical, digest, identifier, Denied, Conflict

def current_root(target):
    target._realm()
    roots=[]
    for row in target.c.db.execute('SELECT subject_idx,payload,active FROM links WHERE channel=? AND project=?',(CHANNEL,target.project)):
        value=json.loads(target.c.decrypt(row['payload'],CHANNEL+':'+row['subject_idx']+':'+target.project))
        if value.get('kind')=='ROOT':roots.append((row,value))
    if len(roots)!=1 or roots[0][0]['active']!=1:raise Denied('ONE_ACTIVE_ORIGINAL_ROOT_REQUIRED')
    value=roots[0][1]
    old=CommunityAdminAuthority(target.c,target.project,target.tenant,tuple(value['capabilities']),tuple(value['workspace_scopes']),value['scope_binding_sha'])
    old.authority(value['uid'])
    return old,value

def policy_intent(target,request_id):
    identifier(request_id)
    if target.capabilities!=frozenset(full_community_capabilities()):raise Denied('FULL_COMMUNITY_POLICY_REQUIRED')
    old,root=current_root(target)
    if old.capabilities!=target.capabilities:raise Denied('POLICY_CAPABILITY_CHANGE_NOT_IN_SCOPE')
    if old.manifest_sha==target.manifest_sha:raise Conflict('POLICY_ALREADY_CURRENT')
    children=[]
    for row in target.c.db.execute('SELECT subject_idx,payload,active FROM links WHERE channel=? AND project=? AND subject_idx!=? ORDER BY subject_idx',(CHANNEL,target.project,root['uid'])):
        value=json.loads(target.c.decrypt(row['payload'],CHANNEL+':'+row['subject_idx']+':'+target.project))
        if value.get('kind')!='DELEGATE' or value.get('parent')!=root['uid']:raise Denied('EXACT_ROOT_CHILDREN_REQUIRED')
        children.append(dict(uid=row['subject_idx'],active=row['active'],payload_sha256=digest(row['payload'].encode() if isinstance(row['payload'],str) else row['payload'])))
    return dict(action='ADOPT_COMMUNITY_BUSINESS_POLICY',request_id=request_id,project=target.project,tenant=target.tenant,root_uid=root['uid'],expected_revision=root['revision'],from_manifest=old.manifest_sha,to_manifest=target.manifest_sha,to_binding_sha=target.scope_binding_sha,capabilities=sorted(target.capabilities),workspace_scopes=sorted(target.workspace_scopes),children=children,children_action='REVOKE_REQUIRE_EXPLICIT_REGRANT',sessions_action='INVALIDATE_ALL_CENTER_SESSIONS_OF_AFFECTED_ADMINS')

def adopt_policy(target,intent,execution_binding_sha256,verifier):
    if type(target) is not CommunityAdminAuthority or type(intent) is not dict or not callable(verifier):raise Denied('PROTECTED_POLICY_COMPOSITION_REQUIRED')
    if type(execution_binding_sha256) is not str or len(execution_binding_sha256)!=64 or any(x not in '0123456789abcdef' for x in execution_binding_sha256):raise Denied('EXACT_EXECUTION_BINDING_REQUIRED')
    if not verifier(dict(intent)):raise Denied('EXACT_OWNER_POLICY_CONFIRMATION_REQUIRED')
    request_id=identifier(intent.get('request_id'))
    bound=dict(intent,execution_binding_sha256=execution_binding_sha256)
    with target.c.tx():
        target._realm()
        saved=target._request(request_id,bound)
        if saved is not None:
            current=target.authority(saved['uid'])
            if current['revision']!=saved['revision'] or current['manifest_sha']!=saved['manifest_sha']:raise Conflict('POLICY_REQUEST_SUPERSEDED')
            return dict(saved,replayed=True)
        if policy_intent(target,request_id)!=intent:raise Conflict('POLICY_INPUT_CHANGED')
        old,root=current_root(target)
        next_root=dict(root,revision=root['revision']+1,manifest_sha=target.manifest_sha,scope_binding_sha=target.scope_binding_sha,workspace_scopes=sorted(target.workspace_scopes),capabilities=sorted(target.capabilities),request_id=request_id)
        target._write(next_root,True)
        # Never enlarge or silently inherit child authority. Original records retained.
        target.c.db.execute('UPDATE links SET active=0 WHERE channel=? AND project=? AND subject_idx!=?',(CHANNEL,target.project,root['uid']))
        target.c.db.execute('DELETE FROM sessions WHERE user_id IN (SELECT user_id FROM links WHERE channel=? AND project=?)',(CHANNEL,target.project))
        target.c.audit(target.project,root['uid'],'COMMUNITY_ADMIN_POLICY_EXPLICITLY_ADOPTED',digest(canonical(bound)))
        result=dict(uid=root['uid'],revision=next_root['revision'],manifest_sha=target.manifest_sha,children_affected=len(intent['children']),children_auto_expanded=False,requires_login=True)
        target._save_request(request_id,bound,result,root['uid'])
        target.authority(root['uid'])
        return result
