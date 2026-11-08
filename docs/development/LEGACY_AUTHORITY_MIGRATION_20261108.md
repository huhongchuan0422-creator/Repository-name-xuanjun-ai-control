# Canonical legacy ledger → FORMAL authority migration

> Candidate contract revision 2. Production execution remains prohibited until
> fresh independent QA, Security, Release and Platform approvals are recorded.

## Platform handoff contract

Platform owns production stop/start, backup, lock proof and root-controlled
trust key. Developer must not execute these commands against production:

```sh
python3 scripts/legacy_authority_migration.py probe --db "$DB"
python3 scripts/legacy_authority_migration.py create-freeze --db "$DB" --backup "$BACKUP" --backup-sha256 "$BACKUP_SHA256" --operation-id "$OPERATION_ID" --freeze-trust-key "$ROOT_KEY" --output "$FREEZE_RECEIPT" --ttl-seconds 300
python3 scripts/legacy_authority_migration.py apply --db "$DB" --backup "$BACKUP" --backup-sha256 "$BACKUP_SHA256" --expected-fingerprint 3e871a9911be87760cb7aa691113b570228f922a609b50ffbd2974e31b7ceb45 --freeze-receipt "$FREEZE_RECEIPT" --freeze-trust-key "$ROOT_KEY" --operation-id "$OPERATION_ID"
python3 scripts/legacy_authority_migration.py recover --db "$DB" --operation-id "$OPERATION_ID"
```

`probe` emits only canonical path, file hash, full schema fingerprint, pragmas,
integrity/classification and count; it never exports row content. Platform may
provide its JSON or a controlled read-only copy to QA. Unavailable production
backup evidence is not a PASS.

The canonical, HMAC-SHA256 freeze receipt binds operation, schema version,
DB/backup realpaths, device/inode, DB/WAL/SHM size/mtime/hash, backup SHA,
creation/expiry and STOPPED/NO_WRITER/lock state. Apply rechecks it immediately.
Query/recover verifies canonical receipt JSON, SHA-256 and operation/request/
source/backup/target/status/generation bindings. Any mismatch is `INTEGRITY_*`.
FORMAL requires the complete table/column/index/FK/CHECK/profile manifest;
pragma-only, partial or TEST_ONLY-shaped databases remain unknown.

This is an offline Platform runbook. It prepares authority schema; it does not
register historical tasks or create attempts, leases, fences, epochs, or P3
authority. A first registration must subsequently be made through the reviewed
formal identity verifier and CAS path.

The only accepted source is the exact canonical legacy schema fingerprint
`3e871a9911be87760cb7aa691113b570228f922a609b50ffbd2974e31b7ceb45`, with
`application_id=0`, `user_version=0`, and `quick_check=ok`. `user_version=0`
alone is never sufficient. Unknown, partial, TEST_ONLY, corrupt, wrong-file,
wrong-backup, unfrozen, symlink, and concurrently locked inputs fail closed.

`apply` first requires the ledger bytes to equal the verified, distinct backup,
then obtains an exclusive SQLite lock and performs every ALTER, conservative
backfill, table/index creation, profile write, version write, and receipt write
in one transaction. On a process/commit-window ambiguity, run `recover`: a
cryptographically and structurally valid `COMMITTED` receipt is authoritative;
`NOT_COMMITTED` means the transaction rolled back. A missing or mismatched
receipt is an explicit `INTEGRITY_*` rejection, never authoritative success or
generic UNKNOWN. Repeating a committed operation with a fresh freeze returns the same stored
receipt and performs no DDL.

Historical rows map `task_id=id` and remain `authority_state=NONE`, with no
valid lease, attempt, epoch, expiry, identity, or resource scope. The original
tables, rows, indexes, and data remain in place. Do not run against production
until an independent QA, Security, and Release review approves this new commit.
