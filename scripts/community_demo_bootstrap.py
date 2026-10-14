"""Ephemeral, explicitly fake local storefront fixture. No user authentication or payment."""
import time
from scripts.community_merchant_store import open_store, upsert_profile, put_item
from scripts.community_ad_store import open_offline, create_campaign, change_campaign_state, review_creative
from scripts.community_ad_contract import AMOUNT, SUCCESS

DEMO_SCOPE = {"tenant_id":"tenant1","merchant_id":"merchant1","store_id":"store1"}
DEMO_OTHER = {"tenant_id":"tenant1","merchant_id":"merchant2","store_id":"store1"}

def fixture_stores():
    """Return fresh in-memory merchant/ad stores, seeded with no customer data."""
    m = open_store()
    try:
        a = open_offline()
    except BaseException:
        m.close()
        raise
    try:
        for identity, name in ((DEMO_SCOPE,"Demo Merchant A"),(DEMO_OTHER,"Demo Merchant B")):
            actor = {"authenticated":True,"role":"MERCHANT_ADMIN",
                     "actor_id":"OFFLINE_DEMO_FIXTURE_ONLY",
                     "tenant_id":identity["tenant_id"],"merchant_id":identity["merchant_id"]}
            upsert_profile(m, identity, actor,
                           {"name":name,"description":"Simulated storefront, not a real merchant",
                            "contact":"No payment or contact","status":"ACTIVE"})
            put_item(m,identity,actor,{"id":"sample_item","name":name+" Sample Item",
                                       "status":"ACTIVE","sort":1})
        now = int(time.time())
        owner = {"authenticated":True,"role":"MERCHANT_ADMIN","actor_id":"OFFLINE_FIXTURE",
                 "tenant_id":DEMO_SCOPE["tenant_id"],"merchant_id":DEMO_SCOPE["merchant_id"]}
        moderator = {"authenticated":True,"role":"PLATFORM_ADMIN","actor_id":"OFFLINE_FIXTURE_MODERATOR"}
        for slot,cid in ((AMOUNT,"sample_amount"),(SUCCESS,"sample_success")):
            record={"id":cid,"slot":slot,"starts_at":now-300,"ends_at":now+86400,
                    "title":"DEMO APPROVED AMOUNT AD" if slot==AMOUNT else "DEMO SUCCESS AD MUST STAY HIDDEN",
                    "target_url":"https://example.org/sale","priority":10}
            create_campaign(a,DEMO_SCOPE,record,owner,now)
            change_campaign_state(a,DEMO_SCOPE,cid,"REVIEW",owner,now,1)
            review_creative(a,DEMO_SCOPE,cid,True,moderator,now,2)
            change_campaign_state(a,DEMO_SCOPE,cid,"APPROVED",owner,now,3)
            change_campaign_state(a,DEMO_SCOPE,cid,"ACTIVE",owner,now,4)
        return m,a,now
    except BaseException:
        a.close();m.close()
        raise
