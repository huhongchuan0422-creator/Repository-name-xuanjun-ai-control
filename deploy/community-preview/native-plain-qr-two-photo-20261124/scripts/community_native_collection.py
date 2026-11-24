"""Native owner official mini-entry code over original signed merchant approval.
No MiniPayments construction, product admission, grant, order or payment flags.
"""
import base64,hashlib,json,re
from contextlib import nullcontext
from scripts.community_collection_code import CollectionCodes,CollectionCodeUnknown,MAX_IMAGE
from scripts.community_mini_login import WechatCodeClient
from scripts.pr122_customer_core import canonical

class NativeOfficialCodeRejected(CollectionCodeUnknown):
    def __init__(self,code):
        super().__init__('OFFICIAL_COLLECTION_CODE_REJECTED')
        self.official_error_code=code if type(code) is int and -2147483648<=code<=2147483647 else None

class NativeCollectionCodes(CollectionCodes):
    def __init__(self,gateway,registry):
        from scripts.native_workbench_runtime import Registry
        from scripts.community_mini_merchant import MiniMerchant
        if (type(registry) is not Registry or registry.identity is not gateway.identity
                or type(gateway.provider) is not WechatCodeClient
                or gateway.provider.appid!=gateway.identity.appid):
            raise PermissionError('ORIGINAL_NATIVE_COLLECTION_REQUIRED')
        self.gateway,self.registry=gateway,registry
        self.merchant=MiniMerchant(gateway.identity,registry.service,registry.operations)
        self._cached_token=None;self._token_expires=0

    @staticmethod
    def _fetch(target,body,maximum):
        raw=CollectionCodes._fetch(target,body,maximum)
        if raw.lstrip().startswith(b'{'):
            try:code=json.loads(raw).get('errcode')
            except (ValueError,UnicodeError,AttributeError):code=None
            if type(code) is int and code!=0:raise NativeOfficialCodeRejected(code)
        return raw

    def eligible(self,opening):
        try:return self.registry.current_opening(opening.owner,opening.scene)==opening
        except (PermissionError,ValueError):return False

    def read_bound(self,opening,reauthorize):
        """Ordinary, printable same-store HTTPS QR; no provider payment IO."""
        from scripts.native_leaves import Opening
        from scripts.community_fixed_qr import fixed_url,locator_for_scope,issue_png,decode_png
        host=getattr(self,'fixed_cashier',None)
        if (type(opening) is not Opening or not callable(reauthorize) or host is None
                or host.native_registry is not self.registry):
            raise PermissionError('ORIGINAL_NATIVE_CASHIER_REQUIRED')
        owner,csrf=reauthorize()
        if owner!=opening.owner or not self.eligible(opening):
            raise PermissionError('NATIVE_COLLECTION_OWNER_REQUIRED')
        observer=self.registry.service.wechat_applyment.observer
        binding=observer.ensure_collection_binding(opening.application)
        def current():
            if reauthorize()!=(owner,csrf) or not self.eligible(opening):
                raise PermissionError('NATIVE_COLLECTION_OPENING_CHANGED')
            with (nullcontext() if host.center.db.in_transaction else host.center.tx()):
                now=observer.collection_binding(opening.application)
            if (now!=binding or binding['owner']!=owner or binding['application']!=opening.application
                    or binding['platform_revision']!=opening.revision):
                raise PermissionError('NATIVE_COLLECTION_APPROVAL_CHANGED')
        current()
        with host.center.tx():host.center.limit('native-cashier-code:'+owner,5,60)
        locator=locator_for_scope(opening.scope());url=fixed_url(host.https_origin,locator)
        if host.entry_scope(locator)!=opening.scope():raise PermissionError('NATIVE_CASHIER_SCOPE_CHANGED')
        issued=issue_png(url);current()
        if issued['download_state']!='READY' or decode_png(issued['png_data'])!=url:
            raise CollectionCodeUnknown('SELF_HOSTED_CASHIER_QR_UNAVAILABLE')
        current();raw=base64.b64decode(issued['png_data'].split(',',1)[1],validate=True)
        return dict(kind='SELF_HOSTED_CASHIER_ENTRY_QR',scene=opening.scene,locator=locator,
                    fixed_url=url,mime='image/png',content_base64=base64.b64encode(raw).decode(),
                    sha256=hashlib.sha256(raw).hexdigest(),payment_completed=False,payable=False,
                    approval_verified=True,payment_product_admitted=False)

    def read_mini_bound(self,opening,reauthorize):
        from scripts.native_leaves import Opening
        if type(opening) is not Opening or not callable(reauthorize):
            raise PermissionError('ORIGINAL_NATIVE_COLLECTION_REQUIRED')
        owner,csrf=reauthorize()
        if owner!=opening.owner or not self.eligible(opening):
            raise PermissionError('NATIVE_COLLECTION_OWNER_REQUIRED')
        c=self.gateway.identity.center
        with c.tx():c.limit('native-collection-code:'+owner,5,60)
        observer=self.registry.service.wechat_applyment.observer
        binding=observer.ensure_collection_binding(opening.application)
        def current():
            if reauthorize()!=(owner,csrf) or not self.eligible(opening):
                raise PermissionError('NATIVE_COLLECTION_OPENING_CHANGED')
            with (nullcontext() if c.db.in_transaction else c.tx()):now=observer.collection_binding(opening.application)
            if (now!=binding or binding['owner']!=owner
                    or binding['application']!=opening.application
                    or binding['platform_revision']!=opening.revision):
                raise PermissionError('NATIVE_COLLECTION_APPROVAL_CHANGED')
        current();access=self._access();current()
        raw=self._fetch('/wxa/getwxacodeunlimit?access_token='+access,
            dict(scene=opening.scene,page='pages/checkout/index',check_path=True,env_version='release',width=1280),MAX_IMAGE)
        current()
        mime='image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else None
        if mime is None or not 32<=len(raw)<=MAX_IMAGE:
            self._cached_token=None
            try:code=json.loads(raw).get('errcode')
            except (ValueError,UnicodeError,AttributeError):code=None
            if type(code) is int:raise NativeOfficialCodeRejected(code)
            raise CollectionCodeUnknown('OFFICIAL_COLLECTION_CODE_UNAVAILABLE')
        with c.tx():
            current();c.audit(opening.application,owner,'COLLECTION_CODE_READ',hashlib.sha256(raw).hexdigest())
        return dict(kind='RELEASE_MINI_COLLECTION_CODE',scene=opening.scene,page='pages/checkout/index',mime=mime,
            content_base64=base64.b64encode(raw).decode(),sha256=hashlib.sha256(raw).hexdigest(),payment_completed=False)

    def checkout(self,token,scene,operation,params):
        # Existing authenticated platform consumers may read this exact signed
        # store entry; never synthesize a legacy Principal or grant for it.
        identity=self.gateway.identity;identity.applicant_context(token)
        if type(params) is not dict:raise ValueError('INVALID_NATIVE_CHECKOUT_FIELDS')
        matches=[]
        for application,owner in self.registry.service.center.db.execute(
                "SELECT project,user_id FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING' AND active=1").fetchall():
            item=self.registry.get_application(application,owner)
            if item and item['scene']==scene:matches.append(item)
        if len(matches)!=1:raise PermissionError('NATIVE_CHECKOUT_STORE_REQUIRED')
        item=matches[0];opening=self.registry.current_opening(item['owner'],scene)
        if opening is None:raise PermissionError('NATIVE_CHECKOUT_STORE_REQUIRED')
        allowed=False
        for original,b in identity.scenes.items():
            if b['project']!=item['project']:continue
            try:_,project,principal=identity._resolve(token,original)
            except PermissionError:continue
            row=identity.center.db.execute('SELECT tenant FROM projects WHERE id=?',(project,)).fetchone()
            original_scope=identity.runtime.bindings.get(principal)
            if row and original_scope and row['tenant']==principal.tenant_id==original_scope['tenant_id']:allowed=True;break
        if not allowed:raise PermissionError('NATIVE_CHECKOUT_CONSUMER_SCOPE_REQUIRED')
        if operation=='commerce.products' and not set(params)-{'after_id'}:
            after=params.get('after_id','')
            if type(after) is not str or after and not re.fullmatch('[A-Za-z0-9_-]{1,64}',after):
                raise ValueError('INVALID_NATIVE_CHECKOUT_FIELDS')
            # No priced/purchasable commerce products are admitted for this
            # native entry. This does not hide or change merchant catalog rows.
            result=dict(products=[],has_more=False,next_cursor=None,payment_enabled=False,
                        availability='NO_PAYMENT_PRODUCT_ADMISSION')
        elif operation=='community.storefront' and params=={}:
            from scripts.community_ad_store import choose
            from scripts.community_ad_contract import AMOUNT,SUCCESS
            scope=opening.scope();d=self.registry.operations.runtime.demo
            row=d.merchant_db.execute('SELECT name,description FROM merchant_profiles WHERE tenant_id=? AND merchant_id=? AND store_id=?',tuple(scope[k] for k in ('tenant_id','merchant_id','store_id'))).fetchone()
            if row is None:raise PermissionError('NATIVE_CHECKOUT_STORE_REQUIRED')
            ad=choose(d.ad_db,scope,AMOUNT,identity.center.now())
            result=dict(merchant=dict(name=row[0],description=row[1]),products=[],ads={AMOUNT:ad,SUCCESS:None},
                        payment_enabled=False,payment_started=False,provider_settlement_verified=False,escape_text_required=True,
                        collection_entry=dict(scene=scene,approval_verified=True,payment_product_admitted=False))
        else:
            # Product admission remains the original protected policy authority.
            raise PermissionError('PAYMENT_PRODUCT_ADMISSION_REQUIRED')
        if self.registry.current_opening(item['owner'],scene)!=opening:
            raise PermissionError('NATIVE_CHECKOUT_OPENING_CHANGED')
        identity.applicant_context(token)
        return result
