# Original-framework integration delta — local candidate, NOT installed

This is not a usable phone link and not final delivery. Do not send this source bundle to Owner as the action required of them. The responsible window must complete the existing-host integration and evidence.

## Implemented locally

`tools/build_native_patch.py` transforms fixed public OpenClaw 2026.9.9 artifact sources in a separate directory, producing `native-framework.patch`, `patched-source/`, and exact original/candidate SHA manifest. It does not access an installed service. Ten existing files change:

1. `question-validation-C3R346Mf.mjs`: original shape validation permits only the exact three fixed community secret names/signature, initial `allowedHosts=[]`; all general original restrictions remain.
2. `question-2U20Yooq.mjs`: original `operator.admin`, trusted agent/runtime authority, current session access and mutation admission remain ahead of the new branch. Exact 600000 ms request, original manager lifecycle, original Store batch and durable original-request receipt; cancellation cannot contradict committed values. Authorized `question.get` gives committed receipt priority even when the old manager is still pending after lost response. After 15-second manager cleanup, terminal metadata is recoverable through original session read admission. Unconfirmed pending is not fabricated as canceled.
3. `server-aux-handlers-ZAnivsB0.mjs`: actual original write/read/Store exports and redaction registration compose the bridge; reload each fixed reference after commit. No fake Owner body property.
4. `openclaw-state-db-contract-CQDemVBb.mjs`: receipt table added to the original lazy-additive table contract.
5. `openclaw-state-db-legacy-backfills-BSKqroDt.mjs`: same metadata-only receipt table added to original canonical schema; no second vault, no secret columns in receipt.
6. `control-ui-boot-shared-_B6VNra2.js`: original request-builder handles exact bundle and keeps only three `stored` markers in submitted-answer state; it cannot edit hosts in this branch.
7. `control-ui-boot-shared-mtfVQ24Y.js`: original Lit question component displays all three masked inputs together, non-collapsed, full-width 48px buttons, existing state/error/submit lifecycle. No independent site/framework/login.

8. `secret-store-CuSJMUWv.mjs`: original six insert/update mutation assignments now generate a fresh UUID4 `revision_token` in the SAME Store transaction. Write/replace, both rollback branches, allowedHosts updates and soft delete all invalidate older versions; delete/recreate creates a new token. This is non-secret version metadata, not a secret-derived hash or auth key. Original actor audit remains untouched.
9. `openclaw-state-db-schema-additive-DAFjL3MG.mjs`: original ensureSecretStoreSchema adds nullable revision_token; canonical schema also contains it. Legacy rows are not silently rewritten; the new consumer refuses rows without a valid version until a normal authorized update. No default guess or timestamp compatibility fallback.
10. `question-page-registration-Ci9YglNL.js`: UNKNOWN recheck invokes original loadQuestion with the same ID, keeping local uncertainty until a terminal receipt. The native submission function and button both refuse repeated resolve while error is pending; querying does not itself resubmit.

New modules: `acceptance_questions.mjs`, `gateway_acceptance_bridge.mjs`, `receipt_schema.mjs`; existing durable adapter has idempotent SQL. New UI `acceptance-signature.js` is generated from the same exact signature source. `receipt_schema.mjs` verifies existing full normalized DDL plus ordered columns/PK, failing on a mismatched table.

**Build caveat:** these are exact-artifact implementation patches, not an installer. Original production UI build must regenerate asset hashes/precompressed assets/manifests; do not overwrite immutable-hash files in a running cache and claim deployment. Installed custom build source must match pins or receive a reviewed source-level port. Canonical schema and lazy registry must travel together through original controlled migration admission; no standalone production SQL.

## Identity scope: no new invented Owner gate

Original native question contract permits authorized `operator.admin` and relevant original session mutation policy, not proof of a named human. Bridge receipt `owner_id` is explicitly a legacy candidate column name containing a hash of server-owned agent/session/run scope, not a human identity assertion. All actual admission remains the original handler. This neither grants new operators access nor proves that a particular human is Owner. Only Owner is to enter real credentials; if an additional named-person-only restriction is wanted, use an existing authenticated profile/device source, not client body or a newly fabricated credential. No such gate is silently added.

## Browser implementation and exact remaining gap

`native_browser_consumer.mjs` implements a **private, not registered** refs-only consumer kernel. It atomically reads the three live rows' values/kind/allowed_hosts/revision_token from the existing shared-state table in one SELECT. It validates exact configured provider, fixed names, purpose/version, trusted plan's opaque UUID revisions (NOT updated_at_ms) and exact approved HTTPS origin; initial empty hosts denies before reading values. Original target/runtime authorization and a private isolation lease must precede the read. It uses original page/locator methods directly, not model-visible `browser.type` plaintext. A private revisionMetadata method obtains only name/kind/revision from the same original Store for the authorized planner; no public RPC is registered. Result and exceptions are fixed codes, never DOM/cookies/values/errors. After login it remains quarantined; this is not page QA.

