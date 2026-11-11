"""Loopback-only privileged admin command adapter.

Tokens are provisioned by the local process owner and bound to server-side
roles/scopes. Never accept client-supplied actor/role claims. This is NOT a
WeChat session, customer identity, or production authentication.
"""
import hmac
from scripts.community_merchant_contract import scope
from scripts.community_merchant_store import upsert_profile,put_item
from scripts.community_ad_store import create_campaign,change_campaign_state,review_creative

class LocalAdminPolicy:
    def __init__(self, merchant_token, platform_token, merchant_scope):
        scope(merchant_scope)
        for value in (merchant_token,platform_token):
            if type(value) is not str or len(value)<32 or len(value)>256 or not value.isascii():
                raise ValueError("INVALID_LOCAL_ADMIN_SECRET")
        if hmac.compare_digest(merchant_token,platform_token):
            raise ValueError("DUPLICATE_LOCAL_ADMIN_SECRET")
        self.merchant_token=merchant_token
        self.platform_token=platform_token
        self.merchant_scope=dict(merchant_scope)
    def role(self,token):
        if type(token) is not str:return None
        if hmac.compare_digest(token,self.merchant_token):return "merchant"
        if hmac.compare_digest(token,self.platform_token):return "platform"
        return None

def dispatch_local_admin(service,path,data,capability):
    policy=service.admin_policy
    if policy is None:
        raise PermissionError("ADMIN_DISABLED")
    role=policy.role(capability)
    if role is None:
        raise PermissionError("ADMIN_UNAUTHORIZED")
    if type(data) is not dict or set(data)!={"identity","operation"}:
        raise ValueError("INVALID_ADMIN_REQUEST")
    identity=data["identity"]
    scope(identity)
    operation=data["operation"]
    if type(operation) is not dict:
        raise ValueError("INVALID_ADMIN_OPERATION")
    if role=="merchant":
        if identity!=policy.merchant_scope:
            raise PermissionError("MERCHANT_SCOPE_DENIED")
        actor={"authenticated":True,"role":"MERCHANT_ADMIN",
               "actor_id":"LOCAL_DEMO_MERCHANT_OPERATOR",
               "tenant_id":identity["tenant_id"],"merchant_id":identity["merchant_id"]}
    else:
        actor={"authenticated":True,"role":"PLATFORM_ADMIN",
               "actor_id":"LOCAL_DEMO_PLATFORM_OPERATOR"}
    if path=="/demo/admin/profile":
        if role!="merchant" or set(operation)!={"record","expected_version"}:
            raise PermissionError("MERCHANT_EDITOR_REQUIRED")
        if service.merchant_db is None:raise ValueError("MERCHANT_STORE_UNAVAILABLE")
        result=upsert_profile(service.merchant_db,identity,actor,
                              operation["record"],operation["expected_version"])
    elif path=="/demo/admin/item":
        if role!="merchant" or set(operation)!={"item"}:
            raise PermissionError("MERCHANT_EDITOR_REQUIRED")
        if service.merchant_db is None:raise ValueError("MERCHANT_STORE_UNAVAILABLE")
        put_item(service.merchant_db,identity,actor,operation["item"])
        result={"written":True}
    elif path=="/demo/admin/campaign/create":
        if role!="merchant" or set(operation)!={"record"}:
            raise PermissionError("MERCHANT_EDITOR_REQUIRED")
        if service.ad_db is None:raise ValueError("AD_STORE_UNAVAILABLE")
        result=create_campaign(service.ad_db,identity,operation["record"],
                               actor,service.now)
    elif path=="/demo/admin/campaign/state":
        if role!="merchant" or set(operation)!={"campaign_id","state","expected_version"}:
            raise PermissionError("MERCHANT_EDITOR_REQUIRED")
        if service.ad_db is None:raise ValueError("AD_STORE_UNAVAILABLE")
        result=change_campaign_state(service.ad_db,identity,
            operation["campaign_id"],operation["state"],actor,service.now,
            operation["expected_version"])
    elif path=="/demo/admin/campaign/review":
        if role!="platform" or set(operation)!={"campaign_id","approved","expected_version"}:
            raise PermissionError("PLATFORM_MODERATOR_REQUIRED")
        if service.ad_db is None:raise ValueError("AD_STORE_UNAVAILABLE")
        result=review_creative(service.ad_db,identity,
            operation["campaign_id"],operation["approved"],actor,service.now,
            operation["expected_version"])
    else:
        raise ValueError("UNKNOWN_ADMIN_ROUTE")
    return {"result":result,"simulation_only":True,
            "provider_settlement_verified":False,"admin_command_executed":True}
