"""Stage5 Phase2: offline integration surface; explicitly not production finance.

Never trust an actor, tenant or payment proof in a request body. This adapter
receives a role+tenant principal from a trusted hosting boundary, and uses
only already approved frozen catalog versions and in-process finance previews.
"""
import json
import sqlite3
from scripts.community_saas_modules import catalog,capability_allowed,entitled
from scripts.community_saas_offer_catalog import list_offers,quote,read_quote
from scripts.community_saas_order_preparation import (
    prepare,read,status,renewal_intent,entitlement_intent)
from scripts.community_saas_offline_handoff import (
    admin_snapshot,create_review,change_review,recovery_check,plan_finance_claim)
from scripts.community_merchant_contract import valid_id

def _id(v):
    if type(v) is not str or not valid_id(v):raise ValueError("INVALID_IDENTIFIER")
    return v

def _time(v):
    if type(v) is not int or v<0:raise ValueError("INVALID_TIME")
    return v

class Principal:
    """Identity supplied by trusted server policy, never from client JSON."""
    def __init__(self,tenant_id,role):
        self.tenant_id=_id(tenant_id)
        if role not in ("CUSTOMER","MERCHANT_ADMIN","PLATFORM_OWNER"):
            raise ValueError("INVALID_ROLE")
        self.role=role

def _customer_view(value):
    """Remove internal cost evidence, supplier prices and approval references."""
    if type(value) is list:return [_customer_view(item) for item in value]
    if type(value) is dict:
        return {key:_customer_view(val) for key,val in value.items()
                if key not in ("cost_cny_minor","cost_usd_minor","cost_evidence_ref",
                               "approval_ref","fx_source","fx_at","source_evidence",
                               "supplier_id","quote_snapshot")}
    return value

class OfflineSaas:
    def __init__(self,quote_db,order_db,module_db):
        self.quotes=quote_db
        self.orders=order_db
        self.modules=module_db

    def dispatch(self,principal,operation,params,now):
        if not isinstance(principal,Principal):
            raise PermissionError("TRUSTED_PRINCIPAL_REQUIRED")
        _time(now)
        if type(params) is not dict:
            raise ValueError("INVALID_REQUEST")
        # Strict per-operation input schema: client cannot supply actor,
        # tenant, approved state, proof or financial authority.
        fields={
            "catalog":set(),
            "offers":{"module_id"},
            "customer_orders":set(),
            "quote":{"quote_id","offer_id","version","expires_at"},
            "quote_read":{"quote_id"},
            "order_prepare":{"order_id","quote_id","currency"},
            "order_read":{"order_id"},
            "order_status":{"order_id"},
            "entitlement":{"module_id"},
            "capability":{"capability"},
            "renewal_plan":{"order_id","valid_until"},
            "finance_requirements":{"order_id"},
            "admin_snapshot":set(),
            "review_open":{"task_id","order_id","kind","reason"},
            "review_close":{"task_id","event_id","state"},
            "recovery":set(),
            "refund_reversal_plan":{"order_id","reason"},
            "health":set()
        }
        if operation not in fields or set(params)!=fields[operation]:
            raise ValueError("INVALID_REQUEST_FIELDS")
        tenant=principal.tenant_id
        if operation=="catalog":
            return {"modules":catalog(),"framework_free":True,"production":False}
        if operation=="offers":
            return {"offers":_customer_view(list_offers(self.quotes,params["module_id"],tenant_id=tenant))}
        if operation=="customer_orders":
            admin=admin_snapshot(self.orders,tenant,now)
            return {"orders":admin["orders"],"finance_state":"NOT_VERIFIED_BY_ADAPTER"}
        if operation=="quote":
            _id(params["quote_id"]);_id(params["offer_id"])
            result=quote(self.quotes,params["quote_id"],tenant,
                params["offer_id"],params["version"],now,_time(params["expires_at"]))
            return {"quote_id":params["quote_id"],**_customer_view(result)}
        if operation=="quote_read":
            return _customer_view(read_quote(self.quotes,_id(params["quote_id"]),tenant))
        if operation=="order_prepare":
            return _customer_view(prepare(self.orders,self.quotes,_id(params["order_id"]),tenant,
                           _id(params["quote_id"]),params["currency"],now))
        if operation=="order_read":
            return _customer_view(read(self.orders,_id(params["order_id"]),tenant))
        if operation=="order_status":
            return status(self.orders,_id(params["order_id"]),tenant)
        if operation=="entitlement":
            return {"module_id":params["module_id"],
                    "active":entitled(self.modules,tenant,params["module_id"],now)}
        if operation=="capability":
            return {"capability":params["capability"],
                    "allowed":capability_allowed(self.modules,tenant,params["capability"],now)}
        if operation=="renewal_plan":
            return renewal_intent(self.orders,_id(params["order_id"]),tenant,now,
                                  params["valid_until"])
        if operation in ("finance_requirements","admin_snapshot","review_open",
                         "review_close","recovery","refund_reversal_plan"):
            if principal.role not in ("MERCHANT_ADMIN","PLATFORM_OWNER"):
                raise PermissionError("ADMIN_ROLE_REQUIRED")
        if operation=="finance_requirements":
            return plan_finance_claim(self.orders,_id(params["order_id"]),tenant)
        if operation=="admin_snapshot":
            return admin_snapshot(self.orders,tenant,now)
        if operation=="review_open":
            return create_review(self.orders,_id(params["task_id"]),tenant,
                _id(params["order_id"]),params["kind"],now,params["reason"])
        if operation=="review_close":
            return change_review(self.orders,_id(params["task_id"]),tenant,
                _id(params["event_id"]),params["state"],now)
        if operation=="recovery":
            return recovery_check(self.orders,tenant)
        if operation=="health":
            return {"status":"OFFLINE_ONLY","service":"SAAS_PHASE2",
                    "finance_provider":"NOT_CONNECTED","grant_writer":"DISABLED"}
        if operation=="refund_reversal_plan":
            order=read(self.orders,_id(params["order_id"]),tenant)
            reason=params["reason"]
            if type(reason) is not str or not reason.strip() or len(reason)>300:
                raise ValueError("INVALID_REFUND_REASON")
            return {"order_id":order["order_id"],"tenant_id":tenant,
                    "quote_sha256":order["quote_sha256"],
                    "action":"REFUND_REVIEW_ONLY","reason":reason,
                    "provider_refund_executed":False,"entitlement_revoked":False,
                    "revenue_reversed":False}
        raise ValueError("UNKNOWN_OPERATION")

def serialize_response(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),
                      allow_nan=False)

def verify_persistent_stores(quote_path,order_path):
    """Fail closed on unknown schemas; does not create or migrate data."""
    from scripts.community_saas_modules import connect
    from scripts.community_saas_order_preparation import SCHEMA,LIFECYCLE_SCHEMA
    from scripts.community_saas_offline_handoff import REVIEW_SCHEMA
    from scripts.community_saas_schema_guard import verify_extension
    module=connect(quote_path)
    try:
        db=sqlite3.connect(order_path)
        try:
            verify_extension(db,SCHEMA)
            verify_extension(db,LIFECYCLE_SCHEMA)
            verify_extension(db,REVIEW_SCHEMA)
            integrity=db.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity!="ok":raise ValueError("DB_INTEGRITY_FAIL")
        finally:db.close()
    finally:module.close()
    return {"verified":True,"payment_processing":False,"migration_executed":False}
