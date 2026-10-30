"""Explicit public display projection over original approved merchant workspaces.
No applicant material is ever published by this module. No new merchant registry.
"""
import hashlib
import json
import re
from scripts.pr122_customer_core import canonical
from scripts.community_merchant_store import profile
from scripts.community_merchant_opening import authorize_workspace
from scripts.community_platform_merchants import assert_trading

CHANNEL='COMMUNITY_PUBLIC_DISPLAY_V1'

def key(g):return hashlib.sha256(canonical([g['project'],g['scope']])).hexdigest()

def approved(ops,workspace,g):
    if g['role']!='MERCHANT_ADMIN' or not g['onboarding_required'] or ops.onboarding is None:
        raise PermissionError('CURRENT_APPROVED_OPENING_REQUIRED')
    authorize_workspace(ops.onboarding,ops,workspace,g['user_id'])

def read_record(c,g):
    k=key(g)
    row=c.db.execute('SELECT payload FROM links WHERE channel=? AND subject_idx=? AND project=? AND user_id=? AND active=1',(CHANNEL,k,g['project'],g['user_id'])).fetchone()
    if row is None:return None
    record=json.loads(c.decrypt(row[0],'community-public-display:'+k))
    if (type(record)is not dict or set(record)!={'project','scope','version','published','category_id','category_name','updated_at'}
            or record['scope']!=g['scope'] or record['project']!=g['project']
            or type(record['version'])is not int or record['version']<1 or type(record['published'])is not bool):
        raise ValueError('PUBLIC_DISPLAY_RECORD_INVALID')
    return record

def settings(ops,workspace,g,operation,p):
    approved(ops,workspace,g)
    c=ops.center
    if operation=='community.public_profile_read':
        if p!={}:raise ValueError('INVALID_PUBLIC_DISPLAY_FIELDS')
        old=read_record(c,g)
        return dict(version=old['version'] if old else 0,published=old['published'] if old else False,
                    category_id=old['category_id'] if old else '',category_name=old['category_name'] if old else '',
                    storefront_photo=None,photo_state='NOT_CONNECTED')
    if set(p)!={'expected_version','published','category_id','category_name'} or type(p['expected_version']) is not int or p['expected_version']<0 or type(p['published']) is not bool:
        raise ValueError('INVALID_PUBLIC_DISPLAY_FIELDS')
    cid,label=p['category_id'],p['category_name']
    if type(cid)is not str or cid and not re.fullmatch('[A-Za-z0-9_-]{1,40}',cid) or type(label)is not str or len(label)>60 or any(ord(ch)<32 for ch in label) or bool(cid)!=bool(label.strip()):
        raise ValueError('INVALID_PUBLIC_DISPLAY_CATEGORY')
    if p['published']:
        profile(ops.runtime.demo.merchant_db,g['scope']);assert_trading(c,g['scope'])
    with c.tx():
        old=read_record(c,g)
        if p['expected_version']!=(old['version'] if old else 0):raise ValueError('PUBLIC_DISPLAY_VERSION_CONFLICT')
        record=dict(project=g['project'],scope=g['scope'],version=p['expected_version']+1,published=p['published'],category_id=cid,category_name=label.strip(),updated_at=c.now())
        k=key(g)
        c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload,user_id=excluded.user_id,active=1',(CHANNEL,k,g['user_id'],g['project'],c.encrypt(canonical(record),'community-public-display:'+k)))
        c.audit(g['project'],g['user_id'],'PUBLIC_DISPLAY_SAVED',k)
    return dict(version=record['version'],published=record['published'],storefront_photo=None,photo_state='NOT_CONNECTED')

def consumer(gateway,token,operation,p):
    if type(p) is not dict:
        raise ValueError('INVALID_PUBLIC_DIRECTORY_FIELDS')
    from scripts.community_mini_center_identity import CenterIdentity
    identity=gateway.identity
    if type(identity)is not CenterIdentity:raise PermissionError('ORIGINAL_CENTER_IDENTITY_REQUIRED')
    identity.applicant_context(token)
    commerce=getattr(gateway,'commerce',None)
    if commerce is None:raise PermissionError('COMMERCE_NOT_CONFIGURED')
    ops=commerce.operations
    if operation=='customer.store' and type(p.get('id'))is str and p['id'].startswith('demo_'):
        if set(p)!={'id'}:raise ValueError('INVALID_PUBLIC_STORE_ID')
        from scripts.community_demo_directory import presentation
        demo=presentation(gateway,token)
        if demo['state']!='VISIBLE' or demo['record']['id']!=p['id']:
            raise PermissionError('PUBLIC_STORE_NOT_ACCESSIBLE')
        return demo['record']
    if operation=='customer.store':
        if set(p)!={'id'} or type(p['id'])is not str or not re.fullmatch('[0-9a-f]{64}',p['id']):raise ValueError('INVALID_PUBLIC_STORE_ID')
        after='';category=''
    else:
        if type(p)is not dict or set(p)-{'after_id','category_id'}:raise ValueError('INVALID_PUBLIC_DIRECTORY_FIELDS')
        after=p.get('after_id','');category=p.get('category_id','')
        if type(after)is not str or after and not re.fullmatch('[0-9a-f]{64}',after) or type(category)is not str or category and not re.fullmatch('[A-Za-z0-9_-]{1,40}',category):raise ValueError('INVALID_PUBLIC_DIRECTORY_CURSOR')
    allowed=set()
    for scene in identity.scenes:
        try:
            _,project,principal=identity._resolve(token,scene)
        except PermissionError:continue
        allowed.add((project,principal.tenant_id))
    records={};categories={}
    for workspace,g in ops.grants.items():
        if (g['project'],g['tenant']) not in allowed or g['role']!='MERCHANT_ADMIN':continue
        try:
            approved(ops,workspace,g)
            saved=read_record(ops.center,g)
            if not saved or not saved['published']:continue
            merchant=profile(ops.runtime.demo.merchant_db,g['scope']);assert_trading(ops.center,g['scope'])
        except PermissionError:continue
        except ValueError as exc:
            if str(exc)=='UNAVAILABLE_STOREFRONT':continue
            raise
        k=key(g)
        if operation=='customer.store' and k!=p['id']:continue
        if saved['category_id']:
            category_key=(saved['category_id'],saved['category_name'])
            categories[category_key]=dict(id=saved['category_id'],name=saved['category_name'])
        if category and saved['category_id']!=category:continue
        records[k]=dict(id=k,name=merchant['name'],description=merchant['description'],category_id=saved['category_id'] or None,category_name=saved['category_name'] or None,category_state='AVAILABLE' if saved['category_id'] else 'NOT_CONFIGURED',storefront_photo=None,photo_state='NOT_CONNECTED',version=saved['version'],profile_version=merchant['version'])
    if operation=='customer.store':
        if p['id'] not in records:raise PermissionError('PUBLIC_STORE_NOT_ACCESSIBLE')
        return records[p['id']]
    names=[k for k in sorted(records) if k>after][:51]
    from scripts.community_demo_directory import presentation
    demo=presentation(gateway,token)
    return dict(demo=demo,records=[records[k] for k in names[:50]],categories=[categories[k] for k in sorted(categories)],has_more=len(names)>50,next_cursor=names[49] if len(names)>50 else None,visibility='CURRENT_AUTHORIZED_PROJECT_TENANT',storefront_photo_supported=False)
