# GEO canonical accepted-version binding — next delta after a529

Base a52918f604136a807fb94e8425bcc6b529c42517, same original feature/customer-geo-crm-release-20261124. Fixed a529 review bytes are preserved separately; this is a serial next delta.

## Dependency choice, not invented authority
The existing community_saas_order_preparation explicitly says PREPARED_ONLY does not grant rights, and community_saas_fulfillment requires an admitted FinanceAuthority implementation. No concrete live Finance signer/configuration or GEO entitlement export was provided here. Those modules are not converted into GEO authority, no community code is changed, and no test proof/body boolean is accepted as real finance evidence.

The dependency that already exists and can be connected now is scripts/pr122_customer_change_authority.py: protected import_snapshot verifies original signed canonical document bytes, document/version hashes, current project revision/contract/owner and accepted record type. It is loaded by the original import-change-authority operator entry, using the original authority key, not a new signer or version store.

## Exact opt-in selection, never newest-document guessing
Existing GEO import-geo-authority now permits an optional signed version_document_id field. The original required fields/signature convention/subject checks/monotonic revision remain unchanged; no extra required field for existing grants. This ID is selected by the existing authoritative exporter/custodian in protected signed input, not a customer body/page/title or heuristic latest generic document. No real ID, identity or grant is invented in this task.

GEO snapshot calls pr122_customer_geo_versions.accepted_version only when existing admitted GEO entitlement is enabled. It reads the exact bound ID from the current canonical source (not historical fallback), rechecks current project_revision/contract_ref/owner and kind=ACCEPTED_VERSION, then exposes only metadata: current_version, confirmation_state=APPROVED for that canonical accepted record, source revision/doc hash/version hash/confirmation time. It does not expose document text, canonical private URL or confirmer identity. comments_status remains NOT_CONNECTED; publication_status remains UNKNOWN; APPROVE_VERSION and every real publication/optimization command remain disabled. This is a read of an already accepted canonical record, not authority to approve/publish a new one.

No mapping -> VERSION_DOCUMENT_BINDING_REQUIRED. No current canonical source or expired source -> precise NOT_CONNECTED reason, while unrelated entitled brand/usage remains usable. Missing selected document in a replacement source -> no history/different-document fallback. Wrong project/revision/contract/owner or non-accepted kind -> denial, not fake READY.

## Actual source entry and delta validation
Original protected import-change-authority -> original change_authority/document store -> existing signed GEO admission with exact optional ID -> original FULL factory -> authenticated geo/snapshot handler -> existing unchanged GEO runtime versions view. No second database/backend/provider, new table, key or config field.

Eight new Python cases use only original synthetic fixtures and real original signature importer, factory and full HTTP handler; all pass. They cover exact binding, actual source->handler projection, unsigned/customer substitution, source replacement, absent/expired source limited to this domain, stale current project revision, wrong kind and other-project signed source. The actual synthetic handler JSON is saved in delivery evidence and directly consumed by unchanged loadGeoRuntime/buildGeoView with six assertions. This is program-level integration, not real HTTP transport/browser or live canonical customer material.

Run python3 -B -m unittest tests.test_pr122_customer_geo_versions -v. Existing14/7 and old24/8 are reused, not rerun. No claim of full CI/SBOM/security scan/build or independent review. No production deployment/service config/real commands/Finance/paid/provider activity.

## Remaining exact real-data condition
Original canonical acceptance/contract source custodian and original signed GEO admission issuer must supply through their existing protected import channels the actual current ACCEPTED_VERSION record and matching version_document_id in the signed grant. The original schema already determines project/project_revision/contract/confirmed actor/time/document bytes and hashes. The executing model needs only non-secret references/completeness metadata, not private document text, signing key or personal details. Concrete custodian identity is not proved here; parent routes via the existing import-change-authority/Center maintainer, not a new Owner credential request.

Source selection/adaptation is implemented internally now. Missing real source bytes/mapping blocks only real version verification. Sampling/diagnosis, optimization, publication, comments, next-round and authoritative Finance entitlement export remain separate internal implementation/binding work, not a claim that all are done.

Recovery: new read-only module plus existing GEO admission optional field/call; no new schema, migration or live writes. Retaining an optional field in an already imported signed grant does not create a new version record or publish anything. No production data changed in this task.
