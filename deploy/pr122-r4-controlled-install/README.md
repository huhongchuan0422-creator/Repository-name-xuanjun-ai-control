# R4 controlled installation plan candidate — NOT RELEASED

PR122#6205371670 accepts temporarily disabling TikTok HTTP disconnect. The
candidate source and its actual-source18 tests are inherited unchanged.
Full artifact-byte review and this new root installation plan still need
independent acceptance. Do not execute this script based only on source approval.

## Fixed implementation and reuse

`controlled_install.py` is a standalone Owner-root action, not a new sudo grant
or general execution channel. It accepts only --install, --status and the
emergency --rollback-offline action, on the exact Tokyo host. No arbitrary path,
service, command, payload or environment input is accepted. Owner's standing
Domestic/Tokyo migration authorization remains valid, but the existing Runner
helper cannot install a different patch; this action needs actual admin/root
execution after plan approval. No new SSH key, service, timer or queue is created.

The script verifies and executes the already installed root-owned helper bytes
SHA2560e61a4ca...2cbcbe in a private Python module, changing only that in-memory
module's fixed source/candidate/builder pins. The original root helper, sudoers,
grant and receipt are not replaced. The exact accepted1859-byte R4 builder is
embedded and hash-checked, not loaded from an admin-writable checkout.

## Installation sequence

1. Require root, Tokyo host, trusted root directories and exact existing helper.
   Acquire nonblocking old-helper lock and a separate fixed R4 execution lock.
2. Refuse previous R4 state/public receipt; require exact current source d5ab592a,
   candidate57e38fc9, source identity and an active expected Portal service.
3. Create root0700 R4 state; preserve original source root0400, grant/receipt0600.
   Reuse the engine's once-only apply marker, atomic source replacement and one
   bounded Portal restart. No automatic cleanup, retry or rollback occurs.
4. Require exact new source and a fresh active admin Portal PID; check actual
   two-site health GET200/HEAD501. Only then propose four empty synthetic POSTs
   (two sites, absent vs fake untrusted headers) to the now-disabled path. Before
   each, recheck exact guarded source. Require TLS-verified403, exact fixed JSON
   and no cookie. No real account, session, authorization or request body is used.
   **These negative requests are part of this pending installation-plan review,
   not authorized merely by the existing source-only approval.**
5. Retain root private receipt/backup and publish only allowlisted operational
   metadata in root-owned0644 /var/lib/xuanjun-pr122-r4-containment-receipt.json.
   Existing non-root Runner can later collect it and independently recheck source,
   service/home/current without exposing private source backups or credentials.

The exact branch stops before lifecycle-store construction. Source identity,
new-process identity, inherited18 isolated tests and fixed403 response establish
the application-level containment argument; no real OAuth state/Token/account
snapshot is read or exported. This is not full authentication or general WAF
acceptance. Other site's static files, DNS, Nginx config, bridge/tunnel and VM
state remain unchanged.

## Explicit emergency rollback

Never automatic and not a normal acceptance step. --rollback-offline requires
the exact guarded current source, exact root0400 old backup and an unused rollback
marker. Stop ONLY Portal, require MainPID0/inactive (or failed), THEN restore the
exact previous source. Keep Portal stopped; do not restart vulnerable old code.
Receipt says ROLLED_BACK_BACKEND_STOPPED, not PASS. Static Nginx/VM stays up, but
dynamic routes will be unavailable. This outage behavior requires the independent
plan's explicit acceptance. Recovery/restart needs an independently reviewed
safe plan; the backup is not permission to reopen the old disconnect vulnerability.
If stop cannot be confirmed, do not restore; preserve current code and evidence.

## Tests and operations notice

19 tests use a temporary filesystem, a synthetic source, injected service/network
actions and the unchanged real transaction-engine code. Hosted root is only an
ephemeral test identity; local namespaceUID fallback is test-only. No production
root preflight, install, restart, POST, disconnect or rollback is executed by CI.
No new claim is made about already approved18/44/83/115 tests; they are not rerun.

After successful approved installation, tell operations: **TikTok HTTP disconnect
is temporarily unavailable for every caller, including administrators.** This
does not disconnect any existing account. Restore capability only after completing
identity, ownership, CSRF/Origin, concurrency and failure-recovery review.
