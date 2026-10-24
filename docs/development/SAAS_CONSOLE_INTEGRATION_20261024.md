# SaaS Console Integration 2026-10-24 — V4

## Bound sources

- PR122 website source anchor: `4dc5e349243d5fd277807c0c023281118d6df9d6` / tree `66b45dc175afa7ecf4347afcbec49455dd4d91c8`.
- Do not mix with PR122 head `cd348c77506e07ba9516a869b8fe1e66597a6e69`.
- Browser prototype handoff received and byte-verified: `2e211190c0d6edb6f2861bd860cbe9b03e27da92cb629c49277b1d4ab4ea5b62`.
- Final ecosystem/8-stage integration specification received and byte-verified: `5049d4f8dc9fe555492338c00afee4ab77c08d29557e52340660426e78330037`.
- Prototype package declares Replacement V3 commit `75f6c245ae29f54b918336a83b39b6ff78b58c7a`, tree `795e923301483cf0f2c8ba59878d8243495ad614`, 69 routes, 34 subviews, offline 52/52 PASS, browser `BROWSER_UNVERIFIED`.

## Frozen-page mapping

`clients/saas-console/prototype-page-map.json` is a mechanical 69/69 projection of `03_PAGE_TRACEABILITY.csv`; it does not upgrade any page to production verified. Current first operable slice maps to:

- CUS-005 project list: original `/me` project membership projection.
- CUS-006 project overview: project metadata + checklist + previews + cases + messages.
- CUS-007 requirement view: only fields already exposed by PR122 checklist are projected; full structured requirement capture/confirmation backend remains HOLD.
- CUS-008 private materials: PR122 source exists, but this console slice does not add upload UI.
- CUS-012/CUS-013 delivery list/detail: `change_updates` only after authoritative preview listing moves to the delivery `after_sha256`.
- CUS-014 formal acceptance: NOT WIRED. `change_retest` is version retest only and never presented as contract final acceptance.
- CUS-015/CUS-016 maintenance: no matching backend evidence in this slice; HOLD.

All other frozen routes remain mapped with their source `gate`, `source_implemented`, `owner_gap_task`, and `real_verified=NO` values. No redesign was performed.

## Corrected preview/change sequence

4dc `Changes.page_updates(uid, project, page, version)` first calls `_preview(uid, project, page, version)` and only returns delivery records where `record.after_sha256 == version`. Therefore the client must not ask for an update while the authoritative listing is still the old SHA. V4 flow is:

1. open original trusted preview V1;
2. submit feedback against V1 once;
3. reload authoritative `previews/{project}`;
4. only after the same path is listed at V2 call `change_updates(project,path,V2)`;
5. render `before_sha256` as the modified-from version and `after_sha256` as the current delivery version;
6. call `change_retest` with V2, current case revision and exact `delivery_sha256`.

Local HTTP tests enforce this sequence. The former v1 request returning a synthetic v2 delivery has been removed.

## Identity / CSRF contract

The console now uses the original 4dc identity surface rather than fabricating roles/tokens:

- `POST /customer/center/api/login {email,password}` returns `csrf`; session token remains server-set HttpOnly SameSite cookie.
- CSRF is stored only in `sessionStorage`, matching the original UI behavior.
- `GET /me` can identify an existing cookie-backed session without CSRF.
- authenticated write operations require the CSRF header.
- `POST /logout {}` uses the original logout contract and clears local CSRF.
- 401 clears CSRF and all project content; 403 clears the selected project content and requires a refreshed project list.

Accurate remaining backend limitation: 4dc exposes no endpoint to recover the CSRF value from an already-valid HttpOnly session cookie in a new tab. Therefore a new tab can remain read-only after `GET /me`, but must re-login before writes. The frontend does not invent a token-recovery protocol.

## Project-switch privacy correction

Opening any project first clears project metadata, requirements, previews, cases and messages, then shows loading placeholders. A stale earlier response is generation-checked and ignored. Any denied/failed project load clears the detail view, so customer A data is never left under customer B's title. `main.test.js` exercises project switch, stale completion and rejected load; 401 clearing is separately tested.

## Submission safety

### Deployed legacy `change_submit`

Legacy feedback has no server idempotency key. V4 does not persist the customer feedback body in localStorage/sessionStorage and does not permanently occupy a project/page/version slot after a successful or explicit 400/403/409 response. A transport-ambiguous POST stores only `{project,page,version,at}` in sessionStorage and blocks blind re-send until the user reconciles by reading the authoritative case list. After reconciliation the marker can be explicitly cleared and a later legitimate feedback on the same page/version is allowed.

### Candidate `change_submit_idempotent`

Still candidate-only / not deployed. A 16–128 `[A-Za-z0-9_-]` key is kept only in in-memory adapter state in this slice; a definite 4xx clears the candidate slot, while a transport-unknown result requires explicit retry and reuses the same key. A missing candidate endpoint never falls back to legacy. This does not claim multi-tab/device idempotency; production-safe durable replay needs the server candidate to be merged and deployed.

## Retest semantics

Local fake/server tests now require exact `project`, `case`, `revision`, `page`, current delivery `version`, `delivery_sha256`, and `ACCEPT|FEEDBACK`. No fictitious `final_contract_acceptance` field is returned or asserted. The result checks `automatic_charge:false` when supplied. Formal project acceptance remains a separate missing server capability from the final specification.

## Test layers and result

Current isolated suite: 18/18 PASS.

- 4 fetch-stub/API boundary tests: HTTP method/body/same-origin/CSRF, transport ambiguity, private URL allowlist, exact retest body.
- 4 candidate-contract in-memory tests: stable replay, same-key changed-body 409, missing endpoint no fallback, cookie-read/CSRF-write distinction.
- 3 real local HTTP socket tests: corrected V1→V2 preview/update/retest journey, cross-project/revoke/expiry/version-drift rejects, legacy response-loss reconciliation.
- 2 `main.js` UI state tests with a minimal deterministic DOM harness: switch/failed-load stale-data clearing and 401 session clearing.
- 1 frozen 69-page mapping integrity test.
- 4 submission state tests: same-version later feedback, definite failures do not lock, unknown does not store feedback body and prevents blind resend, candidate definite-vs-unknown behavior.

These are isolated source tests. They are NOT a real authenticated backend run, browser E2E, Hosted acceptance or production proof.

## Remaining exact gaps for website/backend owner

1. Real authenticated Hosted run of 4dc identity + project + preview/change routes and browser E2E remains NOT_EXECUTED.
2. New-tab CSRF recovery does not exist in 4dc. Either accept re-login-for-write behavior or add a reviewed server endpoint/flow; frontend must not derive the token from the HttpOnly cookie.
3. `change_submit_idempotent` remains unmerged/unavailable; no UI enablement until backend acceptance/deployment.
4. Full structured requirement capture/version confirmation (CUS-007), prototype page-confirmation object (S4/GAP-11), original-task receipt/completion binding (GAP-02/03/07), and frozen-69-page preview registration (GAP-01) remain backend/task-registry gaps.
5. Formal whole-project acceptance (CUS-014/S7) requires an independent server record/authority check. Never reuse `RETEST_ACCEPTED`.
6. Finance/order/entitlement/subscription/maintenance routes outside this first project slice remain HOLD where the final spec has no production interface evidence.
7. Real 360/390/768/1440 browser acceptance and the prototype's 276 screenshot baseline remain BROWSER_UNVERIFIED.
