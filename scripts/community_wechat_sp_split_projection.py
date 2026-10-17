"""Provider-neutral simulated settlement projection; no real payment side effects.

Only deterministic integer-fen accounting for existing Stage5 order snapshots.
No separate Finance ledger, network, merchant credentials or deployment.
"""
from __future__ import unicode_literals
from community_wechat_sp_offline_guard import PaymentHold, validate_checkout_snapshot

def project_split(checkout, allocations, refunded_fen=0):
    draft = validate_checkout_snapshot(checkout)
    amount=checkout["amount_fen"]
    if type(refunded_fen) is not int or not 0 <= refunded_fen <= amount:
        raise PaymentHold("INVALID_REFUND_FEN")
    if not isinstance(allocations,list) or not 1 <= len(allocations) <= 32:
        raise PaymentHold("INVALID_ALLOCATION_LIST")
    seen=set();allocated=0;items=[]
    for item in allocations:
        if not isinstance(item,dict) or set(item)!={"receiver_id","amount_fen"}:
            raise PaymentHold("INVALID_ALLOCATION")
        receiver=item["receiver_id"]
        if not isinstance(receiver,str) or not receiver or len(receiver)>96 or receiver in seen:
            raise PaymentHold("DUPLICATE_OR_INVALID_RECEIVER")
        if any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-" for ch in receiver):
            raise PaymentHold("INVALID_RECEIVER_ID")
        value=item["amount_fen"]
        if type(value) is not int or value < 0:
            raise PaymentHold("INVALID_ALLOCATION_AMOUNT")
        seen.add(receiver);allocated+=value
        items.append({"receiver_id":receiver,"amount_fen":value})
    available=amount-refunded_fen
    if allocated>available:
        raise PaymentHold("ALLOCATION_EXCEEDS_AVAILABLE")
    return {"idempotency_scope":draft["idempotency_scope"],
            "order_snapshot_sha256":draft["snapshot_sha256"],
            "gross_fen":amount,"refund_fen":refunded_fen,
            "available_fen":available,"allocated_fen":allocated,
            "undistributed_fen":available-allocated,
            "allocations":items,"currency":"CNY",
            "state":"SIMULATED_SPLIT_PREVIEW_ONLY",
            "provider_confirmation":"NOT_VERIFIED",
            "finance_write":"DENIED","real_refund":"HOLD",
            "real_split":"HOLD"}
