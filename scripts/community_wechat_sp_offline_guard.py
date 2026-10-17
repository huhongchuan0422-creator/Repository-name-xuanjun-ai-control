"""Community split WeChat service-provider APIv3 *offline* admission contracts.

No credential loading, HTTP requests, merchant onboarding, order creation,
money movement, or ledger replacement. Existing Finance/payment services must
supply authenticated merchant bindings and durable idempotency before any live
adapter is implemented. Python 3.6-compatible standard library.
"""
from __future__ import unicode_literals
import hashlib
import json
import re

class PaymentHold(ValueError):
    pass

_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,95}$")
_DIGITS = re.compile(r"^[0-9]{6,32}$")
_ALLOWED = ("PREPAY_AD", "POSTPAY_AD")
_HOLD = {"payment": "HOLD", "refund": "HOLD", "profitsharing": "HOLD",
         "production": "HOLD", "credential_use": "DENIED"}

def _id(s):
    if not isinstance(s, str) or not _ID.match(s) or _ID.fullmatch(s) is None:
        raise PaymentHold("INVALID_ID")

def _mchid(s):
    if not isinstance(s, str) or _DIGITS.fullmatch(s) is None:
        raise PaymentHold("INVALID_MERCHANT_ID")

def validate_checkout_snapshot(snapshot):
    """Only server-derived synthetic drafts; never grants WeChat API authority."""
    expected = {"tenant_id", "store_id", "order_id", "sp_mchid", "sub_mchid",
                "app_id", "amount_fen", "currency", "payer_type", "ad_slots",
                "merchant_binding_revision", "price_revision"}
    if not isinstance(snapshot, dict) or set(snapshot) != expected:
        raise PaymentHold("INVALID_CHECKOUT_SCHEMA")
    for k in ("tenant_id", "store_id", "order_id", "merchant_binding_revision",
              "price_revision"):
        _id(snapshot[k])
    _mchid(snapshot["sp_mchid"])
    # No sub-merchant: mock preparation possible; live payment is not.
    if snapshot["sub_mchid"] is not None:
        _mchid(snapshot["sub_mchid"])
    appid = snapshot["app_id"]
    if not isinstance(appid, str) or not re.fullmatch(r"wx[a-fA-F0-9]{16}", appid):
        raise PaymentHold("INVALID_APPID")
    if type(snapshot["amount_fen"]) is not int or not 1 <= snapshot["amount_fen"] <= 100000000:
        raise PaymentHold("INVALID_AMOUNT")
    if snapshot["currency"] != "CNY" or snapshot["payer_type"] != "UNVERIFIED_OFFLINE":
        raise PaymentHold("INVALID_CURRENCY_OR_PAYER")
    ads = snapshot["ad_slots"]
    if not isinstance(ads, dict) or set(ads) != set(_ALLOWED):
        raise PaymentHold("TWO_AD_SLOTS_REQUIRED")
    for k in _ALLOWED:
        a = ads[k]
        if not isinstance(a, dict) or set(a) != {"creative_id", "revision", "enabled"}:
            raise PaymentHold("INVALID_AD_SLOT")
        _id(a["creative_id"]); _id(a["revision"])
        if type(a["enabled"]) is not bool:
            raise PaymentHold("INVALID_AD_ENABLED")
    raw = json.dumps(snapshot, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return {"state": "OFFLINE_CANDIDATE_ONLY",
            "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
            "idempotency_scope": snapshot["tenant_id"] + ":" + snapshot["order_id"],
            "ad_pre_payment": ads["PREPAY_AD"]["creative_id"],
            "ad_post_payment": ads["POSTPAY_AD"]["creative_id"],
            "sub_merchant_status": ("ABSENT" if snapshot["sub_mchid"] is None
                                    else "UNVERIFIED"),
            **_HOLD}

def classify_payment_notification(event):
    """Classify an unverified notification without accepting its claims."""
    if not isinstance(event, dict):
        raise PaymentHold("INVALID_NOTIFICATION")
    if any(key in event for key in ("verified", "authenticated", "paid", "success")):
        raise PaymentHold("CLIENT_AUTHENTICATION_CLAIM_FORBIDDEN")
    # A caller-supplied payment success event never posts to Finance.
    return {"state": "UNVERIFIED_EVENT_QUARANTINED",
            "next_action": "SERVER_SIDE_SIGNATURE_AND_ORDER_RECONCILIATION",
            "finance_effect": "NONE", **_HOLD}
