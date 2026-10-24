# Actual f131 image + original update checkpoint/recovery candidate

## Frozen product, distinct control code

The product image is permanently bound here to source
f13155ed63a3137d41766ee587d9b4b96a81477f / Tree
c31a9b1df006eeacd78ae3f9921073f3fe77d2c3. The checkpoint preparation's later
Git commit is CONTROL CODE, not that image's source or a new product image.
No rebuild, model test, connection probe, deployment or upload is performed.
Business/OCR31d3 and offline1e86 accepted scopes are reused.

The authoritative structured product receipt is
deploy/community-preview/f131-image-receipt.json. It records the root-scope
accepted artifact facts, not an execution grant:

| Evidence | Actual value |
| --- | --- |
| Actual image dispatch | Run40059478387, image Job120769700068 SUCCESS |
| Original push proof | Run40058542631, f131 source; distinct from image dispatch |
| Same-dispatch source artifact |12547170894,991730B, outer2a1250b4e8568c317b4d647aee43e351e57e5e690e4aef28a118b63ae839af35 |
| Source ZIP |125ec8633e173d582d5ca5cd3dccc21d2d97104723fb61a136911c48e12d47d1;427 files checked against f131 Git |
| Image artifact |12546452389,57016858B, outer c902a0663793cb3b99c4c5ab3156d4e9d1054d519d05403347ba20fdebbc061e |
| Inner image tar.gz |57365044B, eb7045414ced005a56158ac7eb54519098ec8a9e9da5589f939a0b3717d74875 |
| RELEASE image/config digest |sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a |
| OCI/env/file stamp |exact f131 source; stamp0444; User10001:1008 |
| Root verification |11 layer hashes; verify10+14+12 tests; NONROOT_READONLY_IMAGE_IMPORT PASS |
| Artifact expiry |2026-10-27 03:44:30 UTC |

The verify-target image is NOT the release image. Outer ZIP SHA, inner gzip SHA,
config/image ID and optional registry RepoDigest are different. RepoDigest is
not evidenced here and stays null. No registry publication is implied.

## Concrete implementation added, not an executed updater

community_preview_update_checkpoint.py adds real filesystem checkpoint code and
a serial coordinator over the original community_preview_upgrade inspect /
validate / command / mutate transport helpers. It NEVER invokes old main,
resume_rolled_back, historical image loading or hardcoded old2330 source IDs.
There is no new CLI, listener, HTTP action, secret/grant or cloud channel.
execution_enabled defaults false and no shipped entry point sets it true.
An external reviewed root composition remains REQUIRED; its absence is HOLD.
The boolean itself is not authentication or proof of Owner approval.

Journal code uses a root-owned0700 fixed proposed parent
/opt/xuanjun-community-preview/update-journal. It opens only a descriptor proven
to that exact parent and original no-follow parent-chain helper. It does not
create/chmod this parent; that would require a separately approved future host
action. Same-attempt directory/lock/active record/event/checkpoint writes happen
only when Journal is explicitly instantiated, not on import. This window uses
patched private temporary parents in isolated tests, never that server path.

There is one nonblocking EX lock across attempts, persistent active-attempt
binding, exact compiled plan digest, bounded no-follow/root0600/single-link file
reads, exclusive temporary files, append-only numbered event records, fsync
file+directory, atomic checkpoint-pointer replacement and partial-file/history
HOLD. Wrong owner thread, IO failure or fsync uncertainty poisons the object;
reopening partial state also refuses. No history or failed intent is deleted.
The global active record is not automatically cleared, including after success;
later archival/new-attempt policy needs root review, not an implicit new writer.

Before old stop: prove the exact release image is already loaded (ID/OCI/User
via narrow original image inspect), no colliding recovery name, and exact old
current container/isolation/mounts via original validate. No image pull/load or
database migration is added. A missing image refuses BEFORE stopping old.

