# OCR independent preview container candidate V1 — 2026-10-24

Status: SOURCE CANDIDATE ONLY / NOT BUILT / NOT INSTALLED / NOT STARTED.
This candidate does not authorize UK host access, persistent-volume creation, secret provisioning, network changes, or community source edits.

## 1. Immutable package/source binding

- OCR source baseline: cb28f605291cde6dc48a2d6431166211059dc595.
- Source Tree: 5e602e81e4e747fdc5b8743be916e75baa638e02.
- Existing PR: https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/139
- Formal package workflow: Run 40076963020, run #199; conclusion success and head SHA matches the source baseline above.
- Formal package artifact ID: 12553737114; name xuanjun-ocr-linux-x86_64-cp311-cb28f605291cde6dc48a2d6431166211059dc595.
- Obtainable artifact ZIP URL: https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/40076963020/artifacts/12553737114
- ZIP size: 245,668,446 bytes; ZIP SHA-256: d5142f25afdf6f48297545e504a201039b2d85608af6d16b3d9b5ddb3b6a81a9.
- Inner tar size: 245,599,357 bytes; SHA-256: 5d4ac9dad0badefaab20853cc4ceff0be9caf4c4501cebb4e318599007d662f6.
- Owner-side inspection reports 104 entries / 101 content hashes matching; 37 wheels, 46 Debian packages, 6 APT indexes, 3 models. Offline install/import evidence is from the completed run and owner-side verification, not a test executed by this candidate commit.
- NOT_RELEASE candidate artifact 12553801548 and diagnostics artifact 12553896031 are not substitutes for the formal package.

The formal archive contains runtime sources and offline assets; it does NOT contain a base image, Dockerfile, service installer, production callback adapter, or authorization to start a service. Container packaging/entrypoint in this candidate is separate source and must be bound to its own Git commit. No model or Debian package is re-downloaded or rebuilt.

## 2. Runtime candidate

- Fixed base: python:3.11-slim-bookworm@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199; CPython 3.11.17 / glibc 2.36 / linux-amd64.
- Proposed image label/name: xuanjun-ocr-preview:<candidate-source-sha>. This image does not yet exist.
- Proposed process: one Uvicorn worker, port 8080 inside a private container network; no host-published port and no host socket mount. Community backend may call it only over a private internal network after its owner supplies the trusted binding adapter and confirms the backend's actual network identity.
- Proposed non-root runtime UID/GID: 10001:10001. This is a candidate image identity, not a claim about the UK host or existing containers.
- Only proposed writable persistent mount: /var/lib/xuanjun-ocr, owner 10001:10001, mode 0700; DB path /var/lib/xuanjun-ocr/jobs.sqlite3. Do not create it until the owner approves the exact UK volume/path and retention/backup policy. The self-check does not create it.
- Model paths are read-only image assets at /opt/ocr-bundle/models/PP-OCRv6_det_small.onnx, /opt/ocr-bundle/models/PP-OCRv6_rec_small.onnx, and /opt/ocr-bundle/models/ch_ppocr_mobile_v2.0_cls_mobile.onnx. Pins are the exact three hashes in services/ocr_engine/model_manifest.json at source SHA cb28f605...
- Proposed runtime restrictions: read-only root filesystem, no privilege escalation, drop all Linux capabilities, no outbound network, no host PID/IPC/network namespace, no host Docker socket, and bounded temporary scratch space. These are target settings, not verified runtime facts.
- Candidate starting worker count is one. Upload limit in the API source is 8 MiB/image. CPU is supported; measured peak RAM, throughput, P50/P95, and safe concurrency are not available. Do not claim capacity until measured on the actual isolated target.

## 3. Existing source contract and launch limitation

At source SHA cb28f605, api.py exports create_app(...) as an app factory; it does not expose a ready-to-run module-level production app. Default construction fails closed unless OCR_SQLITE_PATH and OCR_ENCRYPTION_KEY are supplied. Production use additionally requires real injected callbacks:
- authenticate(bearer_token) using the existing trusted identity/token verifier;
- authorize_application(principal, onboarding_application_id) checking tenant and role ownership;
- authorize_attachment(principal, application_id, attachment_id, content_sha256, document_type, expected_application_revision=None) resolving the exact current authoritative binding and revision.

