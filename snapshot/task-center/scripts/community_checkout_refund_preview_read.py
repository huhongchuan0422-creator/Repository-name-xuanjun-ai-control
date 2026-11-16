"""Trusted internal Stage5 read of simulated refund preview alongside a checkout.

This is not an atomic multi-database snapshot, authenticated API, or a refund
receipt. All amounts are offline simulations and provider execution is false.
"""
from scripts.community_checkout_read_integration import merchant_checkout_view
from scripts.community_refund_preview_store import preview_total

def checkout_with_refund_preview(merchant_db, ad_db, order_db, refund_db,
                                 identity, reference, now):
    checkout = merchant_checkout_view(merchant_db, ad_db, order_db,
                                      identity, reference, now)
    total = preview_total(refund_db, identity, reference)
    amount = checkout["order"]["amount_minor"]
    if type(total) is not int or total < 0 or total > amount:
        raise ValueError("INVALID_REFUND_PREVIEW_TOTAL")
    return {
        **checkout,
        "refund_preview": {
            "total_minor": total,
            "remaining_preview_minor": amount-total,
            "provider_refund_executed": False,
            "simulation_only": True,
        },
        "financial_receipt_issued": False,
        "cross_database_atomic_snapshot": False,
    }
