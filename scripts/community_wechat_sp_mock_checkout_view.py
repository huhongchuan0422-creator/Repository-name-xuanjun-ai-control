"""Pure WeChat mini-program UI projection for community split mock checkout.

Uses existing offline guard and existing Stage5 order IDs. Does not persist
orders, grant payment status, read credentials, or contact WeChat.
"""
from __future__ import unicode_literals
from community_wechat_sp_offline_guard import PaymentHold, validate_checkout_snapshot

def view(checkout, payment_state, actor_tenant, actor_store):
    """Project two ad slots without treating browser claims as payment evidence."""
    draft=validate_checkout_snapshot(checkout)
    if not isinstance(actor_tenant,str) or not isinstance(actor_store,str):
        raise PaymentHold("UNVERIFIED_VIEWER")
    if actor_tenant!=checkout["tenant_id"] or actor_store!=checkout["store_id"]:
        raise PaymentHold("TENANT_STORE_SCOPE_DENIED")
    if payment_state not in ("MOCK_NOT_STARTED","MOCK_PENDING","MOCK_FAILED",
                             "MOCK_CANCELLED","MOCK_PAID_SIMULATED"):
        raise PaymentHold("UNTRUSTED_PAYMENT_STATE")
    ads=checkout["ad_slots"]
    result={"tenant_id":checkout["tenant_id"],"store_id":checkout["store_id"],
            "order_id":checkout["order_id"],"checkout_sha256":draft["snapshot_sha256"],
            "display_amount_fen":checkout["amount_fen"],
            "display_currency":"CNY","provider_payment":"HOLD",
            "finance_effect":"NONE","profitsharing":"HOLD",
            "pre_payment_ad":{"visible":ads["PREPAY_AD"]["enabled"],
                              "creative_id":ads["PREPAY_AD"]["creative_id"]},
            "post_payment_ad":{"visible":False,"creative_id":None},
            "payment_state":payment_state,"payment_verified":False,
            "environment":"LOCAL_SIMULATION_ONLY"}
    # Post-payment ad may be shown only in an explicitly simulated success
    # view. It does not imply WeChat settlement or unlock money features.
    if payment_state=="MOCK_PAID_SIMULATED" and ads["POSTPAY_AD"]["enabled"]:
        result["post_payment_ad"]={"visible":True,
                                  "creative_id":ads["POSTPAY_AD"]["creative_id"]}
    return result
