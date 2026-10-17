"""Authenticated Mini community directory, membership and campaign redemption.

Uses the same original directory/relationship records as the web portal. Only
successful authenticated redemptions are recorded; no invented view metrics.
"""
import hashlib
import json
import re
import secrets
from scripts.pr122_customer_core import canonical
from scripts.community_center_communities import CHANNEL,MEMBERS

PROMOTIONS='COMMUNITY_PROMOTION_V1'
REDEMPTIONS='COMMUNITY_PROMOTION_REDEMPTION'

def key(value):return hashlib.sha256(canonical(value)).hexdigest()

def load(c,channel,idx,project,aad):
    row=c.db.execute('SELECT payload FROM links WHERE channel=? AND subject_idx=? AND project=? AND active=1',(channel,idx,project)).fetchone()
    if row is None:raise PermissionError('COMMUNITY_RECORD_NOT_ACCESSIBLE')
    return json.loads(c.decrypt(row[0],aad+idx))

class ConsumerCommunities:
    def __init__(self,commerce):self.commerce=commerce;self.center=commerce.center
    def consumer(self,token,scene,op,p):
        fields={'communities':{'after_id'},'community_mine':set(),'community_join':{'community_id'},'community_leave':{'community_id'},'promotion_redeem':{'code'}}
        if op not in fields or type(p) is not dict or set(p)!=fields[op]:raise ValueError('INVALID_CONSUMER_COMMUNITY_FIELDS')
        uid,project,principal=self.commerce.identity._resolve(token,scene)
        if principal.role!='CUSTOMER':raise PermissionError('CONSUMER_SESSION_REQUIRED')
        identity=self.commerce.runtime.bindings[principal];tenant=identity['tenant_id'];c=self.center
        member_key=key([tenant,'CUSTOMER:'+uid])
        with c.tx():
            c.limit('community-consumer-directory:'+uid,60,60)
            if op=='communities':
                after=p['after_id']
                if type(after) is not str or after and not re.fullmatch('[0-9a-f]{64}',after):raise ValueError('INVALID_COMMUNITY_CURSOR')
                rows=c.db.execute('SELECT subject_idx,payload FROM links WHERE channel=? AND project=? AND active=1 AND subject_idx>? ORDER BY subject_idx LIMIT 51',(CHANNEL,project,after)).fetchall()
                records=[]
                for idx,raw in rows[:50]:
                    value=json.loads(c.decrypt(raw,'community-directory:'+idx))
                    if value['tenant']==tenant and value['state']=='APPROVED':records.append({k:value[k] for k in ('id','name','description','state')})
                return dict(records=records,has_more=len(rows)>50,next_cursor=rows[49][0] if len(rows)>50 else None)
            prior=c.db.execute('SELECT payload,active FROM links WHERE channel=? AND subject_idx=? AND project=?',(MEMBERS,member_key,project)).fetchone()
            previous=json.loads(c.decrypt(prior[0],'community-relation:'+member_key)) if prior else None
            if op=='community_mine':return dict(community_id=previous['community_id'] if prior and prior[1] else None,active=bool(prior and prior[1]))
            promotion=None
            if op=='promotion_redeem':
                if type(p['code']) is not str or not re.fullmatch('cp_[0-9a-f]{32}',p['code']):raise ValueError('INVALID_PROMOTION_CODE')
                promotion=load(c,PROMOTIONS,p['code'],project,'community-promotion:')
                if promotion['tenant']!=tenant or promotion['scene']!=scene or promotion['status']!='ACTIVE' or promotion['expires_at']<=c.now():raise PermissionError('ACTIVE_PROMOTION_FOR_THIS_SCENE_REQUIRED')
                community_id=promotion['community_id']
            else:community_id=p['community_id']
            if type(community_id) is not str or not re.fullmatch('co_[0-9a-f]{32}',community_id):raise ValueError('INVALID_COMMUNITY_ID')
            community=load(c,CHANNEL,key([tenant,community_id]),project,'community-directory:')
            if community['tenant']!=tenant:raise PermissionError('COMMUNITY_TENANT_DENIED')
            leaving=op=='community_leave'
            if not leaving and community['state']!='APPROVED':raise PermissionError('APPROVED_COMMUNITY_REQUIRED')
            if prior and prior[1] and previous['community_id']!=community_id:raise ValueError('LEAVE_EXISTING_COMMUNITY_FIRST')
            if leaving and (not prior or not prior[1] or previous['community_id']!=community_id):raise PermissionError('ACTIVE_COMMUNITY_MEMBERSHIP_REQUIRED')
            relation=dict(community_id=community_id,tenant=tenant,user_id=uid,kind='CUSTOMER',updated_at=c.now())
            c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,?) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload,active=excluded.active',(MEMBERS,member_key,uid,project,c.encrypt(canonical(relation),'community-relation:'+member_key),int(not leaving)))
            if promotion:
                event=key([promotion['id'],uid]);value=dict(promotion_id=promotion['id'],community_id=community_id,tenant=tenant,kind='ALREADY_MEMBER' if prior and prior[1] else 'JOINED',created_at=c.now())
                c.db.execute('INSERT OR IGNORE INTO links VALUES(?,?,?,?,?,1)',(REDEMPTIONS,event,uid,project,c.encrypt(canonical(value),'community-promotion-redemption:'+event)))
            c.audit(project,uid,'CONSUMER_'+op.upper(),community_id)
            return dict(community_id=community_id,active=not leaving)

