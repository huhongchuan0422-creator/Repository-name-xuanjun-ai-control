"""Consume admitted Finance confirmation and fulfill original SaaS entitlements.

The Finance authority is an injected hosting dependency, never a body boolean,
manual review or test HMAC. This module owns no Finance ledger or payment API.
Original Center links/events coordinate original order and module databases.
"""
from abc import ABC,abstractmethod
from dataclasses import dataclass
import hashlib
import json
from scripts.pr122_customer_core import canonical
from scripts.community_center_operations import CenterOperations
from scripts.community_merchant_contract import valid_id
from scripts.community_saas_offline_handoff import plan_finance_claim
from scripts.community_saas_order_preparation import read,status,advance
from scripts.community_saas_modules import grant


@dataclass(frozen=True)
class FinanceConfirmation:
    proof_id:str
    claim_sha256:str
    verified_at:int


class FinanceAuthority(ABC):
    """Adapter implemented by the admitted existing Finance service owner."""
    def configuration_token(self):
        """Optional immutable local configuration stamp, never a Finance proof.

        Opaque admitted adapters retain instance identity checking. Their remote
        issuer validity remains the responsibility of verify, as before.
        """
        return None
    @abstractmethod
    def verify(self,claim,proof,now):
        """Independently confirm the exact original claim or raise; no side effect."""


class FulfillmentPending(RuntimeError):pass


