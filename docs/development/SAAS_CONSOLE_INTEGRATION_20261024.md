# SaaS Console Integration 2026-10-24 — V5

## Fixed anchors

- PR122 customer source: `4dc5e349243d5fd277807c0c023281118d6df9d6` / tree `66b45dc175afa7ecf4347afcbec49455dd4d91c8`.
- Do not mix with PR122 head `cd348c77506e07ba9516a869b8fe1e66597a6e69`.
- Prototype handoff SHA256: `2e211190c0d6edb6f2861bd860cbe9b03e27da92cb629c49277b1d4ab4ea5b62`.
- Final 8-stage specification SHA256: `5049d4f8dc9fe555492338c00afee4ab77c08d29557e52340660426e78330037`.
- Traceability CSV decompressed-byte SHA256: `496624feab3ba3259e1e9bec78b07ecf1b54118b52a37ec2ed7aca7a13feb209`.

The repository carries the exact CSV bytes as deterministic gzip at `clients/saas-console/spec/03_PAGE_TRACEABILITY.csv.gz` and the exact 69-row/26-field projection as `prototype-page-map.json.gz`. The small `prototype-page-map.json` is only a carrier manifest. Tests gunzip both artifacts, recompute the fixed CSV SHA, and compare every page and all 26 fields including `owner_gap_task`. Existing `real_verified=NO` and HOLD gates are preserved.

## First product slice

No second identity system, database, project ledger, payment backend, task registry or preview engine is created.

- CUS-005/006: `/me` project membership, project metadata, checklist/requirements, preview/case/message read model.
- CUS-012/013: authoritative private preview, version-bound feedback, original case history, server delivery update and version retest.
- CUS-014 formal whole-project acceptance remains HOLD; `RETEST_ACCEPTED` is never formal acceptance.

## Preview/update contract

4dc `page_updates` first validates the supplied preview version and then returns only deliveries with `after_sha256 == version`. The UI therefore submits feedback against V1, rereads authoritative `previews/{project}`, waits until the same path is V2, calls `change_updates` with V2, displays `before_sha256` and `after_sha256` separately, and retests using exact project/case/revision/page/V2/delivery SHA/action. The old fake V1→V2 positive path is removed.

## Identity / CSRF

The console reuses 4dc login/logout/session semantics. The session token stays HttpOnly/SameSite; only the returned CSRF value is stored in `sessionStorage`. A valid cookie with no tab-local CSRF may read `GET me`, but the login form stays visible because writes require explicit re-login. No token or CSRF is derived from the cookie.

4dc maps `AUTH_REQUIRED` to HTTP 403. For an active-operation 403, the frontend performs read-only `GET me`: if `me` also rejects 401/403, the session is treated as invalid; if `me` succeeds, identity is still valid and the event is treated as project/write denial, with the authorized project list refreshed. A stale 403 from a previously selected project is generation/project guarded and cannot clear the new project.

Successful logout clears local CSRF and reports success. Transport-unknown logout clears local write capability for safety but reports **unknown**, never successful logout.

4dc has no reviewed CSRF recovery endpoint for a new tab. That remains a backend HOLD; current safe behavior is explicit re-login for write capability.

## Async isolation

Project loads and Q&A/feedback/update/retest mutations capture generation + project. After every await, success/failure DOM changes are allowed only if that context is still active. Tests cover late A success and late A 403 after switching to B, so A cannot reopen or clear B. Project switching clears metadata, requirements, previews, cases and messages before new data is rendered.

## Legacy UNKNOWN reconciliation

Deployed `change_submit` remains the only formal UI submit endpoint and has no server idempotency.

- no feedback text is persisted;
- transport-unknown stores only `{project,page,version,at}` under a scope-specific sessionStorage key;
- unknown A does not block B or another page/version;
- definite 400/403/409 do not create UNKNOWN;
- the UI first performs read-only `changes/{project}` reconciliation, then enables explicit clearing of that exact scope;
- clearing never resends;
- successful submission defensively clears the same-scope marker.

`change_submit_idempotent` remains adapter/test-only, unmerged and undeployed, with explicit retry only and no fallback to legacy.

## Private preview URL

Server-returned URLs are normalized with `new URL` against a fixed dummy same-origin base, then required to match exactly:

`/customer/center/preview/{project}/{64-hex-page-key}/{64-hex-version}`

Expected project/version come from the authorized record. Query, fragment, percent encoding (including encoded traversal), backslash, external/protocol-relative origin, wrong project, non-hex key and normalized escape are rejected. No iframe workaround or synthesized preview URL exists.

