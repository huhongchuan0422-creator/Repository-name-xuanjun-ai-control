# Canonical legacy ledger → FORMAL authority migration

This is an offline Platform runbook. It prepares authority schema; it does not
register historical tasks or create attempts, leases, fences, epochs, or P3
authority. A first registration must subsequently be made through the reviewed
formal identity verifier and CAS path.

The only accepted source is the exact canonical legacy schema fingerprint
`3e871a9911be87760cb7aa691113b570228f922a609b50ffbd2974e31b7ceb45`, with
`application_id=0`, `user_version=0`, and `quick_check=ok`. `user_version=0`
alone is never sufficient. Unknown, partial, TEST_ONLY, corrupt, wrong-file,
wrong-backup, unfrozen, symlink, and concurrently locked inputs fail closed.

Use a new operation id and the production values supplied by the migration
change ticket:

```sh
python3 scripts/legacy_authority_migration.py inspect --db "$LEDGER_COPY"
python3 scripts/legacy_authority_migration.py apply \
  --db "$LEDGER_COPY" --backup "$VERIFIED_BACKUP" \
  --backup-sha256 8e88a3d23159b9076e2e9513ef0076e812f7d0a695e19621295fb7b8a6f4fa1e \
  --expected-fingerprint 3e871a9911be87760cb7aa691113b570228f922a609b50ffbd2974e31b7ceb45 \
  --freeze-marker /run/xuanjun-authority/canonical-ledger.WRITE_FROZEN \
  --operation-id "$OPERATION_ID"
python3 scripts/legacy_authority_migration.py query --db "$LEDGER_COPY" \
  --operation-id "$OPERATION_ID"
python3 scripts/legacy_authority_migration.py recover --db "$LEDGER_COPY" \
  --operation-id "$OPERATION_ID"
```

`apply` first requires the ledger bytes to equal the verified, distinct backup,
then obtains an exclusive SQLite lock and performs every ALTER, conservative
backfill, table/index creation, profile write, version write, and receipt write
in one transaction. On a process/commit-window ambiguity, run `recover`: a
`COMMITTED` receipt is authoritative; `NOT_COMMITTED` means the transaction
rolled back and the same operation may be retried; `UNKNOWN` is a hold for
manual reconciliation. Repeating a committed operation returns the same stored
receipt and performs no DDL.

Historical rows map `task_id=id` and remain `authority_state=NONE`, with no
valid lease, attempt, epoch, expiry, identity, or resource scope. The original
tables, rows, indexes, and data remain in place. Do not run against production
until an independent QA, Security, and Release review approves this new commit.
