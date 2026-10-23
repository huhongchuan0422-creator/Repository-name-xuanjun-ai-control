# 玄钧AI新 OCR Gateway — development handoff

## Supported first-release document types
- `business_license`: local RapidOCR inference plus heuristic field extraction.
- `id_front`: local RapidOCR inference plus heuristic field extraction.
- `id_back`, bank card, food/business permits: not supported until separately implemented/tested.
- Storefront, interior and cashier photographs are not OCR document types and must be rejected.

## HTTP contract
See `docs/development/XUANJUN_OCR_API_V1_20261024.yaml`.
- `POST /api/v1/ocr/jobs`: multipart `file`, `document_type`, `onboarding_application_id`, `attachment_id`; `Idempotency-Key` header.
- `GET /api/v1/ocr/jobs/{job_id}`: same tenant and original subject, or explicit `ocr:admin`.
- `POST /api/v1/ocr/jobs/{job_id}/confirm`: JSON `revision`, `fields`; mandatory `Idempotency-Key`.
- Every recognized field is a suggestion. User confirmation is mandatory; `authenticity_verified=false` always.

## Identity / ownership injection contract (not connected to production)
Construct `create_app(authenticate=..., authorize_application=..., authorize_attachment=..., store=...)`.
- `authenticate(bearer_token) -> Principal(subject, tenant_id, permissions)` must call the existing trusted identity/token verifier. Default is fail-closed (401); no test token belongs in production.
- `authorize_application(principal, onboarding_application_id) -> bool` must check the existing application belongs to the principal/tenant and that their role can submit it.
- `authorize_attachment(principal, onboarding_application_id, attachment_id) -> bool` must verify the attachment record belongs to that application and tenant, is an approved upload object, and is readable by this actor. Check server-side object metadata; never trust client-supplied IDs alone.
- Missing callbacks reject submission (403). Do not create a new customer identity, tenant mapping, attachment store, or fake success callback to bypass existing community onboarding.
- These callbacks are interfaces only. Real community identity/application/attachment callbacks have **not** been injected or verified. Do not connect real user documents until the owning community writer supplies and verifies those bindings.

## Persistence and replay
- Default app construction requires explicit absolute `OCR_SQLITE_PATH` and externally supplied `OCR_ENCRYPTION_KEY`; missing values fail closed.
- Use `SecureSQLiteJobStore`; `JobStore` and `SQLiteJobStore` are test-only adapters, not production stores.
- Submission idempotency is durable, tenant-scoped and binds actor/application/attachment/document type/content hash. Same key + same payload replays the same job; same key + different payload conflicts.
- Confirmation is transactionally idempotent; same key/payload replays the same response; changed payload conflicts. Confirmation revision is monotonic and confirmed values cannot be overwritten by OCR retry.
- Sensitive payloads are encrypted with an external Fernet key; raw image bytes are not stored. Audit confirmation events are encrypted. Key custody/rotation, backup, deletion/retention and operational monitoring require deployment review.
- Restart tests create a fresh store and HTTP app over the same DB. Crash recovery must only run under exclusive lifecycle control; never let a second live worker mark another worker's job failed.

## Verification evidence
- Hosted Run 40007712096 passed after fixing test request fields. Reuse its verified model SHA/inference results.
- New expanded Chinese HTTP E2E adds a generated Chinese synthetic business license and synthetic ID front, confirmation replay, a fresh store/app restart, durable audit verification and concurrent duplicate submission. Its result must be taken from its own latest Hosted run; source code alone is not proof.
- Never use real identity documents for CI. No paid OCR API or server deployment.

## Model provenance / licensing
RapidOCR v3.9.2 source LICENSE and the fixed model-specific notice at https://github.com/RapidAI/RapidOCR/blob/4a3070f304467e6d426e78a82afea5cb1181f305/python/MODEL_LICENSES.md (Git blob 3f66af490abe83df801bfb8d1ea80eed7b0048ae) have been inspected. Sections 4–7 cover the exact three pinned artifacts in model_manifest.json, permit commercial use under Apache-2.0, and require license, attribution/copyright, modification notices, and any applicable NOTICE contents to accompany redistribution. The three hashes match the notice exactly and were rehashed in Hosted Run 40007712096. Source-level rights are now **VERIFIED for the listed artifacts**; release-bundle compliance remains pending until LICENSE-2.0.txt and this attribution notice are included in and checked against the actual distributable archive.

## Remaining external gates
1. Real existing identity/token verifier and application + attachment ownership callbacks, supplied by the owning community integration writer.
2. Model-weight redistribution license evidence.
3. Deployment-specific key custody/rotation, backup, retention/deletion, monitoring and load/rate/timeout settings.
4. Production deployment is not authorized by this document or a green Hosted run.