## Test evidence

V5 isolated suite: **24/24 PASS, 0 FAIL**.

- 4 fetch/API boundary tests.
- 3 candidate-idempotency adapter tests.
- 3 local real HTTP-socket tests using 4dc response/body semantics; not production authentication.
- 8 deterministic `main.js` DOM/state tests for async races, 403 session discrimination and logout-unknown behavior.
- 2 traceability tests: fixed CSV SHA plus exact 69×26 field comparison.
- 4 submission-state tests for scoped UNKNOWN and definite/unknown behavior.

This is source/isolation evidence, not Hosted, real browser E2E, production deployment, payment or customer acceptance proof.

## Remaining HOLD / NOT_EXECUTED

1. Authenticated Hosted real-user 4dc journey: `NOT_EXECUTED`.
2. 360/390/768/1440 real-browser acceptance against frozen baselines: `NOT_EXECUTED`.
3. New-tab CSRF recovery: `MISSING/HOLD`.
4. Frozen 69-page signed preview registration / GAP-01: `HOLD`.
5. Original Task Registry binding/completion-event writeback / GAP-02/GAP-03: `NOT_WIRED`.
6. Full structured requirement fact/version chain / GAP-04: `HOLD`.
7. Formal whole-project acceptance / CUS-014: `HOLD`; never reuse `change_retest`.
8. `change_submit_idempotent` backend merge/deployment: `NOT_DEPLOYED`.
9. Finance/order/entitlement/subscription/maintenance interfaces outside this slice: `HOLD` where the final specification has no production evidence.


## Exact backend 1b48e5fe real-Python-HTTP isolation entry

Backend contract anchor for this continuation is commit `1b48e5fe8015afd9035ff269f9b432d9a68223b2`, tree `b0c0147aeef69d00e6edbaef7e436e5699403cf3`. It adds `change_submit_idempotent` to the real PR122 HTTP operation map and hosted change-submit coverage. The SaaS UI still does not enable automatic candidate submission or resend UNKNOWN results.

Executable integration entry:

```sh
XJ_PR122_BACKEND_ROOT=/absolute/path/to/exact-1b48e5fe-checkout \
  sh clients/saas-console/tests/run_real_python_backend_integration.sh
```

The Python entry refuses to run unless `git rev-parse HEAD` of `XJ_PR122_BACKEND_ROOT` is exactly `1b48e5fe8015afd9035ff269f9b432d9a68223b2`. It imports the repository's actual `Center`, `App`, `HTTPServer`, signed snapshot/import code and existing `HttpTests` fixture. No Node/fetch fake service is used by that test.

Synthetic-only journey covered by the executable entry:
- HTTP login -> secure cookie + CSRF response;
- `GET me` and tenant/project isolation;
- signed TRUSTED_CUSTOMER_FRONTEND `import_snapshot` -> `previews/{project}`;
- actual private preview GET -> `served` / `preview_serves` evidence;
- project Q&A POST/readback;
- legacy change submit -> same-case read-only `changes/{project}` readback;
- real `change_submit_idempotent` replay returns identical case/event and same-key changed-body returns 409;
- signed V2 delivery snapshot -> authoritative V2 listing -> `change_updates` -> exact `change_retest` -> RETEST readback with `automatic_charge:false`.

Current execution status in this ChatGPT runtime: **NOT_EXECUTED**. The runtime has no mounted checkout of the repository and outbound Git/GitHub clone is unavailable, so the exact 1b48 backend modules and their transitive imports cannot be loaded into local Python. This is an environment/input absence, not a backend PASS/FAIL. The existing V5 Node/fetch/local-HTTP results remain isolated frontend evidence only and are not reclassified as backend connectivity.

Minimum missing local input to execute the test: one filesystem checkout whose HEAD is exactly `1b48e5fe8015afd9035ff269f9b432d9a68223b2`. No credentials, customer data, server access, deployment permission or payment environment is required.


## V6 narrow-review corrections

Source parent for this patch: frontend commit `6859130751589ab340ca0664ada509df6b0cc71b`. Existing V5 URL normalization, 69×26 traceability, version/retest binding, mutation cross-project guards and real-backend entry are reused rather than redesigned.

### 403 generation/project probe guard

Project-load 403 no longer clears detail before identity discrimination. Every `handleError` call from a selected project carries `{generation, project, write}`. A 403 performs read-only `GET me`; after that await, it may mutate UI only when the initiating generation/project is still active. A delayed A→`me` result cannot clear or replace B after the user opens B.

