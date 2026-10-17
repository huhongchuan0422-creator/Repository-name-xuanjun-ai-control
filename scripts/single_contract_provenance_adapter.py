"""Fail-closed offline adapter from independently checked evidence to contract draft.

This is NOT an authentication provider or a Finance source. The host application
must verify trusted session, source signatures and their freshness; none of those
can be proven by user-supplied dictionaries. No signing or spending actions.
Python 3.6 compatible, standard library only.
"""
from __future__ import unicode_literals
import hashlib
import hmac
from single_contract_freeze import ContractHold, canonical_bytes, freeze

_DOMAINS = ("identity", "project", "requirements", "selection", "quote",
            "authorization", "materials", "acceptance", "legal")
_REQUIRED = ("project_id", "verified_customer_id", "contract_id")
_HOLD = {"contract_sign": "HOLD", "payment": "HOLD",
         "procurement": "HOLD", "development_start": "HOLD"}

def _checked(evidence, expected):
    if not isinstance(evidence, dict):
        raise ContractHold("PROVENANCE_MISSING")
    if set(evidence) != set(_DOMAINS):
        raise ContractHold("PROVENANCE_INCOMPLETE")
    for domain in _DOMAINS:
        row = evidence[domain]
        if not isinstance(row, dict):
            raise ContractHold("PROVENANCE_MALFORMED")
        if set(row) != {"scope", "version", "digest", "source_ref", "verified_by_trusted_adapter"}:
            raise ContractHold("PROVENANCE_MALFORMED")
        if row["verified_by_trusted_adapter"] is not True:
            raise ContractHold("PROVENANCE_NOT_VERIFIED")
        if row["scope"] != expected:
            raise ContractHold("PROVENANCE_SCOPE")
        if not isinstance(row["version"], str) or not row["version"]:
            raise ContractHold("PROVENANCE_VERSION")
        if not isinstance(row["source_ref"], str) or not row["source_ref"]:
            raise ContractHold("PROVENANCE_SOURCE")
        if not isinstance(row["digest"], str) or len(row["digest"]) != 64:
            raise ContractHold("PROVENANCE_DIGEST")
        try:
            int(row["digest"], 16)
        except ValueError:
            raise ContractHold("PROVENANCE_DIGEST")

def prepare_unsigned(verified_context, snapshot, evidence):
    """Combine verified-context-shaped inputs without promoting them to trust.

    The result always remains HOLD. There is deliberately no callable function
    here to sign, charge, deploy or procure. This is an integration staging gate.
    """
    if not isinstance(verified_context, dict) or set(verified_context) != set(_REQUIRED):
        raise ContractHold("CONTEXT_REQUIRED")
    if not isinstance(snapshot, dict):
        raise ContractHold("SNAPSHOT_REQUIRED")
    expected = {name: snapshot.get(name) for name in _REQUIRED}
    if expected != verified_context:
        raise ContractHold("CONTEXT_SCOPE_MISMATCH")
    _checked(evidence, expected)
    # Revalidate each recorded domain against the explicitly bound version/hash.
    bindings = {
        "requirements": snapshot.get("requirements_version"),
        "selection": snapshot.get("selection_manifest_hash"),
        "quote": snapshot.get("quote_version"),
        "authorization": snapshot.get("authorization_manifest_hash"),
        "materials": snapshot.get("materials_manifest_hash"),
        "acceptance": snapshot.get("acceptance_version"),
    }
    for name, value in bindings.items():
        if not isinstance(value, str):
            raise ContractHold("SNAPSHOT_BINDING_MISSING")
        row = evidence[name]
        if name in ("selection", "authorization", "materials"):
            if not hmac.compare_digest(row["digest"], value):
                raise ContractHold("PROVENANCE_BINDING_MISMATCH")
        elif row["version"] != value:
            raise ContractHold("PROVENANCE_BINDING_MISMATCH")
    candidate = freeze(snapshot)
    # Bind the evidence manifest as separately inspectable provenance, not as
    # the final customer-signed contract document.
    manifest_sha = hashlib.sha256(canonical_bytes(evidence)).hexdigest()
    return {"candidate": candidate, "provenance_sha256": manifest_sha,
            "status": "UNSIGNED_STAGING_ONLY", "trusted_origin": "NOT_ATTESTED_BY_THIS_MODULE",
            **_HOLD}