class SaasFulfillment:
    def __init__(self,operations,finance,authority_id,price_bindings,*,reversal_finance=None):
        if type(operations) is not CenterOperations or not isinstance(finance,FinanceAuthority) or not valid_id(authority_id) or type(price_bindings) is not dict or not price_bindings:
            raise ValueError('ORIGINAL_OPERATIONS_AND_ADMITTED_FINANCE_REQUIRED')
        self.operations,self.center,self.runtime=operations,operations.center,operations.runtime
        if reversal_finance is not None and not isinstance(reversal_finance,FinanceAuthority):raise ValueError('ADMITTED_REVERSAL_AUTHORITY_REQUIRED')
        self.reversal_finance=reversal_finance
        self.finance,self.authority_id=finance,authority_id;self.prices={}
        for key,value in price_bindings.items():
            if (type(key) is not tuple or len(key)!=3 or any(not valid_id(v) for v in key[:2])
                    or type(key[2]) is not int or key[2]<1):raise ValueError('EXPLICIT_LEGACY_PRICE_BINDING_REQUIRED')
            policy={'price_version':value,'perpetual':False} if type(value) is int else value
            if type(policy) is not dict or set(policy)!={'price_version','perpetual'} or type(policy['price_version']) is not int or policy['price_version']<1 or type(policy['perpetual']) is not bool:
                raise ValueError('EXPLICIT_LICENSE_POLICY_REQUIRED')
            self.prices[key]=dict(policy)
    def _operator(self,session,csrf,workspace):
        if type(csrf) is not str or not csrf:raise PermissionError('CENTER_CSRF_REQUIRED')
        c=self.center;uid=c.session(session,csrf);g=self.operations.grants.get(workspace)
        if g is None or g['user_id']!=uid or g['role']!='PLATFORM_OWNER':raise PermissionError('REGISTERED_FINANCE_OPERATOR_REQUIRED')
        p=g['principal']
        if p.role!=g['role'] or p.tenant_id!=g['tenant'] or self.runtime.bindings.get(p)!=g['scope']:
            raise PermissionError('OPERATOR_GRANT_CHANGED')
        project,_,_=c.project(uid,g['project'],('OWNER',))
        if project['tenant']!=g['tenant']:raise PermissionError('PROJECT_TENANT_MISMATCH')
        return g
    def _context(self,session,csrf,workspace):
        """Freeze this request's original authorization; do not persist process IDs."""
        g=self._operator(session,csrf,workspace)
        project,role,_=self.center.project(g['user_id'],g['project'],('OWNER',))
        principal=g['principal']
        grant={k:json.loads(canonical(v)) for k,v in g.items() if k!='principal'}
        frozen=canonical(dict(grant=grant,principal=[principal.tenant_id,principal.role],
            project={k:project[k] for k in ('id','tenant','customer','owner','authority_ref','revision','expires','active')},
            project_payload_sha256=hashlib.sha256(project['payload']).hexdigest(),project_role=role,
            authority_id=self.authority_id,prices=[[list(k),v] for k,v in sorted(self.prices.items())]))
        refs=(self.operations,self.center,self.runtime,self.runtime.saas,self.runtime.saas.orders,
              self.runtime.saas.modules,principal,self.finance,self.reversal_finance)
        tokens=[]
        for authority in (self.finance,self.reversal_finance):
            token=None if authority is None else authority.configuration_token()
            if token is not None and type(token) is not str:raise PermissionError('INVALID_FINANCE_CONFIGURATION_TOKEN')
            tokens.append(token)
        return dict(grant,principal=principal),(refs,frozen,tuple(tokens))
    def _guard(self,context,session,csrf,workspace):
        _,current=self._context(session,csrf,workspace)
        if (any(before is not after for before,after in zip(context[0],current[0]))
                or context[1:]!=current[1:]):
            raise PermissionError('FULFILLMENT_AUTHORITY_CONTEXT_CHANGED')
    def _load(self,key):
        row=self.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_SAAS_FULFILLMENT' AND subject_idx=? AND active=1",(key,)).fetchone()
        return None if row is None else json.loads(self.center.decrypt(row[0],'saas-fulfillment:'+key))
    def _save(self,key,data):
        self.center.db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_SAAS_FULFILLMENT' AND subject_idx=? AND active=1",(self.center.encrypt(canonical(data),'saas-fulfillment:'+key),key))
    def fulfill(self,session,csrf,workspace,order_id,proof):
        g,context=self._context(session,csrf,workspace);c=self.center;db=self.runtime.saas.orders;modules=self.runtime.saas.modules
        guard=lambda:self._guard(context,session,csrf,workspace)
        if not valid_id(order_id):raise ValueError('INVALID_ORDER_ID')
        if db.in_transaction or modules.in_transaction:raise ValueError('EXTERNAL_TRANSACTION_DENIED')
        tenant=g['tenant'];now=c.now();claim=plan_finance_claim(db,order_id,tenant)
        digest=hashlib.sha256(canonical(claim)).hexdigest()
        guard()
        confirmation=self.finance.verify(json.loads(canonical(claim)),proof,now)
        if (type(confirmation) is not FinanceConfirmation or not valid_id(confirmation.proof_id)
                or confirmation.claim_sha256!=digest or type(confirmation.verified_at) is not int
                or not read(db,order_id,tenant)['created_at']<=confirmation.verified_at<=now):
            raise PermissionError('AUTHORITATIVE_FINANCE_CONFIRMATION_REQUIRED')
        guard()
        if plan_finance_claim(db,order_id,tenant)!=claim:raise PermissionError('FINANCE_CLAIM_CHANGED')
        order=read(db,order_id,tenant);quote=order['quote_snapshot'];module=order['module_id']
        policy=self.prices.get((module,order['offer_id'],order['offer_version']))
        if policy is None:raise PermissionError('LEGACY_PRICE_MAPPING_REQUIRED')
        price=policy['price_version'];perpetual=policy['perpetual'];term=quote.get('term_days')
        if perpetual:
            if quote['kind'] not in ('BUYOUT','FREE') or term is not None:raise PermissionError('PERPETUAL_LICENSE_POLICY_MISMATCH')
        elif type(term) is not int or not 1<=term<=36500:raise PermissionError('APPROVED_LICENSE_TERM_REQUIRED')
        if modules.execute('SELECT 1 FROM module_prices WHERE module_id=? AND version=?',(module,price)).fetchone() is None:raise ValueError('ORIGINAL_MODULE_PRICE_REQUIRED')
        key=hashlib.sha256(canonical([tenant,order_id])).hexdigest()
        proof_key=c.idx('saas-finance-proof:'+self.authority_id+':'+confirmation.proof_id)
        lock=c.idx('saas-module-fulfillment:'+tenant+':'+module)
        binding=dict(tenant=tenant,order_id=order_id,module=module,quote_sha256=claim['quote_sha256'],claim_sha256=digest,proof_id=confirmation.proof_id,authority_id=self.authority_id,price_version=price,perpetual=perpetual)
        with c.tx():
            guard();old=self._load(key);guard()
            if old is not None:
                if old['binding']!=binding:raise PermissionError('FULFILLMENT_CONFIRMATION_COLLISION')
                if old['state'] in ('REVERSAL_RESERVED','REVERSED'):raise PermissionError('REVERSED_ORDER_CANNOT_BE_GRANTED_AGAIN')
                if old['state']=='COMPLETED':
                    guard();return dict(order_id=order_id,state='COMPLETED',entitlement_granted=True,duplicate=True,valid_until=old['until'])
            else:
                if c.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_SAAS_MODULE_LOCK' AND subject_idx=? AND active=1",(lock,)).fetchone():raise FulfillmentPending('PRIOR_MODULE_FULFILLMENT_PENDING')
                if c.db.execute("SELECT 1 FROM events WHERE channel='COMMUNITY_SAAS_FINANCE_PROOF' AND event_id=?",(proof_key,)).fetchone():raise PermissionError('FINANCE_PROOF_ALREADY_CONSUMED')
                before=modules.execute('SELECT valid_from,valid_until,price_version,source FROM module_entitlements WHERE tenant_id=? AND module_id=?',(tenant,module)).fetchone()
                start=max(now,before[1]) if before else now;until=253402300799 if perpetual else start+term*86400
                if until<=start:raise FulfillmentPending('EXISTING_PERPETUAL_LICENSE_REVIEW_REQUIRED')
                if until>253402300799:raise ValueError('ENTITLEMENT_TIME_OVERFLOW')
                baseline=modules.execute('SELECT COALESCE(MAX(id),0) FROM module_events').fetchone()[0]
                old=dict(binding=binding,state='RESERVED',at=now,before=list(before) if before else None,start=start,until=until,baseline=baseline)
                c.db.execute("INSERT INTO events VALUES('COMMUNITY_SAAS_FINANCE_PROOF',?,?)",(proof_key,now))
                c.db.execute("INSERT INTO links VALUES('COMMUNITY_SAAS_FULFILLMENT',?,?,?,?,1)",(key,g['user_id'],g['project'],c.encrypt(canonical(old),'saas-fulfillment:'+key)))
                c.db.execute("INSERT INTO links VALUES('COMMUNITY_SAAS_MODULE_LOCK',?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET active=1,payload=excluded.payload,user_id=excluded.user_id",(lock,g['user_id'],g['project'],c.encrypt(canonical({'fulfillment':key}),'saas-module-lock')))
                c.audit(g['project'],g['user_id'],'SAAS_FULFILLMENT_RESERVED',key)
            guard()
        # Original order transitions commit individually; each step is deterministic.
        stages=('PREPARED','AWAITING_EXTERNAL','CONFIRMATION_UNKNOWN','CONFIRMED_EXTERNAL')
        guard();current=status(db,order_id,tenant)
        if current['state'] not in stages:raise FulfillmentPending('ORDER_TERMINAL_STATE_CONFLICT')
        if current['state']=='CONFIRMED_EXTERNAL' and current['proof_ref']!=confirmation.proof_id:raise PermissionError('OTHER_FINANCE_PROOF_RECORDED')
        for target in stages[stages.index(current['state'])+1:]:
            guard()
            advance(db,order_id,tenant,'sf_'+hashlib.sha256(canonical([key,target])).hexdigest()[:48],target,old['at'],proof_ref=confirmation.proof_id if target=='CONFIRMED_EXTERNAL' else None,trusted_finance_attestation=target=='CONFIRMED_EXTERNAL')
            guard()
        with c.tx():
            guard();saved=self._load(key);guard()
            if saved['state']=='COMPLETED':return dict(order_id=order_id,state='COMPLETED',entitlement_granted=True,duplicate=True,valid_until=saved['until'])
            lockrow=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_SAAS_MODULE_LOCK' AND subject_idx=? AND active=1",(lock,)).fetchone()
            if lockrow is None or json.loads(c.decrypt(lockrow[0],'saas-module-lock'))!={'fulfillment':key}:raise FulfillmentPending('MODULE_LOCK_CHANGED')
            before=saved['before'];expected=[min(before[0],saved['start']) if before else saved['start'],saved['until'],price,'PAID_ORDER_CONFIRMED']
            actual=modules.execute('SELECT valid_from,valid_until,price_version,source FROM module_entitlements WHERE tenant_id=? AND module_id=?',(tenant,module)).fetchone()
            actual=list(actual) if actual else None
            guard()
            if actual==before:
                grant(modules,tenant,module,saved['start'],saved['until'],price,source='PAID_ORDER_CONFIRMED')
            elif actual==expected:
                # Recovery after module commit but before Center completion. Require
                # exactly one matching original append-only event after reservation.
                events=modules.execute('SELECT old_until,new_until,occurred_at FROM module_events WHERE tenant_id=? AND module_id=? AND id>?',(tenant,module,saved['baseline'])).fetchall()
                if events!=[(before[1] if before else None,saved['until'],saved['start'])]:raise FulfillmentPending('ENTITLEMENT_RECOVERY_EVENT_CONFLICT')
            else:raise FulfillmentPending('ENTITLEMENT_CHANGED_REVIEW_REQUIRED')
            guard()
            after=modules.execute('SELECT valid_from,valid_until,price_version,source FROM module_entitlements WHERE tenant_id=? AND module_id=?',(tenant,module)).fetchone()
            if list(after)!=expected:raise FulfillmentPending('ENTITLEMENT_WRITE_UNKNOWN')
            saved['state']='COMPLETED';self._save(key,saved)
            c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_SAAS_MODULE_LOCK' AND subject_idx=?",(lock,))
            c.audit(g['project'],g['user_id'],'SAAS_FULFILLMENT_COMPLETED',key)
            guard()
        guard()
        return dict(order_id=order_id,state='COMPLETED',entitlement_granted=True,duplicate=False,valid_until=saved['until'])

    def inspect(self,session,csrf,workspace,order_id):
        g,context=self._context(session,csrf,workspace)
        if not valid_id(order_id):raise ValueError('INVALID_ORDER_ID')
        read(self.runtime.saas.orders,order_id,g['tenant'])
        key=hashlib.sha256(canonical([g['tenant'],order_id])).hexdigest();saved=self._load(key)
        self._guard(context,session,csrf,workspace)
        if saved is None:return dict(order_id=order_id,state='AWAITING_FINANCE_CONFIRMATION',entitlement_granted=False)
        return dict(order_id=order_id,state=saved['state'],entitlement_granted=saved['state']=='COMPLETED',
                    valid_from=saved['start'],valid_until=saved['until'],proof_id=saved['binding']['proof_id'],
                    recovery_required=saved['state'] not in ('COMPLETED','REVERSED'))

    def dispatch(self,session,csrf,body):
        if type(body) is not dict or set(body)!={'workspace','operation','params'} or type(body['workspace']) is not str or type(body['operation']) is not str or type(body['params']) is not dict:
            raise ValueError('INVALID_FULFILLMENT_REQUEST')
        fields={'requirements':{'order_id'},'confirm':{'order_id','proof'},'status':{'order_id'},'reverse':{'order_id','proof'}}
        op,p=body['operation'],body['params']
        if op not in fields or set(p)!=fields[op]:raise ValueError('INVALID_FULFILLMENT_FIELDS')
        self._operator(session,csrf,body['workspace'])
        with self.center.tx():self.center.limit('saas-fulfillment:'+self.center.session(session,csrf),20,60)
        if op=='requirements':
            g,context=self._context(session,csrf,body['workspace']);claim=plan_finance_claim(self.runtime.saas.orders,p['order_id'],g['tenant'])
            self._guard(context,session,csrf,body['workspace'])
            return dict(claim=claim,claim_sha256=hashlib.sha256(canonical(claim)).hexdigest(),confirmation_audience='xuanjun.community.saas.fulfillment.v1',reversal_audience='xuanjun.community.saas.reversal.v1',signed_finance_confirmation_required=True)
        if op=='status':return self.inspect(session,csrf,body['workspace'],p['order_id'])
        if op=='reverse':return self.reverse(session,csrf,body['workspace'],p['order_id'],p['proof'])
        return self.fulfill(session,csrf,body['workspace'],p['order_id'],p['proof'])

    def reverse(self,session,csrf,workspace,order_id,proof):
        """Consume authoritative full reversal; restore only this order's grant.

        Later renewals, manual changes or mixed grants require review. No provider
        refund is initiated and historical original confirmation is not erased.
        """
        if self.reversal_finance is None:raise PermissionError('REVERSAL_AUTHORITY_NOT_CONFIGURED')
        g,context=self._context(session,csrf,workspace);c=self.center;tenant=g['tenant']
        guard=lambda:self._guard(context,session,csrf,workspace)
        if not valid_id(order_id):raise ValueError('INVALID_ORDER_ID')
        db=self.runtime.saas.orders;modules=self.runtime.saas.modules
        if db.in_transaction or modules.in_transaction:raise ValueError('EXTERNAL_TRANSACTION_DENIED')
        claim=plan_finance_claim(db,order_id,tenant);digest=hashlib.sha256(canonical(claim)).hexdigest();now=c.now()
        guard()
        receipt=self.reversal_finance.verify(json.loads(canonical(claim)),proof,now)
        if (type(receipt) is not FinanceConfirmation or not valid_id(receipt.proof_id) or receipt.claim_sha256!=digest
                or type(receipt.verified_at) is not int or not read(db,order_id,tenant)['created_at']<=receipt.verified_at<=now):
            raise PermissionError('AUTHORITATIVE_REVERSAL_REQUIRED')
        guard()
        if plan_finance_claim(db,order_id,tenant)!=claim:raise PermissionError('REVERSAL_CLAIM_CHANGED')
        key=hashlib.sha256(canonical([tenant,order_id])).hexdigest();proof_key=c.idx('saas-finance-reversal:'+self.authority_id+':'+receipt.proof_id)
        with c.tx():
            guard();saved=self._load(key);guard()
            if saved is None or saved['binding']['claim_sha256']!=digest:raise PermissionError('ORIGINAL_FULFILLMENT_REQUIRED')
            module=saved['binding']['module'];lock=c.idx('saas-module-fulfillment:'+tenant+':'+module)
            if saved['state']=='REVERSED':
                if saved['reversal_proof_id']!=receipt.proof_id:raise PermissionError('REVERSAL_PROOF_COLLISION')
                return dict(order_id=order_id,state='REVERSED',entitlement_granted=False,duplicate=True,provider_refund_executed=False)
            if saved['state']=='COMPLETED':
                if c.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_SAAS_MODULE_LOCK' AND subject_idx=? AND active=1",(lock,)).fetchone():raise FulfillmentPending('MODULE_FULFILLMENT_PENDING')
                if c.db.execute("SELECT 1 FROM events WHERE channel='COMMUNITY_SAAS_FINANCE_REVERSAL' AND event_id=?",(proof_key,)).fetchone():raise PermissionError('REVERSAL_PROOF_ALREADY_CONSUMED')
                c.db.execute("INSERT INTO events VALUES('COMMUNITY_SAAS_FINANCE_REVERSAL',?,?)",(proof_key,now))
                saved.update(state='REVERSAL_RESERVED',reversal_proof_id=receipt.proof_id,reversal_at=now,reversal_baseline=modules.execute('SELECT COALESCE(MAX(id),0) FROM module_events').fetchone()[0])
                self._save(key,saved)
                c.db.execute("INSERT INTO links VALUES('COMMUNITY_SAAS_MODULE_LOCK',?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET active=1,payload=excluded.payload,user_id=excluded.user_id",(lock,g['user_id'],g['project'],c.encrypt(canonical({'fulfillment':key,'operation':'REVERSE'}),'saas-module-lock')))
                c.audit(g['project'],g['user_id'],'SAAS_REVERSAL_RESERVED',key)
            elif saved['state']!='REVERSAL_RESERVED' or saved.get('reversal_proof_id')!=receipt.proof_id:
                raise FulfillmentPending('FULFILLMENT_NOT_READY_FOR_REVERSAL')
            guard()
        with c.tx():
            guard();saved=self._load(key);guard()
            if saved['state']=='REVERSED':return dict(order_id=order_id,state='REVERSED',entitlement_granted=False,duplicate=True,provider_refund_executed=False)
            lockrow=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_SAAS_MODULE_LOCK' AND subject_idx=? AND active=1",(lock,)).fetchone()
            if lockrow is None or json.loads(c.decrypt(lockrow[0],'saas-module-lock'))!={'fulfillment':key,'operation':'REVERSE'}:raise FulfillmentPending('REVERSAL_LOCK_CHANGED')
            before=saved['before'];granted=[min(before[0],saved['start']) if before else saved['start'],saved['until'],saved['binding']['price_version'],'PAID_ORDER_CONFIRMED']
            guard();modules.execute('BEGIN IMMEDIATE')
            try:
                row=modules.execute('SELECT valid_from,valid_until,price_version,source FROM module_entitlements WHERE tenant_id=? AND module_id=?',(tenant,module)).fetchone();actual=list(row) if row else None
                if actual==granted:
                    if before is None:modules.execute('DELETE FROM module_entitlements WHERE tenant_id=? AND module_id=?',(tenant,module))
                    else:modules.execute('UPDATE module_entitlements SET valid_from=?,valid_until=?,price_version=?,source=? WHERE tenant_id=? AND module_id=?',(*before,tenant,module))
                    modules.execute("INSERT INTO module_events(tenant_id,module_id,action,old_until,new_until,occurred_at) VALUES(?,?,'REVERSE',?,?,?)",(tenant,module,saved['until'],before[1] if before else None,saved['reversal_at']))
                elif actual==before:
                    events=modules.execute('SELECT action,old_until,new_until,occurred_at FROM module_events WHERE tenant_id=? AND module_id=? AND id>?',(tenant,module,saved['reversal_baseline'])).fetchall()
                    if events!=[('REVERSE',saved['until'],before[1] if before else None,saved['reversal_at'])]:raise FulfillmentPending('REVERSAL_RECOVERY_EVENT_CONFLICT')
                else:raise FulfillmentPending('LATER_LICENSE_CHANGE_REQUIRES_REVIEW')
                guard();modules.commit()
            except BaseException:modules.rollback();raise
            guard()
            saved['state']='REVERSED';self._save(key,saved)
            c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_SAAS_MODULE_LOCK' AND subject_idx=?",(lock,))
            c.audit(g['project'],g['user_id'],'SAAS_REVERSAL_COMPLETED',key)
            guard()
        guard()
        return dict(order_id=order_id,state='REVERSED',entitlement_granted=False,duplicate=False,provider_refund_executed=False)
