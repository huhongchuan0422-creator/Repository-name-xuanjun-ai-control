# Work approved bounded repair — Git-free import and activation contract

STATUS=DESIGN_APPROVED_FOR_BOUNDED_IMPLEMENTATION
EXECUTOR_DELIVERY=NOT_VERIFIED
RUNTIME_START=NOT_VERIFIED
RELEASE_ADMISSION=HOLD
PARENT_TASK=XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1
EXISTING_NODES=A_STAGE1_1.8_1.9_1.11_1.13_B_STAGE1_1.10_1.12
C_STAGE1_1.14_1.15=NOT_STARTED
MODEL_PRIMARY=openai/gpt-6.1-sol
MODEL_ONLY_FALLBACK=openai/gpt-5.6-sol

## Frozen evidence and decision

UK candidate 4bf32c009c433416ac1ef7ff7038fd4dcd29d7d2 is FAIL/HOLD and retained
as a repair baseline, not an installation source. Owner stopped repeated retries.
Archive c5368008106ec56c739bd594efda8cb161b6e16556c9d60dcd63aaa936a46062 and patch
82e81c2bbca62ff28dddab409f66ee53106283a1ebb3a9271c5c89b38e11aac0 were received.
Work verified the actual GitHub source 85ad1d7224485f3c57298e71a429eb576b8d943d
tree fd265cf40ac871cbaa93985cae28388e143739e8 and every source blob, rebuilt the
patch to fb8ee3bd3e2f175bcabc3eefe95aa182f3529b49 exactly as QA reported, and
verified manifest 7a721baadf570decf6fae72747394e84fdac29fe1432fcef4f44a4bd85bf9eaf
and all 33 bound files. This closes artifact identity, not QA/security defects.

This is a Work-approved control-plane maintenance design under the existing A/B
nodes, not a new task registry or proof that an executor has received/started it.
Only a new explicit design/spec revision may reset the failed attempt budget.
Do not resume the failed same-path retries or overwrite its checkpoint.
No Owner server command is currently required: uploaded artifacts replace the
earlier root data-copy request. No production activation is authorized here.

## A1: Replace shared Git worktree handoff with pure-data import

1. Export a fixed approved base from trusted Git blobs into a task-only snapshot.
   Worker gets no .git, Git worktree pointer/object/config/credentials. Do not
   use checkout/smudge or git operations in a Worker-writable directory.
2. Use a distinct Worker sandbox; dispatcher, importer and publisher private
   directories are unreachable. Worker has no ledger/production paths, publisher
   credential, root socket or sudo. Set UMask=0077 on dispatcher/importer/Worker.
   Default max_workers=1 until cross-task write access is disproved on the actual
   host using task-specific UID/mount containment. No shared-UID freeze claims.
3. Root broker proves the entire task unit/cgroup and descendants exited and
   there is no other writable entry into the snapshot. MainPID=0 or chown alone
   does not revoke open write FDs. Stop failure means no export/import.
4. Receive a bounded JSON delta as data, binding task/spec revision+hash/base
   commit+tree/generation/epoch/instance/fence/package hash. Each unique path has
   add/modify/delete, expected old blob SHA/mode, new bytes SHA/size/mode or null.
   Limits: <=128 changed paths, <=1MiB/file, <=8MiB decoded total; explicit
   trusted spec may tighten these. Reject duplicates, traversal, path collisions,
   symlinks/hardlinks/devices/FIFOs/sockets/gitlinks, .git in any component,
   changes to Git control attributes/config/modules and existing protected
   dispatch/CI/approval paths for ordinary tasks. Control-plane maintenance has
   separately reviewed scope; never weaken PROTECTED_PATHS to accept this repair.
   Mode changes/new executables require explicit approval. Unsupported baseline
   entries HOLD instead of silently dropping files. Diff is display, not protocol.
5. Hold directory/file FDs, use O_NOFOLLOW/fstat, and hash/read/copy the same
   bytes once. Freeze exact package into importer-private storage with external
   digest, fsync and atomic publish before consumption; reject changed inputs.
6. Importer has no GitHub/production credentials. In its private bare repo and
   single-use index, use fixed trusted /path/to/git, isolated HOME/config/cwd,
   hash-object --no-filters --stdin, update-index --index-info, write-tree and
   commit-tree with fixed parent. Do not execute git add/status/diff/commit/apply
   against Worker data. Private config/hooks/templates/alternates/replace refs
   cannot be Worker-controlled. Verify final tree delta and parent again.
   Display diff must disable external diff and textconv.
7. Replace prepare/commit/reconcile/freeze/push/PR assumptions together; do not
   patch only commit(). QA/test candidate code in a separate unprivileged
   no-credential/no-production sandbox, never dispatcher/importer/root installer.
   Root installer copies authenticated bytes only; entrypoint smoke runs under
   the isolated verification identity after staging.
8. Ledger persists package/tree/commit/publication identity. Repeat identical
   package returns the existing import result; changed digest/old fence rejects.
   Persist deterministic commit metadata before commit creation to reconcile
   crashes without duplicate commits. Unknown push/PR outcome reconciles actual
   remote before any retry; preserve Worker invocation and patch budget.
9. Publisher accepts only frozen allowed repo/branch/commit and expected remote
   SHA, performs CAS, and cannot execute Worker files. Existing Work connector
   remains the maintenance integrator. Runtime unattended publication needs a
   genuinely installed repo-scoped trusted publisher; Work chat availability is
   not a runtime daemon. No new Worker GitHub token or credential copy. If this
   capability is absent, mark only publication WAITING_HUMAN/PUBLISHER_NOT_READY.

