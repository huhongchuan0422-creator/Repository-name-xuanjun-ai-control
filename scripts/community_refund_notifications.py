"""Trusted refund callbacks update only already-reserved original refunds."""
import base64
import hashlib
import json
import re
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from scripts.pr122_customer_core import canonical
from scripts.community_wechat_sp_verification import verify_signed_body, _json
from scripts.community_order_provider_projection import project_verified_refund


class RefundNotifications:
    def __init__(self, actions, api_v3_key):
        from scripts.community_wechat_sp_actions import ProviderActions
        if type(actions) is not ProviderActions or type(api_v3_key) is not bytes or len(api_v3_key)!=32:
            raise ValueError('ORIGINAL_PROVIDER_ACTIONS_REQUIRED')
        self.actions,self.center,self._api=actions,actions.center,api_v3_key

    def receive(self, headers, raw):
        a,c=self.actions,self.center
        proof=verify_signed_body(headers,raw,a.reader._public,a.reader._kid,c.now())
        event=_json(raw)
        expected_events={'REFUND.SUCCESS':'SUCCESS','REFUND.CLOSED':'CLOSED','REFUND.ABNORMAL':'ABNORMAL'}
        if event.get('event_type') not in expected_events or event.get('resource_type')!='encrypt-resource':
            raise ValueError('UNSUPPORTED_REFUND_NOTIFICATION')
        if type(event.get('id')) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,128}',event['id']):
            raise ValueError('INVALID_REFUND_EVENT_ID')
        resource=event.get('resource')
        if type(resource) is not dict or resource.get('algorithm')!='AEAD_AES_256_GCM':raise ValueError('INVALID_REFUND_RESOURCE')
        nonce,aad,ciphertext=resource.get('nonce'),resource.get('associated_data',''),resource.get('ciphertext')
        if type(nonce) is not str or len(nonce.encode())!=12 or type(aad) is not str or type(ciphertext) is not str:raise ValueError('INVALID_REFUND_RESOURCE_FIELDS')
        data=_json(AESGCM(self._api).decrypt(nonce.encode(),base64.b64decode(ciphertext,validate=True),aad.encode()))
        ref=data.get('out_refund_no')
        if type(ref) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}',ref):raise ValueError('INVALID_REFUND_REFERENCE')
        key=hashlib.sha256(canonical([a.reader._mchid,'REFUND',ref])).hexdigest()
        saved=a._load(key)
        if saved is None or saved['kind']!='REFUND' or saved.get('scope') is None:raise PermissionError('ORIGINAL_SCOPED_REFUND_RESERVATION_REQUIRED')
        identity=saved['scope'];payload=saved['payload'];amount=data.get('amount')
        if (data.get('sp_mchid')!=a.reader._mchid or data.get('sub_mchid')!=payload['sub_mchid']
                or data.get('out_trade_no')!=payload['out_trade_no'] or data.get('transaction_id')!=saved['transaction_id']
                or data.get('refund_status')!=expected_events[event['event_type']]
                or type(amount) is not dict or type(amount.get('total')) is not int or type(amount.get('refund')) is not int
                or amount['total']!=payload['amount']['total'] or amount['refund']!=payload['amount']['refund']
                or amount.get('currency')!='CNY'):
            raise ValueError('SIGNED_REFUND_NOTIFICATION_BINDING_MISMATCH')
        event_key=hashlib.sha256(canonical([a.reader._mchid,event['id']])).hexdigest()
        binding=dict(action=key,body_sha256=proof['body_sha256'])
        with c.tx():
            row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_REFUND_CALLBACK' AND subject_idx=? AND active=1",(event_key,)).fetchone()
            if row and json.loads(c.decrypt(row[0],'community-refund-callback:'+event_key))!=binding:raise ValueError('REFUND_EVENT_COLLISION')
            if not row:c.db.execute("INSERT INTO links VALUES('COMMUNITY_REFUND_CALLBACK',?,?,?,?,1)",(event_key,saved['actor_user_id'],saved['project'],c.encrypt(canonical(binding),'community-refund-callback:'+event_key)))
            current=a._load(key)
            prior=current.get('result',{}).get('status')
            if prior in ('SUCCESS','CLOSED') and prior!=data['refund_status']:raise ValueError('TERMINAL_REFUND_CALLBACK_CONFLICT')
        # If projection fails, no success ACK is sent. The durable callback and
        # original refund IDs recover the same write without another funds call.
        if data['refund_status']=='SUCCESS':
            project_verified_refund(a.runtime.demo.db,identity,saved['reference'],ref,amount['refund'],amount['total'],proof['body_sha256'],c.now())
        lock=c.idx('provider-order-action:'+a.reader._mchid+':'+payload['out_trade_no'])
        with c.tx():
            current=a._load(key)
            prior=current.get('result',{}).get('status')
            if prior in ('SUCCESS','CLOSED') and prior!=data['refund_status']:raise ValueError('TERMINAL_REFUND_CALLBACK_CONFLICT')
            current.update(result=dict(status=data['refund_status'],amount_minor=amount['refund']),response_sha256=proof['body_sha256'],observed_at=c.now())
            a._save(key,current)
            if data['refund_status'] in ('SUCCESS','CLOSED'):
                row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PROVIDER_ORDER_LOCK' AND subject_idx=? AND active=1",(lock,)).fetchone()
                if row and json.loads(c.decrypt(row[0],'provider-order-lock'))==dict(action=key):
                    c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_PROVIDER_ORDER_LOCK' AND subject_idx=?",(lock,))
            commerce=getattr(a,'commerce',None)
            if commerce is not None:
                application=commerce._read(identity,saved['project'],'REFUND_APPLICATION',saved['request_id'])
                if application is not None and application['reference']==saved['reference'] and application['status'] in ('EXECUTION_RESERVED','COMPLETED','CLOSED'):
                    target={'SUCCESS':'COMPLETED','CLOSED':'CLOSED'}.get(data['refund_status'])
                    if target and application['status']!=target:
                        application=dict(application,status=target,revision=application['revision']+1)
                        commerce._save(identity,saved['project'],application['user_id'],'REFUND_APPLICATION',saved['request_id'],application,True)
                        from scripts.community_customer_profile import notify
                        notify(c,saved['project'],application['user_id'],'REFUND_RESULT',saved['request_id'],'微信退款状态：'+data['refund_status'])
            c.audit(saved['project'],saved['actor_user_id'],'WECHAT_REFUND_CALLBACK_CONFIRMED',event_key)
        return dict(accepted=True,finance_status='UNCONFIRMED')
