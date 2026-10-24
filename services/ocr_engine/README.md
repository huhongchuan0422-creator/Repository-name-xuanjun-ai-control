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
- `authorize_attachment(principal, application_id, attachment_id, content_sha256, document_type, expected_application_revision=None) -> dict` must return `authorized`, the exact `content_sha256`, exact `document_type`, authoritative `application_revision`, and optional canonical `provider_version`. On submit (`expected_application_revision=None`) it must resolve the current authoritative revision itself. On later GET/confirm/DELETE, the frozen revision is passed back and must still match. A boolean-only callback is insufficient.
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

## Trusted source binding and confirmation snapshot — production HOLD
The trusted resolver signature is `authorize_attachment(principal, application_id, attachment_id, content_sha256, document_type, expected_application_revision=None) -> {authorized, content_sha256, document_type, application_revision, provider_version?}`.
- On submission, `expected_application_revision=None`; the resolver must obtain the authoritative current application revision from the owning service, never from client input. It must return the exact uploaded SHA, exact supported document type, canonical non-negative application revision, and optionally a canonical non-negative provider version.
- Canonical versions are non-negative integers or dot-separated numeric strings without leading zeros (except `0`). Booleans, negative values, floats and noncanonical strings fail closed.
- The encrypted job and submit idempotency fingerprint persist `attachment_id`, `document_type`, `content_sha256`, `application_revision`, and optional `provider_version`. Reusing the same idempotency key with a changed tuple conflicts.
- The confirmation request must echo `application_revision` and optional `provider_version` exactly as shown to the human reviewer. The server compares them with the stored tuple and re-resolves current trusted values before the transaction. The body is an echo, not proof of authority.
- Confirmation transaction stores the confirmed fields, `confirmation_revision`, and immutable `confirmed_binding` tuple together; the same tuple is included in the encrypted confirmation audit and confirmation-idempotency payload. Mismatches roll back. GET returns the exact confirmed fields/revision and confirmed tuple.
- GET/confirm/DELETE recheck current application and attachment authorization against stored content SHA, document type and application revision. If a provider version was frozen, it must also match. Missing legacy application binding fails closed; no default revision is inferred.
- Legacy jobs without `provider_version` remain available for OCR result review and manual confirmation when their application/attachment binding remains valid. They return `provider_version: null` and `shared_writeback_eligible: false`; they must not write to shared drafts. No silent migration or latest-version substitution is permitted.
- `application_revision` is the source application's revision, distinct from `confirmation_revision`, the user's reviewed-field revision. Provider version is optional, but a shared-draft write requires a trusted provider version.
- Tests use synthetic resolvers and pre-registered synthetic image SHA values only. They are not production identity/ownership proofs. The community integration owner must provide the actual trusted token verifier, application resolver and attachment resolver. Missing callbacks and missing `ocr:use` deny access; no identity mapping is fabricated.


## Offline asset preflight (does not start a service)
- Dependency pins: `requirements.txt` (RapidOCR 3.9.2, ONNX Runtime 1.31.0, FastAPI 0.115.12, Uvicorn 0.34.0, cryptography 46.0.3 and supporting pins). This is a pinned requirements list, not a fully resolved cross-platform lockfile; a platform-specific wheelhouse/lock still needs to be produced for air-gapped installation.
- Model provenance and exact SHA-256 pins: `model_manifest.json`; required redistribution notices: `model_distribution/LICENSE-2.0.txt` and `model_distribution/NOTICE.md`.
- Expected model files are staged externally at absolute paths via `OCR_DET_MODEL_PATH`, `OCR_REC_MODEL_PATH`, `OCR_CLS_MODEL_PATH`; `OCR_MODEL_SHA256` must be supplied to the process environment as a JSON-serialized string containing exact manifest pins (for example, serialize the `{det, rec, cls}` object to JSON before setting the environment variable). The JSON Schema describes the logical object shape only; there is no automatic schema-to-environment loader. The runtime never downloads weights. Hosted CI verified upstream bytes, but this repository does not contain the cached ONNX weight files; a separate approved offline model cache/package is still required.
- External configuration schema: `deployment_config.schema.json`. Required values include absolute `OCR_SQLITE_PATH`, externally provisioned `OCR_ENCRYPTION_KEY`, model paths and hashes. Never commit or print key values; do not generate a production key as part of preflight.
- Read-only preflight: `python services/ocr_engine/startup_selfcheck.py --offline-assets-only`. It checks required env presence, Fernet key format, lexical DB parent chain (rejecting symlink components), non-sticky group/world-writable ancestors, existing DB file permissions, and model file SHA-256 without creating the database, key, directories, or service. For an absent DB it reports `DB_ABSENT_PARENT_CHAIN_VERIFIED_NOT_READY`; this does not certify future creation/startup readiness. `--production-readiness` intentionally returns HOLD until trusted identity/application/attachment callbacks are wired by the owner.
- Resource boundary: inference is CPU-capable via ONNX Runtime; this source has no measured production throughput or peak-RAM benchmark. Upload limit is 8 MiB per image. Set worker count conservatively (start with one worker) until representative synthetic load and memory tests are measured. No GPU is required by the current pinned runtime.
- Operational boundary: these assets are not an installable release archive and do not enable a listener. Production still requires trusted callbacks, external key custody/rotation, protected persistent storage, backup/retention policy, timeout/rate-limit review, and an explicit deployment approval.

