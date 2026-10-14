"""Stage 5 advertising/payment boundary: pure, offline validation only.

No network, database, payment processor or production side effects.
"""
from datetime import datetime, timezone
from urllib.parse import urlsplit
import ipaddress

AMOUNT = "AD_SLOT_PAYMENT_AMOUNT"
SUCCESS = "AD_SLOT_PAYMENT_SUCCESS"
SLOTS = frozenset((AMOUNT, SUCCESS))
PAYMENT_STATES = frozenset(("SUCCESS", "PENDING", "FAILED", "CANCELLED", "REFUNDED"))
ALLOWED_TRANSITIONS = {
    "DRAFT": frozenset(("REVIEW",)),
    "REVIEW": frozenset(("APPROVED", "REJECTED")),
    "APPROVED": frozenset(("ACTIVE", "ARCHIVED")),
    "ACTIVE": frozenset(("PAUSED", "ARCHIVED")),
    "PAUSED": frozenset(("ACTIVE", "ARCHIVED")),
    "REJECTED": frozenset(("REVIEW", "ARCHIVED")),
    "ARCHIVED": frozenset(),
}

def slots_valid(slots):
    """Both separate placements must be represented exactly once."""
    return isinstance(slots, (list, tuple)) and len(slots) == 2 and set(slots) == SLOTS

def verified_receipt(payment):
    """Only server-provider reconciled success can claim a paid receipt."""
    return (isinstance(payment, dict) and payment.get("state") == "SUCCESS"
            and payment.get("server_verified") is True
            and payment.get("provider_reconciled") is True)

def within_scope(ad, request):
    keys = ("tenant_id", "merchant_id", "store_id")
    return all(isinstance(ad.get(k), str) and ad[k] and ad[k] == request.get(k) for k in keys)

def select_active(ads, request, slot, now):
    """Deterministic highest-priority selection within approved active campaigns."""
    if slot not in SLOTS or not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("INVALID_SELECTION_CONTEXT")
    eligible = [a for a in ads if within_scope(a, request)
                and a.get("slot") == slot and a.get("status") == "ACTIVE"
                and isinstance(a.get("starts_at"), datetime)
                and isinstance(a.get("ends_at"), datetime)
                and a["starts_at"].tzinfo is not None
                and a["ends_at"].tzinfo is not None
                and a["starts_at"] <= now < a["ends_at"]
                and type(a.get("priority")) is int and a["priority"] >= 0
                and isinstance(a.get("id"), str) and a["id"]]
    return min(eligible, key=lambda a: (-a["priority"], a["id"])) if eligible else None

def safe_creative_url(url):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 32 for c in url):
        return False
    try:
        p = urlsplit(url)
        if p.scheme != "https" or not p.hostname or p.username or p.password or p.fragment:
            return False
        if p.port not in (None, 443):
            return False
        host = p.hostname.rstrip(".").lower()
        if host in ("localhost",) or host.endswith((".localhost", ".local", ".internal")):
            return False
        try:
            ipaddress.ip_address(host)
            return False  # require externally validated hostname policy
        except ValueError:
            pass
        return "." in host and all(label and len(label) <= 63 and
                                   label.replace("-", "").isalnum() and
                                   not label.startswith("-") and not label.endswith("-")
                                   for label in host.split("."))
    except ValueError:
        return False

def fallback(slot, ad):
    if slot not in SLOTS:
        raise ValueError("UNKNOWN_SLOT")
    return {"slot": slot, "creative": ad if ad is not None else None,
            "payment_enabled": True}

def accept_metric(event, seen):
    """Return dedup decision without mutating ledger or input set."""
    fields = ("event_id", "tenant_id", "merchant_id", "slot")
    if not isinstance(event, dict) or event.get("slot") not in SLOTS or event.get("kind") not in ("IMPRESSION", "CLICK"):
        return False
    if not all(isinstance(event.get(k), str) and event[k] for k in fields):
        return False
    key = (event["tenant_id"], event["merchant_id"], event["slot"], event["kind"], event["event_id"])
    return key not in seen

def audit_transition(before, after, actor):
    return (before in ALLOWED_TRANSITIONS and after in ALLOWED_TRANSITIONS[before]
            and isinstance(actor, dict) and actor.get("authenticated") is True
            and actor.get("role") in ("MERCHANT_ADMIN", "PLATFORM_ADMIN")
            and isinstance(actor.get("actor_id"), str) and bool(actor["actor_id"]))

def ad_surface_allowed(surface, payment):
    if surface == "OWN_AMOUNT_ENTRY":
        return True
    if surface == "OWN_SUCCESS_RECEIPT":
        return verified_receipt(payment)
    return False  # third-party hosted payment UI never modified

def refund_invariant(before, after):
    """Ad presentation may not mutate payment/accounting fields."""
    fields = ("amount_minor", "currency", "provider_order_id", "beneficiary_id",
              "split_allocation", "refund_minor", "settlement_state")
    return (isinstance(before, dict) and isinstance(after, dict)
            and all(before.get(k) == after.get(k) for k in fields))
