"""Fixed-code cashier host composition: original services only, fail closed.

Assembles the frozen candidate cashier over the REAL runtime dependencies
(Center, Commerce, CenterOperations grants, CenterIdentity scenes, protected
MiniPayments merchant bindings and the protected PartnerPrepay/PartnerOrderReader)
and exposes the two entry surfaces the UK main handler mounts:

  * workbench side: authorize_workspace / qr_view / qr_download — the printed
    locator is derived from the caller's own admitted store scope, so a normal
    merchant structurally cannot issue another store's code;
  * payer side: Wire.amount / reserve / prepare / signed result readback.

Nothing here opens a socket, reads a secret into the caller's context, or
fabricates provider qualification. Missing on-site qualification stays an
explicit status, never a payable-looking success.
"""
import re

from scripts.pr122_customer_core import Center
from scripts.community_commerce import Commerce
from scripts.community_center_operations import CenterOperations
from scripts.community_mini_center_identity import CenterIdentity
from scripts.community_mini_payments import MiniPayments
from scripts.community_wechat_sp_prepay import PartnerPrepay
from scripts.community_fixed_cashier_core import Cashier, ExistingStore, OfficialPayer
from scripts.community_fixed_cashier_wire import Wire, AdSettings
from scripts.community_merchant_store import profile as store_profile
from scripts.community_fixed_qr import (fixed_url, issue_png, decode_png,
                                        locator_for_scope, matches_locator)

PENDING = 'PENDING_FIELD_VERIFICATION'


