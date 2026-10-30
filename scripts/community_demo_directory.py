"""Owner-authorized illustrative shop. Never a merchant/order/admission record.

Uses historical original approval events, not current public-list emptiness.
No writes or new registry. Missing evidence hides the illustration.
"""
import hashlib
import json
from scripts.pr122_customer_core import canonical

ASSET_ID='community-demo-storefront-v1'

RETIRE_EVENT='COMMUNITY_DEMO_RETIRED_REAL_APPROVAL'

def retire_on_approval(service,application,owner,actor,revision,meta):
    """Append scope evidence inside original successful approval transaction.
    Not a second ledger; preserves the original audit chain and rollback.
    Unknown scope creates no inferred scope or approval and changes no grant.
    """
    c=service.center
    if not c.db.in_transaction:raise ValueError('ORIGINAL_APPROVAL_TRANSACTION_REQUIRED')
    event=c.db.execute("SELECT actor,event FROM onboarding_events WHERE tenant=? AND application=? AND revision=?",(owner,application,revision)).fetchone()
    if event is None or tuple(event)!=(actor,'APPROVE'):raise ValueError('ORIGINAL_APPROVAL_EVENT_REQUIRED')
    scopes=set();origin=meta.get('ocr_origin')
    if origin is not None:scopes.add((origin['project'],origin['scope']['tenant_id']))
    ops=service.operations
    if ops is not None:
        from scripts.community_merchant_opening import _grant
        for name,g in ops.grants.items():
            if g['user_id']!=owner or not g['onboarding_required']:continue
            try:live=_grant(ops,name,owner)
            except PermissionError:continue
            scopes.add((live['project'],live['scope']['tenant_id']))
    if len(scopes)==1:
        project,tenant=next(iter(scopes))
        c.audit(project,actor,RETIRE_EVENT,hashlib.sha256(canonical([project,tenant])).hexdigest())

def _scope_for_approval(service,application,owner):
    c=service.center
    row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_ONBOARDING' AND subject_idx=? AND project=? AND user_id=?",(application,application,owner)).fetchone()
    scopes=set()
    if row is not None:
        meta=service._decode(row[0],'onboarding-meta:'+application)
        origin=meta.get('ocr_origin')
        if origin is not None:scopes.add((origin['project'],origin['scope']['tenant_id']))
    for k,raw in c.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING' AND project=? AND user_id=?",(application,owner)):
        record=service._decode(raw,'community-opening:'+k+':'+application)
        scopes.add((record['project'],record['scope']['tenant_id']))
    return next(iter(scopes)) if len(scopes)==1 else None

def presentation(gateway,token):
    unknown=dict(state='UNKNOWN',record=None)
    identity=gateway.identity;identity.applicant_context(token)
    allowed=set()
    for scene in identity.scenes:
        try:
            _,project,principal=identity._resolve(token,scene)
        except PermissionError:continue
        allowed.add((project,principal.tenant_id))
    if len(allowed)!=1:return dict(state='NOT_CURRENT_PROJECT',record=None)
    current=next(iter(allowed));c=identity.center
    retirement_key=hashlib.sha256(canonical(list(current))).hexdigest()
    if c.db.execute('SELECT 1 FROM audit WHERE project=? AND event=? AND object_id=?',(current[0],RETIRE_EVENT,retirement_key)).fetchone() is not None:
        return dict(state='HIDDEN_REAL_APPROVAL_OBSERVED',record=None)
    commerce=getattr(gateway,'commerce',None)
    service=getattr(getattr(commerce,'operations',None),'onboarding',None)
    if service is None or service.center is not identity.center:return unknown
    c=identity.center
    try:
        # Detect incomplete historical event coverage. A missing event cannot
        # turn an old approval into an apparent zero-merchant population.
        for application,actor,revision in c.db.execute("SELECT project,actor,object_id FROM audit WHERE event='MERCHANT_ONBOARDING_REVIEW'"):
            rows=c.db.execute('SELECT actor FROM onboarding_events WHERE application=? AND revision=?',(application,revision)).fetchall()
            if len(rows)!=1 or rows[0][0]!=actor:return unknown
        # Existing admission/opening rows without their approval event are an
        # incomplete source, not proof that nobody has ever been approved.
        for owner,application in c.db.execute("SELECT tenant,application FROM onboarding WHERE status='APPROVED'"):
            if c.db.execute("SELECT 1 FROM onboarding_events WHERE tenant=? AND application=? AND event='APPROVE'",(owner,application)).fetchone() is None:return unknown
        for owner,application in c.db.execute("SELECT user_id,project FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING'"):
            if c.db.execute("SELECT 1 FROM onboarding_events WHERE tenant=? AND application=? AND event='APPROVE'",(owner,application)).fetchone() is None:return unknown
        found=False;unmapped=False
        for owner,application,actor,revision in c.db.execute("SELECT tenant,application,actor,revision FROM onboarding_events WHERE event='APPROVE'"):
            if owner==actor:return unknown
            audit=c.db.execute("SELECT count(*) FROM audit WHERE project=? AND actor=? AND event='MERCHANT_ONBOARDING_REVIEW' AND object_id=?",(application,actor,str(revision))).fetchone()[0]
            if audit!=1:return unknown
            source=_scope_for_approval(service,application,owner)
            if source is None:unmapped=True
            elif source==current:found=True
        if found:return dict(state='HIDDEN_REAL_APPROVAL_OBSERVED',record=None)
        if unmapped:return unknown
        # Legacy active profiles without proven admission provenance must not
        # be counted as zero real shops, even if public pagination is empty.
        db=commerce.runtime.demo.merchant_db
        for tenant,merchant,store in db.execute("SELECT tenant_id,merchant_id,store_id FROM merchant_profiles WHERE tenant_id=?",(current[1],)):
            scope=dict(tenant_id=tenant,merchant_id=merchant,store_id=store)
            k=hashlib.sha256(canonical(scope)).hexdigest()
            mappings=[]
            for app,raw in c.db.execute("SELECT project,payload FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING' AND subject_idx=?",(k,)):
                rec=service._decode(raw,'community-opening:'+k+':'+app)
                if rec['scope']!=scope:return unknown
                mappings.append((rec['project'],rec['scope']['tenant_id']))
            if len(mappings)!=1 or mappings[0]==current:return unknown
    except Exception:
        return unknown
    # Only original complete current source with no historical approval here
    # reaches VISIBLE. No object/account/store/order/approval is inserted.
    demo_id='demo_'+hashlib.sha256(canonical(list(current))).hexdigest()
    record=dict(id=demo_id,is_demo=True,display_only=True,name='示例生活小店',
                description='虚拟商家，仅供展示，不提供交易',category_id='DEMO_DINING',category_name='示例餐饮',
                category_state='DEMO',storefront_photo=None,photo_state='BUNDLED_DEMO_ASSET_PENDING',
                photo_asset_id=ASSET_ID,version=1,profile_version=0,
                payment_enabled=False,purchasing_enabled=False,include_in_real_statistics=False)
    return dict(state='VISIBLE',record=record)