### Ambiguous mutation HTTP status

`api.request` now classifies POST HTTP 408 and 5xx responses as `ApiFailure.uncertain=true`, even when the backend returns JSON. GET responses remain definite because they cannot create mutation state. Consequently legacy `change_submit` creates only its scoped UNKNOWN marker on 408/5xx and never blind-resends; candidate idempotent submit retains the existing key for explicit retry rather than generating a new key; logout 408/5xx is reported as unknown rather than successful logout.

### Write-403 / CSRF handling

A write operation 403 followed by successful read-only `/me` proves only that the HttpOnly cookie session still identifies the user; it does not prove the tab-local CSRF remains valid. The console therefore clears `xj_csrf`, refreshes the authorized project list, exposes the login form and requires explicit re-login before more writes. A GET/project-read 403 does not automatically clear CSRF when `/me` still succeeds. No new auth or token-recovery system is introduced.

### Per-delivery retest latch

For one `AWAIT_RETEST` delivery, ACCEPT and FEEDBACK share one in-flight latch. Starting either action disables both controls; any second click while the request is in flight returns without calling the API. This prevents concurrent contradictory RETEST events from the same rendered delivery.

### Tests

V6 frontend/source isolation regression: **29/29 PASS, 0 FAIL**. New targeted coverage includes:
- A project-load 403 → deferred `/me` → open B → late A `/me` result cannot clear B;
- active write 403 + valid cookie clears stale CSRF and exposes explicit re-login;
- POST 408/500/503 are ambiguous while GET remains definite;
- legacy 503 creates only its scoped UNKNOWN marker;
- candidate 503 blocks implicit retry and explicit retry reuses the same idempotency key;
- same delivery ACCEPT/FEEDBACK share one latch and the second click does not issue another API request.

This remains frontend/source isolation evidence. The exact Python backend integration entry bound to `1b48e5fe8015afd9035ff269f9b432d9a68223b2` remains `NOT_EXECUTED` in this runtime because no complete backend checkout exists in `/mnt/data` and outbound GitHub clone is unavailable. Existing Node/local-HTTP PASS results are not counted as real Python backend connectivity.


## V7 UI-only render evidence + e7f non-browser HTTP isolation

Backend input was taken from GitHub Actions Run `40104761192`, Artifact `12564730638` and verified as source `e7f75975c4ab4eedba68306212a2bac6c067a1c3`, tree `d001cfd9855ed3a7758f6286db5cae7d45cce403`, ZIP SHA256 `06d29ed7bfab4b61f366e0cd239409172267075ab7c8726b5180788d19ae5095`, review TAR SHA256 `872609867966dd3ffddbb28ab59fb73ba5b26966eb6b8bbf3e14e265403aa148`, CUSTOMER_MANIFEST SHA256 `f6fe299464ac6c1b0317ebc7489b1762aaa9acd3547a6a41248d3b05443366d1`, 102/102 closure PASS, `REVIEW_ONLY_NOT_DEPLOYED`.

Correct fixture startup is `python -B -m tests.pr122_customer_browser_server` from the extracted customer-center root.

Chromium direct navigation is blocked by host administration policy with `net::ERR_BLOCKED_BY_ADMINISTRATOR`. This browser dependency is therefore stopped and remains `BLOCKED / NOT_VERIFIED`. No alternate address, proxy, route interception or other browser-network workaround is accepted as browser-route verification.

The previously generated 48 Chromium screenshots at 360×844, 390×844, 768×1024 and 1440×900 used `page.set_content`; they are retained only as `UI_ONLY_RENDER` evidence for responsive layout and interaction state. The 156 e7f Python HTTP calls used a test harness/proxy and are retained only as `NON_BROWSER_HTTP_INTEGRATION` evidence. Neither is browser navigation E2E.

Actual V1 preview SHA256: `66096dc90025694f3cdfd46a4cd3e583777a01ac6618672945914455f66484c5`.
Actual V2 delivery SHA256: `ce256a5afa8c26e4bec807edc09005cbaef17e717c50d0130996affb35783940`.

UI-only rendering found and fixed stale post-login status text and 2–4px mobile overflow. These source fixes remain valid and are covered by Node regression; they do not convert the blocked browser route into PASS.

## V8 change_updates read/write 403 split

`updates()` is split into two error domains:

1. authoritative `GET previews/{project}` / `currentPage()` uses `{generation,project,write:false}`;
2. only the subsequent `POST change_updates` uses `{generation,project,write:true}`.