## Offline bundle build entry (source only; build is opt-in)
- Entry: `python services/ocr_engine/build_offline_bundle.py --target-platform <exact-reviewed-platform> --lock-json <platform-lock.json> --wheelhouse <staged-wheelhouse> --model-cache <staged-models> --output <absolute-new-archive-path>`.
- Default is closed: without `--execute-build`, it reports HOLD and creates no archive. This task did not execute the build, download assets, install dependencies, dispatch a workflow, run inference, or start a service.
- The external lock must explicitly provide `target_platform`, `python_implementation`, `python_version`, `abi`, `target_tags`, `requirements_sha256`, and exact wheel filenames/SHA-256. Target platform remains **UNSPECIFIED**; do not infer it from GitHub Ubuntu or legacy Python 3.6 hosts.
- Every wheel is checked by SHA-256, filename compatibility tags, and internal `.dist-info/WHEEL` Tag metadata. `py3-none-any` is accepted only when the internal tag agrees. Platform-specific wheels must intersect the explicit lock's target tags; e.g. cp312/win_amd64 is rejected for a Linux CPython 3.11 target.
- The builder freezes source/model/wheel/license/NOTICE/lock inputs before packaging, checks the final archive's exact member set and hashes against that frozen snapshot, and verifies embedded lock/manifest platform bindings. An A→B→A source race cannot pass merely because the external file is restored after writing a changed tar member.
- Publication uses atomic no-clobber hard-link creation, not `os.replace`; if another process creates the target name first, the build fails and preserves the winner. Output parent must already exist and be protected. Existing archives are never overwritten.
- The archive places the model manifest at `services/ocr_engine/model_manifest.json`, alongside `startup_selfcheck.py`'s default lookup path.
- Required platform lock, compatible wheelhouse, and exact three-model cache are still absent. The model pins and Apache license/NOTICE are fixed in `model_manifest.json`, `model_distribution/LICENSE-2.0.txt`, and `model_distribution/NOTICE.md`. The builder has no network or dependency-resolution code.
- Synthetic gate tests: `python -m unittest services.ocr_engine.test_offline_bundle -v`. They cover platform/tag mismatch, internal wheel metadata mismatch, missing/tampered models, tampered wheels, lock/requirements mismatch, missing attribution, default-off behavior, archive TOCTOU, and output-name race. Tests use synthetic artifacts and do not produce the real release archive.
- A real archive build and member-by-member audit are a separate future action requiring the Owner to select the exact target platform and explicitly authorize execution.
- The current builder also rejects output collisions before reading inputs, then uses atomic no-clobber publication to close the remaining name race. The final tar is verified against the frozen pre-build member digest set; source-file revalidation alone is not treated as archive integrity evidence.

## Manual Hosted platform-package build (default disabled)
- Existing workflow: `.github/workflows/ocr-engine-tests.yml`; no new workflow or service was added.
- Target: `linux/amd64`, CPython `3.11.17`, ABI `cp311`; official base `python:3.11-slim-bookworm@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199`, expected image/config ID `sha256:c8bff6acecbf3f8b9f87bc3193032b39ead42bcc39fb76a4875ebd89975874ee`.
- The build job only runs for a manual dispatch where `build_enabled=true`, on the exact OCR branch, and only if the explicit `source_sha` equals the workflow run's `GITHUB_SHA`. Checkout uses that same SHA. Default is `false`; no build job runs by default.
- The job measures Python patch, SOABI, glibc and compatible tags inside the pinned image. It resolves binary wheels inside that same image, records each wheel SHA-256 and the hash of the pinned requirements input, fetches only the three fixed upstream model URLs and checks their manifest hashes, then performs an offline `pip install --no-index` plus import check in the same base image with networking disabled. It does not start the service or run OCR inference.
- The bundle builder validates the lock's exact base manifest/config IDs, CPython patch/ABI/SOABI, glibc evidence, target tags, wheel internal metadata, model hashes and redistribution files. Artifact includes the archive, platform lock and SHA256SUMS, retained 14 days.
- No manual dispatch has been triggered by this work. This is source preparation only; no actual platform lock, wheelhouse, downloaded model cache or archive exists until an explicitly enabled Hosted run completes.
- Exact future dispatch inputs for root review only: `build_enabled=true`; `source_sha=<the exact reviewed branch HEAD SHA at dispatch>`. The selected ref must be `docs/self-hosted-ocr-architecture-20261024`. The source SHA is intentionally not hard-coded here because it must match the final reviewed HEAD at the time of dispatch.

## OpenCV runtime candidate after first pinned-base import failure
- The failed approved build (Run 40065736418) passed pinned-base, wheel resolution, fixed model SHA checks, offline pip install and `pip check`, but failed `import cv2` because `libxcb.so.1` was unavailable. It is not a successful package.
- The dependency input is changed from `opencv-python-headless==4.11.0.86` to the single official distribution `opencv-python==4.11.0.86`; RapidOCR 3.9.2's upstream metadata is not modified and `--no-deps` is not used. Synthetic CI asserts exactly one OpenCV distribution in the pinned requirements.
- The manual Hosted candidate flow now resolves Debian shared-library closure for the fixed Bookworm base using its configured official apt sources, downloads the package closure without installing it into the runner host, records each `.deb` package/version/architecture/SHA-256 in `system-deb-lock.json`, then verifies that closure is installable offline in a disposable container with network disabled before the OpenCV import and `pip check`.
- The verified Debian closure and lock are included in the offline archive via `--system-deb-cache`. This is an independently hash-locked runtime layer inside the archive; its exact versions and hashes are generated only by the future approved Hosted candidate run, not guessed in source.
- Failed runs retain `ocr-wheelhouse`, `ocr-model-cache`, `ocr-deb-cache`, any generated platform lock, and a SHA-256 candidate-input manifest in an artifact explicitly named `candidate-inputs-not-release`. This artifact is for reuse of verified immutable inputs only and must never be represented as an installable/successful package. The release artifact remains success-only.
- No rerun or dispatch was performed for this source change. The next run requires separate root review; it will be a candidate build, not deployment or service enablement.
