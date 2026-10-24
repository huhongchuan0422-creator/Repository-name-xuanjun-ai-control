# OCR independent preview container candidate V1 — 2026-10-24

## Current source review status (2026-10-24; authoritative for this candidate)

- **Fixed OCR preview container source candidate:** Commit `ae92a0255ed3ab498555789b1a92b0e531758131`; Tree `15500ad6631af4d690c087585e007dfb0c9d10fa`. The document-only alignment commit, if any, is separate and **does not replace** this immutable source candidate.
- **Source review:** `SOURCE_SCOPE_PASS` as reported in the Owner-provided independent root review for **this exact ae92 source/tree**: 54 synthetic tests PASS, Python compile PASS, and three targeted root counterexamples closed; no remaining source-fix items. This is **independent source/isolated synthetic review evidence provided by the Owner**, not a new test run by this documentation update and not a new Hosted/container or UK site acceptance. Source reference: [ae92 commit](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/commit/ae92a0255ed3ab498555789b1a92b0e531758131); original development/evidence thread: [PR139](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/139). The independent root audit's separate receipt URL was not supplied here; do not invent one.
- **Formal offline package remains a distinct, unchanged version:** `cb28f605291cde6dc48a2d6431166211059dc595` / Tree `5e602e81e4e747fdc5b8743be916e75baa638e02`, success [Run 40076963020](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/40076963020), **formal artifact 12553737114**. Its successful offline packaging/dependency/import evidence is **not** evidence that the later ae92 container image was built or started.
- **Still `NOT_EXECUTED` / `NOT_VERIFIED`:** actual Dockerfile parser/image build, runtime image, read-only rootfs and trusted-binding mount in a real container, container restart/capacity, UK install/start/port or persistent-volume access, real authentication/key provisioning and tenant-scoped callbacks, UK community backend/OCR same-version integration, Mini Program-to-backend integration, and community E2E. `/openapi.json` health is liveness only, not authorization/inference/E2E proof. No site execution or deployment authorization is implied.
- **Historical content below remains intentionally preserved.** Earlier `SOURCE CANDIDATE`, floating-head placeholders and `NOT_EXECUTED` statements record the status *at the time those preparation notes were written*; they must not override the fixed ae92 source-review result above, and must not be retroactively rewritten as container tests passing. The historic failure records and external gates remain valid.

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

The formal archive contains runtime sources and offline assets; it does NOT contain a base image, Dockerfile, service installer, production callback adapter, or authorization to start a service. Container packaging/entrypoint are separate candidate source files: services/ocr_engine/Dockerfile.preview and services/ocr_engine/container_entrypoint.py. Their final source binding is the HEAD recorded below. No model or Debian package is re-downloaded or rebuilt.

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
## 7. Candidate packaging files and exact offline build contract

- Dockerfile candidate: services/ocr_engine/Dockerfile.preview.
- Fail-closed launcher candidate: services/ocr_engine/container_entrypoint.py.
- Debian installer reused from the audited source: services/ocr_engine/install_deb_closure.py.
- The Dockerfile expects a directory named bundle/ at repository root, containing the exact inner tar contents from the formal artifact. It verifies wheel set/SHA and all three model SHA values before offline installation; it invokes the audited installer against the locked Debian set, installs only from the wheelhouse with --no-index, and runs pip check. No apt-get, pip network fallback, model download, or inference is part of the image build.
- Before any build, the operator must securely retrieve artifact 12553737114, verify the ZIP and inner tar hashes stated in Section 1, safely extract the tar into bundle/, and verify offline-bundle-manifest.json. This candidate has not downloaded or extracted those bytes itself.
- Candidate build invocation after bundle/ is verified and the pinned base image is already locally available:
  docker build --network=none --build-arg OCR_CONTAINER_SOURCE_SHA="$(git rev-parse HEAD)" -f services/ocr_engine/Dockerfile.preview .
  This command binds the image label to the checked-out candidate commit. Do not run this command as part of this task.