class CommunityPromotions:
    def __init__(self,directory):self.directory=directory;self.center=directory.center
    def dispatch(self,session,csrf,body):
        op,p=body['operation'],body['params'];fields={'promotion_create':{'community_id','scene','title','expires_at'},'promotions':{'community_id','after_id'},'promotion_state':{'community_id','code','expected_version','status'}}
        if op not in fields or type(p) is not dict or set(p)!=fields[op]:raise ValueError('INVALID_PROMOTION_FIELDS')
        g=self.directory.authorize(session,csrf,body['workspace']);c=self.center
        community=self.directory.read(g,p['community_id'])
        if not (g['role']=='COMMUNITY_ADMIN' and community['owner']==g['user_id'] or g['role'] in ('PLATFORM_OWNER','PLATFORM_REVIEWER')):raise PermissionError('COMMUNITY_PROMOTION_OWNER_REQUIRED')
        with c.tx():
            c.limit('community-promotions:'+g['user_id'],30,60)
            if op=='promotions':
                if type(p['after_id']) is not str or p['after_id'] and not re.fullmatch('cp_[0-9a-f]{32}',p['after_id']):raise ValueError('INVALID_PROMOTION_CURSOR')
                rows=c.db.execute('SELECT subject_idx,payload FROM links WHERE channel=? AND project=? AND active=1 AND subject_idx>? ORDER BY subject_idx LIMIT 51',(PROMOTIONS,g['project'],p['after_id'])).fetchall();records=[]
                for idx,raw in rows[:50]:
                    value=json.loads(c.decrypt(raw,'community-promotion:'+idx))
                    if value['tenant']!=g['tenant'] or value['community_id']!=community['id']:continue
                    records.append(value)
                counts={value['id']:{'JOINED':0,'ALREADY_MEMBER':0} for value in records}
                for e,encrypted in c.db.execute('SELECT subject_idx,payload FROM links WHERE channel=? AND project=? AND active=1',(REDEMPTIONS,g['project'])):
                    redemption=json.loads(c.decrypt(encrypted,'community-promotion-redemption:'+e))
                    if redemption['promotion_id'] in counts and redemption['tenant']==g['tenant']:counts[redemption['promotion_id']][redemption['kind']]+=1
                records=[dict(v,authenticated_redemptions=sum(counts[v['id']].values()),new_members=counts[v['id']]['JOINED'],metrics='DISTINCT_AUTHENTICATED_REDEMPTIONS_ONLY') for v in records]
                return dict(records=records,has_more=len(rows)>50,next_cursor=rows[49][0] if len(rows)>50 else None)
            if community['state']!='APPROVED':raise PermissionError('APPROVED_COMMUNITY_REQUIRED')
            if op=='promotion_create':
                scene=self.directory.commerce.identity.scenes.get(p['scene']) if type(p['scene']) is str else None
                if scene is None or scene['project']!=g['project'] or self.directory.commerce.runtime.bindings[scene['principal']]['tenant_id']!=g['tenant']:raise PermissionError('ORIGINAL_MINI_SCENE_REQUIRED')
                if type(p['title']) is not str or not 1<=len(p['title'].strip())<=120 or type(p['expires_at']) is not int or not c.now()<p['expires_at']<=c.now()+90*86400:raise ValueError('INVALID_PROMOTION_TITLE_OR_EXPIRY')
                code='cp_'+secrets.token_hex(16);value=dict(id=code,community_id=community['id'],tenant=g['tenant'],scene=p['scene'],title=p['title'].strip(),expires_at=p['expires_at'],status='ACTIVE',version=1,created_at=c.now())
            else:
                code=p['code']
                if type(code) is not str or not re.fullmatch('cp_[0-9a-f]{32}',code):raise ValueError('INVALID_PROMOTION_CODE')
                value=load(c,PROMOTIONS,code,g['project'],'community-promotion:')
                if value['community_id']!=community['id'] or value['tenant']!=g['tenant']:raise PermissionError('OWN_COMMUNITY_PROMOTION_REQUIRED')
                if type(p['expected_version']) is not int or p['expected_version']!=value['version'] or p['status'] not in ('ACTIVE','PAUSED'):raise ValueError('INVALID_PROMOTION_VERSION_OR_STATE')
                value=dict(value,status=p['status'],version=value['version']+1)
            c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload',(PROMOTIONS,code,community['owner'],g['project'],c.encrypt(canonical(value),'community-promotion:'+code)))
            c.audit(g['project'],g['user_id'],'COMMUNITY_'+op.upper(),code)
            return dict(value,mini_page='pages/checkout/index?scene='+value['scene']+'&promotion='+code)
