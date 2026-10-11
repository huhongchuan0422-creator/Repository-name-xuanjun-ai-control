# Work to UK OpenClaw intake: candidate and platform admission

Status: CANDIDATE_CODE_REVIEW_PASS; PLATFORM_NOT_DEPLOYED_NOT_ACCEPTED.
This is a delivery transport for the existing task authority, not another task
registry, dispatcher, release approver or production database.

## Existing execution is preserved

Owner relayed UK A1/A2 STARTED at 18:16 Asia/Shanghai, bound to control commit
76c0cfe7f7a4dd9ed52a9dc719897c95c437ba8b and spec SHA256
deb334171fdbc10d9ab8abff046493526ca5c992428d514629a86cf32859fc6a.
Evidence: evidence/uk-intake/OWNER_RELAYED_REPAIR_START_20261011.json.
This is a relayed receipt, not an independent host process probe. B waits for
A2_CONTRACT_FREEZE; C waits for real release admission. Intake upgrades and
documentation commits must not restart these tasks, reset their failure budget,
discard checkpoints or revive the failed release candidate.

## Implemented candidate protocol

1. The existing host-guarded UK push workflow conditionally calls only the
   separately installed, root-owned and hash-matching intake module as githubrunner.
   Without that installation it explicitly reports WAITING_PLATFORM_INSTALL.
2. Publisher checks fixed repository/branch/checkout and the Actions control SHA.
   It obtains raw commit/tree/blob bytes with replace refs disabled and controlled
   Git environment, and verifies each object's SHA. It executes no source file
   from the request. Spec/design bytes are transported as bounded data.
3. Validate approved maintenance kind/authority, spec digest, permissions all
   false, exact two-model policy, OAuth route, preserved bounded budget and roles.
   Complete envelope limit is 98,304 bytes; duplicate JSON keys and malformed
   object types fail closed. No CODEX_EXEC is submitted to the old Coordinator.
4. Publication key = SHA256(control SHA + newline + spec digest). Publication is
   immutable per source and serialized. Different control SHAs never overwrite
   each other's envelope. Consumer ignores envelopes outside the current detached
   Runner checkout and rechecks source after auth, immediately before a wake.
   This local freshness check is not a distributed task lease or A2 epoch fence.
5. Execution receipt key = SHA256(parent task + newline + spec digest). Thus a
   documentation SHA change cannot repeat the same work. A changed design under
   the same spec requires a new explicitly approved spec. The already manually
   started spec is imported as STARTED_OWNER_RELAYED without any model request.
6. Consumer is xuanjun_dev, never root; it wakes main only using the existing
   OpenClaw CLI/OAuth route. There is no sudo/runuser, new GitHub credential,
   copied OAuth token, paid model API, channel delivery, DB write or release action.
   Current wake adapter uses the already verified 5.6 fallback and does not probe
   the known unavailable primary. Primary recovery policy remains a separate
   task-boundary model gate; this adapter does not prove that gate complete.
7. A flock and fsync journal record DISPATCHING before Gateway interaction.
   Crash/timeout/unbound response retains effect-unknown state with no automatic
   retry. Main's RECEIVED/STARTED/WAITING_HUMAN is separately reported; a receipt
   never proves independent role start or production PASS. A durable marker may
   conservatively hold even when a send never occurred; reconciliation is explicit.
8. Fixed expected transport profile is status=ok / result.meta.agentMeta with
   provider=openai and the requested 5.6 model. Free text/unrelated JSON cannot
   attest a model. Actual installed Gateway profile and OAuth route must still be
   verified before unattended activation; a schema change holds, never guesses.
9. Every fresh, replayed and Runner-readable receipt is schema checked and
   whitelist sanitized. Unknown fields/raw diagnostics are never printed;
   production_pass and independent_role_start_probe are always false. FIFO,
   symlink, hardlink, wrong owner/mode, unstable file and oversized output fail.
   CLI capture is bounded while reading, not after unlimited buffering.

## Installation boundary: still NOT_VERIFIED

Do not run a generic sudo/systemd grant or another root model command. Integrate
these reviewed transport files into the same controlled installation/manifest
mechanism after the A2 platform contract freezes. Root copies pinned verified
bytes; smoke tests/model calls run only as the intended unprivileged identities.
No standalone unreviewed root installer has been executed or supplied here.

Required dedicated boundaries (actual users/groups must be inspected):

| Path | Owner/group | Mode | Purpose |
|---|---|---|---|
| /opt/xuanjun-work-intake | root/root | 0755 | Immutable to service users |
| /opt/xuanjun-work-intake/uk-work-intake.py | root/root | 0644 | Hash-bound installed module |
| /etc/xuanjun-work-intake.json | root/root | 0644 | Exact two fixed delivery paths |
| /var/lib/xuanjun-work-intake | root/root | 0755 | Protected parent |
| requests | githubrunner/xuanjun_dev | 02750 | Publisher writes; consumer reads |
| receipts | xuanjun_dev/githubrunner | 02750 | Consumer writes; Runner reads |
| Published envelopes / receipts | respective directory owner/inherited group | 0640 | Explicit fchmod under UMask=0077 |
| Intake lock | respective writer | 0600 | Advisory local serialization |

