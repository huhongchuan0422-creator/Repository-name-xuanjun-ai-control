"""Narrow existing merchant name/status projection for an authorized member list.

No profile collection, provider calls, credentials, contacts, business authority
or new identity. Relationships alone never prove merchant/payment admission.
"""
import hashlib,json,re
from scripts.pr122_customer_core import canonical

STATES={'APPLYMENT_STATE_EDITTING','APPLYMENT_STATE_AUDITING','APPLYMENT_STATE_REJECTED',
        'APPLYMENT_STATE_TO_BE_CONFIRMED','APPLYMENT_STATE_TO_BE_SIGNED',
        'APPLYMENT_STATE_SIGNING','APPLYMENT_STATE_FINISHED','APPLYMENT_STATE_CANCELED'}

def _wechat(directory,workspace,target):
    operations=directory.commerce.operations;service=operations.onboarding
    if service is None or service.wechat_applyment is None:return None
    from scripts.community_merchant_opening import authorize_workspace
    authorize_workspace(service,operations,workspace,target['user_id'])
    key=hashlib.sha256(canonical(target['scope'])).hexdigest()
    rows=directory.center.db.execute("SELECT project,payload FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING' AND subject_idx=? AND user_id=? AND active=1",(key,target['user_id'])).fetchall()
    if len(rows)!=1:return None
    application,payload=rows[0]
    opening=service._decode(payload,'community-opening:'+key+':'+application)
    if type(opening) is not dict:return None
    if opening.get('project')!=target['project'] or opening.get('scope')!=target['scope'] or opening.get('workspace')!=workspace:return None
    row=directory.center.db.execute("SELECT user_id,payload FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=? AND project=? AND active=1",(application,application)).fetchone()
    if row is None or row[0]!=target['user_id']:return None
    record=json.loads(directory.center.decrypt(row[1],'wechat-applyment:'+application))
    if type(record) is not dict:return None
    from scripts.community_wechat_applyment import submission_boundary,consumed_rejection_signatures
    recovery=record.get('submission_recovery_receipt',{})
    consumed=record.get('consumed_rejections',[])
    if (type(recovery) is not dict or type(consumed) is not list
            or any(type(v) is not dict or type(v.get('signature_sha256')) is not str for v in consumed)
            or type(record.get('submission_response_signed_at',-1)) is not int
            or type(recovery.get('signed_at',-1)) is not int):return None
    observed=record.get('provider_observed_at');signed=record.get('provider_query_signed_at')
    if (type(record.get('provider_query_signature_sha256')) is not str
            or not re.fullmatch('[0-9a-f]{64}',record['provider_query_signature_sha256'])):return None
    if (record.get('state')=='SUBMISSION_UNKNOWN'
            or record.get('provider_query_signature_sha256') in consumed_rejection_signatures(record)
            or type(signed) is not int or signed<=record.get('submission_response_signed_at',-1)
            or signed<submission_boundary(record)):return None
    if recovery and signed==recovery.get('signed_at'):
        if any(recovery.get(a)!=record.get(b) for a,b in (
                ('business_code','business_code'),('applyment_id','applyment_id'),
                ('signature_sha256','provider_query_signature_sha256'),
                ('response_sha256','provider_response_sha256'))):return None
    if (record.get('provider_state') not in STATES
            or record.get('provider_sp_mchid')!=service.wechat_applyment.reader._mchid
            or not record.get('business_code') or not record.get('applyment_id')
            or type(observed) is not int or not 0<=observed<=directory.center.now()
            or type(signed) is not int or not 0<=signed<=observed
            or any(type(record.get(k)) is not str or not re.fullmatch('[0-9a-f]{64}',record[k])
                   for k in ('provider_query_signature_sha256','provider_response_sha256'))):return None
    if record['provider_state']=='APPLYMENT_STATE_FINISHED':
        sub=record.get('provider_sub_mchid')
        if type(sub) is not str or not re.fullmatch('[0-9]{6,32}',sub):return None
    # Only state and observation time; no profile, merchant IDs or receipt body.
    return {'state':record['provider_state'],'observed_at':observed}

def project_member(directory,grant,community,relation):
    if relation.get('kind')!='MERCHANT':return dict(relation)
    if (relation.get('tenant')!=grant['tenant'] or relation.get('community_id')!=community['id']
            or community.get('tenant')!=grant['tenant']
            or not (grant['role']=='COMMUNITY_ADMIN' and community['owner']==grant['user_id']
                    or grant['role'] in ('PLATFORM_OWNER','PLATFORM_REVIEWER'))):
        raise PermissionError('AUTHORIZED_CURRENT_COMMUNITY_MEMBER_REQUIRED')
    extra=dict(merchant_name=None,merchant_names=[],merchant_name_status='NO_ADMITTED_MAPPING',
        wechat_status='UNKNOWN',wechat_status_source='NOT_AVAILABLE',wechat_observed_at=None)
    if directory.commerce is None:return dict(relation,**extra)
    operations=directory.commerce.operations;names=set();observations=[];mapped=False;unavailable=False
    for workspace,target in sorted(operations.grants.items()):
        if (target['user_id']!=relation['user_id'] or target['project']!=grant['project']
                or target['tenant']!=grant['tenant'] or target['role']!='MERCHANT_ADMIN'):continue
        principal=target['principal']
        try:
            if principal.role!=target['role'] or principal.tenant_id!=grant['tenant'] or operations.runtime.bindings.get(principal)!=target['scope']:
                raise PermissionError('ORIGINAL_MERCHANT_MAPPING_CHANGED')
            project,_,_=directory.center.project(target['user_id'],target['project'],target['project_roles'])
            if project['tenant']!=grant['tenant']:raise PermissionError('PROJECT_TENANT_MISMATCH')
        except PermissionError:
            unavailable=True;continue
        mapped=True
        scope=target['scope'];row=operations.runtime.demo.merchant_db.execute('SELECT name FROM merchant_profiles WHERE tenant_id=? AND merchant_id=? AND store_id=?',tuple(scope[k] for k in ('tenant_id','merchant_id','store_id'))).fetchone()
        if row is not None and type(row[0]) is str and row[0]:names.add(row[0])
        try:observations.append(_wechat(directory,workspace,target))
        except (PermissionError,ValueError,KeyError):observations.append(None)
    extra['merchant_names']=sorted(names)
    extra['merchant_name_status']='MAPPING_UNAVAILABLE' if unavailable else 'MATCHED' if len(names)==1 else 'MULTIPLE' if len(names)>1 else 'NO_PROFILE' if mapped else 'NO_ADMITTED_MAPPING'
    if not unavailable and len(names)==1:extra['merchant_name']=next(iter(names))
    # Do not collapse multiple merchant workspaces into one signing assertion.
    if not unavailable and len(observations)==1 and observations[0] is not None:
        extra.update(wechat_status=observations[0]['state'],wechat_status_source='SIGNED_PROVIDER_QUERY',wechat_observed_at=observations[0]['observed_at'])
    elif len(observations)>1:extra['wechat_status_source']='MULTIPLE_MERCHANT_WORKSPACES'
    return dict(relation,**extra)
