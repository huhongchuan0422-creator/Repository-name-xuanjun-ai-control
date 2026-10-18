"""Project-scoped platform operations views over original identity and stores.

No cross-project account search, credential fields or synthetic Finance ledger.
Verified payment observations and local order state are reported separately.
"""
import json
import re
from scripts.community_platform_merchants import PlatformMerchants
from scripts.community_order_provider_projection import provider_evidence

class PlatformViews:
    def __init__(self,directory):self.directory=directory;self.center=directory.center
    def dispatch(self,session,csrf,body):
        op,p=body['operation'],body['params'];fields={'platform_overview':set(),'platform_orders':{'after_id','status'},'platform_customers':{'after_id'},'platform_audit':{'after_id'}}
        if op not in fields or type(p) is not dict or set(p)!=fields[op]:raise ValueError('INVALID_PLATFORM_VIEW_FIELDS')
        g=self.directory.authorize(session,csrf,body['workspace'])
        if g['role'] not in ('PLATFORM_OWNER','PLATFORM_REVIEWER'):raise PermissionError('PLATFORM_READ_PERMISSION_REQUIRED')
        c=self.center;ops=self.directory.commerce.operations
        unavailable=[]
        # Customer membership and project audit do not depend on a merchant's
        # separate access grant. Store-based views report incomplete coverage.
        if op in ('platform_overview','platform_orders'):
            targets=PlatformMerchants(self.directory)._targets(g,unavailable)
            identities={tuple(v['scope'][k] for k in ('tenant_id','merchant_id','store_id')) for v in targets.values()}
            where=' OR '.join('(tenant_id=? AND merchant_id=? AND store_id=?)' for _ in identities) or '0'
            args=tuple(x for identity in sorted(identities) for x in identity)
        db=ops.runtime.demo.db
        with c.tx():c.limit('community-platform-view:'+g['user_id'],30,60)
        if op=='platform_orders':
            if type(p['after_id']) is not int or not 0<=p['after_id']<=9223372036854775807 or p['status'] not in ('ALL','PENDING','SUCCESS','FAILED','CANCELLED','REFUNDED'):raise ValueError('INVALID_PLATFORM_ORDER_PAGE')
            suffix='' if p['status']=='ALL' else ' AND state=?'
            rows=db.execute('SELECT rowid,tenant_id,merchant_id,store_id,reference,amount_minor,currency,state FROM orders WHERE ('+where+') AND rowid>?'+suffix+' ORDER BY rowid LIMIT 51',args+(p['after_id'],)+(() if p['status']=='ALL' else (p['status'],))).fetchall()
            records=[]
            for idx,t,m,s,ref,amount,currency,status in rows[:50]:
                identity=dict(tenant_id=t,merchant_id=m,store_id=s);evidence=provider_evidence(db,identity,ref)
                records.append(dict(id=idx,scope=identity,reference=ref,amount_minor=amount,currency=currency,order_state=status,payment_evidence=evidence['source'] if evidence else None,finance_status='UNCONFIRMED'))
            result=dict(records=records,has_more=len(rows)>50,next_cursor=rows[49][0] if len(rows)>50 else None)
        elif op=='platform_customers':
            if type(p['after_id']) is not str or p['after_id'] and not re.fullmatch('[A-Za-z0-9_-]{1,64}',p['after_id']):raise ValueError('INVALID_PLATFORM_CUSTOMER_CURSOR')
            rows=c.db.execute('SELECT m.user_id,m.role,m.active,a.verified FROM members m JOIN accounts a ON a.id=m.user_id WHERE m.project=? AND m.user_id>? ORDER BY m.user_id LIMIT 51',(g['project'],p['after_id'])).fetchall();records=[]
            project,_,_=c.project(g['user_id'],g['project'])
            for uid,role,active,verified in rows[:50]:
                idx=c.idx('community-profile:'+g['project']+':'+uid)
                profile=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_CUSTOMER_PROFILE' AND subject_idx=? AND user_id=? AND project=? AND active=1",(idx,uid,g['project'])).fetchone()
                value=json.loads(c.decrypt(profile[0],'COMMUNITY_CUSTOMER_PROFILE:'+idx)) if profile else {}
                from scripts.community_consumer_communities import key
                member_key=key([g['tenant'],'CUSTOMER:'+uid]);member=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_RELATION_V1' AND subject_idx=? AND user_id=? AND project=? AND active=1",(member_key,uid,g['project'])).fetchone()
                community=json.loads(c.decrypt(member[0],'community-relation:'+member_key))['community_id'] if member else None
                orders=c.db.execute("SELECT COUNT(*) FROM links WHERE channel='COMMUNITY_ORDER' AND user_id=? AND project=? AND active=1",(uid,g['project'])).fetchone()[0]
                records.append(dict(user_id=uid,project_customer_id=project['customer'],project_role=role,membership_active=bool(active),verified=bool(verified),nickname=value.get('nickname',''),community_id=community,owned_order_count=orders))
            result=dict(records=records,has_more=len(rows)>50,next_cursor=rows[49][0] if len(rows)>50 else None,coverage='ORIGINAL_PROJECT_MEMBERS_NOT_GLOBAL_ACCOUNTS')
        elif op=='platform_audit':
            if type(p['after_id']) is not int or not 0<=p['after_id']<=9223372036854775807:raise ValueError('INVALID_PLATFORM_AUDIT_CURSOR')
            rows=c.db.execute('SELECT seq,actor,event,object_id,at,parent,sha FROM audit WHERE project=? AND seq>? ORDER BY seq LIMIT 51',(g['project'],p['after_id'])).fetchall()
            result=dict(records=[dict(zip(('id','actor','event','object_id','at','parent','sha'),r)) for r in rows[:50]],has_more=len(rows)>50,next_cursor=rows[49][0] if len(rows)>50 else None,chain_scope='PROJECT_FILTERED_GLOBAL_APPEND_ONLY_CHAIN')
        else:
            order_counts={};verified_count=0;verified_minor=0;verified_refunds=0;unverified_terminal=0
            for t,m,s,ref,amount,currency,status in db.execute('SELECT tenant_id,merchant_id,store_id,reference,amount_minor,currency,state FROM orders WHERE ('+where+')',args):
                order_counts[status]=order_counts.get(status,0)+1
                evidence=provider_evidence(db,dict(tenant_id=t,merchant_id=m,store_id=s),ref)
                if evidence is not None and status in ('SUCCESS','REFUNDED') and currency=='CNY':
                    verified_count+=1;verified_minor+=amount
                    from scripts.community_financial_views import verified_refund_total
                    refunded=verified_refund_total(db,dict(tenant_id=t,merchant_id=m,store_id=s),ref)
                    if refunded>amount:raise ValueError('REFUND_TOTAL_EXCEEDS_PAYMENT')
                    verified_refunds+=refunded
                elif status in ('SUCCESS','REFUNDED'):unverified_terminal+=1
            result=dict(admitted_store_count=len(identities),order_counts=order_counts,signed_paid_order_count=verified_count,signed_gross_payment_minor=verified_minor,signed_refund_minor=verified_refunds,signed_net_payment_minor=verified_minor-verified_refunds,unverified_paid_state_count=unverified_terminal,currency='CNY',amount_basis='GROSS_ORIGINAL_PAYMENTS_BEFORE_REFUNDS',finance_status='UNCONFIRMED',coverage='ORIGINAL_PROJECT_ADMITTED_STORES')
        if op in ('platform_overview','platform_orders'):
            result.update(coverage_complete=not unavailable,unavailable_mapping_count=len(unavailable),
                unavailable_mappings=unavailable[:50],unavailable_mappings_truncated=len(unavailable)>50,
                totals_scope='ACCESSIBLE_STORE_SUBTOTAL' if unavailable else 'ALL_CURRENT_ADMITTED_STORES')
        with c.tx():c.audit(g['project'],g['user_id'],op.upper(),'SCOPED_READ')
        return result
