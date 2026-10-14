# Notifier isolation candidate — scope PR17:6151722263

EXECUTION_CANDIDATE_REVIEW_PENDING. This is a proposal, not an execution receipt.
Original task/branch/transaction retained. Frozen95 runtime source2516b8ad/artifact11833404272 unchanged.

Script: evidence/p2-install-preparation-20261013/notifier_isolation_candidate.py
SHA256: 967204b970c39191eb3eff5e71a61fa0adab3be898dbf8f1fdb61131dfabb11e
Tests SHA256: 026a0710692862773241d89eaa45b332e1a15294ed5d9d935135677e76726bc0
Local Python3.12.14:13/13PASS including exclusive backups and fsynced receipt in disposable Root-owned scratch; external systemctl/cgroup effects simulated.
CI invokes ONLY tests. UK job non-root; Root scratch case SKIP rather than sudo. UK Python3.6 compatibility pending CI. No automatic production invocation.

## Exact operation
Only xj-uk-owner-notify.timer/service. Fixed unit and owner_notify.py digests from PR17:6151692924; fixed UK/root guard.
Existing legacy-isolation.lock validated/held exclusively. Seven original receipt/backup digests checked; four old units remain masked/quiet.
Save original full unit bytes/UID/GID/mode/enabled states in exclusive0600 backups; NEW Root0700 dir:
 /var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/notifier
Existing notifier dir => HOLD; never replay or overwrite.
Pinned dirfd protects backup/receipt/mask writes; fsync files+directories.
Order:durable backups → TIMER_STOP_INTENT → stop TIMER → prove quiet → SERVICE_STOP_INTENT → stop SERVICE → prove quiet → per-unit MASK_INTENT → atomic mask → RELOAD_INTENT → daemon-reload → exact masks/PID/nested cgroups/oldDB FD check.
Recheck unit identity/content, script, prior evidence and DB file set/inode/content before effects; DB/WAL/SHM/journal retained. FD scan matches canonical/deleted names and inode aliases. Denied/racing processes or cgroup traversal => HOLD.
No enable/disable/start/restart/kill/messages/outbox/DB/Fence/Lease/Epoch/NSS/RPM/TLS/P2 install.
Existing enablement symlinks preserved while direct unit is masked.

## Execution delivery after independent acceptance
Exact script is to be executed through existing UK entry only AFTER exact-candidate acceptance. Future wrapper must verify this SHA before root CLI.
CLI:
python3 -I -B evidence/p2-install-preparation-20261013/notifier_isolation_candidate.py --candidate-acceptance PR17:<actual-independent-review-comment-id>
Argument is audit provenance only, NOT authentication or approval. Do not substitute scope approval6151722263 for candidate acceptance.
Expected success:AUTHORIZED_NOTIFIER_ISOLATED; exact two inactive/dead/masked, servicePID0, nested cgroup empty, scoped FD scan complete, original evidence/DB unchanged.
Root-private notifier-isolation-receipt.json and backups must be rehashed and reported to PR17.
Crash/partial failure: durable HOLD or last intent preserved. Inspect exact current state; do not blindly rerun, restore, start or resend.
No automatic rollback/restart: restoring notifier may emit historical messages, so recovery requires separately reconciled scope.
Scope success does not prove global writer exclusion or grant P2 release.

RELEASE=HOLD INSTALL=NO WRITER_ADMISSION=NO
