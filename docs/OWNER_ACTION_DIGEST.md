# Owner action digest (source preparation)

Parent PR17, scope registration 6135848335, V2.7 node 1.10. Source writer DOTS.

`build_digest(snapshot, now, limit=100, max_age=300)` consumes the existing
`owner_dashboard.snapshot()` result. It does not query a database, add a queue,
notify the Owner, approve, resume or launch work. Existing P2 dashboard/outbox
ownership is unchanged. No runtime integration is claimed in this PR.

The caller must obtain the snapshot through the existing authenticated Owner
surface, bind its activation to the current canonical ledger and re-read live
state before any action. Neither a source string nor the digest authenticates
input. VIEW_READY only means this sanitized view passed consistency checks.
A digest is a display/cache identity, never an approval token or dedupe key for
runtime execution. Display freshness is checked against caller-supplied time.

Input: dictionary with source=CANONICAL_LEDGER_READ_ONLY, observed_at, counts,
human_queue. The human_queue contains all WAITING_HUMAN tasks independently of
the truncated recent-task window. Missing queues or >10000 rows reject rather
than silently truncate. Above this bound, integration must use an explicitly
complete paged snapshot, not pretend this projection was complete.

Output groups by sanitized checkpoint error_code/reason. Full group/invalid/
duplicate/omitted/conflict counts are retained even when display is limited to
1..500 rows. Identical projected task/fence rows collapse; conflicting versions
remain visible with HOLD. No latest-writer election is inferred. Unknown reason,
wrong state, invalid IDs/fences, stale/future timestamps and source/count mismatch
are explicit HOLD. Checkpoint output is limited to phase, commit and reason;
raw prompts/logs/dependencies/credentials are never copied. The authenticated UI
must render text as text and keep task identifiers within its authorized audience.

Run `python3 -B -m unittest discover -s tests -p test_owner_action_digest.py -v`.
Python 3.6+ standard library only. Hosted CI and local compatibility are separate
from UK installation, UI integration, actual notification and acceptance, all
NOT_RUN for this source-only module. No release/install permission is granted.
