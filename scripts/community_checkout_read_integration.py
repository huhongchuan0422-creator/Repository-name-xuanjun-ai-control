"""Internal tenant-scoped merchant/order/ad read aggregation; not an authenticated HTTP endpoint."""
from scripts.community_merchant_contract import scope, valid_id
from scripts.community_storefront_snapshot import storefront_snapshot
from scripts.community_order_store import state
from scripts.community_ad_contract import AMOUNT, SUCCESS
from scripts.community_order_provider_projection import provider_evidence

def merchant_checkout_view(merchant_db, ad_db, order_db, identity, reference, now):
    """Compose scoped storefront and order; release SUCCESS only for durable proof.

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
    # Same existing signed-provider projection used by the owned receipt-ad API.
    # No caller-supplied paid flag and no provider request is accepted here.
    verified_success = (order["state"] == "SUCCESS"
                        and provider_evidence(order_db, identity, reference) is not None)
    ads = {AMOUNT: storefront["ads"][AMOUNT],
           SUCCESS: storefront["ads"][SUCCESS] if verified_success else None}
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
        "success_receipt_ad_allowed": verified_success,
        "payment_success_verified": verified_success,
        "simulation_only": not verified_success,
        "escape_text_required": True,
    }