Templates: deploy/uk-work-intake/{config.json,xuanjun-work-intake.service,
xuanjun-work-intake.path,xuanjun-work-intake.timer}. Directory change events
propose immediate activation; the timer reconciles at boot (30 seconds) and
120 seconds after the consumer becomes inactive. The unit is oneshot,
unprivileged, NNP, PrivateTmp, with bounded CPU/memory/tasks. Template validation
is not evidence of systemd239 installation or runtime viability.

## Validation and remaining gates

Work local full regression: 242 PASS, including 20 intake tests. Negative cases
include concurrent duplicate wake, crash after durable marker, timeout/invalid
receipt, same spec/new SHA, changed design, forbidden model/API/permission/budget,
metadata spoofing, raw receipt secrets/false PASS, Git replace, auth-time source
change, malformed/duplicate JSON, true subprocess output bound, oversized envelope,
UMask/group-read preservation, symlink/hardlink/FIFO and root rejection.
Independent Work review initially FAIL; the reported blocking cases were fixed.
Final independent security rerun: 20/20 PASS, script SHA256
40d87f1deee7cd0a2183744ce385b80d278a34eeed136feb83683810a2b675e8.
This scope is Work intake, not the UK A1/A2 release artifact or production E2E.

Still required: controlled installed artifact/hash/owner/mode; real distinct-UID
read/write denial; real systemd239 timer/reboot; actual Gateway profile and OAuth
route; one approved new-source automatic receipt; replay/new-document-SHA no wake;
crash effect-unknown reconciliation and no customer/channel delivery. Production
loop, HTTPS dashboard, two tasks and migration retain their separate gates.

## Event delivery and task supervision are separate — 2026-10-11 19:00 CST

Owner relayed a live UK inspection: the installed module/config/inbox/receipt
directories and intake timer were absent. This confirms the missing installation
from a relayed inspection; Work has not independently probed those paths. An
approved source fetched by Runner cannot wake OpenClaw by itself.

The proposed delivery chain is GitHub push -> existing Actions/UK Runner ->
atomic immutable local envelope -> systemd.path -> the same non-root consumer.
The timer uses that same consumer for boot/missed-event reconciliation. Neither
unit polls GitHub or receives a public webhook. Both retain the identical
parent-task/spec deduplication journal, including the manually started A1/A2.
Events are hints, not durable acknowledgements; overlapping triggers are
serialized by the service/journal and the timer revisits durable requests.

Use PathChanged on the request directory, not DirectoryNotEmpty: immutable
envelopes remain after consumption and a permanently nonempty directory would
continuously reactivate the service. Receipts are written to a separate path;
consumer reads do not write the inbox. Lock/temp-file directory events can cause
a harmless pre-publication scan; atomic complete publication plus the timer
provides another opportunity. Existing contents at watcher startup are handled
by OnBootSec. No assumption of exactly-once events is made. Admission must test
event storms/start limiting, an event during a running consumer, watcher restart,
missed events and boot with an existing envelope. 120 seconds is a scheduling
interval, not a guaranteed end-to-end response SLA.

This transport is not a heartbeat watchdog and must not restart a task merely
because a model response or Agent session stopped. No separate task DB or lease
authority is introduced. The forthcoming A2 canonical ledger/broker must own
task leases, fences, process identities, persistent checkpoints and recovery.
Current source already has heartbeat/checkpoint/lease-expiry mechanisms, but
only a validated read-only CI_WAIT checkpoint is automatically requeued.
Other expired model/tool phases become WAITING_HUMAN for uncertain effects.
Do not advertise general automatic model-task recovery from these unit tests.

Lifecycle release requirements:
- Persist source/spec, phase, lease/fence/epoch, role identity, checkpoint,
  failure fingerprint, preserved remaining budget, next action and blocker.
- Observe actual Worker/session or cgroup progress separately from dispatcher
  liveness. Dispatcher heartbeats alone must not make a stuck child look active.
- A supervisor independent of the blocked model turn must detect process exit,
  stale progress and bounded runtime. Revoke the fence and stop/wait the actual
  unit/cgroup before a successor is admitted. Prove crash/reboot cases live.
- Reconcile a completed external action by its immutable idempotency identity;
  resume only mechanically proven safe steps. An unknown GitHub/model/publish
  effect stays HOLD/WAITING_HUMAN with cause, checkpoint and required action.
  No blind turn replay, budget reset or indefinite repair loop.
- Unlock B only on a validated A2 contract freeze and C only on actual release
  admission. QA/security must bind the final artifact. Continue independent
  ready tasks while an affected task waits for a human or Work review.
