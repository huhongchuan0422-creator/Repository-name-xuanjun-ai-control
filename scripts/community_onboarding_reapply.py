"""Original Center adapter. Protected composition only; no provider IO/schema."""
import hashlib
import json
from scripts.pr122_customer_core import canonical
from scripts.community_reapply_contract import Policy, Target, Snapshot, plan_release, need, digest

KEY='test_reapply_cursor'


def cursors(service, owner):
    rows=service.center.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_ONBOARDING' AND user_id=? AND active=1 AND project=subject_idx",(owner,)).fetchall()
    return [(row[0],meta,meta[KEY]) for row in rows
            for meta in [service._decode(row[1],'onboarding-meta:'+row[0])] if KEY in meta]


def current(service, owner):
    values=cursors(service,owner)
    need(len(values)<=1,'AMBIGUOUS_CURRENT_APPLICATION_CURSOR')
    if not values:return None
    old,meta,value=values[0]
    return dict(application=value['application'],generation=value['generation'],
                version=value['version'],previous_application=old)


def attach_new(service,owner,application,meta):
    # Participate in save's existing BEGIN IMMEDIATE; rollback preserves draft.
    values=cursors(service,owner)
    if not values:return
    need(len(values)==1,'AMBIGUOUS_CURRENT_APPLICATION_CURSOR')
    old,oldmeta,cursor=values[0]
    need(cursor['application'] is None,'CURRENT_GENERATION_ALREADY_HAS_APPLICATION')
    cursor['application']=application;cursor['version']+=1
    meta['business_generation']=cursor['generation']
    meta['business_provider_ref']=cursor['receipt']['next_provider_ref']
    service._meta(old,owner,oldmeta)


