"""Protected fixed-origin APIv3 transport, shared by provider business modules."""
import base64
import hashlib
import secrets
import urllib.request
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from scripts.pr122_customer_core import canonical
from scripts.community_wechat_sp_verification import verify_signed_body, _json


def request(reader, method, target, value=None, *, raw=None, content_type='application/json', signing_body=None, empty_response=False):
    if method not in ('GET','POST') or not target.startswith('/v3/') or any(ord(c)<33 for c in target):
        raise ValueError('FIXED_PROVIDER_REQUEST_REQUIRED')
    body=raw if raw is not None else canonical(value) if value is not None else b''
    signed_body=body if signing_body is None else signing_body
    now=reader._clock()
    if type(now) is not int or now<0:raise ValueError('INVALID_PROVIDER_CLOCK')
    nonce=secrets.token_hex(16)
    message=(method+'\n'+target+'\n'+str(now)+'\n'+nonce+'\n').encode()+signed_body+b'\n'
    signature=base64.b64encode(reader._private.sign(message,padding.PKCS1v15(),hashes.SHA256())).decode()
    authorization='WECHATPAY2-SHA256-RSA2048 mchid="'+reader._mchid+'",nonce_str="'+nonce+'",timestamp="'+str(now)+'",serial_no="'+reader._serial+'",signature="'+signature+'"'
    req=urllib.request.Request('https://api.mch.weixin.qq.com'+target,method=method,data=body if method=='POST' else None,
        headers={'Authorization':authorization,'Accept':'application/json','Content-Type':content_type,'Wechatpay-Serial':reader._kid})
    req._community_expect_empty=empty_response
    headers,response=reader._fetch(req)
    verify_signed_body(headers,response,reader._public,reader._kid,reader._clock())
    if empty_response and response==b'':return dict(acknowledged=True),hashlib.sha256(response).hexdigest()
    return _json(response),hashlib.sha256(response).hexdigest()
