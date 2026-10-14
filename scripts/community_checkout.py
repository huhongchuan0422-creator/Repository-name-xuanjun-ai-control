"""Offline-only checkout composition; no provider calls or HTTP endpoint."""
from scripts.community_merchant_contract import scope, verify_qr, payment_amount, route, split_amounts
from scripts.community_ad_contract import AMOUNT, SUCCESS, verified_receipt


def begin(token, identity, context, now, key, amount_minor, reference, channel):
    scope(identity)
    if not verify_qr(token, identity, context, now, key):
        raise ValueError('INVALID_QR')
    order = payment_amount(amount_minor, 'CNY', reference)
    return {'scope': dict(identity), 'order': order, 'channel': route(channel, 'amount', identity)['channel'],
            'state': 'PENDING', 'ad_slot': AMOUNT, 'provider_started': False}


def result(checkout, evidence):
    if not isinstance(checkout, dict) or checkout.get('state') != 'PENDING':
        raise ValueError('INVALID_CHECKOUT')
    order = checkout['order']
    paid = (verified_receipt(evidence) and evidence.get('reference') == order['reference']
            and type(evidence.get('amount_minor')) is int and evidence['amount_minor'] == order['amount_minor']
            and evidence.get('currency') == 'CNY')
    return {'paid': paid, 'ad_slot': SUCCESS if paid else None, 'provider_settlement_verified': False}


def split_preview(checkout, evidence, shares, refund_minor=0):
    if not result(checkout, evidence)['paid']:
        raise ValueError('UNVERIFIED_PAYMENT')
    return split_amounts(checkout['order']['amount_minor'], shares, refund_minor)