def snapshot(service,application,actor):
    c=service.center
    owner,meta,platform=service._load(application,actor,True)
    loader=service.reapply_authority
    need(callable(loader),'PROTECTED_TEST_POLICY_DISABLED')
    facts=loader(c,application)  # re-read inside the SAME Center write lock
    need(type(facts) is dict,'PROTECTED_AUTHORITY_FACTS_REQUIRED')
    policy=Policy(tuple(Target(**dict(t,scope=tuple(t['scope']))) for t in facts['targets']),
                  facts['new_provider_ref'],facts['dots_effect_ref'],facts.get('enabled',False))
    target=next((t for t in policy.targets if t.application_ref==application and t.owner_ref==owner),None)
    need(target is not None,'EXACT_TEST_OWNER_APPLICATION_STORE_PROVIDER_REQUIRED')
    origin=meta.get('ocr_origin')
    if origin is not None:
        need(tuple(origin['scope'][k] for k in ('tenant_id','merchant_id','store_id'))==target.scope,'ORIGINAL_SCOPE_CHANGED')
    service._reviewer(actor)
    account=c.db.execute('SELECT verified,epoch FROM accounts WHERE id=?',(owner,)).fetchone()
    need(account is not None and account[0]==1,'VERIFIED_ORIGINAL_ACCOUNT_REQUIRED')
    record=service.wechat_applyment._read(application) if service.wechat_applyment is not None else None
    need(type(record) is dict and record.get('provider_sp_mchid')==target.old_provider_ref,'OLD_PROVIDER_RECORD_REQUIRED')
    row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_WECHAT_OBSERVATION' AND subject_idx=? AND user_id=? AND project=? AND active=1",(application,owner,application)).fetchone()
    obs=None if row is None else json.loads(c.decrypt(row[0],'wechat-observation:'+application))
    binding=(obs or {}).get('binding',{});mb=(obs or {}).get('merchant_binding',{})
    record_hash=hashlib.sha256(canonical(record)).hexdigest()
    need(type(obs) is dict and obs.get('record_digest')==record_hash and obs.get('sync_error') is None and
         binding.get('active') is True and binding.get('owner')==owner and binding.get('application')==application and
         binding.get('provider_merchant')==target.old_provider_ref and binding.get('business_code')==record.get('business_code') and
         binding.get('applyment_id')==record.get('applyment_id'),'EXACT_VERIFIED_OBSERVATION_REQUIRED')
    need(all(mb.get(k)==v for k,v in dict(owner=owner,application=application,record_digest=record_hash,
         business_code=record.get('business_code'),applyment_id=record.get('applyment_id'),account_epoch=account[1]).items()) and
         mb.get('signature_sha256')==obs.get('provider_query_signature_sha256') and
         type(mb.get('signature_sha256')) is str and len(mb['signature_sha256'])==64,'EXACT_OLD_FINISHED_PROOF_REQUIRED')
    cursor=meta.get(KEY)
    historical=dict(meta);historical.pop(KEY,None)
    openings=[tuple(r) for r in c.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING' AND user_id=? AND project=? AND active=1",(owner,application))]
    # Ciphertext bytes are represented deterministically without decoding PII.
    openings=[(k,hashlib.sha256(v if isinstance(v,bytes) else v.encode()).hexdigest()) for k,v in openings]
    events=[tuple(r) for r in c.db.execute('SELECT revision,digest FROM onboarding_events WHERE tenant=? AND application=? ORDER BY revision',(owner,application))]
    history=digest(dict(meta=historical,platform=platform,record=record,observation=obs,openings=openings,events=events))
    reader=service.wechat_applyment.reader
    reconciliation=facts.get('reconciliation',{})
    need(reconciliation.get('owner_ref')==owner and reconciliation.get('application_ref')==application and
         tuple(reconciliation.get('scope',()))==target.scope,'EXACT_RECONCILIATION_SCOPE_REQUIRED')
    rows=c.db.execute("SELECT project,payload FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND user_id=? AND active=1",(owner,)).fetchall()
    unknown=any(json.loads(c.decrypt(r[1],'wechat-applyment:'+r[0])).get('state')=='SUBMISSION_UNKNOWN' for r in rows)
    state=Snapshot(owner,application,target.scope,target.old_provider_ref,reader._mchid,
        cursor['version'] if cursor else 1,cursor['receipt']['generation'] if cursor else 1,
        obs.get('provider_state'),digest(obs),mb.get('sub_mchid'),unknown,
        reconciliation.get('receipt_ref'),reconciliation.get('financial_clear') is True,
        account[1],facts.get('login_identity_ref',''),history)
    need(facts.get('account_epoch')==account[1],'ORIGINAL_LOGIN_EPOCH_CHANGED')
    return policy,state,target.alias,owner,meta


def dispatch(service,session,csrf,operation,params):
    c=service.center
    need(not c.db.in_transaction,'EXTERNAL_TRANSACTION_DENIED')
    c.db.execute('BEGIN IMMEDIATE')
    try:
        actor=c.session(session,csrf);service._reviewer(actor)
        policy,state,alias,owner,meta=snapshot(service,params['application'],actor)
        old=meta.get(KEY)
        need(old is None or old['application'] is None,'CURRENT_GENERATION_ALREADY_HAS_APPLICATION')
        receipt=plan_release(policy,state,alias=alias,expected_version=params['expected_version'],
            idempotency_key=params['idempotency_key'],prior_receipt=old['receipt'] if old else None)
        if operation=='reapply_release' and not receipt['replay']:
            meta[KEY]=dict(version=receipt['released_version'],generation=receipt['next_generation'],application=None,receipt=receipt)
            service._meta(params['application'],owner,meta)
            c.audit(params['application'],actor,'MERCHANT_TEST_REAPPLY_RELEASE',receipt['request_digest'])
        need(c.session(session,csrf)==actor,'CURRENT_REVIEWER_SESSION_REQUIRED')
        c.db.commit()
        return dict(status='PREVIEW' if operation=='reapply_preview' else 'RELEASED',
                    expected_version=params['expected_version'],receipt=receipt,
                    current_cursor=current(service,owner))
    except BaseException:
        c.db.rollback();raise
