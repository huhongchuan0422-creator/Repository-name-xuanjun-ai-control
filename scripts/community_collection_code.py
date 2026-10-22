"""Official release mini collection entry image, gated by existing payment authority.

The code opens this app's original checkout scene; it does not prove a payment.
No preview/develop codes, custom QR renderer, arbitrary URLs or grant creation.
Official interfaces: mp-access-token/getStableAccessToken; qr-code/getUnlimitedQRCode.
"""
import base64
import hashlib
import json
import re
import urllib.request
from scripts.community_mini_login import WechatCodeClient,_NoRedirect
from scripts.community_mini_payments import MiniPayments
from scripts.community_wechat_sp_verification import _json
from scripts.pr122_customer_core import canonical

MAX_IMAGE=1_000_000

class CollectionCodeUnknown(RuntimeError):pass

class CollectionCodes:
    def __init__(self,gateway,onboarding,operations):
        from scripts.community_mini_merchant import MiniMerchant
        if (type(gateway.provider) is not WechatCodeClient or gateway.provider.appid!=gateway.identity.appid
                or type(getattr(gateway,'payments',None)) is not MiniPayments
                or gateway.payments.identity is not gateway.identity
                or not callable(getattr(gateway.payments,'activation_guard',None))):
            raise PermissionError('ORIGINAL_VERIFIED_PAYMENT_ACTIVATION_REQUIRED')
        self.gateway=gateway
        self.merchant=MiniMerchant(gateway.identity,onboarding,operations)
        self._cached_token=None
        self._token_expires=0
    def __repr__(self):return '<CollectionCodes credentials redacted>'
    def _authorize(self,token,scene,workspace):
        g,csrf=self.merchant._grant(token,scene,workspace)
        if g['role']!='MERCHANT_ADMIN':raise PermissionError('MERCHANT_ADMIN_REQUIRED')
        self.merchant.operations.dispatch(token,csrf,dict(workspace=workspace,operation='community.summary',params={}))
        payments=self.gateway.payments
        binding=payments.merchants.get(scene)
        if binding is None:raise PermissionError('PAYMENT_SCENE_NOT_ADMITTED')
        if payments.activation_guard(scene)!=binding['record']:raise PermissionError('PAYMENT_ACTIVATION_CHANGED')
        if binding['scope']!=g['scope'] or binding['project']!=g['project']:
            raise PermissionError('COLLECTION_CODE_STORE_BINDING_CHANGED')
        from scripts.community_platform_merchants import assert_trading
        assert_trading(self.merchant.identity.center,g['scope'])
        return canonical([scene,g['scope'],g['project'],binding['record']])
    @staticmethod
    def _fetch(target,body,maximum):
        req=urllib.request.Request('https://api.weixin.qq.com'+target,data=canonical(body),method='POST',headers={'Content-Type':'application/json'})
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
            with opener.open(req,timeout=5) as response:
                if response.status!=200:raise ValueError()
                raw=response.read(maximum+1)
            if len(raw)>maximum:raise ValueError()
            return raw
        except Exception:
            # urllib exception text can contain access_token. Never chain it.
            raise CollectionCodeUnknown('OFFICIAL_COLLECTION_CODE_UNAVAILABLE') from None
    def _access(self):
        now=self.merchant.identity.center.now()
        if self._cached_token is not None and now<self._token_expires:return self._cached_token
        provider=self.gateway.provider
        raw=self._fetch('/cgi-bin/stable_token',dict(grant_type='client_credential',appid=provider.appid,secret=provider._secret,force_refresh=False),16384)
        try:
            value=_json(raw);token=value['access_token'];expires=value['expires_in']
            if (type(token) is not str or not re.fullmatch('[A-Za-z0-9_-]{16,2048}',token)
                    or type(expires) is not int or not 120<expires<=86400 or value.get('errcode',0)!=0):raise ValueError()
        except Exception:raise CollectionCodeUnknown('OFFICIAL_COLLECTION_CODE_UNAVAILABLE') from None
        self._cached_token=token;self._token_expires=now+expires-120
        return token
    def read(self,token,scene,workspace):
        before=self._authorize(token,scene,workspace)
        with self.merchant.identity.center.tx():
            self.merchant.identity.center.limit('collection-code:'+self.merchant.identity.center.idx(token),5,60)
        access=self._access()
        if self._authorize(token,scene,workspace)!=before:raise PermissionError('COLLECTION_AUTHORITY_CHANGED')
        raw=self._fetch('/wxa/getwxacodeunlimit?access_token='+access,
            dict(scene=scene,page='pages/checkout/index',check_path=True,env_version='release',width=1280),MAX_IMAGE)
        if self._authorize(token,scene,workspace)!=before:raise PermissionError('COLLECTION_AUTHORITY_CHANGED')
        mime='image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else None
        if mime is None or not 32<=len(raw)<=MAX_IMAGE:
            self._cached_token=None
            raise CollectionCodeUnknown('OFFICIAL_COLLECTION_CODE_UNAVAILABLE')
        with self.merchant.identity.center.tx():
            self.merchant.identity.center.audit('',self.merchant.identity.center.session(token),'COLLECTION_CODE_READ',hashlib.sha256(raw).hexdigest())
        return dict(kind='RELEASE_MINI_COLLECTION_CODE',scene=scene,page='pages/checkout/index',mime=mime,
            content_base64=base64.b64encode(raw).decode(),sha256=hashlib.sha256(raw).hexdigest(),payment_completed=False)
