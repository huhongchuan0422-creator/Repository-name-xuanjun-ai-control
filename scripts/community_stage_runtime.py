"""One offline composition for Phase1/2. Reuses existing stores and state machines.

Server-owned Principal-to-store bindings are mandatory. No WeChat authentication,
provider callbacks, settlement or production entitlement grants are implemented.
"""
import time
from scripts.community_saas_phase2 import Principal
from scripts.community_merchant_contract import scope
from scripts.community_demo_api import DemoService
from scripts.community_order_store import state, simulated_transition
from scripts.community_storefront_snapshot import storefront_snapshot
from scripts.community_ad_contract import AMOUNT, SUCCESS
from scripts.community_local_admin import dispatch_local_admin
from scripts.community_ad_store import metric_report


class StageRuntime:
    def __init__(self, demo, saas, bindings, clock=None):
        if type(bindings) is not dict or not bindings:
            raise ValueError('SERVER_BINDINGS_REQUIRED')
        self.bindings = {}
        for principal, identity in bindings.items():
            if type(principal) is not Principal:
                raise PermissionError('EXACT_PRINCIPAL_REQUIRED')
            scope(identity)
            if principal.tenant_id != identity['tenant_id']:
                raise PermissionError('TENANT_BINDING_MISMATCH')
            self.bindings[principal] = dict(identity)
        self.demo, self.saas = demo, saas
        self.clock = clock or (lambda: int(time.time()))

    def dispatch(self, principal, operation, params, ignored_client_time):
        if type(principal) is not Principal or principal not in self.bindings:
            raise PermissionError('REGISTERED_PRINCIPAL_REQUIRED')
        if type(operation) is not str or type(params) is not dict:
            raise ValueError('INVALID_REQUEST')
        now = self.clock()
        if type(now) is not int or not 0 <= now <= 253402300799:
            raise ValueError('INVALID_SERVER_CLOCK')
        if not operation.startswith('community.'):
            return self.saas.dispatch(principal, operation, params, now)
        identity = self.bindings[principal]
        self.demo.now = now
        name = operation[len('community.'):]
        fields = {
            'storefront': set(), 'qr': {'context'},
            'checkout': {'context', 'token', 'reference', 'amount_minor'},
            'receipt': {'reference'}, 'orders': set(), 'summary': set(),
            'orders_page': {'limit','after_id','status'},
            'orders_export': {'limit','after_id','status'},
            'merchant_settings': set(), 'order_detail': {'reference'},
            'refund_record': {'reference', 'event_id', 'amount_minor'},
            'refund_preview': {'reference'}, 'split_preview': {'reference', 'shares_bps'},
            'reconciliation': set(), 'ads': set(), 'ads_page': {'limit','after_id'},
            'ad_report': {'starts_at', 'ends_at', 'limit', 'after_id'},
            'profile': {'record', 'expected_version'}, 'item': {'item'},
            'ad_create': {'record'}, 'ad_state': {'campaign_id', 'state', 'expected_version'},
            'ad_review': {'campaign_id', 'approved', 'expected_version'},
        }
        if name not in fields or set(params) != fields[name]:
            raise ValueError('INVALID_COMMUNITY_FIELDS')
        public = {'storefront', 'qr', 'checkout', 'receipt'}
        permissions={
            'orders':{'STORE_STAFF','MERCHANT_ADMIN','FINANCE_APPROVER','PLATFORM_OWNER'},
            'summary':{'STORE_STAFF','MERCHANT_ADMIN','FINANCE_APPROVER','PLATFORM_OWNER'},
            'orders_page':{'STORE_STAFF','MERCHANT_ADMIN','FINANCE_APPROVER','PLATFORM_OWNER'},
            'order_detail':{'STORE_STAFF','MERCHANT_ADMIN','FINANCE_APPROVER','PLATFORM_OWNER'},
            'orders_export':{'MERCHANT_ADMIN','FINANCE_APPROVER','PLATFORM_OWNER'},
            'ads':{'MERCHANT_ADMIN','PLATFORM_REVIEWER','PLATFORM_OWNER'},
            'ads_page':{'MERCHANT_ADMIN','PLATFORM_REVIEWER','PLATFORM_OWNER'},
            'ad_report':{'MERCHANT_ADMIN','PLATFORM_REVIEWER','PLATFORM_OWNER'},
            'ad_review':{'PLATFORM_REVIEWER','PLATFORM_OWNER'},
            'refund_preview':{'MERCHANT_ADMIN','FINANCE_APPROVER','PLATFORM_OWNER'},
            'split_preview':{'MERCHANT_ADMIN','FINANCE_APPROVER','PLATFORM_OWNER'},
            'reconciliation':{'MERCHANT_ADMIN','FINANCE_APPROVER','PLATFORM_OWNER'},
        }
        if name not in public and principal.role not in permissions.get(name,{'MERCHANT_ADMIN','PLATFORM_OWNER'}):
            raise PermissionError('ADMIN_ROLE_REQUIRED')
        if name == 'summary':
            from scripts.community_workbench import order_summary
            return order_summary(self.demo.db,identity)
        if name == 'orders':
            from scripts.community_workbench import orders_page
            return orders_page(self.demo.db,identity,50,'','ALL')
        if name == 'order_detail':
            from scripts.community_workbench import order_detail
            return order_detail(self.demo.db,self.demo.refund_db,identity,**params)
        if name in ('orders_page','orders_export'):
            from scripts.community_workbench import orders_page, orders_export
            return (orders_export if name=='orders_export' else orders_page)(self.demo.db,identity,**params)
        if name == 'merchant_settings':
            from scripts.community_workbench import merchant_settings
            return merchant_settings(self.demo.merchant_db,identity)
        if name == 'ads_page':
            from scripts.community_ad_store import list_campaigns
            return list_campaigns(self.demo.ad_db,identity,**params)
        if name == 'ad_report':
            return metric_report(self.demo.ad_db, identity, **params)
        if name == 'receipt':
            order = state(self.demo.db, identity, params['reference'])
            snapshot = storefront_snapshot(self.demo.merchant_db, self.demo.ad_db, identity, now)
            # State is read from the original durable order store, never a body field.
            from scripts.community_order_provider_projection import provider_evidence
            verified = provider_evidence(self.demo.db, identity, params['reference'])
            paid = order['state'] == 'SUCCESS'
            return {'order': dict(order, reference=params['reference']),
                    'payment_state': ('PROVIDER_' + order['state']) if verified else ('MOCK_PAID_SIMULATED' if paid else 'MOCK_' + order['state']),
                    'ads': {AMOUNT: None, SUCCESS: snapshot['ads'][SUCCESS] if paid else None},
                    'simulation_only': verified is None, 'provider_order_verified': verified is not None,
                    'provider_payment_verified': verified is not None and order['state'] in ('SUCCESS','REFUNDED'),
                    'provider_settlement_verified': False,
                    'financial_receipt_issued': False, 'finance_effect': 'NONE'}
        admin_routes = {'profile': '/demo/admin/profile', 'item': '/demo/admin/item',
                        'ad_create': '/demo/admin/campaign/create',
                        'ad_state': '/demo/admin/campaign/state',
                        'ad_review': '/demo/admin/campaign/review'}
        if name in admin_routes:
            required = 'PLATFORM_OWNER' if name == 'ad_review' else 'MERCHANT_ADMIN'
            allowed = {'PLATFORM_OWNER','PLATFORM_REVIEWER'} if name=='ad_review' else {'MERCHANT_ADMIN'}
            if principal.role not in allowed:
                raise PermissionError('ROLE_REQUIRED')
            policy = self.demo.admin_policy
            if policy is None:
                raise PermissionError('ADMIN_DISABLED')
            if required == 'MERCHANT_ADMIN' and identity != policy.merchant_scope:
                raise PermissionError('MERCHANT_SCOPE_DENIED')
            token = policy.platform_token if required == 'PLATFORM_OWNER' else policy.merchant_token
            return dispatch_local_admin(self.demo, admin_routes[name],
                                        {'identity': identity, 'operation': params}, token)
        paths = {'storefront': '/demo/storefront', 'qr': '/demo/qr/create',
                 'checkout': '/demo/qr/checkout', 'orders': '/demo/orders/list',
                 'summary': '/demo/orders/summary', 'refund_record': '/demo/refunds/record-preview',
                 'refund_preview': '/demo/refunds/preview', 'split_preview': '/demo/splits/preview',
                 'reconciliation': '/demo/reconciliation/preview', 'ads': '/demo/ads/list'}
        return self.demo.dispatch('POST', paths[name], dict(identity, **params))

    def simulate_from_operator(self, principal, reference, event_id, target, transaction_id):
        """Python-only test operator hook; intentionally absent from dispatch/HTTP."""
        if (type(principal) is not Principal or principal not in self.bindings
                or principal.role != 'PLATFORM_OWNER'):
            raise PermissionError('PLATFORM_OPERATOR_REQUIRED')
        identity = self.bindings[principal]
        from scripts.community_order_provider_projection import provider_evidence
        if provider_evidence(self.demo.db, identity, reference) is not None:
            raise PermissionError('REAL_ORDER_SIMULATION_DENIED')
        order = state(self.demo.db, identity, reference)
        return simulated_transition(self.demo.db, identity, reference, event_id, target,
            {'simulation_only': True, 'scope': identity, 'reference': reference,
             'amount_minor': order['amount_minor'], 'provider_transaction_id': transaction_id})
