"""Protected, recoverable workbench opening; original CRM supplies the mapping.

No new accounts, projects, principals, permissions or payment merchant IDs are
created. A durable reservation precedes the original merchant profile write;
unknown outcomes remain reserved until an explicit matching retry.
"""
import hashlib
from scripts.pr122_customer_core import canonical
from scripts.community_merchant_store import upsert_profile


def _grant(operations,workspace,owner):
    grant=operations.grants.get(workspace)
    if (grant is None or grant['user_id']!=owner or not grant['onboarding_required']
            or grant['role']!='MERCHANT_ADMIN' or not set(grant['project_roles']).issubset({'OWNER','EDITOR'})):
        raise PermissionError('PROTECTED_CRM_MERCHANT_MAPPING_REQUIRED')
    principal=grant['principal'];runtime=operations.runtime
    if (principal not in runtime.bindings or principal.role!=grant['role']
            or principal.tenant_id!=grant['tenant'] or runtime.bindings[principal]!=grant['scope']):
        raise PermissionError('REGISTERED_MERCHANT_MAPPING_CHANGED')
    project,_,_=operations.center.project(owner,grant['project'],grant['project_roles'])
    if project['tenant']!=grant['tenant']:raise PermissionError('PROJECT_TENANT_MISMATCH')
    return grant


def _approved(service,application,owner,revision=None,*,check_files=False):
    actual,meta,data=service._load(application,owner)
    if actual!=owner or data['status']!='APPROVED' or revision is not None and data['revision']!=revision:
        raise PermissionError('CURRENT_APPROVED_APPLICATION_REQUIRED')
    account=service.center.db.execute('SELECT verified FROM accounts WHERE id=?',(owner,)).fetchone()
    if account is None or account[0]!=1:raise PermissionError('VERIFIED_APPLICANT_REQUIRED')
    for kind in service._required(meta):
        material=meta['materials'].get(kind);review=meta.get('reviews',{}).get(kind,{})
        if (not material or material['expires_at'] is not None and material['expires_at']<=service.center.now()
                or review.get('decision')!='ACCEPTED' or review.get('sha256')!=material['sha256']):
            raise PermissionError('CURRENT_REVIEWED_MATERIALS_REQUIRED')
    if check_files:service._check_materials(application,meta)
    return meta,data


def authorize_workspace(service,operations,workspace,owner):
    grant=_grant(operations,workspace,owner);c=service.center
    key=hashlib.sha256(canonical(grant['scope'])).hexdigest()
    rows=c.db.execute("SELECT project,payload FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING' AND subject_idx=? AND user_id=? AND active=1",(key,owner)).fetchall()
    if len(rows)!=1:raise PermissionError('MERCHANT_WORKBENCH_NOT_OPENED')
    application,payload=rows[0]
    record=service._decode(payload,'community-opening:'+key+':'+application)
    if (record['state']!='OPENED' or record['workspace']!=workspace or record['scope']!=grant['scope']
            or record['project']!=grant['project']):raise PermissionError('MERCHANT_WORKBENCH_NOT_OPENED')
    _approved(service,application,owner,record['revision'])
    if not operations.runtime.demo.merchant_db.execute('SELECT 1 FROM merchant_profiles WHERE tenant_id=? AND merchant_id=? AND store_id=?',tuple(grant['scope'][k] for k in ('tenant_id','merchant_id','store_id'))).fetchone():
        raise PermissionError('OPENED_MERCHANT_PROFILE_REQUIRED')


