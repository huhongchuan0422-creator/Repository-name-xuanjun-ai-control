"""Offline Stage5 tenant-scoped merchant/order/ad read aggregation; not an authenticated HTTP endpoint."""
from scripts.community_merchant_contract import scope, valid_id
from scripts.community_storefront_snapshot import storefront_snapshot
from scripts.community_order_store import state
from scripts.community_ad_contract import AMOUNT, SUCCESS, result_slot_for_payment

def merchant_checkout_view(merchant_db, ad_db, order_db, identity, reference, now):
    """Compose a single scoped merchant storefront, amount ad and simulated order summary.

    Caller must be a trusted server-side context. Neither supplied identity nor
    simulation state constitutes provider-verified settlement.
    """
    scope(identity)
    if not valid_id(reference):
        raise ValueError("INVALID_ORDER_REFERENCE")
    # Missing/unavailable orders must fail closed rather than disclose a storefront
    # as a receipt for the wrong reference, tenant, merchant or store.
    order = state(order_db, identity, reference)
    storefront = storefront_snapshot(merchant_db, ad_db, identity, now)
    # Even simulation SUCCESS is never a verified receipt. Never return the success
    # creative in this response; frontend cannot accidentally treat candidate as paid.
    ads = {AMOUNT: storefront["ads"][AMOUNT], SUCCESS: None}
    return {
        "merchant": storefront["merchant"],
        "products": storefront["products"],
        "ads": ads,
        "order": {
            "reference": reference,
            "amount_minor": order["amount_minor"],
            "currency": order["currency"],
            "state": order["state"],
            "provider_settlement_verified": False,
        },
        "success_receipt_ad_allowed": result_slot_for_payment(order) is not None,
        "simulation_only": True,
        "escape_text_required": True,
    }
