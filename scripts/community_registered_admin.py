"""Existing business writes after original Center grant authorization.

Local demo capabilities remain confined to their original loopback adapter;
Center-authenticated stores do not borrow a different store's demo token.
"""
from scripts.community_merchant_store import upsert_profile,put_item
from scripts.community_ad_store import create_campaign,change_campaign_state,review_creative


def dispatch(service,identity,role,actor_id,operation,params,now):
    schemas={'community.profile':{'record','expected_version'},'community.item':{'item'},
        'community.ad_create':{'record'},'community.ad_state':{'campaign_id','state','expected_version'},
        'community.ad_review':{'campaign_id','approved','expected_version'}}
    if operation not in schemas or type(params) is not dict or set(params)!=schemas[operation]:raise ValueError('INVALID_REGISTERED_ADMIN_FIELDS')
    review=operation=='community.ad_review'
    if role not in (('PLATFORM_OWNER','PLATFORM_REVIEWER') if review else ('MERCHANT_ADMIN',)):raise PermissionError('REGISTERED_ADMIN_ROLE_REQUIRED')
    actor=dict(authenticated=True,role='PLATFORM_ADMIN' if review else 'MERCHANT_ADMIN',actor_id=actor_id,**identity)
    if operation=='community.profile':result=upsert_profile(service.merchant_db,identity,actor,params['record'],params['expected_version'])
    elif operation=='community.item':put_item(service.merchant_db,identity,actor,params['item']);result=dict(written=True)
    elif operation=='community.ad_create':result=create_campaign(service.ad_db,identity,params['record'],actor,now)
    elif operation=='community.ad_state':result=change_campaign_state(service.ad_db,identity,params['campaign_id'],params['state'],actor,now,params['expected_version'])
    else:result=review_creative(service.ad_db,identity,params['campaign_id'],params['approved'],actor,now,params['expected_version'])
    return dict(result=result,admin_command_executed=True,provider_settlement_verified=False)
