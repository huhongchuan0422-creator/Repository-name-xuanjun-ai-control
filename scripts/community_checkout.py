"""Offline checkout composition. Reconciled evidence must originate from a trusted backend."""
from scripts.community_merchant_contract import scope, verify_qr, payment_amount, route, split_amounts
from scripts.community_ad_contract import AMOUNT, SUCCESS, verified_receipt

def begin(token, identity, context, now, key, amount_minor, reference, channel):
    scope(identity)
    if not verify_qr(token, identity, context, now, key):
        raise ValueError('INVALID_QR')
    order = payment_amount(amount_minor, 'CNY', reference)
    return {'scope': dict(identity), 'order': order,
            'channel': route(channel, 'amount', identity)['channel'],
            'state': 'PENDING', 'ad_slot': AMOUNT, 'provider_started': False}

def _validated(checkout):
    if not isinstance(checkout, dict) or checkout.get('state') != 'PENDING':
        raise ValueError('INVALID_CHECKOUT')
    identity = checkout.get('scope')
    scope(identity)
    order = checkout.get('order')
    if not isinstance(order, dict) or set(order) != {'amount_minor','currency','reference','provider_payment_started'} or order.get('provider_payment_started') is not False:
        raise ValueError('INVALID_CHECKOUT_ORDER')
    payment_amount(order.get('amount_minor'), order.get('currency'), order.get('reference'))
    return identity, order

def result(checkout, evidence):
    identity, order = _validated(checkout)
    # Trust verified_receipt booleans ONLY after authenticated backend reconciliation.
    paid = (verified_receipt(evidence) and isinstance(evidence.get('scope'), dict)
            and evidence['scope'] == identity
            and evidence.get('reference') == order['reference']
            and type(evidence.get('amount_minor')) is int
            and evidence['amount_minor'] == order['amount_minor']
            and evidence.get('currency') == 'CNY')
    return {'paid': paid, 'ad_slot': SUCCESS if paid else None,
            'provider_settlement_verified': False}

def split_preview(checkout, evidence, shares, refund_minor=0):
    if not result(checkout, evidence)['paid']:
        raise ValueError('UNVERIFIED_PAYMENT')
    return split_amounts(checkout['order']['amount_minor'], shares, refund_minor)
