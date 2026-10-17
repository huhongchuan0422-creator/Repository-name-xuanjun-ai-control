"""Offline single-contract freeze candidate. No production signing, payment or procurement.

Pure functions consume *trusted server-side* snapshots; caller MUST authenticate the
principal and verify document/quote provenance before invoking. This module never
executes payment, deploys, signs, or handles raw secrets. Python 3.6 compatible.
"""
from __future__ import unicode_literals
import copy
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, localcontext

class ContractHold(ValueError):
    pass

REQUIRED = ("project_id", "verified_customer_id", "contract_id",
            "requirements_version", "quote_version", "pricebook_hash",
            "selection_manifest_hash", "authorization_manifest_hash",
            "materials_manifest_hash", "acceptance_version")
RESOURCE_MODES = ("EXISTING", "SELF_PURCHASE", "AGENT_PURCHASE", "PLATFORM")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")

def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")

def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()

def money(v):
    if isinstance(v, bool) or not isinstance(v, (str, int)):
        raise ContractHold("INVALID_AMOUNT")
    try:
        n = Decimal(str(v))
    except InvalidOperation:
        raise ContractHold("INVALID_AMOUNT")
    if not n.is_finite() or n < 0 or n.as_tuple().exponent < -2:
        raise ContractHold("INVALID_AMOUNT")
    # Strict currency bound prevents Decimal context precision loss; no silent rounding.
    if len(n.as_tuple().digits) > 16 or n > Decimal("99999999999999.99"):
        raise ContractHold("AMOUNT_OUT_OF_RANGE")
    return n

def cents(v):
    n = money(v)
    return int(n * 100)

def as_money(value):
    return "{:.2f}".format(Decimal(value) / 100)

def _verified_id(value):
    if not isinstance(value, str) or not ID.match(value):
        raise ContractHold("INVALID_ID")
    return value

