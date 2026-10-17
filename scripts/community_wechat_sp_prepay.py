"""Partner Mini Program prepay, signed response and client payment signature.

Protected host composition only; not registered on HTTP or enabled in production.
Original Center events/links persist one-attempt consumption and encrypted result.
https://pay.wechatpay.cn/doc/v3/partner/4012759974
"""
import base64
import hashlib
import json
import re
import secrets
from urllib.parse import urlsplit
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from scripts.community_wechat_sp_readonly import PartnerOrderReader
from scripts.community_wechat_sp_verification import verify_signed_body,_json
from scripts.pr122_customer_core import Center,canonical


class PrepayUnknown(RuntimeError):pass


class PartnerPrepay:
    def __init__(self,center,reader,bindings):
        if type(center) is not Center or not isinstance(reader,PartnerOrderReader) or type(bindings) is not dict:
            raise ValueError('EXISTING_CENTER_AND_PROTECTED_PAYMENT_BINDINGS_REQUIRED')
        self.center,self.reader=center,reader
        self.bindings={}
        fields={'user_id','project','sp_appid','sub_mchid','out_trade_no','amount_minor','description','notify_url','sp_openid','profit_sharing'}
        for reference,b in bindings.items():
            if (type(reference) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}',reference)
                    or type(b) is not dict or set(b)!=fields):raise ValueError('INVALID_PAYMENT_BINDING')
            for field in ('user_id','project'):
                if type(b[field]) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}',b[field]):raise ValueError('INVALID_PAYMENT_OWNER')
            if (type(b['sp_appid']) is not str or not re.fullmatch('wx[0-9a-fA-F]{16}',b['sp_appid'])
                    or type(b['sub_mchid']) is not str or not re.fullmatch('[0-9]{6,32}',b['sub_mchid'])
                    or type(b['out_trade_no']) is not str or not re.fullmatch('[A-Za-z0-9_-]{6,32}',b['out_trade_no'])
                    or type(b['amount_minor']) is not int or not 1<=b['amount_minor']<=100000000
                    or type(b['description']) is not str or not 1<=len(b['description'])<=127
                    or any(ord(c)<32 for c in b['description'])
                    or type(b['sp_openid']) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,128}',b['sp_openid'])
                    or type(b['profit_sharing']) is not bool or type(b['notify_url']) is not str):raise ValueError('INVALID_PROVIDER_ORDER')
            u=urlsplit(b['notify_url'])
            if (u.scheme!='https' or not u.hostname or u.username or u.password or u.fragment
                    or u.query or len(b['notify_url'])>255 or any(ord(c)<33 for c in b['notify_url'])):
                raise ValueError('FIXED_HTTPS_NOTIFICATION_REQUIRED')
            key=(reader._mchid,b['out_trade_no'])
            if any((reader._mchid,x['out_trade_no'])==key for x in self.bindings.values()):raise ValueError('DUPLICATE_PROVIDER_ORDER')
            self.bindings[reference]=dict(b)
    def __repr__(self):return '<PartnerPrepay protected payment bindings redacted>'
    def _authorize(self,session,csrf,reference):
        if type(csrf) is not str or not csrf:raise PermissionError('CENTER_CSRF_REQUIRED')
        if type(reference) is not str or reference not in self.bindings:raise PermissionError('PAYMENT_BINDING_REQUIRED')
        c=self.center;uid=c.session(session,csrf);b=self.bindings[reference]
        if uid!=b['user_id']:raise PermissionError('PAYMENT_OWNER_REQUIRED')
        c.project(uid,b['project'],('OWNER','EDITOR'))
        return dict(b)
    def _identity(self,b):return self.center.idx('community-prepay:'+self.reader._mchid+':'+b['out_trade_no'])
    def _sign(self,message):
        return base64.b64encode(self.reader._private.sign(message,padding.PKCS1v15(),hashes.SHA256())).decode()
    def create(self,session,csrf,reference):
        b=self._authorize(session,csrf,reference)
        return self._create_authorized(b,lambda:self._authorize(session,csrf,reference))
    def _create_authorized(self,b,reauthorize):
        c=self.center;r=self.reader;key=self._identity(b)
        now=r._clock()
        if type(now) is not int or not 0<=now<=253402300799:raise ValueError('INVALID_SERVER_CLOCK')
        binding_hash=hashlib.sha256(canonical(b)).hexdigest()
        # Consume before network, in original durable Center. Unknown is never resent.
        with c.tx():
            if c.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_ORDER_CLOSE' AND subject_idx=? AND active=1",(key,)).fetchone():raise PermissionError('ORDER_CLOSING_OR_CANCELLED')
            if c.db.execute("SELECT 1 FROM events WHERE channel='COMMUNITY_PREPAY_ATTEMPT' AND event_id=?",(key,)).fetchone():
                raise PrepayUnknown('PREPAY_ALREADY_ATTEMPTED_QUERY_EXISTING_ONLY')
            c.db.execute("INSERT INTO events VALUES('COMMUNITY_PREPAY_ATTEMPT',?,?)",(key,now))
            c.audit(b['project'],b['user_id'],'COMMUNITY_PREPAY_ATTEMPT',binding_hash)
        try:
            body=dict(sp_mchid=r._mchid,**{k:b[k] for k in ('sp_appid','sub_mchid','description','out_trade_no','notify_url')},
                      amount={'total':b['amount_minor'],'currency':'CNY'},payer={'sp_openid':b['sp_openid']},settle_info={'profit_sharing':b['profit_sharing']})
            raw=canonical(body);nonce=secrets.token_hex(16);timestamp=str(now);path='/v3/pay/partner/transactions/jsapi'
            signature=self._sign(('POST\n'+path+'\n'+timestamp+'\n'+nonce+'\n').encode()+raw+b'\n')
            import urllib.request
            authorization='WECHATPAY2-SHA256-RSA2048 mchid="'+r._mchid+'",nonce_str="'+nonce+'",timestamp="'+timestamp+'",serial_no="'+r._serial+'",signature="'+signature+'"'
            request=urllib.request.Request('https://api.mch.weixin.qq.com'+path,data=raw,method='POST',headers={
                'Authorization':authorization,'Accept':'application/json','Content-Type':'application/json','Wechatpay-Serial':r._kid})
            headers,response=r._fetch(request)
            verify_signed_body(headers,response,r._public,r._kid,r._clock())
            data=_json(response)
            if type(data) is not dict or type(data.get('prepay_id')) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,128}',data['prepay_id']):
                raise ValueError('INVALID_PREPAY_RESPONSE')
            # Re-check live account and project after provider IO; do not issue a client token after revocation.
            if reauthorize()!=b:raise PermissionError('PAYMENT_BINDING_CHANGED')
            payload={'binding_sha256':binding_hash,'prepay_id':data['prepay_id'],'appid':b['sp_appid']}
            with c.tx():
                c.db.execute("INSERT INTO links VALUES('COMMUNITY_PREPAY_RESULT',?,?,?,?,1)",
                    (key,b['user_id'],b['project'],c.encrypt(canonical(payload),'community-prepay')))
                c.audit(b['project'],b['user_id'],'COMMUNITY_PREPAY_READY',key)
            return self._existing_authorized(b,reauthorize)
        except Exception:raise PrepayUnknown('PREPAY_RESULT_UNKNOWN_QUERY_EXISTING_ONLY') from None
    def existing(self,session,csrf,reference):
        b=self._authorize(session,csrf,reference)
        return self._existing_authorized(b,lambda:self._authorize(session,csrf,reference))
    def _existing_authorized(self,b,reauthorize):
        if reauthorize()!=b:raise PermissionError('PAYMENT_BINDING_CHANGED')
        c=self.center;r=self.reader;key=self._identity(b)
        row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PREPAY_RESULT' AND subject_idx=? AND user_id=? AND project=? AND active=1",(key,b['user_id'],b['project'])).fetchone()
        if row is None:raise PrepayUnknown('NO_VERIFIED_PREPAY_RESULT_DO_NOT_RESEND')
        data=json.loads(c.decrypt(row[0],'community-prepay'))
        if data['binding_sha256']!=hashlib.sha256(canonical(b)).hexdigest():raise PermissionError('PAYMENT_BINDING_CHANGED')
        now=r._clock()
        if type(now) is not int or not 0<=now<=253402300799:raise ValueError('INVALID_SERVER_CLOCK')
        timestamp=str(now);nonce=secrets.token_hex(16);package='prepay_id='+data['prepay_id']
        signature=self._sign((b['sp_appid']+'\n'+timestamp+'\n'+nonce+'\n'+package+'\n').encode())
        return dict(timeStamp=timestamp,nonceStr=nonce,package=package,signType='RSA',paySign=signature,
                    payment_status='AWAITING_PAYER_CONFIRMATION',provider_settlement_verified=False)