Official Git semantics: https://git-scm.com/docs/git-config (filter clean executes
on check-in); https://git-scm.com/docs/git-hash-object (--no-filters);
https://git-scm.com/docs/git-update-index (--index-info imports known objects).

## A2: Durable single dispatcher and restore activation

1. One root-owned activation descriptor binds release/config/binary hashes,
   ledger UUID/generation, epoch, instance and canonical database path. Maintain
   monotonic epoch journal outside every restored database; restore/rollback
   never lowers epoch. Use fixed protected parent and activation lock.
2. Persist PREPARED -> QUIESCED -> ACTIVE via CAS and durable write boundaries.
   Before ACTIVE, stop the exact discovered legacy Coordinator, related parent
   unit and all old task cgroups, validate service identity, MainPID=0 and empty
   cgroups, and inhibit legacy restart. Unknown identity/status blocks activation.
   Existing new-dispatcher flock alone is not legacy exclusion.
3. All claim/heartbeat/checkpoint/finish, Owner decisions and broker launch/stop
   bind generation+epoch+instance+task fence and reject stale values. Lease/epoch
   loss stops the exact registered task unit and proves all descendants exited.
4. Preserve dispatcher NNP. An independent root broker on a private Unix socket
   validates peer UID, registered task, active epoch, fixed trusted binary and
   fixed task roots, then exposes launch/stop/status only. No arbitrary argv,
   command/unit/UID/path, shell, Python import, general manager grant or sudo.
   Verify the chosen property/transport behavior against actual systemd239.
5. Restore activator stops all DB users and Workers, keeps maintenance gate,
   verifies consistent backup/schema/PRAGMA/counts/hash/request state, restores
   into a fresh generation directory without old WAL/SHM, fsyncs DB/directories/
   epoch log and atomically switches descriptor. Reopen before marking ACTIVE.
   Retain old generations. Rollback uses a new epoch and explicit checkpoint
   reconciliation, not copying an active SQLite file or restoring stale epoch.
6. Crash at every durable boundary keeps dispatch disabled until log-driven
   reconciliation. Unknown external effects WAITING_HUMAN; safe CI_WAIT resumes
   only through existing verified rules with retained budget/fence.

## B: Canonical Owner decision endpoint and dependency verification

Callback must not maintain a separate task DB. Read the same activation
descriptor; preferable transport is a private ledger-service socket accepting
only APPROVE/REJECT with existing Owner/chat/HMAC/token/replay/request/fence
checks, then one atomic task/approval/event transaction. No arbitrary SQL.
Missing ledger/generation/socket is a bounded failure, never sqlite auto-create.
Callback has no generic DB-directory write, dispatcher HOME or root socket.
Dashboard reads the same generation and reports real epoch/heartbeat/full queue.
Do not change formal Telegram webhook during repair.

Do not hardcode absent /usr/bin/codex or /usr/bin/gh as already installed.
Discover the active verified Codex0.160.0 binary without reading credentials;
the proposed immutable binary/hash path goes into the reviewed install plan.
Confirm actual App Server support for Git-free cwd; do not guess an exec flag
or copy OAuth to Git. Runtime publisher dependencies must be verified separately.
Portable tests must not assume /usr/libexec/platform-python3.6 exists.
No paid API/other models; primary recovery is verified separately at a task
boundary, not inferred from catalog availability.

## Required independent negative tests on the same next frozen candidate

- Normal snapshot under production-like permissions can start and create/delete
  files; no dispatcher->worker->dispatcher worktree chown is required.
- Malicious .git pointer/config/include/clean/process/smudge/textconv/hooks/
  fsmonitor and Git-control files cannot execute as dispatcher/importer/publisher.
- Open write FDs, forked descendants, another task/same UID, ancestor replacement,
  symlink/hardlink/special entries and partial reads fail freeze/import closed.
- Wrong base/old hash/mode, duplicate/colliding/oversized/protected paths and
  stale spec/epoch/fence reject; exact accepted blob/tree/parent are verified.
- Import/commit/push/PR boundary crashes resume without repeated model/commit/PR.
- Concurrent old/new dispatcher, nonempty/stopping cgroup or broker failure
  cannot become ACTIVE; durable epoch survives DB restore and rollback.
- Missing/wrong canonical DB/generation never creates a second database;
  concurrent replayed APPROVE/REJECT produces exactly one authorized transaction.
- WAL with uncheckpointed committed rows survives backup/restore; old sidecars
  cannot contaminate new generation; PRAGMA/request/event state verified.
- NNP dispatcher works only through broker; arbitrary command/UID/path/unit and
  direct root acquisition remain rejected.
- Actual cross-UID permission, binary/user/broker install, unit inactive and
  production restore/HTTPS evidence remain PLATFORM_HOLD until field tested.

## Delivery/budget and release boundary

After reading this frozen Work source, executor returns source SHA, revised spec
hash, own working directory, model and start/blocked receipt. Work retains failed
candidate and old budgets; new repair budget <=20min per model attempt and <=3
patch rounds total, repeated same fingerprint pauses immediately. A1/A2 may be
parallel only in separate workdirs; B follows their shared descriptor/socket
contract. Freeze one integrated commit, external patch/manifest digests, raw test
outputs and independent QA/security reports. No self-reported aggregate PASS.
If code passes but platform is not proved, HOLD only affected activation/C tasks;
prepare reviewed install/rollback/evidence commands and human queue together.
No production DB/service/trading/webhook change is allowed in this repair scope.
