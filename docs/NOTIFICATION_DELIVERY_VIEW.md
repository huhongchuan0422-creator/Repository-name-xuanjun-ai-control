# Notification delivery diagnostics — source preparation

PR17 registration6136334713; V2.7 1.10/1.12. Uses existing canonical
supervision_events and supervision_delivery. Never creates tables or a queue,
opens another connection, sends messages, retries, claims or records ACKs.

`delivery_page(db, now, expected_authority, limit=100, after=None, read_authority=None)` requires an
existing caller-owned transaction. expected_authority has verified generation
and epoch integers >=1. Actual producer mapping: ExecutionSupervisor._event writes tasks.fence into
supervision_delivery.authority_fence, independent of activation generation.
This view joins existing tasks(id,fence) and compares delivery authority_fence to
the current task fence; delivery authority_epoch must match expected epoch.
Missing tasks or stale fence/epoch stay visible with HOLD. Generation/epoch are
separately rechecked before and after the SQL read through REQUIRED read_authority
callback from the trusted existing ActivationStore/collector (return exactly
{generation,epoch}). Missing callback or changed activation rejects visibly.
The caller must still bind active descriptor UUID/instance and actual DB identity,
keep one pinned transaction across pages, and render errors without substituting
an empty queue. A caller-supplied callback is not cryptographic authentication.
Cursors carry no authority or snapshot proof.

Uses ordered keyset (event_key,destination), 1..100 rows/page plus one lookahead;
counts are THIS_PAGE_ONLY, never a purported global backlog. Consumers must read
until has_more=false or explicitly label a partial view. No 64-page global cap.
Actual canonical key forms are preserved: task:inventory:<64hex>,
task:terminal:kind, task:kind:sequence. Identity strings are bounded to300 ASCII
characters; event keys must agree with joined task/kind/sequence metadata.
Required canonical columns are checked. Missing schema rejects without migration.
Malformed event/destination identities reject the page as corrupt rather than
exporting arbitrary strings in cursors. Orphan event task remains visible/HOLD.
Raw details, tokens, claim owners and error messages are not selected; receipt
content is never returned, only presence. IDs are intended only for authenticated
Owner display, not public notification payloads.

Classification: PENDING/DELIVERY_FAILED -> RETRY_DUE/WAITING_RETRY based on known
time; CLAIMED -> CLAIM_ACTIVE/CLAIM_EXPIRED; SENDING/SENDING_UNCERTAIN ->
RECONCILIATION_REQUIRED; DEAD_LETTER/HELD -> MANUAL_REVIEW_REQUIRED. None triggers
action. ACKED needs a nonempty bounded receipt string or HOLD. ACK_RECORDED only
reports stored evidence; external_delivery_verified is always false here.
Unknown states/counters are UNKNOWN/null with HOLD, never success/zero. Unknown
retry or claim times cannot become due/expired by default.

Source fixture includes the exact _event method snapshot from verified P2artifact11783079460,
not a tasks(task_id) substitute. Production schema also has additional fields
which are deliberately not read. P2 shared modules remain unchanged. Tests use
in-memory fixture databases including readonly query mode and210 deliveries
across composite cursor boundaries, plus actual producer-shaped keys, taskfence4 with generation1/epoch2, stale taskfence/epoch and explicit generation rechecks. UK runtime, actual notification/ACK and Owner
UI integration NOT_RUN; no release/install permission. Integration must map this
view into the existing authenticated dashboard; no new HTTP service is provided.

Python3.6+ standard library. Run python3 -B -m unittest discover -s tests -p
test_notification_delivery_view.py -v (one shell command).

## Exact frozen-package integration evidence

PR17 registration6137242353 continues this same scope. Five additional tests load
the complete ExecutionSupervisor module and initialize its actual supplemental
schema in a temporary SQLite fixture with a minimal existing tasks(id,fence)
table. No P2 source is changed, no operational database is opened, and no model,
service, network sender or external ACK is invoked. ActivationStore is explicitly
a test fixture; this does not verify the production pinned-transaction caller.

Input is P2 artifact11786072168, source46a7c6796f61c6f196eb1d95497f2fb94e22fc00,
tar SHA25625999a0491a94ce8b9c1c24262ccba38bdfc737e32193ae2825c7de9202a205b,
manifest SHA2569c8ded6c3c17c88e76361085b8ee752f997d947c51506656099b22e033777d4c.
All77 manifest file hashes are checked before importing the producer. Extraction
is bounded and writes regular bytes only, never archive permissions or links.
Changed, missing or expired artifact fails the CI job; no latest-artifact fallback.

Set P2_INTEGRATION_ARCHIVE to the downloaded ZIP to run all35 tests. Without it,
the five package tests are explicitly skipped/NOT_RUN; the original30 tests are
not package-integration proof. CI fetches the fixed artifact with read-only Actions
permission and requires a nonempty archive before running. Added checks cover
actual constructor/schema and three event-key forms, readonly composite pagination,
restart/dedupe preserving dead letters, stale task fence/epoch and activation change.

Remaining real integration contract: Work, as sole P2 shared caller owner, must
call delivery_page inside the existing authenticated, pinned canonical read
transaction, supply current verified generation/epoch through the existing
activation reader, retain UUID/instance/file identity checks and label partial
pages. Bind that integrated package to its own artifact/manifest/CI and admitted
UK acceptance task. This producer compatibility result is not that caller wiring,
not OpenClaw pickup, not installed UK E2E and not release permission.
