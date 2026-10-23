# 玄钧AI新 OCR Gateway — isolated development candidate

## Verified evidence
- GitHub-hosted Run 40000857097: dependencies installed, three official pinned ONNX models rehashed SHA256 OK, **real RapidOCR** successfully read one generated in-memory synthetic English image; 12 module tests and 8 governance OCR tests passed. This is **not** Chinese ID/license image accuracy validation.
- GitHub-hosted run 40001530594 covers later persistence/ownership hardening and must be separately checked; do not reuse the prior green as the current verdict.
- Source license: RapidOCR v3.9.2 LICENSE (Apache-2.0) inspected. MODEL_LICENSES.md under the same tag was NOT_FOUND. Model-weight redistribution/commercial bundling requires separate license verification.

## HTTP interface
See `docs/development/XUANJUN_OCR_API_V1_20261024.yaml`. Available **code** exposes:
- POST `/api/v1/ocr/jobs`: image + onboarding id + supported doc type + idempotency header
- GET `/api/v1/ocr/jobs/{job_id}`: only owner or tenant OCR admin may see result
- POST `/api/v1/ocr/jobs/{job_id}/confirm`: user-reviewed fields, monotonically increasing revision

Supported parsers: `business_license`, `id_front`. Others explicitly fail, including storefront/interior/cashier photographs. `authenticity_verified` always false. OCR output is suggestion only.

## Fail-closed initialization
Application must inject its **existing real** bearer token verifier (`authenticate`) and onboarding ownership callback (`authorize_application`). The default verifier denies all; without ownership callback submission responds 403. Production-like initialization with no explicit store requires absolute `OCR_SQLITE_PATH`; absent path raises `OCR_SQLITE_PATH_REQUIRED`. An explicitly injected `JobStore` is **test-only in-memory**.
No listener or customer identity provider was deployed/configured.

## Known blockers for production
- SQLite currently stores suggested and confirmed personal data in plaintext. Requires encrypted storage/key management and retention/deletion implementation **before actual customer material**.
- Idempotency-Key length validated but full key-binding/replay conflict semantics are incomplete. Implement atomic idempotency contract and cross-process safety.
- SQLite schema is local prototype, lacks migration, multi-worker lease/recovery, persistent audit and full HTTP restart/concurrency E2E.
- Upload magic/size and core decode/pixel checks exist, but gateway needs complete image safety, scheduling, timeout and rate limiting.
- User-confirmation flow must be integrated by the original community W4 writer; OCR author must not modify W4 source.
- Model license notifications/redistribution status unresolved. Do not package model weights commercially.

No real IDs, licenses, paid APIs, new credentials, production server or self-hosted Runner have been used.
