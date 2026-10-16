# PR122 Domestic Website Offline Candidate

## 1 Design

Build a delta-only candidate on top of the immutable Tokyo source archive. The
candidate changes only `public/assets/tiktok-integration.js`, adds an isolated
Domestic apex Nginx/TLS design, and provides fail-closed release tooling. The
private control base remains below `/home/openclaw_ops` with mode `0700`; the
public static release lives below `/var/www/wenwenwenyiyiyi.work` and is owned
by root. Existing `winctl` server blocks, certificates, services and routes are
not replaced or included in this package.

The source archive is pinned by SHA-256 and is not repacked. The delta bundle
contains an overlay, the complete expected post-overlay file manifest, exact
configuration candidates, and release tooling. Dynamic integrations and
protected routes remain fail-closed until their independent backends and
authorization contracts are accepted.

## 2 Development Sequence

1. Verify the pinned source archive hash and the original TikTok asset hash.
2. Build the overlay and expected final manifest without rebuilding the source
   archive or recollecting routes.
3. Test network failure, invalid JSON, explicit disconnection, disconnect
   failure and successful connection UI states.
4. Test W1—W5 as one release transaction: worker readability and immutability;
   receipt-bound artifact identity; namespace/link/owner/mode constraints;
   durable intent, reconciliation and exact rollback; one real hard deadline
   across lock and I/O. Include negative cases for A-receipt/B-bundle, content,
   mode, traversal, wrong IDs, link substitution, write failure, interruption,
   ambiguous state, NaN/Inf and actual timeout.
5. Test W6 as one cutover contract: generated CSP hashes in real Chromium on
   a synthetic representative page (not the private 1187-file source archive),
   Tokyo-only ACME challenge forwarding while DNS remains unchanged, exact
   existing Domestic certbot path/version, dynamic-route cutover HOLD, and a
   non-executable cross-object backup/rollback contract that protects winctl.
6. Publish only the offline candidate commit and bundle receipt. Production
   installation, certificate issuance, Nginx changes, permission changes and
   DNS changes require a separate Release Gate.

## 3 Acceptance

- A status request failure or malformed response never displays connected,
  exposes stale account text, or enables disconnect.
- The source archive remains byte-identical and is referenced by its existing
  SHA-256; the delta bundle has its own deterministic manifest and hash.
- Release preparation rejects unsafe archive members, baseline drift, extra or
  missing files, hash mismatch, timeout and existing release collisions.
- Activation writes old state and intent durably before pointer replacement;
  interrupted states use bounded reconciliation, not automatic retry.
- Final releases are root owned, directory 0755/file 0644, and proven readable
  but not writable by a real non-root worker identity.
- Activate/check consume the receipt-embedded trusted manifest and reject a
  substituted bundle, release, mode, owner, pointer, lock or transaction.
- The externally approved package-manifest SHA-256 is a required input.
  Every consumed JSON/overlay/source file is read from a trusted immutable
  object, and release/CSP metadata identities are revalidated at activate,
  check, reconcile and rollback boundaries.
- Check is repeatable. Rollback intent, pointer-side-effect boundaries and
  owned temporary links reconcile to completed, not-applied or UNKNOWN without
  blind retry or duplicate effects.
- Every command shares a finite process deadline; NaN, Inf, non-positive and
  excessive limits fail before side effects. Failure-receipt I/O gets only a
  fixed 100 ms tail budget; inability to persist it returns UNKNOWN.
- Inline script/style compatibility uses exact generated hashes and is tested
  in real Chromium; no unsafe-inline exception is added.
- Full source-package browser coverage (language selector, deep URLs, TikTok
  page and an actual Nginx response) is not claimed by the synthetic Chromium
  test and remains a later isolated acceptance check using the existing private
  archive. The 109 public routes are not recollected.
- Apex certificate issuance uses the proven Domestic
  /usr/local/bin/certbot 5.8.0 and a separately gated Tokyo ACME-only forward,
  never an early DNS switch.
- Any unresolved dynamic route forces cutover HOLD. The cross-object contract
  remains NOT_AUTHORIZED and intentionally provides no installer/sudo entry.
