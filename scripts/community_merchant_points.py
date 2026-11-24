"""Merchant points backed only by verified successful community splits.

One point represents CNY 0.10 actually split to the community.  The account is
kept in the original encrypted Center store so split observation, idempotency
and points mutation share one SQLite transaction.
"""
import hashlib
import json
from scripts.pr122_customer_core import canonical
from scripts.community_merchant_contract import valid_id


CHANNEL='COMMUNITY_MERCHANT_POINTS_V1'
PURPOSES=('CHARITY_MALL','ALLIANCE_MERCHANT')
REDEMPTION_PERCENT_OPTIONS=(0,10,20,25,30)


class MerchantPoints:
    def __init__(self,center):self.center=center

    def _key(self,g):return hashlib.sha256(canonical(g['scope'])).hexdigest()
    def _read(self,g):
        key=self._key(g)
        row=self.center.db.execute("SELECT payload FROM links WHERE channel=? AND subject_idx=? AND project=? AND active=1",(CHANNEL,key,g['project'])).fetchone()
        if row is None:return dict(revision=0,redemption_percent=10,earnings={},redemptions={},returns={},redemption_returns={})
        value=json.loads(self.center.decrypt(row[0],'merchant-points:'+key))
        # Records written before redemption reversal support remain readable.
        value.setdefault('redemption_returns',{})
        return value
    def _save(self,g,value):
        key=self._key(g);payload=self.center.encrypt(canonical(value),'merchant-points:'+key)
        self.center.db.execute("INSERT INTO links VALUES(?,?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload,user_id=excluded.user_id,active=1",(CHANNEL,key,g['user_id'],g['project'],payload))
    def _approved_percent(self,g):
        key=self._key(g)
        rows=self.center.db.execute("SELECT project,payload FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING' AND subject_idx=? AND user_id=? AND active=1",(key,g['user_id'])).fetchall()
        if not rows:return None
        if len(rows)!=1:raise PermissionError('MERCHANT_POINTS_OPENING_CHANGED')
        row=rows[0]
        application,payload=row
        opening=json.loads(self.center.decrypt(payload,'community-opening:'+key+':'+application))
        if (opening.get('state')!='OPENED' or opening.get('scope')!=g['scope'] or opening.get('project')!=g['project']):
            raise PermissionError('MERCHANT_POINTS_OPENING_CHANGED')
        meta_row=self.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_ONBOARDING' AND subject_idx=? AND project=? AND user_id=? AND active=1",(application,application,g['user_id'])).fetchone()
        if meta_row is None:raise PermissionError('MERCHANT_POINTS_APPROVAL_REQUIRED')
        meta=json.loads(self.center.decrypt(meta_row[0],'onboarding-meta:'+application))
        value=meta.get('approved_redemption_percent')
        if type(value) is not int or value not in REDEMPTION_PERCENT_OPTIONS:raise PermissionError('MERCHANT_POINTS_APPROVAL_REQUIRED')
        return value
    @staticmethod
    def _available(value,now):
        total=debt=0
        for lot in value['earnings'].values():
            consumed=lot.get('spent_points',0)+lot.get('reversed_points',0)
            if consumed>lot['points']:debt+=consumed-lot['points']
            elif lot['expires_at']>now:total+=lot['points']-consumed
        return total-debt
    def record_split(self,g,action_key,saved,result):
        if result.get('status')!='FINISHED':return
        amount=sum(r['amount_minor'] for r in result.get('receivers',()) if r.get('result')=='SUCCESS')
        points=amount//10
        if points<=0:return
        value=self._read(g)
        prior=value['earnings'].get(action_key)
        record=dict(reference=saved['reference'],provider_reference=saved['provider_reference'],split_amount_minor=amount,
                    points=points,earned_at=self.center.now(),expires_at=self.center.now()+365*86400,spent_points=0,reversed_points=0)
        if prior is not None:
            if any(prior[k]!=record[k] for k in ('reference','provider_reference','split_amount_minor','points')):raise ValueError('POINTS_SPLIT_RESULT_CONFLICT')
            return
        value['earnings'][action_key]=record;value['revision']+=1;self._save(g,value)
        self.center.audit(g['project'],g['user_id'],'MERCHANT_POINTS_EARNED',action_key)
    def record_return(self,g,split_key,return_key,amount_minor):
        if not valid_id(split_key) or not valid_id(return_key) or type(amount_minor) is not int or amount_minor<=0:
            raise ValueError('INVALID_POINTS_SPLIT_RETURN')
        value=self._read(g)
        if return_key in value['returns']:
            if value['returns'][return_key]['split_key']!=split_key or value['returns'][return_key]['amount_minor']!=amount_minor:raise ValueError('POINTS_RETURN_RESULT_CONFLICT')
            return
        lot=value['earnings'].get(split_key)
        # A verified split below the 0.10 CNY earning threshold creates no lot;
        # its later return must not block the provider return lifecycle.
        if lot is None:return
        returned_minor=amount_minor+sum(item['amount_minor'] for item in value['returns'].values() if item['split_key']==split_key)
        if returned_minor>lot['split_amount_minor']:raise ValueError('POINTS_RETURN_EXCEEDS_ORIGINAL_SPLIT')
        target_points=returned_minor//10;points=target_points-lot['reversed_points']
        lot['reversed_points']=target_points;value['returns'][return_key]=dict(split_key=split_key,amount_minor=amount_minor,points=points)
        value['revision']+=1;self._save(g,value);self.center.audit(g['project'],g['user_id'],'MERCHANT_POINTS_REVERSED',return_key)
    def reverse_redemption(self,g,request_id,redemption_id,points):
        if not valid_id(request_id) or not valid_id(redemption_id) or type(points) is not int or points<=0:
            raise ValueError('INVALID_POINTS_REDEMPTION_RETURN')
        value=self._read(g);request_hash=hashlib.sha256(canonical(dict(redemption_id=redemption_id,points=points))).hexdigest()
        prior=value['redemption_returns'].get(request_id)
        if prior is not None:
            if prior['request_hash']!=request_hash:raise ValueError('POINTS_REDEMPTION_RETURN_ID_COLLISION')
            return prior
        redemption=value['redemptions'].get(redemption_id)
        if redemption is None:raise ValueError('POINTS_ORIGINAL_REDEMPTION_REQUIRED')
        already=sum(item['points'] for item in value['redemption_returns'].values() if item['redemption_id']==redemption_id)
        if already+points>redemption['points']:raise ValueError('POINTS_REDEMPTION_RETURN_EXCEEDS_ORIGINAL')
        released={};left=points
        for key,allocated in sorted(redemption['allocations'].items()):
            returned=sum(item['allocations'].get(key,0) for item in value['redemption_returns'].values() if item['redemption_id']==redemption_id)
            amount=min(left,allocated-returned)
            if amount:
                lot=value['earnings'].get(key)
                if lot is None or lot.get('spent_points',0)<amount:raise ValueError('POINTS_REDEMPTION_RETURN_STATE_CONFLICT')
                lot['spent_points']-=amount;released[key]=amount;left-=amount
            if not left:break
        if left:raise ValueError('POINTS_REDEMPTION_RETURN_STATE_CONFLICT')
        result=dict(request_hash=request_hash,redemption_id=redemption_id,points=points,allocations=released,created_at=self.center.now())
        value['redemption_returns'][request_id]=result;value['revision']+=1;self._save(g,value)
        self.center.audit(g['project'],g['user_id'],'MERCHANT_POINTS_REDEMPTION_REVERSED',request_id)
        return result
    def dispatch(self,g,operation,p):
        fields={'community.points_summary':set(),'community.points_records':set(),'community.points_setting_save':{'redemption_percent','expected_revision'},
                'community.points_redeem':{'request_id','purpose','order_amount_minor','points'},
                'community.points_redeem_reverse':{'request_id','redemption_id','points'}}
        if operation not in fields or type(p) is not dict or set(p)!=fields[operation]:raise ValueError('INVALID_MERCHANT_POINTS_FIELDS')
        c=self.center
        with c.tx():
            value=self._read(g);now=c.now()
            approved_percent=self._approved_percent(g)
            effective_percent=value['redemption_percent'] if approved_percent is None else approved_percent
            if operation=='community.points_records':
                records=[]
                for key,item in value['earnings'].items():
                    records.append(dict(id=key,type='EARN',points=item['points'],reference=item['reference'],created_at=item['earned_at'],expires_at=item['expires_at']))
                    if item.get('reversed_points',0):records.append(dict(id=key+'-return',type='RETURN',points=item['reversed_points'],reference=item['reference'],created_at=item['earned_at']))
                    remaining=max(0,item['points']-item.get('spent_points',0)-item.get('reversed_points',0))
                    if item['expires_at']<=now and remaining:records.append(dict(id=key+'-expired',type='EXPIRE',points=remaining,reference=item['reference'],created_at=item['expires_at']))
                for key,item in value['redemptions'].items():records.append(dict(id=key,type='REDEEM',points=item['points'],reference=key,created_at=item['created_at']))
                for key,item in value['redemption_returns'].items():records.append(dict(id=key,type='RETURN',points=item['points'],reference=item['redemption_id'],created_at=item['created_at']))
                records.sort(key=lambda item:(item['created_at'],item['id']),reverse=True)
                return dict(records=records)
            if operation=='community.points_setting_save':
                if approved_percent is not None:raise PermissionError('APPROVED_REDEMPTION_PERCENT_IMMUTABLE')
                if type(p['redemption_percent']) is not int or p['redemption_percent'] not in REDEMPTION_PERCENT_OPTIONS or type(p['expected_revision']) is not int or p['expected_revision']!=value['revision']:raise ValueError('MERCHANT_POINTS_SETTING_CONFLICT')
                value['redemption_percent']=p['redemption_percent'];effective_percent=p['redemption_percent'];value['revision']+=1;self._save(g,value);c.audit(g['project'],g['user_id'],'MERCHANT_POINTS_SETTING_SAVED',self._key(g))
            elif operation=='community.points_redeem':
                if (not valid_id(p['request_id']) or p['purpose'] not in PURPOSES or type(p['order_amount_minor']) is not int or p['order_amount_minor']<=0
                        or type(p['points']) is not int or p['points']<=0):raise ValueError('INVALID_POINTS_REDEMPTION')
                request_hash=hashlib.sha256(canonical(p)).hexdigest();prior=value['redemptions'].get(p['request_id'])
                if prior is not None:
                    if prior['request_hash']!=request_hash:raise ValueError('POINTS_REDEMPTION_ID_COLLISION')
                    return prior
                maximum=p['order_amount_minor']*effective_percent//100//10
                if p['points']>maximum or p['points']>self._available(value,now):raise ValueError('POINTS_REDEMPTION_EXCEEDS_LIMIT')
                left=p['points'];allocations={}
                for key,lot in sorted(value['earnings'].items(),key=lambda item:(item[1]['expires_at'],item[0])):
                    available=max(0,lot['points']-lot.get('spent_points',0)-lot.get('reversed_points',0)) if lot['expires_at']>now else 0
                    used=min(left,available)
                    if used:lot['spent_points']=lot.get('spent_points',0)+used;allocations[key]=used;left-=used
                    if not left:break
                if left:raise ValueError('POINTS_BALANCE_CHANGED')
                result=dict(request_hash=request_hash,purpose=p['purpose'],points=p['points'],cash_offset_minor=p['points']*10,order_amount_minor=p['order_amount_minor'],redemption_percent=effective_percent,allocations=allocations,created_at=now)
                value['redemptions'][p['request_id']]=result;value['revision']+=1;self._save(g,value);c.audit(g['project'],g['user_id'],'MERCHANT_POINTS_REDEEMED',p['request_id'])
                return result
            elif operation=='community.points_redeem_reverse':
                return self.reverse_redemption(g,p['request_id'],p['redemption_id'],p['points'])
            available=self._available(value,now)
            earned=sum(x['points'] for x in value['earnings'].values())
            expired=sum(max(0,x['points']-x.get('spent_points',0)-x.get('reversed_points',0)) for x in value['earnings'].values() if x['expires_at']<=now)
            redeemed=sum(x['points'] for x in value['redemptions'].values())
            redemption_reversed=sum(x['points'] for x in value['redemption_returns'].values())
            return dict(revision=value['revision'],available_points=available,total_earned_points=earned,expired_points=expired,
                        redemption_percent=effective_percent,redemption_percent_locked=approved_percent is not None,cash_value_minor=max(0,available)*10,valid_days=365,
                        total_redeemed_points=redeemed,total_redemption_reversed_points=redemption_reversed,
                        earn_rule='社区捐赠0.1元=1积分',exchange_rule='10积分=1元',purposes=list(PURPOSES))