The repository explicitly says these callbacks are interfaces only and have not been connected to production. No fake token, fabricated tenant, boolean-only attachment callback, or demo community API is acceptable. The candidate entrypoint must refuse to bind/listen when the trusted adapter module or any required callback is absent or invalid.

## 4. Community integration acceptance, same-version requirement

The OCR side exposes the existing API contract from docs/development/XUANJUN_OCR_API_V1_20261024.yaml:
- POST /api/v1/ocr/jobs: multipart file, document_type, onboarding_application_id, attachment_id, plus Idempotency-Key.
- GET /api/v1/ocr/jobs/{job_id}: same tenant and original subject, or explicit ocr:admin; rechecks current application/attachment authorization.
- POST /api/v1/ocr/jobs/{job_id}/confirm: revision, fields, application_revision, provider_version echo, plus Idempotency-Key.
- DELETE /api/v1/ocr/jobs/{job_id}: authorized cancellation/deletion behavior per the source contract.

Supported OCR document types are business_license and id_front only. ID back, bank cards, permits, storefront/interior/cashier photos are not supported OCR types. Every field is a suggestion; human confirmation is mandatory; authenticity_verified remains false. OCR failure must fall back to manual entry, not block onboarding.

Acceptance must use the same immutable OCR package/source version and the actual community backend API/field contract:
1. Chinese synthetic business-license and ID-front inference; exact model hashes; no real personal documents.
2. HTTP submit/read/confirm over the real internal network; invalid/missing token denied; missing ocr:use denied; cross-tenant and wrong-subject reads denied; revoked or changed attachment/application revision denied; replay with same key/payload idempotent; same key with changed tuple conflicts.
3. Durable encrypted SQLite and audit survive process restart on the approved persistent volume; no raw image bytes or sensitive fields in logs.
4. Community backend calls the private OCR service and maps confirmed fields to the existing onboarding draft only after human confirmation and exact provider/application revision checks. Mini Program calls the community backend, not the OCR container directly. No community source changes are included here; its original unique writer must perform that integration.
5. Verify UI/manual fallback, tenant isolation, rate/size limits, failure/restart recovery, and consistent field rules on Web and Mini Program. WeChat review/release remains a separate step.

Existing Chinese synthetic HTTP/SQLite evidence and the formal offline package evidence can be reused as source evidence. They do not prove the proposed container image, actual UK deployment, actual identity adapter, community API wiring, or WeChat release.

## 5. Install/start/stop/recovery boundary

Preparation only; no host actions have been performed. Once separately approved, the operator would:
- Obtain artifact 12553737114 from the URL above and verify ZIP SHA before extraction; verify inner tar SHA and the exact bundle manifest before using it as the Docker build context.
- Build an image offline from the pinned base plus the already verified bundle; validate the complete locked Debian set and wheelhouse without network fallback. Image build is not service installation or start.
- Provision the externally owned encryption key through the approved secret mechanism; never generate, print, read back, or commit it in this task.
- Obtain a read-only inspection of the actual UK container runtime, network, capacity, storage policy, and existing lifecycle controls before selecting a real container/volume/network name.
- After a separate Owner approval, create only the approved volume and private network, start one non-root container, and verify health and logs with sensitive-field redaction. Stop/restart only through the approved existing lifecycle manager. Do not add a second writer or uncoordinated recovery worker.
- Recovery must preserve the SQLite database and encrypted audit. No automatic deletion/recreation of DB, key, volume, or container state; missing/mismatched key or binding state is HOLD, not reset-to-empty.

## 6. Explicit blockers and owners

1. UK target runtime/container/network/volume identifiers and read-only capacity/status: UK infrastructure owner; NOT inspected in this task.
2. Trusted identity verifier and real application/attachment ownership callbacks, including current scope and provider-version source: community integration owner; not present in this repository candidate.
3. Approved secret injection/custody/rotation and exact DB retention, backup, deletion, and restore policy: security/operations owner; no secret read or generation performed.
4. Existing community backend service endpoint, deployment/network topology, and exact same-version onboarding field mapping: original community unique writer; no community source edited.
5. Container build/run validation and measured resource envelope: pending an authorized non-production build/test environment; no Docker build or service start performed.

Status remains SOURCE_CANDIDATE / NOT_BUILT / NOT_INSTALLED / NOT_STARTED / COMMUNITY_INTEGRATION_NOT_CONNECTED. A green source CI or artifact build cannot change these statuses.