- Apex Nginx/TLS candidates use only the new server name and root namespace;
  `winctl` files and its certificate names are absent from mutation lists.
- Preview pages, controlled APIs, feedback persistence and real dynamic
  backends remain explicitly incomplete and are never reported as deployed.


## 2026-10-15 manual continuation: isolated OAuth source library

The existing static candidate and RG1 host evidence are reused. `deploy/pr122-oauth-candidate` is an **OFFLINE_LIBRARY_CANDIDATE_NOT_DEPLOYABLE**, not a replacement live portal. `scripts/pr122_build_oauth_candidate.py` verifies the Tokyo source archive and entry hashes, then derives passive session/store code and only the Douyin/TikTok service methods and OAuth helpers from the pinned source. The generated package has no trading/database imports, no master-key loader and no Tokyo runtime default. State and operations roots are explicitly supplied. Exchange/Finance/Telegram/WeCom capabilities are not implemented by this library. Original provider helpers are reused; source extraction changes are subject to independent review.

Local synthetic tests: 15 PASS, including complete fake Douyin/TikTok token/user-info callbacks, replay, redirect mismatch, missing inputs, exchange timeout, CSRF/origin, cross-form denial, expired forms, forbidden trading forms, restart persistence, file modes, import boundary and inventory redaction/wrong-host rejection. This is not live OAuth, a full exception/concurrency audit, protected state handoff, or server migration acceptance. The HTTP adapter, protected source-to-target custody, mixed administrative form successors, Telegram edge continuity and production root gate remain outstanding. No installer is supplied and no existing secret/database was copied.

Domestic GitHub channel: run38748827497 and bounded follow-up run38749282394 succeeded on `iZvt5t8tlrm8oiZ` as `githubrunner`. Existing `provider-neutral-domestic-bridge.service` is active as `openclaw_ops`, PID188767, cwd `/home/openclaw_ops/v8-domestic-operations/runtime/internal-bridge`. Observed loopback TCP ports include19444, not19443; no particular process-to-port association is inferred. `sudo -n -l` was unavailable to the Runner; this channel does not establish root installation authority. Read-only collection never exercised sudo commands. Production, DNS/TLS switch and Tokyo retirement remain HOLD.


### Subsequent HTTP adapter implementation (supersedes the HTTP-development TODO above)

The offline candidate now includes a loopback-only HTTP adapter factory. It preserves the existing OAuth form renderers and callback helpers; it does not start automatically, install a unit or provide a production CLI. Provider network calls default to disabled. Trading/finance/Telegram/miscellaneous submissions and TikTok disconnect are explicitly unavailable, not silently migrated. Required existing production routes must retain accepted successors before DNS can switch.

HTTP boundaries: exact Host and forwarded HTTPS identity, Origin and framing/content-type/body-size checks for secret submissions, duplicate form/framing rejection, no request/query/body logging, serialized state handling per server, one server/state root per process, bounded generic failures preserving evidence. Port bind failure releases the process-local factory lease. The shared original OAuth library's direct calls remain a review scope; an adapter-level lock does not establish cross-process exactly-once acceptance.

25 local tests PASS, including real isolated loopback HTTP health/form/submission/replay, Origin/Host/TLS rejection, forbidden-route503, external-provider calls disabled, body/framing/content-type limits, manifest completeness, port bind failure and root isolation, plus the15 original tests. Tests explicitly block and assert no urllib provider transport invocation; successful callback tests use fake clients and synthetic secrets only. GitHub CI for this increment must be checked separately. Status remains OFFLINE_HTTP_CANDIDATE_NOT_DEPLOYABLE. Still pending: protected live-state custody, non-OAuth caller successors, live bridge/channel acceptance, consolidated independent review and root/TLS/DNS execution gates.



### R1—R3 consolidated source correction (independent review pending)

This section supersedes the original inherited JSON persistence and token-first
callback behavior; it does not change previously accepted static RG1 bytes.
Audit reference: PR122 comment6195357263, HOLD_ALL_BLOCKERS_CONSOLIDATED.