**No real original-runtime lease adapter exists yet.** The supplied tests fake browser/lease explicitly. Consequently native `2026.9.9` remains `BROWSER_SECRET_INJECTION_UNSUPPORTED`, and this candidate is not enabled. An absent lease returns HOLD before secret reads. The following exact original entry points need integrated guards and runtime proof before capability enablement:

- `routes-HyMgpcv1.mjs`: `withBrowserProfileCapabilities` (~3778) and `withRouteTabContext` (~275), original `/act`, screencast (~1807), tabs (~3959), response/body, cookies/storage, downloads. Route wrapper alone does not cover direct native CDP or already-running collectors.
- `pw-tools-core.interactions.navigation-JXfYkmoU.mjs`: `ensurePageState` (~568), console/error/request listeners (~586–631), context state (~1313), original document identity/ref/interaction authority. Taint before reading values; stop collector paths, drain concurrent operations. Existing navigation guard (~1605) allows non-document requests and is insufficient for XHR/beacon/WebSocket; enforce precise origin for all request channels in the original context.
- `pw-ai-CXSFycyo.mjs`: page text/errors/requests/console (~40–114), evaluate/wait, snapshots/screenshots/PDF, response bodies/cookies/storage, traceStart/traceStop (~2220), plus native act. Raw observation cannot resume merely because fill returned. Errors must not use raw cause/stack. Existing traceActive only records native trace, not proof that no outside recording exists.
- `browser-node-proxy-PNhF-iqq.mjs`: never use node-unavailable fallback to another host for this private consumer; pin original executor/profile/target/document and original Store identity.

Threat model is credentials not reaching model/chat/logs/screenshots, not preventing the Owner/root from administrating their own protected SQLite. Safe post-login page QA still requires trusted sanitization of observations; raw evaluate/response/storage/cookies/trace cannot be exposed. Screenshots/recordings are HOLD until no-secret output is demonstrated. Do not call a quarantined successful login final QA.

## Existing HTTPS/mobile integration — not yet connected

Reuse `uk.wenwenwenyiyiyi.work:443` dedicated authenticated ask route, original Gateway loopback, no entire management UI proxy, no permanent token/setup code in URLs. Field evidence identifies original `owner_dashboard.py` Bearer comparison and loopback18556. It does not establish a mobile cookie/device session. Actual existing pairing/session bridge and exact site routes are being verified by the sole field executor. Do not invent an anonymous form or new login service. Suppress questionId path in normal access/telemetry logs; preserve `/owner/`, `/task-center-test/`, community previews and TLS/HSTS.

## Tests and limits

- New bridge: 18 checks, actual SQLite, test manager/auth doubles.
- Native patch: 13 checks, exact patched original validator executed, static auth fences, real SQLite receipt DDL; NOT full Gateway.
- Native UI: 18 checks, exact patched original submit function executed, structural mobile render checks; NOT real phone rendering.
- Private browser consumer: 24 checks, actual SQLite, fake browser and fake lease; NOT safe real injection.
- Patched native Store revision: 19 checks using actual SQLite and patched original write kernel with fixed Date.now; same-millisecond writes, hosts, rollback and delete invalidate versions. Original full schema/migration/runtime still unexecuted.
- Existing baseline remains 41 Python tests + 12 Store adapter + 11 original Store kernel + 31 durable receipt + 12 browser policy checks. Kernel is exact original code with explicit harness shims, not whole app runtime.
- Local Chromium launch was denied by sandbox socket constraint; no bypass and no phone/browser screenshot claim.

## Smallest approval/remaining execution boundary

1. Existing authenticated HTTPS ask-path/session bridge and original controlled Gateway/schema/UI update, precise diff/backup/check/reload/rollback through original installer.
2. Restricted new original-browser SecretRef consumer and context isolation capability, bound to existing authorized acceptance task/executor/profile and **exact community hostname/origin** after verification. Not arbitrary secret read, not generic admin expansion; initial hosts remain empty.
3. Non-sensitive canary end-to-end first. Real credentials only after mobile, TTL/once-only, durable Store, logs, route regression, safe browser consumption and page QA evidence all satisfy original requirements. No installation, migration, real credentials or host changes have been executed by this candidate Writer.

### UNKNOWN UI recovery limitation
The in-page UNKNOWN branch is locked against additional resolve and offers only original-request query. Pending metadata alone is not represented as a proven failed submission; it leaves the in-page lock in place. A browser/page restart naturally loses UI memory, but original same-DB once-only transaction still rejects any second commit; request GET is performed on page load. No claim is made that client UI memory is a durable attempt ledger. Fine-grained safe retry after a definitively failed attempt still needs explicit original-request outcome, not blindly interpreting PENDING as failure.