def open_workbench(service,operations,reviewer,application,workspace,revision):
    from scripts.community_center_operations import CenterOperations
    if type(operations) is not CenterOperations or operations.center is not service.center or operations.onboarding is not service:
        raise ValueError('SAME_CENTER_REGISTERED_OPERATIONS_REQUIRED')
    if type(workspace) is not str or type(revision) is not int or revision<1:raise ValueError('INVALID_OPENING_REQUEST')
    c=service.center
    if c.db.in_transaction:raise ValueError('EXTERNAL_TRANSACTION_DENIED')
    service._reviewer(reviewer)
    owner,_,_=service._load(application,reviewer,True)
    if owner==reviewer:raise PermissionError('INDEPENDENT_REVIEW_REQUIRED')
    c.db.execute('BEGIN IMMEDIATE')
    try:
        meta,data=_approved(service,application,owner,revision,check_files=True)
        grant=_grant(operations,workspace,owner);identity=dict(grant['scope'])
        key=hashlib.sha256(canonical(identity)).hexdigest()
        record={'workspace':workspace,'scope':identity,'project':grant['project'],
                'revision':revision,'state':'RESERVED','preserve_profile':False}
        rows=c.db.execute("SELECT subject_idx,user_id,project,payload,active FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING' AND (subject_idx=? OR project=?)",(key,application)).fetchall()
        if rows:
            if len(rows)!=1 or tuple(rows[0][:3])!=(key,owner,application) or rows[0]['active']!=1:
                raise PermissionError('OPENING_MAPPING_ALREADY_RESERVED')
            old=service._decode(rows[0]['payload'],'community-opening:'+key+':'+application)
            old.setdefault('preserve_profile',False)
            if (set(old)!=set(record) or old['state'] not in ('RESERVED','OPENED')
                    or type(old['preserve_profile']) is not bool
                    or any(old[k]!=record[k] for k in ('workspace','scope','project'))):
                raise PermissionError('OPENING_MAPPING_CHANGED')
            if old['revision']!=revision:
                correction=c.db.execute("SELECT 1 FROM onboarding_events WHERE tenant=? AND application=? AND event='CORRECTION' AND revision>? AND revision<?",(owner,application,old['revision'],revision)).fetchone()
                if old['state']!='OPENED' or old['revision']>=revision or correction is None:
                    raise PermissionError('OPENING_APPROVAL_REVISION_CHANGED')
                record['preserve_profile']=True
                c.db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_MERCHANT_OPENING' AND subject_idx=? AND project=? AND user_id=? AND active=1",
                    (service._encode(record,'community-opening:'+key+':'+application),key,application,owner))
                c.audit(application,reviewer,'MERCHANT_REOPENING_RESERVED',key)
            else:
                record['preserve_profile']=old['preserve_profile']
                if old['state']=='OPENED':
                    c.db.commit();authorize_workspace(service,operations,workspace,owner)
                    return {'opening_state':'OPENED','duplicate':True,'payment_enabled':False}
        else:
            # A historical profile is never claimed merely by submitting an
            # application. Existing merchants keep their original legacy grant.
            if operations.runtime.demo.merchant_db.execute('SELECT 1 FROM merchant_profiles WHERE tenant_id=? AND merchant_id=? AND store_id=?',tuple(identity[k] for k in ('tenant_id','merchant_id','store_id'))).fetchone():
                raise PermissionError('EXISTING_MERCHANT_CANNOT_BE_CLAIMED')
            c.db.execute("INSERT INTO links VALUES('COMMUNITY_MERCHANT_OPENING',?,?,?,?,1)",
                (key,owner,application,service._encode(record,'community-opening:'+key+':'+application)))
            c.audit(application,reviewer,'MERCHANT_OPENING_RESERVED',key)
        c.db.commit()
    except BaseException:
        c.db.rollback();raise
    # The reservation is deliberately committed before crossing to the original
    # merchant database. A crash cannot turn an unknown write into a new grant.
    db=operations.runtime.demo.merchant_db
    if db.in_transaction:raise ValueError('EXTERNAL_MERCHANT_TRANSACTION_DENIED')
    db.execute('BEGIN IMMEDIATE')
    try:
        row=db.execute('SELECT name,description,contact,status,version FROM merchant_profiles WHERE tenant_id=? AND merchant_id=? AND store_id=?',tuple(identity[k] for k in ('tenant_id','merchant_id','store_id'))).fetchone()
        expected=(data['fields']['store_name'],data['fields']['store_name'],data['fields']['contact'],'PAUSED',1)
        if record['preserve_profile']:
            if row is None:raise PermissionError('EXISTING_OPENED_PROFILE_REQUIRED')
            db.commit()
        elif row is not None and tuple(row)!=expected:raise PermissionError('OPENING_PROFILE_CHANGED')
        elif row is None:
            # Reuse the original validated profile writer and its own commit.
            actor=dict(identity,authenticated=True,role='MERCHANT_ADMIN')
            upsert_profile(db,identity,actor,dict(zip(('name','description','contact','status'),expected[:4])))
        else:db.commit()
    except BaseException:
        db.rollback();raise
    with c.tx():
        service._reviewer(reviewer);_grant(operations,workspace,owner);_approved(service,application,owner,revision)
        current=c.db.execute("SELECT payload,active FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING' AND subject_idx=? AND project=? AND user_id=?",(key,application,owner)).fetchone()
        if current is None or current['active']!=1:raise PermissionError('OPENING_RESERVATION_REVOKED')
        old=service._decode(current['payload'],'community-opening:'+key+':'+application)
        if dict(old,state='RESERVED')!=record:raise PermissionError('OPENING_RESERVATION_CHANGED')
        if old['state']=='OPENED':return {'opening_state':'OPENED','duplicate':True,'payment_enabled':False}
        if old['state']!='RESERVED':raise PermissionError('OPENING_RESERVATION_CHANGED')
        record['state']='OPENED'
        c.db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_MERCHANT_OPENING' AND subject_idx=? AND project=? AND user_id=? AND active=1",
            (service._encode(record,'community-opening:'+key+':'+application),key,application,owner))
        c.audit(application,reviewer,'MERCHANT_OPENING_COMPLETED',key)
    return {'opening_state':'OPENED','duplicate':False,'payment_enabled':False}


def opening_state(service,application):
    rows=service.center.db.execute("SELECT subject_idx,user_id,payload,active FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING' AND project=?",(application,)).fetchall()
    if not rows:return 'AWAITING_CRM_BINDING'
    if len(rows)!=1 or rows[0]['active']!=1:return 'ACCESS_SUSPENDED'
    key,owner,payload,_=rows[0]
    record=service._decode(payload,'community-opening:'+key+':'+application)
    if record['state']=='RESERVED':return 'OPENING_PENDING'
    if service.operations is None:return 'AWAITING_CRM_BINDING'
    try:authorize_workspace(service,service.operations,record['workspace'],owner)
    except (PermissionError,ValueError,KeyError):return 'ACCESS_SUSPENDED'
    return 'OPENED'