- The launcher imports a trusted adapter module from the externally mounted /opt/ocr-integration path. It requires callables named authenticate, authorize_application and authorize_attachment. Missing module/callback, missing DB/key/model configuration, bad key format or model SHA mismatch exits before binding a listener. It does not create keys, database files, host directories, or callback behavior.
- The image creates only its internal /var/lib/xuanjun-ocr directory during image construction, owned by UID/GID 10001. At runtime this path is intended to be replaced by the separately approved persistent mount; runtime root filesystem should be read-only. This is image-source behavior, not a host-side volume creation.
- This build/source candidate has not been compiled, built, started, or run in Docker. Dockerfile syntax, artifact extraction, offline pip/dpkg, health check, non-root permissions, graceful stop/restart and HTTP contract remain NOT_EXECUTED until a permitted isolated build environment is available.

## 8. Current candidate source binding

- Dockerfile commit: 478fcd02ee6542f9974e2ccfe7c13fd79fbf1946.
- Launcher commit: 6d0617e8be5e58bc95298adb4c7a3e6e46946fc3.
- Final candidate HEAD is verified after this document update; use only the exact branch HEAD and verify the formal artifact hashes before any separately approved build.

## 9. Security review follow-up — source only

This revision closes four source-level findings from the independent review:
1. The Dockerfile model-pin environment value is single-quoted as one key=value token so the embedded JSON double quotes survive Dockerfile parsing; the synthetic test tokenizes the ENV instruction and parses the extracted value with json.loads. This is not a Docker daemon/parser integration test.
2. The launcher now requires check_environment().database == EXISTING_PROTECTED_FILE_VERIFIED, then opens the existing database read-only, runs SQLite integrity_check, checks required schema tables and verifies the encryption-key binding. Missing DB, empty/uninitialized schema, corruption, wrong key, unsafe permissions or read-only inspection errors HOLD before create_app()/Uvicorn. It does not create, migrate, or reset a database.
3. Trusted bindings are loaded from one regular .py file under the supplied absolute read-only integration root. Symlinked path components, symlinked source, noncanonical/escaped module origin, a same-name preloaded sys.modules entry, absent callbacks and incompatible callback signatures are rejected. Required positional call shapes are authenticate(1), authorize_application(2), authorize_attachment(6). No Principal is fabricated.
4. The base image is now a literal FROM digest and cannot be overridden with an ARG. OCR_CONTAINER_SOURCE_SHA must be nonempty, lowercase hex and exactly 40 characters. The floating Dockerfile frontend syntax directive was removed; the build still requires an already-installed local BuildKit using its built-in frontend and the exact pinned base image already present locally. No frontend or base-image download is authorized in this task.

Synthetic test coverage added for ENV tokenization/JSON parsing, fixed base and source-SHA gates, absent and ready encrypted DB behavior/key mismatch, symlinked binding source, and wrong callback arity. These are source-level tests and have NOT been executed in this environment.

The formal runtime package remains source cb28f605291cde6dc48a2d6431166211059dc595; the independent container candidate has a different source commit. The package itself is reused without rebuilding. The image build, actual Docker lexer/frontend, read-only rootfs/capability restrictions, mounted integration path, UK network/volume, service lifecycle, Chinese HTTP inference in the container, real authentication/tenant isolation, community backend integration and Mini Program same-version E2E remain NOT_EXECUTED.

## 10. Four-group source patch result

The four review groups are implemented in the current candidate source:
- Dockerfile ENV carries model pins as one single-quoted JSON value; a synthetic lexer-token/JSON parse test was added. This test has not been run, and actual Dockerfile parser behavior remains unverified without a local BuildKit/Docker environment.
- The launcher rejects an absent/unready database before app construction. It checks the existing database read-only, validates SQLite integrity and required tables, and verifies the existing database key check using the same HMAC derivation as SecureSQLiteJobStore. It never initializes, migrates or replaces the DB.
- The trusted adapter must be a non-symlink single-file module beneath an absolute root with no symlink path components or '..' traversal; spec and loaded module origin are checked against the resolved root; preloaded same-name modules and callback signature mismatch are rejected.
- FROM is a literal pinned digest with no overridable base ARG. OCR_CONTAINER_SOURCE_SHA is required to be lowercase 40-character hex. The floating syntax frontend line is removed; use only a locally available BuildKit built-in frontend and a locally cached pinned base, with no frontend/base pull during the build.

