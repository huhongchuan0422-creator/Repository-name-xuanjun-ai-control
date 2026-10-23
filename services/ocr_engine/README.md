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
- Production candidate uses SecureSQLiteJobStore: sensitive job and confirmation payloads are encrypted with an externally supplied Fernet key; raw image bytes are not stored. Confirmation audit details are encrypted. The legacy SQLiteJobStore in api.py stores plaintext JSON and is test-only; never use it for customer data. Key custody/rotation, backup, deletion/retention and operational monitoring require deployment review.
- Restart tests create a fresh store and HTTP app over the same DB. Crash recovery must only run under exclusive lifecycle control; never let a second live worker mark another worker's job failed.

## Verification evidence
- Hosted Run 40007712096 passed after fixing test request fields. Reuse its verified model SHA/inference results.
- Hosted Run 40008433722 executed real Chinese synthetic business-license and ID-front images through OCR, HTTP submit/read/confirm, same-process fresh-store/fresh-app reconstruction, durable audit checks and concurrent duplicate submission. It did NOT prove a separate OS-process restart. A separate-process SQLite confirmation/audit/idempotency test was added in test_secure_store.py at Commit 9d4fe688abf186abea8106d9b28915eceffd09a2; its dedicated Hosted execution remains pending.
- Never use real identity documents for CI. No paid OCR API or server deployment.

## Model provenance / licensing
RapidOCR v3.9.2 source LICENSE and the fixed model-specific notice at https://github.com/RapidAI/RapidOCR/blob/4a3070f304467e6d426e78a82afea5cb1181f305/python/MODEL_LICENSES.md (Git blob 3f66af490abe83df801bfb8d1ea80eed7b0048ae) have been inspected. Sections 4–7 cover the exact three pinned artifacts in model_manifest.json, permit commercial use under Apache-2.0, and require license, attribution/copyright, modification notices, and any applicable NOTICE contents to accompany redistribution. The three hashes match the notice exactly and were rehashed in Hosted Run 40007712096. Source-level rights are now **VERIFIED for the listed artifacts**; release-bundle compliance remains pending until LICENSE-2.0.txt and this attribution notice are included in and checked against the actual distributable archive.

## Remaining external gates
1. Real existing identity/token verifier and application + attachment ownership callbacks, supplied by the owning community integration writer.
2. Release artifact packaging verification: confirm the actual distributable archive includes model_manifest.json, model_distribution/LICENSE-2.0.txt, model_distribution/NOTICE.md and any applicable upstream NOTICE; source-level license rights for the three pinned files are already verified.
3. Deployment-specific key custody/rotation, backup, retention/deletion, monitoring and load/rate/timeout settings.
4. Production deployment is not authorized by this document or a green Hosted run.

## Integration contract gaps — HOLD
The current attachment callback signature is `(principal, onboarding_application_id, attachment_id, content_sha256) -> {authorized: bool, content_sha256: str}`. It binds the bytes to a server-resolved original object hash, but does not yet bind `document_type` or an application revision/version. The current application callback returns only a boolean and does not pin a revision. Until those fields are added to durable job metadata and rechecked on GET/confirm/delete, replacement/revision-race protection is **HOLD**. The community integration owner must provide the actual trusted resolver and revision contract; this OCR branch must not invent or impersonate it.
