"""Community order attribution and verified payout observations, no new ledger."""
from scripts.community_admin_route_gate import community_project, resolve_admin_workspace, admin_workspace_catalog
import hashlib
import json
import re
from scripts.pr122_customer_core import canonical
from scripts.community_order_store import state
from scripts.community_order_provider_projection import provider_evidence
from scripts.community_merchant_contract import scope as validate_scope, valid_id
from scripts.community_provider_reference import provider_order_reference


def earnings_conflict():
    # Do not include private persisted payloads in public error messages.
    raise ValueError('COMMUNITY_EARNINGS_INTEGRITY_CONFLICT')


def positive_minor(value):
    if type(value) is not int or value <= 0:earnings_conflict()
    return value


def receiver_communities(center,scope,project,receiver_ids):
    result={}
    for rid in receiver_ids:
        key=hashlib.sha256(canonical([scope,rid])).hexdigest()
        row=center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_RECEIVER_BINDING' AND subject_idx=? AND project=? AND active=1",(key,project)).fetchone()
        if row:
            result[rid]=json.loads(center.decrypt(row[0],'community-receiver:'+key))
    return result


def refund_observations(db,identity,reference,original):
    """Narrow read of existing verified refund projections; never provider I/O."""
    def invalid():raise ValueError('COMMUNITY_REFUND_OBSERVATION_INTEGRITY_CONFLICT')
    try:validate_scope(identity)
    except ValueError:invalid()
    if not valid_id(reference) or original.get('currency')!='CNY' or type(original.get('amount_minor')) is not int or not 0<original['amount_minor']<=9007199254740991:invalid()
    t,m,s=(identity[k] for k in ('tenant_id','merchant_id','store_id'))
    records=[];total=0;seen=set()
    rows=db.execute('SELECT event_id,from_state,to_state,evidence_source FROM order_events WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=? ORDER BY rowid',(t,m,s,reference))
    for event_id,before,after,raw in rows:
        try:value=json.loads(raw)
        except (ValueError,TypeError):invalid()
        if type(value) is not dict:invalid()
        if value.get('source')!='WECHAT_SIGNED_REFUND_RESULT':continue
        number=value.get('out_refund_no');amount=value.get('refund_minor');at=value.get('observed_at');digest=value.get('body_sha256')
        if (not valid_id(number) or number in seen or type(amount) is not int or not 0<amount<=9007199254740991
                or type(at) is not int or not 0<=at<=9007199254740991
                or type(digest) is not str or not re.fullmatch('[0-9a-f]{64}',digest)
                or original['state'] not in ('SUCCESS','REFUNDED') or before not in ('SUCCESS','REFUNDED') or after not in ('SUCCESS','REFUNDED')
                or type(original.get('provider_transaction_id')) is not str or not original['provider_transaction_id']
                or value.get('transaction_id')!=original['provider_transaction_id']):invalid()
        expected='wr_'+hashlib.sha256(canonical([identity,reference,number])).hexdigest()[:48]
        if event_id!=expected:invalid()
        seen.add(number);total+=amount
        if total>original['amount_minor']:invalid()
        records.append(dict(reference=reference,out_refund_no=number,refund_minor=amount,currency=original['currency'],observed_at=at,
            evidence_source='WECHAT_SIGNED_REFUND_RESULT',observation_status='RECORDED_SIGNED_SUCCESS',finance_status='UNCONFIRMED'))
    if records and provider_evidence(db,identity,reference) is None:invalid()
    return records