Additional synthetic tests cover missing database preventing app construction, existing protected DB/key binding, wrong key, symlinked module, preloaded module name, bad callback arity, and Docker ENV tokenization. All such tests are currently NOT_EXECUTED because this session has no connected local checkout/test runner and new Hosted dispatch is explicitly prohibited.

Current source binding must be read from the branch ref; this document is not itself an installation authorization. No server/secret/port/volume/real document action has been performed.

## 11. Second-pass review: database schema and integration mount

The database readiness gate now checks the existing SecureSQLiteJobStore schema read-only rather than trusting table names alone. It compares each required table's ordered column names, declared types, NOT NULL flags, primary-key ordinals and defaults; verifies the ocr_audit AUTOINCREMENT contract; verifies the ocr_jobs UNIQUE(tenant_key, idem_key) declaration; verifies idx_ocr_tenant and idx_ocr_audit_job column definitions; and verifies the required unique indexes for job idempotency, confirmation idempotency, rate windows and audit-detail primary key. Integrity, schema, key-binding or permission mismatch is HOLD; no schema migration/repair or create_app call occurs before these checks pass.

Trusted binding loading now reads /proc/self/mountinfo and resolves the deepest mount covering both the configured integration root and its exact module file. Both must be observed read-only. Unknown/missing mount info, read-write mount, symlink path component, traversal, non-regular source, non-root-owned path, group/world-writable root/source, escaped origin, preloaded module, or invalid callback signature fails before module execution. The root/source owner/mode check is read-only and does not chmod/chown anything. A synthetic mount-checker test asserts a read-write result is rejected before the fixture module's marker side effect; a synthetic read-only result permits loading only after both root and source checks. Synthetic mount state is not proof of actual Docker mount flags.

Added source tests:
- genuine SecureSQLiteJobStore-created DB passes the schema/key check;
- same-name fake tables with wrong columns fail;
- a dropped/replaced required index fails;
- main returns HOLD and never calls create_app for schema mismatch;
- writable integration root/source fail;
- a read-write mount stub prevents module execution, while a read-only stub checks root and source before the fixture executes.

These tests have NOT been executed in this session. No actual Docker mount or UK target was inspected. The runtime mount must be proven read-only from the actual container's mount table during a separately approved field test; a declared read-only setting or synthetic stub is not sufficient.

## 12. Exact schema/mount follow-up revision

The read-only schema validator now compares the six existing tables against the column definitions used by SecureSQLiteJobStore at the immutable cb28 source, including declared type, NOT NULL, primary-key ordinal and default; verifies AUTOINCREMENT on ocr_audit; verifies the declared job UNIQUE(tenant_key, idem_key); checks idx_ocr_tenant and idx_ocr_audit_job exact columns; and verifies the unique indexes for submit idempotency, confirmation idempotency, rate windows and audit details. A correct key-check row and PRAGMA integrity_check no longer make a table-name-only impostor READY.

The integration adapter loader now requires the actual deepest mount entry covering both root and module file to report read-only in /proc/self/mountinfo. Mountinfo escape sequences are decoded; missing/unknown mount state is HOLD. Root and source must be root-owned, non-symlink, expected file/directory types, and not group/world writable. It never changes permissions. Synthetic tests include a real SecureSQLiteJobStore-created database, wrong-column impostor tables, wrong required index, a main-path assertion that create_app is not called on schema failure, writable mode rejection, a read-write mount stub whose module marker must remain absent, a read-only stub whose root/source checks must precede module execution, and parsing of synthetic mountinfo ro/rw flags.

Current tests remain NOT_EXECUTED. This is source-level coverage only; no local runner or authorized Hosted run was available. The actual UK/container mount must still be inspected at runtime. Current candidate HEAD is the exact branch ref, not the immutable formal package source; formal package cb28f605... remains unchanged.
