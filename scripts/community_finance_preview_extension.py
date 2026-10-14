"""Extension seam for simulated refund/split/reconciliation reads.

Separate from HTTP transport. No provider access, payout or cross-DB atomicity.
"""
from scripts.community_merchant_contract import scope, split_amounts
from scripts.community_order_store import state
from scripts.community_refund_preview_store import preview_total

FIELDS = {"tenant_id","merchant_id","store_id","reference"}

def _object(raw, expected):
    if type(raw) is not dict or set(raw) != expected:
        raise ValueError("INVALID_REQUEST")
    return raw

def _id(value):
    from scripts.community_merchant_contract import valid_id
    if not valid_id(value):
        raise ValueError("INVALID_ID")
    return value

def dispatch_finance_preview(service,method,path,data):
    if method != "POST":
        raise ValueError("UNKNOWN_FINANCE_ROUTE")
    if method == "POST" and path == "/demo/reconciliation/preview":
        _object(data, {"tenant_id","merchant_id","store_id"})
        identity={k:data[k] for k in ("tenant_id","merchant_id","store_id")}
        t,m,st=scope(identity)
        if service.refund_db is None:
            raise ValueError("REFUND_STORE_UNAVAILABLE")
        # Do not silently claim full reconciliation for truncated results.
        rows=service.db.execute(
            "SELECT reference,amount_minor FROM orders WHERE tenant_id=? "
            "AND merchant_id=? AND store_id=? AND state='SUCCESS' "
            "ORDER BY reference LIMIT 101",(t,m,st)).fetchall()
        if len(rows)>100:
            raise ValueError("RECONCILIATION_SCOPE_TOO_LARGE")
        total=0
        previews=0
        for reference,amount in rows:
            refund=preview_total(service.refund_db,identity,reference)
            if type(refund) is not int or refund<0 or refund>amount:
                raise ValueError("REFUND_PREVIEW_INCONSISTENT")
            total+=amount
            previews+=refund
        return {"simulated_success_order_count":len(rows),
                "simulated_success_total_minor":total,
                "refund_preview_total_minor":previews,
                "simulated_net_minor":total-previews,
                "provider_settlement_minor":None,
                "provider_reconciliation_status":"UNKNOWN",
                "cross_database_atomic_snapshot":False,
                "simulation_only":True,
                "financial_receipt_issued":False}
    if method == "POST" and path == "/demo/splits/preview":
        _object(data, FIELDS | {"shares_bps"})
        identity={k:data[k] for k in ("tenant_id","merchant_id","store_id")}
        scope(identity)
        ref=_id(data["reference"])
        order=state(service.db,identity,ref)
        if order["state"]!="SUCCESS" or order["provider_settlement_verified"] is not False:
            raise ValueError("SIMULATED_SUCCESS_REQUIRED")
        if service.refund_db is None:
            raise ValueError("REFUND_STORE_UNAVAILABLE")
        refund=preview_total(service.refund_db,identity,ref)
        preview=split_amounts(order["amount_minor"],data["shares_bps"],refund)
        return {"allocations_minor":preview["shares_minor"],
                "allocatable_minor":preview["allocatable_minor"],
                "refund_preview_minor":preview["refunded_minor"],
                "simulation_only":True,"provider_settlement_verified":False,
                "provider_split_executed":False,
                "financial_receipt_issued":False,
                "cross_database_atomic_snapshot":False}
    if method == "POST" and path == "/demo/refunds/preview":
        _object(data, FIELDS)
        identity={k:data[k] for k in ("tenant_id","merchant_id","store_id")}
        scope(identity)
        reference=_id(data["reference"])
        order_state=state(service.db,identity,reference)
        if service.refund_db is None:
            raise ValueError("REFUND_PREVIEW_NOT_CONFIGURED")
        total=preview_total(service.refund_db,identity,reference)
        amount=order_state["amount_minor"]
        if type(total) is not int or total<0 or total>amount:
            raise ValueError("INVALID_REFUND_PREVIEW_TOTAL")
        return {"reference":reference,"order_state":order_state["state"],
                "order_amount_minor":amount,"preview_total_minor":total,
                "remaining_preview_minor":amount-total,
                "provider_refund_executed":False,
                "provider_settlement_verified":False,
                "simulation_only":True,
                "financial_receipt_issued":False}
    raise ValueError("UNKNOWN_FINANCE_ROUTE")