class CommunityReports:
    def __init__(self,communities,commerce,actions):
        if communities.center is not commerce.center or actions is not None and actions.center is not communities.center:raise ValueError('SAME_ORIGINAL_COMMUNITY_SERVICES_REQUIRED')
        self.communities,self.commerce,self.actions,self.center=communities,commerce,actions,communities.center

    def _earnings(self,g,community,key,value,snapshot):
        """Read only original, consistently bound split/return observations."""
        c=self.center;identity=value['scope'];mchid=self.actions.reader._mchid
        try:validate_scope(identity)
        except ValueError:earnings_conflict()
        if (value.get('project')!=g['project'] or not valid_id(value.get('reference'))
                or not valid_id(value.get('request_id'))
                or value.get('scope_hash')!=hashlib.sha256(canonical(identity)).hexdigest()
                or type(snapshot) is not dict or snapshot.get('reference')!=value['reference']
                or snapshot.get('currency')!='CNY' or not valid_id(snapshot.get('rule_id'))
                or type(snapshot.get('version')) is not int or snapshot['version']<=0
                or type(value.get('policy_hash')) is not str
                or snapshot.get('policy_hash')!=value['policy_hash']):earnings_conflict()
        provider_ref='ps'+hashlib.sha256(canonical([mchid,identity,value['reference'],value['request_id'],'SPLIT'])).hexdigest()[:30]
        if (value.get('provider_reference')!=provider_ref
                or key!=hashlib.sha256(canonical([mchid,'SPLIT',provider_ref])).hexdigest()):earnings_conflict()
        allocations=snapshot.get('allocations');mappings=snapshot.get('receiver_communities')
        if type(allocations) is not dict or not allocations or type(mappings) is not dict:earnings_conflict()
        if any(not valid_id(rid) for rid in allocations):earnings_conflict()
        if sum(positive_minor(amount) for amount in allocations.values())>positive_minor(snapshot.get('amount_minor')):earnings_conflict()
        payload=value.get('payload')
        if type(payload) is not dict or type(payload.get('receivers')) is not list or len(payload['receivers'])!=len(allocations):earnings_conflict()
        # ProviderActions writes its request receivers in sorted receiver-id order.
        original_receivers={}
        for rid,receiver in zip(sorted(allocations),payload['receivers']):
            if (type(receiver) is not dict or positive_minor(receiver.get('amount'))!=allocations[rid]
                    or receiver.get('type') not in ('MERCHANT_ID','PERSONAL_OPENID','PERSONAL_SUB_OPENID')
                    or type(receiver.get('account')) is not str or not receiver['account']):earnings_conflict()
            original_receivers[rid]=receiver
        if payload.get('out_order_no')!=provider_ref or type(payload.get('sub_mchid')) is not str:earnings_conflict()
        observation=value.get('result')
        if observation is None:return []
        if (type(observation) is not dict or observation.get('status') not in ('PROCESSING','FINISHED')
                or type(observation.get('receivers')) is not list):earnings_conflict()
        observed={}
        for receiver in observation['receivers']:
            if type(receiver) is not dict or not valid_id(receiver.get('receiver_id')):earnings_conflict()
            rid=receiver['receiver_id']
            if (rid in observed or rid not in allocations or positive_minor(receiver.get('amount_minor'))!=allocations[rid]
                    or receiver.get('result') not in ('SUCCESS','CLOSED','PENDING')
                    or observation['status']=='FINISHED' and receiver['result']=='PENDING'):earnings_conflict()
            observed[rid]=receiver
        if observed and set(observed)!=set(allocations) or observation['status']=='FINISHED' and set(observed)!=set(allocations):earnings_conflict()
        lock=c.idx('provider-order-action:'+mchid+':'+provider_order_reference(mchid,identity,value['reference']))
        row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PROVIDER_ORDER_BUDGET' AND subject_idx=? AND project=? AND active=1",(lock,g['project'])).fetchone()
        if row is None:earnings_conflict()
        budget=json.loads(c.decrypt(row[0],'provider-order-budget'))
        if type(budget) is not dict or budget.get('split_action')!=key:earnings_conflict()
        return_keys=budget.get('return_actions',[])
        if (type(return_keys) is not list or len(return_keys)>50
                or any(type(k) is not str or not re.fullmatch('[0-9a-f]{64}',k) for k in return_keys)
                or len(set(return_keys))!=len(return_keys)):earnings_conflict()
        returned={rid:0 for rid in allocations}
        for return_key in return_keys:
            row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PROVIDER_RETURN' AND subject_idx=? AND project=? AND active=1",(return_key,g['project'])).fetchone()
            if row is None:earnings_conflict()
            back=json.loads(c.decrypt(row[0],'community-provider-return:'+return_key))
            if (type(back) is not dict or back.get('scope')!=identity or back.get('project')!=g['project']
                    or back.get('reference')!=value['reference'] or not valid_id(back.get('request_id'))
                    or not valid_id(back.get('receiver_id')) or back['receiver_id'] not in observed):earnings_conflict()
            rid=back['receiver_id'];request=back.get('payload');original=original_receivers[rid]
            return_ref='sr'+hashlib.sha256(canonical([mchid,identity,value['reference'],back['request_id']])).hexdigest()[:30]
            if (return_key!=hashlib.sha256(canonical([mchid,'RETURN',return_ref])).hexdigest()
                    or type(request) is not dict or request.get('out_return_no')!=return_ref
                    or request.get('out_order_no')!=provider_ref or request.get('sub_mchid')!=payload['sub_mchid']
                    or original['type']!='MERCHANT_ID' or request.get('return_mchid')!=original['account']
                    or 'result' in back and back['result'] not in ('PROCESSING','SUCCESS','FAILED')):earnings_conflict()
            amount=positive_minor(request.get('amount'))
            if amount>allocations[rid]:earnings_conflict()
            if back.get('result')=='SUCCESS':returned[rid]+=amount
        records=[]
        for rid,receiver in observed.items():
            amount=receiver['amount_minor'] if receiver['result']=='SUCCESS' and observation['status']=='FINISHED' else 0
            if returned[rid]>amount:raise ValueError('COMMUNITY_RETURN_EXCEEDS_CONFIRMED_SPLIT')
            mapping=mappings.get(rid)
            if mapping is None:continue
            if type(mapping) is not dict:earnings_conflict()
            if mapping.get('community_id')!=community['id']:continue
            if mapping.get('scope')!=identity or mapping.get('receiver_id')!=rid:earnings_conflict()
            records.append(dict(reference=value['reference'],request_id=value['request_id'],receiver_id=rid,
                rule_id=snapshot['rule_id'],rule_version=snapshot['version'],received_minor=amount,
                returned_minor=returned[rid],net_minor=amount-returned[rid],provider_state=observation['status'],
                receiver_state=receiver['result'],finance_status='UNCONFIRMED'))
        return records

    def _receiver_projection(self,value,key,g,community,finance,policy,requested_workspace):
        # Never infer a historical workspace from matching scope or a current grant.
        if type(value) is not dict:raise ValueError('RECEIVER_BINDING_INTEGRITY_CONFLICT')
        if value.get('scope')!=finance['scope'] or value.get('community_id')!=community['id']:return None
        rid=value.get('receiver_id')
        if type(rid) is not str or rid not in policy['receivers']:return None
        expected=hashlib.sha256(canonical([finance['scope'],rid])).hexdigest()
        if key!=expected or type(value.get('version')) is not int or value['version']<1 or type(value.get('at')) is not int:
            raise ValueError('RECEIVER_BINDING_INTEGRITY_CONFLICT')
        stored=value.get('provider_workspace')
        if stored is not None and (type(stored) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}',stored)):
            raise ValueError('RECEIVER_BINDING_INTEGRITY_CONFLICT')
        return dict(community_id=community['id'],receiver_id=rid,scope=dict(finance['scope']),version=value['version'],at=value['at'],
            provider_workspace=stored,provider_workspace_status='RECORDED' if stored is not None else 'LEGACY_NOT_RECORDED',
            requested_provider_workspace=requested_workspace,applies_to='NEW_RULE_VERSIONS_ONLY',funds_operation_executed=False)

    def _read_receivers(self,session,csrf,g,community,op,p):
        if g['role']!='PLATFORM_OWNER' or self.actions is None:raise PermissionError('PLATFORM_RECEIVER_READ_AUTHORITY_REQUIRED')
        c=self.center;community_project(c,g['user_id'],g['project'],('OWNER',))
        finance,policy=self.actions._authorize(session,csrf,p['provider_workspace'])
        if finance['project']!=g['project'] or finance['tenant']!=g['tenant']:raise PermissionError('SAME_PROJECT_ADMITTED_RECEIVER_REQUIRED')
        if op=='community_receiver_read':
            rid=p['receiver_id']
            if type(rid) is not str or rid not in policy['receivers']:raise PermissionError('SAME_PROJECT_ADMITTED_RECEIVER_REQUIRED')
            key=hashlib.sha256(canonical([finance['scope'],rid])).hexdigest()
            rows=c.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_RECEIVER_BINDING' AND project=? AND subject_idx=? AND active=1",(g['project'],key)).fetchall()
        else:
            after=p['after_id']
            if type(after) is not str or after and not re.fullmatch('[0-9a-f]{64}',after):raise ValueError('INVALID_RECEIVER_BINDING_CURSOR')
            rows=c.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_RECEIVER_BINDING' AND project=? AND active=1 AND subject_idx>? ORDER BY subject_idx LIMIT 51",(g['project'],after)).fetchall()
        records=[]
        for key,raw in rows[:50]:
            value=json.loads(c.decrypt(raw,'community-receiver:'+key))
            projected=self._receiver_projection(value,key,g,community,finance,policy,p['provider_workspace'])
            if projected is not None:records.append(projected)
        if op=='community_receiver_read':
            if len(records)!=1:raise ValueError('RECEIVER_BINDING_NOT_FOUND')
            return records[0]
        return dict(records=records,has_more=len(rows)>50,next_cursor=rows[49][0] if len(rows)>50 else None,
            totals_scope='CURRENT_PAGE_ONLY',funds_operation_executed=False)

    def dispatch(self,session,csrf,body):
        fields={'community_orders':{'community_id','after_id'},'community_refunds':{'community_id','after_id'},'community_earnings':{'community_id','after_id'},
            'community_receiver_bind':{'community_id','provider_workspace','receiver_id','expected_version'},
            'community_receiver_list':{'community_id','provider_workspace','after_id'},
            'community_receiver_read':{'community_id','provider_workspace','receiver_id'}}
        op,p=body['operation'],body['params']
        if type(op) is not str or op not in fields or type(p) is not dict or set(p)!=fields[op]:raise ValueError('INVALID_COMMUNITY_REPORT_FIELDS')
        g=self.communities.authorize(session,csrf,body['workspace']);c=self.center
        community=self.communities.read(g,p['community_id'])
        platform=g['role'] in ('PLATFORM_OWNER','PLATFORM_REVIEWER')
        if not platform and not (g['role']=='COMMUNITY_ADMIN' and community['owner']==g['user_id']):raise PermissionError('COMMUNITY_REPORT_OWNER_REQUIRED')
        with c.tx():c.limit('community-report:'+g['user_id'],60,60)
        if op in ('community_receiver_list','community_receiver_read'):
            return self._read_receivers(session,csrf,g,community,op,p)
        if op=='community_receiver_bind':
            if g['role']!='PLATFORM_OWNER' or self.actions is None or community['state']!='APPROVED':raise PermissionError('APPROVED_COMMUNITY_AND_PLATFORM_AUTHORITY_REQUIRED')
            community_project(c,g['user_id'],g['project'],('OWNER',))
            finance,policy=self.actions._authorize(session,csrf,p['provider_workspace'])
            if finance['project']!=g['project'] or finance['tenant']!=g['tenant'] or p['receiver_id'] not in policy['receivers']:raise PermissionError('SAME_PROJECT_ADMITTED_RECEIVER_REQUIRED')
            scope=finance['scope'];key=hashlib.sha256(canonical([scope,p['receiver_id']])).hexdigest()
            with c.tx():
                prior=receiver_communities(c,scope,g['project'],[p['receiver_id']]).get(p['receiver_id'])
                revision=prior['version'] if prior else 0
                if type(p['expected_version']) is not int or p['expected_version']!=revision:raise ValueError('RECEIVER_BINDING_VERSION_CONFLICT')
                result=dict(community_id=community['id'],receiver_id=p['receiver_id'],provider_workspace=p['provider_workspace'],scope=scope,version=revision+1,approved_by=g['user_id'],at=c.now())
                payload=c.encrypt(canonical(result),'community-receiver:'+key)
                c.db.execute("INSERT INTO links VALUES('COMMUNITY_RECEIVER_BINDING',?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload",(key,g['user_id'],g['project'],payload))
                history=hashlib.sha256(canonical(result)).hexdigest()
                c.db.execute("INSERT INTO links VALUES('COMMUNITY_RECEIVER_BINDING_HISTORY',?,?,?,?,1)",(history,g['user_id'],g['project'],c.encrypt(canonical(result),'community-receiver-history:'+history)))
                c.audit(g['project'],g['user_id'],'COMMUNITY_RECEIVER_RELATION_APPROVED',history)
            return dict(result,applies_to='NEW_RULE_VERSIONS_ONLY',funds_operation_executed=False)
        after=p['after_id']
        if type(after) is not str or after and not re.fullmatch('[0-9a-f]{64}',after):raise ValueError('INVALID_COMMUNITY_REPORT_CURSOR')
        channel='COMMUNITY_COMMERCE_V1' if op in ('community_orders','community_refunds') else 'COMMUNITY_PROVIDER_ACTION'
        rows=c.db.execute('SELECT subject_idx,payload FROM links WHERE channel=? AND project=? AND active=1 AND subject_idx>? ORDER BY subject_idx LIMIT 51',(channel,g['project'],after)).fetchall()
        records=[];gross=returned=0
        for key,payload in rows[:50]:
            value=json.loads(c.decrypt(payload,('community-commerce:' if op in ('community_orders','community_refunds') else 'provider-action:')+key))
            if type(value) is not dict:
                if op=='community_earnings':earnings_conflict()
                raise ValueError('COMMUNITY_ORDER_INTEGRITY_CONFLICT')
            identity=value.get('scope')
            if op=='community_earnings':
                if value.get('kind') not in ('SPLIT','REFUND'):earnings_conflict()
                try:validate_scope(identity)
                except ValueError:earnings_conflict()
            if type(identity) is not dict or identity.get('tenant_id')!=g['tenant']:continue
            if op in ('community_orders','community_refunds'):
                if value.get('community_id')!=community['id'] or type(value.get('lines')) is not list:continue
                try:original=state(self.commerce.runtime.demo.db,identity,value['reference'])
                except ValueError:continue
                verified=provider_evidence(self.commerce.runtime.demo.db,identity,value['reference']) is not None
                records.append(dict(reference=value['reference'],merchant_id=identity['merchant_id'],store_id=identity['store_id'],amount_minor=original['amount_minor'],currency='CNY',order_state=original['state'],provider_payment_verified=verified and original['state'] in ('SUCCESS','REFUNDED')))
                if op=='community_refunds':
                    observations=refund_observations(self.commerce.runtime.demo.db,identity,value['reference'],original)
                    records[-1].update(refund_observations=observations,refund_observation_status='RECORDED_SIGNED_REFUND_OBSERVATIONS' if observations else 'NO_RECORDED_VERIFIED_REFUND',finance_status='UNCONFIRMED',funds_operation_executed=False)
                if verified and original['state'] in ('SUCCESS','REFUNDED'):
                    gross+=original['amount_minor']
                    # The community and finance views must reject the same
                    # invalid signed-refund history; bool/float/negative values
                    # must never become apparently valid money totals here.
                    from scripts.community_financial_views import verified_refund_total
                    refunded=verified_refund_total(self.commerce.runtime.demo.db,identity,value['reference'])
                    if not 0<=refunded<=original['amount_minor']:raise ValueError('COMMUNITY_ORDER_REFUND_TOTAL_CONFLICT')
                    returned+=refunded
            else:
                if value.get('kind')!='SPLIT':continue
                if self.actions is None:raise PermissionError('COMMUNITY_EARNINGS_PROVIDER_UNAVAILABLE')
                snapshot_key=hashlib.sha256(canonical([identity,'ORDER',value['reference']])).hexdigest()
                snapshot_row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_SPLIT_RULES_V1' AND subject_idx=? AND project=? AND active=1",(snapshot_key,g['project'])).fetchone()
                # A provider split requires its original frozen attribution.
                # Missing evidence cannot become an apparently valid zero.
                if snapshot_row is None:earnings_conflict()
                snapshot=json.loads(c.decrypt(snapshot_row[0],'community-split-rule:'+snapshot_key))
                for record in self._earnings(g,community,key,value,snapshot):
                    records.append(record);gross+=record['received_minor'];returned+=record['returned_minor']
        with c.tx():c.audit(g['project'],g['user_id'],'COMMUNITY_'+op.upper(),community['id'])
        return dict(records=records,has_more=len(rows)>50,next_cursor=rows[49][0] if len(rows)>50 else None,
            page_gross_minor=gross,page_returns_minor=returned,page_net_minor=gross-returned,currency='CNY',totals_scope='CURRENT_PAGE_ONLY',finance_status='UNCONFIRMED')