def freeze(snapshot):
    """Freeze a verified draft into an immutable, unsigned candidate.

    Returns data + SHA256, but deliberately never a signable/chargeable status.
    Unknown prices, missing authority or ambiguous selection fail closed.
    """
    if not isinstance(snapshot, dict):
        raise ContractHold("INVALID_SNAPSHOT")
    for key in REQUIRED:
        if key not in snapshot:
            raise ContractHold("MISSING_" + key.upper())
        v = snapshot[key]
        if key.endswith("_hash"):
            if not isinstance(v, str) or not HEX64.match(v):
                raise ContractHold("INVALID_" + key.upper())
        else:
            _verified_id(v)
    if snapshot.get("disclosure_confirmed") is not True:
        raise ContractHold("DISCLOSURE_REQUIRED")
    if snapshot.get("customer_selection_confirmed") is not True:
        raise ContractHold("SELECTION_CONFIRMATION_REQUIRED")
    if snapshot.get("signer_authority_verified") is not True:
        raise ContractHold("SIGNER_AUTHORITY_REQUIRED")
    if snapshot.get("legal_review_approved") is not True:
        raise ContractHold("LEGAL_REVIEW_REQUIRED")
    if snapshot.get("quote_valid") is not True:
        raise ContractHold("QUOTE_INVALID")
    features = snapshot.get("features")
    if not isinstance(features, list) or not features:
        raise ContractHold("FEATURES_REQUIRED")
    for f in features:
        if not isinstance(f, dict):
            raise ContractHold("INVALID_FEATURE")
        for key in ("feature_id", "description", "acceptance"):
            if not isinstance(f.get(key), str) or not f[key].strip():
                raise ContractHold("FEATURE_INCOMPLETE")
        _verified_id(f["feature_id"])
    items = snapshot.get("resources")
    if not isinstance(items, list):
        raise ContractHold("RESOURCES_REQUIRED")
    seen = set()
    third_party = 0
    service = 0
    for item in items:
        if not isinstance(item, dict):
            raise ContractHold("INVALID_RESOURCE")
        ident = _verified_id(item.get("item_id"))
        if ident in seen:
            raise ContractHold("DUPLICATE_RESOURCE")
        seen.add(ident)
        mode = item.get("mode")
        if mode not in RESOURCE_MODES:
            raise ContractHold("INVALID_MODE")
        for field in ("third_party_first_cny", "procurement_fee_cny",
                      "deployment_fee_cny", "tax_cny"):
            if field not in item:
                raise ContractHold("UNKNOWN_PRICE")
            money(item[field])
        if mode != "AGENT_PURCHASE" and money(item["third_party_first_cny"]) != 0:
            raise ContractHold("DUPLICATE_THIRD_PARTY_COST")
        if mode == "AGENT_PURCHASE":
            third_party += cents(item["third_party_first_cny"])
        service += sum(cents(item[k]) for k in ("procurement_fee_cny",
                       "deployment_fee_cny", "tax_cny"))
        # Display in both currencies, but do not derive a fictional FX rate.
        for code in ("CNY", "USD"):
            if not isinstance(item.get("display_" + code), str) or not item["display_" + code]:
                raise ContractHold("DUAL_CURRENCY_REQUIRED")
        if not isinstance(item.get("owner"), str) or not item["owner"].strip():
            raise ContractHold("RESOURCE_OWNERSHIP_REQUIRED")
    dev = cents(snapshot.get("development_fee_cny"))
    first_dev = dev // 2
    if first_dev * 2 != dev:
        raise ContractHold("ODD_CENT_SPLIT_REQUIRES_AGREEMENT")
    # Strict input schemas: unknown fields cannot enter the frozen archive.
    root_allowed = set(REQUIRED) | {"disclosure_confirmed", "customer_selection_confirmed",
        "signer_authority_verified", "legal_review_approved", "quote_valid",
        "development_fee_cny", "features", "resources"}
    feature_allowed = {"feature_id", "description", "acceptance"}
    resource_allowed = {"item_id", "mode", "owner", "third_party_first_cny",
        "procurement_fee_cny", "deployment_fee_cny", "tax_cny", "display_CNY",
        "display_USD"}
    if set(snapshot) - root_allowed:
        raise ContractHold("UNKNOWN_ROOT_FIELD")
    for feature in features:
        if set(feature) - feature_allowed:
            raise ContractHold("UNKNOWN_FEATURE_FIELD")
    for item in items:
        if set(item) - resource_allowed:
            raise ContractHold("UNKNOWN_RESOURCE_FIELD")
    # Text is not accepted as a credential transport; the caller must perform
    # separate private-data filtering and send SecretRef only through trusted APIs.
    if third_party + service + first_dev > 9999999999999999:
        raise ContractHold("AMOUNT_OUT_OF_RANGE")
    frozen = {
        "schema": "xuanjun.single-contract.offline.v1",
        "scope": {k: snapshot[k] for k in REQUIRED},
        "features": copy.deepcopy(features),
        "resources": copy.deepcopy(items),
        "payment_cny": {
            "development_first_50pct": as_money(first_dev),
            "development_final_after_acceptance_50pct": str(first_dev),
            "third_party_first_full": as_money(third_party),
            "agreed_services_and_tax_first": as_money(service),
            "first_total": as_money(first_dev + third_party + service)
        },
        "disclosure_confirmed": True,
        "customer_selection_confirmed": True,
        "signer_authority_verified": True,
        "legal_review_approved": True,
        "quote_valid": True
    }
    # Do not present a fake signature, receipt or purchase permission.
    return {"frozen": frozen, "contract_document_hash": digest(frozen),
            "status": "UNSIGNED_CANDIDATE_ONLY",
            "contract_sign": "HOLD", "payment": "HOLD",
            "procurement": "HOLD", "development_start": "HOLD"}

def assert_unchanged(candidate, snapshot):
    current = freeze(snapshot)
    if (candidate.get("contract_document_hash") != current["contract_document_hash"]
            or candidate.get("frozen") != current["frozen"]):
        raise ContractHold("SNAPSHOT_CHANGED")
    return True