- Dashboard distinguishes last heartbeat, last progress, stale/paused/error,
  awaiting Work, WAITING_HUMAN and completion; never retain an unqualified
  STARTED badge after an unverified or expired heartbeat.

Work executes while its conversation or an explicitly configured run is active.
A chat response ending does not create a continuously running Work agent. The
UK supervised runtime must persist execution and surface any Work review
dependency explicitly. Neither this path unit nor the existing read-only hourly
check invokes Work to integrate a patch or approve a release.

No platform installation, model call, production change or repeated A1/A2 wake
was performed for this increment. Package the path/timer with the same frozen
A2 reviewed installation manifest; do not add a competing root installer.

## Current B security continuation delivery candidate

Work implements the approved continuation in the existing intake module, not a
second registry or dispatcher. Current source candidate SHA256:
3c1957c0dc247d18b5f67195509144f7e82f293c718fa39832d179e7cb9e59c9.
This supersedes the historical module digest for a future reviewed installation.
No installed module was replaced and no Gateway call was made by Work.

Publisher now exports the original pinned spec/design plus the exact existing
security-repair amendment from the same verified raw Git commit/tree/blob chain.
Only repair digest9b242998bd64ae1d900389af190de576c1ca876cd02a5b53cf2ff07292d3c5e1
is admitted, against original specdeb33417 and designfbe72ffb. Changing amendment
bytes, baseline, design or digest is rejected before wake. The effective contract
contains only role B, checkpoint7ed631a, current5.6-only policy and original
bounded budget; original spec bytes and manual A1/A2 receipt remain untouched.

Publication dedupe is control SHA plus active amendment digest. Delivery receipt
dedupe is original parent task plus active amendment digest. Thus an already
imported original manual start cannot suppress this approved B continuation,
while a documentation-only commit or repeated event cannot repeat its wake.
The native coordinator must still reconcile actual original B session/lease
and resume it rather than create a new task. Journal dedupe is not a distributed
lease or proof of a live Developer.

The historical base model pair is accepted only for the original exact pinned
spec. That base alone is imported without inference. Synthetic/new maintenance
specs must use current5.6-only/fallbacks=[]; the effective approved B continuation
and actual Gateway argv select5.6. Returned6.1/metadata mismatch remains rejected.

Local control regression252/252 PASS, including28 intake tests; Python3.6 syntax
PASS. New negative cases cover pinned revision forgery/changed baseline, B-only
role response, doc-SHA replay, old manual receipt separation, persistent crash
marker,6.1 policy revival, and actual effective Gateway instructions with no
--deliver. These are candidate code tests, not independent security approval,
installed cross-UID evidence or UK combination acceptance.

### Prepared package and acceptance inputs

Package these existing exact paths with the final A2 reviewed installation;
do not add a competing installer:

| Repository file | Installed target | Owner/mode | Required evidence |
| --- | --- | --- | --- |
| scripts/uk-work-intake.py | /opt/xuanjun-work-intake/uk-work-intake.py | root/root0644; parent0755 | final byte hash and immutable owner/mode |
| deploy/uk-work-intake/config.json | /etc/xuanjun-work-intake.json | root/root0644 | exact fixed inbox/receipts values |
| deploy/uk-work-intake/xuanjun-work-intake.service | /etc/systemd/system/xuanjun-work-intake.service | root/root0644 | oneshot nonroot identity, control-group stop, actual restrictions |
| deploy/uk-work-intake/xuanjun-work-intake.path | /etc/systemd/system/xuanjun-work-intake.path | root/root0644 | actual atomic-publication wake |
| deploy/uk-work-intake/xuanjun-work-intake.timer | /etc/systemd/system/xuanjun-work-intake.timer | root/root0644 | boot and inactive reconciliation |
| requests and receipts directories | /var/lib/xuanjun-work-intake/{requests,receipts} | distinct existing UID/groups02750 | cross-UID read/write denial and fsync receipt |

The existing UK workflow compares installed module bytes against control source
and refuses mismatched upgrades. Do not bypass that guard to get a wake. The
approved staged contract055d3ad1... is an execution/acceptance amendment, not a
new spec accepted by the old publisher schema.

Still unresolved before platform admission:
- full final A2/B frozen source, executable broker paths, units, manifest and
  corrected security report have not been received;
- review/installation of this new module with final A2 manifest and actual
  transport profile is not performed;
- pending older approved deliveries outside current detached checkout need
  provenance-preserving reconciliation; this increment does not relax freshness;
- result events triggering an actual Work execution run are not verified;
- canonical ledger unique writer, stop/recovery, database restore and private
  authenticated HTTPS remain live gates.

Freeze exact package before independent QA/security. Platform role must return
commands derived from actual final broker/unit/DB paths, previous protected
configuration and verified restore backup. Work will not invent those unavailable
paths or replace a failed release with a rollback target. No root/production
installation authority is added by this candidate.
