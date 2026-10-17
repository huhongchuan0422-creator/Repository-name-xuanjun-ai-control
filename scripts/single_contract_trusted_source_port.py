"""Fail-closed boundary between trusted application services and offline contract staging.

Provider MUST be a server-controlled object using existing Customer/Project/Quote/
Authorization services. No browser dictionary, source booleans, or user-selected
adapter is accepted here. No network, identity issuance, signing, or payments.
"""
from __future__ import unicode_literals
import hmac
from single_contract_freeze import ContractHold, digest
from single_contract_provenance_adapter import prepare_unsigned

class TrustedContractSource(object):
    """Application integration port; actual service implementation not shipped."""
    def read_consistent(self, trusted_actor, project_id, contract_id):
        raise NotImplementedError

    def revalidate_revision(self, trusted_actor, project_id, contract_id, revision):
        raise NotImplementedError

def stage_from_trusted_source(source, trusted_actor, project_id, contract_id):
    if not isinstance(source, TrustedContractSource):
        raise ContractHold("TRUSTED_SOURCE_REQUIRED")
    if not isinstance(trusted_actor, str) or not trusted_actor:
        raise ContractHold("AUTHENTICATED_ACTOR_REQUIRED")
    if not all(isinstance(s, str) and s for s in (project_id, contract_id)):
        raise ContractHold("INVALID_SCOPE")
    # Do not accept client-supplied snapshots or authority flags.
    record = source.read_consistent(trusted_actor, project_id, contract_id)
    if not isinstance(record, dict) or set(record) != {
            "actor", "revision", "scope", "snapshot", "evidence"}:
        raise ContractHold("SOURCE_RECORD_INVALID")
    if record["actor"] != trusted_actor or not isinstance(record["revision"], str) or not record["revision"]:
        raise ContractHold("SOURCE_ACTOR_OR_REVISION_INVALID")
    scope = record["scope"]
    if not isinstance(scope, dict) or scope.get("project_id") != project_id or scope.get("contract_id") != contract_id:
        raise ContractHold("SOURCE_SCOPE_MISMATCH")
    result = prepare_unsigned(scope, record["snapshot"], record["evidence"])
    # Recheck with the source before returning; if it changes or is revoked,
    # never return a potentially obsolete candidate.
    if source.revalidate_revision(trusted_actor, project_id, contract_id,
                                  record["revision"]) is not True:
        raise ContractHold("SOURCE_REVISION_REVOKED")
    return {"staging": result, "source_revision": record["revision"],
            "source_record_digest": digest(record),
            "status": "OFFLINE_STAGING_HOLD",
            "contract_sign": "HOLD", "payment": "HOLD",
            "procurement": "HOLD", "development_start": "HOLD"}