Every mutation is preceded by durable intent and a SECOND immediate clock /
protected-binding recheck after that journal I/O. Default time.time floats are
supported; bool/nonfinite/backward clocks fail. Live observations must be fresh
within600s/+30s; config/data/route/isolation/backup identities cannot change.
The live reader must track the frozen old container ID across rename, not
silently substitute the new container at NAME. Original Docker mutation calls
are bounded by its original transport. Future readers must themselves be
bounded; no never-ending reader is claimed solved by the coordinator.

After old stop: prove exact old stopped/socket absent, retain old by unique
bound name, run exact release image with original run_argv resource/mount/
nonroot/port contract, persist actual new64hex ID, verify exact new identity and
remote health-source-image stamp/freshness, prove old still stopped, commit.
A timeout/missing ID/inspection/reader/binding uncertainty persists HOLD and
never turns into permission to restore/start old. Known completed nonmatching
health can enter explicit KNOWN_FAILURE; recovery is a separate guarded call.

Recovery can reload that known receipt from disk, recheck the new image/ID,
stop new, prove stopped/socket absent, retain failed new, restore retained old
ID/name and start old. The old process/DB health can pass without an old runtime
stamp, but preview remains HOLD. New-stop uncertainty cannot start old. A crash
or uncertainty during recovery leaves exact intent for manual same-attempt
inspection; it does not blindly resume a mutating step. Docker operations are
serial and recoverable under proved conditions, NOT an atomic transaction.
DB downgrade/backup restoration is not implemented or authorized automatically.

## Live bindings still required; no guessed evidence

Root's 03:00 old container/image/recheck OBSERVED and matching OCI
2330dd55c07f58d7f45a7c4510a9761d0d4735d6 remain historical observations. Do not
re-query connectivity here or treat their summary as exact current bindings.
Before any separately authorized execution, root must freeze/recheck:

1. Exact current old container ID/image ID and running/nonroot state; full
   original inspect projection (entrypoint/cmd/mounts/CPU/memory/swap/PIDs/network/
   readonly/privileged/capabilities/security/tmpfs/logs); no new published port.
2. Original config directory/three existing argument-file identity projections,
   original data/DB-root identity, own socket parent, community-route file digest
   only. No Env, private config/keys contents, DB bodies or P2 runtime/data reads.
3. Existing backup/recovery reference and compatibility evidence; source/receipt
   hashes and root-approved loaded release image ID. No invented backup path.
4. Fixed-parent no-follow fd opening, bounded real protected-binding reader and
   fixed-URL bounded health reader, plus exact root approval/attempt/executor
   composition. These readers are REQUIRED constructor dependencies, not
   implemented as unconditional authorization callbacks. Production defaults
   do not substitute synthetic test readers or request-body fields.

These are the minimal protection bindings, not a repeat connectivity survey.
If raw values were absent in the approved observation, root decides the next
minimal scope; this window does not probe the server or ask Owner to invent them.
Current compiled actual candidate still has current=null and actions=[] until
those bindings are available. Real checkpoint/coordinator source exists and is
testable independently; missing live composition is not hidden as completed.

## Authorization impact, explicitly not granted

Future host use would write ONLY the separately reviewed fixed root journal
parent/attempt files and invoke original community container inspect/stop/rename/
run/start over its existing Docker socket. It would preserve original read-only
config, writable data/account database and historical rollback containers. It
needs existing authenticated Workbench/sudo/root authority plus specific Owner
approval; no new user/role/secret/socket/permission/DNS/Nginx route is proposed.
Parent creation, exact image loading, snapshot/backup operation, updates and
rollback each remain outside this preparation's execution permission. There is
no permission to touch private data, enable OCR, run self-hosted or upload WeChat.

The isolated tests run actual journal fsync/locks/replace/history, process-lock
exclusion and reopen/recovery, with synthetic Docker/host/clock/health observations.
They explicitly patch only the temporary parent/file owner policy for a Hosted
nonroot fixture; production policy stays root. No mock result is a server receipt.

## Product vs later control SHA and official preview

