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
