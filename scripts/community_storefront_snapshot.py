"""Trusted internal Phase1 storefront read composition, no HTTP or authentication."""
from scripts.community_merchant_contract import scope
from scripts.community_merchant_store import profile, list_items
from scripts.community_ad_store import choose
from scripts.community_ad_contract import AMOUNT, SUCCESS

def storefront_snapshot(merchant_db, ad_db, identity, now):
    scope(identity)
    if type(now) is not int or now<0: raise ValueError("INVALID_TIME")
    record=profile(merchant_db,identity)
    catalog=list_items(merchant_db,identity)
    # Ads are nonessential; a broken ad store cannot block storefront access.
    ads={}
    for slot in (AMOUNT,SUCCESS):
        try: selected=choose(ad_db,identity,slot,now)
        except (ValueError,TypeError,AttributeError):
            selected=None
        ads[slot]=selected
    return {"scope":dict(identity),"merchant":{"name":record["name"],
            "description":record["description"],"contact":record["contact"]},
            "products":catalog,"ads":ads,
            "payment_started":False,"provider_settlement_verified":False,
            "escape_text_required":True}
