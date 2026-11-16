"""Stage5 offline UI/view models only. Caller must authenticate actor server-side."""
from scripts.community_merchant_contract import scope as check_scope, payment_amount, route, merchant_authorized, platform_authorized
from scripts.community_ad_contract import AMOUNT

def _scope(value):
    check_scope(value)
    return dict(value)

def _text(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 500 or any(ord(c) < 32 for c in value):
        raise ValueError('INVALID_TEXT')
    return value

def _rows(rows):
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError('INVALID_ROWS')
    return rows

# 21: consumer storefront (escaped by frontend renderer)
def storefront_view(identity, profile):
    s = _scope(identity)
    if not isinstance(profile, dict) or profile.get('status') != 'ACTIVE':
        raise ValueError('STOREFRONT_UNAVAILABLE')
    return {'scope': s, 'name': _text(profile.get('name')),
            'description': _text(profile.get('description')), 'escape_required': True}

# 22: tenant/merchant/store-scoped store list
def store_list(identity, rows):
    s = _scope(identity)
    out = []
    for row in _rows(rows):
        if not isinstance(row, dict) or row.get('tenant_id') != s['tenant_id'] or row.get('merchant_id') != s['merchant_id']:
            raise ValueError('CROSS_MERCHANT')
        from scripts.community_merchant_contract import valid_id
        if not valid_id(row.get('store_id')):
            raise ValueError('INVALID_STORE_ID')
        out.append({'store_id': row['store_id'], 'name': _text(row.get('name'))})
    return out

# 23: reject rather than silently ignore cross-scope catalog records
def service_cards(identity, rows):
    s = _scope(identity)
    from scripts.community_merchant_contract import valid_id
    out = []
    for row in _rows(rows):
        if not isinstance(row, dict) or row.get('scope') != s:
            raise ValueError('CROSS_SCOPE_CATALOG')
        if not valid_id(row.get('id')) or type(row.get('active')) is not bool:
            raise ValueError('INVALID_CATALOG_ITEM')
        if row['active']:
            out.append({'id': row['id'], 'name': _text(row.get('name'))})
    return out

# 24: mini-program route model
def mini_route(identity, page):
    return route('mini', page, _scope(identity))

# 25: WeChat official-account H5 route model
def h5_route(identity, page):
    return route('official_h5', page, _scope(identity))

# 26: amount-entry advertisement reserved, no payment initiated
def amount_screen(identity, amount_minor):
    s = _scope(identity)
    checked = payment_amount(amount_minor, 'CNY', 'preview')
    return {'scope': s, 'amount_minor': checked['amount_minor'],
            'ad_slot': AMOUNT, 'provider_payment_started': False}

# 27: pending must not claim success
def pending_screen(identity):
    return {'scope': _scope(identity), 'state': 'PENDING',
            'success_ad_slot': None, 'receipt_verified': False}

# 28: merchant orders view; never trust actor fields from browser
def merchant_orders(actor, identity, orders):
    s = _scope(identity)
    if not merchant_authorized(actor, s, 'VIEW'):
        raise ValueError('ACCESS_DENIED')
    out = []
    from scripts.community_merchant_contract import valid_id
    for row in _rows(orders):
        if not isinstance(row, dict) or row.get('scope') != s or not valid_id(row.get('reference')) or row.get('state') not in ('PENDING','SUCCESS','FAILED','CANCELLED','REFUNDED'):
            raise ValueError('INVALID_ORDER_VIEW')
        out.append({'reference': row['reference'], 'state': row['state']})
    return out

# 29: ads management view, merchant administrator only
def merchant_ads(actor, identity, ads):
    s = _scope(identity)
    if not merchant_authorized(actor, s, 'EDIT') or actor.get('role') != 'MERCHANT_ADMIN':
        raise ValueError('ACCESS_DENIED')
    from scripts.community_merchant_contract import valid_id
    out = []
    for row in _rows(ads):
        if not isinstance(row, dict) or row.get('scope') != s or not valid_id(row.get('id')) or row.get('status') not in ('DRAFT','REVIEW','APPROVED','ACTIVE','PAUSED','REJECTED','ARCHIVED'):
            raise ValueError('INVALID_AD_VIEW')
        out.append({'id': row['id'], 'status': row['status']})
    return out

# 30: platform approval and finance approval separate
def platform_decision(actor, action, resource):
    if not platform_authorized(actor, action):
        raise ValueError('SEPARATION_OF_DUTIES')
    from scripts.community_merchant_contract import valid_id
    if not isinstance(resource, dict) or not valid_id(resource.get('id')):
        raise ValueError('INVALID_RESOURCE')
    return {'resource_id': resource['id'], 'action': action,
            'provider_settlement_verified': False}