Therefore a read-side 403 followed by successful `GET me` preserves the current tab CSRF, while a write-side `change_updates` 403 followed by successful `GET me` clears stale `xj_csrf`, refreshes authorized projects and exposes explicit re-login. Generation/project guards are preserved across both phases.

Independent real e7f Python HTTP contract verification:
- valid owner cookie + stale CSRF -> `POST /customer/center/api/change_updates` = HTTP 403;
- same valid owner cookie without CSRF -> `GET /customer/center/api/me` = HTTP 200 and returns `project-a`.

This is non-browser HTTP contract evidence. No browser navigation was retried after the administrator-policy refusal.

Frontend regression after the two contrast tests: **32/32 PASS, 0 FAIL**.

Still NOT_VERIFIED/HOLD: browser route/navigation E2E, Hosted TLS/network path, full frozen 276-screen matrix, production deployment, real customer identity/data, payment, and formal whole-project acceptance.


## V10 private-material submit + exact e7 Python HTTP integration

The SaaS console now consumes the existing e7 `api/save` contract for checklist items whose `submission_type` is `PRIVATE_DOCUMENT`. No backend interface was added.

Exact request:
`{project,item,revision,kind:'DOCUMENT',content:<base64>,expires}`.

UI rules mirror the reviewed customer-center contract: only OWNER/EDITOR may upload; SUBMITTED/IN_REVIEW items are not editable; the chooser is limited to PDF/PNG/JPEG and 5MB client-side before the server performs authoritative file-magic, required-format, scan, permission, quota and revision checks. `SECRETREF`, `OAUTH` and `SERVER_CHALLENGE` remain dedicated-provider flows and do not accept plaintext credentials in this console.

The frontend displays the backend response text as supplied. e7 returns generic Chinese HTTP errors for the relevant boundary, including HTTP 403 `权限不足、凭据失效或请求不符合要求`, rather than exposing internal exception codes.

### Exact e7 isolated integration

`clients/saas-console/tests/real_python_backend_integration.py` is now bound to the review-only artifact manifest:

- commit `e7f75975c4ab4eedba68306212a2bac6c067a1c3`
- tree `d001cfd9855ed3a7758f6286db5cae7d45cce403`
- exactly 102 manifest members, every SHA256 verified before execution
- fixture entry `python -B -m tests.pr122_customer_browser_server`
- required scope `ISOLATED_FIXTURE_NOT_PRODUCTION`
- required signer marker `TEST_ONLY`

Actual local execution PASS covered login → me → checklist → save → V1 preview → feedback → same-case changes → reviewer assessment/candidate → TEST_ONLY publish → V2 preview → updates/retest → cross-project 403 → logout → me 403.

Observed V1:
`66096dc90025694f3cdfd46a4cd3e583777a01ac6618672945914455f66484c5`

Observed V2:
`ce256a5afa8c26e4bec807edc09005cbaef17e717c50d0130996affb35783940`

The run is real Python `HTTPServer/App/Center/SQLite` against the verified e7 artifact, not the Node stub. It remains isolated fixture evidence, not Hosted production/customer acceptance.

Chromium navigation remains `BLOCKED / NOT_VERIFIED` because direct `page.goto` is administratively rejected with `net::ERR_BLOCKED_BY_ADMINISTRATOR`. This task does not retry through proxy, setContent or alternate browser routing.


## V11 original SaaS JS client → exact e7 loopback HTTP

This closes the distinction between the earlier backend-only Python integration and the actual SaaS JavaScript client.

The executable `clients/saas-console/tests/e7-js-client-integration.mjs` imports the repository's actual:
- `src/api.js` blob `8383bee41d2abec68ca580469388e1399cbdab03`;
- `src/journey.js` blob `adf27901abf2fe1311d6742367c4fdb1db4a5a7c`;
- `src/submission.js` blob `fdcb1dd74d61010e320445a138c4570ba530f1e3`.

Before execution it verifies all 102 files in the e7 artifact manifest and requires backend commit `e7f75975c4ab4eedba68306212a2bac6c067a1c3` / tree `d001cfd9855ed3a7758f6286db5cae7d45cce403`.

Exact local command:

```sh
cd clients/saas-console
XJ_PR122_E7_ROOT=/mnt/data/saas_e7/customer-center/customer-center \
  node tests/e7-js-client-integration.mjs
```

Actual exit code: `0`.

