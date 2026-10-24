# SaaS console isolated integration — 2026-10-24

Source anchor: website integration branch commit `4dc5e349243d5fd277807c0c023281118d6df9d6`, tree `66b45dc175afa7ecf4347afcbec49455dd4d91c8`. Do not mix with PR122 head `cd348c77506e07ba9516a869b8fe1e66597a6e69`.

Existing server endpoints: GET `/customer/center/api/me`, GET `/customer/center/api/checklist/{project}`, GET `/customer/center/api/previews/{project}`, GET `/customer/center/api/changes/{project}`, POST `change_context`, `change_submit`, `change_updates`, `change_retest`. POST requests carry session CSRF header and exact body schema. Server supplies preview URL; never synthesize or iframe. GET `/me` may return account-only data lacking `projects`, in which case console holds. OWNER rights on preview and feedback are server enforced. This implementation hides these actions for other roles but never assumes client-side permission is authority.

Transport-ambiguous POST submission has no automatic retry. The same applies to retest. Re-open current server state before manual resolution. A completed `change_retest` is NOT contract final acceptance. No payments, deployments or production claims. UI visual mapping held until authentic 69-page prototype and 8-stage spec arrive. This deliverable is source only; no live backend, browser or deployment proof.

## 2026-10-24 isolated contract suite / two-version compatibility

`change_submit` is the pinned 4dc production-source contract with no server idempotency; legacy mode is the only mode wired in the UI and NEVER automatically resends a submission, including after browser reload. Pending intent journal is stored in browser localStorage per project/page/version, with no credentials or sensitive request body exposed as an external transport. **Caution:** it contains the customer feedback text, so local-storage confidentiality and retention require review before production use. Do not treat the journal as authoritative state. Reconciliation through authenticated `changes/{project}` is needed after UNKNOWN, and opening a new request requires explicit confirmation and record reconciliation.

`change_submit_idempotent` is a **UNMERGED / UNDEPLOYED backend candidate**, not an available production endpoint. Candidate expects `{project,page,version,text,intent,idempotency_key}` and uses a 16–128 character `[A-Za-z0-9_-]` key. The journal prepares and persists one key before first send, reuses the key on explicit retry after network ambiguity, never silently falls back to legacy on 404, and forbids same key with changed body. A server returning an unchanged case/event on replay and 409 on mismatched body is simulated by the bounded contract test, **not verified against deployed server**. Idempotent mode is presently accessible in the isolated JS adapter only; enabling it in UI requires official backend acceptance plus coordinated integration. Local storage alone does not replace server-enforced idempotency or prevent multiple devices from submitting.

Tests use a deterministic in-process fake HTTP boundary which enforces cookie option, CSRF header, project membership, version pin, delivery proof and candidate request replay. They do not impersonate real users or assert actual backend connectivity. Cases: project list/checklist/preview, context, submit, updates, retest; expiration/revocation/cross-tenant 403; version drift 409; lost response/replay stable case and event; repeated button; same key different body 409; legacy uncertainty; absent candidate 404; key format and explicit new request. Exact private URL originates only in the response. `change_retest` does not constitute contractual final signoff.

Actual end-to-end authenticated server requests, backend candidate acceptance, browser policy/frame behavior, production asset hosting, 69-page design mapping, and eight-stage prototype acceptance: **NOT_EXECUTED / NOT_RECEIVED**. No server/deploy/payment/credentials/privilege operations.

## 2026-10-24 first operable product slice

The console UI now directly uses the pinned 4dc contracts, not only adapter tests. It renders the authenticated `/me` project fields (`id/title/role/tenant/customer`), checklist requirement fields and revision/version history, server-returned trusted preview URLs and SHA256 version, original change case/request page/version/text, delivery update proof/new SHA when present, and project-scoped WEB Q&A through `messages/{project}` + `message`.

Formal UI submission remains pinned to legacy `change_submit`: one click/one network attempt; transport ambiguity is held and reconciled by re-reading `changes/{project}`. The unmerged `change_submit_idempotent` exists only in the candidate adapter and bounded tests; there is no UI switch or automatic fallback. `change_retest` is labeled version retest only and is explicitly not contract final acceptance.

Actual loop exercised over a real local HTTP socket using 4dc response shapes: GET me -> checklist/previews/changes/messages -> POST change_context -> legacy change_submit -> GET changes -> POST change_updates -> POST change_retest -> POST project message. Rejection tests cover cross-tenant access, revoke/expiry and version drift. A socket-destroyed response after legacy server acceptance verifies the client does not resend and the original server case is recovered by reading changes. This is a local isolated HTTP boundary, not authenticated Hosted/production proof.

### API status

CONNECTED IN UI against pinned 4dc source contract:
- GET `/customer/center/api/me`
- GET `/customer/center/api/checklist/{project}`
- GET `/customer/center/api/previews/{project}`
- GET `/customer/center/api/changes/{project}`
- GET `/customer/center/api/messages/{project}`
- POST `/customer/center/api/message`
- POST `/customer/center/api/change_context`
- POST `/customer/center/api/change_submit` (legacy safety policy, no blind resend)
- POST `/customer/center/api/change_updates`
- POST `/customer/center/api/change_retest` (version retest only)

CANDIDATE ONLY / NOT DEPLOYED:
- POST `/customer/center/api/change_submit_idempotent`

NOT EXECUTED / NOT RECEIVED:
- authenticated real-user Hosted HTTP session and browser E2E
- production deployment
- accepted idempotent backend endpoint
- frozen 69-page prototype and eight-stage artifact for page-by-page visual mapping

### Minimal backend gaps for the website owner

No new SaaS backend is requested. For this first slice, the pinned 4dc backend already supplies the project, requirement, preview, case, update/retest and Q&A contracts. Remaining integration gaps are external to this frontend scope: (1) real authenticated/Hosted acceptance of those routes; (2) merge/deploy decision and contract fixture for `change_submit_idempotent` before any UI enablement; (3) if product requires a distinct contractual-final-acceptance action, expose a dedicated server contract rather than reusing `change_retest`; (4) provide the frozen 69-page/8-stage artifacts so UI placement and page IDs can be mapped without redesign.
