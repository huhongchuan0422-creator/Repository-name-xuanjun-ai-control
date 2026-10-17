"""Community order attribution and verified payout observations, no new ledger."""
import hashlib
import json
import re
from scripts.pr122_customer_core import canonical
from scripts.community_order_store import state
from scripts.community_order_provider_projection import provider_evidence


def receiver_communities(center,scope,project,receiver_ids):
    result={}
    for rid in receiver_ids:
        key=hashlib.sha256(canonical([scope,rid])).hexdigest()
        row=center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_RECEIVER_BINDING' AND subject_idx=? AND project=? AND active=1",(key,project)).fetchone()
        if row:
            result[rid]=json.loads(center.decrypt(row[0],'community-receiver:'+key))
    return result


class CommunityReports:
    def __init__(self,communities,commerce,actions):
        if communities.center is not commerce.center or actions is not None and actions.center is not communities.center:raise ValueError('SAME_ORIGINAL_COMMUNITY_SERVICES_REQUIRED')
        self.communities,self.commerce,self.actions,self.center=communities,commerce,actions,communities.center
    def dispatch(self,session,csrf,body):
        fields={'community_orders':{'community_id','after_id'},'community_earnings':{'community_id','after_id'},
            'community_receiver_bind':{'community_id','provider_workspace','receiver_id','expected_version'}}
        op,p=body['operation'],body['params']
        if type(op) is not str or op not in fields or type(p) is not dict or set(p)!=fields[op]:raise ValueError('INVALID_COMMUNITY_REPORT_FIELDS')
        g=self.communities.authorize(session,csrf,body['workspace']);c=self.center
        community=self.communities.read(g,p['community_id'])
        platform=g['role'] in ('PLATFORM_OWNER','PLATFORM_REVIEWER')
        if not platform and not (g['role']=='COMMUNITY_ADMIN' and community['owner']==g['user_id']):raise PermissionError('COMMUNITY_REPORT_OWNER_REQUIRED')
        with c.tx():c.limit('community-report:'+g['user_id'],60,60)
        if op=='community_receiver_bind':
            if g['role']!='PLATFORM_OWNER' or self.actions is None or community['state']!='APPROVED':raise PermissionError('APPROVED_COMMUNITY_AND_PLATFORM_AUTHORITY_REQUIRED')
            c.project(g['user_id'],g['project'],('OWNER',))
            finance,policy=self.actions._authorize(session,csrf,p['provider_workspace'])
            if finance['project']!=g['project'] or finance['tenant']!=g['tenant'] or p['receiver_id'] not in policy['receivers']:raise PermissionError('SAME_PROJECT_ADMITTED_RECEIVER_REQUIRED')
            scope=finance['scope'];key=hashlib.sha256(canonical([scope,p['receiver_id']])).hexdigest()
            with c.tx():
                prior=receiver_communities(c,scope,g['project'],[p['receiver_id']]).get(p['receiver_id'])
                revision=prior['version'] if prior else 0
                if type(p['expected_version']) is not int or p['expected_version']!=revision:raise ValueError('RECEIVER_BINDING_VERSION_CONFLICT')
                result=dict(community_id=community['id'],receiver_id=p['receiver_id'],scope=scope,version=revision+1,approved_by=g['user_id'],at=c.now())
                payload=c.encrypt(canonical(result),'community-receiver:'+key)
                c.db.execute("INSERT INTO links VALUES('COMMUNITY_RECEIVER_BINDING',?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload",(key,g['user_id'],g['project'],payload))
                history=hashlib.sha256(canonical(result)).hexdigest()
                c.db.execute("INSERT INTO links VALUES('COMMUNITY_RECEIVER_BINDING_HISTORY',?,?,?,?,1)",(history,g['user_id'],g['project'],c.encrypt(canonical(result),'community-receiver-history:'+history)))
                c.audit(g['project'],g['user_id'],'COMMUNITY_RECEIVER_RELATION_APPROVED',history)
            return dict(result,applies_to='NEW_RULE_VERSIONS_ONLY',funds_operation_executed=False)
        after=p['after_id']
        if type(after) is not str or after and not re.fullmatch('[0-9a-f]{64}',after):raise ValueError('INVALID_COMMUNITY_REPORT_CURSOR')
        channel='COMMUNITY_COMMERCE_V1' if op=='community_orders' else 'COMMUNITY_PROVIDER_ACTION'
        rows=c.db.execute('SELECT subject_idx,payload FROM links WHERE channel=? AND project=? AND active=1 AND subject_idx>? ORDER BY subject_idx LIMIT 51',(channel,g['project'],after)).fetchall()
        records=[];gross=returned=0
        for key,payload in rows[:50]:
            value=json.loads(c.decrypt(payload,('community-commerce:' if op=='community_orders' else 'provider-action:')+key))
            identity=value.get('scope')
            if type(identity) is not dict or identity.get('tenant_id')!=g['tenant']:continue
            if op=='community_orders':
                if value.get('community_id')!=community['id'] or type(value.get('lines')) is not list:continue
                try:original=state(self.commerce.runtime.demo.db,identity,value['reference'])
                except ValueError:continue
                verified=provider_evidence(self.commerce.runtime.demo.db,identity,value['reference']) is not None
                records.append(dict(reference=value['reference'],merchant_id=identity['merchant_id'],store_id=identity['store_id'],amount_minor=original['amount_minor'],currency='CNY',order_state=original['state'],provider_payment_verified=verified and original['state'] in ('SUCCESS','REFUNDED')))
                if verified and original['state'] in ('SUCCESS','REFUNDED'):
                    gross+=original['amount_minor']
                    from scripts.community_merchant_contract import scope
                    refunded=0
                    for raw, in self.commerce.runtime.demo.db.execute('SELECT evidence_source FROM order_events WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?',(*scope(identity),value['reference'])):
                        try:refund_event=json.loads(raw)
                        except (ValueError,TypeError):continue
                        if type(refund_event) is dict and refund_event.get('source')=='WECHAT_SIGNED_REFUND_RESULT':refunded+=refund_event['refund_minor']
                    if not 0<=refunded<=original['amount_minor']:raise ValueError('COMMUNITY_ORDER_REFUND_TOTAL_CONFLICT')
                    returned+=refunded
            else:
                if value.get('kind')!='SPLIT' or self.actions is None:continue
                snapshot_key=hashlib.sha256(canonical([identity,'ORDER',value['reference']])).hexdigest()
                snapshot_row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_SPLIT_RULES_V1' AND subject_idx=? AND project=? AND active=1",(snapshot_key,g['project'])).fetchone()
                if snapshot_row is None:continue
                snapshot=json.loads(c.decrypt(snapshot_row[0],'community-split-rule:'+snapshot_key))
                mappings=snapshot.get('receiver_communities',{})
                for result in value.get('result',{}).get('receivers',[]):
                    mapping=mappings.get(result['receiver_id'])
                    if mapping is None or mapping['community_id']!=community['id']:continue
                    amount=result['amount_minor'] if result['result']=='SUCCESS' and value['result']['status']=='FINISHED' else 0
                    refunded=0
                    # Return references live in the original order budget, whose
                    # key derives from the original payment reference.
                    from scripts.community_provider_reference import provider_order_reference
                    lock=c.idx('provider-order-action:'+self.actions.reader._mchid+':'+provider_order_reference(self.actions.reader._mchid,identity,value['reference']))
                    budget_row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PROVIDER_ORDER_BUDGET' AND subject_idx=? AND project=? AND active=1",(lock,g['project'])).fetchone()
                    if budget_row:
                        budget=json.loads(c.decrypt(budget_row[0],'provider-order-budget'))
                        from scripts.community_split_returns import SplitReturns
                        for return_key in budget.get('return_actions',[]):
                            back=SplitReturns(self.actions)._read(return_key)
                            if back and back['receiver_id']==result['receiver_id'] and back.get('result')=='SUCCESS':refunded+=back['payload']['amount']
                    if refunded>amount:raise ValueError('COMMUNITY_RETURN_EXCEEDS_CONFIRMED_SPLIT')
                    records.append(dict(reference=value['reference'],request_id=value['request_id'],receiver_id=result['receiver_id'],rule_id=snapshot['rule_id'],rule_version=snapshot['version'],received_minor=amount,returned_minor=refunded,net_minor=amount-refunded,provider_state=value['result']['status'],receiver_state=result['result'],finance_status='UNCONFIRMED'))
                    gross+=amount;returned+=refunded
        with c.tx():c.audit(g['project'],g['user_id'],'COMMUNITY_'+op.upper(),community['id'])
        return dict(records=records,has_more=len(rows)>50,next_cursor=rows[49][0] if len(rows)>50 else None,
            page_gross_minor=gross,page_returns_minor=returned,page_net_minor=gross-returned,currency='CNY',totals_scope='CURRENT_PAGE_ONLY',finance_status='UNCONFIRMED')