class FixedCashierHost:
    def __init__(self, *, center, commerce, operations, identity, payments, prepay,
                 https_origin, ad_settings=None, payer_authority=None,
                 qualification=None, clock=None, freeze_original_split=None):
        if (type(center) is not Center or type(commerce) is not Commerce
                or type(operations) is not CenterOperations or type(identity) is not CenterIdentity
                or (payments is not None and type(payments) is not MiniPayments)
                or (prepay is not None and type(prepay) is not PartnerPrepay)):
            raise ValueError('ORIGINAL_RUNTIME_SERVICES_REQUIRED')
        if (commerce.center is not center or commerce.operations is not operations
                or commerce.identity is not identity
                or (payments is not None and (payments.prepay is not prepay
                    or prepay.center is not center or payments.identity is not identity))
                or identity.center is not center or operations.runtime is not identity.runtime):
            raise ValueError('SAME_ORIGINAL_CENTER_COMPOSITION_REQUIRED')
        if payments is not None and payments.merchant_mode is not True:
            raise PermissionError('PROTECTED_MERCHANT_PAYMENT_BINDINGS_REQUIRED')
        if prepay is not None and not callable(prepay.reader.read_order):
            raise ValueError('ORIGINAL_VERIFIED_ORDER_READER_REQUIRED')
        self.center, self.commerce, self.operations = center, commerce, operations
        self.identity, self.payments, self.prepay = identity, payments, prepay
        self.runtime = identity.runtime
        # https_origin is a host configuration fact; validate by rebuilding it.
        if re.fullmatch(r'https://[A-Za-z0-9.-]{1,253}', https_origin or '') is None:
            raise ValueError('APPROVED_HTTPS_ORIGIN_REQUIRED')
        self.https_origin = https_origin
        self._payer_authority = payer_authority
        self._qualification = qualification if callable(qualification) else (lambda store: {})
        self._ad_settings = ad_settings if callable(ad_settings) else self.original_ad_settings
        # Locator uniqueness across admitted scenes: two stores can never share
        # one fixed code. Validated once at composition.
        seen = {}
        for scene, merchant in (self.payments.merchants.items() if self.payments else []):
            locator = locator_for_scope(merchant['scope'])
            if locator in seen:
                raise PermissionError('FIXED_LOCATOR_COLLISION')
            seen[locator] = scene
            if merchant['record']['sp_appid'] != identity.appid:
                raise PermissionError('MINI_APPID_MISMATCH')
        self._locators = seen
        self.cashier = Cashier(commerce, prepay, store_authority=self.store_authority,
                               payer_authority=self.payer_authority,
                               freeze_original_split=freeze_original_split) if payments is not None else None
        self.wire = Wire(self.cashier, self._ad_settings) if self.cashier else None

    def _original_ads(self, identity):
        # Original active/approved/time-bounded campaigns only; no publishing,
        # payment admission, metrics, order or provider operations.
        from scripts.community_ad_store import choose
        from scripts.community_ad_contract import AMOUNT, SUCCESS
        import sqlite3
        ads = {}
        for slot in (AMOUNT, SUCCESS):
            try:
                ads[slot] = choose(self.runtime.demo.ad_db, identity, slot, self.center.now())
            except sqlite3.DatabaseError:
                ads[slot] = None
        return ads

    def original_ad_settings(self, store):
        from scripts.community_fixed_cashier_wire import AdSettings
        from scripts.community_ad_contract import AMOUNT, SUCCESS
        ads = self._original_ads(store.scope())
        return AdSettings(store, 'OWN' if ads[AMOUNT] else 'NONE',
                          'OWN' if ads[SUCCESS] else 'NONE')

    def ad_preview(self, session, csrf, workspace):
        from scripts.community_ad_contract import AMOUNT, SUCCESS
        grant = self.authorize_workspace(session, csrf, workspace)
        identity = dict(grant['scope'])
        ads = self._original_ads(identity)
        return dict(identity, display_context='AD_PREVIEW_ONLY',
                    preview_label='广告位预览 · 非已付款', payable=False,
                    payment_started=False, payment_success_verified=False,
                    finance_status='UNCONFIRMED',
                    amount_ad=ads[AMOUNT], success_ad_preview=ads[SUCCESS],
                    amount_state='AVAILABLE' if ads[AMOUNT] else 'NO_ACTIVE_APPROVED_MATERIAL',
                    success_state='AVAILABLE' if ads[SUCCESS] else 'NO_ACTIVE_APPROVED_MATERIAL')

    def preview_scope(self, locator):
        # Re-read original grants per use; preview creates no payment admission.
        for grant in self.operations.grants.values():
            if (grant['role'] in ('MERCHANT_ADMIN', 'STORE_STAFF')
                    and locator_for_scope(grant['scope']) == locator
                    and self.runtime.bindings.get(grant['principal']) == grant['scope']):
                return dict(grant['scope'])
        raise PermissionError('FIXED_STORE_NOT_ADMITTED')

    def entry_scope(self, locator):
        if locator in self._locators:
            return self.store_authority(locator).scope()
        return self.preview_scope(locator)

    # ----- store/payer authority over existing protected facts -----

    def store_authority(self, locator):
        scene = self._locators.get(locator) if type(locator) is str else None
        if scene is None:
            raise PermissionError('FIXED_STORE_NOT_ADMITTED')
        self.payments._refresh_merchant(scene)
        merchant = self.payments.merchants.get(scene)
        guard = getattr(self.payments, 'activation_guard', None)
        if guard is not None and (merchant is None or guard(scene) != merchant['record']):
            raise PermissionError('PAYMENT_ACTIVATION_CHANGED')
        binding = self.identity.scenes.get(scene)
        if merchant is None or binding is None:
            raise PermissionError('FIXED_STORE_NOT_ADMITTED')
        store_scope = merchant['scope']
        if (self.runtime.bindings.get(binding['principal']) != store_scope
                or binding['project'] != merchant['project']
                or not matches_locator(self.https_origin, locator, store_scope)):
            raise PermissionError('FIXED_STORE_BINDING_CHANGED')
        record = merchant['record']
        return ExistingStore(locator=locator, project=merchant['project'],
                             tenant_id=store_scope['tenant_id'], merchant_id=store_scope['merchant_id'],
                             store_id=store_scope['store_id'], sp_mchid=self.prepay.reader._mchid,
                             sp_appid=record['sp_appid'], sub_mchid=record['sub_mchid'],
                             description=record['description'], notify_url=record['notify_url'],
                             profit_sharing=record['profit_sharing'])

    def payer_authority(self, session, csrf, store):
        """Original protected WeChat subject for this exact session, or host override.

        Production H5 official-account OAuth stays an injected host authority
        (PE field verification); without it the real mini session binding is
        used and nothing is fabricated.
        """
        if self._payer_authority is not None:
            return self._payer_authority(session, csrf, store)
        uid = self.center.session(session, csrf)
        key = self.center.idx('wechat-session:' + session)
        row = self.center.db.execute(
            "SELECT payload FROM links WHERE channel='WECHAT_MINI_SESSION' AND subject_idx=?"
            " AND user_id=? AND project=? AND active=1", (key, uid, store.project)).fetchone()
        if row is None:
            raise PermissionError('CURRENT_WECHAT_PAYER_REQUIRED')
        meta = __import__('json').loads(self.center.decrypt(row[0], 'wechat-mini-session'))
        subject, openid = meta.get('subject_idx'), meta.get('openid')
        if (type(subject) is not str or not subject or type(openid) is not str
                or not 1 <= len(openid) <= 128):
            raise PermissionError('CURRENT_WECHAT_PAYER_REQUIRED')
        if self.center.db.execute(
                "SELECT 1 FROM links WHERE channel='WECHAT_MINI' AND subject_idx=?"
                " AND user_id=? AND project=? AND active=1", (subject, uid, store.project)).fetchone() is None:
            raise PermissionError('PROVIDER_LINK_REVOKED')
        return OfficialPayer(uid=uid, appid=store.sp_appid, sp_openid=openid)

    # ----- workbench side: own-store fixed code only -----

    def authorize_workspace(self, session, csrf, workspace):
        uid = self.center.session(session, csrf)
        grant = self.operations.grants.get(workspace) if type(workspace) is str else None
        if grant is None or grant['user_id'] != uid:
            raise PermissionError('MERCHANT_WORKSPACE_REQUIRED')
        if grant['role'] not in ('MERCHANT_ADMIN', 'STORE_STAFF'):
            raise PermissionError('MERCHANT_ROLE_REQUIRED')
        project, _, _ = self.center.project(uid, grant['project'], grant['project_roles'])
        principal = grant['principal']
        if (principal not in self.runtime.bindings
                or self.runtime.bindings[principal] != grant['scope']
                or project['tenant'] != grant['tenant']):
            raise PermissionError('MERCHANT_GRANT_CHANGED')
        if grant.get('onboarding_required'):
            from scripts.community_merchant_opening import authorize_workspace as opening
            opening(self.operations.onboarding, self.operations, workspace, uid)
        return grant

    def _view(self, grant):
        store_scope = grant['scope']
        locator = locator_for_scope(store_scope)
        url = fixed_url(self.https_origin, locator)
        self.entry_scope(locator)
        admitted = locator in self._locators
        name = ''
        if admitted:
            try:
                name = store_profile(self.runtime.demo.merchant_db, store_scope)['name']
            except Exception:
                name = ''
        status = self._qualification(self.store_authority(locator)) if admitted else {}
        official = status.get('official_verified') is True and admitted
        return dict(store_scope, **{'fixed_url': url, 'locator': locator,
                'store_name': name, 'admitted': admitted,
                'availability': 'ADMITTED' if admitted else PENDING,
                'qualification': status or {'applyment': PENDING, 'sub_mchid': PENDING,
                                            'jsapi_directory': PENDING, 'oauth_domain': PENDING},
                'official_code_available': official,
                'preview_only': not official})

    def qr_view(self, session, csrf, workspace):
        return self.qr_download(session, csrf, workspace)

    def qr_download(self, session, csrf, workspace):
        grant = self.authorize_workspace(session, csrf, workspace)
        view = self._view(grant)
        issued = issue_png(view['fixed_url'])
        if issued['download_state'] == 'READY':
            decoded = decode_png(issued['png_data'])
            if decoded != view['fixed_url']:
                # Never hand out a PNG that does not re-decode to this exact URL.
                return dict(view, download_state='ISSUER_UNAVAILABLE', png_data=None, png_sha256=None)
        return dict(view, **issued)

    def amount(self, locator):
        if locator not in self._locators:
            identity = self.preview_scope(locator)
            from scripts.community_ad_contract import AMOUNT
            selected = self._original_ads(identity)[AMOUNT]
            try:
                name = store_profile(self.runtime.demo.merchant_db, identity)['name']
            except (KeyError, ValueError):
                name = ''
            return dict(identity, store_name=name, payable=False, availability=PENDING,
                        amount_mode='OWN' if selected else 'NONE', amount_ad=selected)
        view = self.wire.amount(locator)
        status = self._qualification(self.store_authority(locator))
        ready = status.get('official_verified') is True and callable(self._payer_authority)
        return dict(view, payable=ready, availability='ADMITTED' if ready else PENDING)

    def _web_ready(self, locator):
        if not callable(self._payer_authority):
            raise PermissionError('WEB_PAYER_AUTHORITY_REQUIRED')
        if self._qualification(self.store_authority(locator)).get('official_verified') is not True:
            raise PermissionError('FIELD_PAYMENT_QUALIFICATION_REQUIRED')

    def reserve(self, session, csrf, locator, reference, yuan):
        self._web_ready(locator)
        return self.cashier.reserve(session, csrf, locator, reference, yuan)

    def prepare(self, session, csrf, locator, reference):
        self._web_ready(locator)
        store = self.store_authority(locator)
        jsapi = self.cashier.prepare(session, csrf, locator, reference)
        keys = ('timeStamp', 'nonceStr', 'package', 'signType', 'paySign')
        return dict(store.scope(), reference=reference, flow='WECHAT_IN_PAGE_JSAPI',
                    jsapi=dict(appId=store.sp_appid, **{k: jsapi[k] for k in keys}))

    def result(self, session, csrf, locator, reference):
        return self.wire.result(session, csrf, locator, reference)