Source evidence for this image is the actual dispatch40059478387 source artifact,
with push_evidence_run_id40058542631 used for later preview proof. The release
planner now retains that distinction instead of recommending a dispatch Run as
push evidence. Control-code CI validates ONLY this new coordinator/plan delta.
Its later source SHA is NEVER recorded as this f131 image's stamp.

The original official preview gate still requires original selected branch HEAD
==input/run frontend SHA==fresh remote backend SHA. Since later control commits
advance that branch, f131 image proof alone cannot admit a later HEAD's preview.
Do not move the branch backwards, weaken exact-SHA checks, use an old Run for a
new SHA, create another channel or pretend unchanged UI removes that rule.
Root must resolve the next exact product/preview candidate via the original
reviewed source/build path before a separately approved preview. Current health
runtimeSHA/freshness are UNKNOWN and preview remains HOLD. OCR production
permission/store/runtime availability remain independent and disabled.

## Concentrated root-review corrections after ba1b / f8cc

The root feedback is an isolated local journal/synthetic-Docker reproduction,
not a UK server incident. f8cc's incomplete new-health UNKNOWN handling is
preserved and extended to stale/incomplete non-ready reports too. This delta
changes only checkpoint source, its tests and this note; the accepted f131
image/receipt, workflow, planner, business/OCR and permissions remain unchanged.

1. **Durable intent is never a writer-state permit.** Before each mutation the
   coordinator now verifies its exact compiled argv and, AFTER the journal write,
   checks phase-specific old/new ID+image and running states. The live binding
   reader's running boolean is explicitly compared with that phase; it is no
   longer normalized to the initial running=True value. NEW_RUN requires old
   stopped and socket absent; every recovery rename/restore/start requires new
   stopped, old stopped and socket absent. An unexpected resurrection, socket or
   identity change durably enters HOLD without the blocked mutation or retry.
   Final commit/recovery also checks the writer pair after its checkpoint.
   These are observations at defined boundaries, not atomic control over another
   external root actor or a Docker transaction.
2. **Legacy recovery health is fresh evidence too.** Read the actual bounded
   health response first, then recheck clock/live binding; require exact integer
   HTTP200, fixed original URL, READY/process-DB scope, production=false and an
   integer observed_at within600s/+30s. Recheck the stopped new writer again
   after the response and after publishing rollback completion. Missing/expired
   response evidence is HOLD, never ROLLED_BACK. A legacy old runtime need not
   claim the new runtimeSHA/stamp. A future protected reader must prove the
   response timestamp; it cannot refresh cached data by assigning time at
   confirmation. No new live reader or server call is introduced here.
3. **Validate all journal records before any repair or resume.** Each event is
   read bounded/no-follow/root0600/single-link, parsed with exact canonical
   structure and required fields, exact plan digest, finite phase, integer
   sequence and valid new ID. Filenames must be a continuous1..N set; the event
   sequence follows allowed phase transitions and retains the same known new ID.
   The last full event must equal the checkpoint. Corrupt/partial JSON, extra or
   missing files, symlinks, hardlinks, wrong mode, oversized/noncanonical records,
   plan/sequence/phase/ID mismatch or missing checkpoint/active record fail closed
   without creating replacement history. Existing old-format valid records use
   the same canonical format; invalid history is retained for inspection, not
   migrated or silently rebuilt. This is protected-journal validation, not a
   cryptographic signature authenticating an independent root actor.

Added negatives reproduce old revival after NEW_RUN intent; new revival after
each recovery intent and after rollback health/final publication; socket or exact
image change after intent; legacy observed_at=1 with now1000 and all wrong/missing
time/URL/types; read-time expiry; malformed first event and the complete protected
history matrix. Every matrix subcase uses a new private test root; no stopped
journal is reset to PREPARED to obtain another test pass. Original lock, child
process exclusion, atomic/fsync and default-disabled assertions remain intact.

No site action, Docker execution, new credential/grant or production authority
is obtained from these synthetic tests. Actual protected current bindings and
reviewed host composition still remain required, with f131 product and later
control-code versions strictly separated.
