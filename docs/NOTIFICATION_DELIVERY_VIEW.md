# Notification delivery diagnostics — source preparation

PR17 registration6136334713; V2.7 1.10/1.12. Uses existing canonical
supervision_events and supervision_delivery. Never creates tables or a queue,
opens another connection, sends messages, retries, claims or records ACKs.

`delivery_page(db, now, expected_authority, limit=100, after=None)` requires an
existing caller-owned transaction. expected_authority has verified generation
and epoch integers >=1. Important legacy mapping: delivery.authority_fence stores
activation generation (ExecutionSupervisor._authority), not task writer fence.
All rows with mismatching generation/epoch stay visible with HOLD. The caller
must verify active descriptor/database identity before and after the read and
keep one transaction across pages; cursors carry no authority or snapshot proof.

Uses ordered keyset (event_key,destination), 1..100 rows/page plus one lookahead;
counts are THIS_PAGE_ONLY, never a purported global backlog. Consumers must read
until has_more=false or explicitly label a partial view. No 64-page global cap.
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

Source fixture uses the exact required column names from P2artifact11783079460,
not a tasks(task_id) substitute. Production schema also has additional fields
which are deliberately not read. P2 shared modules remain unchanged. Tests use
in-memory fixture databases including readonly query mode and210 deliveries
across composite cursor boundaries. UK runtime, actual notification/ACK and Owner
UI integration NOT_RUN; no release/install permission. Integration must map this
view into the existing authenticated dashboard; no new HTTP service is provided.

Python3.6+ standard library. Run python3 -B -m unittest discover -s tests -p
test_notification_delivery_view.py -v (one shell command).
