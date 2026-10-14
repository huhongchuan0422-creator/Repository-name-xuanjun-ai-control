# UK dispatcher controlled rollout (candidate only)

This repository does not activate production. The old Coordinator, trading
permissions, production webhook and production database remain unchanged.

## Admission and backup

1. Freeze the reviewed commit and independently verify the service, config and
   exact artifact hashes. Create the dedicated `xuanjun-dispatcher` and
   `xj_codex_worker` identities; the worker must not belong to production,
   Docker or trading groups. Keep the ledger `0600` and unreadable to the worker.
2. Stop before mutation if the configured repository `HEAD` is not the approved
   `source_commit`, config validation fails, `gh`/Codex managed authentication is
   absent, or an old/new dispatcher ownership decision is unresolved.
3. While holding the existing database writer's maintenance gate, make a
   consistent backup:

       python3 stage1/ledger_backup.py --backup LIVE.sqlite BACKUP.sqlite

   Save the returned SHA-256 outside Git. Verify and perform a restore rehearsal
   into a new path using `--stage-restore ... --expected-sha256 ...`. Never copy
   an active SQLite file directly.

## Canary and switch

1. Install into the deterministic `integration-<manifest_sha256[0:16]>`
   directory under `/opt/xuanjun-control-releases`. This typed directory name
   is not the artifact identity: every runtime `release_sha256` is the complete
   64-lowercase-hex manifest SHA-256. Render units with the exact immutable
   directory name. Runtime units must not follow a mutable release symlink. The
   schema-2 installer additionally requires the externally frozen commit and
   tree; it verifies `HEAD`, `HEAD^{tree}`, the authorized parent, manifest
   SHA-256 and every installed file before staging anything.
2. Render the v2 dispatcher and root-broker configs from the checked-in
   templates. Bind release/config/Codex hashes, ledger UUID, generation, epoch,
   instance and both private sockets. Place the exact reviewed units for
   `xj-root-broker.{socket,service}`, `xuanjun-ledger.{socket,service}`, the
   dispatcher, callback, dashboard and GitHub intake timer; do not substitute
   an old helper, old `--db` callback argv or a mutable path.
3. Run `development_service.py --check-config`; start the unit with no ready
   CODEX_EXEC rows and confirm a second instance fails its dispatcher lock.
4. Verify a disposable approved task: unique worktree, transient
   `xj-codex-*` systemd unit, bounded CPU/memory/tasks, worker UID unable to read
   the ledger or any production DB/credential path, exact-source branch push,
   frozen CI and independent QA evidence. This is not production acceptance.
5. Only after Release Gate approval, quiesce the old development dispatcher,
   reconcile all leases/checkpoints, then enable the new unit. Do not insert
   CODEX_EXEC into the old Coordinator.

## Rollback

Rollback requires a reviewed immutable JSON map, never a `current` or version
symlink. The map binds the exact previous release directory, complete previous
manifest and artifact SHA-256 values, previous and stopped activation epochs,
an affirmative empty-cgroup observation, and every direct unit/config target to
its expected rendered SHA-256 and backup path below that previous immutable
release directory. Reject a stale epoch, symlink, hash mismatch, missing target,
unexpected target, reused backup path or non-empty cgroup.

Stop the new unit, wait for its cgroup to become empty, fence/revoke its epoch,
and retain its ledger/worktrees/evidence. Verify all map identities and backup
bytes before replacing anything. Restore configs first and units second from
their direct immutable backup paths, verify every restored hash, run config
validation, and only then reactivate the prior dispatcher after proving it owns
no overlapping live lease. On any failure, leave services stopped and preserve
the evidence. If database restoration is required, stage and verify the saved
backup first, then atomically replace the stopped database under the
single-writer maintenance gate. Unknown effects go to WAITING_HUMAN; never
replay a model turn, commit, push or PR creation.