R1: both provider state stores use a dedicated candidate-only SQLite database,
BEGIN IMMEDIATE, rollback journaling and synchronous=FULL. Consumption commits
before PASS; cross-process contenders see exactly one consumed state. A lost
commit acknowledgement remains unknown and cannot justify replay.

R2: sessions, credential values, metadata and redacted audit records share one
candidate database under the explicitly supplied private state root. A bounded
SQLite write transaction covers validation, attempt accounting, both Client Key
and Secret, and used_forms. It serializes separate sessions configuring the same
provider as well as duplicate calls on one session. Exceptions roll back all
uncommitted changes. A commit acknowledgement failure returns UNKNOWN, never
CONFIGURED; no blind retry is authorized. SQLite lock wait is at most5seconds.

R3: newly exchanged tokens stay in process memory until user_info verifies the
same exact unmasked open_id as the token response. A different previously bound
account is rejected, not silently rebound. Only then are Access/Refresh Token,
lifecycle and verified account binding activated in the same transaction. Failed
or uncertain exchange/user_info/storage returns REJECTED or UNKNOWN and preserves
the old committed generation. The TikTok existing-binding success fallback and
the alternate mutable lifecycle-file stores have been removed. Status also
requires an unexpired token generation matching the configured Client Key.

Storage boundary: this is a NEW candidate-only SQLite file, not trading.db and
not any Finance/credential_records table. Standard-library sqlite3 is used; no
trading/database package imports, master keys or live state are added. Existing
plaintext session/secret files cause LEGACY_*_HANDOFF_REQUIRED, rather than an
implicit migration. Root owner/mode and symlink/hardlink database checks apply.
No secrets are imported to GitHub or copied between hosts. Protected live-state
custody remains a separate uncompleted gate. No production format compatibility
or automatic restart of an existing portal is claimed.

Builder boundary: pinned Tokyo archive/entry SHA values remain provenance. After
R1—R3, the builder deliberately uses seven reviewed maintained source templates,
verifies the complete module MANIFEST, then copies exact bytes to a fresh output;
it does not regenerate vulnerable upstream persistence. Local rebuild compared
byte-for-byte with the candidate (including MANIFEST). The builder, all seven
modules, tests, workflows, governance and this document are included in the new
review artifact. Artifact hash and CI run bindings must be read from that exact
run; historical artifact hashes do not approve these changed bytes.

45 local tests PASS. New coverage uses actual forked processes, simultaneous
state/callback/submission races, every credential/activation write exception,
SIGKILL at state/write/commit boundaries, SIGTERM during uncommitted submission,
restart rollback recovery, lost commit acknowledgement, expiry/replay, wrong
Token/user identity, old/new account mismatch, user_info timeout, Client Key
rotation and old generation preservation. All provider responses and secrets
are synthetic; urllib provider transport is blocked. The new persistence paths
justify running the complete OAuth suite in hosted CI. Per Owner instruction,
no Domestic Runner workflow is changed or triggered in this correction round.
Domestic45-test execution is NOT_RUN; historical25 tests do not cover this new
version. The tunnel, bridge and all production services remain untouched.

SOURCE_FIX=DEVELOPER_TESTED_PENDING_INDEPENDENT_REVIEW. Provider calls remain
OFF by default. Production deployment, DNS/TLS, Tokyo retirement and PR99/P2
remain HOLD. No installer, sudo grant, SSH key or service activation is supplied.


### Persistent Owner execution adapter, 2026-10-16

Owner standing authorization covers Domestic/Tokyo website and server migration, controlled deployment, maintenance, backup and rollback. The first registered adapter is narrowly limited to the exact Tokyo legacy log_message correction independently approved in PR122#6204793589. It supplies four digest-bound operations: status/apply/rollback/revoke, no expiry, once-only mutation receipts, original-byte backup and unknown-state preservation. Future adapters require implementation/review under the same standing authorization; this is not generic root execution. The helper, embedded-payload installer and 20 synthetic filesystem tests are new review scope; the original16 Tokyo patch tests are inherited. DNS/retirement gates, website/current, bridge/tunnel and312efdd3 configuration remain unchanged. See deploy/pr122-portal-log-capability/README.md. This supplements the legacy-server adapter only; the OAuth candidate above still has no installer or production acceptance.

