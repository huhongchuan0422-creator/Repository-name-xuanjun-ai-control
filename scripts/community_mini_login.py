"""Mini Program login adapter. Reuses hosting Identity authority, no new user DB.

Protocol: https://developers.weixin.qq.com/miniprogram/dev/OpenApiDoc/user-login/code2Session.html
AppSecret and session_key never enter client replies or exception messages.
"""
import base64
import hashlib
import json
import re
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from scripts.community_saas_phase2 import Principal

APPID = re.compile(r'wx[0-9a-fA-F]{16}\Z')
CODE = re.compile(r'[A-Za-z0-9_-]{1,256}\Z')
SCENE = re.compile(r'[A-Za-z0-9_-]{1,32}\Z')


class LoginUnavailable(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class WechatCodeClient:
    def __init__(self, appid, app_secret):
        if type(appid) is not str or not APPID.fullmatch(appid):
            raise ValueError('INVALID_APPID')
        if type(app_secret) is not str or not re.fullmatch('[A-Za-z0-9]{16,128}', app_secret):
            raise ValueError('APP_SECRET_REQUIRED')
        self.appid, self._secret = appid, app_secret

    def __repr__(self):
        return '<WechatCodeClient credentials redacted>'

    def exchange(self, code):
        if type(code) is not str or not CODE.fullmatch(code):
            raise ValueError('INVALID_LOGIN_CODE')
        query = urllib.parse.urlencode({'appid':self.appid, 'secret':self._secret,
                                      'js_code':code, 'grant_type':'authorization_code'})
        request = urllib.request.Request('https://api.weixin.qq.com/sns/jscode2session?'+query,
                                         headers={'Accept':'application/json'})
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
            with opener.open(request, timeout=5) as response:
                if response.status != 200:
                    raise LoginUnavailable('PROVIDER_LOGIN_UNKNOWN')
                raw = response.read(16385)
            if len(raw) > 16384:
                raise ValueError('RESPONSE_TOO_LARGE')
            def pairs(values):
                result = {}
                for key,value in values:
                    if key in result: raise ValueError('DUPLICATE_JSON_KEY')
                    result[key] = value
                return result
            data = json.loads(raw, object_pairs_hook=pairs)
            if type(data) is not dict or data.get('errcode',0) != 0:
                raise ValueError('PROVIDER_REJECTED')
            openid, key = data.get('openid'), data.get('session_key')
            if type(openid) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,128}', openid):
                raise ValueError('INVALID_OPENID')
            if type(key) is not str or len(base64.b64decode(key,validate=True)) != 16:
                raise ValueError('INVALID_SESSION_KEY')
            # Do not return/store provider session_key: no user-data decryption is used.
            return {'appid':self.appid, 'openid':openid}
        except Exception:
            # urllib errors include credential-bearing URLs. Never chain them.
            raise LoginUnavailable('PROVIDER_LOGIN_UNKNOWN_OR_REJECTED') from None


class IdentityPort(ABC):
    """Implement against the existing persistent Identity/CRM, not a second store.

    reserve_code must atomically consume digest before provider IO. An uncertain
    result remains consumed after restart. issue_session associates only an
    existing customer, with default CUSTOMER role; no self-registration as admin.
    resolve must check session expiry/revocation, current tenant/project RBAC and
    server-owned scene-to-store binding on EVERY request. Return a Principal
    already registered in StageRuntime; never infer role/tenant from client body.
    """
    @abstractmethod
    def reserve_code(self, appid, code_sha256, now): pass
    @abstractmethod
    def issue_session(self, attempt, appid, openid, now): pass
    @abstractmethod
    def abandon_attempt(self, attempt, reason, now): pass
    @abstractmethod
    def resolve(self, session_token, scene, now): pass
    @abstractmethod
    def revoke(self, session_token, now): pass


class MiniGateway:
    def __init__(self, runtime, identity, provider):
        if not isinstance(identity,IdentityPort) or not isinstance(provider,WechatCodeClient):
            raise ValueError('TRUSTED_PROVIDER_AND_IDENTITY_REQUIRED')
        self.runtime, self.identity, self.provider = runtime, identity, provider

    def login(self, body):
        if type(body) is not dict or set(body) != {'code'}:
            raise ValueError('INVALID_LOGIN_FIELDS')
        code = body['code']
        if type(code) is not str or not CODE.fullmatch(code):
            raise ValueError('INVALID_LOGIN_CODE')
        now = self.runtime.clock()
        attempt = self.identity.reserve_code(self.provider.appid, hashlib.sha256(code.encode()).hexdigest(), now)
        try:
            result = self.provider.exchange(code)
            if (type(result) is not dict or set(result) != {'appid','openid'}
                    or result['appid'] != self.provider.appid):
                raise LoginUnavailable('PROVIDER_BINDING_MISMATCH')
            issued = self.identity.issue_session(attempt,result['appid'],result['openid'],now)
            if (type(issued) is not dict or set(issued) != {'session_token','expires_at'}
                    or type(issued['session_token']) is not str or not re.fullmatch('[A-Za-z0-9_-]{32,256}',issued['session_token'])
                    or type(issued['expires_at']) is not int or not now < issued['expires_at'] <= now+86400):
                raise LoginUnavailable('IDENTITY_SESSION_INVALID')
            return dict(issued, provider='WECHAT_MINIPROGRAM', payment_enabled=False)
        except Exception:
            try:self.identity.abandon_attempt(attempt,'LOGIN_RESULT_UNKNOWN_OR_REJECTED',now)
            except Exception:pass
            raise LoginUnavailable('LOGIN_RESULT_UNKNOWN_OR_REJECTED') from None

    def dispatch(self, token, body):
        if (type(token) is not str or not re.fullmatch('[A-Za-z0-9_-]{32,256}',token)
                or type(body) is not dict or set(body) != {'scene','operation','params'}):
            raise PermissionError('SESSION_REQUIRED')
        scene = body['scene']
        if type(scene) is not str or not SCENE.fullmatch(scene):
            raise ValueError('INVALID_SCENE')
        principal = self.identity.resolve(token,scene,self.runtime.clock())
        if type(principal) is not Principal:
            raise PermissionError('TRUSTED_PRINCIPAL_REQUIRED')
        # Mini customer session does not turn into merchant/platform admin.
        if principal.role != 'CUSTOMER':
            raise PermissionError('CONSUMER_SESSION_REQUIRED')
        return self.runtime.dispatch(principal,body['operation'],body['params'],None)

    def logout(self, token):
        if type(token) is not str or not re.fullmatch('[A-Za-z0-9_-]{32,256}',token):
            raise PermissionError('SESSION_REQUIRED')
        self.identity.revoke(token,self.runtime.clock())
        return {'logged_out':True}
