"""Opt-in provider refund/profitsharing operations on original scoped orders.

No network call at import/configuration. Original Center persists consumed
intents and uncertainty; query is the only continuation after submission.
Provider observations never substitute for Finance confirmation.
Protocol: pay.wechatpay.cn/doc/v3/partner/4012886219 and /4012690683.
"""
import base64
import hashlib
import json
import re
import secrets
import urllib.parse
import urllib.request
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
from scripts.community_center_operations import CenterOperations
from scripts.community_wechat_sp_readonly import PartnerOrderReader
from scripts.community_wechat_sp_verification import verify_signed_body,_json
from scripts.community_order_store import state
from scripts.community_merchant_contract import scope,valid_id
from scripts.community_provider_reference import provider_order_reference
from scripts.pr122_customer_core import canonical


class ProviderActionUnknown(RuntimeError):pass


class ProviderActions:
    def __init__(self,operations,reader,bindings):
        if type(operations) is not CenterOperations or not isinstance(reader,PartnerOrderReader) or type(bindings) is not dict or not bindings:
            raise ValueError('ORIGINAL_OPERATIONS_AND_PROTECTED_PROVIDER_CONFIG_REQUIRED')
        self.operations,self.center,self.runtime=operations,operations.center,operations.runtime
        self.reader=reader;self.bindings={}
        for identity,record in bindings.items():
            if type(identity) is not tuple or len(identity)!=3:raise ValueError('INVALID_PROVIDER_STORE_BINDING')
            scope(dict(zip(('tenant_id','merchant_id','store_id'),identity)))
            fields={'sp_appid','sub_mchid','sub_appid','refund_notify_url','profit_sharing','max_total_bps','receivers','enabled_operations'}
            if type(record) is not dict or set(record)!=fields:raise ValueError('INVALID_PROVIDER_ACTION_POLICY')
            if (type(record['sp_appid']) is not str or not re.fullmatch('wx[0-9a-fA-F]{16}',record['sp_appid'])
                    or type(record['sub_mchid']) is not str or not re.fullmatch('[0-9]{6,32}',record['sub_mchid'])
                    or record['sub_appid'] is not None and (type(record['sub_appid']) is not str or not re.fullmatch('wx[0-9a-fA-F]{16}',record['sub_appid']))
                    or type(record['profit_sharing']) is not bool or type(record['max_total_bps']) is not int or not 0<=record['max_total_bps']<=10000
                    or type(record['enabled_operations']) not in (list,tuple) or any(x not in ('REFUND','SPLIT') for x in record['enabled_operations'])
                    or type(record['refund_notify_url']) is not str):raise ValueError('INVALID_PROVIDER_ACTION_POLICY')
            url=urllib.parse.urlsplit(record['refund_notify_url'])
            if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment or len(record['refund_notify_url'])>255 or any(ord(ch)<33 for ch in record['refund_notify_url']):raise ValueError('FIXED_REFUND_CALLBACK_REQUIRED')
            receivers=record['receivers']
            if type(receivers) is not dict or len(receivers)>50:raise ValueError('INVALID_ADMITTED_RECEIVERS')
            seen=set()
            for rid,r in receivers.items():
                if (not valid_id(rid) or type(r) is not dict or set(r)!={'type','account','name','label'}
                        or r['type'] not in ('MERCHANT_ID','PERSONAL_OPENID','PERSONAL_SUB_OPENID')
                        or type(r['account']) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}',r['account'])
                        or type(r['label']) is not str or not 1<=len(r['label'])<=80
                        or r['name'] is not None and (type(r['name']) is not str or not 1<=len(r['name'].encode())<=190)
                        or r['type']=='MERCHANT_ID' and (r['name'] is None or not re.fullmatch('[0-9]{6,32}',r['account']))
                        or r['type']=='PERSONAL_SUB_OPENID' and record['sub_appid'] is None):raise ValueError('INVALID_ADMITTED_RECEIVER')
                pair=(r['type'],r['account'])
                if pair in seen:raise ValueError('DUPLICATE_ADMITTED_RECEIVER')
                seen.add(pair)
            self.bindings[identity]=json.loads(canonical(record))
    def __repr__(self):return '<ProviderActions merchant and receiver configuration redacted>'
    def _authorize(self,session,csrf,workspace):
        if type(csrf) is not str or not csrf:raise PermissionError('CENTER_CSRF_REQUIRED')
        c=self.center;uid=c.session(session,csrf);g=self.operations.grants.get(workspace)
        if g is None or g['user_id']!=uid or g['role'] not in ('FINANCE_APPROVER','PLATFORM_OWNER'):raise PermissionError('REGISTERED_FINANCE_OPERATOR_REQUIRED')
        p=g['principal']
        if p.role!=g['role'] or p.tenant_id!=g['tenant'] or self.runtime.bindings.get(p)!=g['scope']:raise PermissionError('FINANCE_GRANT_CHANGED')
        project,_,_=c.project(uid,g['project'],g['project_roles'])
        identity=tuple(g['scope'][k] for k in ('tenant_id','merchant_id','store_id'))
        if project['tenant']!=g['tenant'] or identity not in self.bindings:raise PermissionError('PROVIDER_SCOPE_NOT_ADMITTED')
        return g,json.loads(canonical(self.bindings[identity]))
    def _policy_hash(self,policy):
        return hashlib.sha256(canonical({k:v for k,v in policy.items() if k!='enabled_operations'})).hexdigest()
    def _load(self,key):
        row=self.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PROVIDER_ACTION' AND subject_idx=? AND active=1",(key,)).fetchone()
        return None if row is None else json.loads(self.center.decrypt(row[0],'provider-action:'+key))
    def _save(self,key,data):
        self.center.db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_PROVIDER_ACTION' AND subject_idx=? AND active=1",(self.center.encrypt(canonical(data),'provider-action:'+key),key))
    def _call(self,method,target,body=None):
        r=self.reader;now=r._clock()
        if type(now) is not int or not 0<=now<=253402300799:raise ValueError('INVALID_SERVER_CLOCK')
        nonce=secrets.token_hex(16);raw=canonical(body) if body is not None else b''
        signed=(method+'\n'+target+'\n'+str(now)+'\n'+nonce+'\n').encode()+raw+b'\n'
        sig=base64.b64encode(r._private.sign(signed,padding.PKCS1v15(),hashes.SHA256())).decode()
        authorization='WECHATPAY2-SHA256-RSA2048 mchid="'+r._mchid+'",nonce_str="'+nonce+'",timestamp="'+str(now)+'",serial_no="'+r._serial+'",signature="'+sig+'"'
        request=urllib.request.Request('https://api.mch.weixin.qq.com'+target,method=method,data=raw if method=='POST' else None,headers={'Authorization':authorization,'Accept':'application/json','Content-Type':'application/json','Wechatpay-Serial':r._kid})
        headers,response=r._fetch(request);verify_signed_body(headers,response,r._public,r._kid,r._clock())
        data=_json(response)
        if type(data) is not dict:raise ValueError('INVALID_PROVIDER_RESPONSE')
        return data,hashlib.sha256(response).hexdigest()
    def _summary(self,saved):
        return dict(reference=saved['reference'],request_id=saved['request_id'],kind=saved['kind'],
                    status=saved.get('result',{}).get('status','SUBMITTED_RESULT_UNKNOWN'),
                    provider_response_verified='result' in saved,finance_status='UNCONFIRMED',
                    automatic_retry_allowed=False,provider_reference=saved['provider_reference'])
    def dispatch(self,session,csrf,body):
        if type(body) is not dict or set(body)!={'workspace','operation','params'} or type(body['workspace']) is not str or type(body['operation']) is not str or type(body['params']) is not dict:raise ValueError('INVALID_PROVIDER_ACTION_FIELDS')
        schemas={'receivers':set(),'refund':{'reference','request_id','amount_minor','reason'},'split':{'reference','request_id','allocations','description','unfreeze_unsplit'},'query_refund':{'reference','request_id'},'query_split':{'reference','request_id'},'status_refund':{'reference','request_id'},'status_split':{'reference','request_id'}}
        op,p=body['operation'],body['params']
        if op not in schemas or set(p)!=schemas[op]:raise ValueError('INVALID_PROVIDER_ACTION_PARAMS')
        g,policy=self._authorize(session,csrf,body['workspace']);c=self.center
        with c.tx():c.limit('community-provider-actions:'+g['user_id'],20,60)
        if op=='receivers':return dict(receivers=[dict(id=k,label=v['label'],type=v['type']) for k,v in policy['receivers'].items()],enabled_operations=policy['enabled_operations'])
        if not valid_id(p['reference']) or not valid_id(p['request_id']):raise ValueError('INVALID_PROVIDER_ACTION_REFERENCE')
        kind='REFUND' if op.endswith('refund') or op=='refund' else 'SPLIT'
        original=state(self.runtime.demo.db,g['scope'],p['reference'])
        provider_ref=('rf' if kind=='REFUND' else 'ps')+hashlib.sha256(canonical([self.reader._mchid,g['scope'],p['reference'],p['request_id'],kind])).hexdigest()[:30]
        key=hashlib.sha256(canonical([self.reader._mchid,kind,provider_ref])).hexdigest()
        scope_hash=hashlib.sha256(canonical(g['scope'])).hexdigest();policy_hash=self._policy_hash(policy)
        lock=c.idx('provider-order-action:'+self.reader._mchid+':'+provider_order_reference(self.reader._mchid,g['scope'],p['reference']))
        saved=self._load(key)
        if saved is not None and (saved['scope_hash']!=scope_hash or saved['policy_hash']!=policy_hash):raise PermissionError('PROVIDER_ACTION_BINDING_CHANGED')
        if op.startswith('status_'):
            if saved is None:raise ValueError('PROVIDER_ACTION_NOT_FOUND')
            return self._summary(saved)
        if op.startswith('query_'):
            if saved is None:raise ValueError('PROVIDER_ACTION_NOT_FOUND')
            return self._query(session,csrf,body['workspace'],g,policy,key,lock,saved)
        if kind not in policy['enabled_operations']:raise PermissionError('PROVIDER_ACTION_NOT_ENABLED')
        if saved is not None:
            if saved['request_hash']!=hashlib.sha256(canonical(p)).hexdigest():raise PermissionError('PROVIDER_ACTION_ID_COLLISION')
            return self._summary(saved)
        out_trade_no=provider_order_reference(self.reader._mchid,g['scope'],p['reference'])
        expected=dict(sp_mchid=self.reader._mchid,sp_appid=policy['sp_appid'],sub_mchid=policy['sub_mchid'],out_trade_no=out_trade_no,amount_minor=original['amount_minor'],currency='CNY')
        paid=self.reader.read_order(expected)
        if paid['provider_state'] not in (('SUCCESS','REFUND') if kind=='REFUND' else ('SUCCESS',)):raise PermissionError('SIGNED_SUCCESSFUL_ORDER_REQUIRED')
        if self._authorize(session,csrf,body['workspace'])[1]!=policy:raise PermissionError('PROVIDER_POLICY_CHANGED')
        current=state(self.runtime.demo.db,g['scope'],p['reference'])
        if current!=original:raise PermissionError('ORIGINAL_ORDER_CHANGED')
        from scripts.community_order_provider_projection import project_verified_query
        project_verified_query(self.runtime.demo.db,g['scope'],p['reference'],expected,paid,c.now(),self.reader._kid)
        if kind=='REFUND':
            if type(p['amount_minor']) is not int or not 1<=p['amount_minor']<=original['amount_minor'] or type(p['reason']) is not str or not 1<=len(p['reason'])<=80:raise ValueError('INVALID_REFUND_REQUEST')
            payload=dict(sub_mchid=policy['sub_mchid'],out_trade_no=out_trade_no,out_refund_no=provider_ref,reason=p['reason'],notify_url=policy['refund_notify_url'],amount=dict(refund=p['amount_minor'],total=original['amount_minor'],currency='CNY'))
        else:
            allocations=p['allocations']
            if not policy['profit_sharing'] or type(allocations) is not dict or not 1<=len(allocations)<=50 or any(type(v) is not int or v<=0 for v in allocations.values()) or any(k not in policy['receivers'] for k in allocations) or sum(allocations.values())>original['amount_minor']*policy['max_total_bps']//10000 or type(p['unfreeze_unsplit']) is not bool or type(p['description']) is not str or not 1<=len(p['description'])<=80:raise ValueError('INVALID_ADMITTED_SPLIT')
            public=serialization.load_pem_public_key(self.reader._public);receivers=[]
            for rid,amount in sorted(allocations.items()):
                receiver=policy['receivers'][rid];r=dict(type=receiver['type'],account=receiver['account'],amount=amount,description=p['description'])
                if receiver['name'] is not None:r['name']=base64.b64encode(public.encrypt(receiver['name'].encode(),padding.OAEP(mgf=padding.MGF1(hashes.SHA1()),algorithm=hashes.SHA1(),label=None))).decode()
                receivers.append(r)
            payload=dict(sub_mchid=policy['sub_mchid'],appid=policy['sp_appid'],transaction_id=paid['transaction_id'],out_order_no=provider_ref,receivers=receivers,unfreeze_unsplit=p['unfreeze_unsplit'])
            if policy['sub_appid'] is not None:payload['sub_appid']=policy['sub_appid']
        saved=dict(kind=kind,reference=p['reference'],request_id=p['request_id'],provider_reference=provider_ref,scope_hash=scope_hash,policy_hash=policy_hash,request_hash=hashlib.sha256(canonical(p)).hexdigest(),payload=payload,transaction_id=paid['transaction_id'],at=c.now())
        with c.tx():
            if self._load(key) is not None:raise ProviderActionUnknown('CONCURRENT_ACTION_EXISTS_QUERY_ONLY')
            if c.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_PROVIDER_ORDER_LOCK' AND subject_idx=? AND active=1",(lock,)).fetchone():raise ProviderActionUnknown('PRIOR_ORDER_ACTION_UNKNOWN_QUERY_OR_REVIEW_REQUIRED')
            c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_ACTION',?,?,?,?,1)",(key,g['user_id'],g['project'],c.encrypt(canonical(saved),'provider-action:'+key)))
            c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_ORDER_LOCK',?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET active=1,payload=excluded.payload,user_id=excluded.user_id",(lock,g['user_id'],g['project'],c.encrypt(canonical({'action':key}),'provider-order-lock')))
            c.audit(g['project'],g['user_id'],'PROVIDER_'+kind+'_SUBMITTED',key)
        try:
            data,digest=self._call('POST','/v3/refund/domestic/refunds' if kind=='REFUND' else '/v3/profitsharing/orders',payload)
            return self._accept(session,csrf,body['workspace'],g,policy,key,lock,saved,data,digest)
        except Exception:raise ProviderActionUnknown('PROVIDER_ACTION_RESULT_UNKNOWN_QUERY_EXISTING_ONLY') from None

    def _query(self,session,csrf,workspace,g,policy,key,lock,saved):
        if saved['kind']=='REFUND':target='/v3/refund/domestic/refunds/'+saved['provider_reference']+'?'+urllib.parse.urlencode({'sub_mchid':policy['sub_mchid']})
        else:target='/v3/profitsharing/orders/'+saved['provider_reference']+'?'+urllib.parse.urlencode({'sub_mchid':policy['sub_mchid'],'transaction_id':saved['transaction_id']})
        try:
            data,digest=self._call('GET',target)
            return self._accept(session,csrf,workspace,g,policy,key,lock,saved,data,digest)
        except Exception:raise ProviderActionUnknown('PROVIDER_QUERY_UNKNOWN_NO_RESUBMISSION') from None
    def _accept(self,session,csrf,workspace,g,policy,key,lock,saved,data,digest):
        current,now_policy=self._authorize(session,csrf,workspace)
        if current['scope']!=g['scope'] or self._policy_hash(now_policy)!=self._policy_hash(policy):raise PermissionError('PROVIDER_ACTION_POLICY_CHANGED')
        payload=saved['payload']
        if data.get('sub_mchid')!=policy['sub_mchid']:raise ValueError('PROVIDER_SUBMERCHANT_MISMATCH')
        if saved['kind']=='REFUND':
            amount=data.get('amount')
            if (data.get('out_refund_no')!=saved['provider_reference'] or data.get('out_trade_no')!=payload['out_trade_no']
                    or type(amount) is not dict or type(amount.get('total')) is not int or type(amount.get('refund')) is not int
                    or amount.get('total')!=payload['amount']['total'] or amount.get('refund')!=payload['amount']['refund']
                    or amount.get('currency')!='CNY' or data.get('status') not in ('SUCCESS','CLOSED','PROCESSING','ABNORMAL')):
                raise ValueError('PROVIDER_REFUND_BINDING_MISMATCH')
            result=dict(status=data['status'],amount_minor=amount['refund']);terminal=data['status'] in ('SUCCESS','CLOSED')
        else:
            if data.get('out_order_no')!=saved['provider_reference'] or data.get('transaction_id')!=saved['transaction_id'] or data.get('state') not in ('PROCESSING','FINISHED'):
                raise ValueError('PROVIDER_SPLIT_BINDING_MISMATCH')
            receivers=data.get('receivers',[])
            if type(receivers) is not list or len(receivers)>50:raise ValueError('INVALID_PROVIDER_RECEIVERS')
            expected=sorted((r['type'],r['account'],r['amount']) for r in payload['receivers'])
            observed=[];results=[]
            for r in receivers:
                if type(r) is not dict or type(r.get('amount')) is not int or type(r.get('type')) is not str or type(r.get('account')) is not str or r.get('result') not in ('SUCCESS','CLOSED','PENDING'):raise ValueError('INVALID_RECEIVER_RESULT')
                observed.append((r['type'],r['account'],r['amount']))
                ids=[rid for rid,config in policy['receivers'].items() if config['type']==r['type'] and config['account']==r['account']]
                if len(ids)!=1:raise ValueError('UNADMITTED_PROVIDER_RECEIVER')
                results.append(dict(receiver_id=ids[0],amount_minor=r['amount'],result=r['result']))
            if observed and sorted(observed)!=expected or data['state']=='FINISHED' and sorted(observed)!=expected:raise ValueError('RECEIVER_ALLOCATION_MISMATCH')
            if data['state']=='FINISHED' and any(r['result']=='PENDING' for r in results):raise ValueError('FINISHED_SPLIT_HAS_PENDING_RECEIVERS')
            result=dict(status=data['state'],receivers=results,receiver_results_pending=not receivers);terminal=data['state']=='FINISHED'
        with self.center.tx():
            persisted=self._load(key)
            if persisted is None or persisted['request_hash']!=saved['request_hash']:raise PermissionError('PROVIDER_INTENT_CHANGED')
            previous=persisted.get('result')
            if previous and previous['status'] in ('SUCCESS','CLOSED','FINISHED') and previous['status']!=result['status']:raise ProviderActionUnknown('TERMINAL_PROVIDER_RESULT_CONFLICT')
            persisted['result']=result;persisted['response_sha256']=digest;persisted['observed_at']=self.center.now();self._save(key,persisted)
            if terminal:
                row=self.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PROVIDER_ORDER_LOCK' AND subject_idx=? AND active=1",(lock,)).fetchone()
                if row is not None and json.loads(self.center.decrypt(row[0],'provider-order-lock'))=={'action':key}:
                    self.center.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_PROVIDER_ORDER_LOCK' AND subject_idx=?",(lock,))
            self.center.audit(g['project'],g['user_id'],'PROVIDER_'+saved['kind']+'_OBSERVED',digest)
        if saved['kind']=='REFUND' and result['status']=='SUCCESS':
            from scripts.community_order_provider_projection import project_verified_refund
            project_verified_refund(self.runtime.demo.db,g['scope'],saved['reference'],saved['provider_reference'],payload['amount']['refund'],payload['amount']['total'],digest,self.center.now())
        return dict(self._summary(persisted),result=result)
