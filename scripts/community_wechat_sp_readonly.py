"""Signed, response-verified partner order GET. No payment/refund/split methods.

https://pay.wechatpay.cn/doc/v3/partner/4012759714
Missing trusted merchant binding fails before network. Read-only success does
not write Finance, change orders or grant entitlements. Unknown is never retried.
"""
import base64
import re
import secrets
import urllib.parse
import urllib.request
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding,rsa
from scripts.community_wechat_sp_verification import verify_signed_body,_json
from scripts.community_mini_login import _NoRedirect

class ReadOnlyUnknown(RuntimeError):pass


def certificate_matches(private_key_pem, certificate_pem, expected_serial):
    """Local pairing check only; no certificate issuance or private output."""
    try:
        private=serialization.load_pem_private_key(private_key_pem,password=None)
        cert=x509.load_pem_x509_certificate(certificate_pem)
        return (isinstance(private,rsa.RSAPrivateKey) and
                format(cert.serial_number,'X')==expected_serial.upper() and
                private.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)==
                cert.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo))
    except Exception:raise ValueError('CERTIFICATE_PAIR_CHECK_FAILED') from None


class PartnerOrderReader:
    def __init__(self, sp_mchid, merchant_serial, private_key_pem, public_key_id, public_key_pem, clock):
        if (type(sp_mchid) is not str or not re.fullmatch('[0-9]{6,32}',sp_mchid)
            or type(merchant_serial) is not str or not re.fullmatch('[0-9A-Fa-f]{1,64}',merchant_serial)
            or type(public_key_id) is not str or not re.fullmatch('PUB_KEY_ID_[A-Za-z0-9_]{1,100}',public_key_id)):
            raise ValueError('TRUSTED_MERCHANT_CONFIG_REQUIRED')
        try:
            key=serialization.load_pem_private_key(private_key_pem,password=None)
            public=serialization.load_pem_public_key(public_key_pem)
            if not isinstance(key,rsa.RSAPrivateKey) or key.key_size<2048 or not isinstance(public,rsa.RSAPublicKey) or public.key_size<2048:raise ValueError()
        except Exception:raise ValueError('RSA_KEY_CONFIG_INVALID') from None
        self._private,self._public,self._kid,self._serial=key,public_key_pem,public_key_id,merchant_serial
        self._mchid,self._clock=sp_mchid,clock
    def __repr__(self):return '<PartnerOrderReader credentials redacted>'
    def _fetch(self,request):
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
        with opener.open(request,timeout=5) as response:
            if response.status!=200 and not (response.status==204 and getattr(request,'_community_expect_empty',False)):raise ReadOnlyUnknown('PROVIDER_QUERY_NOT_200')
            headers={};seen=set()
            for key,value in response.headers.items():
                if key.lower() in seen:raise ReadOnlyUnknown('DUPLICATE_PROVIDER_HEADER')
                headers[key]=value;seen.add(key.lower())
            body=response.read(1048577)
            return headers,body
    def read_order(self,expected):
        required={'sp_mchid','sub_mchid','sp_appid','out_trade_no','amount_minor','currency'}
        if (type(expected) is not dict or set(expected)!=required or expected['sp_mchid']!=self._mchid
            or type(expected['sub_mchid']) is not str or not re.fullmatch('[0-9]{6,32}',expected['sub_mchid'])
            or type(expected['sp_appid']) is not str or not re.fullmatch('wx[0-9a-fA-F]{16}',expected['sp_appid'])
            or type(expected['out_trade_no']) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,32}',expected['out_trade_no'])
            or type(expected['amount_minor']) is not int or not 1<=expected['amount_minor']<=100000000
            or expected['currency']!='CNY'):
            raise ValueError('SERVER_ORDER_BINDING_REQUIRED')
        now=self._clock()
        if type(now) is not int or now<0:raise ValueError('SERVER_CLOCK_REQUIRED')
        nonce=secrets.token_hex(16);timestamp=str(now)
        target='/v3/pay/partner/transactions/out-trade-no/'+expected['out_trade_no']+'?'+urllib.parse.urlencode(
            {'sp_mchid':self._mchid,'sub_mchid':expected['sub_mchid']})
        message=('GET\n'+target+'\n'+timestamp+'\n'+nonce+'\n\n').encode()
        signature=base64.b64encode(self._private.sign(message,padding.PKCS1v15(),hashes.SHA256())).decode()
        authorization='WECHATPAY2-SHA256-RSA2048 mchid="'+self._mchid+'",nonce_str="'+nonce+'",timestamp="'+timestamp+'",serial_no="'+self._serial+'",signature="'+signature+'"'
        request=urllib.request.Request('https://api.mch.weixin.qq.com'+target,method='GET',
            headers={'Authorization':authorization,'Accept':'application/json','Wechatpay-Serial':self._kid})
        try:
            headers,raw=self._fetch(request)
            proof=verify_signed_body(headers,raw,self._public,self._kid,self._clock())
            data=_json(raw)
            for field in ('sp_mchid','sub_mchid','sp_appid','out_trade_no'):
                if data.get(field)!=expected[field]:raise ValueError('ORDER_BINDING_MISMATCH')
            amount=data.get('amount')
            if type(amount) is not dict or type(amount.get('total')) is not int or amount['total']!=expected['amount_minor'] or amount.get('currency')!='CNY':
                raise ValueError('ORDER_AMOUNT_MISMATCH')
            state=data.get('trade_state')
            if state not in ('SUCCESS','REFUND','NOTPAY','CLOSED','REVOKED','USERPAYING','PAYERROR'):
                raise ValueError('UNKNOWN_TRADE_STATE')
            tx=data.get('transaction_id')
            if state in ('SUCCESS','REFUND') and (type(tx) is not str or not re.fullmatch('[0-9]{1,64}',tx)):
                raise ValueError('TRANSACTION_ID_REQUIRED')
            from scripts.community_wechat_sp_verification import signed_success_time
            paid_at=signed_success_time(data.get('success_time'),now) if state in ('SUCCESS','REFUND') else None
            return dict(proof,paid_at=paid_at,source='SIGNED_PROVIDER_ORDER_QUERY',out_trade_no=expected['out_trade_no'],
                        provider_state=state,transaction_id=tx if state in ('SUCCESS','REFUND') else None,
                        amount_minor=amount['total'],currency='CNY',provider_settlement_verified=False,
                        payment='HOLD',refund='HOLD',profitsharing='HOLD')
        except Exception:
            raise ReadOnlyUnknown('PROVIDER_ORDER_QUERY_UNKNOWN_OR_MISMATCH') from None
