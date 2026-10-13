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