The JS client path exercised:
1. `makeApi.login` with the real Host/Origin boundary and Secure/HttpOnly/SameSite cookie;
2. `ProjectJourney.projects` / `project`;
3. `ProjectJourney.saveMaterial` against e7 `api/save`, then checklist revision refresh;
4. cross-project read denial with the exact generic Chinese HTTP 403 response;
5. `ProjectJourney.project` returns the current version-bound preview URL;
6. the same client transport performs a real GET of the bound V1 HTML body and verifies `Welcome to Xuanjun` plus the server feedback binding;
7. `feedbackContext` + `submitLegacy` + same-case `changes`;
8. reviewer/test-fixture-only assessment + small-edit candidate + TEST_ONLY publication, not a SaaS customer capability;
9. `currentPage` obtains V2;
10. a real GET of the V2 bound HTML body verifies `Welcomes to Xuanjun`;
11. `updates` + `retest` + final RETEST event;
12. logout followed by `me` yields the generic Chinese HTTP 403 invalid-session boundary.

Observed:
- save revision: `1`;
- V1: `66096dc90025694f3cdfd46a4cd3e583777a01ac6618672945914455f66484c5`;
- V2: `ce256a5afa8c26e4bec807edc09005cbaef17e717c50d0130996affb35783940`;
- V1 rendered body SHA256: `f8920932b0dc5e36ecfd75ddbddf28c246d17831248c446edc17220e06a61d17`;
- V2 rendered body SHA256: `78ef713dccc80fcb86a31cd4ab650f8530112f4c5961bd361f3ee29c3f86dddf`;
- Chinese 403: `权限不足、凭据失效或请求不符合要求`;
- retest: `RETEST_ACCEPTED`.

The first real execution correctly failed with HTTP 400 because the Node transport harness omitted `Content-Length`; after adding that transport header the same client chain passed. Product `api.js`, `ProjectJourney`, and e7 backend source were not changed for that transport fix.

Raw stdout/exit evidence is retained in `clients/saas-console/tests/E7_JS_CLIENT_INTEGRATION_STDOUT_20261024.txt`.

Hosted CI only syntax-checks this artifact-bound integration entry because the e7 review artifact is not part of the repository checkout. A Hosted syntax PASS must not be described as Hosted e7 HTTP execution. Existing frontend `npm test` remains a separate source/isolation gate.

Browser route/navigation remains `BLOCKED / NOT_VERIFIED` due `net::ERR_BLOCKED_BY_ADMINISTRATOR`; no proxy, `setContent`, alternate address, or alternate browser tool is used to convert that refusal into browser E2E evidence.


## V12 CUS-008 material review lifecycle

The SaaS customer console now consumes the existing e7 material lifecycle without adding backend state or reviewer authority.

Customer-side additions:
- `api.transition(project,item,revision,action,reason)` sends the exact five-field e7 transition body.
- `ProjectJourney.submitMaterial` exposes only customer `submit` for OWNER/EDITOR items in `PARTIAL` or `NEEDS_CORRECTION`.
- `accepted_revision` is displayed from checklist server state.
- the latest `request_changes` version reason is displayed as the correction basis.
- historical material links are built only from server-returned `versions[].details.object_id` through `/customer/center/api/download/{project}/{object_id}`.
- no reviewer `begin_review/request_changes/approve` controls are added to the SaaS customer UI.

Exact e7 JS lifecycle evidence imports blobs:
- api.js `81504cda86684faa671689760dd702dde356ca48`
- journey.js `d28bcd2be278310981404a26117c67df891774ff`
- submission.js `fdcb1dd74d61010e320445a138c4570ba530f1e3`

Command:
```sh
cd clients/saas-console
XJ_PR122_E7_ROOT=/path/to/extracted/e7/customer-center \
  node tests/cus008-e7-js-lifecycle.mjs
```

Actual local result: exit 0. It covered first save, authenticated historical download, unauthorized download 403, stale revision 409, stale CSRF 403, an UNKNOWN submit response after the server committed with exactly one transition POST and no retry, checklist readback to SUBMITTED, fixture-only reviewer request-changes, customer correction reason readback, corrected save, two historical downloads, resubmit, fixture-only reviewer approve, `accepted_revision=8`, and a later new save preserving accepted revision 8 while state returned to PARTIAL. Project revocation then produced the real Chinese 403 through the original JS API.

The existing browser fixture has no clock-advance control, so expiry is not fabricated through the JS harness. The exact e7 backend expiry test `CustomerTests.test_authority_signature_scope_replay_and_expiration` was executed separately and passed; this is backend expiry-contract evidence, not JS/browser expiry E2E.

Browser navigation remains `BLOCKED / NOT_VERIFIED` due `ERR_BLOCKED_BY_ADMINISTRATOR` and is not bypassed.
